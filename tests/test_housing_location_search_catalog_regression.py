"""The "Where to live" housing engine is catalogued, switched, and gated.

#330 §3.2 lists Housing "Where to live" among the twelve newly-optional
candidates and states its off-semantics verbatim: *"The UI panel is hidden;
`src/housing/` is not invoked"*. W8b found that neither half existed, because
`src/housing/` had no `OutputModule` at all -- the only housing entry was
`housing_trajectory_comparison`, Sheet 38, which is the *other* engine (#329
§1.4's "When to move"). W9 confirmed the gap was out of its own scope.

This file pins the catalog record and both halves of the off-semantics, so a
future edit cannot quietly return the panel and the two endpoints to being
unconditionally live.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import module_catalog as mc  # noqa: E402
from tests._decomp_dashboard import dashboard_js_text  # noqa: E402

KEY = "housing_location_search"


# ── The catalog record ───────────────────────────────────────────────────────

def test_the_location_search_is_catalogued_at_all():
    """W8b's finding, inverted into a guard. Before this entry existed there
    was nothing to classify, gate or place -- exactly the registry gap W1
    closed for `hsa_drawdown`, `tax_capacity` and `current_vs_proposed`."""
    assert KEY in mc.CATALOG
    m = mc.CATALOG[KEY]
    assert m.optional is True
    assert m.gate_kind == mc.GATE_MODULE_TOGGLE
    assert m.gate_ref is None and m.gate_enable_label is None
    assert m.gated_by is None


def test_the_two_housing_engines_are_distinct_modules_sharing_a_domain():
    """#329 §1.4: "keep both, and name them honestly". They are a *location*
    search and a *schedule* search -- different objective functions, no shared
    result shape -- so they are two records, not one. The domain is the axis
    they genuinely share (#330 §4.1: kind and domain are independent)."""
    here, sibling = mc.CATALOG[KEY], mc.CATALOG["housing_trajectory_comparison"]
    assert here.key != sibling.key
    assert here.domain == sibling.domain == mc.HOUSING_PROPERTY
    # Both are searches over levers the household controls, so both are
    # OPTIMIZATION -- the sibling's "Comparison" display name notwithstanding.
    assert here.kind == sibling.kind == mc.OPTIMIZATION
    # ...and they are separately switchable. One toggle for both would make
    # "hide the UI panel" also delete Sheet 38.
    assert here.optional and sibling.optional


def test_the_location_search_owns_no_workbook_sheet():
    """`sheet=None`, and deliberately so rather than pending.

    Divorce/QDRO carried `sheet=None` because its workbook counterpart was
    missing, and W9 built it. This one is different in kind: a sheet is built
    from the saved plan, and this search's inputs (anchor ZIPs, radii, quality
    floor, budget bounds, per-move windows, objective) are browser-local form
    state with no plan CSV behind them. Sheet 38 exists precisely because it
    reads `next_housing_steps` from the plan instead.
    """
    assert mc.CATALOG[KEY].sheet is None
    # Therefore absent from the build gate's sheet map -- like
    # `spending_tracker_ytd`, the other sheet-less optional module.
    from src.reporting.workbook_common import OPTIONAL_MODULE_SHEETS
    assert KEY not in OPTIONAL_MODULE_SHEETS
    assert "spending_tracker_ytd" not in OPTIONAL_MODULE_SHEETS


def test_the_toggle_moves_the_projection():
    """`engine_participation=True` since design 2026-09-24 §6 [C]: the switch
    owns the housing plan inputs (home sale, next housing steps, state over
    time), and off, the loader blanks them. See
    tests/test_next_housing_move_gating.py for the behavior itself."""
    assert mc.CATALOG[KEY].engine_participation is True
    assert KEY in mc.engine_participants()


def test_no_soft_dependency_on_monte_carlo_is_claimed():
    """The `mc_success_rate` objective calls `planning_engines.monte_carlo`
    directly (`optimizer.py`), not through `market_luck_stress_test`'s gate, so
    turning Monte Carlo off does not make this module say less. W5's rule: a
    declaration nothing can observe is worse than no declaration."""
    assert mc.CATALOG[KEY].degrades_without == ()
    assert KEY not in [dep for dep, _ in
                       mc.soft_dependents("market_luck_stress_test")]
    src = (ROOT / "src" / "housing" / "optimizer.py").read_text(encoding="utf-8")
    assert "_pe.monte_carlo(" in src
    assert "market_luck_stress_test" not in src


def test_it_carries_a_toggle_row_so_the_switch_is_reachable():
    """The failure W1 named: `module_enabled` defaults an absent key to
    enabled, so an optional module with no row is silently always-on -- which
    is how Housing Comparison shipped "optional" while being impossible to turn
    off. Defaulted TRUE, so adding the switch changes no behavior."""
    import csv
    path = ROOT / "input" / "demo" / "client_optional_functions.csv"
    with path.open(encoding="utf-8-sig", newline="") as fh:
        rows = {(r.get("label") or "").strip(): r for r in csv.DictReader(fh)
                if (r.get("section") or "").strip() == "Optional Functions"}
    assert KEY in rows, "no toggle row: the module would be silently always-on"
    assert str(rows[KEY].get("value", "")).strip().upper() in ("TRUE", "YES")


def test_default_plan_behavior_is_unchanged_by_the_new_switch():
    """Behavior-neutral by contract, the same way W1's three additions were:
    absent or TRUE, the module reads enabled."""
    assert mc.module_enabled({"opt": {}}, KEY) is True
    assert mc.module_enabled({"opt": {KEY: True}}, KEY) is True
    assert mc.module_enabled({"opt": {KEY: False}}, KEY) is False


# ── Off-semantics half 1: the UI panel ───────────────────────────────────────

WORKSPACE_JS = (ROOT / "frontend" / "js"
                / "dashboard_decomp_strategy_workspace.js").read_text(encoding="utf-8")


def test_the_optimize_screens_housing_section_gates_on_this_module():
    """"The UI panel is hidden". The Optimize screen's "Next Housing Move"
    section is the panel, and it used to carry `gate: null`. It now routes
    through the same server-declared `step_gates` map every other gated section
    uses -- not a hand-written `optionalFunctionEnabled(...)` branch."""
    assert mc.step_gate_map()[KEY] == KEY
    assert f'gate: "{KEY}"' in WORKSPACE_JS
    assert f'optionalFunctionEnabled("{KEY}")' not in WORKSPACE_JS
    # The gate sits on the section that renders the panel, not on a sibling.
    housing_block = WORKSPACE_JS[WORKSPACE_JS.index('key: "housing"'):]
    housing_block = housing_block[:housing_block.index("renderHousingOptimizePanelHtml()")]
    assert f'gate: "{KEY}"' in housing_block


def test_the_gate_is_a_section_and_not_a_nav_step():
    """`dashboard_step` names a gated UI *surface*. Every other value is also a
    real STEPS entry; this one is a Strategy-screen section only, and naming no
    STEPS entry is what keeps it inert in `visibleSteps()` -- which filters the
    STEPS array, so an id not in it hides nothing."""
    dashboard_js = dashboard_js_text()
    assert f'id: "{KEY}"' not in dashboard_js
    # And it owns no input CSV section either -- there is no plan data behind
    # the panel to hide. This is the no-hidden-data invariant, satisfied by
    # construction rather than by a note.
    assert mc.CATALOG[KEY].csv_sections == ()
    assert KEY not in mc.section_gate_map().values()


def test_the_home_and_housing_input_page_is_not_gated_by_this_switch():
    """The invariant no switch may break: the household's housing plan rows
    (current home, sale year, next housing steps, rent) live on the always-on
    "Home & Housing" page. Turning the search off must not touch them."""
    steps = mc.step_gate_map()
    assert "assets_home_cash" not in steps
    assert "spending_housing" not in steps


# ── Off-semantics half 2: the endpoints ──────────────────────────────────────

ROUTES_PY = ROOT / "src" / "server" / "plan_routes.py"
GATED_ROUTES = {"housing_optimize", "housing_zip_screen"}
# Reference/estimate helpers in `src/housing/api.py` that the ALWAYS-ON "Home &
# Housing" input page also calls (`/api/housing/zip-lookup` via
# dashboard_decomp_housing_scenarios.js, and `top-cities` as a plain table
# read). Gating these would hide plan-input functionality this switch does not
# own, so #330 §3.2's "`src/housing/` is not invoked" is implemented on the two
# endpoints it names: the ones that actually run the search.
UNGATED_ROUTES = {"housing_top_cities", "housing_zip_lookup"}


def _route_functions():
    tree = ast.parse(ROUTES_PY.read_text(encoding="utf-8"))
    return {n.name: n for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def test_both_search_endpoints_check_the_module_before_invoking_src_housing():
    """"`src/housing/` is not invoked". The gate has to sit in the route, not
    only in the panel: the panel being hidden does not stop a direct POST, and
    the endpoints are the only server-side entry into the search."""
    funcs = _route_functions()
    helper = "_housing_search_config_or_disabled"
    assert helper in funcs, "the shared gate helper disappeared"
    helper_src = ast.unparse(funcs[helper])
    assert "module_enabled" in helper_src and KEY in helper_src
    for name in GATED_ROUTES:
        assert name in funcs, f"{name} route disappeared"
        src = ast.unparse(funcs[name])
        assert helper in src, (
            f"{name} invokes src/housing/ without checking the module gate")


def test_the_gate_precedes_the_import_of_the_search():
    """Order matters: a check after `from ..housing import ...` would still
    load and run the package. The import must come after the gate returns."""
    funcs = _route_functions()
    for name in GATED_ROUTES:
        src = ast.unparse(funcs[name])
        assert src.index("_housing_search_config_or_disabled") < src.index(
            "from ..housing import"), (
            f"{name} imports the search before consulting the gate")
    # ...and the helper itself never imports the search package.
    assert "from ..housing import" not in ast.unparse(
        funcs["_housing_search_config_or_disabled"])


def test_the_gate_reads_the_active_plans_toggles():
    """`module_enabled(c, key)` reads `c['opt']`, so the config has to be
    loaded first. A gate handed an empty config would read default-on and
    never fire."""
    helper = _route_functions()["_housing_search_config_or_disabled"]
    helper_src = ast.unparse(helper)
    assert "prepare_config_from_sectioned_data" in helper_src
    assert "load_active_config" in helper_src
    # The gate is called with the loaded config, not with a bare {} -- an empty
    # config has no `opt` mapping, so `module_enabled` would read default-on
    # and the gate would never fire.
    calls = [n for n in ast.walk(helper)
             if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "module_enabled"]
    assert len(calls) == 1, "expected exactly one gate call in the helper"
    first_arg = calls[0].args[0]
    assert isinstance(first_arg, ast.Name) and first_arg.id == "c0"
    assert ast.literal_eval(calls[0].args[1]) == KEY


def test_the_shared_reference_endpoints_stay_ungated():
    """The Home & Housing input page calls `/api/housing/zip-lookup`; gating it
    would hide plan-input functionality behind a switch that does not own it --
    the exact shape the no-hidden-data invariant forbids."""
    funcs = _route_functions()
    for name in UNGATED_ROUTES:
        assert name in funcs
        assert KEY not in ast.unparse(funcs[name])
