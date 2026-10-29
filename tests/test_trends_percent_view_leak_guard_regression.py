"""Percent view leak guard: every /api/ route is classified, and real payloads scale leak-free.

The payload tests build bodies with the real builders (the same fixtures the per-route tests use),
then run strip_detail + scale_payload at a large K and assert find_money_leaks finds nothing.
A key wrongly on NON_MONEY_KEYS, or a dollar string the scaler misses, fails here.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from financial_trends_reporter import balance_store as bs
from financial_trends_reporter import live_snapshot as ls
from financial_trends_reporter import spending_window as sw
from financial_trends_reporter.access_routes import OWNER_ONLY_PREFIXES, PASS_THROUGH_FOR_PERCENT, WITHHELD_FOR_PERCENT
from financial_trends_reporter.main import create_app
from financial_trends_reporter.percent_view import find_money_leaks, scale_payload, strip_detail
from financial_trends_reporter.trends_log import append_or_replace_entry
from financial_trends_reporter.trends_metrics import compute_snapshot
from tests import test_balance_series_unit as bsu
from tests import test_live_snapshot_build_unit as lsb
from tests import test_spending_window_unit as swu
from tests import test_trends_monthly_flows_unit as mfu

K = 2_000_000.0

# Routes whose body is scaled (every /api/ route that returns money and is not pass-through).
KNOWN_SCALED = {
    "/api/history", "/api/accounts", "/api/balances", "/api/flows", "/api/spending",
    "/api/live-snapshot", "/api/app-accounts", "/api/account", "/api/run-now", "/api/exit", "/api/realized",
}


def _workspace(tmp_path: Path) -> Path:
    base = tmp_path / "workspace"
    (base / "input").mkdir(parents=True)
    (base / "local_state").mkdir(parents=True)
    return base


def test_every_api_route_is_classified(tmp_path):
    app = create_app(_workspace(tmp_path), log_path=tmp_path / "log.jsonl")
    unclassified = []
    for rule in app.url_map.iter_rules():
        path = rule.rule
        if not path.startswith("/api/"):
            continue
        owner_only = any(path == p or path.startswith(p + "/") for p in OWNER_ONLY_PREFIXES)
        if not (owner_only or path in PASS_THROUGH_FOR_PERCENT or path in WITHHELD_FOR_PERCENT or path in KNOWN_SCALED):
            unclassified.append(path)
    assert unclassified == [], f"classify these routes for the percent view: {unclassified}"


@pytest.fixture
def client(tmp_path):
    """A local client over a workspace with a Monarch store, a real log entry and YTD data."""
    base = _workspace(tmp_path)
    mfu._seed(base)
    data = tmp_path / "data"
    data.mkdir()
    bsu._seed(tmp_path).replace(data / bs.DB_FILENAME)
    log = data / "log.jsonl"
    append_or_replace_entry(log, compute_snapshot(base, today=mfu.TODAY))
    return create_app(base, log_path=log).test_client()


def _get(client, url):
    resp = client.get(url)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return json.loads(resp.get_data(as_text=True))


def _spending(tmp_path):
    (tmp_path / 'spending').mkdir()
    base = swu._workspace(tmp_path / 'spending', swu.ROWS)
    return sw.spending_window_payload(base, date(2025, 11, 1), date(2026, 3, 31))


def _live_snapshot(tmp_path):
    data_dir = tmp_path / "ls_data"
    data_dir.mkdir()
    (data_dir / "baseline_prices_2026.json").write_text(
        json.dumps({"baseline_date": "2025-12-31", "prices": lsb.BASELINE["prices"]}))
    return lsb._build(data_dir)[0]


def _realized(tmp_path):
    from financial_trends_reporter import realized_view as rv
    from tests import test_realized_view_unit as rvu

    return rv.build(sales=rvu.SALES, candidates=rvu.CANDIDATES, lots=rvu.LOTS, today=rvu.TODAY, start="2026-01-01", include_unconfirmed=True)


BUILDERS = {
    "/api/realized": lambda client, tmp: _realized(tmp),
    "/api/balances": lambda client, tmp: _get(client, "/api/balances"),
    "/api/flows": lambda client, tmp: _get(client, "/api/flows"),
    "/api/history": lambda client, tmp: _get(client, "/api/history"),
    "/api/accounts": lambda client, tmp: _get(client, "/api/accounts"),
    "/api/spending": lambda client, tmp: _spending(tmp),
    "/api/live-snapshot": lambda client, tmp: _live_snapshot(tmp),
}


@pytest.mark.parametrize("route", sorted(BUILDERS))
def test_realistic_payloads_have_no_leaks(route, client, tmp_path):
    payload = BUILDERS[route](client, tmp_path)
    assert payload, f"{route} fixture produced an empty payload, the guard would prove nothing"
    before = find_money_leaks(payload)
    assert before or route in {"/api/accounts"}, f"{route} payload has no money to scale; fixture too thin"
    assert find_money_leaks(scale_payload(strip_detail(route, payload), K)) == []


# Numbers that are public or are counts of something with a public price. Left in a %-only payload they let a
# viewer recover the hidden scale: shares x a public ticker price, or a public index level / its scaled value.
PUBLIC_QUANTITY_KEYS = {"shares", "quantity", "purchase_price", "price"}


def _keys(node, found=None):
    found = set() if found is None else found
    if isinstance(node, dict):
        for k, v in node.items():
            found.add(k)
            _keys(v, found)
    elif isinstance(node, list):
        for v in node:
            _keys(v, found)
    return found


@pytest.mark.parametrize("route", sorted(BUILDERS))
def test_no_public_quantity_or_price_survives_in_a_percent_payload(route, client, tmp_path):
    out = scale_payload(strip_detail(route, BUILDERS[route](client, tmp_path)), K)
    assert _keys(out) & PUBLIC_QUANTITY_KEYS == set()
