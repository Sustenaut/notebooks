import datetime
import decimal
import json
from types import SimpleNamespace

import pandas as pd
import pytest
from google.cloud import bigquery
from pytest_bdd import given, parsers, scenarios, then, when

from notebooks_lib.bigquery import Runner, parameter_names, query_parameters

scenarios("bigquery.feature")

WHEN = datetime.datetime(2026, 3, 1, 12, tzinfo=datetime.UTC)
VALUES = {
    "a bool": True,
    "an int": 3,
    "a float": 1.5,
    "a decimal": decimal.Decimal("2.50"),
    "a text": "tartu",
    "bytes": b"\x00",
    "a zoned datetime": WHEN,
    "a local datetime": WHEN.replace(tzinfo=None),
    "a date": datetime.date(2026, 3, 1),
    "a time of day": datetime.time(8),
    "a list of texts": ["tartu", "parnu"],
    "nothing": None,
    "an empty list": [],
    "a mixed list": [1, "a"],
    "an object": object(),
}


class FakeClient:
    """A BigQuery client that records each job's SQL and config, and reports `scanned` bytes."""

    def __init__(self, scanned):
        self.scanned = scanned
        self.jobs = []

    def query(self, sql, job_config):
        self.jobs.append((sql, job_config))
        frame = pd.DataFrame({"n": [1]})
        return SimpleNamespace(
            total_bytes_processed=self.scanned,
            total_bytes_billed=None if job_config.dry_run else self.scanned,
            result=lambda: SimpleNamespace(to_dataframe=lambda: frame),
        )


def parameter(p):
    """A query parameter as JSON: its class, name, type, and an array's values."""
    if isinstance(p, bigquery.ArrayQueryParameter):
        return {"class": type(p).__name__, "name": p.name, "type": p.array_type, "values": p.values}
    return {"class": type(p).__name__, "name": p.name, "type": p.type_}


def query_result(result):
    return {
        "rows": result.frame.to_dict("records"),
        "bytes_estimated": result.bytes_estimated,
        "bytes_billed": result.bytes_billed,
        "offline": result.offline,
    }


def values_of(datatable):
    """The table's parameters: a value that reads as JSON is that JSON, "date D" the date D, else text."""
    values = {}
    for name, cell in datatable[1:]:
        if cell.startswith("date "):
            values[name] = datetime.date.fromisoformat(cell.removeprefix("date "))
            continue
        try:
            values[name] = json.loads(cell)
        except ValueError:
            values[name] = cell
    return values


def runner(ctx):
    return Runner(
        getattr(ctx, "bigquery", None),
        queries=ctx.directory / "queries",
        samples=ctx.directory / "samples",
        offline=getattr(ctx, "offline", None),
        **({"max_bytes_billed": ctx.cap} if hasattr(ctx, "cap") else {}),
    )


@given(parsers.parse("a BigQuery that scans {scanned:d} bytes"))
def a_bigquery(ctx, scanned):
    ctx.bigquery, ctx.offline = FakeClient(scanned), False


@given(parsers.parse("the byte cap is {cap:d}"))
def the_byte_cap(ctx, cap):
    ctx.cap = cap


@given("the samples are used, not BigQuery")
def samples_used(ctx):
    ctx.offline = True


@given("BigQuery may not be reached")
def bigquery_unreachable(monkeypatch):
    monkeypatch.setattr(bigquery, "Client", lambda *a, **k: pytest.fail("offline made a client"))


@given("BigQuery's clients are counted")
def clients_counted(ctx, monkeypatch):
    ctx.made = []
    monkeypatch.setattr(bigquery, "Client", lambda: ctx.made.append(1) or "client")


@given(parsers.parse('a sample "{file}" whose column "{column}" holds 1 and 2'))
def a_sample(ctx, file, column):
    (ctx.directory / "samples").mkdir(exist_ok=True)
    frame = pd.DataFrame({column: [1, 2]})
    getattr(frame, "to_json" if file.endswith(".json") else "to_parquet")(ctx.directory / "samples" / file)


@when("the parameters of this SQL are read:")
def parameters_of_sql(ctx, docstring):
    ctx.attempt(lambda: sorted(parameter_names(docstring)))


@when(parsers.parse("{value} becomes a query parameter"))
def becomes_a_parameter(ctx, value):
    ctx.attempt(lambda: [parameter(p) for p in query_parameters({"v": VALUES[value]})])


@when(parsers.parse('the query "{name}" runs with:'))
def query_runs(ctx, name, datatable):
    ctx.attempt(lambda: query_result(runner(ctx).run(name, **values_of(datatable))))


@when(parsers.parse('the query "{name}" is dry run with:'))
def query_dry_runs(ctx, name, datatable):
    ctx.attempt(lambda: runner(ctx).dry_run(name, **values_of(datatable)))


@when("a runner is made")
def a_runner_is_made(ctx):
    ctx.attempt(lambda: {"offline": Runner().offline, "clients made": len(ctx.made)})


@when("a runner's client is asked for twice")
def client_asked_twice(ctx):
    def twice():
        made = Runner()
        return {"clients": [made.client, made.client], "clients made": len(ctx.made)}

    ctx.attempt(twice)


@when(parsers.parse('the repository\'s query "{name}" runs offline with "{values}"'))
def repository_query_runs(ctx, name, values):
    def run():
        made = Runner(offline=True)
        found = sorted(parameter_names(made.sql(name)))
        return {"parameters": found, "empty": made.run(name, **json.loads(values)).frame.empty}

    ctx.attempt(run)


@when(parsers.parse('the parameters of the repository\'s query "{name}" are read'))
def repository_parameters(ctx, name):
    ctx.attempt(lambda: sorted(parameter_names(Runner(offline=True).sql(name))))


def job(sql, config):
    return {
        "sql": sql,
        "dry_run": config.dry_run,
        "use_query_cache": config.use_query_cache,
        "maximum_bytes_billed": config.maximum_bytes_billed,
        "parameters": {p.name: {"type": p.type_, "value": str(p.value)} for p in config.query_parameters},
    }


@then("BigQuery was asked these jobs:")
def bigquery_jobs(ctx, docstring):
    asked = [job(sql, config) for sql, config in ctx.bigquery.jobs]
    assert asked == json.loads(docstring), json.dumps(asked, indent=2)
