"""The app reaches BigQuery with no key: google-auth reads the external_account
credential in k8s/google-credential.yaml, whose audience must be the projected
token's and the services pool's provider. A mismatch fails only at run time, as
Google's STS refusing the token."""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from pytest_bdd import scenarios, when

scenarios("google-credential.feature")

ROOT = Path(__file__).resolve().parents[2]


def credential():
    configmap = yaml.safe_load((ROOT / "k8s" / "google-credential.yaml").read_text(encoding="utf-8"))
    return json.loads(configmap["data"]["credential.json"])


def manifests():
    """The credential, the pod's spec, its projected token and the app container's mounts and environment."""
    app = next(d for d in yaml.safe_load_all((ROOT / "k8s" / "app.yaml").read_text(encoding="utf-8"))
               if d and d["kind"] == "Deployment")
    spec = app["spec"]["template"]["spec"]
    volumes = [v for v in spec["volumes"] if v["name"] == "google-token"]
    sources = volumes[0]["projected"]["sources"]
    token = sources[0]["serviceAccountToken"]
    container = next(c for c in spec["containers"] if c["name"] == "app")
    mounts = {m["name"]: m["mountPath"] for m in container["volumeMounts"]}
    env = {e["name"]: e.get("value") for e in container["env"]}
    return {
        "credential": credential(),
        "pod": {k: spec.get(k) for k in ("serviceAccountName", "automountServiceAccountToken")},
        "token": {"volumes": len(volumes), "sources": len(sources), "audience": token["audience"],
                  "file": f"{mounts['google-token']}/{token['path']}"},
        "app": {"GOOGLE_APPLICATION_CREDENTIALS": env["GOOGLE_APPLICATION_CREDENTIALS"],
                "credential file": f"{mounts['google-credential']}/credential.json"},
    }


@when("the credential and the Deployment are read from the manifests")
def read_manifests(ctx):
    ctx.attempt(manifests)


@when("google-auth loads the credential, its token in the scratch directory")
def google_auth_loads(ctx):
    import google.auth

    def load():
        found = credential()
        found["credential_source"]["file"] = str(ctx.directory / "token")
        (ctx.directory / "credential.json").write_text(json.dumps(found), encoding="utf-8")
        return google.auth.load_credentials_from_file(str(ctx.directory / "credential.json"))[0]

    ctx.attempt(load)
