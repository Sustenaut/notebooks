import marimo

__generated_with = "0.25.2"
app = marimo.App(width="medium", app_title="Site costs")


@app.cell
def _():
    import datetime

    import altair as alt
    import marimo as mo
    import pandas as pd
    from google.api_core import exceptions as google_errors

    from notebooks_lib import costs as model_lib
    from notebooks_lib.bigquery import QueryError, Runner
    from notebooks_lib.forms import load_form

    return QueryError, Runner, alt, datetime, google_errors, load_form, mo, model_lib, pd


@app.cell
def _(mo):
    mo.md("""
    # Site costs

    What each site costs a month today, and how that moves as its usage grows. Fixed costs (the server,
    subscriptions) are split by the share table; usage costs follow each site's own usage. The call log gives
    the usage; the price list gives the prices, each with its source and date. Edit either in the forms: a
    change lasts for this session, and a lasting one is a pull request to `data/`.
    """)
    return


@app.cell
def _(datetime, load_form, mo, model_lib):
    query_form = load_form("site_costs")
    _yesterday = datetime.date.today() - datetime.timedelta(days=1)
    query_picker = mo.ui.anywidget(
        query_form.widget(
            {
                "period": {
                    "start": (_yesterday - datetime.timedelta(days=29)).isoformat(),
                    "end": _yesterday.isoformat(),
                },
                "projects": list(model_lib.CALL_LOG_PROJECTS),
            }
        )
    )
    query_picker
    return query_form, query_picker


@app.cell
def _(QueryError, Runner, datetime, google_errors, mo, query_form, query_picker):
    _values = query_picker.value["value"]
    _problems = query_form.errors(_values)
    mo.stop(bool(_problems), mo.callout(mo.md("\n".join(f"- {p.message}" for p in _problems)), kind="warn"))
    runner = Runner()
    start = datetime.date.fromisoformat(_values["period"]["start"])
    end = datetime.date.fromisoformat(_values["period"]["end"])
    projects = list(_values["projects"])
    try:
        calls = runner.run("calls_per_day", start=start, end=end, projects=projects)
        status = runner.run("status_per_day", start=start, end=end, projects=projects)
        storage = runner.run("table_storage", tables=["calls", "status"])
    except (QueryError, google_errors.GoogleAPIError) as _error:
        mo.stop(True, mo.callout(mo.md(f"The call log could not be read: {_error}"), kind="danger"))
    _results = (calls, status, storage)
    _source = (
        "**Sample data** (`SUSTENAUT_DATA=offline`): made up, shaped like the call log."
        if calls.offline
        else f"Read from BigQuery: {sum(r.bytes_estimated for r in _results):,} bytes scanned, "
        f"{sum(r.bytes_billed for r in _results):,} billed (at least 10 MiB per table read)."
    )
    mo.md(_source)
    return calls, end, runner, status, storage


@app.cell
def _(load_form, mo, model_lib):
    model_form = load_form("site_costs.model")
    model_picker = mo.ui.anywidget(model_form.widget(model_lib.model_defaults()))
    model_picker
    return model_form, model_picker


@app.cell
def _(calls, mo, model_form, model_lib, model_picker, status, storage):
    inputs = model_picker.value["value"]
    _problems = model_form.errors(inputs)
    mo.stop(bool(_problems), mo.callout(mo.md("\n".join(f"- `{p.path}`: {p.message}" for p in _problems)), kind="warn"))
    days = int(status.frame["day"].nunique()) if len(status.frame) else 1
    usage = model_lib.usage_now(
        calls.frame,
        status.frame,
        storage.frame,
        inputs["not_measured"],
        days=days,
        notebook_runs_month=inputs.get("notebook_runs_month", 0),
    )
    prices = model_lib.prices_from_rows(inputs["prices"])
    model = model_lib.Model(
        prices, inputs["shares"], usage, load_now=inputs["load_now"] / 100, headroom=inputs["headroom"] / 100
    )
    return days, inputs, model, prices, usage


@app.cell
def _(mo, model):
    today = model.costs({})
    _table = today.per_site.round(2).rename(columns={"fixed": "fixed shared €", "usage": "usage €", "total": "total €"})
    _unpriced = (
        mo.callout(
            mo.md(
                "Not in the totals, because their price could not be read: "
                + ", ".join(today.unpriced)
                + ". Put a price in the Prices tab to include them."
            ),
            kind="warn",
        )
        if today.unpriced
        else mo.md("")
    )
    mo.vstack(
        [
            mo.md(
                f"## This month\n\nPer site, at today's usage, in € excluding VAT. Together: "
                f"**{today.per_site['total'].sum():.2f} €** a month, on a {today.server}."
            ),
            mo.ui.table(_table.reset_index(names="site"), selection=None, pagination=False),
            _unpriced,
        ]
    )
    return (today,)


@app.cell
def _(alt, calls, days, mo, model_lib, status):
    _calls = calls.frame
    _by_plugin = (
        _calls.groupby(["project", "plugin"], as_index=False)["calls"].sum().assign(per_day=lambda f: f["calls"] / days)
        if len(_calls)
        else _calls
    )
    _chart = (
        alt.Chart(_calls.groupby(["day", "project"], as_index=False)["calls"].sum())
        .mark_bar()
        .encode(x=alt.X("day:T", title="Day"), y=alt.Y("calls:Q", title="Calls"), color=alt.Color("project:N", title="Project"))
        .properties(height=220)
        if len(_calls)
        else mo.md("No calls in this period.")
    )
    _status = status.frame
    _writes = (
        _status.groupby("project", as_index=False)
        .agg(
            files_per_day=("busy_sender_cycles", "mean"),
            records_per_day=("records_sent", "mean"),
            calls_load_jobs=("calls_load_jobs", "max"),
            status_load_jobs=("status_load_jobs", "max"),
        )
        .round(1)
        if len(_status)
        else _status
    )
    mo.vstack(
        [
            mo.md(f"## Usage now\n\nCalls per day over {days} {'day' if days == 1 else 'days'} with data, per project and plugin."),
            _chart,
            mo.ui.table(_by_plugin.round(1), selection=None, pagination=False),
            mo.md(
                "**Storage writes.** Each two-minute cycle with records writes one file to the storage service "
                f"and makes one load job on the project's calls table. BigQuery allows "
                f"{model_lib.LOAD_JOBS_PER_DAY_LIMIT:,} a table a day; the cycle makes at most "
                f"{model_lib.LOAD_JOBS_PER_DAY_MAX}. The status table gets one job every cycle."
            ),
            mo.ui.table(_writes, selection=None, pagination=False),
        ]
    )
    return


@app.cell
def _(alt, inputs, mo, model, model_lib, pd, today):
    curve, steps = model_lib.growth(model)
    scenario = model.costs(inputs["multipliers"])
    _steps = pd.DataFrame([{"site": s.site, "multiplier": round(s.multiplier, 1), "step": s.what} for s in steps])
    _marks = _steps.merge(curve, on=["site", "multiplier"]) if len(_steps) else _steps
    _base = alt.Chart(curve).encode(
        x=alt.X("multiplier:Q", scale=alt.Scale(type="log"), title="Usage multiplier (the site alone)"),
        y=alt.Y("cost:Q", title="€ a month"),
        color=alt.Color("site:N", title="Site"),
    )
    _chart = _base.mark_line(interpolate="step-after")
    if len(_marks):
        _chart = _chart + alt.Chart(_marks).mark_point(size=70, filled=True).encode(
            x="multiplier:Q", y="cost:Q", color="site:N", tooltip=["site", "multiplier", "step"]
        )
    _table = pd.DataFrame(
        {
            "multiplier": pd.Series(inputs["multipliers"]),
            "today €": today.per_site["total"],
            "at the multiplier €": scenario.per_site["total"],
        }
    ).round(2)
    mo.vstack(
        [
            mo.md(
                "## As usage grows\n\nEach line is one site's monthly cost as its own usage grows, the others "
                "staying as they are. A dot is a step: a free allowance runs out, a call log table loads every "
                "cycle, or the server needs its next type (hover for which)."
            ),
            _chart.properties(height=320).interactive(),
            mo.md(
                f"**At the Growth tab's multipliers**: {scenario.per_site['total'].sum():.2f} € a month together, "
                f"on a {scenario.server} at {scenario.server_load:.0%} of a cx33."
            ),
            mo.ui.table(_table.reset_index(names="site"), selection=None, pagination=False),
            mo.ui.table(_steps, selection=None, pagination=False) if len(_steps) else mo.md("No steps up to 1000x."),
        ]
    )
    return curve, scenario, steps


@app.cell
def _(end, google_errors, mo, model_lib, runner):
    try:
        _bill = runner.run("billing", month=end.strftime("%Y%m"))
        _summary = model_lib.billing_summary(_bill.frame)
        _shown = (
            mo.ui.table(_summary.round(2), selection=None, pagination=False)
            if len(_summary)
            else mo.md(f"The export has no costs for {end:%B %Y} yet.")
        )
        billing_available = True
    except (google_errors.NotFound, FileNotFoundError):
        billing_available = False
        _shown = mo.callout(
            mo.md(
                "**No billing data yet.** Google's cost export goes to the `billing` dataset once it is turned on "
                "(see the design's steps); until then Google's costs are the BigQuery rows of the price list."
            ),
            kind="info",
        )
    mo.vstack([mo.md(f"## Google's bill for {end:%B %Y}"), _shown])
    return (billing_available,)


@app.cell
def _(inputs, mo):
    def _cell(value):
        return "" if value is None else str(value).replace("|", "\\|")

    _rows = "\n".join(
        f"| {_cell(r.get('provider'))} | {_cell(r.get('item'))} | {_cell(r.get('unit'))} | {_cell(r.get('free'))} "
        f"| {'unknown' if r.get('price_eur') is None else r['price_eur']} | "
        f"{_cell(r.get('price'))} {_cell(r.get('currency'))} | [source]({r.get('source')}) | {_cell(r.get('as_of'))} "
        f"| {_cell(r.get('note'))} |"
        for r in inputs["prices"]
    )
    mo.md(
        "## Price list\n\n| Provider | Item | Unit | Free | € per unit | As stated | Source | As of | Note |\n"
        "|---|---|---|---|---|---|---|---|---|\n" + _rows
    )
    return


if __name__ == "__main__":
    app.run()
