# Sustenaut notebooks

[marimo](https://marimo.io) notebooks over Sustenaut's data in BigQuery, with forms drawn by
[@sustenaut/ui](https://github.com/Sustenaut/ui)'s JSON Forms renderers.

```sh
make lab       # edit the notebooks (marimo edit)
make apps      # use them as apps, code hidden (marimo run)
make offline   # the apps on samples/, without BigQuery
make test      # what CI runs
make image     # the site's image, as the deploy workflow builds it
```

`make lab` and `make apps` build what they need first: the Python environment from `uv.lock` (`make venv`,
which needs [uv](https://docs.astral.sh/uv/)) and the form widget from `package-lock.json` (`make widget`,
which needs Node 20.19 or later). Online, BigQuery is reached with the machine's Google credentials
(`gcloud auth application-default login`); nothing here holds a key.

## What is where

| Path | What it is |
|---|---|
| `notebooks/<name>.py` | A notebook: `site_costs.py`, what each site costs as its usage grows |
| `notebooks/<name>.form.json` | A notebook's form: `{"schema": <JSON Schema>, "uischema": <JSON Forms UI schema>}` |
| `queries/<name>.sql` | A query. Every value is a named parameter (`@projects`) |
| `samples/<name>.csv` | A query's sample result, read in offline mode (`.parquet` and `.json` work too). Made up by `samples/make_samples.py`: no real data is committed |
| `data/` | The Site costs model's starting values: `prices.json` (each row with its source and date), `shares.json`, `not_measured.json` |
| `notebooks_lib/` | The helpers: `bigquery.Runner`, `forms.load_form`, `widget.SchemaFormWidget`, and `costs`, the Site costs model |
| `widget/` | The widget's front end, built into `notebooks_lib/static/` (git-ignored) |

## Site costs

What each site costs a month, split into fixed shared costs (the server, volume, IP, subscriptions, split by
`data/shares.json`) and usage costs (beyond each free allowance, split by each site's usage); what the call log
shows of usage (calls per day per project and plugin, files written and load jobs per two-minute cycle); and how
each site's cost moves as its usage grows from 1x to 1000x, with the steps marked: a free allowance running out,
a call log table loading every cycle (720 of BigQuery's 1,500 load jobs a day), the server's next type. Google's
own bill shows once the billing export exists; until then it says there is no billing data yet.

A price that could not be read from the provider's page is `null` in `data/prices.json`, with a note saying so.
It counts as unknown, not zero: the notebook lists it beside the totals, which leave it out. Page requests are
not ingested yet, so Workers, Pages and R2 usage are entries in the form's "Not measured" tab, and so is the
server's load today.

## Queries

```python
from notebooks_lib.bigquery import Runner

result = Runner().run("calls_per_day", start=date(2026, 10, 1), end=date(2026, 10, 31), projects=["visit_ee"])
result.frame, result.bytes_estimated, result.bytes_billed
```

- **Named parameters only.** Values go to BigQuery as query parameters, typed from the Python value (a list is
  an `ARRAY`), and never into the SQL's text. A value the SQL has no `@parameter` for, or a parameter with no
  value, stops the query before it is sent.
- **A dry run first.** It reports the bytes the query would scan; above the cap (`max_bytes_billed`, 1 GiB by
  default) the query is not run. The real run sets `maximum_bytes_billed` to the cap too, so BigQuery itself
  refuses one that would cost more.
- **Offline.** With `SUSTENAUT_DATA=offline` nothing reaches BigQuery: the result is `samples/<name>.*`. The
  parameters are still checked and converted, so a notebook passes the same values offline as online.

## Forms

`load_form("site_costs")` reads `notebooks/site_costs.form.json`. `form.widget(value)` is a
`SchemaFormWidget`, an [anywidget](https://anywidget.dev) that draws the form with `SchemaForm` from
`@sustenaut/ui/jsonforms`. Its `value` is the form's data and its `errors` are JSON Forms' messages. In a
notebook, wrap it with `mo.ui.anywidget(...)` and read `.value["value"]`. Check values with
`form.errors(values)`, which applies the same schema with jsonschema (draft 7, as JSON Forms' ajv does) and
names each problem by its JSON Pointer.

`@sustenaut/ui` is pinned in `package.json` to the commit that merged its JSON Forms support
(Sustenaut/ui#4), as there is no release with it yet. Move the pin to a tag once one is cut.

## The site

https://notebooks.sustenaut.eu runs on the Sustenaut k3s server (shared-infra's `infra/hetzner.tf`), namespace
`notebooks`, as Sustenaut/opportunity-site does:

| Part | What it is |
|---|---|
| `Dockerfile` | Node builds the widget's bundle, then a Python image runs `uvicorn notebooks_lib.serve:app` as uid 1000. No key, token or data in it; the package `ghcr.io/sustenaut/notebooks` is public |
| `notebooks_lib/serve.py` | Each notebook as a marimo app at `/<name>` (code hidden), a page of links at `/`, behind the access check |
| `notebooks_lib/access_check.py` | A copy of Sustenaut/auth's: on each request and websocket, does the person still have the role `notebooks`? |
| `k8s/` | The app, oauth2-proxy (team realm, `--allowed-group=notebooks`), the ingress; `admin/` the network policy |
| `.github/workflows/deploy.yml` | Once CI passes on a merge to main: build, check and push the image, render `k8s/`, deploy over the tailnet, once `DEPLOY_NOTEBOOKS` is `on` |

BigQuery is read as `notebooks-reader` (shared-infra's `infra/notebooks.tf`), which may read the call log
datasets and `billing` and nothing else; its key is mounted in the app as `GOOGLE_APPLICATION_CREDENTIALS`.
Who may use the site is the team access page (auth.sustenaut.eu/realms/team/access), the column `notebooks`.

## Deploying

`.github/workflows/deploy.yml` builds the image on each merge to main, once CI has
passed, and applies `k8s/` to namespace `notebooks` with pubkit's `k8s-deploy.yml`,
once `DEPLOY_NOTEBOOKS` is `on`.

pubkit.json's `deploy` block lists everything else the deployment needs, and pubkit's
deploy walk checks each need and makes what it can. To take the site live, or bring it
back in step, from a checkout of this repository with Sustenaut/shared-infra and
Sustenaut/auth checked out beside it, on a machine on the admin tailnet, signed in to
`gh` and `gcloud`:

```sh
./with-secrets ./pubkit deploy walk --fulfil --server sustenaut --zones ../shared-infra/pubkit.json
```

It checks every need, prints the plan, and waits for a typed `yes`; then it makes each
missing need it can, over the admin channel (`ssh root@sustenaut`), and checks it again.
Every run can run again: what is ready is left alone. In order:

| Need | What the walk does |
|---|---|
| the namespace `notebooks` | the server's `sustenaut-app`, which makes it and its deploy identity |
| `bitwarden.generated` `notebooks-cookie-secret` | oauth2-proxy's cookie secret: a new one of its shape, written to Bitwarden, when it is missing or misshapen |
| `gcp.service-account-key` `notebooks-reader-key` | the BigQuery key for `notebooks-reader` (shared-infra's `infra/notebooks.tf`): made and written to Bitwarden when it is missing or not one of the account's live keys |
| the Secret `notebooks-secrets` | made from the cookie secret and the reader key; the app and oauth2-proxy restarted |
| `auth.sign-in-client` | sustenaut.eu's team-site client in the team realm, role `notebooks`: the approval record written into shared-infra's `infra/auth-approvals.json` when auth.sustenaut.eu wants one, and once the client is issued, the Secret `notebooks-oidc` made from it on the server |
| `k8s.manifests` | `k8s/admin/network-policy.yaml` applied: only oauth2-proxy's pods may reach the app |
| the deploy settings | the server's variables and secrets in pubkit.json's `"secrets"` on this repository, checked |
| `DEPLOY_NOTEBOOKS` and the rollout | the gate on, once everything before it is ready, and `deploy.yml` run and waited for |
| `service.health` | `https://notebooks.sustenaut.eu/healthz` answers |

A new cookie secret or reader key wants a Bitwarden token that may write: the walk asks
for it once, at a hidden prompt, and keeps it only in its process. An approval record is
a change to shared-infra: commit it there, merge, apply, and run the walk again.

Some needs it only checks, and says what a person does:

- **The DNS record** for `notebooks.sustenaut.eu`, in shared-infra's hosting block.
- **Who may use the site**: the column `notebooks` on the team access page.

`./pubkit deploy walk` without `--fulfil` (or `deploy check`) changes nothing, and
`./pubkit deploy walk --offline` checks only the files. `.github/workflows/deploy-check.yml`
walks the deployment every 30 minutes, read-only, with the deploy key, and writes the walk
to storage's `plane` tenant; it fails when a need is missing, drift or blocked.

### A new server

Before the walk: steps 1 to 7 of Sustenaut/auth's `README.md`, "Deploying" (the server,
the tailnet, the deploy secrets); `./with-secrets terraform -chdir=infra apply` in
shared-infra (the reader account, the DNS record and the `auth_team` output); and the
team realm, with everyone who may use the site holding the role `notebooks`. The ghcr
package `ghcr.io/sustenaut/notebooks` is **public** and holds no private code, so the
cluster pulls it without a secret; give this repository write access under *Manage
Actions access*. Branch protection is `./pubkit protect Sustenaut/notebooks`.

## Tests

`make test` runs the widget's typecheck and Vitest tests (`widget/*.test.tsx`), then pytest: the helpers
(`tests/test_bigquery.py`, `tests/test_forms.py`), `marimo check --strict` on every notebook, and a headless
run of each notebook in offline mode (`tests/test_notebooks.py`). Coverage goes to `coverage/` for
SonarQube Cloud. The repository's setup comes from pubkit (`pubkit.json`, `./pubkit sync --check`); see
`AGENTS.md`.
