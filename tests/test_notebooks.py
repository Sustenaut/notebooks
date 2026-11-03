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


def test_site_costs_queries_the_form_s_values(monkeypatch):
    monkeypatch.setenv("SUSTENAUT_DATA", "offline")
    spec = importlib.util.spec_from_file_location("site_costs", ROOT / "notebooks" / "site_costs.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _, defs = module.app.run()
    assert defs["form"].errors(defs["picker"].value["value"]) == []
    assert defs["result"].offline
    assert defs["result"].frame["amount_eur"].sum() == pytest.approx(149.85)
