Feature: The cost model

  Scenario: A fixed price is quantity times price and a yearly one a twelfth
    Then a fixed price is quantity times price and a yearly one a twelfth

  Scenario: A usage price charges beyond the allowance with its plan fee once
    Then a usage price charges beyond the allowance with its plan fee once

  Scenario: Empty values read as none or zero
    Then empty values read as none or zero

  Scenario: Weights split by the share table and evenly without one
    Then weights split by the share table and evenly without one

  Scenario: Fixed costs follow the shares and unknown prices are listed not counted
    Then fixed costs follow the shares and unknown prices are listed not counted

  Scenario: Usage costs use the account wide allowance and follow each site s usage
    Then usage costs use the account wide allowance and follow each site s usage

  Scenario: A per table metric is checked per site and load jobs never pass one per cycle
    Then a per table metric is checked per site and load jobs never pass one per cycle

  Scenario: The server moves to the next type past the headroom
    Then the server moves to the next type past the headroom

  Scenario: Without a server row there is no server cost
    Then without a server row there is no server cost

  Scenario: Growth marks each step where it happens
    Then growth marks each step where it happens

  Scenario: Usage now turns the query results into monthly usage per site
    Then usage now turns the query results into monthly usage per site

  Scenario: Usage now with nothing read is zero and skips sites it does not cost
    Then usage now with nothing read is zero and skips sites it does not cost

  Scenario: The defaults come from the data files
    Then the defaults come from the data files

  Scenario: Every price row has a source date and a reason when unpriced
    Then every price row has a source date and a reason when unpriced

  Scenario: The billing summary nets credits per service
    Then the billing summary nets credits per service
