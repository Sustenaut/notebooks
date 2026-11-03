-- What the senders and the ingest pod reported per day, between @start and @end (dates, inclusive), for the
-- projects in @projects: cycles, records sent, files loaded, and the load jobs used on each table.
WITH status AS (
  SELECT 'integrations' AS project, * FROM `sustenaut.calls_integrations.status`
  UNION ALL SELECT 'visit_ee', * FROM `sustenaut.calls_visit_ee.status`
  UNION ALL SELECT 'opportunity_site', * FROM `sustenaut.calls_opportunity_site.status`
  UNION ALL SELECT 'business_plan', * FROM `sustenaut.calls_business_plan.status`
)
SELECT
  DATE(`at`) AS day,
  project,
  COUNTIF(kind = 'sender') AS sender_cycles,
  COUNTIF(kind = 'sender' AND calls > 0) AS busy_sender_cycles,
  SUM(IF(kind = 'sender', calls, 0)) AS records_sent,
  SUM(IF(kind = 'sender', drops, 0)) AS drops,
  COUNTIF(kind = 'ingest') AS ingest_cycles,
  SUM(IF(kind = 'ingest', loaded_files, 0)) AS loaded_files,
  MAX(IF(kind = 'ingest', jobs_today, NULL)) AS calls_load_jobs,
  MAX(IF(kind = 'ingest', status_jobs_today, NULL)) AS status_load_jobs,
  MAX(IF(kind = 'ingest', inbox_bytes, NULL)) AS max_inbox_bytes
FROM status
WHERE `at` >= TIMESTAMP(@start)
  AND `at` < TIMESTAMP(DATE_ADD(@end, INTERVAL 1 DAY))
  AND project IN UNNEST(@projects)
GROUP BY day, project
ORDER BY day, project
