import datetime
import decimal
from types import SimpleNamespace

import pandas as pd
import pytest
from google.cloud import bigquery

from notebooks_lib.bigquery import (
    DEFAULT_MAX_BYTES,
    BytesCapExceeded,
    QueryError,
    Runner,
    parameter_names,
    query_parameters,
)


class FakeClient:
    """A BigQuery client that records each job's SQL and config, and reports `scanned` bytes."""

    def __init__(self, scanned=1000, rows=None):
        self.scanned = scanned
        self.rows = rows if rows is not None else pd.DataFrame({"n": [1]})
        self.jobs = []

    def query(self, sql, job_config):
        self.jobs.append((sql, job_config))
        frame = self.rows
        return SimpleNamespace(
            total_bytes_processed=self.scanned,
            total_bytes_billed=None if job_config.dry_run else self.scanned,
            result=lambda: SimpleNamespace(to_dataframe=lambda: frame),
        )


@pytest.fixture
def queries(tmp_path):
    (tmp_path / "costs.sql").write_text(
        "-- @not_a_parameter in a comment\n"
        "SELECT '@not_one_either', @@query_label FROM t WHERE site = @site AND day BETWEEN @start AND @end\n"
    )
    return tmp_path


def test_parameter_names_skip_comments_strings_and_system_variables():
    sql = "SELECT \"@a\", `@b`, @@x /* @c */ # @d\nFROM t WHERE x = @e AND y IN UNNEST(@f_2)"
    assert parameter_names(sql) == {"e", "f_2"}


def test_values_become_typed_query_parameters():
    when = datetime.datetime(2026, 3, 1, 12, tzinfo=datetime.UTC)
    params = {p.name: p for p in query_parameters({
        "flag": True,
        "n": 3,
        "x": 1.5,
        "money": decimal.Decimal("2.50"),
        "s": "tartu",
        "raw": b"\x00",
        "at": when,
        "local": when.replace(tzinfo=None),
        "day": datetime.date(2026, 3, 1),
        "time": datetime.time(8),
        "sites": ["tartu", "parnu"],
    })}
    assert {name: p.type_ for name, p in params.items() if isinstance(p, bigquery.ScalarQueryParameter)} == {
        "flag": "BOOL",
        "n": "INT64",
        "x": "FLOAT64",
        "money": "NUMERIC",
        "s": "STRING",
        "raw": "BYTES",
        "at": "TIMESTAMP",
        "local": "DATETIME",
        "day": "DATE",
        "time": "TIME",
    }
    assert isinstance(params["sites"], bigquery.ArrayQueryParameter)
    assert (params["sites"].array_type, params["sites"].values) == ("STRING", ["tartu", "parnu"])


@pytest.mark.parametrize("value", [None, [], [1, "a"], object()])
def test_values_without_a_bigquery_type_are_refused(value):
    with pytest.raises(QueryError):
        query_parameters({"v": value})


def test_values_go_as_query_parameters_never_into_the_sql(queries):
    client = FakeClient()
    sneaky = "x' OR '1'='1"
    result = Runner(client, queries=queries, offline=False).run(
        "costs", site=sneaky, start=datetime.date(2026, 3, 1), end=datetime.date(2026, 3, 31)
    )
    sqls = {sql for sql, _ in client.jobs}
    assert sqls == {(queries / "costs.sql").read_text()}
    assert sneaky not in sqls.pop()
    dry, real = (config for _, config in client.jobs)
    for config in (dry, real):
        values = {p.name: p.value for p in config.query_parameters}
        assert values == {"site": sneaky, "start": datetime.date(2026, 3, 1), "end": datetime.date(2026, 3, 31)}
    assert result.bytes_estimated == 1000 and result.bytes_billed == 1000 and not result.offline
    assert list(result.frame["n"]) == [1]


def test_a_dry_run_comes_first_and_the_byte_cap_is_set(queries):
    client = FakeClient()
    Runner(client, queries=queries, offline=False, max_bytes_billed=5000).run(
        "costs", site="a", start=datetime.date(2026, 1, 1), end=datetime.date(2026, 1, 2)
    )
    dry, real = (config for _, config in client.jobs)
    assert dry.dry_run is True and dry.use_query_cache is False
    assert real.dry_run is not True and real.maximum_bytes_billed == 5000


def test_the_cap_defaults_to_a_gibibyte(queries):
    client = FakeClient()
    Runner(client, queries=queries, offline=False).run("costs", site="a", start="x", end="y")
    assert client.jobs[-1][1].maximum_bytes_billed == DEFAULT_MAX_BYTES == 1024**3


def test_a_query_over_the_cap_never_runs(queries):
    client = FakeClient(scanned=10_000)
    runner = Runner(client, queries=queries, offline=False, max_bytes_billed=9_999)
    with pytest.raises(BytesCapExceeded) as raised:
        runner.run("costs", site="a", start="x", end="y")
    assert (raised.value.estimate, raised.value.cap) == (10_000, 9_999)
    assert [config.dry_run for _, config in client.jobs] == [True]


def test_dry_run_reports_bytes(queries):
    assert Runner(FakeClient(scanned=42), queries=queries, offline=False).dry_run("costs", site="a", start="x", end="y") == 42


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"site": "a", "start": "x"}, "no value for end"),
        ({"site": "a", "start": "x", "end": "y", "limit": 3}, "no @parameter for limit"),
    ],
)
def test_parameters_must_match_the_sql(queries, values, message):
    client = FakeClient()
    with pytest.raises(QueryError, match=message):
        Runner(client, queries=queries, offline=False).run("costs", **values)
    assert client.jobs == []


def test_offline_reads_the_sample_and_never_makes_a_client(queries, tmp_path, monkeypatch):
    samples = tmp_path / "samples"
    samples.mkdir()
    (samples / "costs.csv").write_text("day,amount\n2026-03-01,4.5\n")
    monkeypatch.setenv("SUSTENAUT_DATA", "offline")
    monkeypatch.setattr(bigquery, "Client", lambda *a, **k: pytest.fail("offline made a client"))
    runner = Runner(queries=queries, samples=samples)
    assert runner.offline
    assert runner.dry_run("costs", site="a", start="x", end="y") == 0
    result = runner.run("costs", site="a", start="x", end="y")
    assert result.offline and result.bytes_billed == 0
    assert result.frame.to_dict("records") == [{"day": "2026-03-01", "amount": 4.5}]
    with pytest.raises(QueryError):
        runner.run("costs", site="a")


@pytest.mark.parametrize("suffix", [".json", ".parquet"])
def test_offline_reads_json_and_parquet_samples(queries, tmp_path, suffix):
    samples = tmp_path / "samples"
    samples.mkdir()
    frame = pd.DataFrame({"n": [1, 2]})
    getattr(frame, "to_json" if suffix == ".json" else "to_parquet")(samples / f"costs{suffix}")
    result = Runner(queries=queries, samples=samples, offline=True).run("costs", site="a", start="x", end="y")
    assert list(result.frame["n"]) == [1, 2]


def test_offline_without_a_sample_says_so(queries, tmp_path):
    with pytest.raises(FileNotFoundError, match="no sample for costs"):
        Runner(queries=queries, samples=tmp_path, offline=True).run("costs", site="a", start="x", end="y")


def test_online_is_the_default_and_makes_its_client_on_first_use(monkeypatch):
    monkeypatch.delenv("SUSTENAUT_DATA", raising=False)
    made = []
    monkeypatch.setattr(bigquery, "Client", lambda: made.append(1) or "client")
    runner = Runner()
    assert not runner.offline and made == []
    assert runner.client == "client" and runner.client == "client" and made == [1]


def test_the_repository_query_has_a_sample():
    runner = Runner(offline=True)
    assert parameter_names(runner.sql("site_costs")) == {"site", "start", "end"}
    assert not runner.run("site_costs", site="tartu", start="2026-03-01", end="2026-03-31").frame.empty
