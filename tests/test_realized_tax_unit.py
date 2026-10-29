"""Realized-sales ledger step 3a.1: per-year capital gain/loss netting (plan section 7.1). Worked examples."""
from __future__ import annotations

import math

import pytest

from src import core, realized_tax
from src.realized_tax import net_realized_by_year, net_realized_year, realized_gain_tax

KEYS = ("net_st", "net_lt", "ordinary_offset", "carryforward_st", "carryforward_lt",
        "gain_to_tax_ordinary", "gain_to_tax_ltcg")


def net(st=0.0, lt=0.0, cf_st=0.0, cf_lt=0.0, filing="MFJ"):
    return net_realized_year(st, lt, carryforward_st=cf_st, carryforward_lt=cf_lt, filing=filing)


def test_empty_input_is_exactly_zero():
    out = net()
    assert tuple(out) == KEYS
    for k in KEYS:
        assert out[k] == 0.0 and math.copysign(1.0, out[k]) == 1.0, k
    assert net_realized_by_year([], {}) == {}


def test_st_gain_with_lt_loss_nets_into_ordinary_gain():
    # +5,000 ST, -2,000 LT: the LT loss cancels 2,000 of the ST gain; 3,000 taxed as ordinary.
    out = net(st=5000, lt=-2000)
    assert (out["net_st"], out["net_lt"]) == (5000.0, -2000.0)
    assert (out["gain_to_tax_ordinary"], out["gain_to_tax_ltcg"]) == (3000.0, 0.0)
    assert (out["ordinary_offset"], out["carryforward_st"], out["carryforward_lt"]) == (0.0, 0.0, 0.0)


def test_st_loss_offsets_lt_gain_and_keeps_ltcg_character():
    out = net(st=-4000, lt=10000)
    assert (out["gain_to_tax_ordinary"], out["gain_to_tax_ltcg"]) == (0.0, 6000.0)
    assert out["ordinary_offset"] == 0.0


def test_st_gain_and_lt_gain_taxed_separately():
    out = net(st=1200, lt=800)
    assert (out["gain_to_tax_ordinary"], out["gain_to_tax_ltcg"]) == (1200.0, 800.0)


def test_lt_loss_beyond_limit_carries_forward_as_long_term():
    # +1,000 ST, -6,000 LT: net loss 5,000 -> 3,000 deducted, 2,000 carried as LT.
    out = net(st=1000, lt=-6000)
    assert out["ordinary_offset"] == 3000.0
    assert (out["carryforward_st"], out["carryforward_lt"]) == (0.0, 2000.0)
    assert (out["gain_to_tax_ordinary"], out["gain_to_tax_ltcg"]) == (0.0, 0.0)


def test_both_losses_beyond_limit_deduction_uses_short_term_first():
    # -2,000 ST, -4,000 LT: 3,000 deduction = 2,000 ST + 1,000 LT; 3,000 LT carries.
    out = net(st=-2000, lt=-4000)
    assert out["ordinary_offset"] == 3000.0
    assert (out["carryforward_st"], out["carryforward_lt"]) == (0.0, 3000.0)
    # -5,000 ST, -1,000 LT: deduction is all ST; 2,000 ST and 1,000 LT carry.
    out = net(st=-5000, lt=-1000)
    assert (out["ordinary_offset"], out["carryforward_st"], out["carryforward_lt"]) == (3000.0, 2000.0, 1000.0)


def test_losses_within_limit_are_fully_deducted():
    out = net(st=-1000, lt=-500)
    assert out["ordinary_offset"] == 1500.0
    assert (out["carryforward_st"], out["carryforward_lt"]) == (0.0, 0.0)


def test_carryforward_in_applies_to_matching_bucket_first():
    # 4,000 ST gain less 1,500 ST carryforward = 2,500; LT carryforward must not touch the ST bucket.
    out = net(st=4000, cf_st=1500, cf_lt=2000)
    assert out["net_st"] == 2500.0 and out["net_lt"] == -2000.0
    assert out["gain_to_tax_ordinary"] == 500.0  # 2,500 ST less the 2,000 LT loss after cross-net
    assert out["gain_to_tax_ltcg"] == 0.0


def test_carryforward_in_alone_is_deducted_then_carried_out():
    out = net(cf_lt=4500)
    assert out["net_lt"] == -4500.0
    assert (out["ordinary_offset"], out["carryforward_st"], out["carryforward_lt"]) == (3000.0, 0.0, 1500.0)


def test_carryforward_out_then_in_over_three_years():
    sales = [
        {"tax_year": 2026, "term": "long", "gain": -8000.0},
        {"tax_year": 2027, "term": "long", "gain": 1000.0},
        {"tax_year": 2028, "term": "short", "gain": 500.0},
    ]
    by_year = net_realized_by_year(sales, {})
    assert by_year[2026]["ordinary_offset"] == 3000.0 and by_year[2026]["carryforward_lt"] == 5000.0
    # 2027: 1,000 LT gain less 5,000 carried = -4,000 -> 3,000 deducted, 1,000 carried on.
    assert by_year[2027]["net_lt"] == -4000.0 and by_year[2027]["carryforward_lt"] == 1000.0
    # 2028: 500 ST gain less the 1,000 LT carry = -500 overall: no tax, 500 deducted, nothing left.
    assert by_year[2028]["gain_to_tax_ordinary"] == 0.0 and by_year[2028]["ordinary_offset"] == 500.0
    assert by_year[2028]["carryforward_lt"] == 0.0
    assert sorted(by_year) == [2026, 2027, 2028]


def test_entered_adjustment_overrides_the_computed_carryforward_for_that_year():
    sales = [{"tax_year": 2026, "term": "long", "gain": -8000.0}, {"tax_year": 2027, "term": "long", "gain": 2000.0}]
    adjustments = {2027: {"carryforward_short": 0.0, "carryforward_long": 500.0}}  # user's Schedule D figure
    by_year = net_realized_by_year(sales, adjustments)
    assert by_year[2027]["net_lt"] == 1500.0 and by_year[2027]["gain_to_tax_ltcg"] == 1500.0


def test_entered_carryforward_year_with_no_sales_is_still_reported():
    by_year = net_realized_by_year([], {2026: {"carryforward_short": 700.0, "carryforward_long": 0.0}})
    assert by_year[2026]["net_st"] == -700.0 and by_year[2026]["ordinary_offset"] == 700.0


def test_mfs_limit_is_half():
    out = net(st=-5000, filing="MFS")
    assert out["ordinary_offset"] == 1500.0 and out["carryforward_st"] == 3500.0
    assert net(st=-5000, filing="Married Filing Separately")["ordinary_offset"] == 1500.0
    for filing in ("MFJ", "Single", "HOH"):
        assert net(st=-5000, filing=filing)["ordinary_offset"] == 3000.0


def test_limit_is_the_shared_tax_table_figure():
    # One figure for the ledger and the engine (IRC 1211(b)): taxes.capital_loss_ordinary_limit.
    from src import taxes
    assert realized_tax.ORDINARY_LOSS_LIMIT is taxes.CAPITAL_LOSS_ORDINARY_LIMIT
    for filing, limit in (("MFJ", 3000.0), ("Single", 3000.0), ("HOH", 3000.0), ("MFS", 1500.0),
                          ("mfs", 1500.0), ("Married Filing Separately", 1500.0), ("", 3000.0), (None, 3000.0)):
        assert taxes.capital_loss_ordinary_limit(filing) == limit, filing


def test_skipped_rows_voided_and_non_taxable_do_not_count():
    sales = [
        {"tax_year": 2026, "term": "short", "gain": 100.0},
        {"tax_year": 2026, "term": "long", "gain": 900.0, "status": "voided"},
        {"tax_year": 2026, "term": "long", "gain": 900.0, "tax_class": "roth"},
        {"tax_year": 2026, "term": "long", "gain": None, "tax_class": "taxable"},
    ]
    out = net_realized_by_year(sales, {})[2026]
    assert (out["net_st"], out["net_lt"]) == (100.0, 0.0)


def test_unknown_term_is_rejected():
    with pytest.raises(ValueError):
        net_realized_by_year([{"tax_year": 2026, "term": "unknown", "gain": 1.0}], {})


# --------------------------------------------------------------------------- tax hooks
_C = {"state": "Texas", "brk_inf": 0.02, "filing_status": "MFJ", "model_niit": True}


def test_gain_tax_calls_existing_functions():
    netting = net(lt=100000)
    t = realized_gain_tax(_C, netting, year=2026, ordinary_income=150000, magi=400000)
    assert t["ltcg_tax"] == core.ltcg_tax_on_gain(_C, 100000, 150000, 2026)
    assert t["niit"] == core.niit_tax(100000, 400000, "MFJ") == pytest.approx(100000 * 0.038)
    assert t["state_tax"] == 0.0
    assert t["total"] == pytest.approx(t["ltcg_tax"] + t["niit"])


def test_gain_tax_state_is_looked_up_per_year():
    c = dict(_C, residency_schedule=[
        {"state": "Texas", "start_year": 2000, "end_year": 2026},
        {"state": "Illinois", "start_year": 2027, "end_year": 2100},
    ])
    netting = net(lt=50000)
    tx = realized_gain_tax(c, netting, year=2026, ordinary_income=100000, magi=150000)
    il = realized_gain_tax(c, netting, year=2027, ordinary_income=100000, magi=150000)
    assert tx["state_tax"] == 0.0 and il["state_tax"] > 0.0
    assert il["state_tax"] == core.state_income_tax("Illinois", 0.0, 0.0, 0.0, 50000, 0.0, 0.0, 2027,
                                                    age_over_65=True, filing="MFJ", brk_inf=0.02, rate_override=None)


def test_gain_tax_rate_override_and_niit_switch():
    c = dict(_C, model_niit=False)
    t = realized_gain_tax(c, net(lt=10000), year=2026, ordinary_income=0, magi=500000, state_rate_override=0.05)
    assert t["niit"] == 0.0 and t["state_tax"] == pytest.approx(500.0)


def test_gain_tax_ordinary_part_and_offset_credit():
    c = dict(_C)
    gain = realized_gain_tax(c, net(st=20000), year=2026, ordinary_income=100000, magi=100000)
    base = core.compute_fed_tax(100000, 2026, "MFJ", 0.02)
    assert gain["ordinary_tax"] == pytest.approx(core.compute_fed_tax(120000, 2026, "MFJ", 0.02) - base)
    loss = realized_gain_tax(c, net(st=-9000), year=2026, ordinary_income=100000, magi=100000)
    assert loss["ordinary_tax"] == pytest.approx(core.compute_fed_tax(97000, 2026, "MFJ", 0.02) - base)
    assert loss["ordinary_tax"] < 0 and loss["niit"] == 0.0 and loss["ltcg_tax"] == 0.0


def test_empty_netting_gives_zero_tax():
    t = realized_gain_tax(_C, net(), year=2026, ordinary_income=100000, magi=100000)
    assert all(v == 0.0 for v in t.values())
