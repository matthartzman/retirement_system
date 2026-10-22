"""client_holdings.csv opened with plain 'utf-8' instead of 'utf-8-sig' silently
dropped every holding when the file carried a UTF-8 BOM: the BOM attaches to
the first header name ('account' -> '﻿account'), so row.get('account')
always returns '', which trips the `if not acct: continue` guard for every
row. Reported live: real holdings visible and intact in the UI, but the
Asset Allocation sheet/charts (which read c['lots_by_account'] downstream of
parse_client()) showed zero invested. A broker CSV export is a realistic,
not contrived, source of a BOM-prefixed file -- this is exactly the shape of
input a user hits via "Preview & replace CSV". No prior test caught this:
synthetic_plans.py and the golden-master fixtures inject
c['lots_by_account'] directly, bypassing the CSV-parsing path entirely.

Holdings are no longer read from the CSV at parse time: parse_client reads the
``holdings_lots`` table of the ACTIVE plan file (plan.rpx), and the CSV is only
read when it is imported into that table. The BOM therefore has to be handled at
the import step, so this test imports a BOM-prefixed CSV into a plan file of its
own (a temporary workspace) and parses that plan. It used to rewrite the shared
session ``input/client_holdings.csv`` -- which parse_client never reads -- so it
asserted against whatever plan an earlier test had left active in the worker and
failed intermittently with no holdings.
"""
import pytest

from src import plan_registry
from src.active_plan import PLAN_DB_ENV
from src.data_io import parse_client
from tests.plan_fixture import make_plan, reload_flat_datasets


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    ws = make_plan(tmp_path)
    monkeypatch.setenv("RETIREMENT_SYSTEM_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.delenv(PLAN_DB_ENV, raising=False)
    plan_registry.invalidate()
    yield ws
    plan_registry.invalidate()


def _lots(ws):
    return parse_client(ws.data(), "").get("lots_by_account") or {}


def _cost_basis(lots_by_account):
    return sum(
        lot.cost_basis
        for symbols in lots_by_account.values()
        for lots in symbols.values()
        for lot in lots
    )


def test_holdings_load_when_client_holdings_csv_has_a_utf8_bom(workspace, tmp_path):
    holdings_path = workspace.input_dir / "client_holdings.csv"
    original = holdings_path.read_bytes().lstrip(b"\xef\xbb\xbf")
    expected = _lots(workspace)
    assert expected, "fixture sanity: the frozen plan must have holdings without a BOM"

    # utf-8-sig encode == plain utf-8 content with a leading BOM, matching
    # what Excel/many broker CSV exporters actually produce.
    holdings_path.write_bytes(b"\xef\xbb\xbf" + original)
    reload_flat_datasets(tmp_path)

    lots_by_account = _lots(workspace)
    assert lots_by_account, (
        "holdings were silently dropped when client_holdings.csv had a "
        "UTF-8 BOM -- the account/symbol columns should still parse"
    )
    assert lots_by_account.keys() == expected.keys()
    assert _cost_basis(lots_by_account) == pytest.approx(_cost_basis(expected))
    assert _cost_basis(lots_by_account) > 0
