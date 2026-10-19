"""A plan.db created before item 356 (schema v14) gains the liabilities payoff_month and
carry_zero columns on open, so saving or applying a liability change no longer fails with
"table liabilities has no column named payoff_month"."""
from src.stores import PlanStore, db
from src.stores.plan_store import PLAN_MIGRATIONS


def _cols(con):
    return [r[1] for r in con.execute("PRAGMA table_info(liabilities)")]


def test_v14_database_is_upgraded_with_payoff_columns(tmp_path):
    path = tmp_path / "old.rpx"
    con = db.connect(path)
    db.migrate(con, PLAN_MIGRATIONS[:14])
    assert "payoff_month" not in _cols(con)
    con.close()
    with PlanStore.open(path) as store:
        assert {"payoff_month", "carry_zero"} <= set(_cols(store._con))
        assert store.schema_version == len(PLAN_MIGRATIONS)


def test_new_database_has_payoff_columns(tmp_path):
    with PlanStore.open(tmp_path / "new.rpx") as store:
        assert {"payoff_month", "carry_zero"} <= set(_cols(store._con))
        assert store.schema_version == len(PLAN_MIGRATIONS)
