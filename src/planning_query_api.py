"""Planning query and optimization convenience layer.

This module provides high-level query APIs for dashboard and scenario analysis,
delegating core projection logic to planning_engines.py. It avoids the rebinding
trap by never attempting to refactor the deterministic/MC mode split — instead,
it imports the stable public interfaces and builds query methods on top.

Query APIs:
- project_scenario(plan_dict) → deterministic projection rows
- compare_scenarios(base, mutations) → {scenario_name: metrics_dict, ...}
- optimize_roth_strategy(plan_dict) → optimized config + candidates
- monte_carlo_run(plan_dict, n_sims, seed) → success rate + path distributions
"""

from __future__ import annotations

import copy
from typing import Dict, List, Mapping, Any

from .planning_engines import (
    project,
    optimize_roth_conversion_strategy,
    monte_carlo,
    monte_carlo_exact_scalar,
)


def project_scenario(c: dict) -> List[Dict[str, Any]]:
    """Run a deterministic projection for a single scenario.

    Args:
        c: Plan configuration dict.

    Returns:
        List of year-by-year projection rows with all metrics.
    """
    return project(c)


def optimize_roth_strategy(c: dict) -> dict:
    """Optimize Roth conversion policy and return updated config.

    Uses the engine's built-in Roth optimizer to select the best policy
    from candidates (if c['roth_policy'] is set to 'optimize' or similar).
    Otherwise returns c unchanged.

    Args:
        c: Plan configuration dict.

    Returns:
        Updated config dict with roth_optimization metadata and selected strategy.
    """
    return optimize_roth_conversion_strategy(c)


def compare_scenarios(base: dict, mutations: Dict[str, dict]) -> Dict[str, dict]:
    """Project multiple scenario variants and compare metrics.

    Args:
        base: Base configuration dict.
        mutations: Dict mapping scenario name to config overrides
                   (e.g., {'high_spending': {'spend_base': 150000}, ...}).

    Returns:
        Dict mapping scenario name to metrics dict:
        {
            'baseline': {
                'terminal_nw': float,
                'lifetime_tax': float,
                'terminal_year': int,
                ...
            },
            'high_spending': {...},
        }
    """
    results = {}
    for scenario_name, overrides in mutations.items():
        c = copy.deepcopy(base)
        c.update(overrides)
        rows = project(c)
        if rows:
            last_row = rows[-1]
            results[scenario_name] = {
                'plan_start': int(c.get('plan_start', rows[0].get('year', 2026))),
                'plan_end': int(last_row.get('year', 2026)),
                'row_count': len(rows),
                'terminal_nw': float(last_row.get('total_nw', 0) or 0),
                'lifetime_tax': round(sum(float(r.get('total_tax', 0) or 0) for r in rows), 2),
                'terminal_year': int(last_row.get('year', 2026)),
            }
    return results


def monte_carlo_run(c: dict, n_sims: int = 1000, seed: int = 42) -> dict:
    """Run Monte Carlo projection and return success metrics.

    Args:
        c: Plan configuration dict.
        n_sims: Number of simulation paths.
        seed: Random seed for reproducibility.

    Returns:
        Dict with success_rate, percentiles, and path statistics.
    """
    return monte_carlo(c, n_sims=n_sims, seed=seed)


def sensitivity_run(base: dict, param_name: str, values: List[float]) -> Dict[str, dict]:
    """Run sensitivity analysis on a single parameter.

    Args:
        base: Base configuration dict.
        param_name: Config key to vary (e.g., 'spend_base', 'ret').
        values: List of parameter values to test.

    Returns:
        Dict mapping parameter value to metrics dict.
    """
    results = {}
    for val in values:
        c = copy.deepcopy(base)
        c[param_name] = val
        rows = project(c)
        if rows:
            last_row = rows[-1]
            results[str(val)] = {
                'param_value': val,
                'terminal_nw': float(last_row.get('total_nw', 0) or 0),
                'lifetime_tax': round(sum(float(r.get('total_tax', 0) or 0) for r in rows), 2),
                'final_year': int(last_row.get('year', 2026)),
            }
    return results
