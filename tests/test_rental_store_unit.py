"""WP12.4: typed rental tables, ``store.rental`` and the v8 -> v9 migration."""
from __future__ import annotations

import copy

import pytest

from src.parsing.rental_properties import parse_rental_properties
from src.stores import PlanStore, ValidationError, db
from src.stores.plan_store import PLAN_MIGRATIONS
from tests import rental_fixtures as rf

TABLES = ("rental_properties", "rental_improvements", "rental_year_overrides")


@pytest.fixture
def store(tmp_path):
    with PlanStore.open(tmp_path / "plan.rpx") as s:
        yield s


FULL = {
    "name": "Duplex", "kind": "Standalone", "owner": "joint", "notes": "north side",
    "purchase_year": 2018, "purchase_month": 6, "purchase_price": 350000.0, "closing_costs": 10000.0,
    "land_share": 0.2, "current_value": 450000.0, "monthly_rent": 2500.0, "vacancy_rate": 0.05,
    "maintenance_pct": 0.08, "loan_balance": 200000.0, "loan_rate": 0.04, "loan_term_years": 22,
    "active_participation": False, "sale_year": 2035, "sale_month": 3,
    "improvements": [{"year": 2028, "month": 4, "amount": 27500.0, "description": "roof"},
                     {"year": 2030, "amount": 5000.0}],
    "overrides": [{"year": 2026, "gross_rent": 20000.0}, {"year": 2027, "operating_expenses": 9000.0, "notes": "repairs"}],
}


def test_round_trip_is_lossless_and_ordered(store):
    other = {"name": "Condo", "purchase_price": 1.0, "improvements": [], "overrides": []}
    assert store.rental.replace_all([FULL, other]) == 2
    got = store.rental.properties()
    assert [p["name"] for p in got] == ["Duplex", "Condo"]
    assert got[0] == FULL  # types, nested rows, False kept (not dropped as blank)
    assert got[1] == {"name": "Condo", "kind": "standalone", "purchase_price": 1.0, "improvements": [], "overrides": []}
    assert store.rental.count() == 2 and store.rental.names() == ["Duplex", "Condo"]


def test_source_forms_are_stored_typed(store):
    store.rental.replace_all([rf.LOSS_MAKING | {"overrides": {"2030": {"gross_rent": "1,000"}}}])
    p = store.rental.properties()[0]
    assert p["purchase_price"] == 500000.0 and p["management_pct"] == 0.08 and p["active_participation"] is True
    assert p["overrides"] == [{"year": 2030, "gross_rent": 1000.0}]
    with store._read() as con:
        assert con.execute("SELECT typeof(purchase_price), typeof(purchase_year) FROM rental_properties").fetchone()[:] == ("real", "integer")


def test_read_rows_feed_the_parser_like_the_originals(store):
    rows = [rf.PROFITABLE, rf.SALE_WITH_RECAPTURE, rf.LOSS_MAKING]
    store.rental.replace_all(copy.deepcopy(rows))
    assert parse_rental_properties({}, store.rental.properties()) == parse_rental_properties({}, copy.deepcopy(rows))


def test_blank_month_comes_back_blank_and_parser_defaults_to_july(store):
    store.rental.replace_all([{"name": "A", "purchase_price": 1, "improvements": [{"year": 2030, "amount": 10}]}])
    row = store.rental.properties()[0]
    assert "purchase_month" not in row and "month" not in row["improvements"][0]
    parsed = parse_rental_properties({}, [row])[0]
    assert parsed["purchase_month"] == 7 and parsed["improvements"][0]["month"] == 7


def test_incomplete_rows_are_kept_for_the_parser_to_judge(store):
    store.rental.replace_all([{"name": "Draft", "improvements": [{"year": 2030}]}])
    assert store.rental.count() == 1
    with pytest.raises(ValueError, match="purchase_price|amount"):
        parse_rental_properties({}, store.rental.properties())


def test_upsert_replaces_in_place_and_appends(store):
    store.rental.replace_all([{"name": "A", "monthly_rent": 1}, {"name": "B", "monthly_rent": 2}])
    store.rental.upsert({"name": "a", "monthly_rent": 9, "improvements": [{"year": 2030, "amount": 5}]})
    store.rental.upsert({"name": "C"})
    got = store.rental.properties()
    assert [p["name"] for p in got] == ["a", "B", "C"]
    assert got[0]["monthly_rent"] == 9 and got[0]["improvements"] == [{"year": 2030, "amount": 5.0}]
    assert store.rental.get("B")["monthly_rent"] == 2 and store.rental.get("zzz") is None


def test_delete_cascades(store):
    store.rental.replace_all([FULL, {"name": "B"}])
    assert store.rental.delete("duplex") is True and store.rental.delete("duplex") is False
    assert store.rental.names() == ["B"]
    with store._read() as con:
        assert [con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABLES[1:]] == [0, 0]


def test_replace_all_replaces_everything(store):
    store.rental.replace_all([FULL])
    store.rental.replace_all([{"name": "Only"}])
    assert store.rental.names() == ["Only"]
    with store._read() as con:
        assert con.execute("SELECT COUNT(*) FROM rental_improvements").fetchone()[0] == 0
    store.rental.replace_all([])
    assert store.rental.count() == 0


@pytest.mark.parametrize("bad, msg", [
    ({"name": ""}, "name is required"),
    ({"name": "A", "purchase_price": "lots"}, "purchase_price must be a number"),
    ({"name": "A", "purchase_year": 2020.5}, "whole number"),
    ({"name": "A", "active_participation": "maybe"}, "yes or no"),
    ({"name": "A", "typo_field": 1}, "unknown field"),
    ({"name": "A", "improvements": [{"year": 2030, "bogus": 1}]}, "unknown field"),
    ({"name": "A", "overrides": [{"gross_rent": 1}]}, "year is required"),
    ({"name": "A", "overrides": [{"year": 2030}, {"year": 2030}]}, "two overrides"),
    ({"name": "A", "monthly_rent": float("nan")}, "finite"),
])
def test_bad_rows_are_refused_and_leave_the_old_set(store, bad, msg):
    store.rental.replace_all([{"name": "Keep"}])
    with pytest.raises(ValidationError, match=msg):
        store.rental.replace_all([bad])
    assert store.rental.names() == ["Keep"]


def test_duplicate_names_refused_ignoring_case(store):
    with pytest.raises(ValidationError, match="names must differ"):
        store.rental.replace_all([{"name": "A"}, {"name": "a"}])


def test_writes_join_the_enclosing_transaction(store):
    with pytest.raises(RuntimeError):
        with store.transaction():
            store.rental.replace_all([{"name": "A"}])
            raise RuntimeError("roll back")
    assert store.rental.count() == 0


def test_v8_file_upgrades_to_current_keeping_rows(tmp_path):
    p = tmp_path / "v8.rpx"
    con = db.connect(str(p))
    db.migrate(con, PLAN_MIGRATIONS[:8])
    con.execute("INSERT INTO plan_rows (section, sort_order) VALUES ('Household', 0)")
    con.execute("INSERT INTO holdings_lots (position, account) VALUES (0, 'A_IRA')")
    con.commit()
    assert db.get_version(con) == 8
    con.close()
    with PlanStore.open(p) as s:
        assert s.schema_version == len(PLAN_MIGRATIONS) == 11
        assert [r["section"] for r in s.all_rows()] == ["Household"] and s.holdings.rows()[0]["account"] == "A_IRA"
        assert s.rental.properties() == [] and s.rental.count() == 0
        s.rental.replace_all([FULL])
    with PlanStore.open(p, readonly=True) as s:
        assert s.rental.properties() == [FULL]


def test_new_file_has_the_three_tables(store):
    with store._read() as con:
        names = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert set(TABLES) <= names
