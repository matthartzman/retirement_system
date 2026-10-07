"""Regression test for the reported ``/api/note-receivable/add`` 500.

Repro from the bug report: ``addOtherAssetItem()``, ``addNoteReceivable()`` and
``addEducation529Section()`` fired in the same JS tick.  They used to rewrite
``input/client_assets.csv`` alike; the note-receivable request returned 500 with
``PermissionError: [WinError 32]`` from the temp-file replace.

WP4.4a: the endpoints edit the plan rows through the active-plan edit context (one rows
transaction each), so the CSV file is only written back.

Asserting only "all three return 200" is not enough -- serialising just the
write would satisfy that while two of the three additions were silently
clobbered, because each request reads the plan, modifies its snapshot and
writes the whole thing back.  So these tests assert the additions survive.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

import src.server.app_core as app_core
from src.server import plan_routes
from tests.plan_fixture import make_plan


@pytest.fixture
def ws(tmp_path, monkeypatch):
    plan = make_plan(tmp_path / "ws")
    monkeypatch.setenv("RETIREMENT_SYSTEM_WORKSPACE_ROOT", str(plan.root))
    monkeypatch.delenv("RETIREMENT_SYSTEM_PLAN_DB", raising=False)
    monkeypatch.delenv("RETIREMENT_SYSTEM_CONFIG_FILE", raising=False)
    monkeypatch.setattr(app_core, "CSV_PATH", plan.input_dir / "client_data.csv")
    return plan


def _service():
    return plan_routes._strategy_asset_feature_service()


def _run_concurrently(fns):
    start = threading.Barrier(len(fns))

    def wrapped(fn):
        def run():
            start.wait(timeout=10)
            return fn()

        return run

    with ThreadPoolExecutor(max_workers=len(fns)) as pool:
        futures = [pool.submit(wrapped(fn)) for fn in fns]
        return [f.result(timeout=30) for f in futures]


def _sections(ws):
    with ws.store(readonly=True) as store:
        return {(r["section"], r["subsection"]) for r in store.all_rows()}


def _subsections(ws, section):
    with ws.store(readonly=True) as store:
        return [r["subsection"] for r in store.rows(section)]


def test_concurrent_asset_adds_all_succeed_and_all_survive(ws):
    service = _service()
    before = {s: set(_subsections(ws, s)) for s in ("Other Assets", "Note Receivable", "Education Funding")}

    results = _run_concurrently([
        lambda: service.add_other_asset_payload({"asset_type": "Auto"}),
        lambda: service.add_note_receivable_payload({"name": "Seller Note"}),
        lambda: service.add_education_529_payload(),
    ])

    statuses = [status for _payload, status in results]
    assert statuses == [200, 200, 200], f"an endpoint failed: {results}"
    for payload, _status in results:
        assert payload["section"] not in {sub for subs in before.values() for sub in subs}

    for section, (payload, _status) in zip(before, results):
        assert set(_subsections(ws, section)) - before[section] == {payload["section"]}


def test_concurrent_note_adds_do_not_collide_on_one_subsection_id(ws):
    """Concurrent adds that all read the same snapshot would all compute the same
    ``Note N`` and one would be clobbered."""
    service = _service()
    before = set(_subsections(ws, "Note Receivable"))

    results = _run_concurrently([
        lambda: service.add_note_receivable_payload({"name": "First"}),
        lambda: service.add_note_receivable_payload({"name": "Second"}),
        lambda: service.add_note_receivable_payload({"name": "Third"}),
    ])
    assert [status for _payload, status in results] == [200, 200, 200]

    added = {payload["section"] for payload, _status in results}
    assert len(added) == 3, f"two adds took the same subsection: {results}"
    assert set(_subsections(ws, "Note Receivable")) - before == added

    with ws.store(readonly=True) as store:
        names = sorted(r["value"] for r in store.rows("Note Receivable")
                       if r["label"] == "name" and r["subsection"] in added)
    assert names == ["First", "Second", "Third"], f"an add was lost: {names}"
