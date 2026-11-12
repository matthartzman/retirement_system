"""WI-311 / DOC-001: the tax-year runbook and the in-app dashboard text must
describe the dated-row rule the engine depends on, and must not send a
maintainer to a file the engine does not read."""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNBOOK = (ROOT / "documentation/reference/ANNUAL_MAINTENANCE_RUNBOOK.md").read_text(encoding="utf-8")
DASH = ROOT / "reference_src/tax_update_dashboard.csv"


def test_runbook_states_the_dated_row_rule():
    assert "effective_year" in RUNBOOK
    assert "never overwrite" in RUNBOOK.lower()
    assert "tax_law_v10.json" in RUNBOOK


def test_runbook_points_at_the_dataset_and_register_instead_of_copying_the_family_list():
    # One source: the dataset itself is the list of value families, and the
    # register's section L records what each law assumes. The runbook must say so.
    assert "tax_law_v10.json" in RUNBOOK
    assert "PLANNING_ASSUMPTIONS_AND_EXPERT_DECISIONS_REGISTER.md" in RUNBOOK
    assert "section L" in RUNBOOK


def test_runbook_says_tax_constants_csv_is_gone_and_limits_are_plan_data():
    assert "tax_constants.csv` has been removed" in RUNBOOK
    assert "annual_401k_limit_base_year" in RUNBOOK
    assert "Update `reference_data/tax_constants.csv`: standard deduction" not in RUNBOOK


def test_dashboard_text_points_at_the_json_dataset_not_embedded_tables():
    rows = list(csv.DictReader(DASH.open(encoding="utf-8")))
    federal = [r for r in rows if r["constant"] in {"federal_brackets", "standard_deduction", "irmaa_tiers", "ltcg_brackets", "ss_wage_base"}]
    assert federal
    for r in federal:
        text = r["source"] + " " + r["notes"]
        assert "tax_law_v10.json" in text, r["constant"]
        assert "embedded in src/taxes.py" not in text, r["constant"]
        assert "update tax_constants.csv" not in text.lower(), r["constant"]
