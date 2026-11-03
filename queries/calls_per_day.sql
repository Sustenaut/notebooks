-- Calls per day for each project, plugin and operation, between @start and @end (dates, inclusive), for the
-- projects in @projects. Each project's call log is its own dataset, so the four are read side by side.
WITH calls AS (
  SELECT 'integrations' AS project, * FROM `sustenaut.calls_integrations.calls`
  UNION ALL SELECT 'visit_ee', * FROM `sustenaut.calls_visit_ee.calls`
  UNION ALL SELECT 'opportunity_site', * FROM `sustenaut.calls_opportunity_site.calls`
  UNION ALL SELECT 'business_plan', * FROM `sustenaut.calls_business_plan.calls`
)
SELECT
  DATE(`at`) AS day,
  project,
  plugin,
  operation,
  COUNT(*) AS calls,
  COUNTIF(outcome != 'ok') AS not_ok,
  SUM(bytes_in) AS bytes_in,
  SUM(bytes_out) AS bytes_out,
  APPROX_QUANTILES(latency_ms, 100)[OFFSET(95)] AS p95_latency_ms
FROM calls
WHERE `at` >= TIMESTAMP(@start)
  AND `at` < TIMESTAMP(DATE_ADD(@end, INTERVAL 1 DAY))
  AND project IN UNNEST(@projects)
GROUP BY day, project, plugin, operation
ORDER BY day, project, plugin, operation
