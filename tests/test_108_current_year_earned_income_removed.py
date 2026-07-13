from pathlib import Path
import csv
import json


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "frontend/js/dashboard.js"


def test_current_year_earned_income_label_is_removed_from_ui_copy():
    text = DASHBOARD.read_text(encoding="utf-8")
    assert "Current Year Earned Income" not in text
    assert "Current year earned income" not in text
    assert "Earned Income End Year" in text


def test_work_income_page_hides_internal_earned_income_end_year_driver():
    text = DASHBOARD.read_text(encoding="utf-8")
    assert 'case "income_work"' in text
    assert "lbl!=='earned_income_last_year'" in text


def test_income_mirrors_store_earned_income_last_year_as_year_not_currency():
    with (ROOT / "input/client_income.csv").open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    row = next(r for r in rows if r.get("label") == "earned_income_last_year")
    assert row.get("value") == "2027"
    assert "$" not in row.get("value", "")
    data = json.loads((ROOT / "input/client_data.json").read_text(encoding="utf-8"))
    assert data["Cashflow"]["Earned Income"]["earned_income_last_year"] == "2027"
