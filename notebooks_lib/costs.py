"""The Site costs model: what each site costs a month, from the price list, the share table and usage.

Everything here is plain arithmetic on tables the notebook gives it, so the tests can hold it to exact answers:

- A **fixed** price row (the server, the volume, subscriptions) costs quantity × price a month (a yearly price
  is divided by 12). Its cost is split between the sites by the share table's weights for that row; a site
  with no weight for it gets an even share.
- A **usage** price row is billed on one usage metric summed over all sites, since free allowances are
  per account: nothing up to the allowance, then `price_eur` per unit beyond it, and `step_fee_eur` once (a
  plan that becomes necessary). Its cost is split by each site's part of that usage.
- The **server** grows with load: today's load (a fraction of the current type) scales with each site's
  multiplier, weighted by its share of the server. When it passes the headroom the next server type's price
  replaces the current one.
- A price that could not be read is `None`. Its cost is unknown, never zero: it is left out of the totals and
  listed, and the points where its allowance runs out are still marked.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

#: The sites the costs are split between: the call log's four projects and the k3s server's other apps.
SITES = ("auth", "integrations", "visit_ee", "opportunity_site", "business_plan", "pub", "estimate", "notebooks")

#: The call log's projects, each with its own calls_<project> dataset.
CALL_LOG_PROJECTS = ("integrations", "visit_ee", "opportunity_site", "business_plan")

#: The ingest pod loads each table once per two-minute cycle at most.
LOAD_JOBS_PER_DAY_MAX = 24 * 60 // 2
#: BigQuery's limit on load jobs per table per day.
LOAD_JOBS_PER_DAY_LIMIT = 1500
#: The call log keeps 395 days (shared-infra infra/call_log.tf).
RETENTION_DAYS = 395
#: What a call log row takes when a table is still empty and its size cannot be measured.
DEFAULT_ROW_BYTES = 150
#: BigQuery bills a query at least 10 MiB for each table it reads; the notebook's queries read eight.
NOTEBOOK_RUN_BYTES = 8 * 10 * 2**20
DAYS_PER_MONTH = 30

#: The usage metrics a price row can be billed on, with what each one is.
METRICS = {
    "bq_storage_gib": "BigQuery storage at the end of the retention, GiB",
    "bq_query_tib": "BigQuery bytes the notebooks' queries are billed, TiB a month",
    "bq_load_jobs_day": "Load jobs per call log table per day (each site has its own tables)",
    "workers_mreq": "Cloudflare Workers requests, millions a month",
    "pages_builds": "Cloudflare Pages builds a month",
    "r2_storage_gb": "R2 storage, GB",
    "r2_class_a_m": "R2 writes, millions a month",
    "r2_class_b_m": "R2 reads, millions a month",
}
#: A metric whose allowance is per table, so per site, rather than per account.
PER_SITE_METRICS = {"bq_load_jobs_day"}


def _number(value) -> float | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    return float(value)


@dataclass(frozen=True)
class Price:
    id: str
    item: str
    kind: str  # fixed, usage or server
    metric: str
    quantity: float
    free: float
    price_eur: float | None
    step_fee_eur: float
    per: str
    capacity: float | None = None

    @classmethod
    def from_row(cls, row: Mapping) -> Price:
        return cls(
            id=row["id"],
            item=row.get("item", row["id"]),
            kind=row.get("kind", "fixed"),
            metric=row.get("metric") or "",
            quantity=_number(row.get("quantity")) or 0.0,
            free=_number(row.get("free")) or 0.0,
            price_eur=_number(row.get("price_eur")),
            step_fee_eur=_number(row.get("step_fee_eur")) or 0.0,
            per=row.get("per", "month"),
            capacity=_number(row.get("capacity")),
        )

    def monthly(self) -> float | None:
        """A fixed row's cost a month; None when its price is unknown."""
        if self.price_eur is None:
            return None
        return self.quantity * self.price_eur / (12 if self.per == "year" else 1)

    def usage_cost(self, total: float) -> float | None:
        """A usage row's cost for this much usage; None when usage is past the allowance and the price is unknown."""
        over = max(0.0, total - self.free)
        if over == 0:
            return 0.0
        if self.price_eur is None:
            return None
        return self.step_fee_eur + over * self.price_eur


def prices_from_rows(rows: Iterable[Mapping]) -> list[Price]:
    return [Price.from_row(r) for r in rows]


def weights(shares: Iterable[Mapping], item: str, sites: Sequence[str]) -> dict[str, float]:
    """Each site's part of a fixed item, from the share table; even when the table gives it no weights."""
    given = {r["site"]: _number(r.get(item)) for r in shares if r.get("site") in sites}
    raw = {s: given.get(s) for s in sites}
    if all(v is None for v in raw.values()):
        raw = {s: 1.0 for s in sites}
    raw = {s: max(0.0, v or 0.0) for s, v in raw.items()}
    total = sum(raw.values())
    if total == 0:
        return {s: 1 / len(sites) for s in sites}
    return {s: v / total for s, v in raw.items()}


def usage_now(
    calls_per_day: pd.DataFrame,
    status_per_day: pd.DataFrame,
    table_storage: pd.DataFrame,
    not_measured: Iterable[Mapping] = (),
    *,
    days: int,
    notebook_runs_month: float = 0,
    sites: Sequence[str] = SITES,
) -> pd.DataFrame:
    """Each site's usage a month (a day, for load jobs), by metric, from the query results over `days` days.

    The call log's storage grows by its rows per day (calls, plus every status cycle) times the bytes a row
    takes, kept for the retention. The notebooks' queries are billed by the run. What the call log does not
    measure (Workers requests, Pages builds, R2) comes from the not-measured table.
    """
    days = max(1, days)
    usage = pd.DataFrame(0.0, index=list(sites), columns=list(METRICS))
    usage["calls_day"] = 0.0
    usage["storage_files_day"] = 0.0

    calls = calls_per_day.groupby("project")["calls"].sum() if len(calls_per_day) else pd.Series(dtype=float)
    status = status_per_day.groupby("project").sum(numeric_only=True) if len(status_per_day) else pd.DataFrame()
    jobs = (
        status_per_day.groupby("project")["calls_load_jobs"].mean()
        if len(status_per_day) and "calls_load_jobs" in status_per_day
        else pd.Series(dtype=float)
    )
    row_bytes = _row_bytes(table_storage)
    for project in CALL_LOG_PROJECTS:
        if project not in usage.index:
            continue
        calls_day = float(calls.get(project, 0.0)) / days
        status_rows_day = 0.0
        if project in status.index:
            row = status.loc[project]
            status_rows_day = float(row.get("sender_cycles", 0) + row.get("ingest_cycles", 0)) / days
            usage.loc[project, "storage_files_day"] = float(row.get("busy_sender_cycles", 0)) / days
        usage.loc[project, "calls_day"] = calls_day
        stored = (calls_day * row_bytes.get((project, "calls"), DEFAULT_ROW_BYTES)) + (
            status_rows_day * row_bytes.get((project, "status"), DEFAULT_ROW_BYTES)
        )
        usage.loc[project, "bq_storage_gib"] = stored * RETENTION_DAYS / 2**30
        usage.loc[project, "bq_load_jobs_day"] = _number(jobs.get(project)) or 0.0
    if "notebooks" in usage.index:
        usage.loc["notebooks", "bq_query_tib"] = notebook_runs_month * NOTEBOOK_RUN_BYTES / 2**40
    for row in not_measured:
        site = row.get("site")
        if site not in usage.index:
            continue
        usage.loc[site, "workers_mreq"] = (_number(row.get("workers_requests_day")) or 0) * DAYS_PER_MONTH / 1e6
        usage.loc[site, "pages_builds"] = _number(row.get("pages_builds_month")) or 0
        usage.loc[site, "r2_storage_gb"] = _number(row.get("r2_storage_gb")) or 0
        usage.loc[site, "r2_class_a_m"] = (_number(row.get("r2_writes_day")) or 0) * DAYS_PER_MONTH / 1e6
        usage.loc[site, "r2_class_b_m"] = (_number(row.get("r2_reads_day")) or 0) * DAYS_PER_MONTH / 1e6
    return usage


def _row_bytes(table_storage: pd.DataFrame) -> dict[tuple[str, str], float]:
    sizes = {}
    for row in table_storage.to_dict("records") if len(table_storage) else []:
        if row.get("row_count"):
            sizes[(row["project"], row["table_name"])] = row["size_bytes"] / row["row_count"]
    return sizes


def scale(usage: pd.DataFrame, multipliers: Mapping[str, float]) -> pd.DataFrame:
    """Usage with each site's multiplier applied. Load jobs grow too, but never past one per cycle."""
    factors = pd.Series({s: float(multipliers.get(s, 1)) for s in usage.index})
    scaled = usage.mul(factors, axis=0)
    scaled["bq_load_jobs_day"] = scaled["bq_load_jobs_day"].clip(upper=LOAD_JOBS_PER_DAY_MAX)
    return scaled


@dataclass
class Costs:
    """One scenario's monthly cost per site, and what could not be priced."""

    per_site: pd.DataFrame  # index site; columns fixed, usage, total
    items: pd.DataFrame  # one row per price row: monthly cost (NaN when unknown)
    server: str
    server_load: float
    unpriced: list[str] = field(default_factory=list)


def server_load(load_now: float, server_weights: Mapping[str, float], multipliers: Mapping[str, float]) -> float:
    """The current server type's load at these multipliers, where 1 is full."""
    return load_now * sum(w * float(multipliers.get(s, 1)) for s, w in server_weights.items())


def pick_server(prices: Sequence[Price], load: float, headroom: float) -> Price | None:
    """The smallest server type that keeps `load` (in units of the current type) under `headroom` of itself."""
    servers = sorted((p for p in prices if p.capacity), key=lambda p: p.capacity or 0)
    for p in servers:
        if load <= headroom * (p.capacity or 0):
            return p
    return servers[-1] if servers else None


class Model:
    """The price list, the share table and today's usage, ready to be costed at any multipliers."""

    def __init__(self, prices: Sequence[Price], shares: Sequence[Mapping], usage: pd.DataFrame, *, load_now: float, headroom: float, sites: Sequence[str] = SITES):
        self.prices = list(prices)
        self.sites = list(sites)
        self.usage = usage.reindex(self.sites).fillna(0.0)
        self._usage = {m: self.usage[m].to_dict() for m in self.usage.columns}
        self.load_now = load_now
        self.headroom = headroom
        self.current = next((p for p in self.prices if p.kind == "fixed" and p.capacity), None)
        self.weights = {p.id: weights(shares, p.id, self.sites) for p in self.prices if p.kind == "fixed"}

    def _scaled(self, metric: str, multipliers: Mapping[str, float]) -> dict[str, float]:
        values = self._usage.get(metric, {})
        scaled = {s: values.get(s, 0.0) * float(multipliers.get(s, 1)) for s in self.sites}
        if metric == "bq_load_jobs_day":
            scaled = {s: min(v, LOAD_JOBS_PER_DAY_MAX) for s, v in scaled.items()}
        return scaled

    def costs(self, multipliers: Mapping[str, float]) -> Costs:
        """The monthly cost of each site at these multipliers."""
        fixed, used, items, unpriced, load, server_name = self._compute(multipliers)
        per_site = pd.DataFrame({"fixed": pd.Series(fixed), "usage": pd.Series(used)})
        per_site["total"] = per_site["fixed"] + per_site["usage"]
        return Costs(per_site, pd.DataFrame(items), server_name, load, unpriced)

    def total(self, multipliers: Mapping[str, float], site: str) -> float:
        fixed, used, *_ = self._compute(multipliers)
        return fixed[site] + used[site]

    def _compute(self, multipliers: Mapping[str, float]):
        fixed = dict.fromkeys(self.sites, 0.0)
        used = dict.fromkeys(self.sites, 0.0)
        items, unpriced = [], []
        load, server_name = 0.0, ""
        if self.current:
            server_weights = self.weights[self.current.id]
            load = server_load(self.load_now, server_weights, multipliers)
            picked = pick_server(self.prices, load, self.headroom) or self.current
            server_name = picked.item
            if picked.price_eur is None:
                unpriced.append(picked.item)
            else:
                for s, w in server_weights.items():
                    fixed[s] += picked.price_eur * w
            items.append({"id": picked.id, "item": picked.item, "kind": "server", "cost": picked.price_eur})
        for p in self.prices:
            if p.kind == "server" or p is self.current or (p.kind == "fixed" and p.capacity):
                continue
            if p.kind == "fixed":
                cost = p.monthly()
                if cost is None:
                    unpriced.append(p.item)
                else:
                    for s, w in self.weights[p.id].items():
                        fixed[s] += cost * w
            else:
                column = self._scaled(p.metric, multipliers)
                if p.metric in PER_SITE_METRICS:
                    parts = {s: p.usage_cost(v) for s, v in column.items()}
                    cost = None if any(c is None for c in parts.values()) else sum(parts.values())
                    if cost is None:
                        unpriced.append(p.item)
                    else:
                        for s, c in parts.items():
                            used[s] += c
                else:
                    total = sum(column.values())
                    cost = p.usage_cost(total)
                    if cost is None:
                        unpriced.append(p.item)
                    elif cost and total:
                        for s, v in column.items():
                            used[s] += v / total * cost
            items.append({"id": p.id, "item": p.item, "kind": p.kind, "cost": cost})
        return fixed, used, items, unpriced, load, server_name

    def state(self, multipliers: Mapping[str, float], site: str) -> set[str]:
        """What has happened for `site` at these multipliers: allowances used up, load jobs at their most, the
        server type."""
        load = server_load(self.load_now, self.weights[self.current.id], multipliers) if self.current else 0.0
        picked = pick_server(self.prices, load, self.headroom) if self.current else None
        state = {f"server: {picked.item}"} if picked else set()
        for p in self.prices:
            if p.kind != "usage" or not self._usage.get(p.metric, {}).get(site):
                continue
            column = self._scaled(p.metric, multipliers)
            unknown = " (its price is unknown)" if p.price_eur is None else ""
            if p.metric in PER_SITE_METRICS:
                if column[site] >= LOAD_JOBS_PER_DAY_MAX:
                    state.add(f"{p.item}: one per cycle, {LOAD_JOBS_PER_DAY_MAX} a day of the {LOAD_JOBS_PER_DAY_LIMIT:,} limit")
            elif sum(column.values()) > p.free:
                state.add(f"{p.item}: free allowance used up{unknown}")
        return state


#: The multipliers a growth curve is drawn at: 1x to 1000x, evenly on a log scale.
GRID = tuple(round(10 ** (i / 40), 4) for i in range(0, 121))


@dataclass(frozen=True)
class Step:
    site: str
    multiplier: float
    what: str


def growth(model: Model, grid: Sequence[float] = GRID) -> tuple[pd.DataFrame, list[Step]]:
    """Each site's monthly cost as its own usage grows (the others staying at 1x), and where a step happens.

    A step is where a free allowance runs out, a call log table reaches one load job per cycle (720 of
    BigQuery's 1,500 a day), or the server needs its next type.
    """
    curve, steps = [], []
    for site in model.sites:
        before = None
        for m in grid:
            multipliers = {s: (m if s == site else 1.0) for s in model.sites}
            curve.append({"site": site, "multiplier": m, "cost": model.total(multipliers, site)})
            now = model.state(multipliers, site)
            if before is not None:
                steps += [Step(site, m, what) for what in sorted(now - before)]
            before = now
    return pd.DataFrame(curve), steps

DATA = Path(__file__).resolve().parent.parent / "data"


def model_defaults(data: Path = DATA) -> dict:
    """The cost model form's starting values: the price list, the share table and the not-measured usage."""
    read = lambda name: json.loads((data / f"{name}.json").read_text())  # noqa: E731
    not_measured = read("not_measured")
    return {
        "multipliers": {s: 1 for s in SITES},
        "load_now": 30,
        "headroom": 80,
        "notebook_runs_month": not_measured["notebook_runs_month"],
        "prices": read("prices")["rows"],
        "shares": read("shares")["rows"],
        "not_measured": not_measured["rows"],
    }


def billing_summary(frame: pd.DataFrame) -> pd.DataFrame:
    """Google's bill per service: cost, credits (negative) and what is left, per currency."""
    if frame.empty:
        return pd.DataFrame(columns=["service", "currency", "cost", "credits", "net"])
    summary = frame.groupby(["service", "currency"], as_index=False)[["cost", "credits"]].sum()
    summary["net"] = summary["cost"] + summary["credits"]
    return summary.sort_values("net", ascending=False, ignore_index=True)
