"""Dependency-free feature service layer for local dashboard/API handlers.

Route modules in ``src.server`` adapt HTTP request/response concerns.  Modules in
this package own feature behavior and intentionally avoid importing the HTTP
runtime or route decorators.
"""
from __future__ import annotations

__all__ = [
    "admin_service",
    "base_service",
    "build_job_service",
    "build_service",
    "holdings_service",
    "plan_file_service",
    "plan_forms_service",
    "pricing_service",
    "report_service",
    "spending_service",
    "strategy_asset_service",
    "ytd_service",
]
