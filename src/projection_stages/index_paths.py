"""Index-path helpers lifted out of run_deterministic_projection_stage (ARC-001).

path_factor / path_ratio read a per-year index path from the plan config ``c`` (used by Monte Carlo
paths) and fall back to compounding the annual rate. Behaviour is identical to the former closures.
"""
from __future__ import annotations

from ..fallback_log import log_fallback as _log_fallback


def path_factor(c, path_key, annual_rate, year):
    path = c.get(path_key)
    if isinstance(path, dict) and year in path:
        try:
            return float(path[year])
        except (TypeError, ValueError) as _exc:
            _log_fallback("path_factor", _exc, path_key=path_key, year=year)
    return (1 + float(annual_rate or 0.0)) ** (year - c['plan_start'])

def path_ratio(c, path_key, annual_rate, year, base_year):
    if year <= base_year:
        return (1 + float(annual_rate or 0.0)) ** max(0, year - base_year)
    path = c.get(path_key)
    if isinstance(path, dict) and year in path and base_year in path:
        try:
            denom = float(path[base_year])
            if denom != 0:
                return float(path[year]) / denom
        except (TypeError, ValueError, ZeroDivisionError) as _exc:
            _log_fallback("path_ratio", _exc, path_key=path_key, year=year)
    return (1 + float(annual_rate or 0.0)) ** (year - base_year)
