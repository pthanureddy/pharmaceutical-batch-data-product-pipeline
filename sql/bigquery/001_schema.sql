CREATE SCHEMA IF NOT EXISTS `portfolio-project.pharma_raw`
OPTIONS (
  location = 'EU',
  description = 'Immutable accepted pharmaceutical batch events'
);

CREATE SCHEMA IF NOT EXISTS `portfolio-project.pharma_curated`
OPTIONS (
  location = 'EU',
  description = 'Curated pharmaceutical batch data product'
);

CREATE SCHEMA IF NOT EXISTS `portfolio-project.pharma_ops`
OPTIONS (
  location = 'EU',
  description = 'Pipeline quality and operational evidence'
);

CREATE TABLE IF NOT EXISTS `portfolio-project.pharma_raw.raw_batch_event` (
  event_id STRING NOT NULL,
  event_digest STRING NOT NULL,
  event_type STRING NOT NULL,
  occurred_at TIMESTAMP NOT NULL,
  site_id STRING NOT NULL,
  line_id STRING NOT NULL,
  batch_id STRING NOT NULL,
  material_id STRING NOT NULL,
  source_system STRING NOT NULL,
  sequence_no INT64 NOT NULL,
  payload_json JSON NOT NULL,
  ingested_at TIMESTAMP NOT NULL,
  source_object STRING NOT NULL
)
PARTITION BY DATE(occurred_at)
CLUSTER BY batch_id, site_id, event_type;

CREATE TABLE IF NOT EXISTS `portfolio-project.pharma_curated.batch_snapshot` (
  batch_id STRING NOT NULL,
  site_id STRING NOT NULL,
  line_id STRING NOT NULL,
  material_id STRING NOT NULL,
  started_at TIMESTAMP,
  released_at TIMESTAMP,
  quality_status STRING,
  completed_step_count INT64 NOT NULL,
  latest_sequence_no INT64 NOT NULL,
  latest_event_at TIMESTAMP NOT NULL,
  source_event_count INT64 NOT NULL,
  refreshed_at TIMESTAMP NOT NULL
)
CLUSTER BY site_id, line_id, quality_status;

CREATE TABLE IF NOT EXISTS `portfolio-project.pharma_ops.data_quality_issue` (
  issue_id STRING NOT NULL,
  event_id STRING,
  issue_code STRING NOT NULL,
  issue_message STRING NOT NULL,
  raw_digest STRING NOT NULL,
  raw_payload STRING NOT NULL,
  source_object STRING NOT NULL,
  recorded_at TIMESTAMP NOT NULL
)
PARTITION BY DATE(recorded_at)
CLUSTER BY issue_code, source_object;
