Feature: Queries reach BigQuery as typed parameters
  A query is a .sql file whose values are named parameters. Online, a stand-in BigQuery records
  each job it is asked; offline, the result is the query's sample. A query's values are a table of
  parameter and value: a value that reads as JSON is that JSON, "date D" is the date D, anything
  else is text.

  Background:
    Given a scratch directory
    And a file "queries/costs.sql" holding:
      """
      -- @not_a_parameter in a comment
      SELECT '@not_one_either', @@query_label FROM t WHERE site = @site AND day BETWEEN @start AND @end
      """

  Scenario: Parameter names skip comments strings and system variables
    When the parameters of this SQL are read:
      """
      SELECT "@a", `@b`, @@x /* @c */ # @d
      FROM t WHERE x = @e AND y IN UNNEST(@f_2)
      """
    Then the result is "["e", "f_2"]"

  Scenario Outline: A value becomes a query parameter of its BigQuery type
    When <value> becomes a query parameter
    Then the result has 1 parameter
    And the result's "0.class" is "ScalarQueryParameter"
    And the result's "0.name" is "v"
    And the result's "0.type" is "<type>"

    Examples:
      | value              | type      |
      | a bool             | BOOL      |
      | an int             | INT64     |
      | a float            | FLOAT64   |
      | a decimal          | NUMERIC   |
      | a text             | STRING    |
      | bytes              | BYTES     |
      | a zoned datetime   | TIMESTAMP |
      | a local datetime   | DATETIME  |
      | a date             | DATE      |
      | a time of day      | TIME      |

  Scenario: A list becomes an array query parameter
    When a list of texts becomes a query parameter
    Then the result's "0.class" is "ArrayQueryParameter"
    And the result's "0.type" is "STRING"
    And the result's "0.values" is "["tartu", "parnu"]"

  Scenario Outline: Values without a bigquery type are refused
    When <value> becomes a query parameter
    Then it is refused, saying "<says>"
    And the refusal's "__class__.__name__" is "QueryError"

    Examples:
      | value        | says                                     |
      | nothing      | v is None, whose type BigQuery cannot tell |
      | an empty list | v is an empty list                      |
      | a mixed list | v mixes types: INT64, STRING             |
      | an object    | no BigQuery type for object              |

  Scenario: Values go as query parameters never into the sql
    Given a BigQuery that scans 1000 bytes
    When the query "costs" runs with:
      | parameter | value           |
      | site      | x' OR '1'='1    |
      | start     | date 2026-03-01 |
      | end       | date 2026-03-31 |
    Then the result is:
      """
      {"rows": [{"n": 1}], "bytes_estimated": 1000, "bytes_billed": 1000, "offline": false}
      """
    And the file "queries/costs.sql" does not include "x' OR '1'='1"
    And BigQuery was asked these jobs:
      """
      [
        {
          "sql": "-- @not_a_parameter in a comment\nSELECT '@not_one_either', @@query_label FROM t WHERE site = @site AND day BETWEEN @start AND @end\n",
          "dry_run": true, "use_query_cache": false, "maximum_bytes_billed": null,
          "parameters": {
            "end": {"type": "DATE", "value": "2026-03-31"},
            "site": {"type": "STRING", "value": "x' OR '1'='1"},
            "start": {"type": "DATE", "value": "2026-03-01"}
          }
        },
        {
          "sql": "-- @not_a_parameter in a comment\nSELECT '@not_one_either', @@query_label FROM t WHERE site = @site AND day BETWEEN @start AND @end\n",
          "dry_run": null, "use_query_cache": null, "maximum_bytes_billed": 1073741824,
          "parameters": {
            "end": {"type": "DATE", "value": "2026-03-31"},
            "site": {"type": "STRING", "value": "x' OR '1'='1"},
            "start": {"type": "DATE", "value": "2026-03-01"}
          }
        }
      ]
      """

  Scenario: A dry run comes first and the byte cap is set
    Given a BigQuery that scans 1000 bytes
    And the byte cap is 5000
    When the query "costs" runs with:
      | parameter | value           |
      | site      | a               |
      | start     | date 2026-01-01 |
      | end       | date 2026-01-02 |
    Then BigQuery was asked these jobs:
      """
      [
        {
          "sql": "-- @not_a_parameter in a comment\nSELECT '@not_one_either', @@query_label FROM t WHERE site = @site AND day BETWEEN @start AND @end\n",
          "dry_run": true, "use_query_cache": false, "maximum_bytes_billed": null,
          "parameters": {
            "end": {"type": "DATE", "value": "2026-01-02"},
            "site": {"type": "STRING", "value": "a"},
            "start": {"type": "DATE", "value": "2026-01-01"}
          }
        },
        {
          "sql": "-- @not_a_parameter in a comment\nSELECT '@not_one_either', @@query_label FROM t WHERE site = @site AND day BETWEEN @start AND @end\n",
          "dry_run": null, "use_query_cache": null, "maximum_bytes_billed": 5000,
          "parameters": {
            "end": {"type": "DATE", "value": "2026-01-02"},
            "site": {"type": "STRING", "value": "a"},
            "start": {"type": "DATE", "value": "2026-01-01"}
          }
        }
      ]
      """

  Scenario: The cap defaults to a gibibyte
    Given a BigQuery that scans 1000 bytes
    When the query "costs" runs with:
      | parameter | value |
      | site      | a     |
      | start     | x     |
      | end       | y     |
    Then BigQuery was asked these jobs:
      """
      [
        {
          "sql": "-- @not_a_parameter in a comment\nSELECT '@not_one_either', @@query_label FROM t WHERE site = @site AND day BETWEEN @start AND @end\n",
          "dry_run": true, "use_query_cache": false, "maximum_bytes_billed": null,
          "parameters": {
            "end": {"type": "STRING", "value": "y"},
            "site": {"type": "STRING", "value": "a"},
            "start": {"type": "STRING", "value": "x"}
          }
        },
        {
          "sql": "-- @not_a_parameter in a comment\nSELECT '@not_one_either', @@query_label FROM t WHERE site = @site AND day BETWEEN @start AND @end\n",
          "dry_run": null, "use_query_cache": null, "maximum_bytes_billed": 1073741824,
          "parameters": {
            "end": {"type": "STRING", "value": "y"},
            "site": {"type": "STRING", "value": "a"},
            "start": {"type": "STRING", "value": "x"}
          }
        }
      ]
      """


  Scenario: A query over the cap never runs
    Given a BigQuery that scans 10000 bytes
    And the byte cap is 9999
    When the query "costs" runs with:
      | parameter | value |
      | site      | a     |
      | start     | x     |
      | end       | y     |
    Then it is refused, saying "costs would scan 10000 bytes, more than the cap of 9999"
    And the refusal's "__class__.__name__" is "BytesCapExceeded"
    And the refusal's "estimate" is "10000"
    And the refusal's "cap" is "9999"
    And BigQuery was asked these jobs:
      """
      [
        {
          "sql": "-- @not_a_parameter in a comment\nSELECT '@not_one_either', @@query_label FROM t WHERE site = @site AND day BETWEEN @start AND @end\n",
          "dry_run": true, "use_query_cache": false, "maximum_bytes_billed": null,
          "parameters": {
            "end": {"type": "STRING", "value": "y"},
            "site": {"type": "STRING", "value": "a"},
            "start": {"type": "STRING", "value": "x"}
          }
        }
      ]
      """

  Scenario: Dry run reports bytes
    Given a BigQuery that scans 42 bytes
    When the query "costs" is dry run with:
      | parameter | value |
      | site      | a     |
      | start     | x     |
      | end       | y     |
    Then the result is "42"

  Scenario: Parameters must match the sql
    Given a BigQuery that scans 1000 bytes
    When the query "costs" runs with:
      | parameter | value |
      | site      | a     |
      | start     | x     |
    Then it is refused, saying "costs: no value for end"
    And the refusal's "__class__.__name__" is "QueryError"
    And BigQuery was asked these jobs:
      """
      []
      """

  Scenario: A value for every parameter and none more
    Given a BigQuery that scans 1000 bytes
    When the query "costs" runs with:
      | parameter | value |
      | site      | a     |
      | start     | x     |
      | end       | y     |
      | limit     | 3     |
    Then it is refused, saying "costs: no @parameter for limit"
    And the refusal's "__class__.__name__" is "QueryError"
    And BigQuery was asked these jobs:
      """
      []
      """

  Scenario: Offline reads the sample and never makes a client
    Given a file "samples/costs.csv" holding:
      """
      day,amount
      2026-03-01,4.5
      """
    And the environment sets "SUSTENAUT_DATA" to "offline"
    And BigQuery may not be reached
    When the query "costs" runs with:
      | parameter | value |
      | site      | a     |
      | start     | x     |
      | end       | y     |
    Then the result is:
      """
      {"rows": [{"day": "2026-03-01", "amount": 4.5}], "bytes_estimated": 0, "bytes_billed": 0, "offline": true}
      """

  Scenario: Offline a dry run scans nothing
    Given a file "samples/costs.csv" holding "day,amount"
    And the environment sets "SUSTENAUT_DATA" to "offline"
    And BigQuery may not be reached
    When the query "costs" is dry run with:
      | parameter | value |
      | site      | a     |
      | start     | x     |
      | end       | y     |
    Then the result is "0"

  Scenario: Offline the parameters are still checked
    Given a file "samples/costs.csv" holding "day,amount"
    And the environment sets "SUSTENAUT_DATA" to "offline"
    And BigQuery may not be reached
    When the query "costs" runs with:
      | parameter | value |
      | site      | a     |
    Then it is refused, saying "costs: no value for end, start"
    And the refusal's "__class__.__name__" is "QueryError"

  Scenario Outline: Offline reads json and parquet samples
    Given a sample "costs<suffix>" whose column "n" holds 1 and 2
    And the samples are used, not BigQuery
    When the query "costs" runs with:
      | parameter | value |
      | site      | a     |
      | start     | x     |
      | end       | y     |
    Then the result's "rows" is "[{"n": 1}, {"n": 2}]"

    Examples:
      | suffix   |
      | .json    |
      | .parquet |

  Scenario: Offline without a sample says so
    Given the samples are used, not BigQuery
    When the query "costs" runs with:
      | parameter | value |
      | site      | a     |
      | start     | x     |
      | end       | y     |
    Then it is refused, saying "no sample for costs"
    And the refusal's "__class__.__name__" is "FileNotFoundError"

  Scenario: Online is the default and makes no client until it is used
    Given the environment does not set "SUSTENAUT_DATA"
    And BigQuery's clients are counted
    When a runner is made
    Then the result is:
      """
      {"offline": false, "clients made": 0}
      """

  Scenario: Online makes its client on first use and keeps it
    Given the environment does not set "SUSTENAUT_DATA"
    And BigQuery's clients are counted
    When a runner's client is asked for twice
    Then the result is:
      """
      {"clients": ["client", "client"], "clients made": 1}
      """

  Scenario Outline: The repository queries have samples
    When the repository's query "<name>" runs offline with "<values>"
    Then it is not refused
    And the result's "parameters" is "<parameters>"
    And the result's "empty" is "false"

    Examples:
      | name           | values                                                                | parameters                    |
      | calls_per_day  | {"start": "2026-10-04", "end": "2026-11-02", "projects": ["visit_ee"]} | ["end", "projects", "start"] |
      | status_per_day | {"start": "2026-10-04", "end": "2026-11-02", "projects": ["visit_ee"]} | ["end", "projects", "start"] |
      | table_storage  | {"tables": ["calls"]}                                                 | ["tables"]                    |

  Scenario: The billing query has no sample until the export exists
    When the repository's query "billing" runs offline with "{"month": "202611"}"
    Then it is refused, saying "no sample for billing"
    And the refusal's "__class__.__name__" is "FileNotFoundError"

  Scenario: The billing query takes the invoice month
    When the parameters of the repository's query "billing" are read
    Then the result is "["month"]"
