"""Each notebook passes `marimo check` and runs headless, offline, from start to end."""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
NOTEBOOKS = sorted((ROOT / "notebooks").glob("*.py"))
OFFLINE = {**os.environ, "SUSTENAUT_DATA": "offline"}


def test_there_are_notebooks():
    assert NOTEBOOKS


def test_marimo_check_passes():
    done = subprocess.run(
        [sys.executable, "-m", "marimo", "check", "--strict", *map(str, NOTEBOOKS)],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert done.returncode == 0, done.stdout + done.stderr


@pytest.mark.parametrize("notebook", NOTEBOOKS, ids=lambda p: p.stem)
def test_each_notebook_runs_headless_offline(notebook):
    done = subprocess.run([sys.executable, str(notebook)], capture_output=True, text=True, cwd=ROOT, env=OFFLINE)
    assert done.returncode == 0, done.stdout + done.stderr


def test_site_costs_shows_every_section_offline(monkeypatch):
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
