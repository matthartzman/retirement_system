from pathlib import Path
import csv

ROOT = Path(__file__).resolve().parents[1]


def test_january_first_retirement_date_sets_final_earned_income_year_to_prior_year():
    from src.data_io import _last_earned_income_year_from_retirement_date

    assert _last_earned_income_year_from_retirement_date("2027-01-01") == 2026
    assert _last_earned_income_year_from_retirement_date("1/1/2027") == 2026


def test_non_january_first_retirement_date_keeps_existing_annual_boundary():
    from src.data_io import _last_earned_income_year_from_retirement_date

    assert _last_earned_income_year_from_retirement_date("2027-06-30") == 2027
    assert _last_earned_income_year_from_retirement_date("2/28/2027") == 2027


def test_ytd_earned_income_forecast_uses_same_january_first_boundary(tmp_path):
    from src.ytd_tracking import annual_earned_income_forecast

    with (tmp_path / "client_income.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["section", "subsection", "label", "value", "type", "notes"])
        w.writeheader()
        w.writerow({"section":"Cashflow","subsection":"Earned Income","label":"annual_earned_income","value":"100000"})
        w.writerow({"section":"Cashflow","subsection":"Earned Income","label":"earned_income_start_year","value":"2026"})
        w.writerow({"section":"Cashflow","subsection":"Earned Income","label":"earned_income_annual_increase","value":"3%"})
    with (tmp_path / "client_household.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["section", "subsection", "label", "value", "type", "notes"])
        w.writeheader()
        w.writerow({"section":"Household","subsection":"","label":"husband_retirement_date","value":"1/1/2027"})

    assert annual_earned_income_forecast(tmp_path, 2026) == 100000
    assert annual_earned_income_forecast(tmp_path, 2027) == 0.0
