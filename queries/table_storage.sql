-- How much each call log table stores now. __TABLES__ needs only read access to its dataset.
SELECT
  REGEXP_REPLACE(dataset_id, r'^calls_', '') AS project,
  table_id AS table_name,
  row_count,
  size_bytes
FROM (
  SELECT * FROM `sustenaut.calls_integrations.__TABLES__`
  UNION ALL SELECT * FROM `sustenaut.calls_visit_ee.__TABLES__`
  UNION ALL SELECT * FROM `sustenaut.calls_opportunity_site.__TABLES__`
  UNION ALL SELECT * FROM `sustenaut.calls_business_plan.__TABLES__`
)
WHERE table_id IN UNNEST(@tables)
ORDER BY project, table_name
