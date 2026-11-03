-- Google's cost per service and SKU in the invoice month @month ("YYYYMM"), from the standard usage cost
-- export (https://cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage). Its table is
-- named after the billing account, so the wildcard reads whichever export the dataset holds.
SELECT
  service.description AS service,
  sku.description AS sku,
  project.id AS project,
  currency,
  SUM(cost) AS cost,
  SUM(IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) AS c), 0)) AS credits
FROM `sustenaut.billing.gcp_billing_export_v1_*`
WHERE invoice.month = @month
GROUP BY service, sku, project, currency
ORDER BY cost DESC
