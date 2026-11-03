import marimo

__generated_with = "0.25.2"
app = marimo.App(width="medium")


@app.cell
def _():
    # A placeholder for the Site costs notebook: one form and one query, to show the pieces working together.
    import datetime

    import marimo as mo

    from notebooks_lib.bigquery import Runner
    from notebooks_lib.forms import load_form

    return Runner, datetime, load_form, mo


@app.cell
def _(load_form, mo):
    form = load_form("site_costs")
    picker = mo.ui.anywidget(form.widget({"site": "tartu", "period": {"start": "2026-03-01", "end": "2026-03-31"}}))
    picker
    return form, picker


@app.cell
def _(Runner, datetime, form, mo, picker):
    values = picker.value["value"]
    problems = form.errors(values)
    mo.stop(bool(problems), mo.callout(mo.md("\n".join(f"- {p.message}" for p in problems)), kind="warn"))
    result = Runner().run(
        "site_costs",
        site=values["site"],
        start=datetime.date.fromisoformat(values["period"]["start"]),
        end=datetime.date.fromisoformat(values["period"]["end"]),
    )
    source = "sample data" if result.offline else f"{result.bytes_billed:,} bytes billed"
    mo.vstack([mo.md(f"**{result.frame['amount_eur'].sum():.2f} €** ({source})"), mo.ui.table(result.frame)])
    return (result,)


if __name__ == "__main__":
    app.run()
