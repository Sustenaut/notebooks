Feature: The site behind oauth2-proxy
  The access gate on each request and websocket, the front page, the notebooks. oauth2-proxy
  passes the person's email in X-Forwarded-Email and their token in X-Forwarded-Access-Token.
  Behind the gate, the notebooks answer "notebook" and accept a websocket; the access check
  answers from what each scenario gives it, and no role for anyone else.

  Background:
    Given the access check answers "ok" for "member@sustenaut.eu"
    And the access check answers "degraded" for "reading@sustenaut.eu"
    And the access check answers "sign_in" for "gone@sustenaut.eu"
    And the access check answers "unavailable" for "later@sustenaut.eu"

  Scenario: Someone with the role gets through
    Given the notebooks behind the gate
    And I am signed in as "member@sustenaut.eu"
    And requests carry the header "X-Forwarded-Access-Token" set to "tok"
    When I GET "/site_costs"
    Then the answer is 200
    And the result's "text" is "notebook"
    And the access check was asked:
      | person              | token | write |
      | member@sustenaut.eu | tok   | false |

  Scenario: Someone with the role opens a websocket
    Given the notebooks behind the gate
    And I am signed in as "member@sustenaut.eu"
    And requests carry the header "X-Forwarded-Access-Token" set to "t"
    When a websocket opens "/site_costs/ws"
    Then the result's "0.type" is "websocket.accept"
    And the access check was asked:
      | person              | token | write |
      | member@sustenaut.eu | t     | false |

  Scenario: Someone let in on the last answer reads on
    Given the notebooks behind the gate
    And I am signed in as "reading@sustenaut.eu"
    And requests carry the header "X-Forwarded-Access-Token" set to "t"
    When I GET "/x"
    Then the answer is 200
    And the access check was asked:
      | person               | token | write |
      | reading@sustenaut.eu | t     | false |

  Scenario: Without the role the site refuses
    Given the notebooks behind the gate
    And I am signed in as "stranger@sustenaut.eu"
    When I GET "/site_costs"
    Then the answer is 403
    And the answer includes "team access page"

  Scenario: Without the role a websocket is closed
    Given the notebooks behind the gate
    And I am signed in as "stranger@sustenaut.eu"
    When a websocket opens "/ws"
    Then the result is "[{"type": "websocket.close", "code": 4403}]"

  Scenario: An ended session is sent to sign in keeping where it was
    Given the notebooks behind the gate
    And I am signed in as "gone@sustenaut.eu"
    When I GET "/site_costs/?a=1"
    Then the answer is 302
    And the answer's "location" is "/oauth2/sign_in?rd=%2Fsite_costs%2F%3Fa%3D1"

  Scenario: No email is sent to sign in
    Given the notebooks behind the gate
    And I am not signed in
    When I GET "/"
    Then the answer is 302
    And the answer's "location" is "/oauth2/sign_in?rd=%2F"

  Scenario: A websocket with no email is closed as unsigned
    Given the notebooks behind the gate
    And I am not signed in
    When a websocket opens "/ws"
    Then the result is "[{"type": "websocket.close", "code": 4401}]"

  Scenario: When auth cannot vouch the site says try later
    Given the notebooks behind the gate
    And I am signed in as "later@sustenaut.eu"
    When I GET "/x"
    Then the answer is 503

  Scenario: When auth cannot vouch a websocket is closed to try later
    Given the notebooks behind the gate
    And I am signed in as "later@sustenaut.eu"
    When a websocket opens "/ws"
    Then the result is "[{"type": "websocket.close", "code": 4503}]"

  Scenario: Health is open
    Given the notebooks behind the gate
    And I am not signed in
    When I GET "/healthz"
    Then the answer is 200
    And the result's "text" is "ok"
    And the access check was asked:
      | person | token | write |

  Scenario: Lifespan passes through
    Given the notebooks behind the gate
    When the server starts the site
    Then the result is "["lifespan"]"
    And the access check was asked:
      | person | token | write |

  Scenario: Each notebook has its address
    Given a scratch directory
    And a file "site_costs.py" holding "#"
    And a file "b.py" holding "#"
    And a file "data.json" holding "{}"
    When the notebooks in the scratch directory are given their addresses
    Then the result is "["/b", "/site_costs"]"

  Scenario: The front page links the notebooks
    Given a scratch directory
    And a file "site_costs.py" holding "#"
    And a file "b.py" holding "#"
    And the front page of the notebooks in the scratch directory
    When I GET "/"
    Then the answer is 200
    And the answer's "content-type" is "text/html; charset=utf-8"
    And the answer includes "<a href="/site_costs">Site costs</a>"

  Scenario: The built site serves the front page behind the gate
    Given the site built from the repository's notebooks
    And I am signed in as "member@sustenaut.eu"
    When I GET "/"
    Then the answer includes "/site_costs"

  Scenario Outline: The built site keeps the front page and the notebooks behind the gate
    Given the site built from the repository's notebooks
    And I am signed in as "stranger@sustenaut.eu"
    When I GET "<path>"
    Then the answer is 403

    Examples:
      | path        |
      | /           |
      | /site_costs |

  Scenario: The site needs its sign in client
    Given the environment does not set "NOTEBOOKS_CLIENT_ID"
    And the environment does not set "NOTEBOOKS_CLIENT_SECRET"
    When the site is made from the environment
    Then it is refused, saying "make apps"
    And the refusal's "__class__.__name__" is "RuntimeError"

  Scenario: The app is not made without the sign in client
    Given the environment does not set "NOTEBOOKS_CLIENT_ID"
    And the environment does not set "NOTEBOOKS_CLIENT_SECRET"
    When the site module is asked for "app"
    Then it is refused
    And the refusal's "__class__.__name__" is "RuntimeError"

  Scenario: The site module has nothing else to give
    When the site module is asked for "not_a_name"
    Then it is refused
    And the refusal's "__class__.__name__" is "AttributeError"

  Scenario: The app is the gate with the sign in client
    Given the environment sets "NOTEBOOKS_CLIENT_ID" to "id"
    And the environment sets "NOTEBOOKS_CLIENT_SECRET" to "secret"
    When the site module is asked for "app"
    Then the result's "__class__.__name__" is "AccessGate"
    And the result's "check.client_id" is "id"
    And the result's "check.role" is "notebooks"
    And the result's "check.realm_url" is "https://auth.sustenaut.eu/realms/team"
