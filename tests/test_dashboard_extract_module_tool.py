"""Guards the safety rails of tools/js_codemod/extract_module.mjs.

That codemod moves top-level declarations out of frontend/js/dashboard.js into
a new ES module. Its correctness is enforced at runtime by a round-trip check
it performs on every invocation (see the tool's own header). What THIS file
guards is the set of refusals -- the cases where the tool must abort rather
than produce a plausible-looking but broken split. Those rails are the part
most likely to be quietly deleted by a future edit, because removing them makes
the tool "work" on inputs it should reject.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "js_codemod" / "extract_module.mjs"
DASHBOARD_JS = ROOT / "frontend" / "js" / "dashboard.js"
CENSUS_REPORT = ROOT / "tools" / "js_codemod" / "census_report.json"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["node", str(TOOL), *args], cwd=ROOT, text=True, capture_output=True, timeout=120
    )


def test_tool_exists():
    assert TOOL.is_file()


def test_unknown_name_is_refused():
    before = DASHBOARD_JS.read_bytes()
    result = _run("--names", "thisFunctionDoesNotExistAnywhere", "--out",
                  "frontend/js/dashboard_decomp_should_not_exist.js", "--check")
    assert result.returncode != 0, result.stdout + result.stderr
    assert "not a top-level declaration" in (result.stdout + result.stderr)
    assert DASHBOARD_JS.read_bytes() == before
    assert not (ROOT / "frontend" / "js" / "dashboard_decomp_should_not_exist.js").exists()


def test_reassigned_function_is_refused():
    """renderMain is monkey-patched by other leaf modules as a decorator chain,
    so it needs the reassignable-let + get/set accessor treatment that
    convert_dashboard.mjs applies inside dashboard.js. This tool does not
    reproduce that for a target module, so it must refuse rather than emit a
    plain `export function renderMain` that silently breaks the chain."""
    census = json.loads(CENSUS_REPORT.read_text(encoding="utf-8"))
    assert "renderMain" in census["reassigned_functions"]
    before = DASHBOARD_JS.read_bytes()
    result = _run("--names", "renderMain", "--out",
                  "frontend/js/dashboard_decomp_should_not_exist.js", "--check")
    assert result.returncode != 0, result.stdout + result.stderr
    assert "reassigned" in (result.stdout + result.stderr).lower()
    assert DASHBOARD_JS.read_bytes() == before


def test_duplicate_name_is_refused():
    result = _run("--names", "renderLiabilitiesTable,renderLiabilitiesTable", "--out",
                  "frontend/js/dashboard_decomp_should_not_exist.js", "--check")
    assert result.returncode != 0, result.stdout + result.stderr
    assert "duplicate" in (result.stdout + result.stderr).lower()
