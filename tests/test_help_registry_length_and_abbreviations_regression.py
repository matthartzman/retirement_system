"""Help page records stay short, name current pages and define their abbreviations (W2-08 / DOC-001).

Each help slot (summary, whatFor, connections, options, impact) of HELP_PAGES is page-scoped text:
sub-page detail belongs in HELP_SECTIONS. This guard fails when a slot grows past the word limit, when
or an abbreviation is neither defined nor spelled out. Retired page names, glossary entries and the
success-rate wording are checked in tests/frontend/help_registry_content.test.mjs.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is needed to read the help registry")

SLOTS = ("summary", "whatFor", "connections", "options", "impact")
MAX_SLOT_WORDS = 120
# Literal ticker-like words that are not abbreviations of a term.
NOT_ABBREVIATIONS = {"CASH"}


@pytest.fixture(scope="module")
def records():
    import page_help_ledger as ledger

    return ledger.registry_records(ROOT)


def _known_abbreviations() -> set[str]:
    """Client acronyms (read by running the dashboard in the Node vm sandbox) plus the server glossary."""
    from src.glossary import GLOSSARY as SERVER_GLOSSARY

    script = (
        'import vm from "node:vm";'
        f'import {{ loadDashboardSandbox }} from {(ROOT / "tests" / "frontend" / "load_dashboard.mjs").as_uri()!r};'
        'const d = loadDashboardSandbox();'
        'console.log(vm.runInContext("JSON.stringify(Object.keys(ACRONYM_DEFINITIONS))", d));'
    )
    out = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True, check=True, cwd=ROOT)
    return {k.upper() for k in json.loads(out.stdout.strip().splitlines()[-1])} | {k.upper() for k in SERVER_GLOSSARY}


def test_no_help_slot_is_over_the_word_limit(records):
    over = {f"{pid}.{slot}": len(str(rec.get(slot, "")).split()) for pid, rec in records.items()
            for slot in SLOTS if len(str(rec.get(slot, "")).split()) > MAX_SLOT_WORDS}
    assert not over, f"help slots over {MAX_SLOT_WORDS} words (move sub-page detail to HELP_SECTIONS): {over}"


def test_every_abbreviation_in_a_help_slot_is_defined_or_spelled_out(records):
    known = _known_abbreviations() | NOT_ABBREVIATIONS
    bad: dict[str, set[str]] = {}
    for pid, rec in records.items():
        for slot in SLOTS:
            text = str(rec.get(slot, ""))
            for m in re.finditer(r"\b[A-Z][A-Z0-9]{1,}\b", text):
                abbr = m.group(0)
                if abbr in known or f"({abbr})" in text or f"{abbr} (" in text or f"{abbr})" in text:
                    continue
                bad.setdefault(abbr, set()).add(f"{pid}.{slot}")
    assert not bad, f"undefined abbreviations (spell them out or add them to the glossary): { {k: sorted(v) for k, v in bad.items()} }"
