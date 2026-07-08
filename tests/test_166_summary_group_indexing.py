"""Lock in the projection behavior for a summary-level group budget.

A group budgeted at the Summary level (e.g. Travel = $25,000/yr) must:
  * drive every future year at that amount indexed for inflation
    ($25,000 -> $25,625 in the next year at 2.5%), and
  * in the present year show the higher of the budget and the client's
    annualized run rate (the current-year top-up computed by the YTD blend).

These are exercised through the real projection engine (parse_client + project,
the same pattern as test_119) so a regression in the resolver span, the engine's
inflation indexing, or the current-year top-up hook is caught end to end.
"""
from pathlib import Path

from src.data_io import load_csv, parse_client
from src.planning_engines import project
from src.spending_budget_resolver import resolve_spending_inputs

ROOT = Path(__file__).resolve().parents[1]

TRAVEL_SUMMARY = 25000.0


def _write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_summary_group_budget_resolves_to_full_window_extra(tmp_path):
    """A Summary-mode group budget must resolve to a single recurring extra that
    spans the entire plan window, so the engine has an amount to index every
    future year (rather than a one-off that vanishes after the current year)."""
    _write(tmp_path / "input/client_spending_taxonomy.csv",
           "tracking_type,group,category_id,label,origin,status,notes\n"
           "Travel,Travel,travel_vacation,Travel & Vacation,transaction,active,\n")
    _write(tmp_path / "input/client_spending_aliases.csv",
           "match_value,match_field,exact,priority,category_id,source\n")
    _write(tmp_path / "input/client_spending_budget.csv",
           "kind,key,label,annual_budget,start_year,end_year,one_time_year,notes,_mode,line_section,line_mode\n"
           "group,Travel::Travel,Travel,25000,,,,,summary,,\n")
    out = resolve_spending_inputs(tmp_path, config={"plan_start": 2026, "plan_end": 2030})
    travel = [e for e in out["recurring_extras"] if e.get("tracking_type") == "Travel"]
    assert len(travel) == 1
    assert travel[0]["amount"] == TRAVEL_SUMMARY
    assert int(travel[0]["start_year"]) == 2026
    assert int(travel[0]["end_year"]) == 2030


def _config_with_travel_summary():
    cfg = parse_client(load_csv(ROOT / "input" / "client_data.csv"), "")
    ps = int(cfg["plan_start"])
    # A summary Travel group resolves to a single recurring extra spanning the
    # whole plan window (see resolve_spending_inputs). Model that directly and
    # clear the legacy vacation/home-project drivers so rec_extra is Travel only.
    cfg["recurring_extras"] = [{
        "type": "Travel", "amount": TRAVEL_SUMMARY,
        "start_year": ps, "end_year": int(cfg["plan_end"]),
        "tracking_type": "Travel", "is_home_improvement": False,
    }]
    cfg["vac"] = 0.0
    cfg["vac_end"] = ps - 1
    cfg["home_proj"] = 0.0
    cfg["home_proj_end"] = ps - 1
    return cfg, ps


def test_summary_group_amount_indexes_for_inflation_in_future_years():
    cfg, ps = _config_with_travel_summary()
    inf = float(cfg.get("inf") or 0.0)
    rows = project(cfg)
    by_year = {int(r["year"]): float(r["rec_extra"]) for r in rows}

    # Present year is the un-inflated budget (no top-up injected here).
    assert abs(by_year[ps] - TRAVEL_SUMMARY) < 0.01
    # Each following year compounds the group amount by the inflation rate.
    for n in (1, 2, 3):
        expected = TRAVEL_SUMMARY * (1.0 + inf) ** n
        assert abs(by_year[ps + n] - expected) < 0.01, (
            f"year {ps + n}: {by_year[ps + n]} != indexed {expected}")


def test_present_year_uses_higher_of_budget_and_run_rate_topup():
    cfg, ps = _config_with_travel_summary()
    inf = float(cfg.get("inf") or 0.0)
    # The YTD blend emits this current-year-only top-up when the annualized
    # actual exceeds the budget (annualized $31,328 run rate vs $25,000 budget).
    topup = 6328.70
    cfg["ytd_blend_extra_topup"] = {ps: topup}
    rows = project(cfg)
    by_year = {int(r["year"]): float(r["rec_extra"]) for r in rows}

    # Present year = max(budget, run rate) = budget + top-up.
    assert abs(by_year[ps] - (TRAVEL_SUMMARY + topup)) < 0.01
    # The top-up is current-year only: the next year is still the indexed budget,
    # not carrying the run-rate bump forward.
    assert abs(by_year[ps + 1] - TRAVEL_SUMMARY * (1.0 + inf)) < 0.01
