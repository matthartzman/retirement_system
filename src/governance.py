from __future__ import annotations
"""Model-risk, advisor-readiness, tax freshness, and guardrail helpers."""

import csv, datetime, json, math
from pathlib import Path
from typing import Any, Dict, Iterable, List

try:
    from .version import VERSION, RELEASE_LABEL
    from . import taxes
except ImportError:  # pragma: no cover
    from src.version import VERSION, RELEASE_LABEL
    from src import taxes

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TAX_DASHBOARD = PROJECT_ROOT / "reference_data" / "tax_update_dashboard.csv"

def _pct(value: object, default: float = 0.0) -> float:
    s = str(value or '').strip()
    if not s:
        return default
    is_pct = s.endswith('%')
    try:
        n = float(s.replace('%','').replace(',',''))
        return n/100.0 if is_pct or n > 1.0 else n
    except Exception:
        return default

def tax_law_dashboard(reference_year: int | None = None, max_lag_years: int = 1) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if TAX_DASHBOARD.exists():
        with TAX_DASHBOARD.open(newline='', encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                row = dict(row)
                row['blocking'] = str(row.get('blocking','')).strip().upper() in {'TRUE','YES','1'}
                rows.append(row)
    if not rows:
        for key, meta in sorted(getattr(taxes, 'TAX_YEAR_PROVENANCE', {}).items()):
            yr = meta.get('tax_year','')
            rows.append({'constant':key,'category':'tax','year':yr,'source':meta.get('source',''),
                         'source_url':'','last_reviewed':'','review_frequency':'annual','status':'REVIEW_REQUIRED',
                         'blocking': True, 'notes':'Generated fallback from taxes.TAX_YEAR_PROVENANCE.'})
    ref = int(reference_year or getattr(taxes, 'TAX_REFERENCE_YEAR', datetime.date.today().year))
    for row in rows:
        try:
            yr = int(str(row.get('year','')).strip())
            stale = abs(ref - yr) > int(max_lag_years)
        except Exception:
            stale = str(row.get('status','')).upper().startswith(('STALE','REVIEW'))
        if stale and str(row.get('constant','')).lower() not in {'niit_threshold'}:
            row['status'] = row.get('status') or 'STALE_REVIEW_REQUIRED'
            row['blocking'] = True
    return rows

def tax_freshness_summary(c: dict[str, Any]) -> dict[str, Any]:
    max_lag = int(c.get('tax_table_currency_max_lag_years', c.get('max_tax_table_lag_years', 1)) or 1)
    warnings = list(c.get('tax_table_currency_warnings') or taxes.tax_table_currency_warnings(max_lag_years=max_lag))
    dashboard = tax_law_dashboard(max_lag_years=max_lag)
    blocking = [r for r in dashboard if r.get('blocking')]
    return {'warnings': warnings, 'dashboard': dashboard, 'blocking_count': len(blocking),
            'status': 'BLOCKING_REVIEW_REQUIRED' if warnings or blocking else 'CURRENT'}

def model_risk_rating(mc_data: dict[str, Any] | None, deterministic: bool = False) -> dict[str, str]:
    mc_data = mc_data or {}
    if deterministic:
        return {'rating':'DETERMINISTIC_REFERENCE', 'label':'Deterministic illustration', 'description':'No-volatility reference path; not a recommendation by itself.'}
    engine = str((mc_data.get('portfolio_return_diagnostics') or {}).get('mc_engine') or mc_data.get('mc_engine') or '').lower()
    status = str(mc_data.get('mc_approximation_status') or '').upper()
    if 'exact_scalar' in engine:
        rating = 'EXACT_SCALAR_MC'
        label = 'Exact scalar Monte Carlo validation mode'
        desc = 'Runs full scalar tax/withdrawal projection per path; slower but highest internal fidelity.'
    elif 'vectorized' in engine:
        rating = 'APPROXIMATE_VECTORIZED_MC' if status != 'TOLERANCE_BOUNDED' else 'TOLERANCE_BOUNDED_VECTORIZED_MC'
        label = 'Approximate vectorized Monte Carlo' if status != 'TOLERANCE_BOUNDED' else 'Tolerance-bounded vectorized Monte Carlo'
        desc = 'Batched engine for speed; exact scalar parity checks must remain within tolerance before advisor-ready reliance.'
    elif mc_data:
        rating = 'SCENARIO_OR_UNKNOWN_OUTPUT'
        label = 'Scenario/unknown probabilistic output'
        desc = 'Model mode is not fully classified; treat as illustrative.'
    else:
        rating = 'SCENARIO_ONLY'
        label = 'Scenario-only output'
        desc = 'No Monte Carlo data was generated.'
    return {'rating': rating, 'label': label, 'description': desc}

def pricing_staleness_summary(diag: dict[str, Any] | None, max_fallback_pct: float = 0.10) -> dict[str, Any]:
    diag = diag or {}
    prices = diag.get('prices') or {}
    sources = diag.get('sources') or {}
    fallback_sources = {'fallback_cost_basis','fallback','stale_cache','cost_basis','manual_fallback','unknown'}
    total = float(len(prices) or len(sources) or 0)
    fallback = 0.0
    warnings=[]
    per=[]
    for sym, src in sorted(sources.items()):
        s=str(src or '').lower()
        is_fb = any(tok in s for tok in fallback_sources)
        if is_fb:
            fallback += 1
            warnings.append(f'{sym}: priced from {src}')
        per.append({'symbol':sym,'source':src,'warning':is_fb})
    fallback_pct = (fallback/total) if total else 0.0
    return {'fallback_symbol_count': int(fallback), 'priced_symbol_count': int(total),
            'fallback_symbol_pct': fallback_pct, 'advisor_ready_blocked': fallback_pct > max_fallback_pct,
            'max_fallback_pct': max_fallback_pct, 'warnings': warnings, 'per_ticker': per}

def assumption_signoff_status(c: dict[str, Any]) -> dict[str, Any]:
    required = ['risk_tolerance','spending_floor_flex','longevity_assumption','inflation_assumption',
                'tax_review','return_assumption','roth_conversion_objective','estate_intent']
    # Config can provide booleans as advisor_signoff_<name>. Default is unsigned.
    missing=[]
    for name in required:
        raw = str(c.get('advisor_signoff_'+name, '') or '').strip().upper()
        if raw not in {'YES','TRUE','SIGNED','COMPLETE','1'}:
            missing.append(name)
    return {'required': required, 'missing': missing, 'complete': not missing,
            'status': 'SIGNED' if not missing else 'ILLUSTRATION_ONLY'}

def stress_narratives(c: dict[str, Any], rows: Iterable[dict[str, Any]], mc_data: dict[str, Any]) -> list[dict[str, str]]:
    success = float((mc_data or {}).get('success_rate', 0.0) or 0.0)
    spend = float(c.get('spend_base', 0.0) or 0.0)
    narratives=[]
    narratives.append({'stress':'Poor first-five-year returns', 'narrative': 'Early negative returns matter most when withdrawals start soon; funded status depends on whether liquid assets can cover spending while impaired assets recover.'})
    narratives.append({'stress':'High inflation', 'narrative': 'Inflation raises spending, Medicare/IRMAA thresholds, and tax-bracket interactions. Stochastic inflation paths are modeled, but tax constants must be reviewed annually.'})
    narratives.append({'stress':'Early death / survivor', 'narrative': 'Survivor single-filer tax compression can raise marginal rates and IRMAA risk while one Social Security benefit may disappear.'})
    narratives.append({'stress':'Long-term-care shock', 'narrative': 'An LTC event can rapidly consume liquid assets; the report separates insured benefits from self-funded costs.'})
    narratives.append({'stress':'Plan outcome driver', 'narrative': f'At {success:.1%} modeled success and base spending near ${spend:,.0f}, failures usually come from spending/tax pressure exceeding liquid assets, not accounting net worth alone.'})
    return narratives

def advisor_readiness(c: dict[str, Any], mc_data: dict[str, Any] | None = None, pricing_diag: dict[str, Any] | None = None) -> dict[str, Any]:
    blockers=[]; warnings=[]
    tax = tax_freshness_summary(c)
    if tax['status'] != 'CURRENT':
        blockers.append('Tax table/source review is stale or blocking.')
    pr = pricing_staleness_summary(pricing_diag, _pct(c.get('advisor_ready_max_fallback_value_pct', 0.10), 0.10))
    if pr['advisor_ready_blocked']:
        blockers.append('Too much of the priced holdings universe uses fallback/stale/manual pricing.')
    signoff = assumption_signoff_status(c)
    if not signoff['complete']:
        warnings.append('Advisor/client assumption signoff is incomplete; output is still allowed because signoff is an optional advisor workflow.')
    risk = model_risk_rating(mc_data)
    if risk['rating'] == 'APPROXIMATE_VECTORIZED_MC':
        warnings.append('Vectorized Monte Carlo is approximate until scalar parity is tolerance-bounded.')
    status='ADVISOR_READY' if not blockers and not warnings else ('BLOCKED' if blockers else 'REVIEW_REQUIRED')
    return {'status': status, 'is_advisor_ready': status == 'ADVISOR_READY', 'blockers': blockers, 'warnings': warnings,
            'tax_freshness': tax, 'pricing': pr, 'assumption_signoff': signoff, 'model_risk': risk,
            'illustration_notice': ''}

def source_citations(c: dict[str, Any]) -> list[dict[str, str]]:
    cites=[]
    for k, v in sorted((c.get('tax_provenance') or getattr(taxes, 'TAX_YEAR_PROVENANCE', {})).items()):
        cites.append({'topic': k, 'year': str(v.get('tax_year','')), 'source': str(v.get('source',''))})
    for row in tax_law_dashboard():
        if row.get('source_url'):
            cites.append({'topic': row.get('constant',''), 'year': str(row.get('year','')), 'source': row.get('source_url','')})
    return cites

def workbook_consistency_warnings(c: dict[str, Any], rows: Iterable[dict[str, Any]]) -> list[dict[str, str]]:
    """Return workbook-visible consistency warnings without blocking generation.

    This is intentionally conservative: it catches mismatches between the canonical
    optimizer result contract and values that workbook sheets are expected to show.
    The workbook renders these as warnings so an illustration can still be built,
    while advisor review can see what needs attention.
    """
    row_list = list(rows or [])
    warnings: list[dict[str, str]] = []
    # Advisory-only: an explicit h_rmd_start_age/w_rmd_start_age (or shared
    # rmd_start_age) override that disagrees with the SECURE 2.0 statutory
    # default computed from that member's date of birth (statutory_rmd_start_age
    # in core.py). Recorded at parse time in data_io.py; surfaced here rather
    # than blocking, per item 2.2's "advisory, not a blocker" requirement.
    for _w in (c.get('rmd_start_age_warnings') or []):
        if isinstance(_w, dict):
            warnings.append(dict(_w))
    ropt = c.get('roth_optimization') or {}
    selected_policy = str(ropt.get('selected_policy') or c.get('roth_policy') or '').lower()
    if ropt and selected_policy != str(c.get('roth_policy','')).lower():
        warnings.append({'code':'ROTH_POLICY_MISMATCH', 'severity':'WARN',
                         'message':f"Optimizer selected {selected_policy}, but runtime policy is {c.get('roth_policy')}.",
                         'action':'Use the canonical RothStrategyResult contract for all workbook surfaces.'})
    if ropt and ropt.get('selected_label'):
        label = str(ropt.get('selected_label',''))
        import re
        m = re.search(r'(\d{1,2})% bracket', label)
        if m:
            label_rate = int(m.group(1)) / 100.0
            target_rate = float(c.get('roth_target_rate', c.get('roth_brk', label_rate)) or label_rate)
            if abs(label_rate - target_rate) > 1e-6:
                warnings.append({'code':'ROTH_BRACKET_LABEL_MISMATCH', 'severity':'WARN',
                                 'message':f"Selected label says {label_rate:.0%}, but configured target is {target_rate:.0%}.",
                                 'action':'Regenerate the Roth narrative from the selected strategy object.'})
    forced_total = sum(float(v or 0.0) for v in (c.get('forced_roth') or {}).values())
    schedule_total = sum(float(r.get('roth_conv', 0.0) or 0.0) for r in row_list)
    if schedule_total + 1e-6 < forced_total:
        warnings.append({'code':'FORCED_CONVERSION_NOT_IN_SCHEDULE', 'severity':'WARN',
                         'message':f"Forced Roth conversions total ${forced_total:,.0f}, but schedule shows ${schedule_total:,.0f}.",
                         'action':'Check forced-action years and projection horizon.'})
    candidates = ropt.get('candidates') if isinstance(ropt, dict) else None
    if candidates:
        top = max(candidates, key=lambda x: float(x.get('score', 0.0) or 0.0))
        if str(top.get('label')) != str(ropt.get('selected_label')):
            warnings.append({'code':'ROTH_SELECTED_NOT_TOP_SCORE', 'severity':'WARN',
                             'message':f"Selected strategy {ropt.get('selected_label')} is not the highest score candidate {top.get('label')}.",
                             'action':'Re-sort candidate table or rerun optimization.'})
    return warnings
