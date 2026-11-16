ASSERT (
  SELECT COUNT(*) = COUNT(DISTINCT event_id)
  FROM `portfolio-project.pharma_raw.raw_batch_event`
) AS 'raw event_id values must remain unique';

ASSERT (
  SELECT COUNTIF(latest_event_at < TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)) = 0
  FROM `portfolio-project.pharma_curated.batch_snapshot`
) AS 'curated snapshots must meet the 24-hour freshness policy';

ASSERT (
  SELECT COUNTIF(issue_code = 'EVENT_ID_CONFLICT') = 0
  FROM `portfolio-project.pharma_ops.data_quality_issue`
  WHERE recorded_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 DAY)
) AS 'event-ID conflicts require operator review';
