"""Vanguard 1099-B text parser (plan step 5.1a): Various lines, CORRECTED flag, blank symbols, redemptions. Synthetic text only."""
from __future__ import annotations

import broker_1099b_vanguard_synthetic as syn
from src import broker_1099b
from src.broker_1099b import normalized, vanguard

SYMBOLS = {"ABCD", "LMNO"}


def parse(text=None, **kw):
    return vanguard.parse(text if text is not None else syn.build_statement(), known_symbols=SYMBOLS, **kw)


def by_key(st):
    return {(r["symbol"], r["date_sold"]): r for r in st.rows}


def test_reads_every_line_with_normalized_fields_and_ties_to_the_summary():
    st = parse()
    assert not st.errors
    assert len(st.rows) == 5
    assert set(normalized.ROW_FIELDS) <= set(st.rows[0])
    assert st.control["status"] == "ok"
    assert st.meta["account"] == "99990042" and {r["account"] for r in st.rows} == {"99990042"}


def test_various_line_is_an_aggregate_with_a_transaction_count_and_no_acquisition_date():
    r = by_key(parse())[("ABCD", "2025-09-10")]
    assert r["aggregated"] is True and r["transaction_count"] == 3
    assert r["date_acquired"] is None
    assert (r["quantity"], r["proceeds"], r["basis"], r["gain"]) == (15.5, 2280.5, 2300.25, -19.75)
    assert (r["term"], r["covered"], r["cusip"], r["description"]) == ("short", True, "111111111", "ALPHA BETA CORP CL A")


def test_lot_line_with_wash_sale_letter():
    r = by_key(parse())[("ABCD", "2025-10-15")]
    assert r["aggregated"] is False and r["date_acquired"] == "2025-07-01"
    assert (r["wash_disallowed"], r["market_discount"], r["gain"]) == (60.0, 0.0, -40.0)


def test_market_discount_letter_is_told_apart_from_wash_sale():
    r = by_key(parse())[("LMNO", "2025-06-03")]
    assert (r["market_discount"], r["wash_disallowed"], r["gain"]) == (12.0, 0.0, 22.0)
    assert r["term"] == "long"


def test_blank_symbol_is_kept_by_cusip_with_a_warning_and_redemption_kind():
    st = parse()
    r = by_key(st)[(None, "2025-12-03")]
    assert r["cusip"] == "555555555" and r["kind"] == "redemption" and r["quantity"] == 5000.0
    assert r["legend_code"] == "K"
    assert any("no symbol" in w for w in st.warnings)
    assert by_key(st)[("ABCD", "2025-10-15")]["kind"] == "sale"


def test_corrected_flag_and_statement_date_are_read():
    st = parse()
    assert st.meta["corrected"] is True and st.meta["statement_date"] == "2026-03-14"
    assert all(r["corrected"] is True and r["statement_date"] == "2026-03-14" for r in st.rows)
    assert parse(syn.build_statement(corrected=False)).meta["corrected"] is False


def test_repeated_headers_continuations_and_total_lines_are_skipped():
    st = parse()
    assert len(st.rows) == 5 and not st.errors
    assert {r["description"] for r in st.rows if r["symbol"] == "ABCD"} == {"ALPHA BETA CORP CL A"}


def test_account_override_wins():
    assert {r["account"] for r in parse(account="Brokerage").rows} == {"Brokerage"}


def test_control_totals_report_a_gap():
    bad = syn.totals()
    key = ("long", True)
    bad[key] = (bad[key][0] + 10.0,) + bad[key][1:]
    st = parse(syn.build_statement(summary=bad))
    assert st.control["status"] == "mismatch"
    assert st.control["gaps"][0]["column"] == "proceeds" and st.control["gaps"][0]["difference"] == 10.0


def test_missing_summary_is_unverified():
    assert parse(syn.build_statement(include_summary=False)).control["status"] == "missing"


def test_unreadable_line_is_an_error_with_a_line_number():
    st = parse(syn.build_statement().replace("2,280.50", "oops", 1))
    assert st.errors and st.errors[0]["line"] > 0 and len(st.rows) == 4


def test_empty_text_is_an_error():
    assert parse("").errors


def test_registered_and_previewed_through_the_shared_entry_point():
    assert "vanguard" in broker_1099b.available_brokers()
    pv = broker_1099b.preview_statement("vanguard", text=syn.build_statement(), known_symbols=SYMBOLS)
    assert pv["can_apply"] is True and pv["received"] == 5 and pv["meta"]["corrected"] is True
