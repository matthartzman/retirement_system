"""Create, duplicate, rename and delete plans in one user's workspace (multi-plan design, sections 2-3)."""
from __future__ import annotations

import pytest

from src import app_state, plan_limits, plan_manage, plan_registry
from src.active_plan import PlanStore


@pytest.fixture()
def ws(tmp_path, monkeypatch):
    monkeypatch.setenv("RETIREMENT_SYSTEM_REMOTE_MODE", "1")
    monkeypatch.setenv("RETIREMENT_SYSTEM_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.delenv(plan_limits.MAX_PLANS_ENV, raising=False)
    monkeypatch.delenv(plan_limits.QUOTA_ENV, raising=False)
    plan_registry.invalidate()
    plan_limits.invalidate()
    return tmp_path


def _rows(path):
    with PlanStore.open(path, create=False, readonly=True) as s:
        return len(s.all_rows())


def test_create_demo_copy_is_server_named_and_registered(ws):
    rec = plan_manage.create_plan("What if: retire at 60", "demo")
    assert rec["kind"] == "user" and rec["name"] == "What if: retire at 60"
    assert rec["path"] == str(ws / "plans" / f"{rec['plan_id']}.rpx")
    assert len(rec["plan_id"]) == 32 and _rows(rec["path"]) > 0


def test_create_blank_has_the_structure_but_no_household_facts(ws):
    demo = plan_manage.create_plan("D", "demo")
    blank = plan_manage.create_plan("B", "blank")
    with PlanStore.open(blank["path"], create=False, readonly=True) as b, \
            PlanStore.open(demo["path"], create=False, readonly=True) as d:
        assert len(b.all_rows()) == len(d.all_rows())
        assert [r["value"] for r in b.all_rows()] != [r["value"] for r in d.all_rows()]


def test_create_rejects_an_unknown_source(ws):
    with pytest.raises(plan_registry.PlanRegistryError):
        plan_manage.create_plan("X", "../../etc")


@pytest.mark.parametrize("raw, expected", [
    ("  My   plan \t one ", "My plan one"),
    ("a\u202eb\x00c\x01d", "abcd"),
    ("e\u0301", "\u00e9"),
    ("x" * 500, "x" * 60),
])
def test_names_are_normalised(raw, expected):
    assert plan_manage.normalize_name(raw) == expected


@pytest.mark.parametrize("bad", ["", "   ", "\x00\u202e", None])
def test_empty_names_are_refused(bad):
    with pytest.raises(plan_registry.PlanRegistryError):
        plan_manage.normalize_name(bad)


def test_hostile_names_never_reach_the_file_system(ws):
    for name in ("..\\..\\evil", "../x", "CON", "a/b:c*?", "x." * 40):
        rec = plan_manage.create_plan(name, "blank")
        assert rec["path"] == str(ws / "plans" / f"{rec['plan_id']}.rpx")
    assert sorted(p.suffix for p in (ws / "plans").iterdir()) == [".rpx"] * 5


def test_create_and_duplicate_make_names_unique_case_insensitively(ws):
    a = plan_manage.create_plan("Base", "demo")
    b = plan_manage.create_plan("base", "blank")
    c = plan_manage.duplicate_plan(a["plan_id"])
    assert (a["name"], b["name"], c["name"]) == ("Base", "base (2)", "Base (copy)")
    d = plan_manage.duplicate_plan(a["plan_id"])
    assert d["name"] == "Base (copy) (2)"


def test_rename_refuses_a_clash_and_normalises(ws):
    a = plan_manage.create_plan("One", "demo")
    b = plan_manage.create_plan("Two", "demo")
    with pytest.raises(plan_registry.PlanRegistryError, match="already"):
        plan_manage.rename_plan(b["plan_id"], " one ")
    assert plan_manage.rename_plan(b["plan_id"], "  Two  b ")["name"] == "Two b"
    assert plan_manage.rename_plan(a["plan_id"], "ONE")["name"] == "ONE"  # its own name is not a clash


def test_duplicate_is_an_independent_copy_and_stays_on_the_current_plan(ws):
    a = plan_manage.create_plan("A", "demo")
    plan_registry.activate(a["plan_id"], check=False)
    b = plan_manage.duplicate_plan(a["plan_id"])
    assert plan_registry.active_record()["plan_id"] == a["plan_id"]
    assert b["path"] != a["path"] and _rows(b["path"]) == _rows(a["path"])
    with PlanStore.open(b["path"]) as s:
        first = s.all_rows()[0]
        s.set_row(first["row_id"], value="changed-in-copy")
    with PlanStore.open(a["path"], create=False, readonly=True) as s:
        assert s.all_rows()[0]["value"] != "changed-in-copy"


def test_limits_refuse_create_and_duplicate_and_change_nothing(ws, monkeypatch):
    a = plan_manage.create_plan("A", "demo")
    monkeypatch.setenv(plan_limits.MAX_PLANS_ENV, str(len(plan_limits._counted_plans())))
    before = sorted(p.name for p in (ws / "plans").iterdir())
    with pytest.raises(plan_limits.PlanLimitError):
        plan_manage.create_plan("B", "blank")
    with pytest.raises(plan_limits.PlanLimitError):
        plan_manage.duplicate_plan(a["plan_id"])
    assert sorted(p.name for p in (ws / "plans").iterdir()) == before


def test_delete_needs_the_typed_name_and_removes_file_and_outputs(ws):
    a = plan_manage.create_plan("Keep", "demo")
    b = plan_manage.create_plan("Scratch", "demo")
    plan_registry.activate(a["plan_id"], check=False)
    out = ws / "output" / "plans" / b["plan_id"]
    out.mkdir(parents=True)
    (out / "r.xlsx").write_bytes(b"x")
    with pytest.raises(plan_registry.PlanRegistryError, match="name"):
        plan_manage.delete_plan(b["plan_id"], confirm_name="wrong")
    assert (ws / "plans" / f"{b['plan_id']}.rpx").exists()
    plan_manage.delete_plan(b["plan_id"], confirm_name="scratch")
    assert not (ws / "plans" / f"{b['plan_id']}.rpx").exists() and not out.exists()
    assert b["plan_id"] not in [p["plan_id"] for p in plan_registry.list_plans()]


def test_delete_refuses_active_demo_and_running_build(ws):
    a = plan_manage.create_plan("A", "demo")
    b = plan_manage.create_plan("B", "demo")
    plan_registry.activate(a["plan_id"], check=False)
    with pytest.raises(plan_registry.PlanRegistryError, match="active"):
        plan_manage.delete_plan(a["plan_id"], confirm_name="A")
    with pytest.raises(plan_registry.PlanRegistryError, match="build"):
        plan_manage.delete_plan(b["plan_id"], confirm_name="B", build_running=True)
    demo = plan_registry.register_plan_file(ws / "demo.rpx", name="Demo", kind="demo", plan_id="demo")
    with pytest.raises(plan_registry.PlanRegistryError, match="demo"):
        plan_manage.delete_plan(demo["plan_id"], confirm_name="Demo")
    assert (ws / "plans" / f"{b['plan_id']}.rpx").exists()


def test_delete_refuses_the_last_user_plan(ws):
    only = plan_registry.active_record()  # the workspace plan.rpx, registered on first use
    other = plan_manage.create_plan("Other", "demo")
    plan_registry.activate(other["plan_id"], check=False)
    plan_manage.delete_plan(only["plan_id"], confirm_name=only["name"])
    demo = plan_registry.register_plan_file(ws / "demo.rpx", name="Demo", kind="demo", plan_id="demo")
    plan_registry.activate(demo["plan_id"], check=False)
    with pytest.raises(plan_registry.PlanRegistryError, match="last"):
        plan_manage.delete_plan(other["plan_id"], confirm_name="Other")


def test_unknown_malformed_and_foreign_ids_get_one_uniform_error(ws):
    plan_manage.create_plan("A", "demo")
    for bad in ("0" * 32, "../x", "\\x", "CON", "x" * 100, "", None, "\u00e9"):
        for call in (lambda i: plan_manage.duplicate_plan(i), lambda i: plan_manage.rename_plan(i, "n"),
                     lambda i: plan_manage.delete_plan(i, confirm_name="n"), lambda i: plan_manage.plan_file_for(i)):
            with pytest.raises(plan_registry.PlanRegistryError) as exc:
                call(bad)
            assert str(exc.value) == plan_manage.NOT_FOUND


def test_a_registry_row_pointing_outside_the_workspace_is_refused(ws, tmp_path_factory):
    outside = tmp_path_factory.mktemp("other") / "victim.rpx"
    outside.write_bytes(b"SQLite format 3\x00" + b"0" * 100)
    with app_state.open_app_store() as store:
        store.register_plan(outside, "evil", "user", plan_id="evil")
    for call in (lambda: plan_manage.duplicate_plan("evil"), lambda: plan_manage.plan_file_for("evil")):
        with pytest.raises(plan_registry.PlanRegistryError):
            call()
    with pytest.raises(plan_registry.PlanRegistryError):
        plan_manage.delete_plan("evil", confirm_name="evil")
    assert outside.exists()
