variable "project_id" {
  description = "Google Cloud project that owns the data-product resources."
  type        = string
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.project_id))
    error_message = "project_id must be a valid Google Cloud project ID"
  }
}

variable "region" {
  description = "Region for regional resources."
  type        = string
  default     = "europe-north1"
}

variable "environment" {
  description = "Short environment identifier."
  type        = string
  default     = "dev"
  validation {
    condition     = contains(["dev", "test", "prod"], var.environment)
    error_message = "environment must be dev, test, or prod"
  }
}

variable "name_prefix" {
  description = "Resource-name prefix."
  type        = string
  default     = "pharma-data"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,19}$", var.name_prefix))
    error_message = "name_prefix must be 3-20 lowercase letters, numbers, or hyphens"
  }
}

variable "raw_retention_days" {
  description = "Retention period for landed synthetic raw objects."
  type        = number
  default     = 30
  validation {
    condition     = var.raw_retention_days >= 7 && var.raw_retention_days <= 365
    error_message = "raw_retention_days must be between 7 and 365"
  }
}

variable "cloud_run_image" {
  description = "Digest-pinned container image for the ingestion Cloud Run job."
  type        = string
  default     = "europe-north1-docker.pkg.dev/portfolio-project/data/pharma-ingest@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  validation {
    condition     = can(regex("@sha256:[0-9a-f]{64}$", var.cloud_run_image))
    error_message = "cloud_run_image must be pinned by sha256 digest"
  }
}

variable "input_object" {
  description = "Cloud Storage object processed by the scheduled reference job."
  type        = string
  default     = "incoming/batch-events.ndjson"
  validation {
    condition     = can(regex("^[a-zA-Z0-9][a-zA-Z0-9/_.,=-]{0,511}$", var.input_object))
    error_message = "input_object must be a bounded relative Cloud Storage object name"
  }
}

