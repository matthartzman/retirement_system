from tests.broker_activity_fixtures import FILE_NAME, ROWS, history_csv
from src import broker_activity
from src.broker_activity import fidelity, group_orders


def _parse(rows=None):
    return broker_activity.parse_file("fidelity", history_csv(rows), account="Member_1_HSA", file_name=FILE_NAME)


def test_header_found_past_blank_lines_and_footer_ignored():
    p = _parse()
    assert p.errors == []
    assert len(p.rows) == len(ROWS)
    assert [r["run_date"] for r in p.rows] == sorted(r["run_date"] for r in p.rows)
    assert p.meta["account_hint"] == "fidelity:5678"


def test_kinds_and_sweep():
    kinds = {(r["kind"], r["symbol"], r["sweep"]) for r in _parse().rows}
    assert ("reinvest", "FDRXX", True) in kinds
    assert ("dividend", "FDRXX", True) in kinds
    assert ("reinvest", "TOTL", False) in kinds
    assert ("sell", "TOTL", False) in kinds
    assert ("buy", "TOTL", False) in kinds
    assert ("other", None, False) in kinds


def test_numbers_and_dates():
    sell = next(r for r in _parse().rows if r["kind"] == "sell" and r["quantity"] == -6)
    assert sell["fees"] == 0.03 and sell["amount"] == 629.97 and sell["price"] == 105
    assert sell["run_date"] == "2026-08-12" and sell["settle_date"] == "2026-08-13"
    div = next(r for r in _parse().rows if r["kind"] == "dividend" and r["symbol"] == "TOTL")
    assert div["settle_date"] is None and div["amount"] == 201


def test_classify_other_actions():
    assert fidelity.classify("LONG-TERM CAP GAIN EXAMPLE (X) (Cash)") == "cap_gain_long"
    assert fidelity.classify("SHORT-TERM CAP GAIN EXAMPLE (X) (Cash)") == "cap_gain_short"
    assert fidelity.classify("INTEREST EARNED FDIC INSURED DEPOSIT") == "interest"
    assert fidelity.classify("FOREIGN TAX PAID EXAMPLE (X)") == "foreign_tax"
    assert fidelity.classify("NORMAL DISTR PARTIAL /WEB (Cash)") == "other"


def test_row_keys_stable_and_identical_rows_kept():
    dup = ROWS + [ROWS[5]]
    a, b = _parse(dup), _parse(dup)
    keys = [r["row_key"] for r in a.rows]
    assert keys == [r["row_key"] for r in b.rows]
    assert len(set(keys)) == len(keys) == len(dup)


def test_row_keys_depend_on_account():
    a = broker_activity.parse_file("fidelity", history_csv(), account="A", file_name=FILE_NAME)
    b = broker_activity.parse_file("fidelity", history_csv(), account="B", file_name=FILE_NAME)
    assert {r["row_key"] for r in a.rows}.isdisjoint({r["row_key"] for r in b.rows})


def test_split_fills_combine_into_one_order():
    orders = group_orders(_parse().rows)
    aug = [o for o in orders if o["trade_date"] == "2026-08-12"]
    assert len(aug) == 1
    o = aug[0]
    assert o["shares"] == 6.5 and o["proceeds"] == 682.47 and o["fees"] == 0.03 and len(o["row_keys"]) == 2
    assert o["settle_date"] == "2026-08-13"
    assert [x["symbol"] for x in orders] == ["SHRT", "TOTL", "TOTL"]


def test_not_a_fidelity_file():
    p = broker_activity.parse_file("fidelity", "a,b\n1,2\n", account="A")
    assert p.rows == [] and p.errors


def test_trade_row_without_quantity_is_an_error_row_only():
    bad = '05/12/2026,YOU BOUGHT EXAMPLE (TOTL) (Cash),TOTL,EXAMPLE,Cash,100,"","","","","-1000",0,05/13/2026'
    p = _parse(ROWS + [bad])
    assert len(p.rows) == len(ROWS) and len(p.errors) == 1 and "quantity" in p.errors[0]["error"]


def test_unknown_broker():
    p = broker_activity.parse_file("nope", "", account="A")
    assert p.errors and "fidelity" in p.errors[0]["error"]
