"""Liability payoff date (year + month) and carry-zero, in the cash-gap stage."""
from src.projection_stages.withdrawal_cascade_gap_assembly import apply_gap_assembly

ZERO = dict(h_ss=0, w_ss=0, pension=0, wife_single_ann=0, wife_joint_ann=0, h_single_ann=0, h_joint_ann=0,
            note_princ_yr=0, note_int_yr=0, rmd_taxable_total=0, earned_base=0,
            equity_events={'cash_proceeds': 0}, di_cash=0, total_spend_need=0, total_tax=0, other_cash_need_yr=0,
            rec_extra=0, lump_yr=0, heloc_draw_yr=0, heloc_interest_yr=0, heloc_repayment_principal_yr=0)


def _run(liab, years):
    c = {'liabilities': [dict({'liability_id': 'cc', 'type': 'credit_card', 'start_year': 0, 'monthly_payment': 0.0,
                               'interest_rate': 0.0, 'payoff_month': 0, 'carry_zero': True}, **liab)]}
    bal = {'_liability_balances': {'cc': float(liab['balance'])}}
    out = []
    for y in years:
        row = {}
        apply_gap_assembly(c, bal, row, year=y, **ZERO)
        out.append((y, bal['_liability_balances']['cc'], row['liability_payment']))
    return out


def test_payoff_month_limits_the_payoff_year_payments_and_settles_the_residual():
    # 1,000/yr-end balance, $100/mo, no interest, paid off in June 2027: 6 payments, then the residual is settled
    res = _run({'balance': 10000, 'monthly_payment': 100, 'payoff_year': 2027, 'payoff_month': 6}, [2026, 2027, 2028])
    assert res[0][1] == 10000 - 1200 and res[0][2] == 1200
    assert res[1][1] == 0 and round(res[1][2], 2) == 8800     # 6 x 100 + residual 8,200 paid on the payoff date
    assert res[2][1] == 0 and res[2][2] == 0                  # carries zero afterwards, no more payments


def test_carry_zero_off_keeps_the_residual_but_stops_payments():
    res = _run({'balance': 10000, 'monthly_payment': 100, 'payoff_year': 2026, 'payoff_month': 6, 'carry_zero': False},
               [2026, 2027])
    assert res[0][1] == 9400 and res[0][2] == 600
    assert res[1][1] == 9400 and res[1][2] == 0


def test_no_payoff_date_is_unchanged_interest_only_and_never_paid_off():
    res = _run({'balance': 10000, 'interest_rate': 0.2}, [2026, 2027])
    assert [r[1] for r in res] == [10000, 10000] and res[0][2] == 2000


def test_payoff_date_without_payment_level_amortizes_to_the_month():
    res = _run({'balance': 12000, 'payoff_year': 2026, 'payoff_month': 12}, [2026])
    assert abs(res[0][1]) < 1e-6 and abs(res[0][2] - 12000) < 1e-6
