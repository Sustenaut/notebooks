-- A site's costs per day between two dates. Every value is a named query parameter.
SELECT day, category, amount_eur
FROM `sustenaut.costs.site_costs`
WHERE site = @site
  AND day BETWEEN @start AND @end
ORDER BY day, category
