from datetime import UTC, datetime

import pytest

from pharma_data_product.models import BatchEvent, EventType, ValidationError


def valid_event(**overrides):
    event = {
        "event_id": "evt-001",
        "event_type": "BATCH_STARTED",
        "occurred_at": "2026-10-06T08:00:00+00:00",
        "site_id": "SITE-SE-01",
        "line_id": "LINE-A",
        "batch_id": "BATCH-2026-001",
        "material_id": "MAT-100",
        "source_system": "MES",
        "sequence_no": 1,
        "payload": {"operator_shift": "DAY"},
    }
    event.update(overrides)
    return event


def test_parses_valid_event():
    event = BatchEvent.from_mapping(valid_event())
    assert event.event_type is EventType.BATCH_STARTED
    assert event.occurred_at == datetime(2026, 10, 6, 8, tzinfo=UTC)
    assert event.partition_key == "MES|SITE-SE-01|LINE-A"


def test_digest_is_stable_for_payload_key_order():
    first = BatchEvent.from_mapping(valid_event(payload={"b": 2, "a": 1}))
    second = BatchEvent.from_mapping(valid_event(payload={"a": 1, "b": 2}))
    assert first.digest == second.digest


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"event_id": "bad id"}, "safe identifier"),
        ({"sequence_no": -1}, "non-negative"),
        ({"sequence_no": True}, "non-negative"),
        ({"occurred_at": "2026-10-06T08:00:00"}, "timezone"),
        ({"event_type": "UNKNOWN"}, "not supported"),
        ({"payload": []}, "JSON object"),
    ],
)
def test_rejects_invalid_contract_values(override, message):
    with pytest.raises(ValidationError, match=message):
        BatchEvent.from_mapping(valid_event(**override))


def test_rejects_missing_and_unknown_fields():
    missing = valid_event()
    missing.pop("site_id")
    with pytest.raises(ValidationError, match="missing fields: site_id"):
        BatchEvent.from_mapping(missing)

    with pytest.raises(ValidationError, match="unknown fields: unexpected"):
        BatchEvent.from_mapping(valid_event(unexpected=True))


def test_quality_status_contract():
    with pytest.raises(ValidationError, match="payload.status"):
        BatchEvent.from_mapping(
            valid_event(event_type="QUALITY_RECORDED", payload={"status": "UNKNOWN"})
        )


def test_step_code_contract():
    with pytest.raises(ValidationError, match="payload.step_code"):
        BatchEvent.from_mapping(valid_event(event_type="STEP_COMPLETED", payload={}))


def test_rejects_oversized_payload():
    with pytest.raises(ValidationError, match="16 KiB"):
        BatchEvent.from_mapping(valid_event(payload={"value": "x" * 16_500}))

