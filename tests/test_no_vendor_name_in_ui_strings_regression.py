"""Item 359: the third-party import is generic -- no user-visible "Monarch" in the UI.

Scans the frontend sources (comments stripped) for the standalone word "Monarch".
Identifiers (monarch_value, renderMonarchReconciliation) are internal and allowed;
only the capitalised standalone word, which is what a person would read, is not.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCAN = [*sorted((ROOT / "frontend").rglob("*.js")), ROOT / "frontend" / "index.html",
        *sorted((ROOT / "financial_trends_reporter" / "frontend").glob("*.js")),
        ROOT / "financial_trends_reporter" / "frontend" / "index.html"]
_COMMENTS = re.compile(r"/\*.*?\*/|<!--.*?-->|^[ \t]*//[^\n]*", re.M | re.S)
_WORD = re.compile(r"\bMonarch\b")


def test_no_user_visible_monarch_in_frontend_strings():
    hits = []
    for path in SCAN:
        text = _COMMENTS.sub("", path.read_text(encoding="utf-8"))
        for n, line in enumerate(text.splitlines(), 1):
            if _WORD.search(line):
                hits.append(f"{path.relative_to(ROOT)}:{n}: {line.strip()[:100]}")
    assert not hits, "vendor name in UI strings:\n" + "\n".join(hits)


def test_nav_entry_is_generic_and_gated_by_the_plan_feature():
    from src import module_catalog as mc

    assert mc.step_gate_map()["monarch_reconciliation"] == "account_import"
    assert mc.CATALOG["account_import"].default_on is True
    assert "Monarch" not in mc.CATALOG["account_import"].name
    assert "Monarch" not in mc.CATALOG["account_import"].description
