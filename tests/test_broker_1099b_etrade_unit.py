"""E*Trade 1099-B text parser (plan step 5.1): normalized rows, header split, control totals, preview. Synthetic text only."""
from __future__ import annotations

import pytest

import broker_1099b_synthetic as syn
from src import broker_1099b
from src.broker_1099b import etrade, normalized

SYMBOLS = {"ABCD", "WXYZ", "QRST", "LMNO", "PQRS", "AB", "ABC"}


def parse(text=None, **kw):
    return etrade.parse(text if text is not None else syn.build_statement(), known_symbols=SYMBOLS, **kw)


def test_parses_every_lot_with_normalized_fields():
    st = parse()
    assert len(st.rows) == 7
    first = st.rows[0]
    assert set(normalized.ROW_FIELDS) <= set(first)
    assert first["symbol"] == "ABCD"
    assert first["description"] == "Alpha Beta Corp Class A"
    assert first["cusip"] == "111111111"
    assert first["date_acquired"] == "2025-03-04"
    assert first["date_sold"] == "2025-09-10"
    assert (first["proceeds"], first["basis"], first["gain"], first["wash_disallowed"]) == (1500.0, 1400.0, 100.0, 0.0)
    assert first["quantity"] == 10.0
    assert first["account"] == "XXXX-0042"
    assert first["broker"] == "etrade"


def test_term_and_covered_come_from_the_section_heading():
    st = parse()
    got = {(r["symbol"], r["term"], r["covered"]) for r in st.rows}
    assert got == {("ABCD", "short", True), ("WXYZ", "short", True), ("QRST", "short", False),
                   ("LMNO", "long", True), ("PQRS", "long", False)}


def test_parentheses_are_losses_and_wash_sale_is_read():
    st = parse()
    by = {(r["symbol"], r["quantity"]): r for r in st.rows}
    assert by[("ABCD", 5.5)]["gain"] == -119.75
    wx = by[("WXYZ", 8.0)]
    assert (wx["gain"], wx["wash_disallowed"]) == (-40.0, 60.0)
    assert by[("LMNO", 31.25)]["market_discount"] == 12.0


def test_two_digit_years_resolve_acquired_not_after_sold():
    st = parse()
    assert [r["date_acquired"] for r in st.rows if r["symbol"] == "PQRS"] == ["2020-02-14"]
    assert all(r["date_acquired"] <= r["date_sold"] for r in st.rows)


def test_repeated_page_headers_and_total_lines_are_skipped():
    st = parse(syn.build_statement(page_break_every=1))
    assert len(st.rows) == 7
    assert not st.errors


def test_account_override_wins_over_statement_text():
    assert {r["account"] for r in parse(account="Trust brokerage").rows} == {"Trust brokerage"}


# ---------------------------------------------------------------- symbol / description split
@pytest.mark.parametrize("rest, symbol, desc", [
    ("ABCDAlpha Beta Corp", "ABCD", "Alpha Beta Corp"),
    ("ABCD Alpha Beta Corp", "ABCD", "Alpha Beta Corp"),
    ("ABCAlpha Beta", "ABC", "Alpha Beta"),          # longest known symbol that ends on a word boundary
    ("ABAlpha Beta", "AB", "Alpha Beta"),
    ("ABCD", "ABCD", ""),
])
def test_split_symbol_uses_known_symbols(rest, symbol, desc):
    assert etrade.split_symbol(rest, SYMBOLS) == (symbol, desc, "master")


def test_split_symbol_rejects_a_match_that_cuts_a_word():
    # "AB" is known but "ABCDE" would leave "CDE..." glued on: not a boundary, so fall back to the heuristic.
    sym, desc, source = etrade.split_symbol("ABCDEVanguard Fund", SYMBOLS)
    assert (sym, desc, source) == ("ABCDE", "Vanguard Fund", "guessed")


def test_split_symbol_blank_symbol():
    assert etrade.split_symbol("", SYMBOLS) == (None, "", "blank")


def test_unknown_symbol_is_flagged_as_guessed_in_warnings():
    text = syn.build_statement(header_override="CUSIP: 999999999 Symbol: ZZZZZebra Industries")
    st = etrade.parse(text, known_symbols=SYMBOLS)
    assert st.rows and all(r["symbol"] == "ZZZZ" and r["description"] == "Zebra Industries" for r in st.rows)
    assert any("guessed" in w.lower() for w in st.warnings)


# ---------------------------------------------------------------- control totals
def test_control_totals_match_the_summary_on_a_clean_statement():
    st = parse()
    assert st.control["status"] == "ok"
    assert st.control["gaps"] == []
    assert len(st.control["buckets"]) == 4


def test_control_totals_report_the_gap_per_bucket_and_column():
    bad = syn.totals()
    key = ("long", True)
    bad[key] = (bad[key][0] + 25.50,) + bad[key][1:]
    st = parse(syn.build_statement(summary=bad))
    assert st.control["status"] == "mismatch"
    assert st.control["gaps"] == [{"term": "long", "covered": True, "column": "proceeds",
                                   "statement": bad[key][0], "detail": syn.totals()[key][0], "difference": 25.5}]


def test_a_missing_summary_is_unverified_not_ok():
    st = parse(syn.build_statement(include_summary=False))
    assert st.control["status"] == "missing"


def test_a_bucket_present_in_the_summary_but_without_detail_is_a_gap():
    sections = {k: v for k, v in syn.DEFAULT_SECTIONS.items() if k != ("short", False)}
    st = parse(syn.build_statement(sections, summary={("short", False): (250.0, 200.0, 0.0, 0.0, 50.0)}))
    assert st.control["status"] == "mismatch"
    assert {g["column"] for g in st.control["gaps"]} == {"proceeds", "basis", "gain"}


def test_row_whose_gain_does_not_foot_gets_a_warning():
    sections = {("short", True): [("111111111", "ABCD", "Alpha", [
        ("03/04/25", "09/10/25", 1500.00, 1400.00, 0.00, 0.00, 99.00, 0.00, 10.0)])]}
    st = parse(syn.build_statement(sections))
    assert any("gain" in w.lower() and "foot" in w.lower() for w in st.warnings)


# ---------------------------------------------------------------- malformed input
def test_unparseable_lot_line_is_an_error_with_line_number_not_a_silent_skip():
    text = syn.build_statement().replace("1,500.00 1,400.00", "1,500.00 oops", 1)
    st = parse(text)
    assert st.errors and "line" in st.errors[0]["error"].lower() or st.errors[0]["line"]
    assert len(st.rows) == 6


def test_lot_line_before_any_heading_is_an_error():
    st = parse("CUSIP: 111111111 Symbol: ABCDAlpha\n03/04/25 09/10/25 1.00 1.00 0.00 0.00 0.00 0.00 1.000\n")
    assert st.rows == [] and st.errors


def test_empty_text_has_no_rows_and_an_error():
    st = parse("")
    assert st.rows == [] and st.errors


# ---------------------------------------------------------------- preview + registry
def test_preview_applies_only_when_control_totals_tie():
    pv = broker_1099b.preview_statement("etrade", text=syn.build_statement(), known_symbols=SYMBOLS)
    assert pv["schema"] == "import_preview_v1" and pv["kind"] == "broker_1099b"
    assert pv["received"] == 7 and len(pv["will_write"]) == 7 and pv["can_apply"] is True
    assert pv["errors"] == [] and pv["control_totals"]["status"] == "ok"
    assert len(pv["parsed"]) == 7


def test_preview_refuses_and_shows_the_gap():
    bad = syn.totals()
    bad[("short", True)] = (1.0,) + bad[("short", True)][1:]
    pv = broker_1099b.preview_statement("etrade", text=syn.build_statement(summary=bad), known_symbols=SYMBOLS)
    assert pv["can_apply"] is False and pv["will_write"] == []
    assert pv["received"] == 7 and len(pv["parsed"]) == 7        # the lines stay visible for checking
    assert pv["control_totals"]["status"] == "mismatch" and pv["control_totals"]["gaps"]
    assert any("control" in e["error"].lower() for e in pv["errors"])


def test_preview_refuses_when_there_are_no_control_totals():
    pv = broker_1099b.preview_statement("etrade", text=syn.build_statement(include_summary=False), known_symbols=SYMBOLS)
    assert pv["can_apply"] is False and pv["will_write"] == []


def test_preview_refuses_a_file_with_unparseable_lines():
    text = syn.build_statement().replace("1,500.00 1,400.00", "1,500.00 oops", 1)
    pv = broker_1099b.preview_statement("etrade", text=text, known_symbols=SYMBOLS)
    assert pv["can_apply"] is False and pv["will_write"] == [] and pv["errors"]


def test_preview_never_touches_the_database(monkeypatch, tmp_path):
    from src import active_plan
    monkeypatch.setattr(active_plan, "workspace_store", lambda *a, **k: pytest.fail("preview must not open the store"))
    broker_1099b.preview_statement("etrade", text=syn.build_statement(), known_symbols=SYMBOLS)


def test_unknown_broker_is_a_clean_error():
    pv = broker_1099b.preview_statement("nosuch", text="x")
    assert pv["can_apply"] is False and pv["errors"] and pv["received"] == 0


def test_registry_lists_etrade_and_accepts_new_parsers():
    assert "etrade" in broker_1099b.available_brokers()
    calls = []

    def fake(text, *, known_symbols=None, account=None):
        calls.append(text)
        return normalized.ParsedStatement(broker="fake")

    broker_1099b.register("fake_broker", fake)
    try:
        assert "fake_broker" in broker_1099b.available_brokers()
        pv = broker_1099b.preview_statement("fake_broker", text="hello")
        assert calls == ["hello"] and pv["received"] == 0
    finally:
        broker_1099b.REGISTRY.pop("fake_broker", None)


def test_default_symbol_list_comes_from_the_security_master(monkeypatch):
    monkeypatch.setattr(broker_1099b, "_master_symbols", lambda: {"ABCD", "WXYZ", "QRST", "LMNO", "PQRS"})
    pv = broker_1099b.preview_statement("etrade", text=syn.build_statement())
    assert pv["can_apply"] is True
    assert not any("guessed" in w.lower() for w in pv["warnings"])
