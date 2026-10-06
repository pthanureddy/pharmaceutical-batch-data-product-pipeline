# Conceptual, Logical, and Physical Data Model

## Conceptual model

- A **site** contains production **lines**.
- A **batch** is produced on one line for one material.
- A source system emits ordered **batch events**.
- Accepted events determine a current **batch snapshot**.
- Invalid, conflicting, or late input creates a **data-quality issue**.
- Every ingestion invocation produces a **processing run**.

## Logical model

```text
Site 1---* Line 1---* Batch 1---* BatchEvent
                         |
                         1
                         |
                    BatchSnapshot

BatchEvent 0---* DataQualityIssue (issue may lack a valid event identity)
ProcessingRun records aggregate ingestion evidence independently.
```

Business keys are `site_id`, `(site_id, line_id)`, `material_id`, `batch_id`, and `event_id`.
`event_id` must be globally stable for replay handling. `sequence_no` is informative within the
source event stream but does not replace event time or a stable event identity.

## Physical SQLite model

| Object | Grain | Key | Purpose |
| --- | --- | --- | --- |
| `raw_batch_event` | one accepted source event | `event_id` | immutable source facts and digest |
| `stream_watermark` | one source/site/line partition | `partition_key` | maximum accepted event time |
| `batch_snapshot` | one batch | `batch_id` | current curated operational state |
| `data_quality_issue` | one rejected observation | surrogate ID | reason, evidence digest, raw record |
| `processing_run` | one CLI/processor invocation | `run_id` | operational counts and timing |
| `v_batch_cycle_time` | one batch | inherited | derived cycle duration |
| `v_data_quality_summary` | one issue code | inherited | current issue volumes |

The Snowflake target keeps raw events append-oriented, separates quarantine and curated schemas,
and uses a deterministic incremental `MERGE`. The SQL is in `sql/snowflake/` and is design-only.

## Data lineage

```text
input NDJSON line
  -> canonical event digest
  -> raw_batch_event
  -> ordered accepted history for batch_id
  -> batch_snapshot
  -> v_batch_cycle_time
```

Rejected input follows:

```text
input NDJSON line -> SHA-256 raw digest + issue code -> data_quality_issue
```

