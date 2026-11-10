"""Count snapshot rebuilds for a fixed synthetic ingestion and replay workload."""

import json
from datetime import UTC, datetime, timedelta

from pharma_data_product.pipeline import StreamProcessor
from pharma_data_product.store import DataProductStore

EVENT_COUNT = 1000
MICRO_BATCH_SIZE = 100


class CountingStore(DataProductStore):
    def __init__(self) -> None:
        super().__init__()
        self.refresh_count = 0

    def refresh_batch(self, batch_id: str) -> None:
        self.refresh_count += 1
        super().refresh_batch(batch_id)


def fixture_events() -> list[dict]:
    start = datetime(2026, 10, 6, 8, tzinfo=UTC)
    events = []
    for index in range(EVENT_COUNT):
        event_type = "STEP_COMPLETED"
        payload = {"step_code": f"STEP-{index:04d}"}
        if index == 0:
            event_type, payload = "BATCH_STARTED", {"operator_shift": "DAY"}
        elif index == EVENT_COUNT - 2:
            event_type, payload = "QUALITY_RECORDED", {"status": "PASSED"}
        elif index == EVENT_COUNT - 1:
            event_type, payload = "BATCH_RELEASED", {"release_reference": "REL-001"}
        events.append(
            {
                "event_id": f"measure-{index:04d}",
                "event_type": event_type,
                "occurred_at": (start + timedelta(seconds=index)).isoformat(),
                "site_id": "SITE-SE-01",
                "line_id": "LINE-A",
                "batch_id": "BATCH-MEASUREMENT",
                "material_id": "MAT-100",
                "source_system": "MES",
                "sequence_no": index + 1,
                "payload": payload,
            }
        )
    return events


def main() -> None:
    events = fixture_events()
    store = CountingStore()
    try:
        processor = StreamProcessor(store, micro_batch_size=MICRO_BATCH_SIZE)
        initial = processor.ingest(events)
        initial_refreshes = store.refresh_count
        replay = processor.ingest(events)
        snapshot = store.fetch_one("SELECT * FROM batch_snapshot")
        assert snapshot is not None
        snapshot.pop("refreshed_at")
        assert initial.accepted_count == EVENT_COUNT and initial.quarantined_count == 0
        assert replay.duplicate_count == EVENT_COUNT and replay.accepted_count == 0
        assert replay.quarantined_count == 0
        print(
            json.dumps(
                {
                    "events": EVENT_COUNT,
                    "micro_batch_size": MICRO_BATCH_SIZE,
                    "accepted_events": initial.accepted_count,
                    "snapshot_refresh_calls": initial_refreshes,
                    "replayed_duplicates": replay.duplicate_count,
                    "replay_snapshot_refresh_calls": store.refresh_count - initial_refreshes,
                    "snapshot": snapshot,
                },
                indent=2,
                sort_keys=True,
            )
        )
    finally:
        store.close()


if __name__ == "__main__":
    main()
