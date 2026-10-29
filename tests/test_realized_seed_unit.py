"""Realized-sales ledger step 3b.1: the pure seed handed to the projection (plan section 7.3). Empty ledger = None."""
from __future__ import annotations

import math

import pytest

from src.projection_stages.year_state import create_initial_year_state
from src.realized_seed import build_realized_seed

YEAR = 2026


def sale(gain, term, date=f"{YEAR}-06-10", **over):
    return {"sale_date": date, "gain": gain, "holding_period": term, "status": "confirmed", "tax_class": "taxable", **over}


def seed(sales=(), adjustments=None, year=YEAR, filing="MFJ"):
    return build_realized_seed(list(sales), adjustments or {}, year, filing)


def test_empty_ledger_gives_no_seed():
    assert seed() is None
    assert seed(adjustments={}) is None


def test_other_years_voided_and_non_taxable_rows_give_no_seed():
    rows = [sale(500.0, "long", date="2027-01-05"),
            sale(900.0, "long", status="voided"),
            sale(900.0, "long", tax_class="roth"),
            sale(None, "long")]
    assert seed(rows) is None


def test_gains_split_ordinary_and_long_term_with_no_loss_pool():
    s = seed([sale(1500.0, "short"), sale(800.0, "long")])
    assert s == {"year": YEAR, "gain_ordinary": 1500.0, "gain_ltcg": 800.0, "loss_pool": 0.0}


def test_cross_net_leaves_ordinary_gain_only():
    s = seed([sale(5000.0, "short"), sale(-2000.0, "long")])
    assert (s["gain_ordinary"], s["gain_ltcg"], s["loss_pool"]) == (3000.0, 0.0, 0.0)


def test_net_loss_becomes_the_pool_the_engine_applies_its_own_offset_to():
    s = seed([sale(-8000.0, "long"), sale(1000.0, "short")])  # net loss 7,000: engine takes its $3,000 offset itself
    assert (s["gain_ordinary"], s["gain_ltcg"], s["loss_pool"]) == (0.0, 0.0, 7000.0)


def test_entered_carryforward_alone_seeds_a_pool():
    s = seed(adjustments={YEAR: {"carryforward_short": 250.0, "carryforward_long": 1000.0}})
    assert s["loss_pool"] == 1250.0 and s["gain_ordinary"] == 0.0 and s["gain_ltcg"] == 0.0


def test_carryforward_is_used_against_the_years_gains_before_seeding():
    s = seed([sale(4000.0, "long")], {YEAR: {"carryforward_short": 0.0, "carryforward_long": 1000.0}})
    assert (s["gain_ltcg"], s["loss_pool"]) == (3000.0, 0.0)


def test_prior_year_loss_chains_into_the_seed():
    rows = [sale(-8000.0, "long", date="2025-03-03")]  # 3,000 used in 2025, 5,000 carried in
    assert seed(rows)["loss_pool"] == 5000.0


def test_seed_values_are_plain_non_negative_floats():
    s = seed([sale(-3.0, "short"), sale(3.0, "long")])  # nets to exactly zero: still a seed, all zeros
    assert s is not None
    for k in ("gain_ordinary", "gain_ltcg", "loss_pool"):
        assert s[k] == 0.0 and math.copysign(1.0, s[k]) == 1.0


def test_year_state_starts_from_the_pool_or_exactly_zero():
    assert create_initial_year_state({}).cap_loss_carryforward == 0.0
    assert create_initial_year_state({"realized_seed": None}).cap_loss_carryforward == 0.0
    state = create_initial_year_state({"realized_seed": {"loss_pool": 5000.0, "gain_ordinary": 0.0, "gain_ltcg": 0.0}})
    assert state.cap_loss_carryforward == 5000.0


# ------------------------------------------------------------------------------ config assembly
from src import active_plan, platform_runtime  # noqa: E402
from src.realized_seed import active_realized_seed  # noqa: E402
from tests.test_synthetic_golden_master import empty_workspace  # noqa: E402


def _record(root, **over):
    from src import sales_service
    row = dict(sale_date=f"{YEAR}-06-10", account="Trust_taxable", tax_class="taxable", symbol="VTI", shares=10,
               proceeds=2000.0, fees=0.0, basis=1500.0, purchase_date="2025-01-02")
    row.update(over)
    return sales_service.add_sale(root / "input", row)


def test_active_seed_is_none_without_a_plan_file_and_never_creates_one():
    with empty_workspace() as root:
        assert active_realized_seed(YEAR, "MFJ") is None
        assert not (root / "plan.rpx").exists()


def test_active_seed_reads_the_active_plans_ledger():
    with empty_workspace() as root:
        with active_plan.workspace_store(root, write=True):
            pass
        assert active_realized_seed(YEAR, "MFJ") is None  # empty ledger
        _record(root)  # +500 long-term
        s = active_realized_seed(YEAR, "MFJ")
        assert s == {"year": YEAR, "gain_ordinary": 0.0, "gain_ltcg": 500.0, "loss_pool": 0.0}


def test_parse_client_puts_the_seed_in_the_config():
    from src.data_io import parse_client
    from tests.golden_pricing import FROZEN_GOLDEN_MASTER_PRICES, frozen_holdings_prices
    from tests.plan_fixture import plan_data
    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        with empty_workspace() as root:
            with active_plan.workspace_store(root, write=True):
                pass
            c = parse_client(plan_data(), "")
            assert c["realized_seed"] is None
            _record(root, sale_date=f"{c['plan_start']}-06-10", proceeds=1000.0, basis=1400.0)
            c = parse_client(plan_data(), "")
            assert c["realized_seed"] == {"year": c["plan_start"], "gain_ordinary": 0.0, "gain_ltcg": 0.0, "loss_pool": 400.0}


def test_use_realized_sales_setting_defaults_on_and_false_drops_the_seed():
    from src.data_io import parse_client
    from tests.golden_pricing import FROZEN_GOLDEN_MASTER_PRICES, frozen_holdings_prices
    from tests.plan_fixture import plan_data
    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        with empty_workspace() as root:
            with active_plan.workspace_store(root, write=True):
                pass
            data = plan_data()
            c = parse_client(data, "")
            assert c["use_realized_sales"] is True
            _record(root, sale_date=f"{c['plan_start']}-06-10", proceeds=1000.0, basis=1400.0)
            assert parse_client(data, "")["realized_seed"]["loss_pool"] == 400.0
            data.setdefault("Plan Settings", {}).setdefault("Tax Detail", {})["use_realized_sales"] = "FALSE"
            c = parse_client(data, "")
            assert c["use_realized_sales"] is False and c["realized_seed"] is None


# ------------------------------------------------------------------------------ report note
from src.governance import workbook_consistency_warnings  # noqa: E402


def _ledger_notes(c):
    return [w for w in workbook_consistency_warnings(c, []) if w["code"] == "REALIZED_LEDGER_IN_YEAR_1"]


def test_no_ledger_note_without_a_seed():
    assert _ledger_notes({}) == [] and _ledger_notes({"realized_seed": None}) == []


def test_ledger_note_names_the_year_the_amounts_and_the_switch():
    notes = _ledger_notes({"realized_seed": {"year": YEAR, "gain_ordinary": 1500.0, "gain_ltcg": 12345.6, "loss_pool": 0.0}})
    assert len(notes) == 1 and notes[0]["severity"] == "INFO"
    msg = notes[0]["message"]
    assert f"{YEAR}" in msg and "$1,500 net short-term gain" in msg and "$12,346 net long-term gain" in msg
    assert "loss" not in msg
    assert "use_realized_sales" in notes[0]["action"]


def test_ledger_note_for_a_loss_pool():
    msg = _ledger_notes({"realized_seed": {"year": YEAR, "gain_ordinary": 0.0, "gain_ltcg": 0.0, "loss_pool": 5000.0}})[0]["message"]
    assert "$5,000 capital-loss pool" in msg and "gain" not in msg


def test_ledger_note_for_a_year_that_nets_to_zero():
    msg = _ledger_notes({"realized_seed": {"year": YEAR, "gain_ordinary": 0.0, "gain_ltcg": 0.0, "loss_pool": 0.0}})[0]["message"]
    assert "net to zero" in msg
