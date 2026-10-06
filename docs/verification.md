# Verification Record

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
- Hosted CI evidence is added only after the public workflow completes.

