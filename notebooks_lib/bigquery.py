"""Run the notebooks' `.sql` files on BigQuery.

Values reach a query only as named query parameters (`@site` in the SQL, `site=` in Python), never spliced
into its text. Each query is dry-run first, to report the bytes it would scan, and runs with
`maximum_bytes_billed` set, so BigQuery refuses one that would cost more than the cap.

With `SUSTENAUT_DATA=offline` nothing reaches BigQuery: a query's result is the sample with its name in
`samples/` (`samples/site_costs.csv` for `queries/site_costs.sql`). The parameters are still checked against the
SQL and turned into query parameters, so a notebook that runs offline passes the same values it would online.
"""

from __future__ import annotations

import datetime
import decimal
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from google.cloud import bigquery

ROOT = Path(__file__).resolve().parent.parent
QUERIES = ROOT / "queries"
SAMPLES = ROOT / "samples"

#: The environment variable that picks where data comes from: "offline" for the samples, anything else BigQuery.
DATA_MODE = "SUSTENAUT_DATA"

#: The most a query may scan, unless a Runner is given another cap: 1 GiB.
DEFAULT_MAX_BYTES = 1024**3


class QueryError(ValueError):
    """A query that cannot run as asked: a parameter missing, extra or of a type BigQuery has no name for."""


class BytesCapExceeded(QueryError):
    """The dry run says the query would scan more than the cap."""

    def __init__(self, name: str, estimate: int, cap: int):
        super().__init__(f"{name} would scan {estimate} bytes, more than the cap of {cap}")
        self.estimate = estimate
        self.cap = cap


# Comments and quoted text, which may hold an "@" that is not a parameter.
_NOT_CODE = re.compile(r"--[^\n]*|#[^\n]*|/\*.*?\*/|'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"|`[^`]*`", re.S)
_PARAMETER = re.compile(r"(?<![@\w])@([A-Za-z_]\w*)")


def parameter_names(sql: str) -> set[str]:
    """The named parameters (`@name`) a query uses; `@@` system variables are not parameters."""
    return set(_PARAMETER.findall(_NOT_CODE.sub(" ", sql)))


def _type_of(value: Any) -> str:
    # bool before int: a bool is an int in Python.
    if isinstance(value, bool):
        return "BOOL"
    if isinstance(value, int):
        return "INT64"
    if isinstance(value, float):
        return "FLOAT64"
    if isinstance(value, decimal.Decimal):
        return "NUMERIC"
    if isinstance(value, str):
        return "STRING"
    if isinstance(value, bytes):
        return "BYTES"
    # datetime before date: a datetime is a date in Python.
    if isinstance(value, datetime.datetime):
        return "TIMESTAMP" if value.tzinfo else "DATETIME"
    if isinstance(value, datetime.date):
        return "DATE"
    if isinstance(value, datetime.time):
        return "TIME"
    raise QueryError(f"no BigQuery type for {type(value).__name__} {value!r}")


def query_parameters(values: Mapping[str, Any]) -> list[bigquery.ScalarQueryParameter | bigquery.ArrayQueryParameter]:
    """BigQuery query parameters for `values`, typed from the Python values; a list or tuple is an ARRAY."""
    parameters: list[bigquery.ScalarQueryParameter | bigquery.ArrayQueryParameter] = []
    for name, value in sorted(values.items()):
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            if not value:
                raise QueryError(f"{name} is an empty list, whose element type BigQuery cannot tell")
            types = {_type_of(v) for v in value}
            if len(types) != 1:
                raise QueryError(f"{name} mixes types: {', '.join(sorted(types))}")
            parameters.append(bigquery.ArrayQueryParameter(name, types.pop(), list(value)))
        elif value is None:
            raise QueryError(f"{name} is None, whose type BigQuery cannot tell")
        else:
            parameters.append(bigquery.ScalarQueryParameter(name, _type_of(value), value))
    return parameters


@dataclass(frozen=True)
class Result:
    """A query's rows, with the bytes the dry run estimated and the bytes BigQuery billed (0 offline)."""

    frame: pd.DataFrame
    bytes_estimated: int
    bytes_billed: int
    offline: bool


class Runner:
    """Runs the `.sql` files in `queries` with named parameters, a dry run first and a byte cap.

    `client` is a `google.cloud.bigquery.Client`, made on first use from the environment's credentials when not
    given; offline, none is made.
    """

    def __init__(
        self,
        client: bigquery.Client | None = None,
        *,
        max_bytes_billed: int = DEFAULT_MAX_BYTES,
        queries: Path = QUERIES,
        samples: Path = SAMPLES,
        offline: bool | None = None,
    ):
        self._client = client
        self.max_bytes_billed = max_bytes_billed
        self.queries = queries
        self.samples = samples
        self.offline = os.environ.get(DATA_MODE) == "offline" if offline is None else offline

    @property
    def client(self) -> bigquery.Client:
        if self._client is None:
            self._client = bigquery.Client()
        return self._client

    def sql(self, name: str) -> str:
        """The text of `queries/<name>.sql`."""
        return (self.queries / f"{name}.sql").read_text()

    def _prepare(self, name: str, values: Mapping[str, Any]):
        sql = self.sql(name)
        wanted = parameter_names(sql)
        missing = wanted - values.keys()
        extra = values.keys() - wanted
        problems = []
        if missing:
            problems.append(f"no value for {', '.join(sorted(missing))}")
        if extra:
            problems.append(f"no @parameter for {', '.join(sorted(extra))}")
        if problems:
            raise QueryError(f"{name}: {'; '.join(problems)}")
        return sql, query_parameters(values)

    def dry_run(self, name: str, **values: Any) -> int:
        """The bytes `name` would scan with these values; 0 offline."""
        sql, parameters = self._prepare(name, values)
        if self.offline:
            return 0
        config = bigquery.QueryJobConfig(query_parameters=parameters, dry_run=True, use_query_cache=False)
        return int(self.client.query(sql, job_config=config).total_bytes_processed or 0)

    def run(self, name: str, **values: Any) -> Result:
        """Run `name` with these values as its parameters, refusing it when the dry run passes the cap."""
        sql, parameters = self._prepare(name, values)
        if self.offline:
            return Result(self._sample(name), bytes_estimated=0, bytes_billed=0, offline=True)
        estimate = self.dry_run(name, **values)
        if estimate > self.max_bytes_billed:
            raise BytesCapExceeded(name, estimate, self.max_bytes_billed)
        config = bigquery.QueryJobConfig(query_parameters=parameters, maximum_bytes_billed=self.max_bytes_billed)
        job = self.client.query(sql, job_config=config)
        frame = job.result().to_dataframe()
        return Result(frame, bytes_estimated=estimate, bytes_billed=int(job.total_bytes_billed or 0), offline=False)

    def _sample(self, name: str) -> pd.DataFrame:
        for suffix, read in ((".parquet", pd.read_parquet), (".csv", pd.read_csv), (".json", pd.read_json)):
            path = self.samples / f"{name}{suffix}"
            if path.exists():
                return read(path)
        raise FileNotFoundError(f"no sample for {name} in {self.samples} (.parquet, .csv or .json)")
