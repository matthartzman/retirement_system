"""WP2.2: AppStore (app.db): plan registry, active plan, settings."""
import math
import re

import pytest

from src.stores import (
    APP_SCHEMA_VERSION,
    PLAN_KINDS,
    AppStore,
    IntegrityError,
    NotFoundError,
    PlanStore,
    StoreError,
    ValidationError,
)
from src.stores.app_store import APP_APPLICATION_ID


def _ticker():
    n = iter(range(1, 10_000))
    return lambda: f"2026-02-01T00:00:{next(n):02d}+00:00"


@pytest.fixture
def app():
    s = AppStore.open(":memory:", clock=_ticker())
    yield s
    s.close()


@pytest.fixture
def plans_dir(tmp_path):
    return tmp_path / "plans"


def test_fresh_schema(app):
    assert app.schema_version == APP_SCHEMA_VERSION == 1
    assert app._con.execute("PRAGMA application_id").fetchone()[0] == APP_APPLICATION_ID
    assert app.list_plans() == [] and app.active_plan() is None and app.settings() == {}
    assert PLAN_KINDS == ("user", "demo", "case")


def test_register_get_list(app, plans_dir):
    mine = app.register_plan(plans_dir / "My Plan.rpx", "My Plan")
    assert re.fullmatch(r"[0-9a-f]{32}", mine["plan_id"])
    assert mine == {"plan_id": mine["plan_id"], "path": str(plans_dir / "My Plan.rpx"), "name": "My Plan",
                    "kind": "user", "last_opened": None}
    demo = app.register_plan(str(plans_dir / "demo.rpx"), "Demo", "demo", plan_id="demo")
    case = app.register_plan(plans_dir / "case.rpx", "A case", kind="case", plan_id="case-1")
    assert app.get_plan("demo") == demo
    assert [p["plan_id"] for p in app.list_plans()] == ["case-1", "demo", mine["plan_id"]]  # by name
    assert app.list_plans(kind="demo") == [demo]
    assert app.list_plans(kind="case") == [case]
    app.set_active_plan("demo")
    app.set_active_plan(mine["plan_id"])
    assert [p["plan_id"] for p in app.list_plans()] == [mine["plan_id"], "demo", "case-1"]  # recent first


def test_register_rejections(app, plans_dir):
    app.register_plan(plans_dir / "a.rpx", "A", plan_id="a")
    with pytest.raises(IntegrityError):
        app.register_plan(plans_dir / "other.rpx", "dup id", plan_id="a")
    with pytest.raises(IntegrityError):
        app.register_plan(plans_dir / "a.rpx", "dup path")
    with pytest.raises(ValidationError):
        app.register_plan("relative/a.rpx", "rel")
    with pytest.raises(ValidationError):
        app.register_plan(plans_dir / "b.rpx", "B", kind="saved")
    with pytest.raises(ValidationError):
        app.register_plan(plans_dir / "b.rpx", "  ")
    with pytest.raises(ValidationError):
        app.register_plan(plans_dir / "b.rpx", "B", plan_id="../escape")
    with pytest.raises(ValidationError):
        app.list_plans(kind="nope")
    with pytest.raises(NotFoundError):
        app.get_plan("missing")
    assert len(app.list_plans()) == 1


def test_update_plan(app, plans_dir):
    app.register_plan(plans_dir / "a.rpx", "A", plan_id="a")
    app.register_plan(plans_dir / "b.rpx", "B", plan_id="b")
    out = app.update_plan("a", name="A2", path=plans_dir / "a2.rpx")
    assert out["name"] == "A2" and out["path"] == str(plans_dir / "a2.rpx")
    with pytest.raises(IntegrityError):
        app.update_plan("a", path=plans_dir / "b.rpx")
    with pytest.raises(ValidationError):
        app.update_plan("a")
    with pytest.raises(NotFoundError):
        app.update_plan("zzz", name="x")


def test_active_plan_switching(app, plans_dir):
    app.register_plan(plans_dir / "mine.rpx", "Mine", plan_id="mine")
    app.register_plan(plans_dir / "demo.rpx", "Demo", "demo", plan_id="demo")
    assert app.active_plan() is None
    rec = app.set_active_plan("demo")
    assert rec["last_opened"] == "2026-02-01T00:00:01+00:00"
    assert app.active_plan() == rec
    app.set_active_plan("mine")  # exit demo
    assert app.active_plan()["plan_id"] == "mine"
    assert app._con.execute("SELECT count(*) FROM active_plan").fetchone()[0] == 1
    with pytest.raises(NotFoundError):
        app.set_active_plan("ghost")
    assert app.active_plan()["plan_id"] == "mine"  # failed switch changed nothing


def test_remove_plan(app, plans_dir):
    app.register_plan(plans_dir / "mine.rpx", "Mine", plan_id="mine")
    app.register_plan(plans_dir / "demo.rpx", "Demo", "demo", plan_id="demo")
    app.set_active_plan("mine")
    with pytest.raises(ValidationError, match="active"):
        app.remove_plan("mine")
    app.remove_plan("demo")
    with pytest.raises(NotFoundError):
        app.remove_plan("demo")
    app.clear_active_plan()
    assert app.active_plan() is None
    app.remove_plan("mine")
    assert app.list_plans() == []


def test_active_plan_fk_backstop(app, plans_dir):
    app.register_plan(plans_dir / "m.rpx", "M", plan_id="m")
    app.set_active_plan("m")
    with pytest.raises(IntegrityError):
        with app.transaction() as s:
            s._con.execute("DELETE FROM plan_registry WHERE plan_id = 'm'")
    assert app.active_plan()["plan_id"] == "m"


def test_settings_roundtrip(app):
    assert app.get_setting("missing") is None
    assert app.get_setting("missing", 7) == 7
    values = {"flag": True, "n": 3, "x": 1.5, "s": "é", "none": None, "list": [1, "a"], "obj": {"b": 1, "a": [2]}}
    for k, v in values.items():
        app.set_setting(k, v)
    for k, v in values.items():
        assert app.get_setting(k) == v
    assert app.get_setting("none", "dflt") is None  # stored null is not "missing"
    assert app.settings() == dict(sorted(values.items()))
    assert list(app.settings()) == sorted(values)
    app.set_setting("n", 4)
    assert app.get_setting("n") == 4
    assert app.delete_setting("n") is True
    assert app.delete_setting("n") is False
    assert app._con.execute("SELECT value FROM settings WHERE key='obj'").fetchone()[0] == '{"a":[2],"b":1}'


@pytest.mark.parametrize("bad", [math.nan, math.inf, object(), {1, 2}, b"x"])
def test_settings_rejects_non_json(app, bad):
    with pytest.raises(ValidationError):
        app.set_setting("k", bad)
    assert app.get_setting("k") is None


def test_settings_key_validation(app):
    for bad in ("", "   ", None, 3):
        with pytest.raises(ValidationError):
            app.set_setting(bad, 1)


def test_transaction_groups_writes(app, plans_dir):
    with pytest.raises(RuntimeError):
        with app.transaction():
            app.register_plan(plans_dir / "x.rpx", "X", plan_id="x")
            app.set_active_plan("x")
            app.set_setting("k", 1)
            raise RuntimeError
    assert app.list_plans() == [] and app.active_plan() is None and app.get_setting("k") is None
    with app.transaction():
        app.register_plan(plans_dir / "x.rpx", "X", plan_id="x")
        app.set_active_plan("x")
    assert app.active_plan()["plan_id"] == "x"


def test_file_persistence_and_cross_open(tmp_path, plans_dir):
    p = tmp_path / "app.db"
    with AppStore.open(p) as a:
        a.register_plan(plans_dir / "m.rpx", "M", plan_id="m")
        a.set_active_plan("m")
        a.set_setting("theme", "dark")
    with AppStore.open(p, create=False) as a:
        assert a.active_plan()["plan_id"] == "m"
        assert a.get_setting("theme") == "dark"
    with AppStore.open(p, readonly=True) as a:
        assert a.get_plan("m")["name"] == "M"
        with pytest.raises(StoreError):
            a.set_setting("theme", "light")
    with pytest.raises(StoreError, match="not a valid plan.db"):
        PlanStore.open(p)
    rpx = tmp_path / "x.rpx"
    PlanStore.open(rpx).close()
    with pytest.raises(StoreError, match="not a valid app.db"):
        AppStore.open(rpx)
