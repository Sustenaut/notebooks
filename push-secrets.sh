#!/usr/bin/env bash
# Puts the notebooks site's secrets into the cluster on the Sustenaut k3s server: the
# Secret notebooks-secrets and the network policy (k8s/admin/), both in namespace
# notebooks. Run it from the repository root through with-secrets, after making the
# namespace (ssh root@sustenaut sustenaut-app notebooks), whenever a secret changes:
#
#   ./with-secrets ./push-secrets.sh
#
# From Bitwarden (which with-secrets exports in upper case):
#   notebooks-cookie-secret    oauth2-proxy's cookie secret (32 random bytes, base64)
#   notebooks-reader-key       notebooks-reader's key (shared-infra's infra/notebooks.tf), base64-encoded
#                              as pubkit service-account-key create writes it
# Who may sign in is not here: the team access page at auth.sustenaut.eu/realms/team/access
# is the one list. Not here either: the sign-in client oauth2-proxy uses (the Secret
# notebooks-oidc), which register-client.sh registers with auth.sustenaut.eu and puts in
# on the server.
# They travel to the server inside the SSH connection, never on a command line.
# The pods read them at start: after a change, restart them with
#   ssh root@sustenaut k3s kubectl -n notebooks rollout restart deployment/app deployment/oauth2-proxy
set -euo pipefail
root="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
# The server's name is a Terraform output of shared-infra's infra/: a checkout of it
# beside this one, or SHARED_INFRA=its path.
infra="${SHARED_INFRA:-$root/../shared-infra}/infra"
[ -d "$infra" ] || { echo "no shared-infra checkout at ${infra%/infra}: clone it beside this repository or set SHARED_INFRA" >&2; exit 1; }

for name in NOTEBOOKS_COOKIE_SECRET NOTEBOOKS_READER_KEY; do
  if [ -z "${!name:-}" ]; then
    echo "$name is not set: run this through ./with-secrets, and check the secret is in Bitwarden." >&2
    exit 1
  fi
done

# SSH reaches the server over Sustenaut's tailnet only (be signed in to it).
server=$(terraform -chdir="$infra" output -json sustenaut_server | jq -r .ssh_host)
b64() { printf '%s' "$1" | base64 -w0; }

# shellcheck disable=SC2087 # expanded here on purpose: the values go in the SSH stream
ssh "root@$server" 'k3s kubectl apply -f -' <<YAML
apiVersion: v1
kind: Secret
type: Opaque
metadata:
  name: notebooks-secrets
  namespace: notebooks
data:
  cookie-secret: $(b64 "$NOTEBOOKS_COOKIE_SECRET")
  notebooks-reader-key: $NOTEBOOKS_READER_KEY
---
$(cat "$root/k8s/admin/network-policy.yaml")
YAML
