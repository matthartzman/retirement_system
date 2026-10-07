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


def test_runbook_names_every_value_family_in_the_dataset():
    names = {r["name"] for r in json.loads((ROOT / "reference_src/tax_law_v10.json").read_text(encoding="utf-8"))["values"]}
    # IRMAA/SALT families are listed in the runbook by prefix or range.
    def covered(n):
        if n.startswith("irmaa_tier"):
            return "irmaa_tier1..5" in RUNBOOK
        # ACA applicable-percentage band rows are listed by band range (WI-307).
        for regime in ("original", "enhanced"):
            if n.startswith(f"aca_applicable_pct_{regime}_band"):
                return f"aca_applicable_pct_{regime}_band1.." in RUNBOOK
        return n in RUNBOOK
    missing = sorted(n for n in names if not covered(n))
    assert not missing, f"runbook omits value families in tax_law_v10.json: {missing}"


def test_runbook_treats_tax_constants_as_fallback_and_limits_as_plan_data():
    assert "fallback only" in RUNBOOK
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
