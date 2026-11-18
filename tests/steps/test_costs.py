import dataclasses
import json
import math

import pandas as pd
from pytest_bdd import given, parsers, scenarios, when

from notebooks_lib import costs as C

scenarios("costs.feature")

SITES = ("a", "b")
BASE = {"id": "x", "item": "X", "kind": "fixed", "quantity": 1, "free": 0, "price_eur": 10.0, "per": "month"}


def plain(value):
    """A number as JSON has it: NaN, pandas's unknown, is null."""
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def cell(text):
    try:
        return json.loads(text)
    except ValueError:
        return text


def frame(datatable):
    header, *rows = datatable
    return pd.DataFrame([[cell(c) for c in row] for row in rows], columns=header)


def usage_of(table):
    """Usage for the sites, by metric: each metric the scenario does not give is 0."""
    usage = pd.DataFrame(0.0, index=list(SITES), columns=list(C.METRICS))
    for metric, values in table.items():
        usage[metric] = values
    return usage


def model(ctx):
    prices = [C.Price.from_row(BASE | row) for row in getattr(ctx, "rows", [])]
    return C.Model(
        prices,
        getattr(ctx, "shares", []),
        usage_of(getattr(ctx, "usage", {})),
        load_now=getattr(ctx, "load_now", 0.0),
        headroom=getattr(ctx, "headroom", 0.8),
        sites=SITES,
    )


def costs_view(costs):
    per_site = costs.per_site
    return {
        "per_site": {site: {k: plain(v) for k, v in row.items()} for site, row in per_site.to_dict("index").items()},
        "totals": {column: plain(per_site[column].sum()) for column in per_site.columns},
        "items": {row["id"]: {"item": row["item"], "kind": row["kind"], "cost": plain(row["cost"])}
                  for row in costs.items.to_dict("records")},
        "server": costs.server,
        "server_load": costs.server_load,
        "unpriced": costs.unpriced,
    }


def usage_view(usage):
    return {
        "sites": list(usage.index),
        "usage": usage.to_dict("index"),
        "totals": usage.sum(axis=1).to_dict(),
    }


@given(parsers.parse('a price row with "{row}"'))
def a_price_row(ctx, row):
    ctx.rows = [json.loads(row)]


@given("the price rows:")
def price_rows(ctx, docstring):
    ctx.rows = [*getattr(ctx, "rows", []), *json.loads(docstring)]


@given(parsers.parse('the server types small, medium and large, medium priced at "{price}"'))
def server_types(ctx, price):
    ctx.rows = [
        {"id": "s1", "item": "small", "capacity": 1, "price_eur": 10},
        {"id": "s2", "item": "medium", "kind": "server", "capacity": 2, "price_eur": json.loads(price)},
        {"id": "s4", "item": "large", "kind": "server", "capacity": 4, "price_eur": 40},
        *getattr(ctx, "rows", []),
    ]


@given(parsers.parse("the server is at load {load:g} with {headroom:g} headroom"))
def server_load(ctx, load, headroom):
    ctx.load_now, ctx.headroom = load, headroom


@given(parsers.parse('the share table "{shares}"'))
def share_table(ctx, shares):
    ctx.shares = json.loads(shares)


@given("the sites use:")
def sites_use(ctx, datatable):
    header, *rows = datatable
    ctx.usage = {row[0]: [float(row[header.index(site)]) for site in SITES] for row in rows}


@given("the calls per day:")
def calls_per_day(ctx, datatable):
    ctx.calls = frame(datatable)


@given("the status per day:")
def status_per_day(ctx, datatable):
    ctx.status = frame(datatable)


@given("the table storage:")
def table_storage(ctx, datatable):
    ctx.storage = frame(datatable)


@given("nothing was read")
def nothing_read(ctx):
    ctx.calls = ctx.status = ctx.storage = pd.DataFrame()


@given(parsers.parse('what is not measured is "{rows}"'))
def not_measured(ctx, rows):
    ctx.not_measured = json.loads(rows)


@given(parsers.parse("the notebooks run {runs:d} times a month"))
def notebook_runs(ctx, runs):
    ctx.runs = runs


@given(parsers.parse('the only site is "{site}"'))
def only_site(ctx, site):
    ctx.sites = (site,)


@given("the billing rows:")
def billing_rows(ctx, datatable):
    ctx.billing = frame(datatable)


@when("its monthly cost is worked out")
def monthly_cost(ctx):
    ctx.attempt(lambda: C.Price.from_row(BASE | ctx.rows[0]).monthly())


@when(parsers.parse("its cost for a usage of {used:g} is worked out"))
def usage_cost(ctx, used):
    ctx.attempt(lambda: C.Price.from_row(BASE | ctx.rows[0]).usage_cost(used))


@when(parsers.parse('the price row "{row}" is read as it is'))
def row_read(ctx, row):
    ctx.attempt(lambda: dataclasses.asdict(C.Price.from_row(json.loads(row))))


@when(parsers.parse('the weights of "{item}" between the sites are worked out'))
def weights(ctx, item):
    ctx.attempt(lambda: C.weights(ctx.shares, item, SITES))


@when("the costs are worked out")
def costs_now(ctx):
    ctx.attempt(lambda: costs_view(model(ctx).costs({})))


@when(parsers.parse('the costs are worked out with the multipliers "{multipliers}"'))
def costs_at(ctx, multipliers):
    ctx.attempt(lambda: costs_view(model(ctx).costs(json.loads(multipliers))))


@when(parsers.parse('the usage is scaled by the multipliers "{multipliers}"'))
def usage_scaled(ctx, multipliers):
    ctx.attempt(lambda: C.scale(model(ctx).usage, json.loads(multipliers)).to_dict("index"))


@when(parsers.parse("a server is picked for a load of {load:g} with {headroom:g} headroom"))
def server_picked(ctx, load, headroom):
    ctx.attempt(lambda: C.pick_server([], load, headroom))


@when(parsers.parse('the state of site "{site}" is read'))
def state_read(ctx, site):
    ctx.attempt(lambda: sorted(model(ctx).state({}, site)))


@when(parsers.parse('the growth is drawn at the multipliers "{grid}"'))
def growth_drawn(ctx, grid):
    def draw():
        curve, steps = C.growth(model(ctx), grid=tuple(json.loads(grid)))
        found = {}
        for step in steps:
            found.setdefault(step.site, {}).setdefault(f"{step.multiplier:g}", []).append(step.what)
        return {
            "sites": sorted(set(curve["site"])),
            "points": len(curve),
            "cost": {site: {f"{m:g}": cost for m, cost in zip(rows["multiplier"], rows["cost"], strict=True)}
                     for site, rows in curve.groupby("site")},
            "steps": found,
        }

    ctx.attempt(draw)


@when(parsers.parse("the usage now is worked out over {days:d} days"))
def usage_now(ctx, days):
    ctx.attempt(lambda: usage_view(C.usage_now(
        ctx.calls, ctx.status, ctx.storage, getattr(ctx, "not_measured", ()), days=days,
        notebook_runs_month=getattr(ctx, "runs", 0), sites=getattr(ctx, "sites", C.SITES),
    )))


@when("the model's defaults are read from the scratch directory")
def defaults_from(ctx):
    ctx.attempt(lambda: C.model_defaults(ctx.directory))


@when("the repository's price list is read row by row")
def price_list(ctx):
    """Each rule a price row keeps, with the rows that break it."""

    def read():
        rows = C.model_defaults()["prices"]
        ids = [r["id"] for r in rows]
        return {
            "ids used twice": sorted({i for i in ids if ids.count(i) > 1}),
            "sources not on https": [r["id"] for r in rows if not r["source"].startswith("https://")],
            "without a date": [r["id"] for r in rows if not r["as_of"]],
            "without a note": [r["id"] for r in rows if not r["note"]],
            "of another kind": [r["id"] for r in rows if r["kind"] not in {"fixed", "usage", "server"}],
            "on an unknown metric": [r["id"] for r in rows if r["kind"] == "usage" and r["metric"] not in C.METRICS],
            "unpriced without saying so": [
                r["id"] for r in rows if r["price_eur"] is None and "not priced" not in r["note"].lower()
            ],
        }

    ctx.attempt(read)


@when("the billing is summed up")
def billing_summed(ctx):
    ctx.attempt(lambda: C.billing_summary(ctx.billing).to_dict("records"))
