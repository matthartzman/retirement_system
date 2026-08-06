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
"""
import shutil

from conftest import TEST_INPUT_DIR
from src.data_io import load_csv, parse_client


def test_holdings_load_when_client_holdings_csv_has_a_utf8_bom(tmp_path):
    holdings_path = TEST_INPUT_DIR / "client_holdings.csv"
    original = holdings_path.read_bytes()
    backup = tmp_path / "client_holdings.csv.orig"
    backup.write_bytes(original)
    try:
        # utf-8-sig encode == plain utf-8 content with a leading BOM, matching
        # what Excel/many broker CSV exporters actually produce.
        holdings_path.write_bytes(b"\xef\xbb\xbf" + original.lstrip(b"\xef\xbb\xbf"))
        c = parse_client(load_csv(TEST_INPUT_DIR / "client_data.csv"), "")
        lots_by_account = c.get("lots_by_account") or {}
        assert lots_by_account, (
            "holdings were silently dropped when client_holdings.csv had a "
            "UTF-8 BOM -- the account/symbol columns should still parse"
        )
        total_cost_basis = sum(
            lot.cost_basis
            for symbols in lots_by_account.values()
            for lots in symbols.values()
            for lot in lots
        )
        assert total_cost_basis > 0
    finally:
        shutil.copy(backup, holdings_path)
