"""Pair-status tax floor (cash plan section 10 item 3; owner choice "floor"): default OFF, and a no-op while OFF."""
import copy

from src import cash_tax_floor, cash_view
from src import sales_confirm


def test_off_by_default_and_outside_the_first_year():
    bal = {"IRA": 100.0}
    assert cash_tax_floor.floor_draws({"plan_start": 2026, "cash_pair_floor_draws": {"IRA": 5}}, bal, 2026) == {}
    on = {"cash_pair_status_tax": True, "plan_start": 2026, "cash_pair_floor_draws": {"IRA": 5, "Gone": 9, "Zero": 0}}
    assert cash_tax_floor.floor_draws(on, bal, 2026) == {"IRA": 5.0}
    assert cash_tax_floor.floor_draws(on, bal, 2027) == {}
    assert cash_tax_floor.floor_draws({**on, "cash_pair_floor_draws": {"IRA": 500}}, bal, 2026) == {"IRA": 100.0}   # capped


def test_reported_draws_take_external_withdrawals_of_pre_tax_accounts_only(monkeypatch):
    def led(status, cls="distribution"):
        return [{"class": cls, "counts": True, "in_kind": False, "date": "2026-03-01", "amount": -50.0, "pair_status": status}]
    ledgers = {"A_IRA": led("external_withdrawal"), "B_IRA": led("internal"), "C_Roth": led("external_withdrawal"),
               "D_IRA": led("external_withdrawal", "excess_return")}
    monkeypatch.setattr(cash_view, "_accounts", lambda s: list(ledgers))
    monkeypatch.setattr(cash_view, "_ledgers", lambda s, a: ledgers)
    monkeypatch.setattr(sales_confirm, "default_tax_class", lambda s, a: "roth" if a.endswith("Roth") else "pre_tax")
    assert cash_tax_floor.reported_draws(None, 2026) == {"A_IRA": 50.0}


def test_engine_off_is_identical_and_on_forces_a_taxed_pretax_draw():
    from src.planning_engines import project
    from tests.golden_pricing import FROZEN_GOLDEN_MASTER_PRICES, frozen_holdings_prices
    from tests.test_frozen_sample_plan_golden_master_regression import _frozen_config
    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        c = _frozen_config()
        base = project(copy.deepcopy(c))
        off = project({**copy.deepcopy(c), "cash_pair_floor_draws": {"Member_2_IRA": 30000.0}})   # draws given, setting off
        on = project({**copy.deepcopy(c), "cash_pair_status_tax": True, "cash_pair_floor_draws": {"Member_2_IRA": 30000.0}})
    assert off == base and all("_pair_floor_draws" not in r for r in base)
    assert on[0]["_pair_floor_draws"] == {"Member_2_IRA": 30000.0}
    assert on[0]["_account_withdrawals"]["Member_2_IRA"] == 30000.0
    assert on[0]["total_tax"] > base[0]["total_tax"]                  # ordinary income, like an RMD
    assert all("_pair_floor_draws" not in r for r in on[1:])          # first year only


def test_setting_row_exists_and_defaults_off():
    from src.server import app_core
    rows = [r for r in app_core.CASH_TRACKING_UI_PLAN_DATA_ROWS if r[2] == "cash_pair_status_tax"]
    assert len(rows) == 1 and rows[0][3] == "FALSE" and rows[0][4] == "bool"
