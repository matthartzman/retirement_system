"""#240 / WP8.4: Open demo / Exit demo / Reset demo over the plan registry (design F section 5A).

The demo plan (``demo.rpx``) and the user's plan are separate plan files, one active at a time.
Opening the demo creates ``demo.rpx`` from the bundled seed when it is missing and switches the
active plan to it; Exit demo switches back; Reset demo rebuilds ``demo.rpx`` from the seed. The
user's plan file is never modified, copied over or restored, and nothing is written into the seed.

Every test runs in its own workspace (``tmp_path``: plan file, ``local_state/app.db``, seed folder).
"""
import dataclasses
import hashlib
from pathlib import Path

import pytest

from src import active_plan, plan_registry
from src.server_services.demo_plan_service import DemoPlanService, DemoPlanServiceContext
from src.stores import PlanStore
from src.workspace_context import active_plan_id, workspace_output_dir

SEED = "client_spending_budget.recovery_seed.csv"
REAL_SEED_ROWS = [{"kind": "category", "key": "real_cat", "label": "Real", "annual_budget": "999"}]
HEADER = "section,subsection,label,value,units,notes\n"
ROOT = Path(__file__).resolve().parents[1]


def _make_plan(path: Path, marker: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with PlanStore.open(path) as store:
        store.set_value("Marker", "", "value", marker)
        store.spending.set_recovery_seed(REAL_SEED_ROWS)


def _plan_view(path: Path):
    with PlanStore.open(path, create=False, readonly=True) as store:
        return store.sectioned_data()


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _seed_keys() -> list[str]:
    with active_plan.active_plan_store(readonly=True) as store:
        return [r["key"] for r in store.spending.recovery_seed()]


def _make_seed(demo_dir: Path) -> None:
    demo_dir.mkdir(parents=True, exist_ok=True)
    (demo_dir / "client_household.csv").write_text(
        HEADER + "Household,,member_1_name,Demo Person,text,\nHousehold,,state,TX,text,\n", encoding="utf-8")
    (demo_dir / "client_data.csv").write_text(HEADER + "Scenarios,Base,growth,1,pct,\n", encoding="utf-8")
    (demo_dir / SEED).write_text("kind,key,label,annual_budget\ncategory,demo_cat,Demo,10\n", encoding="utf-8")


@pytest.fixture
def ws(tmp_path, monkeypatch):
    monkeypatch.setenv("RETIREMENT_SYSTEM_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.delenv(active_plan.PLAN_DB_ENV, raising=False)
    monkeypatch.delenv("RETIREMENT_SYSTEM_APP_DB", raising=False)
    plan_registry.invalidate()
    _make_plan(tmp_path / "plan.rpx", "real-plan")
    _make_seed(tmp_path / "input" / "demo")
    return tmp_path


def _service(ws: Path, **overrides):
    audits, switched = [], []
    ctx = DemoPlanServiceContext(
        demo_dir=lambda: ws / "input" / "demo",
        audit=lambda event, payload: audits.append((event, payload)),
        after_switch=lambda path: switched.append(Path(path)),
    )
    return DemoPlanService(dataclasses.replace(ctx, **overrides)), audits, switched


def _marker():
    return active_plan.peek_plan_data().get("Marker", {}).get("", {}).get("value")


def test_first_use_registers_the_workspace_plan_and_the_demo_is_inactive(ws):
    service, *_ = _service(ws)
    status = service.status_payload()
    assert status["active"] is False and status["demo_exists"] is False
    assert status["plan"]["kind"] == "user" and status["plan"]["plan_id"] == "plan"
    assert active_plan.active_plan_path() == ws / "plan.rpx"


def test_open_demo_creates_demo_rpx_from_the_seed_and_switches_to_it(ws):
    real = ws / "plan.rpx"
    before = _digest(real)
    service, audits, switched = _service(ws)
    out = service.open_demo_payload()
    assert out["success"] is True and out["created"] is True and out["plan"]["kind"] == "demo"
    demo = ws / "demo.rpx"
    assert active_plan.active_plan_path() == demo and switched == [demo]
    assert active_plan.peek_plan_data()["Household"][""]["member_1_name"] == "Demo Person"
    assert _seed_keys() == ["demo_cat"]
    assert service.status_payload()["active"] is True
    # the user's plan file is untouched; none of the old swap artefacts exist
    assert _digest(real) == before
    assert not list(ws.rglob("*.before_demo")) and not (ws / "local_state" / "demo_mode_marker.json").exists()
    assert not (ws / "local_state" / "demo_plan").exists()
    assert ("demo_plan_opened", {"plan_id": "demo", "created": True}) in audits


def test_exit_demo_switches_back_and_never_touches_the_user_plan(ws):
    real = ws / "plan.rpx"
    before = _digest(real)
    service, _, switched = _service(ws)
    service.open_demo_payload()
    with active_plan.edit_active_plan() as edit:  # an edit made while in the demo
        edit.store.set_value("Household", "", "member_1_name", "Demo Edit")
    out = service.exit_demo_payload()
    assert out["success"] is True and out["restored"] is True and out["plan"]["plan_id"] == "plan"
    assert active_plan.active_plan_path() == real and switched[-1] == real
    assert _marker() == "real-plan" and _seed_keys() == ["real_cat"]
    assert _digest(real) == before
    # the demo edit stays in demo.rpx for next time
    assert _plan_view(ws / "demo.rpx")["Household"][""]["member_1_name"] == "Demo Edit"
    out = service.open_demo_payload()
    assert out["created"] is False and active_plan.peek_plan_data()["Household"][""]["member_1_name"] == "Demo Edit"


def test_exit_demo_when_no_demo_is_active_is_a_safe_noop(ws):
    service, *_ = _service(ws)
    out = service.exit_demo_payload()
    assert out["success"] is True and out["restored"] is False
    assert active_plan.active_plan_path() == ws / "plan.rpx"


def test_exit_demo_returns_to_the_plan_that_was_active_before_it(ws):
    other = ws / "cases" / "Second.rpx"
    _make_plan(other, "second-plan")
    plan_registry.activate(plan_registry.register_plan_file(other)["plan_id"])
    service, *_ = _service(ws)
    service.open_demo_payload()
    service.exit_demo_payload()
    assert active_plan.active_plan_path() == other and _marker() == "second-plan"


def test_reset_demo_rebuilds_the_demo_from_the_seed_even_while_open(ws):
    real = ws / "plan.rpx"
    before = _digest(real)
    seed_before = {p.name: p.read_bytes() for p in (ws / "input" / "demo").iterdir()}
    service, _, switched = _service(ws)
    service.open_demo_payload()
    with active_plan.edit_active_plan() as edit:
        edit.store.set_value("Household", "", "member_1_name", "Demo Edit")
    out = service.reset_demo_payload()
    assert out == {"success": True, "reset": True}
    assert active_plan.active_plan_path() == ws / "demo.rpx"
    assert active_plan.peek_plan_data()["Household"][""]["member_1_name"] == "Demo Person"
    assert switched[-1] == ws / "demo.rpx"
    assert _digest(real) == before
    assert {p.name: p.read_bytes() for p in (ws / "input" / "demo").iterdir()} == seed_before


def test_reset_demo_before_any_open_creates_the_demo_without_switching(ws):
    service, *_ = _service(ws)
    assert service.reset_demo_payload()["success"] is True
    assert (ws / "demo.rpx").is_file() and active_plan.active_plan_path() == ws / "plan.rpx"


def test_a_seed_that_is_not_a_plan_changes_nothing(ws):
    empty = ws / "empty_seed"
    empty.mkdir()
    service, *_ = _service(ws, demo_dir=lambda: empty)
    with pytest.raises(FileNotFoundError):
        service.open_demo_payload()
    assert active_plan.active_plan_path() == ws / "plan.rpx" and not (ws / "demo.rpx").exists()


def test_demo_builds_write_to_their_own_output_folder(ws):
    assert active_plan_id() == "plan"
    real_out = workspace_output_dir()
    service, *_ = _service(ws)
    service.open_demo_payload()
    assert active_plan_id() == "demo"
    assert workspace_output_dir() == real_out.parent / "demo" != real_out
    env = active_plan.plan_db_env({})
    assert env[active_plan.PLAN_ID_ENV] == "demo" and env[active_plan.PLAN_DB_ENV] == str(ws / "demo.rpx")


def test_the_real_demo_folder_builds_the_demo_plan_equal_to_the_loader(ws):
    """The shipped input/demo household is the demo plan's seed: the importer's rows equal the
    legacy loader's view (what ``tests.plan_fixture.make_plan('demo')`` also guarantees)."""
    from src.data_io import load_csv
    from src.plan_label_rules import dropped_at_load

    real_demo = ROOT / "input" / "demo"
    service, *_ = _service(ws, demo_dir=lambda: real_demo)
    service.open_demo_payload()
    view = _plan_view(ws / "demo.rpx")
    assert view == load_csv(real_demo / "client_data.csv")
    assert not any(dropped_at_load(s, sub, lbl) for s, subs in view.items() for sub, vals in subs.items() for lbl in vals)


def test_demo_ytd_fixture_files_exist_and_are_fictional():
    demo_dir = ROOT / "input" / "demo"
    for name in ("ytd_transactions.csv", "ytd_account_setup.csv", "ytd_import_history.csv"):
        p = demo_dir / name
        assert p.exists(), f"input/demo/{name} is missing"
        text = p.read_text(encoding="utf-8-sig")
        assert text.strip(), f"input/demo/{name} is empty"
        for real_marker in ("Max and Benny", "Hartzman", "RedMane"):
            assert real_marker not in text, f"input/demo/{name} leaks real data: {real_marker!r}"


def test_no_demo_file_swapping_code_is_left():
    offenders = []
    for f in (ROOT / "src").rglob("*.py"):
        if "legacy_conversion" in f.parts:
            continue  # the one-time converter names the old files it reads
        text = f.read_text(encoding="utf-8")
        for needle in ("before_demo", "demo_mode_marker", "DEMO_SLOT_DIR", "restore_current_payload"):
            if needle in text:
                offenders.append(f"{f.relative_to(ROOT)}: {needle}")
    assert offenders == []


def test_the_routes_wire_the_demo_service_and_the_plan_switch_hook():
    from src.server import plan_routes

    ctx = plan_routes._demo_plan_feature_service().context
    assert ctx.after_switch is plan_routes._after_plan_switch
    assert plan_routes._plan_file_feature_service().ctx.after_switch is plan_routes._after_plan_switch
    rules = {r.rule for r in plan_routes.app.url_map.iter_rules()}
    assert {"/api/plan/open-demo", "/api/plan/exit-demo", "/api/plan/reset-demo", "/api/plan/demo-status",
            "/api/plans", "/api/plans/switch", "/api/plans/rename", "/api/plans/forget"} <= rules
    assert "/api/plan/restore-current" not in rules


HEADERS = {"X-User-Role": "admin"}


def test_plan_registry_routes_list_switch_rename_forget_and_demo(ws):
    from src.server import app

    client = app.test_client()
    listing = client.get("/api/plans", headers=HEADERS).get_json()
    assert listing["success"] is True and listing["active"]["plan_id"] == "plan" and listing["demo_active"] is False

    opened = client.post("/api/plan/open-demo", headers=HEADERS, json={}).get_json()
    assert opened["success"] is True, opened
    listing = client.get("/api/plans", headers=HEADERS).get_json()
    assert listing["demo_active"] is True and {p["plan_id"] for p in listing["plans"]} == {"plan", "demo"}
    assert client.get("/api/plan/demo-status", headers=HEADERS).get_json()["active"] is True

    out = client.post("/api/plans/forget", headers=HEADERS, json={"plan_id": "demo"})
    assert out.status_code == 400 and out.get_json()["success"] is False  # the active plan stays

    out = client.post("/api/plan/exit-demo", headers=HEADERS, json={}).get_json()
    assert out["success"] is True and out["restored"] is True
    out = client.post("/api/plans/switch", headers=HEADERS, json={"plan_id": "demo"}).get_json()
    assert out["success"] is True and out["active"]["plan_id"] == "demo"
    out = client.post("/api/plans/switch", headers=HEADERS, json={"plan_id": "plan"}).get_json()
    assert out["active"]["plan_id"] == "plan"
    out = client.post("/api/plans/rename", headers=HEADERS, json={"plan_id": "plan", "name": "Our Plan"}).get_json()
    assert out["active"]["name"] == "Our Plan"
    out = client.post("/api/plans/forget", headers=HEADERS, json={"plan_id": "demo"}).get_json()
    assert out["success"] is True and [p["plan_id"] for p in out["plans"]] == ["plan"]
    assert (ws / "demo.rpx").is_file()  # forgetting leaves the file
    bad = client.post("/api/plans/switch", headers=HEADERS, json={"plan_id": "nope"})
    assert bad.status_code == 400 and bad.get_json()["success"] is False
