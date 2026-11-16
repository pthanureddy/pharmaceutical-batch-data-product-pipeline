MERGE `portfolio-project.pharma_curated.batch_snapshot` AS tgt
USING (
  WITH deduplicated AS (
    SELECT * EXCEPT (ingestion_rank)
    FROM (
      SELECT
        raw_event.*,
        ROW_NUMBER() OVER (
          PARTITION BY event_id
          ORDER BY ingested_at DESC, source_object DESC
        ) AS ingestion_rank
      FROM `portfolio-project.pharma_raw.raw_batch_event` AS raw_event
      WHERE occurred_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
    ) AS ranked
    WHERE ingestion_rank = 1
  )

  SELECT
    batch_id,
    ARRAY_AGG(site_id ORDER BY occurred_at, sequence_no LIMIT 1)[SAFE_OFFSET(0)] AS site_id,
    ARRAY_AGG(line_id ORDER BY occurred_at, sequence_no LIMIT 1)[SAFE_OFFSET(0)] AS line_id,
    ARRAY_AGG(material_id ORDER BY occurred_at, sequence_no LIMIT 1)[SAFE_OFFSET(0)]
      AS material_id,
    MIN(IF(event_type = 'BATCH_STARTED', occurred_at, NULL)) AS started_at,
    MAX(IF(event_type = 'BATCH_RELEASED', occurred_at, NULL)) AS released_at,
    ARRAY_AGG(
      IF(event_type = 'QUALITY_RECORDED', JSON_VALUE(payload_json, '$.status'), NULL)
      IGNORE NULLS ORDER BY occurred_at DESC, sequence_no DESC LIMIT 1
    )[SAFE_OFFSET(0)] AS quality_status,
    COUNT(
      DISTINCT IF(event_type = 'STEP_COMPLETED', JSON_VALUE(payload_json, '$.step_code'), NULL)
    ) AS completed_step_count,
    MAX(sequence_no) AS latest_sequence_no,
    MAX(occurred_at) AS latest_event_at,
    COUNT(*) AS source_event_count,
    CURRENT_TIMESTAMP() AS refreshed_at
  FROM deduplicated
  GROUP BY batch_id
) AS src
  ON tgt.batch_id = src.batch_id
WHEN MATCHED THEN
  UPDATE
    SET
      site_id = src.site_id,
      line_id = src.line_id,
      material_id = src.material_id,
      started_at = src.started_at,
      released_at = src.released_at,
      quality_status = src.quality_status,
      completed_step_count = src.completed_step_count,
      latest_sequence_no = src.latest_sequence_no,
      latest_event_at = src.latest_event_at,
      source_event_count = src.source_event_count,
      refreshed_at = src.refreshed_at
WHEN NOT MATCHED THEN INSERT (
  batch_id,
  site_id,
  line_id,
  material_id,
  started_at,
  released_at,
  quality_status,
  completed_step_count,
  latest_sequence_no,
  latest_event_at,
  source_event_count,
  refreshed_at
) VALUES (
  src.batch_id,
  src.site_id,
  src.line_id,
  src.material_id,
  src.started_at,
  src.released_at,
  src.quality_status,
  src.completed_step_count,
  src.latest_sequence_no,
  src.latest_event_at,
  src.source_event_count,
  src.refreshed_at
);
