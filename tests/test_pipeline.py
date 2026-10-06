import json
from datetime import timedelta

import pytest

from pharma_data_product.pipeline import StreamProcessor
from pharma_data_product.store import DataProductStore
from tests.test_models import valid_event


@pytest.fixture
def store():
    value = DataProductStore()
    yield value
    value.close()


def test_ingests_and_curates_batch(store):
    events = [
        valid_event(),
        valid_event(
            event_id="evt-002",
            event_type="STEP_COMPLETED",
            occurred_at="2026-10-06T08:05:00+00:00",
            sequence_no=2,
            payload={"step_code": "MIXING"},
        ),
        valid_event(
            event_id="evt-003",
            event_type="QUALITY_RECORDED",
            occurred_at="2026-10-06T08:10:00+00:00",
            sequence_no=3,
            payload={"status": "PASSED"},
        ),
        valid_event(
            event_id="evt-004",
            event_type="BATCH_RELEASED",
            occurred_at="2026-10-06T08:20:00+00:00",
            sequence_no=4,
            payload={"release_reference": "REL-001"},
        ),
    ]
    result = StreamProcessor(store).ingest(events)
    snapshot = store.fetch_one(
        "SELECT * FROM batch_snapshot WHERE batch_id = ?", ("BATCH-2026-001",)
    )

    assert result.accepted_count == 4
    assert result.quarantined_count == 0
    assert snapshot["quality_status"] == "PASSED"
    assert snapshot["completed_step_count"] == 1
    assert snapshot["source_event_count"] == 4
    assert snapshot["released_at"] == "2026-10-06T08:20:00+00:00"


def test_identical_replay_is_counted_without_new_row(store):
    processor = StreamProcessor(store)
    processor.ingest([valid_event()])
    replay = processor.ingest([valid_event()])

    assert replay.duplicate_count == 1
    assert replay.quarantined_count == 0
    assert store.fetch_one("SELECT COUNT(*) AS value FROM raw_batch_event")["value"] == 1


def test_event_id_conflict_is_quarantined(store):
    processor = StreamProcessor(store)
    processor.ingest([valid_event()])
    result = processor.ingest([valid_event(payload={"operator_shift": "NIGHT"})])

    assert result.conflict_count == 1
    assert result.quarantined_count == 1
    issue = store.fetch_one("SELECT * FROM data_quality_issue")
    assert issue["issue_code"] == "EVENT_ID_CONFLICT"


def test_late_event_is_quarantined_beyond_watermark(store):
    processor = StreamProcessor(store, allowed_lateness=timedelta(minutes=10))
    processor.ingest([valid_event(occurred_at="2026-10-06T09:00:00+00:00")])
    result = processor.ingest(
        [valid_event(event_id="evt-late", occurred_at="2026-10-06T08:49:59+00:00")]
    )

    assert result.late_count == 1
    assert result.accepted_count == 0


def test_out_of_order_event_within_lateness_is_recurated(store):
    processor = StreamProcessor(store, allowed_lateness=timedelta(minutes=15))
    processor.ingest(
        [
            valid_event(
                event_id="evt-release",
                event_type="BATCH_RELEASED",
                occurred_at="2026-10-06T09:00:00+00:00",
                sequence_no=4,
            )
        ]
    )
    result = processor.ingest([valid_event(occurred_at="2026-10-06T08:50:00+00:00")])
    snapshot = store.fetch_one("SELECT * FROM batch_snapshot")

    assert result.accepted_count == 1
    assert snapshot["started_at"] == "2026-10-06T08:50:00+00:00"
    assert snapshot["released_at"] == "2026-10-06T09:00:00+00:00"


def test_duplicate_step_codes_count_once(store):
    events = [
        valid_event(
            event_id="step-1",
            event_type="STEP_COMPLETED",
            payload={"step_code": "MIXING"},
        ),
        valid_event(
            event_id="step-2",
            event_type="STEP_COMPLETED",
            sequence_no=2,
            occurred_at="2026-10-06T08:01:00+00:00",
            payload={"step_code": "MIXING"},
        ),
    ]
    StreamProcessor(store).ingest(events)
    assert store.fetch_one("SELECT completed_step_count FROM batch_snapshot")[
        "completed_step_count"
    ] == 1


def test_watermark_is_partition_specific(store):
    processor = StreamProcessor(store, allowed_lateness=timedelta(0))
    processor.ingest([valid_event(occurred_at="2026-10-06T12:00:00+00:00")])
    result = processor.ingest(
        [
            valid_event(
                event_id="other-line",
                line_id="LINE-B",
                occurred_at="2026-10-06T07:00:00+00:00",
            )
        ]
    )
    assert result.accepted_count == 1


def test_invalid_contract_and_invalid_json_are_quarantined(store):
    processor = StreamProcessor(store)
    result = processor.ingest_json_lines(
        [json.dumps(valid_event(sequence_no=-1)), "{not-json", "[]"]
    )

    assert result.input_count == 3
    assert result.quarantined_count == 3
    issues = store.fetch_all("SELECT issue_code FROM data_quality_issue")
    codes = {row["issue_code"] for row in issues}
    assert codes == {"CONTRACT_VIOLATION", "INVALID_JSON"}


def test_processing_run_records_counts(store):
    result = StreamProcessor(store, micro_batch_size=1).ingest([valid_event(), valid_event()])
    run = store.fetch_one("SELECT * FROM processing_run WHERE run_id = ?", (result.run_id,))

    assert run["input_count"] == 2
    assert run["accepted_count"] == 1
    assert run["duplicate_count"] == 1
    assert run["status"] == "COMPLETED"


def test_cycle_time_view(store):
    StreamProcessor(store).ingest(
        [
            valid_event(),
            valid_event(
                event_id="released",
                event_type="BATCH_RELEASED",
                occurred_at="2026-10-06T10:00:00+00:00",
                sequence_no=2,
            ),
        ]
    )
    row = store.fetch_one("SELECT cycle_hours FROM v_batch_cycle_time")
    assert row["cycle_hours"] == pytest.approx(2.0)


def test_processor_configuration_guards(store):
    with pytest.raises(ValueError, match="negative"):
        StreamProcessor(store, allowed_lateness=timedelta(seconds=-1))
    with pytest.raises(ValueError, match="between"):
        StreamProcessor(store, micro_batch_size=0)

