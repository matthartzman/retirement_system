from pathlib import Path

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
    from tests.plan_fixture import stage_plan_csv

    head = "section,subsection,label,value,type,notes\n"
    inp = stage_plan_csv(tmp_path, {
        "client_income.csv": head
        + "Cashflow,Earned Income,annual_earned_income,100000,,\n"
        + "Cashflow,Earned Income,earned_income_start_year,2026,,\n"
        + "Cashflow,Earned Income,earned_income_annual_increase,3%,,\n",
        "client_household.csv": head + "Household,,member_1_retirement_date,1/1/2027,,\n",
    })

    assert annual_earned_income_forecast(inp, 2026) == 100000
    assert annual_earned_income_forecast(inp, 2027) == 0.0
