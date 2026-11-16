Feature: Each notebook passes marimo check and runs headless, offline, from start to end

  Scenario: There are notebooks
    Then there are notebooks

  Scenario: Marimo check passes
    Then marimo check passes

  Scenario: Each notebook runs headless offline
    Then each notebook runs headless offline

  Scenario: Site costs shows every section offline
    Then site costs shows every section offline
