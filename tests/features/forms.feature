Feature: The forms the notebooks load
  A form is notebooks/<name>.form.json: a JSON Schema and the JSON Forms ui schema that draws it.
  Checking values gives the errors, each a path and a message, the kinds of error they are, and
  whether the values are valid.

  Scenario: A form loads its schema and ui schema
    When the form "site_costs" is loaded
    Then the result's "name" is "site_costs"
    And the result's "schema.required" is "["period", "projects"]"
    And the result's "uischema.type" is "Group"

  Scenario: Valid values pass
    When the form "site_costs" checks the values "{"period": {"start": "2026-03-01", "end": "2026-03-31"}, "projects": ["visit_ee"]}"
    Then the result is:
      """
      {"errors": [], "paths": [], "kinds": [], "valid": true}
      """

  Scenario: Errors name the value by its path
    When the form "site_costs" checks the values "{"projects": ["riga"], "period": {"start": "not a date"}}"
    Then the result is:
      """
      {
        "errors": [
          {"path": "/period", "message": "'end' is a required property"},
          {"path": "/period/start", "message": "'not a date' is not a 'date'"},
          {"path": "/projects/0", "message": "'riga' is not valid under any of the given schemas"}
        ],
        "paths": ["/period", "/period/start", "/projects/0"],
        "kinds": ["FormError"],
        "valid": false
      }
      """

  Scenario: No values miss what the form requires
    When the form "site_costs" checks the values "{}"
    Then the result's "valid" is "false"
    And the result's "errors" is "[{"path": "", "message": "'period' is a required property"}, {"path": "", "message": "'projects' is a required property"}]"

  Scenario: The model form is a categorization
    When the form "site_costs.model" is loaded
    Then the result's "uischema.type" is "Categorization"

  Scenario: The model form accepts the data files
    Given the values are the cost model's defaults
    When the form "site_costs.model" checks the values
    Then the result's "errors" is "[]"

  Scenario: The model form names the values out of its range
    Given the values are the cost model's defaults, but for "{"load_now": 200, "multipliers": {"pub": 0}}"
    When the form "site_costs.model" checks the values
    Then the result's "paths" is "["/load_now", "/multipliers/pub"]"

  Scenario: A schema that is not json schema is refused
    Given a scratch directory
    And a file "bad.form.json" holding "{"schema": {"type": 5}, "uischema": {}}"
    When the form "bad" is loaded from the scratch directory
    Then it is refused
    And the refusal's "__class__.__name__" is "SchemaError"

  Scenario: A missing form is an error
    Given a scratch directory
    When the form "nothing" is loaded from the scratch directory
    Then it is refused
    And the refusal's "__class__.__name__" is "FileNotFoundError"

  Scenario: A form becomes a widget whose value is its data
    Given the form "x" whose schema is "{"required": ["projects"]}" and ui schema is "{"type": "Group"}"
    When the form becomes a widget starting from "{"projects": ["visit_ee"]}"
    Then the result's "__class__.__name__" is "SchemaFormWidget"
    And the result's "schema" is "{"required": ["projects"]}"
    And the result's "uischema" is "{"type": "Group"}"
    And the result's "value" is "{"projects": ["visit_ee"]}"
    And the result's "errors" is "[]"

  Scenario: A widget starts from empty data
    Given the form "x" whose schema is "{}" and ui schema is "{}"
    When the form becomes a widget
    Then the result's "value" is "{}"

  Scenario: The widget's bundle is built
    When the widget is made
    Then the result's "__class__.__name__" is "SchemaFormWidget"
    And the file "notebooks_lib/static/schema_form.js" exists

  Scenario: The widget needs its built bundle
    Given a scratch directory
    And the widget's bundle is "missing.js" in the scratch directory
    When the widget is made
    Then it is refused, saying "make widget"
    And the refusal's "__class__.__name__" is "FileNotFoundError"

  Scenario: Every form is valid json schema with a ui schema
    When every form is loaded
    Then the result's "not laid out" is "[]"
