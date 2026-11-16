from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from pharma_data_product.models import BatchEvent, ValidationError, canonical_json


class Blob(Protocol):
    def download_as_text(self, *, encoding: str = "utf-8") -> str: ...

    def upload_from_string(self, data: str, *, content_type: str) -> None: ...


class Bucket(Protocol):
    def blob(self, name: str) -> Blob: ...


class StorageClient(Protocol):
    def bucket(self, name: str) -> Bucket: ...


class BigQueryClient(Protocol):
    def insert_rows_json(
        self,
        table: str,
        rows: list[dict[str, Any]],
        *,
        row_ids: list[str],
    ) -> list[dict[str, Any]]: ...


@dataclass(frozen=True, slots=True)
class LandingResult:
    input_count: int
    accepted_count: int
    quarantined_count: int
    quarantine_object: str | None


class GcpLandingJob:
    """Validate one Cloud Storage NDJSON object and land rows in BigQuery.

    BigQuery insert IDs reduce duplicate streaming inserts but do not replace the deterministic
    event-ID MERGE and quality controls in the curated SQL layer.
    """

    def __init__(
        self,
        *,
        storage: StorageClient,
        bigquery: BigQueryClient,
        bucket: str,
        object_name: str,
        raw_table: str,
        quality_table: str,
        quarantine_prefix: str = "quarantine",
        now: Callable[[], datetime] | None = None,
    ) -> None:
        for field, value in {
            "bucket": bucket,
            "object_name": object_name,
            "raw_table": raw_table,
            "quality_table": quality_table,
        }.items():
            if not value.strip():
                raise ValueError(f"{field} must not be empty")
        self.storage = storage
        self.bigquery = bigquery
        self.bucket_name = bucket
        self.object_name = object_name
        self.raw_table = raw_table
        self.quality_table = quality_table
        self.quarantine_prefix = quarantine_prefix.strip("/") or "quarantine"
        self.now = now or (lambda: datetime.now(UTC))

    def run(self) -> LandingResult:
        bucket = self.storage.bucket(self.bucket_name)
        text = bucket.blob(self.object_name).download_as_text(encoding="utf-8")
        ingested_at = self.now().astimezone(UTC).isoformat()
        raw_rows: list[dict[str, Any]] = []
        raw_ids: list[str] = []
        issues: list[dict[str, Any]] = []

        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                decoded = json.loads(line)
                if not isinstance(decoded, dict):
                    raise ValueError("line must contain a JSON object")
                event = BatchEvent.from_mapping(decoded)
            except (json.JSONDecodeError, ValidationError, ValueError) as exc:
                issues.append(self._issue(line_number, line, str(exc), ingested_at))
                continue

            raw_rows.append(
                {
                    "event_id": event.event_id,
                    "event_digest": event.digest,
                    "event_type": event.event_type.value,
                    "occurred_at": event.occurred_at.isoformat(),
                    "site_id": event.site_id,
                    "line_id": event.line_id,
                    "batch_id": event.batch_id,
                    "material_id": event.material_id,
                    "source_system": event.source_system,
                    "sequence_no": event.sequence_no,
                    "payload_json": canonical_json(event.payload),
                    "ingested_at": ingested_at,
                    "source_object": f"gs://{self.bucket_name}/{self.object_name}",
                }
            )
            raw_ids.append(event.event_id)

        if raw_rows:
            errors = self.bigquery.insert_rows_json(self.raw_table, raw_rows, row_ids=raw_ids)
            if errors:
                raise RuntimeError(f"BigQuery raw insert returned {len(errors)} error entries")

        quarantine_object = None
        if issues:
            issue_ids = [str(issue["issue_id"]) for issue in issues]
            errors = self.bigquery.insert_rows_json(
                self.quality_table,
                issues,
                row_ids=issue_ids,
            )
            if errors:
                raise RuntimeError(f"BigQuery quality insert returned {len(errors)} error entries")
            timestamp = self.now().astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
            object_digest = hashlib.sha256(self.object_name.encode()).hexdigest()[:12]
            quarantine_object = f"{self.quarantine_prefix}/{timestamp}-{object_digest}.ndjson"
            payload = "\n".join(json.dumps(issue, sort_keys=True) for issue in issues) + "\n"
            bucket.blob(quarantine_object).upload_from_string(
                payload,
                content_type="application/x-ndjson",
            )

        return LandingResult(
            input_count=len(raw_rows) + len(issues),
            accepted_count=len(raw_rows),
            quarantined_count=len(issues),
            quarantine_object=quarantine_object,
        )

    def _issue(
        self,
        line_number: int,
        raw_line: str,
        message: str,
        recorded_at: str,
    ) -> dict[str, Any]:
        bounded = raw_line[:16_384]
        digest = hashlib.sha256(bounded.encode()).hexdigest()
        return {
            "issue_id": f"{digest[:24]}-{line_number}",
            "event_id": None,
            "issue_code": "CONTRACT_VIOLATION",
            "issue_message": f"line {line_number}: {message}"[:1_024],
            "raw_digest": digest,
            "raw_payload": bounded,
            "source_object": f"gs://{self.bucket_name}/{self.object_name}",
            "recorded_at": recorded_at,
        }


def _required_environment(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"required environment variable {name} is missing")
    return value


def main() -> None:
    from google.cloud import bigquery, storage

    project = _required_environment("GCP_PROJECT")
    result = GcpLandingJob(
        storage=storage.Client(project=project),
        bigquery=bigquery.Client(project=project),
        bucket=_required_environment("RAW_BUCKET"),
        object_name=_required_environment("INPUT_OBJECT"),
        raw_table=_required_environment("BIGQUERY_RAW_TABLE"),
        quality_table=_required_environment("BIGQUERY_QUALITY_TABLE"),
    ).run()
    print(json.dumps(asdict(result), sort_keys=True))


if __name__ == "__main__":
    main()
