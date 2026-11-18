"""Scheduled per-user Financial Insight update on the multi-user gateway (insights design 4.6, Phase 8).

The desktop app refreshes its FI history from a 5 pm weekday Task Scheduler job; on the server a user's log would
otherwise gain one entry per day they open FI. This thread closes that gap: every weekday after a cutoff it asks each
active user's own worker to run the same read-only update (``POST /insights/api/run-now``, authenticated with the
worker token, no new inbound path, nothing sent off the machine). Only the worker touches the user's plan and log.

Who is due is the rule the FI page already applies on open (``autoUpdateReason`` in
``financial_trends_reporter/frontend/insights_client.js``): no history yet, or the newest entry is older than the last
weekday 21:00 UTC. ``last_session_end`` and ``update_reason`` below are its exact mirror (a test runs both on the same
inputs); the page and this scheduler therefore never disagree, and a user who opens FI after the cutoff gets no second
entry because the due check is made again, against the worker, just before the run.

Days the gateway was down are not backfilled: the log gets one entry per day the scheduler or the user ran an update.
"""
from __future__ import annotations

import http.client
import json
import logging
import socket
import threading
import time
from datetime import datetime, time as dtime, timedelta, timezone
from typing import Callable

from .supervisor import Endpoint, WorkerUnavailable, call_worker

log = logging.getLogger("retirement_system.insights_schedule")

CHECK_SECONDS = 60.0
PASS_INTERVAL_SECONDS = 3600.0  # passes while the window is open: hourly
RETRY_WINDOW_SECONDS = 6 * 3600.0  # the window closes this long after the cutoff
RUN_TIMEOUT_SECONDS = 15 * 60.0
RUN_NOW_PATH = "/insights/api/run-now"
RUN_STATUS_PATH = "/insights/api/run-status"
AUDIT_EVENT = "insights_scheduled_update"
_SESSION_HOUR_UTC = 21


# ---- the due rule (mirror of insights_client.js) ----
def last_session_end(now: float) -> float:
    """Most recent weekday 21:00 UTC at or before ``now`` (epoch seconds), as ``lastMarketSessionEnd`` computes."""
    d = datetime.fromtimestamp(now, timezone.utc).replace(hour=_SESSION_HOUR_UTC, minute=0, second=0, microsecond=0)
    if d.timestamp() > now:
        d -= timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.timestamp()


def update_reason(last_run_at: str | None, now: float) -> str:
    """"first" (no usable history), "daily" (newest entry predates the last session) or "" (current)."""
    try:
        text = str(last_run_at or "").strip()
        if not text:
            return "first"
        parsed = datetime.fromisoformat(text[:-1] + "+00:00" if text.endswith("Z") else text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        last = parsed.timestamp()
    except (ValueError, OverflowError):
        return "first"
    return "daily" if last < last_session_end(now) else ""


def parse_cutoff(text: str) -> dtime:
    """``HH:MM`` (24 h, gateway local time)."""
    try:
        hh, mm = str(text).strip().split(":")
        if not (len(hh) in (1, 2) and len(mm) == 2):
            raise ValueError
        return dtime(int(hh), int(mm))
    except ValueError:
        raise ValueError(f"--insights-schedule must be HH:MM (24 hour, server local time), not {text!r}") from None


def window_start(local_now: datetime, cutoff: dtime) -> datetime | None:
    """The cutoff of the weekday whose retry window contains ``local_now``, else None (weekend or outside)."""
    for back in (0, 1):  # a window can run past midnight
        day = (local_now - timedelta(days=back)).date()
        if day.weekday() >= 5:
            continue
        start = datetime.combine(day, cutoff)
        if start <= local_now < start + timedelta(seconds=RETRY_WINDOW_SECONDS):
            return start
    return None


class InsightsScheduler:
    def __init__(
        self,
        *,
        supervisor,
        list_users: Callable[[float], list[dict]],
        session_count: Callable[[int, float], int],
        cutoff: dtime,
        audit: Callable[[str, str], None] | None = None,
        clock: Callable[[], float] = time.time,
        run_timeout: float = RUN_TIMEOUT_SECONDS,
        check_seconds: float = CHECK_SECONDS,
    ) -> None:
        self._sup = supervisor
        self._list_users = list_users
        self._session_count = session_count
        self._cutoff = cutoff
        self._audit = audit
        self._clock = clock
        self._run_timeout = float(run_timeout)
        self._check = float(check_seconds)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._window: datetime | None = None
        self._next_pass = 0.0
        self._done: set[int] = set()  # current for today (updated by us, or already current): not asked again
        self._updated: set[int] = set()
        self._outcomes: dict[int, dict] = {}  # latest attempt per user in this window: {user_id, ok, reason}
        self._last: dict = {"at": None, "updated": 0, "failed": 0, "skipped": 0, "results": []}

    # ---- selection (pure apart from the injected user list) ----
    def eligible_users(self, now: float) -> list[int]:
        """Active, non-disabled users (every one of them has FI when the gateway runs with --insights)."""
        users = self._list_users(now)
        return sorted(int(u["id"]) for u in users if not u.get("disabled") and not u.get("expired"))

    # ---- one user ----
    @staticmethod
    def _json(ep: Endpoint, method: str, path: str, timeout: float) -> tuple[int, dict]:
        status, body = call_worker(ep, method, path, timeout=timeout)
        try:
            data = json.loads(body)
        except ValueError:
            data = {}
        return status, data if isinstance(data, dict) else {}

    def _update_user(self, uid: int, now: float) -> tuple[str, str]:
        """("updated" | "current" | "skipped" | "failed", reason code). Reasons are codes, never worker text."""
        if self._sup.build_busy(uid):
            return "skipped", "build_busy"
        was_running = self._sup.is_running(uid)
        try:
            ep = self._sup.endpoint(uid)
        except WorkerUnavailable:
            return "failed", "worker_unavailable"
        except Exception:  # noqa: BLE001
            log.warning("could not start the worker for user %s", uid, exc_info=True)
            return "failed", "worker_start_failed"
        try:
            return self._run_on_worker(ep, now)
        finally:
            if not was_running and self._session_count(uid, self._clock()) == 0:
                try:
                    self._sup.release(uid, "scheduled update finished")
                except Exception:  # noqa: BLE001
                    log.warning("could not release the worker for user %s", uid, exc_info=True)

    def _run_on_worker(self, ep: Endpoint, now: float) -> tuple[str, str]:
        try:
            status, info = self._json(ep, "GET", RUN_STATUS_PATH, 15.0)
            if status != 200:
                return "failed", f"status_http_{status}"
            if info.get("running"):
                return "skipped", "update_running"
            if not update_reason(info.get("last_run_at"), now):
                return "current", ""  # the user opened FI after the session: no second entry
            status, info = self._json(ep, "POST", RUN_NOW_PATH, self._run_timeout)
        except (socket.timeout, TimeoutError):
            return "failed", "timeout"
        except (OSError, http.client.HTTPException):
            return "failed", "worker_unreachable"
        if status == 200 and info.get("success"):
            return "updated", ""
        return "failed", f"run_http_{status}"

    # ---- one pass over the users ----
    def run_pass(self) -> dict:
        """Ask each due user's worker for one update, one at a time. Returns the pass summary (also last_result)."""
        now = self._clock()
        updated, failed, skipped = [], [], []
        for uid in self.eligible_users(now):
            if self._stop.is_set():
                break
            if uid in self._done:
                continue
            try:
                kind, reason = self._update_user(uid, now)
            except Exception:  # noqa: BLE001 - one user never stops the pass
                log.warning("scheduled update for user %s failed", uid, exc_info=True)
                kind, reason = "failed", "unexpected_error"
            if kind in ("updated", "current"):
                self._done.add(uid)
                self._outcomes[uid] = {"user_id": uid, "ok": True, "reason": ""}
                if kind == "updated":
                    self._updated.add(uid)
                    updated.append(uid)
            elif kind == "failed":
                failed.append(uid)
                self._outcomes[uid] = {"user_id": uid, "ok": False, "reason": reason}
            else:
                skipped.append(uid)
        results = [dict(self._outcomes[u]) for u in sorted(self._outcomes)]
        summary = {"at": self._clock(), "updated": len(self._updated),
                   "failed": sum(1 for r in results if not r["ok"]), "skipped": len(skipped), "results": results}
        with self._lock:
            self._last = summary
        if updated or failed or skipped:
            self._emit_audit(updated, failed, skipped)
        return summary

    def _emit_audit(self, updated: list[int], failed: list[int], skipped: list[int]) -> None:
        if self._audit is None:
            return
        details = (f"updated={len(updated)} failed={len(failed)} skipped={len(skipped)}"
                   f" updated_ids={','.join(map(str, updated))} failed_ids={','.join(map(str, failed))}")
        try:
            self._audit(AUDIT_EVENT, details)  # user ids and counts only, never amounts
        except Exception:  # noqa: BLE001
            log.warning("could not record the scheduled-update audit event", exc_info=True)

    # ---- scheduling ----
    def tick(self) -> bool:
        """One look at the clock; runs a pass when one is due. True when a pass ran."""
        now = self._clock()
        start = window_start(datetime.fromtimestamp(now), self._cutoff)
        if start is None:
            return False
        if start != self._window:  # a new weekday window: nobody is done yet
            self._window, self._next_pass = start, 0.0
            self._done, self._updated, self._outcomes = set(), set(), {}
        if now < self._next_pass:
            return False
        self._next_pass = now + PASS_INTERVAL_SECONDS
        self.run_pass()
        return True

    def last_result(self) -> dict:
        with self._lock:
            return dict(self._last, results=[dict(r) for r in self._last["results"]])

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:  # noqa: BLE001
                log.error("scheduled Financial Insight update pass failed", exc_info=True)
            self._stop.wait(self._check)

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="gateway-insights-schedule", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=30)
        self._thread = None
