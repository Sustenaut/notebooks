"""Each notebook passes `marimo check` and runs headless, offline, from start to end."""

import importlib.util
from pathlib import Path

from pytest_bdd import parsers, scenarios, when

scenarios("notebooks.feature")

ROOT = Path(__file__).resolve().parents[2]


@when("the notebooks are listed")
def notebooks_listed(ctx):
    ctx.attempt(lambda: [path.stem for path in sorted((ROOT / "notebooks").glob("*.py"))])


@when(parsers.parse('the notebook "{name}" runs in-process'))
def notebook_runs(ctx, name):
    def run():
        spec = importlib.util.spec_from_file_location(name, ROOT / "notebooks" / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _, defs = module.app.run()
        return {
            **defs,
            "today total": defs["today"].per_site["total"].sum(),
            "step kinds": {step.what.split(":")[0]: True for step in defs["steps"]},
        }

    ctx.attempt(run)
