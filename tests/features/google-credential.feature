Feature: The app reaches BigQuery with no key
  google-auth reads the external_account credential, whose audience must be the services pool's provider.
  The manifests are k8s/google-credential.yaml (the credential) and k8s/app.yaml (the Deployment that
  mounts it and the pod's projected token).

  Scenario: The token the credential and the provider name one audience
    When the credential and the Deployment are read from the manifests
    Then the result's "credential.type" is "external_account"
    And the result's "credential.audience" is "//iam.googleapis.com/projects/948171295184/locations/global/workloadIdentityPools/services/providers/sustenaut-k3s"
    And the result's "token.audience" is "//iam.googleapis.com/projects/948171295184/locations/global/workloadIdentityPools/services/providers/sustenaut-k3s"
    And the result's "credential.service_account_impersonation_url" is "https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/notebooks-reader@sustenaut.iam.gserviceaccount.com:generateAccessToken"

  Scenario: The pod runs as its own account with no API token
    When the credential and the Deployment are read from the manifests
    Then the result's "pod.serviceAccountName" is "app"
    And the result's "pod.automountServiceAccountToken" is "false"
    And the result's "token.volumes" is "1"
    And the result's "token.sources" is "1"

  Scenario: The credential reads the token where the pod mounts it
    When the credential and the Deployment are read from the manifests
    Then the result's "token.file" is "/var/run/secrets/google/token"
    And the result's "credential.credential_source.file" is "/var/run/secrets/google/token"
    And the result's "app.GOOGLE_APPLICATION_CREDENTIALS" is "/etc/google/credential.json"
    And the result's "app.credential file" is "/etc/google/credential.json"

  Scenario: Google auth takes the credential without a key
    Given a scratch directory
    When google-auth loads the credential, its token in the scratch directory
    Then the result's "__class__.__module__" is "google.auth.identity_pool"
    And the result's "service_account_email" is "notebooks-reader@sustenaut.iam.gserviceaccount.com"
