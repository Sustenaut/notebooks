Feature: Each notebook passes marimo check and runs headless, offline, from start to end

  Scenario: There are notebooks, each in the scenarios below
    When the notebooks are listed
    Then the result is "["site_costs"]"

  Scenario Outline: Marimo check passes
    When I run "python -m marimo check --strict notebooks/<notebook>.py"
    Then it succeeds

    Examples:
      | notebook   |
      | site_costs |

  Scenario Outline: Each notebook runs headless offline
    Given the environment sets "SUSTENAUT_DATA" to "offline"
    When I run "python notebooks/<notebook>.py"
    Then it succeeds

    Examples:
      | notebook   |
      | site_costs |

  Scenario: Site costs shows every section offline
    A cell that stops (mo.stop) defines nothing, so every section's names being there means each one ran.
    The result is what the notebook defines, with today's total over the sites and the kinds of step
    its growth curve marks.

    Given the environment sets "SUSTENAUT_DATA" to "offline"
    When the notebook "site_costs" runs in-process
    Then the result includes "today"
    And the result includes "curve"
    And the result includes "scenario"
    And the result includes "steps"
    And the result includes "billing_available"
    And the result's "billing_available" is "false"
    And the result's "calls.offline" is "true"
    And the result's "days" is "30"
    And the result's "today.unpriced" is "["Volume sustenaut-data", "Domain sustenaut.eu"]"
    # 8.99 + 0.50 + 4 / 1.1216 + 6 / 1.1216 + 4.00
    And the result's "today total" is about "22.4058" give or take "0.01"
    And the result's "step kinds.server" is "true"
    And the result's "step kinds.BigQuery batch load jobs" is "true"
