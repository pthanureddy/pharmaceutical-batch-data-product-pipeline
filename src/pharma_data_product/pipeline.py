from __future__ import annotations

import hashlib
import json
import time
import uuid
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from pharma_data_product.models import BatchEvent, ValidationError, canonical_json
from pharma_data_product.store import DataProductStore


@dataclass(slots=True)
class IngestionResult:
    run_id: str
    input_count: int = 0
    accepted_count: int = 0
    duplicate_count: int = 0
    quarantined_count: int = 0
    late_count: int = 0
    conflict_count: int = 0
    duration_ms: int = 0
    status: str = "COMPLETED"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class StreamProcessor:
    """Deterministic micro-batch processor with deduplication and event-time watermarks."""

    def __init__(
        self,
        store: DataProductStore,
        *,
        allowed_lateness: timedelta = timedelta(minutes=15),
        micro_batch_size: int = 100,
    ) -> None:
        if allowed_lateness < timedelta(0):
            raise ValueError("allowed_lateness must not be negative")
        if micro_batch_size < 1 or micro_batch_size > 10_000:
            raise ValueError("micro_batch_size must be between 1 and 10000")
        self.store = store
        self.allowed_lateness = allowed_lateness
        self.micro_batch_size = micro_batch_size

    def ingest_json_lines(self, lines: Iterable[str]) -> IngestionResult:
        def decoded() -> Iterable[dict[str, Any]]:
            for line_number, line in enumerate(lines, start=1):
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as exc:
                    yield {
                        "__invalid_json__": True,
                        "line_number": line_number,
                        "raw": line.rstrip("\n"),
                        "message": str(exc),
                    }
                    continue
                if isinstance(value, dict):
                    yield value
                else:
                    yield {
                        "__invalid_json__": True,
                        "line_number": line_number,
                        "raw": line.rstrip("\n"),
                        "message": "line must contain a JSON object",
                    }

        return self.ingest(decoded())

    def ingest(self, raw_events: Iterable[dict[str, Any]]) -> IngestionResult:
        result = IngestionResult(run_id=str(uuid.uuid4()))
        started = datetime.now(UTC)
        timer = time.perf_counter()
        batch: list[dict[str, Any]] = []

        for raw in raw_events:
            batch.append(raw)
            if len(batch) >= self.micro_batch_size:
                self._ingest_batch(batch, result)
                batch = []
        if batch:
            self._ingest_batch(batch, result)

        completed = datetime.now(UTC)
        result.duration_ms = max(0, round((time.perf_counter() - timer) * 1000))
        run = result.as_dict()
        run.update(started_at=started.isoformat(), completed_at=completed.isoformat())
        with self.store.transaction():
            self.store.record_run(run)
        return result

    def _ingest_batch(self, raw_events: list[dict[str, Any]], result: IngestionResult) -> None:
        with self.store.transaction():
            for raw in raw_events:
                result.input_count += 1
                self._ingest_one(raw, result)

    def _ingest_one(self, raw: dict[str, Any], result: IngestionResult) -> None:
        if raw.get("__invalid_json__") is True:
            raw_text = str(raw.get("raw", ""))[:16_384]
            self._quarantine(
                result,
                event_id=None,
                code="INVALID_JSON",
                message=f"line {raw.get('line_number')}: {raw.get('message')}",
                raw_text=raw_text,
            )
            return

        raw_text = canonical_json(raw)
        try:
            event = BatchEvent.from_mapping(raw)
        except ValidationError as exc:
            self._quarantine(
                result,
                event_id=str(raw.get("event_id")) if raw.get("event_id") is not None else None,
                code="CONTRACT_VIOLATION",
                message=str(exc),
                raw_text=raw_text[:16_384],
            )
            return

        existing_digest = self.store.existing_digest(event.event_id)
        if existing_digest is not None:
            if existing_digest == event.digest:
                result.duplicate_count += 1
                return
            self._quarantine(
                result,
                event_id=event.event_id,
                code="EVENT_ID_CONFLICT",
                message="event_id was reused with a different canonical payload",
                raw_text=raw_text,
            )
            result.conflict_count += 1
            return

        watermark = self.store.watermark(event.partition_key)
        if watermark is not None and event.occurred_at < watermark - self.allowed_lateness:
            self._quarantine(
                result,
                event_id=event.event_id,
                code="LATE_EVENT",
                message=(
                    f"occurred_at {event.occurred_at.isoformat()} is older than partition "
                    f"watermark {watermark.isoformat()} minus allowed lateness"
                ),
                raw_text=raw_text,
            )
            result.late_count += 1
            return

        self.store.insert_event(event)
        self.store.advance_watermark(event)
        self.store.refresh_batch(event.batch_id)
        result.accepted_count += 1

    def _quarantine(
        self,
        result: IngestionResult,
        *,
        event_id: str | None,
        code: str,
        message: str,
        raw_text: str,
    ) -> None:
        self.store.record_issue(
            event_id=event_id,
            code=code,
            message=message,
            raw_digest=hashlib.sha256(raw_text.encode()).hexdigest(),
            raw_payload=raw_text,
        )
        result.quarantined_count += 1

