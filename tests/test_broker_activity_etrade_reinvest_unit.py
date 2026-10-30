"""E*Trade files an automatic dividend reinvestment as a negative 'Dividend' row with shares, next to the positive
dividend row: the first is a purchase (kind reinvest), only the second is income."""
from src import broker_activity
from tests.broker_activity_fixtures import etrade_csv

ROWS = [
    "02/05/2026,02/05/2026,02/05/2026,Dividend,EXAMPLE SHORT TREASURY DIVIDEND REINVESTMENT,SHRT,--,5.719,110.14,-629.89,0.0,--,--",
    "02/05/2026,02/05/2026,02/05/2026,Dividend,EXAMPLE SHORT TREASURY,SHRT,--,,,629.94,0.0,--,--",
]


def test_reinvestment_row_is_a_purchase_not_negative_income():
    p = broker_activity.parse_file("etrade", etrade_csv(ROWS), account="A")
    assert p.errors == []
    kinds = sorted((r["kind"], r["amount"]) for r in p.rows)
    assert kinds == [("dividend", 629.94), ("reinvest", -629.89)]
    r = next(x for x in p.rows if x["kind"] == "reinvest")
    assert r["quantity"] == 5.719 and r["price"] == 110.14 and not r["sweep"]
