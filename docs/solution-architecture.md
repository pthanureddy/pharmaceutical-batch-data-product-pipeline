# Solution Architecture Document

## 1. Purpose and decision context

The data product provides a consistent, auditable view of synthetic manufacturing batch events
originating from a manufacturing execution system (MES) and quality process. Its consumers are
operations analysts, data-quality stewards, and downstream reporting teams. The implementation is
a local reference; the target architecture describes how the same contracts could be separated
across cloud ingestion and Snowflake layers after platform, security, and validation review.

## 2. Business requirements mapped to capabilities

| Requirement | Implemented capability | Evidence |
| --- | --- | --- |
| Preserve source facts | Immutable raw event rows keyed by event ID | `raw_batch_event` |
| Avoid duplicate processing | Canonical digest and replay handling | pipeline tests |
| Identify changed duplicate IDs | Conflict quarantine with raw digest | quality-issue tests |
| Tolerate bounded out-of-order data | Partition watermark and allowed-lateness window | lateness tests |
| Produce a usable batch view | Deterministic snapshot recomputation | snapshot tests |
| Expose data quality | Structured issue codes and summary view | `v_data_quality_summary` |
| Support operational review | Per-run counts, status, and duration | `processing_run` |
| Support qualification review | Traceability and release checklist | qualification document |

## 3. Logical components

1. **Contract boundary** parses each NDJSON record, forbids undeclared fields, enforces
   timezone-aware event time, validates identifiers, and applies event-type payload rules.
2. **Micro-batch processor** groups bounded inputs, checks replay identity, evaluates lateness by
   source/site/line partition, and commits each micro-batch atomically.
3. **Raw zone** stores accepted canonical events and their SHA-256 digest.
4. **Quality zone** stores invalid, late, and conflicting records with reason codes.
5. **Curated zone** rebuilds the latest batch snapshot from the accepted ordered event history.
6. **Operations evidence** records counts and duration for every processing run.

## 4. Target cloud and streaming architecture

The target is a design, not a deployed environment:

```text
MES / quality sources
  -> managed event broker with schema registry
  -> immutable object-storage landing zone
  -> validation and quarantine processor
  -> Snowflake RAW.BATCH_EVENT
  -> Streams/Tasks or orchestrated incremental MERGE
  -> CURATED.BATCH_SNAPSHOT
  -> governed semantic/data-product access

Control plane:
  Git + CI -> lint/test -> reviewed infrastructure/data-model release
  Monitoring -> ingestion lag, quarantine rate, freshness, failed tasks, warehouse cost
```

Required production decisions include approved connectivity, encryption and key ownership,
identity roles, network boundaries, retention, data classification, schema evolution, disaster
recovery, region selection, warehouse sizing, cost controls, and validated change management.

## 5. Security and privacy

The synthetic contract excludes patient and operator-identifying data. A production version would
still require data classification, least-privilege roles, secret management, encrypted transport
and storage, private connectivity where required, audited access, retention rules, and a review of
whether free-text payload fields can contain sensitive data. Raw quarantine access should be more
restricted than curated analytical access.

## 6. Performance and sustainability approach

The executable design bounds payload size and micro-batch size, indexes the batch-order query, and
recomputes only affected batches. The target design separates storage and compute, clusters or
partitions around observed access paths only after measurement, and scales warehouses by workload
class rather than defaulting to permanent high capacity. Query history, ingestion lag, task
duration, scanned bytes, and credit consumption would drive tuning.

No large-scale benchmark or Snowflake cost result is claimed by this repository.

## 7. Reliability and observability

Implemented evidence includes accepted/duplicate/quarantined/late/conflict counts, processing
duration, durable issue records, deterministic replay, and non-zero CLI status for quarantine.
Production alerting would cover missing partitions, ingestion lag, quarantine-rate thresholds,
task failures, snapshot freshness, storage growth, and access anomalies.

## 8. Architecture decisions

- SQLite keeps local verification dependency-light and transactional; it is not the target
  enterprise warehouse.
- Event time, not arrival time, orders curated state.
- The processor accepts bounded disorder and quarantines records beyond the configured window.
- Snapshot recomputation favors correctness and explainability over maximum write throughput.
- Snowflake target SQL is isolated from executable SQLite behavior to keep deployment claims clear.

## 9. Qualification boundary

The repository supplies engineering verification evidence, not regulated validation. Qualification
would require approved requirements, risk assessment, test protocols, traceability sign-off,
environment qualification, access review, controlled release records, deviation handling, and
organizational ownership. See `data-product-qualification.md`.

