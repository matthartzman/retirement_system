from src.balance_sheet_liabilities import balance_sheet_liabilities


def test_every_liability_line_is_listed_once_and_heloc_is_not_folded_into_the_mortgage():
    yr0 = {'mort_bal_yr': 200000, 'heloc_liability': 30000, 'next_housing_mortgage_balance': 150000,
           'additional_liabilities': 12000}
    lines = {lbl: amt for lbl, amt, _ in balance_sheet_liabilities(yr0, 999)}
    assert lines == {'Mortgage': 200000, 'HELOC': 30000, 'Next-Housing Mortgage': 150000,
                     'Credit Cards, Loans & Other Liabilities': 12000}
    assert sum(lines.values()) == 392000      # == the engine's total_liabilities (before rental mortgages)


def test_falls_back_to_the_derived_mortgage_when_the_row_has_no_balance_key():
    assert balance_sheet_liabilities({}, 55.0)[0][1] == 55.0
