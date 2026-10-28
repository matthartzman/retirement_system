"""A plan file created before the Tax Treatment / After-Tax Premium columns (schema v15) gains them
on open, so the Monarch import's reconcile step no longer fails with
"table ytd_account_setup has no column named Tax Treatment"."""
from src.stores import PlanStore, db
from src.stores.plan_store import PLAN_MIGRATIONS

NEW = {"Tax Treatment", "After-Tax Premium"}


def _cols(con):
    return [r[1] for r in con.execute("PRAGMA table_info(ytd_account_setup)")]


def test_v15_database_is_upgraded_with_tax_columns(tmp_path):
    path = tmp_path / "old.rpx"
    con = db.connect(path)
    db.migrate(con, PLAN_MIGRATIONS[:15])
    assert not NEW & set(_cols(con))
    con.close()
    with PlanStore.open(path) as store:
        assert NEW <= set(_cols(store._con))
        assert store.schema_version == len(PLAN_MIGRATIONS)


def test_v15_rows_survive_and_can_take_tax_values(tmp_path):
    path = tmp_path / "old.rpx"
    con = db.connect(path)
    db.migrate(con, PLAN_MIGRATIONS[:15])
    con.execute('INSERT INTO ytd_account_setup (position, "Account", "Role") VALUES (1, \'Cash\', \'cash\')')
    con.commit()
    con.close()
    with PlanStore.open(path) as store:
        rows = store.dataset("ytd_account_setup").rows()
        assert rows[0]["Account"] == "Cash" and rows[0]["Tax Treatment"] == ""
        store.dataset("ytd_account_setup").replace_all([{**rows[0], "Tax Treatment": "taxable"}])
        assert store.dataset("ytd_account_setup").rows()[0]["Tax Treatment"] == "taxable"


def test_new_database_has_tax_columns(tmp_path):
    with PlanStore.open(tmp_path / "new.rpx") as store:
        assert NEW <= set(_cols(store._con))
        assert store.schema_version == len(PLAN_MIGRATIONS)
