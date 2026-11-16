Feature: The site behind oauth2-proxy
  The access gate on each request and websocket, the front page, the notebooks.

  Scenario: Someone with the role gets through and every request is a read
    Then someone with the role gets through and every request is a read

  Scenario: Without the role the site refuses
    Then without the role the site refuses

  Scenario: An ended session or no email is sent to sign in keeping where it was
    Then an ended session or no email is sent to sign in keeping where it was

  Scenario: When auth cannot vouch the site says try later
    Then when auth cannot vouch the site says try later

  Scenario: Health is open and lifespan passes through
    Then health is open and lifespan passes through

  Scenario: Each notebook has its address and the front page links them
    Then each notebook has its address and the front page links them

  Scenario: The built site serves the front page and the notebooks behind the gate
    Then the built site serves the front page and the notebooks behind the gate

  Scenario: The site needs its sign in client
    Then the site needs its sign in client
