"""WP12.4: parse_client fills c['rental_properties'] from the plan's rental tables only while
the rental_property_income feature is on; off leaves the config untouched and the data kept."""
from __future__ import annotations

import copy

import pytest

from src import module_catalog as mc
from src.active_plan import PLAN_DB_ENV, active_rental_properties
from src.data_io import parse_client
from src.parsing.rental_properties import RentalPropertyInputError
from tests import rental_fixtures as rf
from tests.plan_fixture import make_plan, plain

KEY = "rental_property_income"


@pytest.fixture
def ws(tmp_path, monkeypatch):
    plan = make_plan(tmp_path)
    monkeypatch.setenv(PLAN_DB_ENV, str(plan.plan_db))
    return plan


def _parse(ws):
    return parse_client(ws.store_data(), "")


def _set_feature(ws, on):
    with ws.store() as s:
        mc.set_feature(s, KEY, on)


def test_off_by_default_ignores_stored_properties(ws):
    base = plain(_parse(ws))
    with ws.store() as s:
        s.rental.replace_all(copy.deepcopy([rf.PROFITABLE]))
    c = _parse(ws)
    assert "rental_properties" not in c and "mfs_lived_apart" not in c
    assert plain(c) == base  # config byte-for-byte what it was without rental data
    assert active_rental_properties()[0]["name"] == "Duplex"  # data kept


def test_on_fills_config_from_the_store(ws):
    with ws.store() as s:
        s.rental.replace_all(copy.deepcopy([rf.PROFITABLE, rf.CONVERTED_HOME | {"name": "Our house"}]))
    _set_feature(ws, True)
    c = _parse(ws)
    props = c["rental_properties"]
    assert [p["name"] for p in props] == ["Duplex", "Our house"]
    assert props[0]["purchase_month"] == 6 and props[1]["conversion_month"] == 7  # stored / default month
    assert props[0]["improvements"] == [{"year": 2028, "amount": 27500.0, "month": 7}]
    assert "mfs_lived_apart" not in c


def test_on_with_no_properties_gives_an_empty_list(ws):
    _set_feature(ws, True)
    assert _parse(ws)["rental_properties"] == []


def test_household_mfs_lived_apart_row_is_passed_through(ws):
    _set_feature(ws, True)
    with ws.store() as s:
        s.set_value("Household", "", "mfs_lived_apart", "yes")
    assert _parse(ws)["mfs_lived_apart"] is True


def test_toggle_off_again_keeps_the_data_and_drops_the_input(ws):
    with ws.store() as s:
        s.rental.replace_all(copy.deepcopy([rf.PROFITABLE]))
    _set_feature(ws, True)
    assert len(_parse(ws)["rental_properties"]) == 1
    _set_feature(ws, False)
    assert "rental_properties" not in _parse(ws)
    with ws.store() as s:
        assert s.rental.names() == ["Duplex"]


def test_bad_stored_property_fails_the_build_only_when_on(ws):
    with ws.store() as s:
        s.rental.replace_all([{"name": "Draft"}])  # no purchase_price
    _parse(ws)
    _set_feature(ws, True)
    with pytest.raises(RentalPropertyInputError, match="purchase_price"):
        _parse(ws)
