"""Forecast API service helpers extracted from the local route layer."""
from __future__ import annotations

from typing import Any, Dict, Mapping

from .report_compute import prepare_config_from_json, run_projection_artifacts
from .after_tax import estimate_after_tax_terminal_net_worth


def forecast_from_plan_json(plan: Mapping[str, Any], run_mc: bool = True) -> Dict[str, Any]:
    c = prepare_config_from_json(plan, optimize_roth=True)
    # For fast API calls, let the caller decide whether to run MC.  The route
    # keeps the historical behavior and asks for MC by default.
    # Forecast API responses should return the projected gaps as data rather than
    # failing the whole request.  Hard release-gate checks remain available to
    # callers that explicitly invoke run_projection_artifacts with
    # enforce_release_gate=True.
    artifacts = run_projection_artifacts(c, run_mc=run_mc, enforce_release_gate=False)
    rows = list(artifacts.rows)
    mc = artifacts.mc_data or {}
    terminal_row = rows[-1] if rows else {}
    # Post-Tax Inheritance (PTI) = terminal net worth minus embedded taxes heirs
    # would owe (deferred ordinary tax on pre-tax accounts + deferred cap-gains
    # tax on taxable brokerage). Reuses the existing after-tax terminal estimator.
    after_tax = estimate_after_tax_terminal_net_worth(artifacts.config, terminal_row) if rows else {}
    after_tax_nw = after_tax.get('after_tax_terminal_net_worth')
    post_tax_inheritance = after_tax.get('post_tax_inheritance', after_tax_nw)
    return {
        'status': 'ok',
        'terminal_nw': round(rows[-1].get('total_nw', 0) if rows else 0),
        'after_tax_terminal_nw': round(after_tax_nw) if after_tax_nw is not None else None,
        'post_tax_inheritance': round(post_tax_inheritance) if post_tax_inheritance is not None else None,
        'terminal_estate_tax': round(after_tax.get('terminal_estate_tax', 0)),
        'terminal_deferred_tax_total': round(after_tax.get('terminal_deferred_tax_total', 0)),
        'lifetime_tax': round(sum(r.get('total_tax', 0) for r in rows)),
        'mc_success': round(mc.get('success_rate', 0) * 100, 1) if mc else None,
        'plan_years': len(rows),
        'survival_curve': mc.get('survival_curve', []) if mc else [],
        'validation': artifacts.validation,
        'config_contract_source': artifacts.config.get('config_contract_source'),
    }
