"""Each notebook passes `marimo check` and runs headless, offline, from start to end."""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest
from pytest_bdd import scenarios, then

scenarios("notebooks.feature")

ROOT = Path(__file__).resolve().parents[2]
NOTEBOOKS = sorted((ROOT / "notebooks").glob("*.py"))
OFFLINE = {**os.environ, "SUSTENAUT_DATA": "offline"}


@then("there are notebooks")
def there_are_notebooks():
    assert NOTEBOOKS


@then("marimo check passes")
def marimo_check_passes():
    done = subprocess.run(
        [sys.executable, "-m", "marimo", "check", "--strict", *map(str, NOTEBOOKS)],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert done.returncode == 0, done.stdout + done.stderr


@then("each notebook runs headless offline")
def each_notebook_runs_headless_offline():
    """Every case of the parametrized test this was, in turn."""
    for notebook in NOTEBOOKS:
        notebook = notebook.values[0] if type(notebook).__name__ == "ParameterSet" else notebook
        _case_each_notebook_runs_headless_offline(notebook=notebook)


def _case_each_notebook_runs_headless_offline(notebook):
    done = subprocess.run([sys.executable, str(notebook)], capture_output=True, text=True, cwd=ROOT, env=OFFLINE)
    assert done.returncode == 0, done.stdout + done.stderr


@then("site costs shows every section offline")
def site_costs_shows_every_section_offline(monkeypatch):
    monkeypatch.setenv("SUSTENAUT_DATA", "offline")
    spec = importlib.util.spec_from_file_location("site_costs", ROOT / "notebooks" / "site_costs.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _, defs = module.app.run()
    # A cell that stops (mo.stop) defines nothing, so every section's names being there means each one ran.
    assert {"today", "curve", "scenario", "steps", "billing_available"} <= defs.keys()
    assert defs["billing_available"] is False
    assert defs["calls"].offline and defs["days"] == 30
    today = defs["today"]
    assert set(today.unpriced) == {"Volume sustenaut-data", "Domain sustenaut.eu"}
    assert today.per_site["total"].sum() == pytest.approx(8.99 + 0.50 + 4 / 1.1216 + 6 / 1.1216 + 4.00, abs=0.01)
    assert {s.what.split(":")[0] for s in defs["steps"]} >= {"server", "BigQuery batch load jobs"}
