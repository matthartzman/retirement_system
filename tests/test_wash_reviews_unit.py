"""wash_reviews: the user's outcome for a wash flag, keyed by the sale grouping key so it survives a re-record."""
from __future__ import annotations

import sqlite3

import pytest

from src import active_plan, sales_service, sales_tax_year
from src.sales_ledger import ValidationError
from src.server import app, plan_routes
from src.stores import plan_store

KEY = "Matt_Trust|VTI|2026-06-10"


@pytest.fixture()
def input_dir(tmp_path):
    (tmp_path / "input").mkdir()
    with active_plan.workspace_store(tmp_path, write=True):
        pass
    return tmp_path / "input"


def test_not_wash_requires_reason(input_dir):
    with pytest.raises(ValidationError):
        sales_tax_year.set_wash_review(input_dir, KEY, "not_wash")
    with pytest.raises(ValidationError):
        sales_tax_year.set_wash_review(input_dir, KEY, "not_wash", reason="   ")
    sales_tax_year.set_wash_review(input_dir, KEY, "not_wash", reason="not substantially identical")
    with active_plan.workspace_store(input_dir.parent) as store:
        assert store.sales.reviews()[KEY]["reason"] == "not substantially identical"


def test_outcome_must_be_one_of_the_three(input_dir):
    with pytest.raises(ValidationError):
        sales_tax_year.set_wash_review(input_dir, KEY, "forgiven")


def test_clear_review(input_dir):
    sales_tax_year.set_wash_review(input_dir, KEY, "wash")
    sales_tax_year.set_wash_review(input_dir, KEY, "broker_reported", broker_amount=12.5)
    with active_plan.workspace_store(input_dir.parent) as store:
        assert store.sales.reviews()[KEY]["outcome"] == "broker_reported"
        assert store.sales.reviews()[KEY]["broker_amount"] == 12.5
    sales_tax_year.clear_wash_review(input_dir, KEY)
    with active_plan.workspace_store(input_dir.parent) as store:
        assert store.sales.reviews() == {}


def test_review_survives_requeue_and_rerecord(input_dir):
    """RF: voiding the rows and writing new ones (new sale_ids) leaves the review in place: it is keyed to the sale, not the rows."""
    row = dict(sale_date="2026-06-10", account="Matt_Trust", tax_class="taxable", symbol="VTI", shares=10, proceeds=900.0, fees=0.0,
               basis=1000.0, purchase_date="2025-01-02")
    first = sales_service.add_sale(input_dir, row)
    sales_tax_year.set_wash_review(input_dir, KEY, "not_wash", reason="other: test")
    sales_service.void_sale(input_dir, first["sale_id"])
    second = sales_service.add_sale(input_dir, row)
    assert second["sale_id"] != first["sale_id"]
    with active_plan.workspace_store(input_dir.parent) as store:
        assert store.sales.reviews()[KEY]["outcome"] == "not_wash"
    sales_tax_year.refresh_wash_flags(input_dir)                       # a scan does not drop it either
    with active_plan.workspace_store(input_dir.parent) as store:
        assert KEY in store.sales.reviews()


def test_migration_adds_table_on_existing_plan(input_dir):
    """A plan stored at schema 22 (no wash_reviews) gains the table when it is opened."""
    assert plan_store.PLAN_SCHEMA_VERSION == 23
    with active_plan.workspace_store(input_dir.parent, write=True) as store:
        path = store.path
    assert path is not None
    con = sqlite3.connect(path)
    assert con.execute("SELECT name FROM sqlite_master WHERE name = 'wash_reviews'").fetchone()
    con.execute("DROP TABLE wash_reviews")
    con.execute("PRAGMA user_version = 22")
    con.commit()
    con.close()
    with active_plan.workspace_store(input_dir.parent, write=True) as store:
        assert store.schema_version == 23
        assert store.sales.reviews() == {}
    con = sqlite3.connect(path)
    assert con.execute("SELECT name FROM sqlite_master WHERE name = 'wash_reviews'").fetchone()
    con.close()


def test_routes(input_dir, monkeypatch):
    monkeypatch.setattr(plan_routes, "_ytd_input_root", lambda: input_dir)
    c = app.test_client()
    bad = c.post("/api/sales/wash/review", json={"sale_key": KEY, "outcome": "not_wash"})
    assert bad.status_code == 400 and "reason" in bad.get_json()["error"]
    assert c.post("/api/sales/wash/review", json={"sale_key": KEY, "outcome": "wash"}).status_code == 200
    assert c.post("/api/sales/wash/review/clear", json={"sale_key": KEY}).status_code == 200
    with active_plan.workspace_store(input_dir.parent) as store:
        assert store.sales.reviews() == {}
