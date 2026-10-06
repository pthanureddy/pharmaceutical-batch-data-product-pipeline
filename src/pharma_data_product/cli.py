from __future__ import annotations

import argparse
import json
from datetime import timedelta
from pathlib import Path

from pharma_data_product.pipeline import StreamProcessor
from pharma_data_product.store import DataProductStore


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Synthetic batch data-product pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="Create or verify the SQLite schema")
    init.add_argument("--database", required=True)

    ingest = subparsers.add_parser("ingest", help="Ingest an NDJSON event stream")
    ingest.add_argument("--database", required=True)
    ingest.add_argument("--input", required=True)
    ingest.add_argument("--allowed-lateness-minutes", type=int, default=15)
    ingest.add_argument("--micro-batch-size", type=int, default=100)

    summary = subparsers.add_parser("summary", help="Print data-product counts and run evidence")
    summary.add_argument("--database", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    database = Path(args.database)
    database.parent.mkdir(parents=True, exist_ok=True)
    store = DataProductStore(database)
    try:
        if args.command == "init":
            print(json.dumps({"database": str(database), "status": "ready"}, sort_keys=True))
            return 0
        if args.command == "ingest":
            if args.allowed_lateness_minutes < 0:
                raise SystemExit("allowed lateness must not be negative")
            processor = StreamProcessor(
                store,
                allowed_lateness=timedelta(minutes=args.allowed_lateness_minutes),
                micro_batch_size=args.micro_batch_size,
            )
            with Path(args.input).open(encoding="utf-8") as stream:
                result = processor.ingest_json_lines(stream)
            print(json.dumps(result.as_dict(), sort_keys=True))
            return 0 if result.quarantined_count == 0 else 2

        payload = {
            "raw_event_count": store.fetch_one("SELECT COUNT(*) AS value FROM raw_batch_event")[
                "value"
            ],
            "batch_count": store.fetch_one("SELECT COUNT(*) AS value FROM batch_snapshot")[
                "value"
            ],
            "quality_issue_count": store.fetch_one(
                "SELECT COUNT(*) AS value FROM data_quality_issue"
            )["value"],
            "latest_run": store.fetch_one(
                "SELECT * FROM processing_run ORDER BY completed_at DESC LIMIT 1"
            ),
        }
        print(json.dumps(payload, sort_keys=True))
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())

