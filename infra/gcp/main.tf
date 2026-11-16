locals {
  prefix = "${var.name_prefix}-${var.environment}"
}

data "google_project" "current" {
  project_id = var.project_id
}

resource "google_service_account" "pipeline" {
  account_id   = "${local.prefix}-pipeline"
  display_name = "Pharmaceutical batch data-product pipeline"
}

resource "google_storage_bucket" "raw" {
  name                        = "${var.project_id}-${local.prefix}-raw"
  location                    = "EU"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false

  versioning {
    enabled = true
  }

  lifecycle_rule {
    condition {
      age = var.raw_retention_days
    }
    action {
      type = "Delete"
    }
  }
}

resource "google_pubsub_topic" "events" {
  name                       = "${local.prefix}-batch-events"
  message_retention_duration = "604800s"
}

resource "google_pubsub_topic" "dead_letter" {
  name                       = "${local.prefix}-batch-events-dlq"
  message_retention_duration = "1209600s"
}

resource "google_pubsub_subscription" "events" {
  name                       = "${local.prefix}-batch-events"
  topic                      = google_pubsub_topic.events.id
  ack_deadline_seconds       = 60
  message_retention_duration = "604800s"
  retain_acked_messages      = false

  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"
  }

  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.dead_letter.id
    max_delivery_attempts = 5
  }
}

resource "google_bigquery_dataset" "raw" {
  dataset_id                 = "pharma_raw_${var.environment}"
  friendly_name              = "Pharmaceutical batch raw zone"
  location                   = "EU"
  delete_contents_on_destroy = false
  max_time_travel_hours      = 168
}

resource "google_bigquery_dataset" "curated" {
  dataset_id                 = "pharma_curated_${var.environment}"
  friendly_name              = "Pharmaceutical batch curated zone"
  location                   = "EU"
  delete_contents_on_destroy = false
  max_time_travel_hours      = 168
}

resource "google_bigquery_dataset" "ops" {
  dataset_id                 = "pharma_ops_${var.environment}"
  friendly_name              = "Pharmaceutical batch operations evidence"
  location                   = "EU"
  delete_contents_on_destroy = false
  max_time_travel_hours      = 168
}

resource "google_bigquery_table" "raw_event" {
  dataset_id          = google_bigquery_dataset.raw.dataset_id
  table_id            = "raw_batch_event"
  deletion_protection = true
  schema              = file("${path.module}/schemas/raw_batch_event.json")
  clustering          = ["batch_id", "site_id", "event_type"]

  time_partitioning {
    type  = "DAY"
    field = "occurred_at"
  }
}

resource "google_bigquery_table" "batch_snapshot" {
  dataset_id          = google_bigquery_dataset.curated.dataset_id
  table_id            = "batch_snapshot"
  deletion_protection = true
  schema              = file("${path.module}/schemas/batch_snapshot.json")
  clustering          = ["site_id", "line_id", "quality_status"]
}

resource "google_bigquery_table" "quality_issue" {
  dataset_id          = google_bigquery_dataset.ops.dataset_id
  table_id            = "data_quality_issue"
  deletion_protection = true
  schema              = file("${path.module}/schemas/data_quality_issue.json")
  clustering          = ["issue_code", "source_object"]

  time_partitioning {
    type  = "DAY"
    field = "recorded_at"
  }
}

resource "google_cloud_run_v2_job" "ingest" {
  name                = "${local.prefix}-ingest"
  location            = var.region
  deletion_protection = false

  template {
    template {
      service_account = google_service_account.pipeline.email
      max_retries     = 3
      timeout         = "900s"

      containers {
        image = var.cloud_run_image
        env {
          name  = "GCP_PROJECT"
          value = var.project_id
        }
        env {
          name  = "RAW_BUCKET"
          value = google_storage_bucket.raw.name
        }
        env {
          name  = "INPUT_OBJECT"
          value = var.input_object
        }
        env {
          name  = "BIGQUERY_RAW_TABLE"
          value = "${var.project_id}.${google_bigquery_dataset.raw.dataset_id}.${google_bigquery_table.raw_event.table_id}"
        }
        env {
          name  = "BIGQUERY_QUALITY_TABLE"
          value = "${var.project_id}.${google_bigquery_dataset.ops.dataset_id}.${google_bigquery_table.quality_issue.table_id}"
        }
      }
    }
  }
}

resource "google_project_iam_member" "storage_user" {
  project = var.project_id
  role    = "roles/storage.objectUser"
  member  = "serviceAccount:${google_service_account.pipeline.email}"
}

resource "google_project_iam_member" "bigquery_editor" {
  project = var.project_id
  role    = "roles/bigquery.dataEditor"
  member  = "serviceAccount:${google_service_account.pipeline.email}"
}

resource "google_project_iam_member" "bigquery_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.pipeline.email}"
}

resource "google_pubsub_topic_iam_member" "dead_letter_publisher" {
  topic  = google_pubsub_topic.dead_letter.name
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}

resource "google_pubsub_subscription_iam_member" "forwarder" {
  subscription = google_pubsub_subscription.events.name
  role         = "roles/pubsub.subscriber"
  member       = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}

resource "google_monitoring_alert_policy" "subscription_backlog" {
  display_name = "${local.prefix} Pub/Sub backlog"
  combiner     = "OR"
  enabled      = true

  conditions {
    display_name = "Undelivered messages above 100 for five minutes"
    condition_threshold {
      filter = join(" AND ", [
        "resource.type = \"pubsub_subscription\"",
        "metric.type = \"pubsub.googleapis.com/subscription/num_undelivered_messages\"",
        "resource.label.subscription_id = \"${google_pubsub_subscription.events.name}\"",
      ])
      comparison      = "COMPARISON_GT"
      threshold_value = 100
      duration        = "300s"

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_MAX"
      }
    }
  }

  documentation {
    content   = "Inspect Cloud Run job failures, Pub/Sub retries, dead-letter messages, and data-quality issues before replaying."
    mime_type = "text/markdown"
  }
}

