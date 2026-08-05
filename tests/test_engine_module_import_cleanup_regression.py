"""Wave 4.1 and 4.7 (system review 2026-08-04, architect findings).

4.1: _we/_ce/_ie/_ge (deterministic_engine.py) all pointed at the identical
module (planning_engines) -- collapsed to one name. Also removed duplicate
mid-file imports in planning_engines.py's 8-concatenated-file monolith
(dataclass/field, MutableMapping each imported twice; numpy imported locally
12 separate times).

4.7: deleted src/engine_config_loader.py (orphaned Phase 1 DB-canonical
migration scaffolding -- additive, never wired into any real call site, only
referenced by its own now-also-deleted test). This file adds the field-set
guard test the finding also asked for: PlanningCaseV1 (Python) and the
planning_case_v1 object literal (JS, frontend/js/planning_workbench_ui.js)
are two independent hand-maintained descriptions of the same browser-local
storage contract -- nothing enforces they stay in sync.
"""
from __future__ import annotations

import dataclasses
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_engine_config_loader_is_gone():
    assert not (ROOT / "src" / "engine_config_loader.py").exists()


def _code_lines(path: Path) -> list[str]:
    return [ln for ln in path.read_text(encoding="utf-8").splitlines() if not ln.strip().startswith("#")]


def test_no_we_ce_ie_ge_aliases_remain():
    lines = _code_lines(ROOT / "src" / "projection_stages" / "deterministic_engine.py")
    for alias in ("_we", "_ce", "_ie", "_ge"):
        hits = [ln for ln in lines if re.search(rf"\b{alias}\b", ln)]
        assert not hits, f"{alias} alias should have been removed: {hits}"


def test_planning_engines_has_no_duplicate_top_level_imports():
    lines = _code_lines(ROOT / "src" / "planning_engines.py")
    numpy_imports = [ln for ln in lines if ln.strip() == "import numpy as _np"]
    assert len(numpy_imports) == 1, f"numpy should be imported exactly once, found {len(numpy_imports)}"
    dataclass_imports = [ln for ln in lines if ln.strip() == "from dataclasses import dataclass, field"]
    assert len(dataclass_imports) == 1, f"dataclass/field should be imported exactly once, found {len(dataclass_imports)}"
    bare_mutable_mapping = [ln for ln in lines if ln.strip() == "from typing import MutableMapping"]
    assert not bare_mutable_mapping, "the redundant bare MutableMapping re-import should have been removed"


def _js_planning_case_fields() -> set[str]:
    js = (ROOT / "frontend" / "js" / "planning_workbench_ui.js").read_text(encoding="utf-8")
    # The literal object construction: `const c = { case_id: ..., ... };`
    m = re.search(r"const c = \{(.*?)\n    \};", js, re.DOTALL)
    assert m, "could not find the planning_case_v1 object literal in planning_workbench_ui.js"
    body = m.group(1)
    return set(re.findall(r"^\s*(\w+):", body, re.MULTILINE))


def _python_planning_case_fields() -> set[str]:
    from src.planning_workbench import PlanningCaseV1
    return {f.name for f in dataclasses.fields(PlanningCaseV1)}


def test_planning_case_v1_field_set_matches_between_python_and_js():
    py_fields = _python_planning_case_fields()
    js_fields = _js_planning_case_fields()
    assert py_fields == js_fields, (
        f"PlanningCaseV1 (src/planning_workbench.py) and the planning_case_v1 object "
        f"literal (frontend/js/planning_workbench_ui.js) have drifted: "
        f"python-only={py_fields - js_fields}, js-only={js_fields - py_fields}"
    )
