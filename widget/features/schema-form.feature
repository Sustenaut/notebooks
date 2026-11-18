Feature: SchemaFormWidget's front end
  The widget draws a JSON Forms form from the schema Python gives it, and
  sends back the data and its errors through anywidget's model, here a
  model held in memory, in jsdom. The site form has one field, Site, a text
  of at least two characters that is required. What the widget shows is the
  Site field's value, what it last saved, and how many listeners it keeps on
  the model.

  Scenario: It draws the form from the value and sends its errors back
    Given a model of the site form whose value is '{"site": "x"}'
    When the widget is drawn
    Then the result's "field" is "x"
    And the result's "saved.errors" is '[{"path": "/site", "message": "must NOT have fewer than 2 characters"}]'

  Scenario: It brings its styles
    Given a model of the site form whose value is '{"site": "x"}'
    When the widget is drawn
    And its first style is read
    Then the result includes "rounded-control"

  Scenario: It sends what is typed back
    Given a model of the site form whose value is '{"site": "x"}'
    When the widget is drawn
    And "Tartu" is typed into the field
    Then the result's "saved.value" is '{"site": "Tartu"}'
    And the result's "saved.errors" is "[]"

  Scenario: It draws a value Python changes
    Given a model of the site form whose value is '{"site": "x"}'
    When the widget is drawn
    And Python changes the value to '{"site": "Pärnu"}'
    Then the result's "field" is "Pärnu"

  Scenario: It stops listening once it is taken down
    Given a model of the site form whose value is '{"site": "x"}'
    When the widget is drawn
    And the widget is taken down
    Then the result's "listeners" is "0"

  Scenario: It starts from empty data
    Given a model of the site form with no value
    When the widget is drawn twice
    Then the result's "saved.value" is "{}"

  Scenario: It registers Tailwind's properties once
    Given a model of the site form with no value
    When the widget is drawn twice
    And the registered properties are read
    Then the result has 1 style

  Scenario: The registered properties are Tailwind's
    Given a model of the site form with no value
    When the widget is drawn twice
    And the first registered property style is read
    Then the result matches "@property --tw-*"

  Scenario: It reports no errors as none
    When no errors are turned into messages
    Then the result is "[]"

  Scenario: It reports errors without a path or message as empty strings
    When the errors '[{}]' are turned into messages
    Then the result is '[{"path": "", "message": ""}]'
