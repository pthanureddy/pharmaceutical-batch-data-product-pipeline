# GCP Target Architecture

## Scope and evidence boundary

This directory maps the executable local data product to Google Cloud components used by a
regulated reporting platform. Terraform plans and mock-provider tests validate resource contracts;
BigQuery SQL is linted; the Cloud Run adapter is unit tested with fake clients; and the Composer
DAG is imported and inspected in CI. No Google Cloud project was provisioned, no Composer
environment was created, and no production data was processed.

## Flow

```text
source export -> Cloud Storage raw landing
                  |                    |
                  |                    +-> Pub/Sub notification contract
                  |                        with retry / DLQ policy
                  v
          scheduled Cloud Run ingestion job
             | accepted       | rejected
             v                v
       BigQuery RAW       BigQuery OPS + quarantine object
             |
             v
   Composer/Airflow incremental MERGE
             |
             v
       BigQuery CURATED -> reporting consumers

Control plane: Git -> Python/SQL/IaC checks -> reviewed release
Operations: Pub/Sub backlog alert, bounded retries, DLQ, quality assertions, runbook
```

## Controls implemented in code

- Cloud Storage uses uniform bucket-level access, public-access prevention, versioning, and a
  bounded raw-object lifecycle.
- Pub/Sub uses bounded exponential retry and a dead-letter topic after five attempts.
- BigQuery raw and quality tables are partitioned by event time and clustered around common review
  keys. The curated table is rebuilt with a deterministic event-ID deduplication rule.
- The landing adapter sends event IDs as BigQuery streaming insert IDs, records source-object
  lineage, writes structured issue rows, and preserves quarantined NDJSON in Cloud Storage.
- The Cloud Run job uses a dedicated service account, digest-pinned image input, bounded retries,
  and least-privilege data roles.
- The Airflow DAG permits one active run, retries tasks three times, executes the Cloud Run job,
  performs the incremental merge, and runs data-quality assertions.
- Monitoring raises a policy when the Pub/Sub subscription backlog remains above 100 messages for
  five minutes.

## Deployment prerequisites

Before an apply, replace the example project and image digest, enable required APIs, create a remote
Terraform state backend, review organization policies and regions, configure Composer DAG/SQL
delivery, connect Pub/Sub notifications to the intended trigger, and add approved notification
channels. Production identity, KMS ownership, private networking, retention, and support ownership
must be approved separately.

## Trade-offs

- The local SQLite reference remains the executable source for deterministic watermark and replay
  behavior. The GCP landing adapter focuses on contract validation and raw/quality persistence.
- Streaming insert IDs provide best-effort duplicate suppression. The BigQuery MERGE remains the
  deterministic event-ID control.
- The Composer DAG uses `gcloud` and `bq` commands available in the managed environment to keep
  provider dependencies small. A production team may prefer native Google provider operators after
  version and deferrable-execution review.
- The target uses a scheduled micro-batch merge rather than claiming real-time reporting. The
  schedule, freshness threshold, and cost controls require workload evidence.

