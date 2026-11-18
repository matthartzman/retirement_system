"""Scheduled per-user Financial Insight update (src/gateway/insights_schedule.py): fakes for the clock, the
supervisor, the worker HTTP calls and the user list. No worker, no network, no sleeping."""
from __future__ import annotations

import json
import shutil
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.gateway import health as gateway_health
from src.gateway import insights_schedule as sched
from src.gateway.supervisor import Endpoint, WorkerUnavailable

ROOT = Path(__file__).resolve().parents[1]
CUTOFF = sched.parse_cutoff("17:30")


def local(y, m, d, hh=17, mm=31) -> float:
    return datetime(y, m, d, hh, mm).timestamp()


WED = (2026, 11, 18)  # a Wednesday
SAT = (2026, 11, 21)


def iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class Clock:
    def __init__(self, now: float) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


class FakeSup:
    def __init__(self, busy=(), running=(), unavailable=()) -> None:
        self.busy, self.running, self.unavailable = set(busy), set(running), set(unavailable)
        self.released: list[int] = []

    def build_busy(self, uid):
        return uid in self.busy

    def is_running(self, uid):
        return uid in self.running

    def endpoint(self, uid):
        if uid in self.unavailable:
            raise WorkerUnavailable("down")
        return Endpoint(uid, 1000 + uid, 1, "tok")

    def release(self, uid, reason=""):
        self.released.append(uid)


class FakeWorkers:
    """Stands in for call_worker: per-user newest log entry, optional run-now failures, call and overlap log."""

    def __init__(self, clock: Clock, last_run: dict[int, str | None], fail=()) -> None:
        self.clock, self.last_run, self.fail = clock, dict(last_run), set(fail)
        self.calls: list[tuple[int, str, str]] = []
        self.active = self.max_active = 0
        self.lock = threading.Lock()

    def __call__(self, ep, method, path, *, body=None, timeout=10.0, content_type="application/json"):
        uid = ep.user_id
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            self.calls.append((uid, method, path))
        try:
            assert ep.token == "tok"
            if path == sched.RUN_STATUS_PATH:
                return 200, json.dumps({"running": False, "last_run_at": self.last_run.get(uid)}).encode()
            assert (method, path) == ("POST", sched.RUN_NOW_PATH)
            if uid in self.fail:
                return 500, b'{"success": false, "error": "private text"}'
            self.last_run[uid] = iso(self.clock())
            return 200, b'{"success": true}'
        finally:
            with self.lock:
                self.active -= 1

    def posts(self, uid=None):
        return [c for c in self.calls if c[1] == "POST" and (uid is None or c[0] == uid)]


def user(uid, **kw):
    return {"id": uid, "username": f"u{uid}", "kind": "member", "disabled": False, "expired": False, **kw}


def build(monkeypatch, users, last_run, *, now=None, sessions=None, audit=None, sup=None, fail=()):
    clock = Clock(now if now is not None else local(*WED))
    due = sched.last_session_end(clock.now) - 3600  # a log entry from before the last session
    stamp = {"due": iso(due), "current": iso(sched.last_session_end(clock.now) + 60)}
    workers = FakeWorkers(clock, {u: stamp.get(v, v) for u, v in last_run.items()}, fail=fail)
    monkeypatch.setattr(sched, "call_worker", workers)
    sup = sup or FakeSup()
    events: list[tuple[str, str]] = []
    s = sched.InsightsScheduler(
        supervisor=sup, list_users=lambda now: users, session_count=lambda uid, now: (sessions or {}).get(uid, 0),
        cutoff=CUTOFF, audit=audit or (lambda e, d: events.append((e, d))), clock=clock)
    return s, clock, workers, sup, events


# ---- the due rule ----
def test_due_rule_matches_the_page_rule_cases():
    wed_night = datetime(2026, 11, 18, 22, 0, tzinfo=timezone.utc).timestamp()
    assert sched.last_session_end(wed_night) == datetime(2026, 11, 18, 21, 0, tzinfo=timezone.utc).timestamp()
    mon_morning = datetime(2026, 11, 23, 9, 0, tzinfo=timezone.utc).timestamp()
    assert sched.last_session_end(mon_morning) == datetime(2026, 11, 20, 21, 0, tzinfo=timezone.utc).timestamp()  # Friday
    assert sched.update_reason(None, wed_night) == "first"
    assert sched.update_reason("not a date", wed_night) == "first"
    assert sched.update_reason("2026-11-18T20:59:59Z", wed_night) == "daily"
    assert sched.update_reason("2026-11-18T21:00:00Z", wed_night) == ""


def test_python_rule_equals_insights_client_js():
    assert shutil.which("node"), "node is needed to run the page rule for the parity check"
    js = (ROOT / "financial_trends_reporter" / "frontend" / "insights_client.js").as_posix()
    nows = [datetime(2026, 11, d, h, 0, tzinfo=timezone.utc).timestamp() * 1000 for d in (16, 18, 20, 21, 22, 23) for h in (0, 20, 21, 23)]
    histories = [[], [{"run_at": "2026-11-17T21:00:00Z"}], [{"run_at": "2026-11-20T21:30:00Z"}], [{"run_at": "bad"}]]
    script = (f"import {{lastMarketSessionEnd, autoUpdateReason}} from 'file://{js}';"
              f"const out=[];for(const n of {json.dumps(nows)}){{out.push([lastMarketSessionEnd(n),"
              f"{json.dumps(histories)}.map(h=>autoUpdateReason(h,n))]);}}console.log(JSON.stringify(out));")
    proc = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    for now_ms, (end_ms, reasons) in zip(nows, json.loads(proc.stdout)):
        assert sched.last_session_end(now_ms / 1000) * 1000 == end_ms
        got = [sched.update_reason(h[-1]["run_at"] if h else None, now_ms / 1000) for h in histories]
        assert got == reasons


def test_parse_cutoff_rejects_garbage():
    assert sched.parse_cutoff("17:30").hour == 17
    for bad in ("1730", "25:00", "17:5", "", "ab:cd"):
        with pytest.raises(ValueError):
            sched.parse_cutoff(bad)


# ---- selection ----
def test_picks_only_due_users(monkeypatch):
    s, _c, workers, _sup, _ev = build(monkeypatch, [user(1), user(2), user(3)], {1: "due", 2: "current", 3: None})
    summary = s.run_pass()
    assert [p[0] for p in workers.posts()] == [1, 3]
    assert summary["updated"] == 2 and summary["failed"] == 0


def test_skips_disabled_and_expired_users(monkeypatch):
    users = [user(1, disabled=True), user(2, expired=True), user(3)]
    s, *_rest = build(monkeypatch, users, {1: "due", 2: "due", 3: "due"})
    assert s.eligible_users(0) == [3]
    _s, _c, workers, _sup, _ev = build(monkeypatch, users, {1: "due", 2: "due", 3: "due"})
    _s.run_pass()
    assert {c[0] for c in workers.calls} == {3}


def test_no_pass_on_weekends_before_cutoff_or_after_the_window(monkeypatch):
    for when in (local(*SAT), local(2026, 11, 22), local(*WED, 17, 29), local(*WED, 23, 31), local(*WED, 3, 0)):
        s, _c, workers, _sup, _ev = build(monkeypatch, [user(1)], {1: "due"}, now=when)
        assert s.tick() is False and workers.calls == []
    s, _c, workers, *_ = build(monkeypatch, [user(1)], {1: "due"}, now=local(*WED, 23, 29))
    assert s.tick() is True and len(workers.posts()) == 1  # last minutes of the 6 h window


def test_friday_window_that_crosses_midnight_belongs_to_friday(monkeypatch):
    late = sched.parse_cutoff("20:00")
    s, clock, workers, *_ = build(monkeypatch, [user(1)], {1: "due"}, now=local(2026, 11, 21, 1, 30))  # Sat 01:30, Fri window
    s._cutoff = late
    assert s.tick() is True
    s2, *_ = build(monkeypatch, [user(1)], {1: "due"}, now=local(2026, 11, 22, 1, 30))  # Sun 01:30: Sat's window does not exist
    s2._cutoff = late
    assert s2.tick() is False


# ---- execution ----
def test_one_user_at_a_time(monkeypatch):
    s, _c, workers, *_ = build(monkeypatch, [user(i) for i in range(1, 6)], {i: "due" for i in range(1, 6)})
    s.run_pass()
    assert workers.max_active == 1 and len(workers.posts()) == 5


def test_skips_a_build_busy_user_and_retries_on_a_later_pass(monkeypatch):
    sup = FakeSup(busy={2})
    s, clock, workers, _sup, events = build(monkeypatch, [user(1), user(2)], {1: "due", 2: "due"}, sup=sup)
    assert s.tick() is True
    assert [p[0] for p in workers.posts()] == [1] and s.last_result()["skipped"] == 1
    assert s.last_result()["failed"] == 0 and 2 not in s._done
    sup.busy.clear()
    clock.now += 3600
    assert s.tick() is True
    assert [p[0] for p in workers.posts()] == [1, 2]


def test_failure_is_recorded_and_not_retried_inside_the_same_pass(monkeypatch):
    s, clock, workers, _sup, events = build(monkeypatch, [user(1), user(2)], {1: "due", 2: "due"}, fail={1})
    summary = s.run_pass()
    assert workers.posts(1) == [(1, "POST", sched.RUN_NOW_PATH)]  # exactly once in the pass
    assert summary["results"] == [{"user_id": 1, "ok": False, "reason": "run_http_500"}, {"user_id": 2, "ok": True, "reason": ""}]
    assert "private text" not in json.dumps(summary)
    assert [e[0] for e in events] == [sched.AUDIT_EVENT]
    assert "failed=1" in events[0][1] and "failed_ids=1" in events[0][1] and "updated_ids=2" in events[0][1]
    assert not any(ch.isalpha() and ch not in "updatedfailskipdids" for ch in events[0][1].replace("_", ""))  # ids/counts only
    # a later pass retries only the failed user
    workers.fail.clear()
    clock.now += 3600
    s.tick()
    assert [p[0] for p in workers.posts()] == [1, 2, 1] and s.last_result()["failed"] == 0


def test_worker_that_cannot_start_is_a_failure_with_a_code(monkeypatch):
    s, *_ = build(monkeypatch, [user(1)], {1: "due"}, sup=FakeSup(unavailable={1}))
    assert s.run_pass()["results"] == [{"user_id": 1, "ok": False, "reason": "worker_unavailable"}]


def test_hourly_passes_until_the_window_closes_then_give_up_until_tomorrow(monkeypatch):
    s, clock, workers, *_ = build(monkeypatch, [user(1)], {1: "due"}, fail={1})
    ran = []
    for minutes in range(0, 8 * 60, 10):
        clock.now = local(*WED, 17, 31) + minutes * 60
        ran.append(s.tick())
    assert sum(ran) == 6  # 17:31 .. 22:31; 23:31 is past cutoff + 6 h
    assert len(workers.posts()) == 6
    clock.now = local(2026, 11, 19, 17, 31)  # tomorrow: a fresh window
    assert s.tick() is True and len(workers.posts()) == 7


def test_no_second_entry_when_the_user_opened_fi_the_same_day(monkeypatch):
    s, clock, workers, *_ = build(monkeypatch, [user(1)], {1: "current"})
    s.run_pass()
    assert workers.posts() == [] and s.last_result()["failed"] == 0
    # and a user the scheduler updated is not asked again in later passes of the window
    s2, clock2, workers2, *_ = build(monkeypatch, [user(1)], {1: "due"})
    s2.tick()
    clock2.now += 3600
    s2.tick()
    assert len(workers2.posts()) == 1


def test_a_running_update_is_not_started_twice(monkeypatch):
    s, _c, workers, *_ = build(monkeypatch, [user(1)], {1: "due"})
    orig = workers.__call__

    def running(ep, method, path, **kw):
        if path == sched.RUN_STATUS_PATH:
            return 200, b'{"running": true, "last_run_at": null}'
        return orig(ep, method, path, **kw)

    monkeypatch.setattr(sched, "call_worker", running)
    assert s.run_pass()["skipped"] == 1 and workers.posts() == []


def test_releases_only_a_worker_it_started_and_only_without_a_session(monkeypatch):
    sup = FakeSup(running={2})
    s, _c, _w, _sup, _ev = build(monkeypatch, [user(1), user(2), user(3)], {1: "due", 2: "due", 3: "due"},
                                 sessions={3: 1}, sup=sup)
    s.run_pass()
    assert sup.released == [1]  # 2 was already up, 3 has a signed-in session


# ---- lifecycle ----
def test_starts_and_stops_cleanly(monkeypatch):
    clock = Clock(local(*WED))
    monkeypatch.setattr(sched, "call_worker", FakeWorkers(clock, {1: iso(clock.now - 9 * 86400)}))
    s = sched.InsightsScheduler(supervisor=FakeSup(), list_users=lambda now: [user(1)], session_count=lambda u, n: 0,
                                cutoff=CUTOFF, clock=clock, check_seconds=0.01)
    s.start()
    deadline = time.time() + 5
    while s.last_result()["at"] is None and time.time() < deadline:
        time.sleep(0.01)
    s.stop()
    assert s._thread is None and s.last_result()["updated"] == 1
    assert not [t for t in threading.enumerate() if t.name == "gateway-insights-schedule"]


def test_audit_failure_never_stops_the_pass(monkeypatch):
    def boom(event, details):
        raise OSError("disk")

    s, *_ = build(monkeypatch, [user(1)], {1: "due"}, audit=boom)
    assert s.run_pass()["updated"] == 1


# ---- flag wiring ----
def test_nothing_is_built_without_the_flag_and_the_flag_needs_insights(monkeypatch):
    from types import SimpleNamespace

    from src.gateway import server

    off = SimpleNamespace(insights_schedule=None, insights=True)
    assert server._Runtime._insights_scheduler(SimpleNamespace(), off, object()) is None
    with pytest.raises(ValueError, match="needs --insights"):
        server._Runtime._insights_scheduler(SimpleNamespace(), SimpleNamespace(insights_schedule="17:30", insights=False), object())
    on = SimpleNamespace(insights_schedule="17:30", insights=True)
    store = SimpleNamespace(list_users=lambda now: [], count_user_sessions=lambda u, n: 0, audit=lambda *a, **k: None)
    built = server._Runtime._insights_scheduler(SimpleNamespace(supervisor=FakeSup()), on, store)
    assert isinstance(built, sched.InsightsScheduler)
    parsed = server._parser().parse_args(["--db", "x.db", "--local-port", "1"])
    assert parsed.insights_schedule is None


# ---- admin status line (the existing health report) ----
def test_health_report_carries_one_status_line(monkeypatch, tmp_path):
    s, *_ = build(monkeypatch, [user(1), user(2)], {1: "due", 2: "due"}, fail={2})
    s.run_pass()
    base = dict(started_at=0.0, schema_version=1, workers_running=0, build_running=0, build_waiting=0, data_root=tmp_path,
                backup_dir=None)
    rep = gateway_health.build_health(**base, insights_schedule=s)
    assert rep["insights_schedule"]["configured"] is True
    assert (rep["insights_schedule"]["updated"], rep["insights_schedule"]["failed"]) == (1, 1)
    assert rep["insights_schedule"]["last_run_at"] is not None
    assert any("Financial Insight" in w for w in rep["warnings"])
    assert gateway_health.build_health(**base)["insights_schedule"] == {"configured": False}
