"""Live Snapshot Group By: the page's JS grouping (live_groups.js) must total every group exactly as the
server's formulas do (live_snapshot._summarize, which also totals the liquid book). The same lots go through
both and each level is compared, in several orders."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from financial_trends_reporter import live_snapshot as ls
from tests.test_live_snapshot_compute_unit import LOTS, _compute

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "financial_trends_reporter" / "frontend" / "live_groups.js"
NODE = shutil.which("node")

CELLS = ("start", "new_money", "current", "share", "day", "day_pct", "market_gain", "return_pct", "share_of_gain", "annualized_pct")
KEYS = {
    "class": lambda p: p["asset_class"] or "Other",
    "subclass": lambda p: p["subclass"] or p["asset_class"] or "Other",
    "symbol": lambda p: p["symbol"],
    "account": lambda p: p["account"],
}

# More lots than the base fixture: a second ITOT lot in another account, a reinvested one, and an old one.
EXTRA = [
    {"account": "Member_1_Trust", "symbol": "ITOT", "purchase_date": "2026-10-01", "shares": "10", "purchase_price": "125"},
    {"account": "Member_1_IRA", "symbol": "ITOT", "purchase_date": "2026-04-15", "shares": "2.5", "purchase_price": "128", "lot_type": "reinvested"},
    {"account": "Member_1_IRA", "symbol": "IXUS", "purchase_date": "2024-01-10", "shares": "30", "purchase_price": "48"},
]

_RUN = """
const m = await import(process.argv[1]);
const input = JSON.parse(await new Promise((r) => { let s = ""; process.stdin.on("data", (c) => (s += c)); process.stdin.on("end", () => r(s)); }));
const strip = (n) => ({ name: n.name, inline: n.inline ?? null, skipped: n.skipped ?? null, row: n.row, children: n.children.map(strip) });
const t = m.buildTree(input.positions, input.order, { days: input.days });
process.stdout.write(JSON.stringify({ nodes: t.nodes.map(strip), total: t.total }));
"""

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")


def _js(positions, order, days):
    done = subprocess.run([NODE, "--input-type=module", "-e", _RUN, MODULE.as_uri()], capture_output=True, text=True, timeout=60,
                          input=json.dumps({"positions": positions, "order": order, "days": days}))
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def _same(server_row, js_row, where):
    for k in CELLS:
        s, j = server_row[k], js_row[k]
        if s is None or j is None:
            assert s is None and j is None, (where, k, s, j)
        else:
            assert j == pytest.approx(s, abs=0.006 if k in ("start", "new_money", "current", "day", "market_gain") else 1e-9), (where, k, s, j)


def _newest_first(members):
    dated = sorted((m for m in members if m["purchase_date"]), key=lambda m: m["purchase_date"], reverse=True)
    return dated + [m for m in members if not m["purchase_date"]]


@pytest.fixture(scope="module")
def out():
    return _compute(lots=LOTS + EXTRA)


def _server_row(out, members, name="x"):
    positions = out["liquid"]["positions"]
    total_current = sum(p["current"] for p in positions)
    total_gain = sum(p["current"] - p["start"] - p["new_money"] for p in positions)
    return ls._summarize(name, members, total_current, total_gain, out["days"])


def _compare(out, js_nodes, members, order, where=""):
    """Every JS node against the server's formulas on the same lots, recursively down ``order``."""
    dim = order[0]
    if dim == "lot":
        lots = _newest_first(members)
        assert [n["name"] for n in js_nodes] == [m["purchase_date"] or "Undated" for m in lots], where
        for node, lot in zip(js_nodes, lots):
            _same(_server_row(out, [lot]), node["row"], f"{where}/lot {node['name']}")
        return
    groups = {}
    for m in members:
        groups.setdefault(KEYS[dim](m), []).append(m)
    assert {n["name"] for n in js_nodes} == set(groups), where
    for node in js_nodes:
        ms = groups[node["name"]]
        _same(_server_row(out, ms), node["row"], f"{where}/{node['name']}")
        rest = order[1:]
        for skipped in node.get("skipped") or []:   # a level that would only repeat this row's name
            assert rest[0] == skipped and {KEYS[skipped](m).lower() for m in ms} == {node["name"].lower()}, where
            rest = rest[1:]
        if node.get("inline") is not None:
            assert rest[0] == "lot" and len(ms) == 1 and ms[0]["symbol"].startswith("CASH")   # a single cash lot folds into its row
        else:
            _compare(out, node["children"], ms, rest, f"{where}/{node['name']}")


@pytest.mark.parametrize("order", [
    ["class", "symbol", "account", "lot"],
    ["class", "subclass", "symbol", "account", "lot"],
    ["subclass", "symbol", "account", "lot"],
    ["account", "symbol", "lot"],
    ["symbol", "account", "class", "lot"],
    ["lot"],
])
def test_every_level_matches_the_servers_formulas(out, order):
    js = _js(out["liquid"]["positions"], order, out["days"])
    _compare(out, js["nodes"], out["liquid"]["positions"], order)


def test_non_equity_holdings_keep_their_class_at_the_sub_class_level(out):
    js = _js(out["liquid"]["positions"], ["subclass", "lot"], out["days"])
    assert {n["name"] for n in js["nodes"]} == {"International Equity", "US Total Equity", "Small-Cap Value", "Cash"}


def test_the_total_row_matches_the_servers_total(out):
    liquid = out["liquid"]
    total = _js(liquid["positions"], ["subclass", "lot"], out["days"])["total"]
    _same({**liquid, "share": 1, "share_of_gain": 1}, total, "total")


def test_the_annualize_threshold_is_the_servers():
    done = subprocess.run([NODE, "--input-type=module", "-e", "const m = await import(process.argv[1]); process.stdout.write(String(m.ANNUALIZE_MIN_DAYS));",
                           MODULE.as_uri()], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    assert int(done.stdout) == ls.ANNUALIZE_MIN_DAYS
