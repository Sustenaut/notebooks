# Sustenaut notebooks

[marimo](https://marimo.io) notebooks over Sustenaut's data in BigQuery, with forms drawn by
[@sustenaut/ui](https://github.com/Sustenaut/ui)'s JSON Forms renderers.

```sh
make lab       # edit the notebooks (marimo edit)
make apps      # use them as apps, code hidden (marimo run)
make offline   # the apps on samples/, without BigQuery
make test      # what CI runs
```

`make lab` and `make apps` build what they need first: the Python environment from `uv.lock` (`make venv`,
which needs [uv](https://docs.astral.sh/uv/)) and the form widget from `package-lock.json` (`make widget`,
which needs Node 20.19 or later). Online, BigQuery is reached with the machine's Google credentials
(`gcloud auth application-default login`); nothing here holds a key.

## What is where

| Path | What it is |
|---|---|
| `notebooks/<name>.py` | A notebook. `site_costs.py` is a placeholder showing the pieces together |
| `notebooks/<name>.form.json` | A notebook's form: `{"schema": <JSON Schema>, "uischema": <JSON Forms UI schema>}` |
| `queries/<name>.sql` | A query. Every value is a named parameter (`@site`) |
| `samples/<name>.csv` | A query's sample result, read in offline mode (`.parquet` and `.json` work too) |
| `notebooks_lib/` | The helpers: `bigquery.Runner`, `forms.load_form`, `widget.SchemaFormWidget` |
| `widget/` | The widget's front end, built into `notebooks_lib/static/` (git-ignored) |

## Queries

```python
from notebooks_lib.bigquery import Runner

result = Runner().run("site_costs", site="tartu", start=date(2026, 3, 1), end=date(2026, 3, 31))
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

## Tests

`make test` runs the widget's typecheck and Vitest tests (`widget/*.test.tsx`), then pytest: the helpers
(`tests/test_bigquery.py`, `tests/test_forms.py`), `marimo check --strict` on every notebook, and a headless
run of each notebook in offline mode (`tests/test_notebooks.py`). Coverage goes to `coverage/` for
SonarQube Cloud. The repository's setup comes from pubkit (`pubkit.json`, `./pubkit sync --check`); see
`AGENTS.md`.
