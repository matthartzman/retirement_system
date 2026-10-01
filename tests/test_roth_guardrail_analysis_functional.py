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
        assert gid in ("irmaa", "ltcg", "niit")
        assert set(w) == {"extra_converted", "lifetime_tax_pv_change", "terminal_wealth_pv_change", "lcv_change"}
    assert out["settings"]["switches"].keys() == {"irmaa", "ltcg", "niit"}
