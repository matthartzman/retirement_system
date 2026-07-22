from __future__ import annotations

"""Semantic Results Explorer model for v10.

The Results Explorer should not reverse-engineer Excel formatting to decide
what users see.  This module emits UI-native result pages from the same
projection artifacts that feed the workbook.  The workbook remains downloadable
and older workbooks still have an Excel-parser fallback, but new builds write a
`results_explorer_model.json` sidecar that the browser can consume directly.
"""

from datetime import datetime, UTC
import json
from pathlib import Path
from typing import Any, Iterable

from .version import VERSION
from .person_labels import member_nick

RESULTS_MODEL_FILENAME = "results_explorer_model.json"
RESULTS_MODEL_SCHEMA = "results_model_v10"


def _n(value: Any) -> float:
    try:
        if value in (None, ""):
            return 0.0
        return float(value)
    except Exception:
        return 0.0


def _int(value: Any) -> int:
    try:
        return int(round(float(value)))
    except Exception:
        return 0


def _row_cashflow_breakdown(r: dict[str, Any]) -> dict[str, Any]:
    """Return the engine's canonical cash-flow breakdown for a projection row.

    The deterministic engine attaches ``row['cashflow_breakdown']`` (the single
    source of truth shared by build_sheet6, build_sheet8 and this module's
    cash-flow page + chart page). This accessor returns it verbatim, and only
    reconstructs an equivalent dict for the rare row that was not produced by
    the full engine (e.g. a hand-built synthetic row in a test), so the UI never
    crashes and still reconciles. See
    tests/test_cashflow_breakdown_single_source_of_truth.py.
    """
    bd = r.get('cashflow_breakdown')
    if bd:
        return bd
    home_sale = _n(r.get('home_sale_tax'))
    ltcg = _n(r.get('ltcg_tax'))
    return {
        'income': {
            'earned': _n(r.get('earned')), 'h_ss': _n(r.get('h_ss')), 'w_ss': _n(r.get('w_ss')),
            'pension': _n(r.get('pension')), 'wife_single_ann': _n(r.get('wife_single_ann')),
            'wife_joint_ann': _n(r.get('wife_joint_ann')), 'h_single_ann': _n(r.get('h_single_ann')),
            'h_joint_ann': _n(r.get('h_joint_ann')),
            'note_pi': _n(r.get('note_princ')) + _n(r.get('note_int')), 'rmd_total': _n(r.get('rmd_total')),
        },
        'draws': {
            'trust_wd': _n(r.get('h_trust_wd')) + _n(r.get('w_trust_wd')), 'hsa_wd': _n(r.get('hsa_wd')),
            'roth_wd': _n(r.get('h_roth_wd')) + _n(r.get('w_roth_wd')),
            'ira_elective': _n(r.get('h_ira_elective')) + _n(r.get('w_ira_elective')),
            'heloc_draw': _n(r.get('heloc_draw')),
        },
        'expense': {
            'spend_base': _n(r.get('spend_base_yr')), 'mortgage': _n(r.get('mortgage')),
            'rent': _n(r.get('rent_yr')), 'housing_operating': _n(r.get('housing_operating_yr')),
            'wellness': _n(r.get('wellness_base_yr')) + _n(r.get('wellness_shock_yr')) + _n(r.get('ltc_prem_yr')),
            'travel': _n(r.get('rec_extra')), 'other_lump': _n(r.get('lump')),
            'heloc_pai': _n(r.get('heloc_interest')) + _n(r.get('heloc_repayment_principal')),
            'other_cash_need': _n(r.get('other_cash_need_yr')),
        },
        'tax': {
            'federal': _n(r.get('fed_tax')), 'state': _n(r.get('state_tax')), 'niit': _n(r.get('niit')),
            'irmaa': _n(r.get('irmaa')), 'payroll': _n(r.get('payroll_tax')), 'home_sale': home_sale,
            'ltcg': max(0.0, ltcg - home_sale), 'tlh_credit': 0.0, 'other': 0.0,
        },
        'surplus': _n(r.get('surplus')), 'unfunded_gap': _n(r.get('unfunded_gap')),
    }


def _json_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (int, float, bool, str)):
        return value
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    return str(value)


def _display(value: Any, kind: str = "text") -> str:
    if value in (None, ""):
        return ""
    if kind == "currency":
        n = _n(value)
        return ("-" if n < 0 else "") + "$" + f"{round(abs(n) / 1000):,}" + "K"
    if kind == "percent":
        n = _n(value)
        pct = n * 100 if abs(n) <= 1 else n
        return f"{pct:.0f}%"
    if kind in {"year", "integer"}:
        return str(_int(value))
    if kind == "number":
        n = _n(value)
        if float(n).is_integer():
            return str(int(n))
        return f"{n:.6f}".rstrip("0").rstrip(".")
    return str(value)


def cell(value: Any, kind: str = "text") -> dict[str, Any]:
    return {"value": _json_value(value), "display": _display(value, kind), "kind": kind}


def row(values: Iterable[tuple[Any, str] | Any]) -> dict[str, Any]:
    cells = []
    for item in values:
        if isinstance(item, tuple):
            value, kind = item
        else:
            value, kind = item, "text"
        cells.append(cell(value, kind))
    return {"cells": cells}


def _section(title: str, rows: list[dict[str, Any]], *, column_groups: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    max_cols = max((len(r.get("cells") or []) for r in rows), default=0)
    out = {
        "title": title,
        "row_count": max(0, len(rows) - 2 if len(rows) > 2 else len(rows)),
        "rows": rows,
        "source": "semantic_results_model",
    }
    if column_groups:
        out["column_groups"] = column_groups
    out["column_count"] = max_cols
    return out


def _page(name: str, category: str, sections: list[dict[str, Any]], *, kind: str = "table", charts: list[dict[str, Any]] | None = None, note: str = "") -> dict[str, Any]:
    if kind == "chart_dashboard":
        return {
            "name": name,
            "display_name": _clean_page_name(name),
            "category": category,
            "kind": kind,
            "source": "semantic_results_model",
            "row_count": len(charts or []),
            "column_count": 0,
            "section_count": len(charts or []),
            "chart_count": len(charts or []),
            "charts": charts or [],
            "chart_note": note or "Chart Dashboard is rendered from the shared semantic results model. Chart source tables are not displayed.",
            "loaded": True,
            "preview": False,
            "truncated": False,
        }
    row_count = sum(s.get("row_count", len(s.get("rows") or [])) for s in sections)
    col_count = max((s.get("column_count", 0) for s in sections), default=0)
    return {
        "name": name,
        "display_name": _clean_page_name(name),
        "category": category,
        "kind": kind,
        "source": "semantic_results_model",
        "row_count": row_count,
        "column_count": col_count,
        "section_count": len(sections),
        "sections": sections,
        "loaded": True,
        "preview": False,
        "truncated": False,
    }


def _clean_page_name(name: str) -> str:
    import re
    return re.sub(r"^\s*\d+[A-Za-z]?\.\s*", "", str(name or "Results")).strip() or "Results"


def _result_top_level_category(page: dict[str, Any]) -> str:
    """Align Results Explorer with the simplified top-level UI structure."""
    raw = f"{page.get('name','')} {page.get('display_name','')} {page.get('category','')}".lower()
    if any(token in raw for token in ["monte carlo", "survivor", "insurance", "ltc", "stress", "scenario", "market-luck", "divorce", "qdro"]):
        return "Stress Tests"
    if any(token in raw for token in ["roth", "optimizer", "asset location", "asset allocation", "social security", "state residency", "s-corp", "llc", "entity", "charitable", "withdrawal strategy", "planning lever", "estate"]):
        return "Strategy"
    if any(token in raw for token in ["configuration", "assumption registry", "diagnostic", "reference", "schema"]):
        return "System Configuration"
    return "Reports"


def _categories_from_pages(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    order = ["Reports", "Strategy", "Stress Tests", "System Configuration", "Other workbook detail"]
    by: dict[str, list[dict[str, Any]]] = {}
    for p in pages:
        cat = _result_top_level_category(p)
        p["category"] = cat
        by.setdefault(cat, []).append({
            "name": p["name"],
            "display_name": p.get("display_name") or _clean_page_name(p["name"]),
            "row_count": p.get("row_count", 0),
            "section_count": p.get("chart_count", p.get("section_count", 0)),
            "chart_count": p.get("chart_count", 0),
            "kind": p.get("kind", "table"),
            "source": p.get("source", "semantic_results_model"),
        })
    cats = []
    for name in order:
        if name in by:
            cats.append({"name": name, "sheets": by[name]})
    for name in sorted(k for k in by if k not in order):
        cats.append({"name": name, "sheets": by[name]})
    return cats


def _projection_years(rows: list[dict[str, Any]]) -> list[int]:
    return [_int(r.get("year")) for r in rows]


def _compact_series(years: list[Any], series: list[dict[str, Any]], max_points: int = 45, max_series: int = 10) -> tuple[list[Any], list[dict[str, Any]], bool]:
    compacted = False
    series = [s for s in series if any(abs(_n(v)) > 1e-9 for v in (s.get("values") or []))]
    if len(series) > max_series:
        # Keep the largest series by total magnitude, not by list position --
        # truncating in definition order silently dropped whichever series
        # happened to be listed last (e.g. every portfolio-draw series on the
        # "Income & Portfolio Draws" chart sits after the 10 income streams,
        # so it vanished from the stacked bar for any household with that many
        # non-zero income streams). Roll the smallest series into "Other" so
        # each bar's stacked total still equals the real sum instead of
        # quietly shedding dollars.
        by_total = sorted(series, key=lambda s: sum(abs(_n(v)) for v in (s.get("values") or [])), reverse=True)
        kept = by_total[: max_series - 1]
        dropped = by_total[max_series - 1 :]
        if dropped:
            other_values = [sum(_n(v) for v in vals) for vals in zip(*[s.get("values") or [] for s in dropped])]
            kept.append({"label": "Other", "values": other_values})
        series = kept
        compacted = True
    if len(years) > max_points:
        step = max(1, int(round(len(years) / max_points)))
        idxs = list(range(0, len(years), step))
        if idxs[-1] != len(years) - 1:
            idxs.append(len(years) - 1)
        years = [years[i] for i in idxs]
        series = [{**s, "values": [(s.get("values") or [])[i] if i < len(s.get("values") or []) else 0 for i in idxs]} for s in series]
        compacted = True
    return years, series, compacted


def _compact_pie(slices: list[dict[str, Any]], max_slices: int = 12) -> tuple[list[dict[str, Any]], bool]:
    total = sum(max(0.0, _n(s.get("value"))) for s in slices)
    min_material_value = max(1.0, total * 0.000001) if total > 0 else 1.0
    slices = [s for s in slices if _n(s.get("value")) > min_material_value]
    slices.sort(key=lambda s: _n(s.get("value")), reverse=True)
    if len(slices) <= max_slices:
        return slices, False
    keep = slices[: max_slices - 1]
    other = sum(_n(s.get("value")) for s in slices[max_slices - 1 :])
    if other > 0:
        keep.append({"label": "Other", "value": other})
    return keep, True


def _chart_page(c: dict[str, Any], rows: list[dict[str, Any]], mc_data: dict[str, Any] | None) -> tuple[dict[str, Any], bool]:
    years = _projection_years(rows)
    compacted = False
    charts: list[dict[str, Any]] = []

    def add_xy(title: str, typ: str, series: list[dict[str, Any]], unit: str = "currency") -> None:
        nonlocal compacted
        x, s, was = _compact_series(years, series)
        compacted = compacted or was
        if x and s:
            charts.append({"type": typ, "title": title, "unit": unit, "x": x, "series": s})

    add_xy("Net Worth by Component", "stacked_bar", [
        {"label": "Annuities & Pension", "values": [round(_n(r.get("ann_nw"))) for r in rows]},
        {"label": "Pre-Tax IRA/401k", "values": [round(_n(r.get("pretax_nw"))) for r in rows]},
        {"label": "Roth", "values": [round(_n(r.get("roth_nw"))) for r in rows]},
        {"label": "Trust", "values": [round(_n(r.get("trust_nw"))) for r in rows]},
        {"label": "HSA", "values": [round(_n(r.get("hsa_nw"))) for r in rows]},
        {"label": "Home Value", "values": [round(_n(r.get("home_val"))) for r in rows]},
        {"label": "Other Assets", "values": [round(_n(r.get("other_nw")) - _n(r.get("home_equity"))) for r in rows]},
        {"label": "Mortgage", "values": [-round(_n(r.get("mort_bal_yr"))) for r in rows]},
        {"label": "HELOC", "values": [-round(_n(r.get("heloc_liability"))) for r in rows]},
    ])

    # Every series below is sourced from the engine's canonical
    # row['cashflow_breakdown'] (single source of truth shared with the Excel
    # cash-flow sheet build_sheet6 and charts dashboard build_sheet8), so the
    # chart can never itemize a year differently from the worksheet again.
    bds = [_row_cashflow_breakdown(r) for r in rows]

    def _inc_series(sub: str, key: str) -> list[int]:
        return [round(_n(bd[sub].get(key))) for bd in bds]

    def _draw_series(key: str) -> list[int]:
        return [round(max(0, _n(bd['draws'].get(key)))) for bd in bds]

    inc_values = {
        "Earned Income": _inc_series('income', 'earned'),
        f"{member_nick(c, 'member_1')} SS": _inc_series('income', 'h_ss'),
        f"{member_nick(c, 'member_2')} SS": _inc_series('income', 'w_ss'),
        "Pension": _inc_series('income', 'pension'),
        f"{member_nick(c, 'member_2')} Single Ann": _inc_series('income', 'wife_single_ann'),
        f"{member_nick(c, 'member_2')} Joint Ann": _inc_series('income', 'wife_joint_ann'),
        f"{member_nick(c, 'member_1')} Single Ann": _inc_series('income', 'h_single_ann'),
        f"{member_nick(c, 'member_1')} Joint Ann": _inc_series('income', 'h_joint_ann'),
        "Note P+I": _inc_series('income', 'note_pi'),
        "RMD": _inc_series('income', 'rmd_total'),
        "Trust Draw": _draw_series('trust_wd'),
        "HSA Draw": _draw_series('hsa_wd'),
        "Roth Draw": _draw_series('roth_wd'),
        "IRA Draw": _draw_series('ira_elective'),
        "HELOC Draw": _draw_series('heloc_draw'),
    }
    # Unfunded shortfall (usually all-zero): the funding the plan could not
    # raise to meet spending+taxes that year. Placed on the income bar so it
    # reconciles with the taller spending bar in a failed-funding year -- a
    # shortfall is materially different from a surplus, so it gets its own
    # labeled series rather than being silently dropped.
    inc_values["Unfunded Shortfall"] = [round(max(0, _n(bd['unfunded_gap']))) for bd in bds]

    def _exp_series(key: str) -> list[int]:
        return [round(_n(bd['expense'].get(key))) for bd in bds]

    def _tax_series(key: str) -> list[int]:
        return [round(_n(bd['tax'].get(key))) for bd in bds]

    exp_values = {
        "Base Spending": _exp_series('spend_base'),
        "Rec Extras": _exp_series('travel'),
        "Lump Events": _exp_series('other_lump'),
        "Mortgage + RE Tax": _exp_series('mortgage'),
        "Rent": _exp_series('rent'),
        "Housing Operating": _exp_series('housing_operating'),
        "Wellness": _exp_series('wellness'),
        "HELOC P&I": _exp_series('heloc_pai'),
        "Other Cash Need": _exp_series('other_cash_need'),
        "Federal Tax": _tax_series('federal'),
        f"State Tax ({str(c.get('state', ''))[:2]})": _tax_series('state'),
        "NIIT": _tax_series('niit'),
        "Payroll Tax": _tax_series('payroll'),
        "IRMAA": _tax_series('irmaa'),
        "Home Sale Tax": _tax_series('home_sale'),
        # Portfolio LTCG beyond the home-sale portion, plus any tax-loss-harvest
        # ordinary credit and residual tax adjustments, so the itemized tax
        # series partition row['total_tax'] exactly (this slice used to be
        # silently dropped from the chart).
        "LTCG Tax": [round(_n(bd['tax'].get('ltcg')) + _n(bd['tax'].get('tlh_credit')) + _n(bd['tax'].get('other'))) for bd in bds],
    }
    # Authoritative engine surplus (year-end reinvested excess), read verbatim
    # from the breakdown -- NOT a re-derived plug of the chart's own totals.
    # Because every real cash-need component is now itemized above, the two
    # bars still reconcile: income+draws+unfunded == spend+taxes+surplus, using
    # the engine's own surplus/unfunded_gap rather than a chart-local guess.
    exp_values["Surplus (Reinvested)"] = [round(max(0, _n(bd['surplus']))) for bd in bds]

    add_xy("Cash Flow — Income & Portfolio Draws", "stacked_bar", [
        {"label": label, "values": vals} for label, vals in inc_values.items()
    ], unit="currency")

    add_xy("Cash Flow — Spending & Taxes", "stacked_bar", [
        {"label": label, "values": vals} for label, vals in exp_values.items()
    ])

    pct_by_year = (mc_data or {}).get("pct_by_year", {}) or {}
    if pct_by_year:
        add_xy("Net Worth Percentile Bands — Monte Carlo", "line", [
            {"label": "P10", "values": [_n((pct_by_year.get(y) or {}).get(10)) for y in years]},
            {"label": "P25", "values": [_n((pct_by_year.get(y) or {}).get(25)) for y in years]},
            {"label": "P50 Median", "values": [_n((pct_by_year.get(y) or {}).get(50)) for y in years]},
            {"label": "P75", "values": [_n((pct_by_year.get(y) or {}).get(75)) for y in years]},
            {"label": "P90", "values": [_n((pct_by_year.get(y) or {}).get(90)) for y in years]},
        ])

    alloc = c.get("_alloc_chart_data", {}) or {}
    buckets = alloc.get("buckets") or []
    before = alloc.get("before_vals") or []
    after = alloc.get("after_vals") or []
    if buckets:
        slices, was = _compact_pie([{"label": str(b), "value": _n(before[i] if i < len(before) else 0)} for i, b in enumerate(buckets)])
        compacted = compacted or was
        if slices:
            charts.append({"type": "pie", "title": "Current Portfolio Allocation", "unit": "currency", "slices": slices})
        slices, was = _compact_pie([{"label": str(b), "value": _n(after[i] if i < len(after) else 0)} for i, b in enumerate(buckets)])
        compacted = compacted or was
        if slices:
            charts.append({"type": "pie", "title": "Target Portfolio Allocation", "unit": "currency", "slices": slices})

    # Efficient Frontier: mirrors sheets_projection_charts.py's Excel scatter
    # chart (volatility vs. expected return), which was never ported to the
    # UI results model -- this chart previously did not exist in the app at
    # all, not just missing/hidden.
    try:
        from . import optimization as _opt
        from . import allocation_policy as _ap
        ef_points = _opt.efficient_frontier(c, n_points=15)
    except Exception:
        ef_points = []
    if ef_points and len(ef_points) >= 2:
        ef_series = [{
            "label": "Efficient Frontier",
            "style": "line",
            "points": [{"x": _n(p.get("volatility")), "y": _n(p.get("return"))} for p in ef_points],
        }]

        def _add_marker(label: str, stats: dict[str, Any] | None) -> None:
            if not stats:
                return
            vol = _n(stats.get("volatility"))
            ret = _n(stats.get("expected_return"))
            ef_series.append({"label": label, "style": "point", "points": [{"x": vol, "y": ret}]})

        try:
            _add_marker("Recommended Portfolio", _opt.allocation_portfolio_stats(c))
        except Exception:
            pass
        try:
            _cur_weights = {bkt: _n(before[i] if i < len(before) else 0) for i, bkt in enumerate(buckets) if bkt in _opt.ASSET_CLASSES}
            _add_marker("Current Portfolio", _opt.portfolio_stats_from_weights(c, _cur_weights) if _cur_weights else None)
        except Exception:
            pass
        try:
            _add_marker("Max Sharpe (Risk-Budgeted)", _opt.allocation_portfolio_stats(c, force_mode=_ap.ALLOCATION_MODE_MAX_SHARPE))
        except Exception:
            pass
        try:
            _add_marker("Pure Tangency", _opt.allocation_portfolio_stats(c, force_mode=_ap.ALLOCATION_MODE_TANGENCY))
        except Exception:
            pass
        charts.append({
            "type": "scatter",
            "title": "Efficient Frontier — Risk vs. Return",
            "unit": "percent",
            "x_label": "Volatility (Standard Deviation)",
            "y_label": "Expected Return",
            "series": ef_series,
        })

    note = "Chart Dashboard is rendered from the shared v10 semantic results model. Chart source tables are not displayed."
    if compacted:
        note += " Some long series are sampled/limited for browser responsiveness; download the workbook for full Excel chart detail."
    return _page("1E. Charts", "Reports", [], kind="chart_dashboard", charts=charts, note=note), compacted


def _cashflow_page(c: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    group = [
        ("Identifiers", 3), ("Income", 11), ("Tax & RMD", 6), ("Spending", 7),
        ("Portfolio Draws", 16), ("Surplus", 2),
    ]
    group_row = []
    for label, span in group:
        group_row.extend([(label, "text")] + [("", "text")] * (span - 1))
    n1 = member_nick(c, 'member_1')
    n2 = member_nick(c, 'member_2')
    headers = [
        ("Year", "text"), (f"{n1} Age", "text"), (f"{n2} Age", "text"),
        ("Earned", "text"), (f"{n1} SS", "text"), (f"{n2} SS", "text"), ("Pension", "text"),
        (f"{n2} Single Ann", "text"), (f"{n2} Joint Ann", "text"), (f"{n1} Single Ann", "text"), (f"{n1} Joint Ann", "text"),
        ("Note P+I", "text"), ("RMD Dist", "text"), ("Σ Income", "text"),
        ("Roth Conv", "text"), ("AGI", "text"), ("Taxable Inc", "text"), ("Fed Tax", "text"), ("State Tax", "text"), ("NIIT", "text"),
        ("Spend Base", "text"), ("Rec Extra", "text"), ("Lump", "text"), ("Mortgage + RE Tax", "text"), ("Rent", "text"), ("HELOC P&I", "text"), ("Σ Spend", "text"),
        (f"{n1} Trust WD", "text"), (f"{n2} Trust WD", "text"), ("Σ Trust", "text"), ("HSA WD", "text"),
        (f"{n1} Roth WD", "text"), (f"{n2} Roth WD", "text"), ("Σ Roth", "text"),
        (f"{n1} IRA RMD", "text"), (f"{n1} IRA Elec", "text"), (f"{n1} IRA Conv", "text"), (f"{n1} IRA Outflow", "text"),
        (f"{n2} IRA RMD", "text"), (f"{n2} IRA Elec", "text"), (f"{n2} IRA Conv", "text"), (f"{n2} IRA Outflow", "text"),
        ("HELOC Draw", "text"), ("Σ Cash Draws", "text"), ("Surplus", "text"), ("NW Check", "text"),
    ]
    data_rows = [row(group_row), row(headers)]
    for r in rows:
        # Σ Income, HELOC P&I, Σ Spend (this page's narrower spend definition:
        # only the columns actually displayed here) and the Surplus column all
        # come from the engine's canonical row['cashflow_breakdown'], so this
        # page and build_sheet6 can never disagree on income or surplus again.
        bd = _row_cashflow_breakdown(r)
        _bi = bd['income']; _be = bd['expense']
        inc_total = sum(_bi.values())
        heloc_pai = _be['heloc_pai']
        spend_total = (_be['spend_base'] + _be['travel'] + _be['other_lump']
                       + _be['mortgage'] + _be['rent'] + heloc_pai)
        surplus_val = bd['surplus']
        trust_total = _n(r.get('h_trust_wd')) + _n(r.get('w_trust_wd'))
        roth_total = _n(r.get('h_roth_wd')) + _n(r.get('w_roth_wd'))
        h_ira_cash = _n(r.get('rmd_h')) + _n(r.get('h_ira_elective'))
        w_ira_cash = _n(r.get('rmd_w')) + _n(r.get('w_ira_elective'))
        h_ira_total = _n(r.get('h_ira_total_outflow', h_ira_cash + _n(r.get('h_ira_conversion'))))
        w_ira_total = _n(r.get('w_ira_total_outflow', w_ira_cash + _n(r.get('w_ira_conversion'))))
        wd_total = trust_total + _n(r.get('hsa_wd')) + roth_total + h_ira_cash + w_ira_cash + _n(r.get('heloc_draw'))
        data_rows.append(row([
            (r.get('year'), 'year'), (r.get('h_age'), 'integer'), (r.get('w_age'), 'integer'),
            (r.get('earned'), 'currency'), (r.get('h_ss'), 'currency'), (r.get('w_ss'), 'currency'), (r.get('pension'), 'currency'),
            (r.get('wife_single_ann'), 'currency'), (r.get('wife_joint_ann'), 'currency'), (r.get('h_single_ann'), 'currency'), (r.get('h_joint_ann'), 'currency'),
            (_n(r.get('note_princ')) + _n(r.get('note_int')), 'currency'), (r.get('rmd_total'), 'currency'), (inc_total, 'currency'),
            (r.get('roth_conv'), 'currency'), (r.get('agi'), 'currency'), (r.get('taxable_inc'), 'currency'), (r.get('fed_tax'), 'currency'), (r.get('state_tax'), 'currency'), (r.get('niit'), 'currency'),
            (r.get('spend_base_yr'), 'currency'), (r.get('rec_extra'), 'currency'), (r.get('lump'), 'currency'), (r.get('mortgage'), 'currency'), (r.get('rent_yr'), 'currency'), (heloc_pai, 'currency'), (spend_total, 'currency'),
            (r.get('h_trust_wd'), 'currency'), (r.get('w_trust_wd'), 'currency'), (trust_total, 'currency'), (r.get('hsa_wd'), 'currency'),
            (r.get('h_roth_wd'), 'currency'), (r.get('w_roth_wd'), 'currency'), (roth_total, 'currency'),
            (r.get('rmd_h'), 'currency'), (r.get('h_ira_elective'), 'currency'), (r.get('h_ira_conversion'), 'currency'), (h_ira_total, 'currency'),
            (r.get('rmd_w'), 'currency'), (r.get('w_ira_elective'), 'currency'), (r.get('w_ira_conversion'), 'currency'), (w_ira_total, 'currency'),
            (r.get('heloc_draw'), 'currency'), (wd_total, 'currency'), (surplus_val, 'currency'), (r.get('total_nw'), 'currency'),
        ]))
    column_groups = []
    pos = 0
    for label, span in group:
        column_groups.append({"label": label, "start": pos, "end": pos + span - 1})
        pos += span
    return _page("1C. Cash Flow", "Reports", [_section("Cash Flow Projection", data_rows, column_groups=column_groups)])


def _net_worth_page(c: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    # Columns: Year | H Age | W Age | Σ Ann | Σ PreTax | Σ Roth | Σ Trust | HSA | Home Value | Mortgage | HELOC | Home Equity | Σ Other | TOTAL NW
    # Home Value is a gross asset; Mortgage and HELOC are negative liabilities; Home Equity = Home Value - Mortgage - HELOC.
    # TOTAL NW is already computed net (unchanged).
    group_row = row([
        ("Identifiers", "text"), ("", "text"), ("", "text"),
        ("Account balances", "text"), ("", "text"), ("", "text"), ("", "text"), ("", "text"),
        ("Real Estate", "text"), ("", "text"), ("", "text"), ("", "text"),
        ("", "text"), ("", "text"),
    ])
    headers = row([
        ("Year", "text"), (f"{member_nick(c, 'member_1')} Age", "text"), (f"{member_nick(c, 'member_2')} Age", "text"),
        ("Σ Ann", "text"), ("Σ PreTax", "text"), ("Σ Roth", "text"), ("Σ Trust", "text"), ("HSA", "text"),
        ("Home Value", "text"), ("Mortgage", "text"), ("HELOC", "text"), ("Home Equity", "text"),
        ("Σ Other", "text"), ("TOTAL NW", "text"),
    ])
    data = [group_row, headers]
    for r in rows:
        mort = _n(r.get('mort_bal_yr'))
        heloc = _n(r.get('heloc_liability'))
        data.append(row([
            (r.get('year'), 'year'), (r.get('h_age'), 'integer'), (r.get('w_age'), 'integer'),
            (r.get('ann_nw'), 'currency'), (r.get('pretax_nw'), 'currency'),
            (r.get('roth_nw'), 'currency'), (r.get('trust_nw'), 'currency'), (r.get('hsa_nw'), 'currency'),
            (r.get('home_val'), 'currency'), (-mort if mort else 0, 'currency'), (-heloc if heloc else 0, 'currency'),
            (r.get('home_equity'), 'currency'),
            (r.get('other_nw'), 'currency'), (r.get('total_nw'), 'currency'),
        ]))
    return _page("1B. Net Worth", "Reports", [_section("Net Worth Projection", data, column_groups=[
        {"label": "Identifiers", "start": 0, "end": 2},
        {"label": "Account balances", "start": 3, "end": 7},
        {"label": "Real Estate", "start": 8, "end": 11},
        {"label": "Totals", "start": 12, "end": 13},
    ])])


def _lifetime_tax_page(c: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    headers = row([("Year", "text"), ("Filing", "text"), ("AGI", "text"), ("Taxable Income", "text"), ("Roth Conv", "text"), ("Federal", "text"), ("State", "text"), ("NIIT", "text"), ("Total Tax", "text"), ("Effective Rate", "text")])
    data = [row([("Tax projection", "text")]), headers]
    lifetime = 0.0
    for r in rows:
        total = _n(r.get('total_tax'))
        lifetime += total
        agi = _n(r.get('agi'))
        data.append(row([(r.get('year'), 'year'), (r.get('filing_status', c.get('filing_status', 'MFJ')), 'text'), (agi, 'currency'), (r.get('taxable_inc'), 'currency'), (r.get('roth_conv'), 'currency'), (r.get('fed_tax'), 'currency'), (r.get('state_tax'), 'currency'), (r.get('niit'), 'currency'), (total, 'currency'), ((total / agi) if agi else 0, 'percent')]))
    data.append(row([("Lifetime Total Tax", "text"), ("", "text"), ("", "text"), ("", "text"), ("", "text"), ("", "text"), ("", "text"), ("", "text"), (lifetime, "currency"), ("", "text")]))
    return _page("1F. Lifetime Taxes", "Reports", [_section("Lifetime Tax", data)])


def _asset_allocation_page(c: dict[str, Any]) -> dict[str, Any]:
    alloc = c.get("_alloc_chart_data", {}) or {}
    buckets = alloc.get("buckets") or []
    before = alloc.get("before_vals") or []
    after = alloc.get("after_vals") or []
    rows = [row([("Asset class", "text"), ("Current value", "text"), ("Target value", "text"), ("Current share", "text"), ("Target share", "text")])]
    total_before = sum(_n(x) for x in before) or 1.0
    total_after = sum(_n(x) for x in after) or 1.0
    if buckets:
        for i, b in enumerate(buckets):
            bv = _n(before[i] if i < len(before) else 0)
            av = _n(after[i] if i < len(after) else 0)
            rows.append(row([(b, "text"), (bv, "currency"), (av, "currency"), (bv / total_before, "percent"), (av / total_after, "percent")]))
    else:
        rows.append(row([("No allocation chart data available in the semantic model.", "text")]))
    return _page("2B. Asset Allocation", "Reports", [_section("Asset Allocation", rows)])


def _executive_summary_page(c: dict[str, Any], rows: list[dict[str, Any]], mc_data: dict[str, Any] | None) -> dict[str, Any]:
    first = rows[0] if rows else {}
    terminal = rows[-1] if rows else {}
    summary = [
        ("Household", f"{c.get('h_name','Client')} & {c.get('w_name','')}", "text"),
        ("Plan horizon", f"{c.get('plan_start')}–{c.get('plan_end')}", "text"),
        ("Starting net worth", _n(first.get('total_nw')), "currency"),
        ("Terminal net worth", _n(terminal.get('total_nw')), "currency"),
        ("Monte Carlo success", _n((mc_data or {}).get('success_rate')), "percent"),
        ("Lifetime tax", sum(_n(r.get('total_tax')) for r in rows), "currency"),
        ("Total Roth conversions", sum(_n(r.get('roth_conv')) for r in rows), "currency"),
    ]
    data = [row([("Metric", "text"), ("Value", "text")])]
    for label, value, kind in summary:
        data.append(row([(label, "text"), (value, kind)]))
    return _page("1A. Executive Summary", "Reports", [_section("Executive Summary", data)])


def build_result_explorer_model(c: dict[str, Any], rows: list[dict[str, Any]], mc_data: dict[str, Any] | None = None) -> dict[str, Any]:
    pages: list[dict[str, Any]] = []
    pages.append(_executive_summary_page(c, rows, mc_data))
    pages.append(_asset_allocation_page(c))
    pages.append(_net_worth_page(c, rows))
    pages.append(_cashflow_page(c, rows))
    pages.append(_lifetime_tax_page(c, rows))
    chart_page, _ = _chart_page(c, rows, mc_data)
    pages.append(chart_page)
    pages.sort(key=lambda p: {"1A. Executive Summary": 1, "1B. Net Worth": 2, "1C. Cash Flow": 3, "1D. Balance Sheet": 4, "1E. Charts": 5, "1F. Lifetime Taxes": 6, "2B. Asset Allocation": 20}.get(p.get("name"), 99))
    return {
        "success": True,
        "schema": RESULTS_MODEL_SCHEMA,
        "version": VERSION,
        "source": "semantic_results_model",
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "workbook": "retirement_plan.xlsx",
        "sheet_count": len(pages),
        "sheets": pages,
        "categories": _categories_from_pages(pages),
    }


def write_result_explorer_model(path: str | Path, c: dict[str, Any], rows: list[dict[str, Any]], mc_data: dict[str, Any] | None = None) -> dict[str, Any]:
    model = build_result_explorer_model(c, rows, mc_data)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(model, indent=2, ensure_ascii=False), encoding="utf-8")
    return model


def read_result_explorer_model(path: str | Path) -> dict[str, Any] | None:
    p = Path(path)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict) or data.get("schema") != RESULTS_MODEL_SCHEMA:
        return None
    return data


def model_index(model: dict[str, Any]) -> dict[str, Any]:
    sheets = []
    for p in model.get("sheets") or []:
        sheets.append({
            "name": p.get("name"),
            "display_name": p.get("display_name") or _clean_page_name(p.get("name")),
            "category": p.get("category") or "Other workbook detail",
            "row_count": p.get("row_count", 0),
            "column_count": p.get("column_count", 0),
            "section_count": p.get("chart_count", p.get("section_count", 0)),
            "chart_count": p.get("chart_count", 0),
            "kind": p.get("kind", "table"),
            "source": p.get("source", "semantic_results_model"),
            "loaded": False,
            "preview": False,
        })
    return {
        "success": True,
        "mode": "index",
        "schema": model.get("schema"),
        "version": model.get("version"),
        "sheets": sheets,
    }


def model_sheet(model: dict[str, Any], sheet_name: str) -> dict[str, Any] | None:
    """Return the semantic model page for *sheet_name*, or None if not found.

    Tries an exact match first, then a case-insensitive match on ``name``
    or ``display_name`` so callers don't need to worry about capitalisation.
    """
    if not model or not sheet_name:
        return None
    sheets = model.get("sheets") or []
    name_lower = sheet_name.lower().strip()
    # Exact match
    for page in sheets:
        if page.get("name") == sheet_name:
            return dict(page, success=True, source="semantic_results_model")
    # Case-insensitive fallback
    for page in sheets:
        if (page.get("name") or "").lower().strip() == name_lower:
            return dict(page, success=True, source="semantic_results_model")
        if (page.get("display_name") or "").lower().strip() == name_lower:
            return dict(page, success=True, source="semantic_results_model")
    return None

