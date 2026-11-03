# The notebooks: `make lab` to edit them, `make apps` to use them. Both build what they need first.
NOTEBOOKS := notebooks
UV := uv run --locked

.PHONY: venv widget lab apps test check-js check-py offline

venv: ## the Python environment, from uv.lock
	uv sync --locked

node_modules: package-lock.json
	npm ci --ignore-scripts --no-audit --no-fund
	touch node_modules

widget: node_modules ## SchemaFormWidget's front end, into notebooks_lib/static/
	npm run build

lab: venv widget ## edit the notebooks in marimo
	$(UV) marimo edit $(NOTEBOOKS)

apps: venv widget ## the notebooks as apps, code hidden
	$(UV) marimo run $(NOTEBOOKS)

offline: venv widget ## the apps on the sample data, without BigQuery
	SUSTENAUT_DATA=offline $(UV) marimo run $(NOTEBOOKS)

check-js: node_modules
	npm test

check-py:
	$(UV) pytest -q --cov --cov-report=xml:coverage/coverage.xml tests

test: check-js check-py ## everything CI runs: typecheck, widget and Python tests, marimo check, notebooks run offline
