from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pharma_data_product.models import BatchEvent, EventType, canonical_json


class DataProductStore:
    """SQLite reference store with raw, curated, quality, lineage, and run evidence."""

    def __init__(self, database: str | Path = ":memory:") -> None:
        self.connection = sqlite3.connect(str(database))
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self._create_schema()

    def close(self) -> None:
        self.connection.close()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        try:
            self.connection.execute("BEGIN")
            yield
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def _create_schema(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS raw_batch_event (
                event_id TEXT PRIMARY KEY,
                event_digest TEXT NOT NULL,
                event_type TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                site_id TEXT NOT NULL,
                line_id TEXT NOT NULL,
                batch_id TEXT NOT NULL,
                material_id TEXT NOT NULL,
                source_system TEXT NOT NULL,
                sequence_no INTEGER NOT NULL CHECK(sequence_no >= 0),
                payload_json TEXT NOT NULL,
                ingested_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS ix_raw_batch_order
                ON raw_batch_event(batch_id, occurred_at, sequence_no, event_id);

            CREATE TABLE IF NOT EXISTS stream_watermark (
                partition_key TEXT PRIMARY KEY,
                max_occurred_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS batch_snapshot (
                batch_id TEXT PRIMARY KEY,
                site_id TEXT NOT NULL,
                line_id TEXT NOT NULL,
                material_id TEXT NOT NULL,
                started_at TEXT,
                released_at TEXT,
                quality_status TEXT,
                completed_step_count INTEGER NOT NULL,
                latest_sequence_no INTEGER NOT NULL,
                latest_event_at TEXT NOT NULL,
                source_event_count INTEGER NOT NULL,
                refreshed_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS data_quality_issue (
                issue_id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT,
                issue_code TEXT NOT NULL,
                issue_message TEXT NOT NULL,
                raw_digest TEXT NOT NULL,
                raw_payload TEXT NOT NULL,
                recorded_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS ix_quality_issue_code
                ON data_quality_issue(issue_code, recorded_at);

            CREATE TABLE IF NOT EXISTS processing_run (
                run_id TEXT PRIMARY KEY,
                started_at TEXT NOT NULL,
                completed_at TEXT NOT NULL,
                input_count INTEGER NOT NULL,
                accepted_count INTEGER NOT NULL,
                duplicate_count INTEGER NOT NULL,
                quarantined_count INTEGER NOT NULL,
                late_count INTEGER NOT NULL,
                conflict_count INTEGER NOT NULL,
                duration_ms INTEGER NOT NULL,
                status TEXT NOT NULL
            );

            CREATE VIEW IF NOT EXISTS v_batch_cycle_time AS
            SELECT batch_id, site_id, line_id, material_id, quality_status,
                   started_at, released_at,
                   CASE WHEN started_at IS NOT NULL AND released_at IS NOT NULL
                     THEN (julianday(released_at) - julianday(started_at)) * 24.0
                   END AS cycle_hours
              FROM batch_snapshot;

            CREATE VIEW IF NOT EXISTS v_data_quality_summary AS
            SELECT issue_code, COUNT(*) AS issue_count, MAX(recorded_at) AS latest_issue_at
              FROM data_quality_issue
             GROUP BY issue_code;
            """
        )
        self.connection.commit()

    @staticmethod
    def now_iso() -> str:
        return datetime.now(UTC).isoformat()

    def existing_digest(self, event_id: str) -> str | None:
        row = self.connection.execute(
            "SELECT event_digest FROM raw_batch_event WHERE event_id = ?", (event_id,)
        ).fetchone()
        return None if row is None else str(row["event_digest"])

    def watermark(self, partition_key: str) -> datetime | None:
        row = self.connection.execute(
            "SELECT max_occurred_at FROM stream_watermark WHERE partition_key = ?",
            (partition_key,),
        ).fetchone()
        return None if row is None else datetime.fromisoformat(str(row["max_occurred_at"]))

    def insert_event(self, event: BatchEvent) -> None:
        self.connection.execute(
            """
            INSERT INTO raw_batch_event (
                event_id, event_digest, event_type, occurred_at, site_id, line_id,
                batch_id, material_id, source_system, sequence_no, payload_json, ingested_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.event_id,
                event.digest,
                event.event_type.value,
                event.occurred_at.isoformat(),
                event.site_id,
                event.line_id,
                event.batch_id,
                event.material_id,
                event.source_system,
                event.sequence_no,
                canonical_json(event.payload),
                self.now_iso(),
            ),
        )

    def advance_watermark(self, event: BatchEvent) -> None:
        current = self.watermark(event.partition_key)
        if current is not None and current >= event.occurred_at:
            return
        self.connection.execute(
            """
            INSERT INTO stream_watermark(partition_key, max_occurred_at, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(partition_key) DO UPDATE SET
                max_occurred_at = excluded.max_occurred_at,
                updated_at = excluded.updated_at
            """,
            (event.partition_key, event.occurred_at.isoformat(), self.now_iso()),
        )

    def record_issue(
        self,
        *,
        event_id: str | None,
        code: str,
        message: str,
        raw_digest: str,
        raw_payload: str,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO data_quality_issue(
                event_id, issue_code, issue_message, raw_digest, raw_payload, recorded_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (event_id, code, message, raw_digest, raw_payload, self.now_iso()),
        )

    def refresh_batch(self, batch_id: str) -> None:
        rows = self.connection.execute(
            """
            SELECT * FROM raw_batch_event
             WHERE batch_id = ?
             ORDER BY occurred_at, sequence_no, event_id
            """,
            (batch_id,),
        ).fetchall()
        if not rows:
            return

        first = rows[0]
        started_at = None
        released_at = None
        quality_status = None
        completed_steps: set[str] = set()
        latest_sequence_no = 0
        for row in rows:
            event_type = EventType(row["event_type"])
            payload = json.loads(row["payload_json"])
            latest_sequence_no = max(latest_sequence_no, int(row["sequence_no"]))
            if event_type is EventType.BATCH_STARTED and started_at is None:
                started_at = row["occurred_at"]
            elif event_type is EventType.STEP_COMPLETED:
                completed_steps.add(str(payload["step_code"]))
            elif event_type is EventType.QUALITY_RECORDED:
                quality_status = str(payload["status"])
            elif event_type is EventType.BATCH_RELEASED:
                released_at = row["occurred_at"]

        self.connection.execute(
            """
            INSERT INTO batch_snapshot(
                batch_id, site_id, line_id, material_id, started_at, released_at,
                quality_status, completed_step_count, latest_sequence_no, latest_event_at,
                source_event_count, refreshed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(batch_id) DO UPDATE SET
                site_id = excluded.site_id,
                line_id = excluded.line_id,
                material_id = excluded.material_id,
                started_at = excluded.started_at,
                released_at = excluded.released_at,
                quality_status = excluded.quality_status,
                completed_step_count = excluded.completed_step_count,
                latest_sequence_no = excluded.latest_sequence_no,
                latest_event_at = excluded.latest_event_at,
                source_event_count = excluded.source_event_count,
                refreshed_at = excluded.refreshed_at
            """,
            (
                batch_id,
                first["site_id"],
                first["line_id"],
                first["material_id"],
                started_at,
                released_at,
                quality_status,
                len(completed_steps),
                latest_sequence_no,
                rows[-1]["occurred_at"],
                len(rows),
                self.now_iso(),
            ),
        )

    def record_run(self, run: dict[str, Any]) -> None:
        self.connection.execute(
            """
            INSERT INTO processing_run(
                run_id, started_at, completed_at, input_count, accepted_count,
                duplicate_count, quarantined_count, late_count, conflict_count,
                duration_ms, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            tuple(
                run[key]
                for key in (
                    "run_id",
                    "started_at",
                    "completed_at",
                    "input_count",
                    "accepted_count",
                    "duplicate_count",
                    "quarantined_count",
                    "late_count",
                    "conflict_count",
                    "duration_ms",
                    "status",
                )
            ),
        )

    def fetch_one(self, sql: str, parameters: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        row = self.connection.execute(sql, parameters).fetchone()
        return None if row is None else dict(row)

    def fetch_all(self, sql: str, parameters: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        return [dict(row) for row in self.connection.execute(sql, parameters).fetchall()]

