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


# ---- HSA: bank-capped, income tax only (owner choice 2026-11-03) ------------------------------------------------------
def test_hsa_excess_over_the_bank_only_and_blank_bank_means_all_qualified():
    on = {"cash_pair_status_tax": True, "plan_start": 2026}
    bal = {"H1": 10000.0, "H2": 100.0}
    c = {**on, "cash_pair_floor_hsa_draws": {"H1": 3000.0, "H2": 1000.0}, "hsa_expense_bank": 1000.0}
    assert cash_tax_floor.floor_draws(c, bal, 2026) == {"H1": 2250.0, "H2": 100.0}          # excess 3000, pro rata, H2 capped at balance
    assert cash_tax_floor.floor_draws({**c, "hsa_expense_bank": None}, bal, 2026) == {}      # blank bank: all qualified
    assert cash_tax_floor.floor_draws({**c, "hsa_expense_bank": 9999.0}, bal, 2026) == {}    # bank covers it
    assert cash_tax_floor.floor_draws({**c, "cash_pair_status_tax": False}, bal, 2026) == {}


def test_reported_hsa_draws_use_hsa_accounts_only(monkeypatch):
    row = [{"class": "distribution", "counts": True, "in_kind": False, "date": "2026-03-01", "amount": -40.0,
            "pair_status": "external_withdrawal"}]
    ledgers = {"A_HSA": row, "B_IRA": row}
    monkeypatch.setattr(cash_view, "_accounts", lambda s: list(ledgers))
    monkeypatch.setattr(cash_view, "_ledgers", lambda s, a: ledgers)
    monkeypatch.setattr(sales_confirm, "default_tax_class", lambda s, a: "hsa" if a.endswith("HSA") else "pre_tax")
    assert cash_tax_floor.reported_hsa_draws(None, 2026) == {"A_HSA": 40.0}
    assert cash_tax_floor.reported_draws(None, 2026) == {"B_IRA": 40.0}


def test_engine_hsa_excess_is_drawn_and_taxed_but_qualified_part_is_left_alone():
    from src.planning_engines import project
    from tests.golden_pricing import FROZEN_GOLDEN_MASTER_PRICES, frozen_holdings_prices
    from tests.test_frozen_sample_plan_golden_master_regression import _frozen_config
    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        c = _frozen_config()
        base = project(copy.deepcopy(c))
        rep = {"cash_pair_status_tax": True, "cash_pair_floor_hsa_draws": {"Member_1_HSA": 6000.0}}
        qual = project({**copy.deepcopy(c), **rep, "hsa_expense_bank": 6000.0})     # bank covers it: nothing changes
        base_bank = project({**copy.deepcopy(c), "hsa_expense_bank": 6000.0})        # same bank, floor setting off
        nonq = project({**copy.deepcopy(c), **rep, "hsa_expense_bank": 1000.0})     # 5,000 excess
    assert qual == base_bank and all("_pair_floor_draws" not in r for r in qual)
    assert nonq[0]["_pair_floor_draws"] == {"Member_1_HSA": 5000.0}
    assert nonq[0]["_account_withdrawals"]["Member_1_HSA"] >= 5000.0
    assert all("_pair_floor_draws" not in r for r in nonq[1:])

# ---- taxable: cash leaving a brokerage account is not itself taxed; the sales are (realized_seed) ------------------------
def test_taxable_withdrawals_never_enter_the_floor_so_realized_sales_are_not_double_counted(monkeypatch):
    row = [{"class": "distribution", "counts": True, "in_kind": False, "date": "2026-03-01", "amount": -900.0,
            "pair_status": "external_withdrawal"}]
    ledgers = {"A_Trust": row, "B_IRA": row, "C_HSA": row}
    monkeypatch.setattr(cash_view, "_accounts", lambda s: list(ledgers))
    monkeypatch.setattr(cash_view, "_ledgers", lambda s, a: ledgers)
    monkeypatch.setattr(sales_confirm, "default_tax_class",
                        lambda s, a: {"A_Trust": "taxable", "B_IRA": "pre_tax", "C_HSA": "hsa"}[a])
    assert cash_tax_floor.reported_draws(None, 2026) == {"B_IRA": 900.0}
    assert cash_tax_floor.reported_hsa_draws(None, 2026) == {"C_HSA": 900.0}
    on = {"cash_pair_status_tax": True, "plan_start": 2026, "cash_pair_floor_taxable_draws": {"A_Trust": 900.0}}
    assert cash_tax_floor.floor_draws(on, {"A_Trust": 5000.0}, 2026) == {}      # no taxable channel exists


def test_engine_taxes_realized_sales_through_realized_seed_not_the_floor():
    from src.planning_engines import project
    from tests.golden_pricing import FROZEN_GOLDEN_MASTER_PRICES, frozen_holdings_prices
    from tests.test_frozen_sample_plan_golden_master_regression import _frozen_config
    seed = {"year": 2026, "gain_ordinary": 0.0, "gain_ltcg": 40000.0, "loss_pool": 0.0}
    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        c = _frozen_config()
        base = project(copy.deepcopy(c))
        seeded = project({**copy.deepcopy(c), "realized_seed": seed})
        both = project({**copy.deepcopy(c), "realized_seed": seed, "cash_pair_status_tax": True,
                        "cash_pair_floor_taxable_draws": {"Member_1_Trust": 25000.0}})
    assert seeded[0]["total_tax"] > base[0]["total_tax"]       # the sales are taxed ...
    assert both == seeded                                      # ... and a reported taxable withdrawal adds nothing


# ---- Roth: basis first; earnings taxed unless owner >= 60 and 5 years from the first contribution --------------------
ROTH = {"cash_pair_status_tax": True, "plan_start": 2026,
        "account_registry": [{"id": "R1", "owner_idx": 0}, {"id": "R2", "owner_idx": 1}]}


def roth(rep, basis, first, **kw):
    return {**ROTH, "cash_pair_floor_roth_draws": rep, "roth_basis": {a: {"basis": basis, "first_year": first} for a in rep}, **kw}


def test_roth_basis_covers_withdrawal_means_no_tax():
    assert cash_tax_floor.floor_draws(roth({"R1": 4000.0}, 5000.0, 2015), {"R1": 9e4}, 2026, 50, 50) == {}


def test_roth_earnings_taxed_when_under_60_or_five_year_not_met_else_qualified():
    bal = {"R1": 9e4, "R2": 9e4}
    assert cash_tax_floor.floor_draws(roth({"R1": 7000.0}, 5000.0, 2015), bal, 2026, 55, 70) == {"R1": 2000.0}   # owner 55: not qualified
    assert cash_tax_floor.floor_draws(roth({"R1": 7000.0}, 5000.0, 2023), bal, 2026, 70, 70) == {"R1": 2000.0}   # only 3 years
    assert cash_tax_floor.floor_draws(roth({"R1": 7000.0}, 5000.0, 2021), bal, 2026, 70, 55) == {}               # 60+ and 5 years
    assert cash_tax_floor.floor_draws(roth({"R2": 7000.0}, 5000.0, 2015), bal, 2026, 70, 55) == {"R2": 2000.0}   # owner_idx 1 uses w_age
    assert cash_tax_floor.floor_draws(roth({"R1": 7000.0}, 5000.0, 2015), bal, 2026, 59, 70) == {"R1": 2000.0}   # 59 counts as under 59 1/2


def test_roth_unknown_inputs_are_never_guessed_and_draw_is_capped_at_balance():
    bal = {"R1": 1500.0}
    assert cash_tax_floor.floor_draws(roth({"R1": 7000.0}, None, 2015), bal, 2026, 50, 50) == {}
    assert cash_tax_floor.floor_draws(roth({"R1": 7000.0}, 5000.0, None), bal, 2026, 50, 50) == {}
    assert cash_tax_floor.floor_draws(roth({"R1": 7000.0}, 0.0, 2015), bal, 2026, 50, 50) == {"R1": 1500.0}


def test_reported_roth_draws_use_roth_accounts_only(monkeypatch):
    row = [{"class": "distribution", "counts": True, "in_kind": False, "date": "2026-03-01", "amount": -70.0,
            "pair_status": "external_withdrawal"}]
    ledgers = {"A_Roth": row, "B_IRA": row}
    monkeypatch.setattr(cash_view, "_accounts", lambda s: list(ledgers))
    monkeypatch.setattr(cash_view, "_ledgers", lambda s, a: ledgers)
    monkeypatch.setattr(sales_confirm, "default_tax_class", lambda s, a: "roth" if a.endswith("Roth") else "pre_tax")
    assert cash_tax_floor.reported_roth_draws(None, 2026) == {"A_Roth": 70.0}


def test_roth_basis_rows_exist_only_for_roth_accounts(monkeypatch, tmp_path):
    from src.server import app_core
    monkeypatch.setattr(app_core, "_all_account_ids_from_holdings", lambda d=None: ["Member_1_Roth", "Member_1_IRA", "Family_Checking"])
    rows = app_core._roth_basis_ui_plan_data_rows(tmp_path)
    assert [(r[0], r[1], r[2], r[3]) for r in rows] == [("Roth Basis", "Member_1_Roth", "roth_contribution_basis", ""),
                                                        ("Roth Basis", "Member_1_Roth", "roth_first_contribution_year", "")]


def test_engine_roth_earnings_drawn_and_taxed_only_when_not_qualified():
    from src.planning_engines import project
    from tests.golden_pricing import FROZEN_GOLDEN_MASTER_PRICES, frozen_holdings_prices
    from tests.test_frozen_sample_plan_golden_master_regression import _frozen_config
    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        c = _frozen_config()
        base = project(copy.deepcopy(c))
        inp = {"cash_pair_status_tax": True, "cash_pair_floor_roth_draws": {"Member_1_Roth": 20000.0}}
        owner_age = base[0]["h_age"]
        young = {**inp, "roth_basis": {"Member_1_Roth": {"basis": 5000.0, "first_year": 2025}}}      # 5-year not met
        old = {**inp, "roth_basis": {"Member_1_Roth": {"basis": 5000.0, "first_year": 2005}}}
        nonq = project({**copy.deepcopy(c), **young})
        qual = project({**copy.deepcopy(c), **old})
    assert nonq[0]["_pair_floor_draws"] == {"Member_1_Roth": 15000.0}
    assert nonq[0]["_account_withdrawals"]["Member_1_Roth"] >= 15000.0
    assert owner_age >= 60 and qual == base                      # 5 years met and owner >= 60: qualified, nothing changes
