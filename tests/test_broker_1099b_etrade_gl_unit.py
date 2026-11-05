"""E*Trade Gains & Losses CSV parser: sell lines, deferred loss, T-bill symbol, control totals and rounding."""
from src import broker_1099b
from src.broker_1099b import etrade_gl

HEAD = """Account Summary
Account,Net Account Value,Total Gain $
"Trust -1234",1000.00,5.00

SEARCH CRITERIA
Account,Start Date,End  Date
"Trust -1234",01/01/2026,11/05/2026,All

TAXABLE G&L SUMMARY
Total Gain Realized,Short-Term Gain Realized,Long-Term Gain Realized,Deferred Loss,Total Commissions & Fees
{gain},{gain},.00,-.33,0.00,
TAXABLE G&L DETAILS
Symbol,Quantity,Date,Cost/Share $,Total Cost $,Date,Price/Share $,Proceeds $,Gain $,Deferred Loss $,Term,Lot Selection
"""
BODY = """ITOT,10,--,--,1000.00,--,--,1100.00,100.00,--,Short,--
    Sell,10,12/30/2025,100.00,1000.00,04/01/2026,110.00,1100.00,100.00,.00,Short,FIFO,
MUB,1,--,--,46.06,--,--,45.73,.00,-0.33,Short,--
    Sell,1,12/30/2025,46.06,46.06,04/01/2026,45.73,45.73,.00,-.33,Short,FIFO,
UNITED STATES TREASURY BILL 0% 10/27/2026,1000,--,--,990.00,--,--,1000.00,10.00,--,Short,--
    Sell,1000,09/24/2026,99.00,990.00,10/27/2026,100.00,1000.00,10.00,.00,Short,FIFO,
Total,,,,2036.06,,,2145.73,110.00,-.33,
Generated at Nov 5 2026 09:10 AM ET
"""


def _parse(gain="110.00", body=BODY):
    return etrade_gl.parse(HEAD.format(gain=gain) + body)


def test_registered_and_reads_every_sell_line():
    assert "etrade_gl" in broker_1099b.available_brokers()
    st = _parse()
    assert [r["symbol"] for r in st.rows] == ["ITOT", "MUB", "CASH (T-BILL)"]
    assert st.rows[0]["date_acquired"] == "2025-12-30" and st.rows[0]["date_sold"] == "2026-04-01"
    assert st.meta["account_last4"] == "1234" and st.meta["tax_year"] == 2026


def test_deferred_loss_is_the_disallowed_wash_amount_and_gain_foots():
    mub = _parse().rows[1]
    assert mub["wash_disallowed"] == 0.33
    assert round(mub["proceeds"] - mub["basis"] + mub["wash_disallowed"], 2) == mub["gain"]


def test_tbill_is_named_like_its_holding_lot_and_keeps_its_description():
    tb = _parse().rows[2]
    assert tb["symbol"] == "CASH (T-BILL)" and "10/27/2026" in tb["description"]
    assert tb["date_sold"] == "2026-10-27"   # the redemption date


def test_control_totals_tie_and_a_wrong_summary_is_refused():
    assert _parse().control["status"] == "ok"
    pv = broker_1099b.preview_statement("etrade_gl", text=HEAD.format(gain="999.00") + BODY, known_symbols=[])
    assert pv["control_totals"]["status"] == "mismatch" and not pv["can_apply"]


def test_cent_rounding_in_the_summary_is_tolerated_with_a_warning():
    st = _parse(gain="109.98")
    assert st.control["status"] == "ok" and any("rounding" in w for w in st.warnings)


def test_fractional_share_counts_are_not_rounded_to_cents():
    body = BODY.replace("Sell,10,12/30/2025,100.00", "Sell,10.484,12/30/2025,100.00")
    assert _parse(body=body).rows[0]["quantity"] == 10.484


def test_a_line_without_an_acquired_date_is_allowed():
    body = BODY.replace("Sell,10,12/30/2025", "Sell,10,--")
    assert _parse(body=body).rows[0]["date_acquired"] is None
