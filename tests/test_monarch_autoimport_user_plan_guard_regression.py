"""The Monarch import writes into whichever plan is active, so it may only run while the user's own plan is.

On 2026-11-15 at 03:00 the demo plan was the active plan. That night's job wrote the new
transactions, the account-setup rows and a full copy of the balance history into ``demo.rpx``; the
user's real plan never received them, and the extractor was told the run was delivered, so the
events were gone for good.

The job now writes only into a plan registered as kind ``user``, or one the registry does not know
(a bare workspace, a plan chosen by ``RETIREMENT_SYSTEM_PLAN_DB``). For a demo or saved-case plan it
skips the run, records why for the status panel, and acknowledges nothing to the extractor, so the
next run on the user's own plan delivers everything that was waiting.

Every test runs in its own workspace (``tmp_path``: plan files, ``local_state/app.db``, extractor
output). The transaction and balance values are synthetic.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src import active_plan, monarch_autoimport_job as job, monarch_autoupdate as mau, plan_registry, platform_runtime
from src.stores import PlanStore

EMPTY = {"transactions": 0, "balances": 0, "balance_imports": None}
DEMO_NAME = "Demo plan (Alex & Morgan)"


def _create_plan(path: Path) -> Path:
    with PlanStore.open(path):
        pass
    return path


def _contents(path: Path) -> dict:
    """What the Monarch import would have put in a plan file: its transactions and balance history."""
    with PlanStore.open(path, create=False, readonly=True) as store:
        return {
            "transactions": len(store.dataset("ytd_transactions").rows()),
            "balances": store.monarch.count(),
            "balance_imports": store.monarch.last_import(),
        }


def _switch_to(ws: Path, plan_id: str, kind: str, name: str) -> Path:
    path = _create_plan(ws / f"{plan_id}.rpx")
    plan_registry.register_plan_file(path, name=name, kind=kind, plan_id=plan_id)
    plan_registry.activate(plan_id, check=False)
    return path


@pytest.fixture
def ws(tmp_path, monkeypatch):
    """A workspace whose active plan is the user's own plan.rpx, with one pending Monarch
    transaction and a balances file dated today waiting in the extractor's output folder."""
    monkeypatch.setenv("RETIREMENT_SYSTEM_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.delenv(active_plan.PLAN_DB_ENV, raising=False)
    monkeypatch.delenv("RETIREMENT_SYSTEM_APP_DB", raising=False)
    plan_registry.invalidate()
    (tmp_path / "input").mkdir()
    (tmp_path / "local_state").mkdir()
    _create_plan(tmp_path / "plan.rpx")
    extractor = tmp_path / "Monarch Extractor"
    out = extractor / "output"
    out.mkdir(parents=True)
    (extractor / "monarch_extract.py").write_text("# stub: the job only checks that it exists\n", encoding="utf-8")
    (out / "new_transactions.csv").write_text(
        "run_id,id,date,merchant,category,account,amount\n"
        "run-1,mid-1,2026-03-04,Kroger,Groceries,Checking,-52.10\n",
        encoding="utf-8",
    )
    (out / "balances.csv").write_text(
        "date,account_key,account,balance\n"
        f"{platform_runtime.today().isoformat()},checking,Checking,1000.00\n",
        encoding="utf-8",
    )
    mau.save_policy(tmp_path, {"enabled": True, "transactions": True, "balances": True})
    return tmp_path


@pytest.fixture
def acknowledged(ws, monkeypatch):
    """The run ids the job told the extractor it had delivered (the real call starts a subprocess)."""
    calls: list[list[str]] = []
    monkeypatch.setattr(job, "_mark_runs_delivered", lambda extractor_dir, run_ids: calls.append(list(run_ids)) or [])
    return calls


@pytest.mark.parametrize("force", [False, True], ids=["scheduled", "import_now"])
@pytest.mark.parametrize("kind, name", [("demo", DEMO_NAME), ("case", "Retire at 62")])
def test_a_demo_or_saved_case_plan_receives_nothing(ws, kind, name, force):
    other = _switch_to(ws, "other", kind, name)
    result = job.run(ws, force=force)
    assert result["success"] is False and result["skipped"] is True
    assert result["skip_reason"] == "not_user_plan"
    assert name in result["error"]
    assert _contents(other) == EMPTY
    assert _contents(ws / "plan.rpx") == EMPTY  # and nothing was misdirected into the user's plan either


def test_the_refusal_is_visible_in_the_status_panel(ws):
    _switch_to(ws, "demo", "demo", DEMO_NAME)
    job.run(ws)
    status = mau.load_status(ws)
    assert status["success"] is False and DEMO_NAME in status["errors"][0]
    assert mau.load_balances_status(ws)["status"] == "skipped"


def test_nothing_is_acknowledged_while_refused_and_the_next_run_delivers_it(ws, acknowledged):
    _switch_to(ws, "demo", "demo", DEMO_NAME)
    job.run(ws)
    assert acknowledged == []  # the extractor still holds the event as pending
    plan_registry.activate("plan", check=False)  # back on the user's own plan
    result = job.run(ws)
    assert result["success"] is True and result["upsert"]["added"] == 1
    assert acknowledged == [["run-1"]]
    own = _contents(ws / "plan.rpx")
    assert own["transactions"] == 1 and own["balances"] == 1 and own["balance_imports"]["status"] == "ok"


def test_with_both_steps_off_there_is_nothing_to_refuse(ws):
    # No step would write anything, so a demo plan being open is not a failure to report.
    _switch_to(ws, "demo", "demo", DEMO_NAME)
    mau.save_policy(ws, {"transactions": False, "balances": False})
    result = job.run(ws)
    assert result["success"] is True and result["skip_reason"] == "transactions off"
    assert mau.load_status(ws) is None


def test_the_users_own_plan_is_imported_into(ws):
    result = job.run(ws)
    assert result["success"] is True and result["upsert"]["added"] == 1
    assert result["balances"]["status"] == "ok"


def test_a_plan_the_registry_does_not_know_is_written(ws, monkeypatch):
    scratch = _create_plan(ws / "scratch.rpx")
    monkeypatch.setenv(active_plan.PLAN_DB_ENV, str(scratch))  # an override, not in the registry
    result = job.run(ws)
    assert result["success"] is True
    assert _contents(scratch)["transactions"] == 1
