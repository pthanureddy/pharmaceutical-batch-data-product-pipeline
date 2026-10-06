from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any


class ValidationError(ValueError):
    """Raised when an event violates the bounded input contract."""


class EventType(StrEnum):
    BATCH_STARTED = "BATCH_STARTED"
    STEP_COMPLETED = "STEP_COMPLETED"
    QUALITY_RECORDED = "QUALITY_RECORDED"
    BATCH_RELEASED = "BATCH_RELEASED"


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$")
_REQUIRED = {
    "event_id",
    "event_type",
    "occurred_at",
    "site_id",
    "line_id",
    "batch_id",
    "material_id",
    "source_system",
    "sequence_no",
    "payload",
}


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


@dataclass(frozen=True, slots=True)
class BatchEvent:
    event_id: str
    event_type: EventType
    occurred_at: datetime
    site_id: str
    line_id: str
    batch_id: str
    material_id: str
    source_system: str
    sequence_no: int
    payload: dict[str, Any]

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> BatchEvent:
        if not isinstance(raw, dict):
            raise ValidationError("event must be a JSON object")
        missing = sorted(_REQUIRED - raw.keys())
        unknown = sorted(raw.keys() - _REQUIRED)
        if missing:
            raise ValidationError(f"missing fields: {', '.join(missing)}")
        if unknown:
            raise ValidationError(f"unknown fields: {', '.join(unknown)}")

        identifiers = {}
        for field in (
            "event_id",
            "site_id",
            "line_id",
            "batch_id",
            "material_id",
            "source_system",
        ):
            value = raw[field]
            if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
                raise ValidationError(f"{field} must be a safe identifier of 1-64 characters")
            identifiers[field] = value

        try:
            event_type = EventType(raw["event_type"])
        except (TypeError, ValueError) as exc:
            raise ValidationError("event_type is not supported") from exc

        try:
            occurred_at = datetime.fromisoformat(str(raw["occurred_at"]).replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValidationError("occurred_at must be ISO-8601") from exc
        if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
            raise ValidationError("occurred_at must include a timezone")

        sequence_no = raw["sequence_no"]
        if isinstance(sequence_no, bool) or not isinstance(sequence_no, int) or sequence_no < 0:
            raise ValidationError("sequence_no must be a non-negative integer")

        payload = raw["payload"]
        if not isinstance(payload, dict):
            raise ValidationError("payload must be a JSON object")
        if len(canonical_json(payload).encode("utf-8")) > 16_384:
            raise ValidationError("payload exceeds 16 KiB")

        if event_type is EventType.QUALITY_RECORDED:
            status = payload.get("status")
            if status not in {"PASSED", "FAILED", "PENDING"}:
                raise ValidationError(
                    "QUALITY_RECORDED payload.status must be PASSED, FAILED, or PENDING"
                )
        if event_type is EventType.STEP_COMPLETED:
            step_code = payload.get("step_code")
            if not isinstance(step_code, str) or not _SAFE_ID.fullmatch(step_code):
                raise ValidationError("STEP_COMPLETED payload.step_code is required")

        return cls(
            event_type=event_type,
            occurred_at=occurred_at,
            sequence_no=sequence_no,
            payload=payload,
            **identifiers,
        )

    def as_mapping(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "occurred_at": self.occurred_at.isoformat(),
            "site_id": self.site_id,
            "line_id": self.line_id,
            "batch_id": self.batch_id,
            "material_id": self.material_id,
            "source_system": self.source_system,
            "sequence_no": self.sequence_no,
            "payload": self.payload,
        }

    @property
    def digest(self) -> str:
        return hashlib.sha256(canonical_json(self.as_mapping()).encode()).hexdigest()

    @property
    def partition_key(self) -> str:
        return f"{self.source_system}|{self.site_id}|{self.line_id}"

