"""Regression test: the Results Explorer's 'Cash Flow -- Income & Portfolio
Draws' chart silently dropped every portfolio-draw series (Trust/HSA/Roth/
IRA/HELOC Draw) for any household with 10+ non-zero income-stream series,
because results_model.py's _compact_series() truncated by list position
(series[:max_series]) rather than by magnitude -- and the chart lists all 5
draw series after the 10 income streams. This also understated each bar's
displayed total by the dropped dollars, since truncation discarded values
instead of folding them into an "Other" bucket.
"""
from pathlib import Path

from src.data_io import load_csv, parse_client
from src.plan_config import ensure_engine_config
from src.planning_engines import project
from src.results_model import _compact_series, _chart_page
from tests.golden_pricing import FROZEN_GOLDEN_MASTER_PRICES, frozen_holdings_prices

ROOT = Path(__file__).resolve().parents[1]


def sample_config():
    data = load_csv(ROOT / 'input' / 'client_data.csv')
    c = parse_client(data, '')
    return ensure_engine_config(c, source='test')


def test_compact_series_keeps_largest_not_first_n():
    # 10 "big" series (distinct magnitudes, all listed BEFORE the tiny one --
    # the bug this guards against truncated by list position, so a tiny
    # series listed first used to survive while a huge one listed later
    # vanished) plus one tiny series. Only the two smallest by magnitude
    # (max_series - 1 = 9 kept, so 11 - 9 = 2 dropped) should be folded away.
    years = [2026, 2027, 2028]
    series = [{"label": f"big_{i}", "values": [1000 + i, 1000 + i, 1000 + i]} for i in range(10)]
    series.append({"label": "small_but_real", "values": [1, 1, 1]})
    _, out, compacted = _compact_series(years, series, max_series=10)
    assert compacted
    assert len(out) == 10
    labels = {s["label"] for s in out}
    # The small series must survive by folding into "Other", not by silently
    # disappearing -- it must not still be present under its own label once
    # it's below the cutoff, and "Other" must exist to carry its dollars.
    assert "small_but_real" not in labels
    assert "Other" in labels
    # The single largest series (big_9, magnitude 1009) must never be the one
    # dropped just because of where it sits in the input list.
    assert "big_9" in labels


def test_compact_series_preserves_per_year_totals():
    years = list(range(5))
    series = [{"label": f"s{i}", "values": [i * 10 + y for y in range(5)]} for i in range(14)]
    original_totals = [sum(s["values"][y] for s in series) for y in range(5)]
    _, out, compacted = _compact_series(years, series, max_series=10)
    assert compacted
    assert len(out) == 10
    new_totals = [sum(s["values"][y] for s in out) for y in range(5)]
    assert new_totals == original_totals


def test_compact_series_no_truncation_when_within_limit():
    years = [2026, 2027]
    series = [{"label": f"s{i}", "values": [5, 5]} for i in range(10)]
    _, out, compacted = _compact_series(years, series, max_series=10)
    assert not compacted
    assert len(out) == 10
    assert all(s["label"] != "Other" for s in out)


def test_income_and_portfolio_draws_chart_keeps_draw_series_on_real_plan():
    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        c = sample_config()
        rows = project(c)
    page, _compacted = _chart_page(c, rows, None)
    chart = next(ch for ch in page["charts"] if "Portfolio Draws" in ch["title"])
    labels = {s["label"] for s in chart["series"]}
    draw_labels = {"Trust Draw", "HSA Draw", "Roth Draw", "IRA Draw", "HELOC Draw"}
    # At least one real draw series (or the Other bucket absorbing it) must
    # survive -- not silently vanish because 10 income streams came first.
    assert (labels & draw_labels) or "Other" in labels


def test_income_and_portfolio_draws_bar_totals_are_not_understated():
    """The chart's displayed per-year total must equal the real sum of every
    series that has a non-zero value that year -- compaction must never
    discard dollars, only relabel them as 'Other'."""
    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        c = sample_config()
        rows = project(c)
    page, _compacted = _chart_page(c, rows, None)
    chart = next(ch for ch in page["charts"] if "Portfolio Draws" in ch["title"])
    n_years = len(chart["x"])
    displayed_totals = [sum(s["values"][i] for s in chart["series"]) for i in range(n_years)]
    real_totals = []
    # Recompute the true per-row total directly from engine rows (uncompacted
    # x-axis order matches rows when the horizon is short enough to skip
    # point-sampling; guard on that rather than assuming it).
    if len(rows) == n_years:
        for r in rows:
            streams = (r.get('earned', 0) + r.get('h_ss', 0) + r.get('w_ss', 0) + r.get('pension', 0)
                       + r.get('wife_single_ann', 0) + r.get('wife_joint_ann', 0)
                       + r.get('h_single_ann', 0) + r.get('h_joint_ann', 0)
                       + r.get('note_princ', 0) + r.get('note_int', 0) + r.get('rmd_total', 0))
            draws = (max(0, r.get('trust_wd', 0)) + max(0, r.get('hsa_wd', 0)) + max(0, r.get('roth_wd', 0))
                     + max(0, r.get('ira_wd', 0)) + max(0, r.get('heloc_draw', 0)))
            real_totals.append(round(streams + draws))
        # Tolerance covers legitimate per-series rounding (each series is
        # individually rounded before summing) accumulating across ~15
        # series -- not a proxy for the multi-thousand-dollar gaps the bug
        # itself produced by dropping whole series.
        for displayed, real in zip(displayed_totals, real_totals):
            assert abs(displayed - real) <= 10, f"displayed={displayed} real={real}"


def test_efficient_frontier_chart_present_in_ui_results_model():
    """The Results Explorer's chart dashboard never included an Efficient
    Frontier chart at all -- it existed only in the Excel workbook
    (sheets_projection_charts.py). Confirms the UI-facing model now carries
    equivalent scatter data: the frontier curve plus portfolio markers."""
    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        c = sample_config()
        rows = project(c)
    page, _compacted = _chart_page(c, rows, None)
    chart = next((ch for ch in page["charts"] if "Efficient Frontier" in ch["title"]), None)
    assert chart is not None, "Efficient Frontier chart missing from UI results model"
    assert chart["type"] == "scatter"
    labels = {s["label"] for s in chart["series"]}
    assert "Efficient Frontier" in labels
    frontier = next(s for s in chart["series"] if s["label"] == "Efficient Frontier")
    assert len(frontier["points"]) >= 2
    for pt in frontier["points"]:
        assert "x" in pt and "y" in pt


def test_income_and_spending_bars_reconcile_via_surplus_series():
    """The two cash-flow bars for the same year should carry the same total:
    Income & Portfolio Draws vs Spending & Taxes + Surplus (Reinvested).
    Guaranteed income routinely exceeds spending need in a given year -- the
    engine sweeps the excess into savings rather than discarding it
    (deterministic_engine.py's `row['surplus']`) -- so the Spending & Taxes
    bar must include that surplus as its own series for the two bars to
    match, instead of leaving an unexplained gap between them."""
    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        c = sample_config()
        rows = project(c)
    page, _compacted = _chart_page(c, rows, None)
    inc_chart = next(ch for ch in page["charts"] if "Portfolio Draws" in ch["title"])
    exp_chart = next(ch for ch in page["charts"] if "Spending & Taxes" in ch["title"])
    exp_labels = {s["label"] for s in exp_chart["series"]}
    assert "Surplus (Reinvested)" in exp_labels
    n_years = min(len(inc_chart["x"]), len(exp_chart["x"]))
    inc_totals = [sum(s["values"][i] for s in inc_chart["series"]) for i in range(n_years)]
    exp_totals = [sum(s["values"][i] for s in exp_chart["series"]) for i in range(n_years)]
    for i, (inc_t, exp_t) in enumerate(zip(inc_totals, exp_totals)):
        assert abs(inc_t - exp_t) <= 10, f"year index {i}: income={inc_t} expense+surplus={exp_t}"
