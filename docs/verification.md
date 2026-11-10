# Verification Record

## Snapshot refresh verification, 10 November 2026

The processor now collects changed batch IDs in a set and rebuilds each affected snapshot once
before committing the micro-batch transaction. Raw writes, watermarks, quarantines and curated
updates share the transaction. Two regression tests cover distinct batch IDs across micro-batches
and a snapshot write failure that rolls back the current micro-batch.

Run `python tools/measure_snapshot_refresh.py` after installing the package. The script uses an
in-memory SQLite store, one synthetic manufacturing batch, 1,000 ordered events and a micro-batch
size of 100. It measures calls to `refresh_batch` and replays the input once. For the baseline
comparison, use the same script with `PYTHONPATH` pointing to `src` in a checkout of
`7e1f6f185cc9155195fc1f0a9cae9d538f6755d7`. Run it again against the updated source.

| Measure | Baseline | Updated |
| --- | ---: | ---: |
| Accepted events | 1,000 | 1,000 |
| Snapshot rebuild calls | 1,000 | 10 |
| Replay duplicates | 1,000 | 1,000 |
| Snapshot rebuild calls during replay | 0 | 0 |

The curated values matched after excluding the wall-clock `refreshed_at` metadata field. The count
measures repeated work for this fixture. Runtime throughput, distributed scaling and performance
on other workloads remain unmeasured.

Local Ruff lint, 27 tests, SQLFluff lint, source distribution and wheel builds, and the four-event
CLI smoke flow passed. Coverage was 305/314 lines (97.13%) and 73/78 branches (93.59%). The
branch-aware aggregate used by the configured coverage gate was 96.43%.

## Original project verification, 6 October 2026

Verified locally on 2026-10-06 with Python 3.11.9 on Windows.

## Commands and results

| Check | Command | Result |
| --- | --- | --- |
| Python quality | `python -m ruff check .` | passed |
| Automated tests | `python -m pytest` | 25 passed, 0 failed |
| Coverage | pytest-cov with branch measurement | 297/309 lines (96.12%); 69/74 branches (93.24%) |
| Snowflake SQL syntax/style | `python -m sqlfluff lint sql/snowflake --dialect snowflake` | passed |
| Package build | `python -m build` | source distribution and wheel built |
| CLI smoke | init, four-event ingest, summary | 4 accepted, 0 quarantined; 1 curated batch |

The local smoke run measured 5 ms for the bundled four-event fixture. That value is recorded only
as command evidence and is not a throughput or scalability claim.

## Evidence boundary

- SQLite behavior is executable and tested.
- The Snowflake files were linted with the Snowflake dialect but were not executed in a Snowflake
  account.
- No external broker, object store, cloud deployment, production source, regulated validation,
  load test, availability result, or business improvement is claimed.

## Hosted CI

GitHub Actions run
[`37492057602`](https://github.com/pthanureddy/pharmaceutical-batch-data-product-pipeline/actions/runs/37492057602)
passed Ruff, all tests and coverage enforcement, Snowflake-dialect SQLFluff linting, package build,
the four-event CLI smoke flow, and verification-artifact upload for commit
`1b097aa18ebe8759cdd4d8c245e9cabc6ec50b0b`.

