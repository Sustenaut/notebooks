Feature: Queries reach BigQuery as typed parameters

  Scenario: Parameter names skip comments strings and system variables
    Then parameter names skip comments strings and system variables

  Scenario: Values become typed query parameters
    Then values become typed query parameters

  Scenario: Values without a bigquery type are refused
    Then values without a bigquery type are refused

  Scenario: Values go as query parameters never into the sql
    Then values go as query parameters never into the sql

  Scenario: A dry run comes first and the byte cap is set
    Then a dry run comes first and the byte cap is set

  Scenario: The cap defaults to a gibibyte
    Then the cap defaults to a gibibyte

  Scenario: A query over the cap never runs
    Then a query over the cap never runs

  Scenario: Dry run reports bytes
    Then dry run reports bytes

  Scenario: Parameters must match the sql
    Then parameters must match the sql

  Scenario: Offline reads the sample and never makes a client
    Then offline reads the sample and never makes a client

  Scenario: Offline reads json and parquet samples
    Then offline reads json and parquet samples

  Scenario: Offline without a sample says so
    Then offline without a sample says so

  Scenario: Online is the default and makes its client on first use
    Then online is the default and makes its client on first use

  Scenario: The repository queries have samples
    Then the repository queries have samples

  Scenario: The billing query has no sample until the export exists
    Then the billing query has no sample until the export exists
