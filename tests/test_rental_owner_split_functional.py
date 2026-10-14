"""H4: rental sale proceeds follow ownership (RENTAL_TAX_RULES.md section 11)."""
from __future__ import annotations

import pytest

from src.parsing.rental_properties import RentalPropertyInputError, parse_rental_properties
from tests import rental_fixtures as rf


def _sale_row(**extra):
    row = rf.by_year(rf.project(rf.rental_config(rf.RentalCase([dict(rf.SALE_WITH_RECAPTURE, **extra)]))))[2035]
    parts = {k: sum(x["amount"] for x in v if "Rental" in x["source"])
             for k, v in row["_account_deposit_sources"].items() if any("Rental" in x["source"] for x in v)}
    return row, parts


def test_unset_owner_keeps_the_single_default_account():
    row, parts = _sale_row()
    assert parts == {"Member_2_Trust": pytest.approx(row["rental_sale_net_proceeds"])}
    assert "owner" not in row["rental_by_property"][0]


@pytest.mark.parametrize("extra, m1, m2", [
    ({"owner": "joint"}, 0.5, 0.5),                            # O1
    ({"owner": "joint", "member_1_share": 0.6}, 0.6, 0.4),     # O2
    ({"owner": "member_1"}, 1.0, 0.0),                         # O3
    ({"owner": "member_2"}, 0.0, 1.0),
])
def test_proceeds_split_by_ownership(extra, m1, m2):
    row, parts = _sale_row(**extra)
    net = row["rental_sale_net_proceeds"]
    assert parts.get("Member_1_Trust", 0.0) == pytest.approx(net * m1, abs=0.01)
    assert parts.get("Member_2_Trust", 0.0) == pytest.approx(net * m2, abs=0.01)
    assert row["rental_by_property"][0]["owner"] == extra["owner"]


def test_rental_tax_items_are_the_same_whoever_owns_it():
    base = rf.by_year(rf.project(rf.rental_config(rf.RentalCase([dict(rf.SALE_WITH_RECAPTURE)]))))
    split = rf.by_year(rf.project(rf.rental_config(rf.RentalCase([dict(rf.SALE_WITH_RECAPTURE, owner="joint")]))))
    # the rental tax items are identical; only where the cash lands (and so later investment income) can differ
    for k in ("rental_sale_gain", "rental_sale_capital_gain", "rental_schedule_e_net", "rental_schedule_e_to_agi"):
        assert split[2035][k] == pytest.approx(base[2035][k], abs=0.01)  # O7


def test_validation():
    c = rf.base_config()
    with pytest.raises(RentalPropertyInputError, match="only to Joint"):
        parse_rental_properties(c, [dict(rf.PROFITABLE, owner="member_1", member_1_share=0.6)])  # O6
    with pytest.raises(RentalPropertyInputError, match="owner must be"):
        parse_rental_properties(c, [dict(rf.PROFITABLE, owner="bob")])
    assert parse_rental_properties(c, [dict(rf.PROFITABLE, owner="Member 2")])[0]["owner"] == "member_2"
