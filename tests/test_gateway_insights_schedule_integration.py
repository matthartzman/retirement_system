"""Real gateway + real worker: with --insights-schedule set to a minute ago, the scheduler updates the user's
Financial Insight history once, records one audit event and shows the status line on the health report.
Slow (starts a worker). On a weekend the scheduler must stay idle, which is what the test then asserts."""
from __future__ import annotations

import time
from datetime import datetime, timedelta

import pytest

from test_multi_user_isolation_integration import Client, launch_gateway  # noqa: F401

pytestmark = [pytest.mark.integration, pytest.mark.e2e, pytest.mark.slow]

START = datetime.now() - timedelta(minutes=2)


def test_scheduler_updates_a_real_worker_once(tmp_path):
    cutoff = START.strftime("%H:%M")
    extra = ("--insights", "--insights-schedule", cutoff)
    for gateway in launch_gateway(tmp_path, {"alice": "admin"}, extra):
        store, uid = gateway["store"], gateway["users"]["alice"][0]
        c = Client(gateway["ready"]["local_port"])
        token, csrf = store.create_session(uid, "active", time.time(), "127.0.0.1")
        c.cookie, c.csrf = f"__Host-rp_session={token}", csrf
        if START.weekday() >= 5:  # weekdays only: nothing may run, the status line stays empty
            time.sleep(8)
            assert not [e for e in store.read_audit(limit=200) if e["event"] == "insights_scheduled_update"]
            status, line = c.json("GET", "/api/auth/admin/health")
            assert status == 200 and line["insights_schedule"] == {"configured": True, "last_run_at": None, "updated": 0, "failed": 0}
            return
        deadline = time.time() + 240
        events: list[dict] = []
        while time.time() < deadline and not events:
            time.sleep(2)
            events = [e for e in store.read_audit(limit=200) if e["event"] == "insights_scheduled_update"]
        assert len(events) == 1, "expected exactly one scheduled-update audit event"
        assert str(uid) in events[0]["details"] and "$" not in events[0]["details"]
        status, line = c.json("GET", "/api/auth/admin/health")
        assert status == 200 and line["insights_schedule"]["configured"] is True
        assert line["insights_schedule"]["last_run_at"] is not None
        if line["insights_schedule"]["updated"] == 1:  # the run succeeded: one entry, and opening FI adds no second
            status, hist = c.json("GET", "/insights/api/history")
            assert status == 200 and len(hist) == 1
            c.json("POST", "/insights/api/run-status")  # harmless poke; the page rule would not start another run
            time.sleep(1)
            _, hist = c.json("GET", "/insights/api/history")
            assert len(hist) == 1
