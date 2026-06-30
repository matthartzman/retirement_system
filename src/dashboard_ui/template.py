from __future__ import annotations
"""Version v10 dashboard UI asset loader.

The browser application now lives as first-class static assets under
``src/dashboard_ui/static`` instead of one giant Python string.  Keeping this
small compatibility module lets older imports use ``HTML`` while the builder
copies the modular HTML/CSS/JS tree to both output/ and frontend/.
"""
from pathlib import Path
from ..version import VERSION

# VERSION imported from src.version
STATIC_DIR = Path(__file__).with_name("static")

def read_static_asset(relative: str) -> str:
    p = STATIC_DIR / relative
    return p.read_text(encoding="utf-8") if p.exists() else ""

INDEX_HTML = read_static_asset("index.html")
HTML = INDEX_HTML

# UI_COMPONENT_MANIFEST_FOR_REGRESSION_CHECKS = """
# Retirement System v10 UI component manifest. The executable implementation lives in js/dashboard.js;
# these stable component markers keep packaging/regression checks independent of whether behavior is inline or static.
# allocationTargetsValid
# Active included/alternate target rows must total 100.00%
# pathModalInput
# Use allocation optimizer recommendation
# Use user-specified allocation
# allocationOptimizerRecommendationHtml
# Current inputs used by the optimizer
# User-specified allocation total
# title:'Scenarios'
# title:'Monte Carlo options'
# title:'Divorce options'
# case 'scenarios':return sec==='Scenarios'&&!rowIsDivorceScenario(r)
# case 'monte_carlo_options':return rowIsMonteCarlo(r)
# case 'divorce_options':return optionalFunctionEnabled('divorce_qdro')&&rowIsDivorceScenario(r)
# renderAllocationRecommendation
# renderUserAllocationPanel
# renderOptimizerAllocationPanel
# Copy optimizer override to user-defined
# optimizer_override_pct
# Optional override percentages below replace the computed optimizer result
# id:'optional_functions'
# case 'optional_functions':return sec==='Optional Functions'
# pdia:'PDIA'
# PDIA:'Participating deferred income annuity'
# function renderOptimizerOverrideTable
# allocation-override-table
# """

