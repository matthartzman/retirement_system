"""Live Snapshot Group By: the page's JS grouping (live_groups.js) must total every group exactly as the
server's own groups do (live_snapshot._summarize). The same lots go through both; each level is compared."""
from __future__ import annotations

import json
import re
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

# More lots than the base fixture: a second ITOT lot in another account, a reinvested one, and a later purchase.
EXTRA = [
    {"account": "Member_1_Trust", "symbol": "ITOT", "purchase_date": "2026-10-01", "shares": "10", "purchase_price": "125"},
    {"account": "Member_1_IRA", "symbol": "ITOT", "purchase_date": "2026-04-15", "shares": "2.5", "purchase_price": "128", "lot_type": "reinvested"},
    {"account": "Member_1_IRA", "symbol": "IXUS", "purchase_date": "2024-01-10", "shares": "30", "purchase_price": "48"},
]

_RUN = """
const m = await import(process.argv[1]);
const input = JSON.parse(await new Promise((r) => { let s = ""; process.stdin.on("data", (c) => (s += c)); process.stdin.on("end", () => r(s)); }));
const strip = (n) => ({ name: n.name, inline: n.inline ?? null, row: n.row, children: n.children.map(strip) });
const t = m.buildTree(input.positions, input.order, { days: input.days });
process.stdout.write(JSON.stringify({ nodes: t.nodes.map(strip), total: t.total }));
"""


def _tree(positions, order, days):
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


def _named(nodes):
    return {n["name"]: n for n in nodes}


pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")


@pytest.fixture(scope="module")
def out():
    return _compute(lots=LOTS + EXTRA)


def test_every_level_of_the_class_grouping_matches_the_server(out):
    liquid, days = out["liquid"], out["days"]
    js = _tree(liquid["positions"], ["class", "symbol", "account", "lot"], days)
    assert [n["name"] for n in js["nodes"]] == [r["name"] for r in liquid["by_class"]]
    for cls in liquid["by_class"]:
        jc = _named(js["nodes"])[cls["name"]]
        _same(cls, jc["row"], cls["name"])
        for tk in cls["tickers"]:
            jt = _named(jc["children"])[tk["symbol"]]
            _same(tk, jt["row"], tk["symbol"])
            for ac in tk["accounts"]:
                ja = _named(jt["children"])[ac["name"]]
                _same(ac, ja["row"], f"{tk['symbol']}/{ac['name']}")
                if ja["inline"] is not None:
                    continue                       # a single cash lot is folded into its account row
                assert len(ja["children"]) == len(ac["lots"])
                for sl, jl in zip(ac["lots"], ja["children"]):
                    assert jl["name"] == (sl["purchase_date"] or "Undated")     # newest first, undated last
                    _same(sl, jl["row"], f"{tk['symbol']}/{ac['name']}/{jl['name']}")


def test_the_subclass_grouping_matches_the_servers_equity_subclasses(out):
    liquid = out["liquid"]
    js = _named(_tree(liquid["positions"], ["subclass", "symbol", "lot"], out["days"])["nodes"])
    for sub in liquid["by_equity_subclass"]:
        _same(sub, js[sub["name"]]["row"], sub["name"])
        assert [t["name"] for t in js[sub["name"]]["children"]] == [t["symbol"] for t in sub["tickers"]]
    assert set(js) - {s["name"] for s in liquid["by_equity_subclass"]} == {"Cash"}     # non-equity holdings keep their class


def test_the_total_row_matches_the_servers_total(out):
    liquid = out["liquid"]
    total = _tree(liquid["positions"], ["subclass", "lot"], out["days"])["total"]
    _same({**liquid, "share": 1, "share_of_gain": 1}, total, "total")


def test_a_different_order_regroups_to_the_same_totals(out):
    liquid, days = out["liquid"], out["days"]
    by_account = _tree(liquid["positions"], ["account", "symbol", "lot"], days)
    assert sum(n["row"]["current"] for n in by_account["nodes"]) == pytest.approx(liquid["current"])
    assert sum(n["row"]["market_gain"] for n in by_account["nodes"]) == pytest.approx(liquid["market_gain"])


def test_the_annualize_threshold_is_the_servers():
    js = MODULE.read_text(encoding="utf-8")
    assert int(re.search(r"const ANNUALIZE_MIN_DAYS = (\d+)", js).group(1)) == ls.ANNUALIZE_MIN_DAYS
