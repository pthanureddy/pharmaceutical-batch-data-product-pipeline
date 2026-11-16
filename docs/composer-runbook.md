# Composer/Airflow Operations Runbook

## Deployment inputs

Ship `orchestration/dags/batch_data_product.py` to the Composer DAG bucket and make the
`sql/bigquery` directory available at the configured `PIPELINE_SQL_ROOT`. Configure
`GCP_PROJECT`, `GCP_REGION`, and `CLOUD_RUN_JOB` as environment variables. The DAG never embeds
credentials.

## Failure triage

1. **Cloud Run execution fails:** inspect job execution logs and the exact image digest; check
   missing object/table environment values and service-account permissions. Do not bypass the
   quarantine path to make a run green.
2. **Pub/Sub retries grow:** inspect age and count of undelivered messages, Cloud Run errors, and
   dead-letter messages. Replay only after the cause and idempotency boundary are understood.
3. **MERGE fails:** confirm the raw schema, event-time types, dataset location, and duplicate-event
   facts. Preserve the failed query job ID for the incident record.
4. **Quality assertion fails:** treat freshness and event-ID conflict checks as delivery blockers.
   Record an approved exception rather than editing the assertion during an incident.

## Recovery

Airflow retries each task three times with a five-minute delay. After a permanent failure, correct
the source, configuration, permission, or query issue and clear only the failed task. The Cloud Run
adapter sends stable event IDs as insert IDs; the curated MERGE deduplicates by event ID and latest
ingestion evidence. Review the DLQ and quality table before replaying an object.

## Required production additions

Add an on-call owner, notification channels, SLOs, remote Terraform state, separate service
accounts for Composer and ingestion, secret rotation, budget alerts, backup/restore tests, approved
retention, and a controlled release process before external operation.

