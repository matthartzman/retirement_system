"""WP12.1: rental tax core (src/rental_tax.py) against IRS-style worked examples.

Cases live in ``tests/fixtures/irs_style_examples.json`` under ``rental_property_examples``;
each has an ``id`` (R01..R24) that ``documentation/reference/RENTAL_TAX_RULES.md`` explains.
Constants come from the shipped reference.db (``reference_src/tax_law_v10.json``).
"""
from __future__ import annotations

import ast
import json
from datetime import date
from pathlib import Path

import pytest

from src import rental_tax as rt
from src.tax_law import load_tax_law_dataset

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = json.loads((ROOT / "tests/fixtures/irs_style_examples.json").read_text(encoding="utf-8"))[
    "rental_property_examples"]
RULES_DOC = ROOT / "documentation/reference/RENTAL_TAX_RULES.md"
YEAR = 2026


@pytest.fixture(scope="module")
def dataset():
    return load_tax_law_dataset()


def _consts(dataset, filing="MFJ", lived_apart=False):
    return rt.rental_tax_constants(dataset, YEAR, filing, mfs_lived_apart_all_year=lived_apart)


def _ids(section):
    return [f"{c['id']}-{c['name']}" for c in EXAMPLES[section]]


# --------------------------------------------------------------------------- constants

def test_constants_come_from_reference_data(dataset):
    mfj = _consts(dataset)
    assert (mfj.recovery_years, mfj.special_allowance, mfj.phaseout_start, mfj.phaseout_rate) == (27.5, 25000, 100000, 0.5)
    assert (mfj.unrecaptured_1250_max_rate, mfj.section_121_exclusion) == (0.25, 500000)
    assert (mfj.section_121_required_days, mfj.section_121_lookback_years) == (730, 5)
    for status in ("Single", "HOH"):
        c = _consts(dataset, status)
        assert (c.special_allowance, c.phaseout_start, c.section_121_exclusion) == (25000, 100000, 250000)
    apart = _consts(dataset, "MFS", lived_apart=True)
    assert (apart.special_allowance, apart.phaseout_start, apart.section_121_exclusion) == (12500, 50000, 250000)
    assert _consts(dataset, "MFS", lived_apart=False).special_allowance == 0


def test_rental_rows_are_dated_and_sourced(dataset):
    names = {"residential_rental_recovery_years", "passive_rental_special_allowance", "passive_rental_phaseout_start",
             "passive_rental_phaseout_rate", "passive_rental_special_allowance_mfs_not_living_apart",
             "unrecaptured_1250_max_rate", "section_121_exclusion", "section_121_required_days",
             "section_121_lookback_years"}
    rows = [v for v in dataset.values if v.name in names]
    assert {v.name for v in rows} == names
    for v in rows:
        assert v.status == "legislated" and "IRC" in v.source and v.effective_year <= 1997, v


# --------------------------------------------------------------------------- depreciation

@pytest.mark.parametrize("case", EXAMPLES["depreciation_table"], ids=_ids("depreciation_table"))
def test_table_a6_percentages(case):
    pcts = rt.macrs_mid_month_percentages(case["placed_month"], 27.5)
    assert pcts[case["recovery_year"] - 1] == pytest.approx(case["expected_pct"], abs=1e-9)


@pytest.mark.parametrize("month", range(1, 13))
def test_table_a6_columns_sum_to_100_and_have_the_published_shape(month):
    pcts = rt.macrs_mid_month_percentages(month, 27.5)
    assert sum(pcts) == pytest.approx(100.0, abs=1e-9)
    assert len(pcts) == (28 if month <= 6 else 29)
    assert all(p == 3.636 for p in pcts[1:9])  # years 2-9
    assert all(p in (3.636, 3.637) for p in pcts[9:27])  # years 10-27 alternate
    assert pcts[9] == (3.637 if month <= 6 else 3.636)


@pytest.mark.parametrize("case", EXAMPLES["depreciation_dollars"], ids=_ids("depreciation_dollars"))
def test_annual_depreciation(case):
    got = rt.annual_depreciation(case["basis"], case["placed_year"], case["placed_month"], case["tax_year"], 27.5,
                                 disposed_month=case["disposed_month"])
    assert got == pytest.approx(case["expected"], abs=0.005)


@pytest.mark.parametrize("case", EXAMPLES["accumulated_depreciation"], ids=_ids("accumulated_depreciation"))
def test_accumulated_depreciation(case):
    got = rt.accumulated_depreciation(case["basis"], case["placed_year"], case["placed_month"], case["through_year"],
                                      27.5, disposed_month=case["disposed_month"])
    assert got == pytest.approx(case["expected"], abs=0.005)


def test_improvements_depreciate_from_their_own_placed_year():
    assets = [rt.DepreciableAsset(288000, 2026, 6), rt.DepreciableAsset(27500, 2028, 10)]
    assert rt.property_depreciation(assets, 2027, 27.5) == pytest.approx(10471.68)  # roof not yet placed
    assert rt.property_depreciation(assets, 2028, 27.5) == pytest.approx(10471.68 + 208.45)
    full = rt.property_accumulated_depreciation(assets, 2080, 27.5)
    assert full == pytest.approx(288000 + 27500)  # fully recovered, never more than basis


def test_depreciation_edges():
    assert rt.annual_depreciation(100000, 2026, 3, 2025, 27.5) == 0.0  # before placed in service
    assert rt.annual_depreciation(0, 2026, 3, 2026, 27.5) == 0.0
    # sold in the placed-in-service year: placed mid-March, sold mid-September = 6 months
    assert rt.annual_depreciation(110000, 2026, 3, 2026, 27.5, disposed_month=9) == pytest.approx(110000 / 27.5 / 2)
    # sold in the final short year never exceeds that year's table amount
    assert rt.annual_depreciation(100000, 2026, 7, 2054, 27.5, disposed_month=12) == pytest.approx(152.0)
    with pytest.raises(ValueError):
        rt.macrs_mid_month_percentages(13, 27.5)
    with pytest.raises(ValueError):
        rt.annual_depreciation(1000, 2026, 9, 2026, 27.5, disposed_month=3)


@pytest.mark.parametrize("case", EXAMPLES["basis"], ids=_ids("basis"))
def test_depreciable_basis(case):
    if case["kind"] == "purchase":
        got = rt.depreciable_basis(case["purchase_price"], case["closing_costs"], case["land_share"])
    else:
        got = rt.converted_home_depreciable_basis(case["value_at_conversion"], case["adjusted_basis_at_conversion"],
                                                  case["land_share"])
    assert got == pytest.approx(case["expected"])


# --------------------------------------------------------------------------- Schedule E

@pytest.mark.parametrize("case", EXAMPLES["schedule_e"], ids=_ids("schedule_e"))
def test_schedule_e_net(case):
    got = rt.schedule_e_net(case["gross_rent"], case["vacancy_rate"], case["operating_expenses"],
                            case["mortgage_interest"], case["depreciation"])
    assert got == pytest.approx(case["expected"], abs=0.005)


# --------------------------------------------------------------------------- passive-activity loss limit

@pytest.mark.parametrize("case", EXAMPLES["special_allowance"], ids=_ids("special_allowance"))
def test_special_allowance_phase_out(dataset, case):
    c = _consts(dataset, case["filing"], case["mfs_lived_apart_all_year"])
    assert rt.special_allowance(case["magi"], c) == pytest.approx(case["expected"])
    assert rt.special_allowance(case["magi"], c, active_participation=False) == 0.0


@pytest.mark.parametrize("case", EXAMPLES["passive_loss"], ids=_ids("passive_loss"))
def test_passive_loss_limits(dataset, case):
    c = _consts(dataset, case["filing"], case["mfs_lived_apart_all_year"])
    acts = [rt.PassiveActivity(**a) for a in case["activities"]]
    res = rt.apply_passive_loss_limits(acts, case["magi"], c, other_passive_income=case["other_passive_income"])
    by_name = {r.name: r for r in res.activities}
    for name, exp in case["expected"].items():
        r = by_name[name]
        assert (r.allowed, r.suspended, r.released) == (pytest.approx(exp["allowed"]), pytest.approx(exp["suspended"]),
                                                        exp["released"]), name
    assert res.net_to_agi == pytest.approx(case["expected_net_to_agi"])


def test_suspended_loss_carries_forward_then_releases_at_sale(dataset):
    c = _consts(dataset)
    y1 = rt.apply_passive_loss_limits([rt.PassiveActivity("A", -20000)], 160000, c)
    carried = y1.activities[0].suspended
    assert carried == 20000 and y1.net_to_agi == 0
    y2 = rt.apply_passive_loss_limits([rt.PassiveActivity("A", -5000, prior_suspended=carried)], 160000, c)
    assert y2.activities[0].suspended == 25000
    y3 = rt.apply_passive_loss_limits([rt.PassiveActivity("A", 1000, prior_suspended=25000, fully_disposed=True)],
                                      160000, c)
    assert (y3.activities[0].allowed, y3.activities[0].suspended, y3.released_loss) == (-24000, 0, 24000)


def test_allowance_only_for_active_participation_and_offset_shared_pro_rata(dataset):
    c = _consts(dataset)
    acts = [rt.PassiveActivity("act", -30000), rt.PassiveActivity("pas", -10000, active_participation=False),
            rt.PassiveActivity("inc", 8000)]
    res = rt.apply_passive_loss_limits(acts, 90000, c, other_passive_income=2000)
    r = {a.name: a for a in res.activities}
    # Form 8582: line 1d = 8,000 - 30,000 = -22,000; line 3 = 10,000 - 40,000 = -30,000; line 4 = 22,000;
    # allowance available 25,000, used 22,000 (all to the active property, Worksheet 4); passive income
    # 10,000 shared by remaining loss 8,000 : 10,000 (Worksheet 5).
    assert (res.special_allowance_available, res.special_allowance_used) == (25000, 22000)
    assert res.passive_income_offset == pytest.approx(10000)
    assert r["act"].allowed == pytest.approx(-(22000 + 10000 * 8 / 18))
    assert r["pas"].allowed == pytest.approx(-(10000 * 10 / 18))
    assert r["act"].suspended + r["pas"].suspended == pytest.approx(8000)
    assert r["inc"].allowed == 8000
    assert res.net_to_agi == pytest.approx(8000 - 32000)


# --------------------------------------------------------------------------- sale

@pytest.mark.parametrize("case", EXAMPLES["sale"], ids=_ids("sale"))
def test_rental_sale(case):
    res = rt.rental_sale(case["sale_price"], case["selling_costs"], case["cost_basis"], case["improvements"],
                         case["accumulated_depreciation"], loss_basis=case["loss_basis"])
    for k, v in case["expected"].items():
        assert getattr(res, k) == pytest.approx(v), k


@pytest.mark.parametrize("case", EXAMPLES["recapture_tax"], ids=_ids("recapture_tax"))
def test_unrecaptured_1250_tax(dataset, case):
    brackets = [(b.lower, b.upper, b.rate) for b in dataset.bracket_table("ordinary", case["year"],
                                                                          filing_status=case["filing"])]
    cap = _consts(dataset, case["filing"]).unrecaptured_1250_max_rate
    got = rt.unrecaptured_1250_tax(case["amount"], case["ordinary_taxable_income"], brackets, cap)
    assert got == pytest.approx(case["expected"], abs=0.005)


# --------------------------------------------------------------------------- section 121 (converted homes)

@pytest.mark.parametrize("case", EXAMPLES["section_121_test"], ids=_ids("section_121_test"))
def test_section_121_two_of_five(dataset, case):
    c = _consts(dataset)
    periods = [(date.fromisoformat(a), date.fromisoformat(b)) for a, b in case["residence_periods"]]
    got = rt.section_121_two_of_five(date.fromisoformat(case["sale_date"]), date.fromisoformat(case["owned_from"]),
                                     periods, required_days=c.section_121_required_days,
                                     lookback_years=c.section_121_lookback_years)
    assert got is case["expected"]


def test_section_121_needs_ownership_too(dataset):
    c = _consts(dataset)
    # lived there as a tenant from 2020, bought only in mid-2025, sold 2026: ownership < 730 days
    ok = rt.section_121_two_of_five(date(2026, 6, 30), date(2025, 7, 1), [(date(2020, 1, 1), date(2026, 6, 30))],
                                    required_days=c.section_121_required_days,
                                    lookback_years=c.section_121_lookback_years)
    assert ok is False


@pytest.mark.parametrize("case", EXAMPLES["section_121_gain"], ids=_ids("section_121_gain"))
def test_section_121_converted_home_gain(dataset, case):
    c = _consts(dataset, case["filing"])
    res = rt.section_121_converted_home(case["gain"], case["accumulated_depreciation"], qualifies=case["qualifies"],
                                        exclusion=c.section_121_exclusion)
    for k, v in case["expected"].items():
        assert getattr(res, k) == pytest.approx(v), k


# --------------------------------------------------------------------------- module hygiene and documentation

def test_module_is_pure_stdlib_with_no_engine_imports():
    tree = ast.parse((ROOT / "src/rental_tax.py").read_text(encoding="utf-8"))
    allowed = {"__future__", "math", "dataclasses", "datetime", "decimal", "functools", "typing"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert {a.name.split(".")[0] for a in node.names} <= allowed
        elif isinstance(node, ast.ImportFrom):
            # the one relative import is the TaxLawDataset type, under TYPE_CHECKING only
            assert node.level == 0 and node.module.split(".")[0] in allowed or (node.level == 1 and node.module == "tax_law")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id != "open"


def test_rules_document_explains_every_example_id():
    text = RULES_DOC.read_text(encoding="utf-8")
    ids = {c["id"] for cases in EXAMPLES.values() for c in cases}
    missing = sorted(i for i in ids if f"| {i} " not in text)
    assert not missing, f"RENTAL_TAX_RULES.md has no worked-example row for {missing}"
