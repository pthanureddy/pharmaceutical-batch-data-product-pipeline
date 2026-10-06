# Operations Runbook

## Routine checks

1. Run `pharma-data-product summary --database <path>` and inspect the latest run.
2. Query `v_data_quality_summary` for new issue codes or increasing counts.
3. Compare the maximum `occurred_at` per partition with source expectations.
4. Confirm curated batch freshness and investigate batches without a start event.
5. Retain package, test, coverage, SQL-lint, and workflow evidence with the release record.

## Issue triage

- `CONTRACT_VIOLATION`: compare the producing schema with the committed contract; do not silently
  coerce undeclared fields.
- `INVALID_JSON`: preserve the raw digest, contact the producer, and replay only after correction.
- `EVENT_ID_CONFLICT`: stop automatic reconciliation; one identity now represents two payloads.
- `LATE_EVENT`: determine whether the lateness window is wrong, the producer clock is incorrect,
  or the record needs an approved backfill path.

## Recovery

Identical replay is safe. A corrected rejected record must use an identity consistent with the
source contract. For a full rebuild, create a new empty database and replay accepted source events
in bounded micro-batches; compare counts, digests, quality issues, and curated snapshots before
cutover. Back up the prior database before replacement.

## Production additions

A deployed version needs managed monitoring, alert ownership, dashboards, pager routing,
authentication, authorization, backup/restore tests, disaster-recovery objectives, schema-registry
compatibility, orchestration retries, dead-letter replay approvals, and platform cost controls.

