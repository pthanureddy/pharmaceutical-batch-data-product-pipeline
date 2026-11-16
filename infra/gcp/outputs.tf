output "raw_bucket" {
  description = "Cloud Storage landing bucket."
  value       = google_storage_bucket.raw.name
}

output "subscription" {
  description = "Pub/Sub subscription consumed by the landing-job integration."
  value       = google_pubsub_subscription.events.name
}

output "cloud_run_job" {
  description = "Cloud Run ingestion job name."
  value       = google_cloud_run_v2_job.ingest.name
}

output "datasets" {
  description = "BigQuery datasets by data-product zone."
  value = {
    raw     = google_bigquery_dataset.raw.dataset_id
    curated = google_bigquery_dataset.curated.dataset_id
    ops     = google_bigquery_dataset.ops.dataset_id
  }
}

