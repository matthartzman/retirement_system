"""Sales ledger 4.5: percent-view handling of the realized view, the sold-lot rows and the realized tax line.

Rules (plan 10): dollar fields are scaled; a percent-only person gets group-level totals and returns, no per-sale
rows, share counts or prices; counts and years pass; an unlisted number is scaled, never passed through."""
from __future__ import annotations

from datetime import date

from financial_trends_reporter import percent_view as pv, realized_view as rv
from tests.test_realized_view_unit import CANDIDATES, LOTS, SALES, TODAY
from tests.test_realized_tax_line_unit import BASE, QUOTES, _lots, _sold
from tests.test_live_snapshot_compute_unit import MONARCH, SECURITY_MASTER, TAX
from financial_trends_reporter import live_snapshot as ls

K = 100000.0


def _realized(**kw):
    return rv.build(sales=SALES, candidates=CANDIDATES, lots=LOTS, today=TODAY, start="2026-01-01", **kw)


def _transform(payload, route):
    return pv.scale_payload(pv.strip_detail(route, payload), K)


def _walk(node, key=None):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _walk(v, k)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v, key)
    else:
        yield key, node


def test_realized_payload_has_no_leaks_and_no_per_sale_detail():
    out = _transform(_realized(include_unconfirmed=True), "/api/realized")
    assert pv.find_money_leaks(out) == []
    keys = {k for k, _ in _walk(out)}
    assert not keys & {"lots", "shares", "sale_id", "purchase_date", "sale_date"}, keys & {"lots", "shares", "sale_id", "purchase_date", "sale_date"}
    assert out["groups"] and out["estimate"]["groups"]


def test_dollars_are_scaled_and_counts_years_and_dates_are_not():
    raw = _realized(include_unconfirmed=True)
    out = _transform(raw, "/api/realized")
    assert out["summary"]["net"] == raw["summary"]["net"] / K and out["summary"]["proceeds"] == raw["summary"]["proceeds"] / K
    assert out["summary"]["count"] == raw["summary"]["count"] and out["unconfirmed"]["count"] == raw["unconfirmed"]["count"]
    assert out["unconfirmed"]["not_estimated"] == raw["unconfirmed"]["not_estimated"]
    assert out["years"] == raw["years"] and out["window"] == raw["window"]
    assert out["estimate"]["basis_missing"] == raw["estimate"]["basis_missing"]
    year = _transform(rv.build(sales=SALES, candidates=[], lots=[], today=TODAY, tax_year=2025), "/api/realized")
    assert year["window"]["tax_year"] == 2025
    # The ratio a percent-only person sees, net over basis, is unchanged by the scaling.
    g = out["groups"][0]
    raw_g = raw["groups"][0]
    assert g["net"] / g["basis"] == raw_g["net"] / raw_g["basis"]


def test_a_key_nobody_listed_is_scaled_not_passed_through():
    payload = _realized()
    payload["summary"]["mystery_total"] = 12345.0
    out = _transform(payload, "/api/realized")
    assert out["summary"]["mystery_total"] == 12345.0 / K
    assert pv.find_money_leaks({"mystery_total": 12345.0}) == ["mystery_total"]


def test_live_snapshot_with_sold_lots_and_the_realized_tax_line_has_no_leaks():
    body = ls.compute(lots=_lots(sold=True), quotes=QUOTES, baseline=BASE, security_master=SECURITY_MASTER, accounts=[], flows_daily={},
                      monarch=MONARCH, tax_rates=TAX, today=date(2026, 10, 27), sales=[_sold(13000.0)],
                      unconfirmed=[{"sale_date": "2026-10-01"}, {"sale_date": "2026-10-02"}])
    out = _transform(body, "/api/live-snapshot")
    assert pv.find_money_leaks(out) == []
    assert out["liquid"]["sold"] == {"count": 1} and out["liquid"]["unconfirmed_sales"] == {"count": 2}
    tax = out["tax"]["realized_tax"]
    assert tax["tax_year"] == 2026 and tax["total"] == body["tax"]["realized_tax"]["total"] / K
    assert tax["unknown_term"] == {"count": 0}
    assert out["tax"]["total_with_realized"] == body["tax"]["total_with_realized"] / K
    assert not {k for k, _ in _walk(out)} & {"shares", "purchase_price"}


def test_the_daily_log_block_has_no_leaks():
    from financial_trends_reporter import realized_log

    entry = {"as_of_date": "2026-10-27", "realized_ytd": realized_log.from_rows(SALES, CANDIDATES, TODAY)}
    assert pv.find_money_leaks(_transform([entry], "/api/history")) == []
