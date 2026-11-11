"""User-facing disclosure text from the 2026-11-10 system review (W2-03).

No numeric behaviour: these pin the strings that stop the app from claiming things the engine
does not do (FIN-001, FIN-005, FIN-008, FIN-009, FIN-010, FIN-012) and the QA-005 rule that no
user-facing string names the untracked ``reference_data/`` directory.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_no_user_facing_string_names_the_dead_reference_data_path():
    """QA-005: reference_data/ is not tracked; only comments and the module catalog may mention it."""
    for rel in ("src/core.py", "src/reporting/sheets_strategy.py", "src/tax_assumptions.py",
                "src/server_services/strategy_asset_service.py"):
        for n, line in enumerate(_read(rel).splitlines(), 1):
            code = line.split("#", 1)[0] if rel.endswith(".py") else line
            if "reference_data/state_tax.csv" in code and not line.lstrip().startswith(("#", "//")):
                # docstring prose (not a message) is allowed in core.py's supported_states()
                assert rel == "src/core.py" and 950 < n < 965, f"{rel}:{n}: {line.strip()[:100]}"


def test_s_corp_comparison_does_not_claim_a_qbi_basis_or_a_surcharge_the_engine_lacks():
    text = _read("src/reporting/sheets_strategy.py")
    assert "allocable basis" not in text
    assert "Corp Surcharge" not in text and "corporate surcharge applies" not in text
    assert "Not modeled in the projection" in text


def test_income_comment_no_longer_says_the_il_surcharge_is_captured_via_agi():
    text = _read("src/projection_stages/income.py")
    assert "already captured in state_tax via AGI" not in text
    assert "Replacement Income Tax" in text


def test_life_insurance_sheet_banner_describes_the_death_benefit_routing():
    # FIN-005 (W4-04): the sheet is only built with the module on, when death benefits ARE projected.
    text = _read("src/reporting/sheets_protection.py")
    assert "INVENTORY ONLY" not in text
    assert "DEATH BENEFITS ARE IN THE PROJECTION" in text
    assert "ILIT" in text and "Beneficiary designations are not modelled" in text


def test_divorce_scenario_label_says_what_stays_unchanged():
    text = _read("src/reporting/sheets_stress.py")
    assert "Filing status (joint)" in text and "not a post-divorce household analysis" in text


def test_401k_limit_help_discloses_the_simplifications():
    row = next(l for l in _read("reference_src/schema.csv").splitlines() if "annual_401k_limit_base_year" in l)
    assert "no age-based catch-up" in row and "Roth catch-up" in row


def test_mortality_docstring_names_the_ssa_2023_table_and_the_positional_convention():
    text = _read("src/engine_kernels.py")
    block = text[text.index("def _mortality_qx_table"):][:1400]
    assert "SSA 2023 period" in block and "positional" in block
