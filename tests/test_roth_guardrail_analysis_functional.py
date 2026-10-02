"""Roth guardrail panel data: every sized cap is exposed per year, the LTCG band
setting is honored, and the what-if rerun reports measured (not assumed) changes."""
import json
from pathlib import Path

from conftest import TEST_INPUT_DIR
from src.data_io import load_csv, parse_client
from src.planning_engines import project, roth_guardrail_analysis, roth_guardrail_id
from test_roth_ltcg_niit_guardrails import _plan, _roth_ltcg_thresholds_base


def test_guardrail_ids_are_stable():
    assert roth_guardrail_id("32% bracket") == "bracket"
    assert roth_guardrail_id("Tier 2") == "irmaa"
    assert roth_guardrail_id("LTCG rate tier") == "ltcg"
    assert roth_guardrail_id("NIIT threshold") == "niit"
    assert roth_guardrail_id("Annual IRA percentage cap") == "pct"
    assert roth_guardrail_id("IRA balance") == "balance"


def test_plan_exposes_all_sized_caps_not_just_two():
    _c, plan = _plan({'roth_niit_cap': True}, portfolio_qualified=200_000.0, portfolio_ordinary=20_000.0)
    caps = json.loads(plan.guardrail_caps)
    ids = [c["id"] for c in caps]
    assert {"bracket", "ltcg", "niit", "pct", "balance"} <= set(ids)
    assert [c["cap"] for c in caps] == sorted(c["cap"] for c in caps)
    assert plan.as_row_fields()["conv_guardrail_caps"] == plan.guardrail_caps


def test_ltcg_band_named_zero_skips_when_income_already_past_it():
    c, plan = _plan({'roth_niit_cap': False, 'roth_ltcg_band': '0%'}, portfolio_qualified=200_000.0)
    top0, _top15 = _roth_ltcg_thresholds_base(c, 'MFJ')
    assert plan.pre_agi > top0
    assert plan.binding_limit != 'LTCG rate tier'


def test_ltcg_band_named_fifteen_caps_at_fifteen_top():
    c, plan = _plan({'roth_niit_cap': False, 'roth_ltcg_band': '15%'}, portfolio_qualified=200_000.0)
    _top0, top15 = _roth_ltcg_thresholds_base(c, 'MFJ')
    assert plan.binding_limit == 'LTCG rate tier'
    assert plan.amount == top15 - plan.pre_agi


def test_full_pipeline_analysis_reports_measured_whatif():
    c = parse_client(load_csv(TEST_INPUT_DIR / "client_data.csv"), "")
    c["roth_policy"] = "fill_to_bracket"
    c["roth_target_rate"] = 0.24
    c["plan_start"] = 2026
    c["forced_roth"] = {}
    rows = project(c)
    out = roth_guardrail_analysis(c, rows)
    assert out and out["years"]
    first = out["years"][0]
    assert first["caps"] and all({"id", "name", "cap"} <= set(x) for x in first["caps"])
    for gid, w in out["whatif"].items():
        assert gid in ("bracket", "aca", "irmaa", "ltcg", "niit")
        assert set(w) == {"extra_converted", "lifetime_tax_pv_change", "terminal_wealth_pv_change", "lcv_change"}
    assert out["settings"]["switches"].keys() == {"bracket", "aca", "irmaa", "ltcg", "niit"}


def test_forced_conversion_year_is_listed_even_with_no_caps():
    c = parse_client(load_csv(TEST_INPUT_DIR / "client_data.csv"), "")
    out = roth_guardrail_analysis(c, project(c))
    first = out["years"][0]
    assert first["forced"] is True
    assert first["amount"] == 125000.0


def test_bracket_guardrail_off_removes_the_bracket_cap_and_sizes_the_rest():
    _c, on = _plan({'roth_niit_cap': False, 'roth_ltcg_cap': False})
    _c, off = _plan({'roth_niit_cap': False, 'roth_ltcg_cap': False, 'roth_bracket_cap': False})
    assert "bracket" in [c["id"] for c in json.loads(on.guardrail_caps)]
    off_ids = [c["id"] for c in json.loads(off.guardrail_caps)]
    assert "bracket" not in off_ids and "pct" in off_ids
    assert off.amount >= on.amount


def test_aca_guardrail_off_drops_the_aca_cap_in_a_bridge_year():
    kw = {'aca_bridge_people': 1}
    base = {'roth_niit_cap': False, 'roth_ltcg_cap': False, 'aca_ptc_enabled': True}
    _c, on = _plan(base, **kw)
    _c, off = _plan({**base, 'roth_aca_cap': False}, **kw)
    assert "aca" in [c["id"] for c in json.loads(on.guardrail_caps)]
    assert "aca" not in [c["id"] for c in json.loads(off.guardrail_caps)]


def test_a_year_with_no_room_under_the_limits_is_still_listed_with_its_caps():
    """After a forced conversion is deleted, that year used to vanish from the panel
    (nothing was sized because the bracket had no room). It must stay selectable,
    show its caps, and convert nothing."""
    c = parse_client(load_csv(TEST_INPUT_DIR / "client_data.csv"), "")
    c["forced_roth"] = {}
    c["forced_roth_accounts"] = {}
    out = roth_guardrail_analysis(c, project(c))
    first = out["years"][0]
    assert first["year"] == c["plan_start"]
    assert first["forced"] is False
    assert first["amount"] == 0
    assert first["caps"], "caps should be sized even when no conversion fits"
