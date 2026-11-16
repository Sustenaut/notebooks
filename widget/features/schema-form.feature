Feature: SchemaFormWidget's front end
  The widget draws a JSON Forms form from the schema Python gives it, and
  sends back the data and its errors through anywidget's model, here a
  model held in memory, in jsdom.

  Scenario: It draws the form and sends its data and errors back
    Then it draws the form and sends its data and errors back

  Scenario: It starts from empty data and registers Tailwind's properties once
    Then it starts from empty data and registers Tailwind's properties once

  Scenario: It reports errors without a path or message as empty strings
    Then it reports errors without a path or message as empty strings
