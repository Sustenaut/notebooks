import json

import pandas as pd
import pytest

from notebooks_lib import costs as C

SITES = ("a", "b")


def price(**row):
    base = {"id": "x", "item": "X", "kind": "fixed", "quantity": 1, "free": 0, "price_eur": 10.0, "per": "month"}
    return C.Price.from_row(base | row)


def usage(**metrics):
    """Usage for sites a and b: metric=(a, b)."""
    frame = pd.DataFrame(0.0, index=list(SITES), columns=list(C.METRICS))
    for metric, (a, b) in metrics.items():
        frame[metric] = [a, b]
    return frame


def model(prices, shares=(), use=None, load_now=0.0, headroom=0.8):
    return C.Model(prices, list(shares), use if use is not None else usage(), load_now=load_now, headroom=headroom, sites=SITES)


def test_a_fixed_price_is_quantity_times_price_and_a_yearly_one_a_twelfth():
    assert price(quantity=20, price_eur=0.5).monthly() == 10
    assert price(per="year", price_eur=12).monthly() == 1
    assert price(price_eur=None).monthly() is None


def test_a_usage_price_charges_beyond_the_allowance_with_its_plan_fee_once():
    p = price(kind="usage", free=3, price_eur=2, step_fee_eur=5)
    assert p.usage_cost(3) == 0
    assert p.usage_cost(4) == 5 + 2
    assert price(kind="usage", free=3, price_eur=None).usage_cost(1) == 0
    assert price(kind="usage", free=3, price_eur=None).usage_cost(4) is None


def test_empty_values_read_as_none_or_zero():
    p = C.Price.from_row({"id": "y", "price_eur": float("nan"), "quantity": None})
    assert (p.item, p.kind, p.price_eur, p.quantity, p.metric) == ("y", "fixed", None, 0.0, "")


def test_weights_split_by_the_share_table_and_evenly_without_one():
    assert C.weights([{"site": "a", "x": 3}, {"site": "b", "x": 1}], "x", SITES) == {"a": 0.75, "b": 0.25}
    assert C.weights([], "x", SITES) == {"a": 0.5, "b": 0.5}
    assert C.weights([{"site": "a", "x": 2}], "x", SITES) == {"a": 1.0, "b": 0.0}
    assert C.weights([{"site": "a", "x": 0}, {"site": "b", "x": 0}], "x", SITES) == {"a": 0.5, "b": 0.5}
    assert C.weights([{"site": "zz", "x": 9}], "x", SITES) == {"a": 0.5, "b": 0.5}


def test_fixed_costs_follow_the_shares_and_unknown_prices_are_listed_not_counted():
    prices = [price(id="srv", price_eur=9), price(id="vol", item="Volume", price_eur=None)]
    c = model(prices, [{"site": "a", "srv": 2}, {"site": "b", "srv": 1}]).costs({})
    assert c.per_site.loc["a", "fixed"] == pytest.approx(6)
    assert c.per_site.loc["b", "total"] == pytest.approx(3)
    assert c.unpriced == ["Volume"]
    assert pd.isna(c.items.set_index("id").loc["vol", "cost"])


def test_usage_costs_use_the_account_wide_allowance_and_follow_each_site_s_usage():
    prices = [price(id="st", kind="usage", metric="bq_storage_gib", free=10, price_eur=1)]
    c = model(prices, use=usage(bq_storage_gib=(9, 3))).costs({})
    assert c.per_site["usage"].tolist() == pytest.approx([1.5, 0.5])
    assert model(prices, use=usage(bq_storage_gib=(4, 3))).costs({}).per_site["usage"].sum() == 0
    unknown = [price(id="st", item="Storage", kind="usage", metric="bq_storage_gib", free=1, price_eur=None)]
    assert model(unknown, use=usage(bq_storage_gib=(4, 3))).costs({}).unpriced == ["Storage"]


def test_a_per_table_metric_is_checked_per_site_and_load_jobs_never_pass_one_per_cycle():
    jobs = [price(id="j", item="Jobs", kind="usage", metric="bq_load_jobs_day", free=1500, price_eur=0)]
    m = model(jobs, use=usage(bq_load_jobs_day=(100, 0)))
    assert m.costs({"a": 1000}).per_site["usage"].sum() == 0
    assert C.scale(m.usage, {"a": 1000}).loc["a", "bq_load_jobs_day"] == C.LOAD_JOBS_PER_DAY_MAX == 720
    unpriced = [price(id="j", item="Jobs", kind="usage", metric="bq_load_jobs_day", free=10, price_eur=None)]
    assert model(unpriced, use=usage(bq_load_jobs_day=(100, 0))).costs({}).unpriced == ["Jobs"]
    paid = [price(id="j", kind="usage", metric="bq_load_jobs_day", free=10, price_eur=1)]
    assert model(paid, use=usage(bq_load_jobs_day=(12, 0))).costs({}).per_site.loc["a", "usage"] == 2
    missing = [price(id="w", kind="usage", metric="not_a_metric", free=0, price_eur=1)]
    assert model(missing).costs({}).per_site["usage"].sum() == 0


def servers(next_price=20.0):
    return [
        price(id="s1", item="small", capacity=1, price_eur=10),
        price(id="s2", item="medium", kind="server", capacity=2, price_eur=next_price),
        price(id="s4", item="large", kind="server", capacity=4, price_eur=40),
    ]


def test_the_server_moves_to_the_next_type_past_the_headroom():
    m = model(servers(), load_now=0.5, headroom=0.8)
    assert (m.costs({}).server, m.costs({}).server_load) == ("small", 0.5)
    grown = m.costs({"a": 3, "b": 3})
    assert grown.server == "medium" and grown.server_load == pytest.approx(1.5)
    assert grown.per_site["fixed"].sum() == pytest.approx(20)
    assert m.costs({"a": 20, "b": 20}).server == "large"
    assert C.pick_server([], 1, 0.8) is None
    assert model(servers(next_price=None), load_now=0.5).costs({"a": 3, "b": 3}).unpriced == ["medium"]


def test_without_a_server_row_there_is_no_server_cost():
    c = model([price(id="gh", price_eur=4)]).costs({})
    assert (c.server, c.server_load, c.per_site["total"].sum()) == ("", 0.0, 4)
    assert model([price(id="gh")]).state({}, "a") == set()


def test_growth_marks_each_step_where_it_happens():
    prices = servers() + [
        price(id="st", item="Storage", kind="usage", metric="bq_storage_gib", free=10, price_eur=None),
        price(id="j", item="Jobs", kind="usage", metric="bq_load_jobs_day", free=1500, price_eur=0),
    ]
    m = model(prices, use=usage(bq_storage_gib=(1, 0), bq_load_jobs_day=(72, 0)), load_now=0.4, headroom=0.8)
    curve, steps = C.growth(m, grid=(1, 3, 4, 10, 12, 30))
    assert set(curve["site"]) == set(SITES) and len(curve) == 12
    found = {(s.site, s.multiplier, s.what) for s in steps}
    assert ("a", 4, "server: medium") in found and ("a", 10, "server: large") in found
    assert ("a", 10, "Jobs: one per cycle, 720 a day of the 1,500 limit") in found
    assert ("a", 12, "Storage: free allowance used up (its price is unknown)") in found
    assert not any(s.site == "b" and s.what.startswith(("Jobs", "Storage")) for s in steps)
    assert curve.query("site == 'a' and multiplier == 3")["cost"].item() == pytest.approx(5)


def test_usage_now_turns_the_query_results_into_monthly_usage_per_site():
    calls = pd.DataFrame({"project": ["visit_ee", "visit_ee"], "calls": [100, 200]})
    status = pd.DataFrame(
        {
            "project": ["visit_ee"],
            "sender_cycles": [1440],
            "ingest_cycles": [1440],
            "busy_sender_cycles": [30],
            "calls_load_jobs": [15],
        }
    )
    storage = pd.DataFrame(
        {"project": ["visit_ee", "visit_ee"], "table_name": ["calls", "status"], "row_count": [10, 0], "size_bytes": [2000, 0]}
    )
    not_measured = [{"site": "estimate", "workers_requests_day": 100_000, "r2_writes_day": 1000}, {"site": "elsewhere"}]
    u = C.usage_now(calls, status, storage, not_measured, days=2, notebook_runs_month=1024)
    assert u.loc["visit_ee", "calls_day"] == 150
    assert u.loc["visit_ee", "storage_files_day"] == 15
    assert u.loc["visit_ee", "bq_load_jobs_day"] == 15
    # 150 calls a day at 200 bytes, plus 1,440 status rows a day at the 150 bytes of an empty table, for 395 days.
    assert u.loc["visit_ee", "bq_storage_gib"] == pytest.approx((150 * 200 + 1440 * 150) * 395 / 2**30)
    assert u.loc["notebooks", "bq_query_tib"] == pytest.approx(1024 * 80 * 2**20 / 2**40)
    assert u.loc["estimate", "workers_mreq"] == pytest.approx(3.0)
    assert u.loc["estimate", "r2_class_a_m"] == pytest.approx(0.03)
    assert u.loc["integrations"].sum() == 0


def test_usage_now_with_nothing_read_is_zero_and_skips_sites_it_does_not_cost():
    empty = pd.DataFrame()
    u = C.usage_now(empty, empty, empty, days=0, sites=("visit_ee",))
    assert u.loc["visit_ee"].sum() == 0
    assert list(u.index) == ["visit_ee"]


def test_the_defaults_come_from_the_data_files(tmp_path):
    for name, body in {
        "prices": {"rows": [{"id": "p"}]},
        "shares": {"rows": [{"site": "a"}]},
        "not_measured": {"notebook_runs_month": 7, "rows": []},
    }.items():
        (tmp_path / f"{name}.json").write_text(json.dumps(body))
    d = C.model_defaults(tmp_path)
    assert d["prices"] == [{"id": "p"}] and d["shares"] == [{"site": "a"}] and d["notebook_runs_month"] == 7
    assert d["multipliers"] == dict.fromkeys(C.SITES, 1) and (d["load_now"], d["headroom"]) == (30, 80)


def test_every_price_row_has_a_source_date_and_a_reason_when_unpriced():
    rows = C.model_defaults()["prices"]
    assert len({r["id"] for r in rows}) == len(rows)
    for r in rows:
        assert r["source"].startswith("https://") and r["as_of"] and r["note"]
        assert r["kind"] in {"fixed", "usage", "server"}
        if r["kind"] == "usage":
            assert r["metric"] in C.METRICS
        if r["price_eur"] is None:
            assert "not priced" in r["note"].lower()


def test_the_billing_summary_nets_credits_per_service():
    frame = pd.DataFrame(
        {
            "service": ["BigQuery", "BigQuery", "Cloud Storage"],
            "sku": ["Analysis", "Storage", "Standard"],
            "project": ["sustenaut"] * 3,
            "currency": ["EUR"] * 3,
            "cost": [2.0, 1.0, 0.5],
            "credits": [-2.0, 0.0, 0.0],
        }
    )
    summary = C.billing_summary(frame)
    assert summary.to_dict("records") == [
        {"service": "BigQuery", "currency": "EUR", "cost": 3.0, "credits": -2.0, "net": 1.0},
        {"service": "Cloud Storage", "currency": "EUR", "cost": 0.5, "credits": 0.0, "net": 0.5},
    ]
    assert C.billing_summary(frame.iloc[0:0]).empty
