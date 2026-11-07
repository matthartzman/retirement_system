"""Current Snapshot: alternatives (start-up equity, art ...) linked to a Planner Other Asset taxed on gains.

The non-liquid row's gain if sold today (value minus the item's basis) is taxed at the LTCG rate, a collectible's
at min(ordinary, 28%) but never below LTCG, and a gain held a year or less as ordinary income. The link is the
reconcile page's match (other_asset_links), else the item name the row's name starts with. An explicit Accounts &
Sources / settings treatment still wins."""
from datetime import date

import pytest

from financial_trends_reporter import live_snapshot as ls
from tests.test_live_snapshot_compute_unit import MONARCH, TAX, _compute, _row

ART = 5000.0  # the fixture's "Art" Monarch row


def _item(name, treatment, basis="1000", purchase="2020-01-01", section="Other Asset 1"):
    return {"section": section, "name": name, "type": "Art", "basis": float(basis or 0), "basis_entered": bool(basis),
            "tax_treatment": treatment, "purchase_date": purchase}


def _cfg(*items):
    return {"other_asset_items": list(items)}


def test_collectible_gain_taxed_at_min_ordinary_and_28_percent():
    out = _compute(planner_cfg=_cfg(_item("Art", "collectible_gains")))
    assert _row(out["non_liquid"]["rows"], "Art")["tax_treatment"] == "collectible_gains"
    tax = out["tax"]
    [alt] = tax["alternatives_rows"]
    assert (alt["kind"], alt["gain"], alt["long_term"]) == ("collectible", ART - 1000, True)
    want = max(tax["alternatives_ltcg_rate"], min(tax["pre_tax_rate"], 0.28))
    assert tax["alternatives_collectible_rate"] == pytest.approx(want, abs=1e-4)
    assert tax["alternatives_tax"] == pytest.approx((ART - 1000) * want, rel=1e-3)
    base = _compute(planner_cfg=_cfg())["tax"]["total"]
    assert tax["total"] == pytest.approx(base + tax["alternatives_tax"], abs=0.02)
    # Flat fallback: ordinary 25% is under the 28% cap, so the collectible pays 25%.
    assert tax["flat_total"] == pytest.approx(_compute()["tax"]["flat_total"] + (ART - 1000) * 0.25)


def test_regular_gain_at_ltcg_and_short_term_as_ordinary():
    ltcg = _compute(planner_cfg=_cfg(_item("Art", "gains")))["tax"]
    assert ltcg["alternatives_tax"] == pytest.approx((ART - 1000) * ltcg["alternatives_ltcg_rate"], rel=1e-3)
    assert ltcg["flat_total"] == pytest.approx(_compute()["tax"]["flat_total"] + (ART - 1000) * 0.15)
    short = _compute(planner_cfg=_cfg(_item("Art", "gains", purchase="2026-06-01")))["tax"]
    assert short["alternatives_rows"][0]["kind"] == "ordinary" and short["alternatives_tax"] == 0
    assert short["flat_total"] == pytest.approx(_compute()["tax"]["flat_total"] + (ART - 1000) * 0.25)


def test_reconcile_link_beats_name_and_not_taxed_items_are_left_alone():
    linked = _item("Masterworks", "collectible_gains", section="Other Asset 4")
    rates = {**TAX, "other_asset_links": {"Art": "Other Asset 4"}}
    out = _compute(planner_cfg=_cfg(_item("Other", "none", section="Other Asset 2"), linked), tax_rates=rates)
    assert out["tax"]["alternatives_rows"][0]["item"] == "Masterworks"
    none = _compute(planner_cfg=_cfg(_item("Art", "none")))
    assert _row(none["non_liquid"]["rows"], "Art")["tax_treatment"] == "none"
    assert none["tax"]["alternatives_rows"] == [] and none["tax"]["alternatives_tax"] == 0


def test_explicit_accounts_and_sources_treatment_wins():
    rates = {**TAX, "non_liquid_tax": {"Art": "none"}}
    out = _compute(planner_cfg=_cfg(_item("Art", "collectible_gains")), tax_rates=rates)
    assert out["tax"]["alternatives_rows"] == []


def test_missing_basis_taxes_the_whole_value_and_is_flagged():
    [alt] = _compute(planner_cfg=_cfg(_item("Art", "gains", basis="", purchase="")))["tax"]["alternatives_rows"]
    assert (alt["gain"], alt["basis_missing"], alt["purchase_missing"], alt["long_term"]) == (ART, True, True, True)


def test_other_asset_for_prefers_the_longest_name_prefix():
    items = [_item("Art", "gains"), _item("Art Fund", "gains", section="Other Asset 2")]
    assert ls.other_asset_for("Art Fund 2023", None, items)["section"] == "Other Asset 2"
    assert ls.other_asset_for("Car", None, items) is None


def test_alternative_gain_holding_period_uses_today():
    item = _item("x", "gains", purchase="2025-10-28")
    assert not ls.alternative_gain(2000, item, date(2026, 10, 28))["long_term"]
    assert ls.alternative_gain(2000, item, date(2026, 10, 29))["long_term"]
