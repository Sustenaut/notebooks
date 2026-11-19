Feature: The cost model
  A price row is {"id": "x", "item": "X", "kind": "fixed", "quantity": 1, "free": 0,
  "price_eur": 10, "per": "month"} but for what a scenario gives it. The costs are split between
  the sites a and b, whose usage is nothing but what a scenario gives them, with the server at
  no load and 0.8 headroom unless a scenario says otherwise. Costs come per site (fixed, usage,
  total), in totals over the sites, per price row by id, with the server picked, its load, and
  the items whose price is unknown.

  Scenario Outline: A fixed price is quantity times price and a yearly one a twelfth
    Given a price row with "<row>"
    When its monthly cost is worked out
    Then the result is "<cost>"

    Examples:
      | row                                | cost |
      | {"quantity": 20, "price_eur": 0.5} | 10   |
      | {"per": "year", "price_eur": 12}   | 1    |
      | {"price_eur": null}                | null |

  Scenario Outline: A usage price charges beyond the allowance with its plan fee once
    Given a price row with "<row>"
    When its cost for a usage of <used> is worked out
    Then the result is "<cost>"

    Examples:
      | row                                                            | used | cost |
      | {"kind": "usage", "free": 3, "price_eur": 2, "step_fee_eur": 5} | 3    | 0    |
      | {"kind": "usage", "free": 3, "price_eur": 2, "step_fee_eur": 5} | 4    | 7    |
      | {"kind": "usage", "free": 3, "price_eur": null}                 | 1    | 0    |
      | {"kind": "usage", "free": 3, "price_eur": null}                 | 4    | null |

  Scenario: Empty values read as none or zero
    When the price row "{"id": "y", "price_eur": NaN, "quantity": null}" is read as it is
    Then the result is:
      """
      {"id": "y", "item": "y", "kind": "fixed", "metric": "", "quantity": 0, "free": 0, "price_eur": null,
       "step_fee_eur": 0, "per": "month", "capacity": null}
      """

  Scenario Outline: Weights split by the share table and evenly without one
    Given the share table "<shares>"
    When the weights of "x" between the sites are worked out
    Then the result is "<weights>"

    Examples:
      | shares                                         | weights              |
      | [{"site": "a", "x": 3}, {"site": "b", "x": 1}] | {"a": 0.75, "b": 0.25} |
      | []                                             | {"a": 0.5, "b": 0.5}   |
      | [{"site": "a", "x": 2}]                        | {"a": 1.0, "b": 0.0}   |
      | [{"site": "a", "x": 0}, {"site": "b", "x": 0}] | {"a": 0.5, "b": 0.5}   |
      | [{"site": "zz", "x": 9}]                       | {"a": 0.5, "b": 0.5}   |

  Scenario: Fixed costs follow the shares and unknown prices are listed not counted
    Given the price rows:
      """
      [{"id": "srv", "price_eur": 9}, {"id": "vol", "item": "Volume", "price_eur": null}]
      """
    And the share table "[{"site": "a", "srv": 2}, {"site": "b", "srv": 1}]"
    When the costs are worked out
    Then the result's "per_site.a.fixed" is about "6"
    And the result's "per_site.b.total" is about "3"
    And the result's "unpriced" is "["Volume"]"
    And the result's "items.vol.cost" is "null"

  Scenario: Usage costs use the account wide allowance and follow each site s usage
    Given the price rows:
      """
      [{"id": "st", "kind": "usage", "metric": "bq_storage_gib", "free": 10, "price_eur": 1}]
      """
    And the sites use:
      | metric         | a | b |
      | bq_storage_gib | 9 | 3 |
    When the costs are worked out
    Then the result's "per_site.a.usage" is about "1.5"
    And the result's "per_site.b.usage" is about "0.5"

  Scenario: Usage within the account wide allowance costs nothing
    Given the price rows:
      """
      [{"id": "st", "kind": "usage", "metric": "bq_storage_gib", "free": 10, "price_eur": 1}]
      """
    And the sites use:
      | metric         | a | b |
      | bq_storage_gib | 4 | 3 |
    When the costs are worked out
    Then the result's "totals.usage" is "0"

  Scenario: Usage past the allowance at an unknown price is listed not counted
    Given the price rows:
      """
      [{"id": "st", "item": "Storage", "kind": "usage", "metric": "bq_storage_gib", "free": 1, "price_eur": null}]
      """
    And the sites use:
      | metric         | a | b |
      | bq_storage_gib | 4 | 3 |
    When the costs are worked out
    Then the result's "unpriced" is "["Storage"]"

  Scenario: A per table metric is checked per site
    Given the price rows:
      """
      [{"id": "j", "item": "Jobs", "kind": "usage", "metric": "bq_load_jobs_day", "free": 1500, "price_eur": 0}]
      """
    And the sites use:
      | metric           | a   | b |
      | bq_load_jobs_day | 100 | 0 |
    When the costs are worked out with the multipliers "{"a": 1000}"
    Then the result's "totals.usage" is "0"

  Scenario: Load jobs never pass one per cycle
    Given the sites use:
      | metric           | a   | b |
      | bq_load_jobs_day | 100 | 0 |
    When the usage is scaled by the multipliers "{"a": 1000}"
    Then the result's "a.bq_load_jobs_day" is "720"

  Scenario: A per table metric past its allowance at an unknown price is listed
    Given the price rows:
      """
      [{"id": "j", "item": "Jobs", "kind": "usage", "metric": "bq_load_jobs_day", "free": 10, "price_eur": null}]
      """
    And the sites use:
      | metric           | a   | b |
      | bq_load_jobs_day | 100 | 0 |
    When the costs are worked out
    Then the result's "unpriced" is "["Jobs"]"

  Scenario: A per table metric past its allowance is charged to its site
    Given the price rows:
      """
      [{"id": "j", "kind": "usage", "metric": "bq_load_jobs_day", "free": 10, "price_eur": 1}]
      """
    And the sites use:
      | metric           | a  | b |
      | bq_load_jobs_day | 12 | 0 |
    When the costs are worked out
    Then the result's "per_site.a.usage" is "2"

  Scenario: A price on a metric nobody measures costs nothing
    Given the price rows:
      """
      [{"id": "w", "kind": "usage", "metric": "not_a_metric", "free": 0, "price_eur": 1}]
      """
    When the costs are worked out
    Then the result's "totals.usage" is "0"

  Scenario Outline: The server moves to the next type past the headroom
    Given the server types small, medium and large, medium priced at "20"
    And the server is at load 0.5 with 0.8 headroom
    When the costs are worked out with the multipliers "<multipliers>"
    Then the result's "server" is "<server>"
    And the result's "server_load" is "<load>"
    And the result's "totals.fixed" is "<fixed>"

    Examples:
      | multipliers          | server | load | fixed |
      | {}                   | small  | 0.5  | 10    |
      | {"a": 3, "b": 3}     | medium | 1.5  | 20    |
      | {"a": 20, "b": 20}   | large  | 10   | 40    |

  Scenario: A server type at an unknown price is listed not counted
    Given the server types small, medium and large, medium priced at "null"
    And the server is at load 0.5 with 0.8 headroom
    When the costs are worked out with the multipliers "{"a": 3, "b": 3}"
    Then the result's "unpriced" is "["medium"]"

  Scenario: With no server types no server is picked
    When a server is picked for a load of 1 with 0.8 headroom
    Then the result is empty

  Scenario: Without a server row there is no server cost
    Given the price rows:
      """
      [{"id": "gh", "price_eur": 4}]
      """
    When the costs are worked out
    Then the result is:
      """
      {
        "per_site": {"a": {"fixed": 2, "usage": 0, "total": 2}, "b": {"fixed": 2, "usage": 0, "total": 2}},
        "totals": {"fixed": 4, "usage": 0, "total": 4},
        "items": {"gh": {"item": "X", "kind": "fixed", "cost": 4}},
        "server": "", "server_load": 0, "unpriced": []
      }
      """

  Scenario: Without a server row nothing has happened to a site
    Given the price rows:
      """
      [{"id": "gh"}]
      """
    When the state of site "a" is read
    Then the result is empty

  Scenario: Growth marks each step where it happens
    Given the server types small, medium and large, medium priced at "20"
    And the price rows:
      """
      [
        {"id": "st", "item": "Storage", "kind": "usage", "metric": "bq_storage_gib", "free": 10, "price_eur": null},
        {"id": "j", "item": "Jobs", "kind": "usage", "metric": "bq_load_jobs_day", "free": 1500, "price_eur": 0}
      ]
      """
    And the sites use:
      | metric           | a  | b |
      | bq_storage_gib   | 1  | 0 |
      | bq_load_jobs_day | 72 | 0 |
    And the server is at load 0.4 with 0.8 headroom
    When the growth is drawn at the multipliers "[1, 3, 4, 10, 12, 30]"
    Then the result's "sites" is "["a", "b"]"
    And the result's "points" is "12"
    And the result's "cost.a.3" is about "5"
    And the result's "steps.a" is "{"4": ["server: medium"], "10": ["Jobs: one per cycle, 720 a day of the 1,500 limit", "server: large"], "12": ["Storage: free allowance used up (its price is unknown)"]}"
    And the result's "steps.b" is "{"4": ["server: medium"], "10": ["server: large"]}"

  Scenario: Usage now turns the query results into monthly usage per site
    Given the calls per day:
      | project  | calls |
      | visit_ee | 100   |
      | visit_ee | 200   |
    And the status per day:
      | project  | sender_cycles | ingest_cycles | busy_sender_cycles | calls_load_jobs |
      | visit_ee | 1440          | 1440          | 30                 | 15              |
    And the table storage:
      | project  | table_name | row_count | size_bytes |
      | visit_ee | calls      | 10        | 2000       |
      | visit_ee | status     | 0         | 0          |
    And what is not measured is "[{"site": "estimate", "workers_requests_day": 100000, "r2_writes_day": 1000}, {"site": "elsewhere"}]"
    And the notebooks run 1024 times a month
    When the usage now is worked out over 2 days
    Then the result's "usage.visit_ee.calls_day" is "150"
    And the result's "usage.visit_ee.storage_files_day" is "15"
    And the result's "usage.visit_ee.bq_load_jobs_day" is "15"
    # 150 calls a day at 200 bytes, plus 1,440 status rows a day at the 150 bytes of an empty table, for 395 days.
    And the result's "usage.visit_ee.bq_storage_gib" is about "0.09049661457538605"
    # 1,024 runs of 80 MiB.
    And the result's "usage.notebooks.bq_query_tib" is about "0.078125"
    And the result's "usage.estimate.workers_mreq" is about "3.0"
    And the result's "usage.estimate.r2_class_a_m" is about "0.03"
    And the result's "totals.integrations" is "0"

  Scenario: Usage now with nothing read is zero and skips sites it does not cost
    Given nothing was read
    And the only site is "visit_ee"
    When the usage now is worked out over 0 days
    Then the result's "sites" is "["visit_ee"]"
    And the result's "totals.visit_ee" is "0"

  Scenario: The defaults come from the data files
    Given a scratch directory
    And a file "prices.json" holding "{"rows": [{"id": "p"}]}"
    And a file "shares.json" holding "{"rows": [{"site": "a"}]}"
    And a file "not_measured.json" holding "{"notebook_runs_month": 7, "rows": []}"
    When the model's defaults are read from the scratch directory
    Then the result's "prices" is "[{"id": "p"}]"
    And the result's "shares" is "[{"site": "a"}]"
    And the result's "notebook_runs_month" is "7"
    And the result's "not_measured" is "[]"
    And the result's "multipliers" is "{"auth": 1, "integrations": 1, "visit_ee": 1, "opportunity_site": 1, "business_plan": 1, "pub": 1, "estimate": 1, "notebooks": 1}"
    And the result's "load_now" is "30"
    And the result's "headroom" is "80"

  Scenario: Every price row has a source date and a reason when unpriced
    When the repository's price list is read row by row
    Then the result's "ids used twice" is "[]"
    And the result's "sources not on https" is "[]"
    And the result's "without a date" is "[]"
    And the result's "without a note" is "[]"
    And the result's "of another kind" is "[]"
    And the result's "on an unknown metric" is "[]"
    And the result's "unpriced without saying so" is "[]"

  Scenario: The billing summary nets credits per service
    Given the billing rows:
      | service       | sku      | project   | currency | cost | credits |
      | BigQuery      | Analysis | sustenaut | EUR      | 2.0  | -2.0    |
      | BigQuery      | Storage  | sustenaut | EUR      | 1.0  | 0.0     |
      | Cloud Storage | Standard | sustenaut | EUR      | 0.5  | 0.0     |
    When the billing is summed up
    Then the result is:
      """
      [
        {"service": "BigQuery", "currency": "EUR", "cost": 3.0, "credits": -2.0, "net": 1.0},
        {"service": "Cloud Storage", "currency": "EUR", "cost": 0.5, "credits": 0.0, "net": 0.5}
      ]
      """

  Scenario: The billing summary of no rows is empty
    Given the billing rows:
      | service | sku | project | currency | cost | credits |
    When the billing is summed up
    Then the result is empty
