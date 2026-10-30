"""E*Trade and Vanguard activity parsers (synthetic files), broker detection and the multi-account import flow."""
import pytest

from src import active_plan, broker_activity, broker_import
from src.sales_ledger import ValidationError
from tests.broker_activity_fixtures import (ETRADE_FILE_NAME, FILE_NAME, VANGUARD_FILE_NAME, VANGUARD_ROWS, etrade_csv,
                                            history_csv, vanguard_csv)


def _etrade(rows=None, **kw):
    return broker_activity.parse_file("etrade", etrade_csv(rows, **kw), account="Member_1_IRA", file_name=ETRADE_FILE_NAME)


def _vanguard(rows=None):
    return broker_activity.parse_file("vanguard", vanguard_csv(rows), account="X", file_name=VANGUARD_FILE_NAME)


# ------------------------------------------------------------------------------------------------ E*Trade
def test_etrade_hint_comes_from_line_three_and_rows_read_cleanly():
    p = _etrade()
    assert p.meta["account_hint"] == "etrade:9876" and not p.errors and len(p.rows) == 9
    assert [r["run_date"] for r in p.rows] == sorted(r["run_date"] for r in p.rows)


def test_etrade_kinds_and_sweep():
    kinds = {(r["action"], r["kind"], r["sweep"]) for r in _etrade().rows}
    assert ("Sold", "sell", False) in kinds and ("Bought", "buy", False) in kinds
    assert ("Dividend", "dividend", False) in kinds
    assert ("Interest Income", "interest", True) in kinds  # Bank Deposit Program interest is income on a sweep
    for other in ("Redemption", "Contribution", "Service Fee"):
        assert (other, "other", False) in kinds


def test_etrade_sell_quantity_negative_amount_net_of_commission():
    sells = [r for r in _etrade().rows if r["kind"] == "sell"]
    assert [r["quantity"] for r in sells] == [-1.5, -2]
    assert sells[0]["amount"] == 164.9 and sells[0]["commission"] == 0.1
    order = broker_activity.group_orders(sells)
    assert len(order) == 1 and order[0]["shares"] == 3.5 and order[0]["proceeds"] == 384.9 and order[0]["fees"] == 0.1


def test_etrade_bond_price_is_rescaled_to_per_unit():
    bond = next(r for r in _etrade().rows if r["symbol"] == "912797AA1")
    assert bond["quantity"] == 5000 and bond["price"] == pytest.approx(0.985)


def test_etrade_missing_account_line_warns_and_bad_rows_are_errors():
    p = _etrade(account_line="")
    assert "account_hint" not in p.meta and any("account" in w for w in p.warnings)
    bad = _etrade(["06/10/2026,06/10/2026,06/11/2026,Bought,X,TOTL,--,-10,100.0,-1000.0,0.0,--,--"])
    assert bad.errors and "negative quantity" in bad.errors[0]["error"]
    assert broker_activity.parse_file("etrade", "a,b\n1,2\n", account="A").errors


# ------------------------------------------------------------------------------------------------ Vanguard
def test_vanguard_rows_carry_their_own_account_hint():
    p = _vanguard()
    assert not p.errors and len(p.rows) == len(VANGUARD_ROWS)
    assert broker_activity.row_hints(p.rows) == ["vanguard:1111", "vanguard:2222"] or \
        sorted(broker_activity.row_hints(p.rows)) == ["vanguard:1111", "vanguard:2222"]
    assert all(r["account_hint"] in ("vanguard:1111", "vanguard:2222") for r in p.rows)
    assert "11111111" not in repr(p.rows)


def test_vanguard_kinds_signs_and_sweeps():
    rows = _vanguard().rows
    sell = next(r for r in rows if r["kind"] == "sell" and not r["sweep"] and r["symbol"] == "EXMK")
    assert sell["quantity"] == -5 and sell["amount"] == 999.5 and sell["fees"] == 0.5
    sweep = [r for r in rows if r["sweep"]]
    assert {(r["kind"], r["symbol"]) for r in sweep} == {("buy", "VMFXX"), ("dividend", "VMFXX"), ("reinvest", "VMFXX")}
    other = {r["action"] for r in rows if r["kind"] == "other"}
    assert other == {"Conversion (outgoing)", "Withdrawal"}
    assert next(r for r in rows if r["kind"] == "interest")["symbol"] is None


def test_vanguard_bad_rows_and_header():
    bad = _vanguard(["11111111,9/15/2026,9/16/2026,Sell,Sell,X,EXMK,5,200,1000,0,1000,0,CASH"])
    assert bad.errors and "positive quantity" in bad.errors[0]["error"]
    assert broker_activity.parse_file("vanguard", history_csv(), account="A").errors


def test_detect_broker():
    assert broker_activity.detect_broker(history_csv(), FILE_NAME) == "fidelity"
    assert broker_activity.detect_broker(etrade_csv(), ETRADE_FILE_NAME) == "etrade"
    assert broker_activity.detect_broker(vanguard_csv(), VANGUARD_FILE_NAME) == "vanguard"
    assert broker_activity.detect_broker("a,b\n1,2\n") is None


# ------------------------------------------------------------------------------------------------ import flow
HOLDINGS = [
    {"account": "Member_1_IRA", "symbol": "TOTL", "purchase_date": "2025-01-02", "shares": "20", "purchase_price": "90", "lot_type": "buy", "note": ""},
    {"account": "Member_2_IRA", "symbol": "EXMK", "purchase_date": "2025-03-01", "shares": "10", "purchase_price": "150", "lot_type": "buy", "note": ""},
    {"account": "Member_2_Roth", "symbol": "EXSB", "purchase_date": "2025-03-01", "shares": "5", "purchase_price": "70", "lot_type": "buy", "note": ""},
]
MAP = {"vanguard:1111": "Member_2_IRA", "vanguard:2222": "Member_2_Roth"}


@pytest.fixture
def ws(tmp_path):
    base = tmp_path / "ws"
    (base / "input").mkdir(parents=True)
    with active_plan.workspace_store(base, write=True) as store:
        store.dataset("holdings").replace_all(HOLDINGS)
    return base / "input"


def test_etrade_single_account_flow_with_auto_detected_broker(ws):
    rep = broker_import.preview(ws, text=etrade_csv(), file_name=ETRADE_FILE_NAME)
    assert rep["needs_account"] and rep["broker"] == "etrade" and rep["hints"][0]["hint"] == "etrade:9876"
    rep = broker_import.preview(ws, text=etrade_csv(), file_name=ETRADE_FILE_NAME, account="Member_1_IRA")
    assert rep["counts"]["orders"] == 1 and rep["orders"][0]["status"] == "ready" and rep["counts"]["lots_add"] == 2
    out = broker_import.commit(ws, text=etrade_csv(), file_name=ETRADE_FILE_NAME, account="Member_1_IRA", confirm_method="fifo")
    assert len(out["confirmed"]) == 1 and out["import_ids"] == [out["import_id"]]
    again = broker_import.preview(ws, text=etrade_csv(), file_name=ETRADE_FILE_NAME)  # account remembered from line 3
    assert again["account"] == "Member_1_IRA" and not again["will_write"]


def test_vanguard_needs_one_account_per_hint(ws):
    rep = broker_import.preview(ws, text=vanguard_csv(), file_name=VANGUARD_FILE_NAME, account="Member_2_IRA")
    assert rep["needs_account"] and "each account" in rep["errors"][0]["error"]  # one `account` cannot cover two hints
    assert {h["hint"]: h["rows"] for h in rep["hints"]} == {"vanguard:1111": 6, "vanguard:2222": 5}
    half = broker_import.preview(ws, text=vanguard_csv(), file_name=VANGUARD_FILE_NAME, accounts={"vanguard:1111": "Member_2_IRA"})
    assert half["needs_account"]
    with pytest.raises(ValidationError):
        broker_import.commit(ws, text=vanguard_csv(), file_name=VANGUARD_FILE_NAME, accounts={"vanguard:1111": "Member_2_IRA"})


def test_vanguard_preview_splits_lots_orders_and_income_per_account(ws):
    rep = broker_import.preview(ws, text=vanguard_csv(), file_name=VANGUARD_FILE_NAME, accounts=MAP)
    assert not rep["needs_account"] and rep["broker"] == "vanguard" and len(rep["parts"]) == 2
    assert rep["counts"]["orders"] == 2 and {o["account"] for o in rep["orders"]} == set(MAP.values())
    ira = next(p for p in rep["parts"] if p["account"] == "Member_2_IRA")
    roth = next(p for p in rep["parts"] if p["account"] == "Member_2_Roth")
    assert [l["symbol"] for l in ira["lots"]] == ["EXMK"] and [l["symbol"] for l in roth["lots"]] == ["EXMK"]
    assert ira["orders"][0]["symbol"] == "EXMK" and ira["orders"][0]["shares"] == 5 and ira["orders"][0]["proceeds"] == 999.5
    assert roth["orders"][0]["symbol"] == "EXSB" and roth["orders"][0]["proceeds"] == 240
    assert ira["income_totals"] == {"dividend": 43.11, "interest": 8.41} and roth["income_totals"] == {"dividend": 2.5}
    assert rep["income_totals"] == {"dividend": 45.61, "interest": 8.41}
    assert len(rep["ignored"]) >= 3  # sweep rows and the conversion/withdrawal are listed, never acted on


def test_vanguard_commit_is_one_transaction_with_an_import_per_account_and_reverts_independently(ws):
    out = broker_import.commit(ws, text=vanguard_csv(), file_name=VANGUARD_FILE_NAME, accounts=MAP, confirm_method="fifo")
    assert len(out["import_ids"]) == 2 and out["rows_new"] == 11 and len(out["confirmed"]) == 2
    with active_plan.workspace_store(ws.parent) as store:
        accounts = {i["account"] for i in store.broker.list_imports()}
        assert accounts == set(MAP.values())
        for acct in MAP.values():
            assert all(r["account"] == acct for r in store.broker.activity(account=acct))
        assert store.broker.account_for("vanguard:1111") == "Member_2_IRA"
    again = broker_import.preview(ws, text=vanguard_csv(), file_name=VANGUARD_FILE_NAME)  # mapping remembered
    assert not again["will_write"] and again["already_imported"] == 11
    for iid in out["import_ids"]:
        with pytest.raises(ValidationError):
            broker_import.revert(ws, iid)  # confirmed sales block a revert, as for a single account


def test_vanguard_commit_failure_leaves_nothing(ws):
    bad = VANGUARD_ROWS + ["11111111,9/15/2026,9/16/2026,Sell,Sell,X,EXMK,5,200,1000,0,1000,0,CASH"]
    with pytest.raises(ValidationError):
        broker_import.commit(ws, text=vanguard_csv(bad), file_name=VANGUARD_FILE_NAME, accounts=MAP)
    with active_plan.workspace_store(ws.parent) as store:
        assert store.broker.list_imports() == []


def test_unrecognized_file_reports_instead_of_guessing(ws):
    rep = broker_import.preview(ws, text="a,b\n1,2\n", file_name="x.csv")
    assert rep["errors"] and "not recognized" in rep["errors"][0]["error"]
