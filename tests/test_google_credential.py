"""The app reaches BigQuery with no key: google-auth reads the external_account
credential in k8s/google-credential.yaml, whose audience must be the projected
token's and the services pool's provider. A mismatch fails only at run time, as
Google's STS refusing the token."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PROVIDER = ("//iam.googleapis.com/projects/948171295184/locations/global/workloadIdentityPools/services/"
            "providers/sustenaut-k3s")


def test_the_token_the_credential_and_the_provider_name_one_audience():
    configmap = yaml.safe_load((ROOT / "k8s" / "google-credential.yaml").read_text(encoding="utf-8"))
    credential = json.loads(configmap["data"]["credential.json"])
    assert credential["type"] == "external_account" and credential["audience"] == PROVIDER
    assert credential["service_account_impersonation_url"].endswith(
        "/notebooks-reader@sustenaut.iam.gserviceaccount.com:generateAccessToken")
    app = next(d for d in yaml.safe_load_all((ROOT / "k8s" / "app.yaml").read_text(encoding="utf-8"))
               if d and d["kind"] == "Deployment")
    spec = app["spec"]["template"]["spec"]
    assert spec["serviceAccountName"] == "app" and spec["automountServiceAccountToken"] is False
    (volume,) = [v for v in spec["volumes"] if v["name"] == "google-token"]
    (source,) = volume["projected"]["sources"]
    assert source["serviceAccountToken"]["audience"] == PROVIDER
    container = next(c for c in spec["containers"] if c["name"] == "app")
    mounts = {m["name"]: m["mountPath"] for m in container["volumeMounts"]}
    assert f"{mounts['google-token']}/{source['serviceAccountToken']['path']}" == credential["credential_source"]["file"]
    env = {e["name"]: e.get("value") for e in container["env"]}
    assert env["GOOGLE_APPLICATION_CREDENTIALS"] == f"{mounts['google-credential']}/credential.json"


def test_google_auth_takes_the_credential_without_a_key(tmp_path):
    import google.auth

    configmap = yaml.safe_load((ROOT / "k8s" / "google-credential.yaml").read_text(encoding="utf-8"))
    credential = json.loads(configmap["data"]["credential.json"])
    credential["credential_source"]["file"] = str(tmp_path / "token")
    (tmp_path / "credential.json").write_text(json.dumps(credential), encoding="utf-8")
    found, _project = google.auth.load_credentials_from_file(str(tmp_path / "credential.json"))
    assert type(found).__module__ == "google.auth.identity_pool"
    assert found.service_account_email == "notebooks-reader@sustenaut.iam.gserviceaccount.com"
