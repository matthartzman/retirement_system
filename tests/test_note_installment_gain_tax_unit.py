"""Tax on the installment gain inside Note Receivable principal (projection_stages/note_installment_gain.py).

Each principal payment carries a fixed share of short-term gain (ordinary income) and long-term gain (LTCG),
from the note's Form 8949 inputs. Before 2026-11 principal was untaxed.

Design: documentation/future/superpowers/plans/2026-11-06-note-installment-gain-tax-design-and-plan.md 4.2-4.3."""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS", "1")

from src import note_installment_tax as nit
from src.projection_stages import note_installment_gain as nig

ST, LT = nit.gain_ratios(10_671, 0, 48_611, 7_500)
FIRST, LAST = 2027, 2031


def test_year_gains_sums_notes_and_skips_zero_principal():
    a = {"st_gain_per_principal": 0.5, "lt_gain_per_principal": 0.25}
    b = {"st_gain_per_principal": 0.0, "lt_gain_per_principal": 1.0}
    g = nig.year_gains([(a, 100.0), (b, 10.0), (a, 0.0)])
    assert (g.st, g.lt) == (pytest.approx(50.0), pytest.approx(35.0))
    assert nig.year_gains([]) == nig.NoteGains(0.0, 0.0)


def _note(st=ST, lt=LT):
    return {"section": "Note 1", "name": "RedMane Note", "face_value": 59_281.62 * 4 + 59_327.50,
            "first_payment_year": FIRST, "last_payment_year": LAST, "annual_principal": 59_281.62,
            "final_principal": 59_327.50, "interest_by_year": {}, "st_gain_per_principal": st,
            "lt_gain_per_principal": lt}


def _run(note, items=None, proceeds=0.0, sale_year=None):
    from src.planning_engines import project
    from tests import synthetic_plans as sp
    from tests.test_synthetic_golden_master import empty_workspace

    with empty_workspace():
        c = sp.SCENARIOS["baseline_balanced_couple"].build(optimize=False)
        c["note_items"] = [note] if note else []
        c["note_face"] = note["face_value"] if note else 0.0
        if items:
            c["other_asset_items"] = items
            c["startup_eq"] = sum(i["value"] for i in items)
            c["startup_gr"] = 0.0
            c["startup_sale_year"] = sale_year
            c["startup_sale_price"] = proceeds
        return {r["year"]: r for r in project(c)}


def _asset(sell):
    return {"name": "hucu.ai", "type": "Other", "value": 100_000, "basis": 0, "basis_entered": False,
            "tax_treatment": "gains", "purchase_date": f"{sell[:4]}-01-01", "sell_date": sell, "in_startup": True}


@pytest.fixture(scope="module")
def runs():
    return {
        "untaxed": _run(_note(0.0, 0.0)),
        "taxed": _run(_note()),
        "asset_only": _run(_note(0.0, 0.0), [_asset("2029-06-30")], 100_000, 2029),
        "both": _run(_note(), [_asset("2029-06-30")], 100_000, 2029),
    }


def test_engine_taxes_note_gain(runs):
    row, base = runs["taxed"][2028], runs["untaxed"][2028]
    assert row["note_gain_st"] == pytest.approx(10_671, abs=1)
    assert row["note_gain_lt"] == pytest.approx(41_111, abs=1)
    extra = row["total_tax"] - base["total_tax"]
    assert 0.10 * 10_671 - 1 <= extra  # this couple's long-term gain is partly in the 0% LTCG band
    assert extra <=(0.37 + 0.038 + 0.0495) * 10_671 + (0.20 + 0.038 + 0.0495) * 41_111 + 1
    assert row["agi"] >= base["agi"] + 51_782 - 1
    assert row["cashflow_breakdown"]["tax"]["note_installment_gain"] == pytest.approx(row["note_gain_stacked_tax"])
    assert sum(row["cashflow_breakdown"]["tax"].values()) == pytest.approx(row["total_tax"], abs=0.01)


def test_short_term_gain_pushes_long_term_gain_up_the_ltcg_brackets(runs):
    # Schedule D stacks LTCG on top of all ordinary income, the short-term gain included.
    from src import tax_kernel as tk
    from tests import synthetic_plans as sp
    from tests.test_synthetic_golden_master import empty_workspace

    with empty_workspace():
        c = sp.SCENARIOS["baseline_balanced_couple"].build(optimize=False)
    row = runs["taxed"][2028]
    on_top = tk.ltcg_tax_on_gain(c, row["note_gain_lt"], row["taxable_inc"] + row["note_gain_st"], 2028, row["filing"])
    assert on_top > tk.ltcg_tax_on_gain(c, row["note_gain_lt"], row["taxable_inc"], 2028, row["filing"]) + 100
    # At least that much (the gain also makes more Social Security taxable, which sits under the stack too).
    assert row["cashflow_breakdown"]["tax"]["ltcg"] >= on_top - 1


def test_note_gain_tax_is_charged_once(runs):
    # Every dollar the note adds to total_tax is in a named line: the leftover 'other' does not move, so the stacked
    # tax was not charged twice (e.g. on the Priority-4b re-tax path), alone or beside an Other Asset sale.
    for taxed, base, year in (("taxed", "untaxed", 2028), ("both", "asset_only", 2029)):
        t, b = runs[taxed][year]["cashflow_breakdown"]["tax"], runs[base][year]["cashflow_breakdown"]["tax"]
        assert t["other"] == pytest.approx(b["other"], abs=0.01)
    both, asset = runs["both"][2029], runs["asset_only"][2029]
    assert both["other_asset_sale_stacked_tax"] + both["note_gain_stacked_tax"] >= asset["other_asset_sale_stacked_tax"]


def test_final_year_uses_final_principal(runs):
    row = runs["taxed"][LAST]
    assert row["note_gain_st"] == pytest.approx(10_679, abs=1)
    assert row["note_gain_lt"] == pytest.approx(41_143, abs=1)


def test_blank_inputs_and_years_without_principal_change_nothing(runs):
    for year in (FIRST - 1, LAST + 1):
        assert runs["taxed"][year]["total_tax"] == pytest.approx(runs["untaxed"][year]["total_tax"])
        assert "note_gain_st" not in runs["taxed"][year]
    assert "note_gain_st" not in runs["untaxed"][2028]


def test_same_year_asset_sale_and_note_gain_are_split(runs):
    both, asset = runs["both"][2029], runs["asset_only"][2029]
    assert both["other_asset_sale_ordinary_gain"] == pytest.approx(asset["other_asset_sale_ordinary_gain"])
    assert both["note_gain_st"] == pytest.approx(10_671, abs=1)
    stacked = both["other_asset_sale_ordinary_gain"] + both["note_gain_st"]
    total = both["other_asset_sale_stacked_tax"] + both["note_gain_stacked_tax"]
    assert both["note_gain_stacked_tax"] == pytest.approx(total * both["note_gain_st"] / stacked, rel=1e-6)
    assert both["cashflow_breakdown"]["tax"]["other_asset_sale"] == pytest.approx(both["other_asset_sale_stacked_tax"])
    assert sum(both["cashflow_breakdown"]["tax"].values()) == pytest.approx(both["total_tax"], abs=0.01)
