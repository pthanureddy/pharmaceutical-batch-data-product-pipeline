mock_provider "google" {}

run "secure_data_product_defaults" {
  command = plan

  variables {
    project_id = "portfolio-project"
  }

  assert {
    condition     = google_storage_bucket.raw.uniform_bucket_level_access
    error_message = "raw bucket must use uniform bucket-level access"
  }

  assert {
    condition     = google_storage_bucket.raw.public_access_prevention == "enforced"
    error_message = "raw bucket must prevent public access"
  }

  assert {
    condition     = google_pubsub_subscription.events.dead_letter_policy[0].max_delivery_attempts == 5
    error_message = "subscription must bound retries with a dead-letter policy"
  }

  assert {
    condition     = google_pubsub_subscription.events.retry_policy[0].maximum_backoff == "600s"
    error_message = "subscription retry backoff changed unexpectedly"
  }

  assert {
    condition     = google_bigquery_table.raw_event.time_partitioning[0].field == "occurred_at"
    error_message = "raw events must remain event-time partitioned"
  }

  assert {
    condition     = google_cloud_run_v2_job.ingest.template[0].template[0].max_retries == 3
    error_message = "Cloud Run job retries must remain bounded"
  }

  assert {
    condition     = google_monitoring_alert_policy.subscription_backlog.enabled
    error_message = "subscription backlog alert must be enabled"
  }
}

run "production_names_are_isolated" {
  command = plan

  variables {
    project_id  = "portfolio-project"
    environment = "prod"
  }

  assert {
    condition     = output.cloud_run_job == "pharma-data-prod-ingest"
    error_message = "environment must be reflected in Cloud Run job names"
  }

  assert {
    condition     = output.datasets.raw == "pharma_raw_prod"
    error_message = "environment must be reflected in dataset IDs"
  }
}

