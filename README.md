# Pharmaceutical Batch Data Product Pipeline

An independent portfolio project for ingesting synthetic pharmaceutical manufacturing batch
events into a traceable operational data product. It demonstrates Python and SQL engineering,
event-time processing, data quality, conceptual/logical/physical modeling, monitoring evidence,
CI/CD, and a qualification-oriented solution architecture package.

All data are synthetic. This repository is not affiliated with Roche or another pharmaceutical
company, is not a validated GxP system, and has not processed production or patient data. The
Snowflake assets are linted target-state SQL only; no Snowflake account or live warehouse was used.

## Implemented behavior

- Validates a bounded NDJSON event contract for batch start, process-step completion, quality
  status, and release events.
- Processes configurable micro-batches with partition watermarks and an allowed-lateness window.
- Treats identical event replays as duplicates and quarantines conflicting event-ID reuse.
- Quarantines malformed, contract-invalid, and excessively late records with SHA-256 evidence.
- Recomputes deterministic batch snapshots from accepted source events so bounded out-of-order
  arrival does not corrupt the curated state.
- Persists raw events, watermarks, curated snapshots, data-quality issues, processing runs, and
  analytical views in SQLite for reproducible local verification.
- Provides Snowflake-dialect raw/curated schemas and an incremental `MERGE` target design checked
  with SQLFluff, without presenting that design as deployed experience.
- Includes a Solution Architecture Document, three-level data model, data-product qualification
  checklist, operational runbook, and explicit production gaps.

## Architecture

```text
Synthetic MES / quality event exports
                |
                v
       NDJSON contract validation
                |
                v
   micro-batch processor + event-time watermark
        | accepted                 | invalid / late / conflict
        v                          v
 raw_batch_event           data_quality_issue
        |
        v
 deterministic batch_snapshot + cycle-time view
        |
        +---- processing_run evidence and operator summary

Target-state only: object storage / Kafka -> Snowflake RAW -> CURATED -> MART
```

See [Solution Architecture](docs/solution-architecture.md),
[Data Model](docs/data-model.md), and
[Data Product Qualification](docs/data-product-qualification.md).

## Quick start

Python 3.11 or newer is required.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pharma_data_product init --database artifacts\batch-data.db
.\.venv\Scripts\python.exe -m pharma_data_product ingest `
  --database artifacts\batch-data.db `
  --input examples\batch-events.ndjson
.\.venv\Scripts\python.exe -m pharma_data_product summary `
  --database artifacts\batch-data.db
```

The ingest command returns `0` when every non-empty line is accepted or replayed and `2` when at
least one record is quarantined. A processing-run record is written in both cases.

## Verification

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m sqlfluff lint sql\snowflake --dialect snowflake
.\.venv\Scripts\python.exe -m build
```

GitHub Actions runs the same checks and uploads the package plus test/coverage evidence. Measured
results belong in [Verification](docs/verification.md) after a reproducible run rather than in this
overview.

## Repository map

```text
src/pharma_data_product/  event contract, micro-batch processor, SQLite data product, CLI
tests/                    model, pipeline, replay, lateness, quality, and CLI tests
examples/                 synthetic NDJSON input
sql/snowflake/            linted target-state Snowflake DDL and incremental MERGE
docs/                     architecture, models, qualification, operations, and verification
.github/workflows/        repeatable lint, test, package, and SQL checks
```

## Boundaries

- This is an independently engineered portfolio system using synthetic data.
- It does not provide 21 CFR Part 11, GxP validation, electronic signatures, validated change
  control, disaster recovery, or regulated retention.
- SQLite is the executable local reference, not a large-scale warehouse.
- Snowflake SQL is a design artifact validated by SQLFluff, not a deployment or operational claim.
- The stream is a deterministic NDJSON micro-batch reference. Kafka, CDC, schema registry, object
  storage, orchestration, and multi-node processing are target-state components only.
- No throughput, scalability, availability, business-impact, or production-quality claim is made.

## License

MIT

