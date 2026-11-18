"""The share publisher (Phase 9, ``multi-user-shared-view-design.md`` 5.4): the owner's worker renders, the gateway
checks and stores.

1. The row is found by id **and** the owner's own user id, and must be active (else one uniform not-found).
2. At most one publish per share per minute, one at a time per owner, two at a time in the whole gateway (C33).
3. The owner's own worker is reached through ``supervisor.endpoint(owner)``: never anyone else's.
4. The request body is built from the row (expected plan, money view, views, revision), never from the browser.
5. The worker's answer is untrusted input (AC-15): status 200, JSON, the size cap (read one byte more than the cap and
   refuse a body that long, never parse a truncated one), the exact top-level keys, ``share_id`` and ``scope_rev`` equal
   to the request, tabs within the row's tabs and keys within each tab's routes, and in the percent view the leak check
   again, here in the gateway (C19, C20). Every string is normalised (C24).
6. The body is written atomically and bound to its row by SHA-256, size and revision, with a conditional commit: a
   revoke or scope change that won the race leaves nothing to serve, and the file just written is deleted (C14, C15).

Audit events carry ids, revisions, byte counts and reason codes only (C32).
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

from financial_trends_reporter import percent_view

from .share_store import NAME_MAX, ShareNotFound, ShareStore, clean_text
from .store import Actor
from .supervisor import Endpoint, WorkerUnavailable, call_worker_full

LOG = logging.getLogger("retirement.gateway.share_publish")
SNAPSHOT_PATH = "/insights/api/share-snapshot"
PUBLISH_HEADER = "X-Gateway-Share-Publish"  # financial_trends_reporter/share_snapshot.py; stripped from browsers
SCHEMA = "shared_view/1"
TOP_LEVEL_KEYS = frozenset({"schema", "share_id", "scope_rev", "generated_at", "plan", "money_view", "basis_date",
                            "scopes", "views"})
SCOPES = ("week", "month", "3m", "6m", "ytd", "1y", "all")
# The gateway's own copy of what each tab may hold (written out, not imported from the worker side).
_TAB_KEYS: dict[str, re.Pattern[str]] = {
    "trends": re.compile(r"^/api/(history|balances|flows|liquid-change)$|^/api/spending\?scope=(%s)$" % "|".join(SCOPES)),
    "live": re.compile(r"^/api/live-snapshot\?scope=(%s)$|^/api/realized\?tax_year=\d{4}$" % "|".join(SCOPES)),
    "projections": re.compile(r"^/api/projections$"),
}
VALUE_MAX = 2000  # any string value; names and the plan name are capped at NAME_MAX
MIN_SECONDS_BETWEEN = 60.0
MAX_CONCURRENT = 2
TIMEOUT_SECONDS = 180.0
# Worker answers the owner may see a plain message for (codes, never worker text).
MESSAGES = {
    "not_found": "Not found.",
    "too_soon": "This view was refreshed less than a minute ago. Try again shortly.",
    "busy": "Another refresh is running. Try again shortly.",
    "worker_unavailable": "Your planner could not be started. Try again shortly.",
    "plan_not_active": "Open this view's plan in the planner to refresh it.",
    "plan_missing": "This view's plan was deleted, so the view was revoked.",
    "no_basis": "The percent view is not available until account balances are imported.",
    "money_leak": "The view could not be published safely. Try dollars, or try again after the next update.",
    "too_large": "This view is too large to publish. Share fewer tabs.",
    "invalid": "The view could not be published. Try again shortly.",
    "lost_race": "This view changed while it was being refreshed. Try again.",
    "failed": "The view could not be published. Try again shortly.",
}


class PublishError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class PublishResult:
    ok: bool
    code: str  # "published" or a key of MESSAGES
    nbytes: int = 0

    @property
    def message(self) -> str:
        return "Published." if self.ok else MESSAGES.get(self.code, MESSAGES["failed"])


def _normalise(obj: Any, key: str | None = None) -> Any:
    """Every string NFC, with control and bidi characters removed and capped; keys too (C24)."""
    if isinstance(obj, dict):
        return {clean_text(k, NAME_MAX): _normalise(v, k) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_normalise(v, key) for v in obj]
    if isinstance(obj, str):
        limit = NAME_MAX if key in ("name", "account", "account_name", "title", "label", "category", "merchant") else VALUE_MAX
        return clean_text(obj, limit)
    return obj


def validate_record(status: int, ctype: str, data: bytes, row: dict, max_bytes: int) -> dict:
    """The worker's answer as a normalised record, or PublishError with a reason code."""
    if status == 409:
        try:
            err = json.loads(data).get("error")
        except (ValueError, AttributeError):
            err = None
        raise PublishError(err if err in ("plan_not_active", "no_basis") else "invalid")
    if status == 410:
        raise PublishError("plan_missing")
    if status == 422:
        raise PublishError("money_leak")
    if status != 200:
        raise PublishError("invalid")
    if len(data) > max_bytes:
        raise PublishError("too_large")
    if ctype.split(";", 1)[0].strip().lower() != "application/json":
        raise PublishError("invalid")
    try:
        doc = json.loads(data)
    except ValueError:
        raise PublishError("invalid") from None
    if not isinstance(doc, dict) or set(doc) != TOP_LEVEL_KEYS or doc.get("schema") != SCHEMA:
        raise PublishError("invalid")
    if doc.get("share_id") != row["id"] or doc.get("scope_rev") != row["scope_rev"] \
            or doc.get("money_view") != row["money_view"]:
        raise PublishError("invalid")
    plan = doc.get("plan")
    if not isinstance(plan, dict) or set(plan) != {"id", "name"} or plan.get("id") != row["plan_id"]:
        raise PublishError("invalid")
    views = doc.get("views")
    if not isinstance(views, dict) or not views or not set(views) <= set(row["views"]):
        raise PublishError("invalid")  # more than it was asked for: a worker bug, so fail closed
    for tab, panel in views.items():
        pattern = _TAB_KEYS.get(tab)
        if pattern is None or not isinstance(panel, dict) or not all(pattern.match(str(k)) for k in panel):
            raise PublishError("invalid")
    scopes = doc.get("scopes")
    if not isinstance(scopes, dict) or set(scopes) - set(SCOPES):
        raise PublishError("invalid")
    if row["money_view"] == "percent" and percent_view.find_money_leaks(views):
        raise PublishError("money_leak")  # checked again here, in the gateway (C19)
    return _normalise(doc)


class SharePublisher:
    def __init__(self, shares: ShareStore, supervisor, *, clock: Callable[[], float] = time.time,  # noqa: ANN001
                 audit: Callable[..., None], max_bytes: int | None = None, timeout: float = TIMEOUT_SECONDS,
                 call: Callable[..., tuple[int, str, bytes]] = call_worker_full,
                 max_concurrent: int = MAX_CONCURRENT, min_seconds_between: float = MIN_SECONDS_BETWEEN) -> None:
        self.shares = shares
        self.supervisor = supervisor
        self._clock = clock
        self._audit = audit  # (event, *, actor, target_user_id, details)
        self.max_bytes = int(max_bytes if max_bytes is not None else shares.settings.max_bytes)
        self._timeout = float(timeout)
        self._call = call
        self._slots = threading.BoundedSemaphore(max(1, int(max_concurrent)))
        self._owner_locks: dict[int, threading.Lock] = {}
        self._locks_lock = threading.Lock()
        self._last: dict[str, float] = {}
        self._min_between = float(min_seconds_between)
        self.after_store: Callable[[str], None] | None = None  # tests: runs between the file write and the commit

    def _owner_lock(self, owner_id: int) -> threading.Lock:
        with self._locks_lock:
            lock = self._owner_locks.get(int(owner_id))
            if lock is None:
                lock = self._owner_locks[int(owner_id)] = threading.Lock()
            return lock

    def publish(self, owner_id: int, share_id: object, *, actor: Actor, endpoint: Endpoint | None = None,
                rate_limit: bool = True) -> PublishResult:
        """Render, check and store one share of ``owner_id``. ``endpoint`` is given by the scheduler, which already
        holds that owner's worker; otherwise the owner's own endpoint is asked for."""
        row = self.shares.publish_target(owner_id, share_id)
        if row is None:
            return PublishResult(False, "not_found")
        now = self._clock()
        if rate_limit and now - self._last.get(row["id"], float("-inf")) < self._min_between:
            return PublishResult(False, "too_soon")
        lock = self._owner_lock(owner_id)
        if not lock.acquire(blocking=False):
            return PublishResult(False, "busy")
        try:
            if not self._slots.acquire(timeout=5.0):
                return PublishResult(False, "busy")
            try:
                self._last[row["id"]] = now
                return self._publish_locked(int(owner_id), row, actor, endpoint)
            finally:
                self._slots.release()
        finally:
            lock.release()

    def _publish_locked(self, owner_id: int, row: dict, actor: Actor, endpoint: Endpoint | None) -> PublishResult:
        try:
            ep = endpoint if endpoint is not None else self.supervisor.endpoint(owner_id)
        except WorkerUnavailable:
            return self._failed(owner_id, row, actor, "worker_unavailable")
        except Exception:  # noqa: BLE001
            LOG.exception("could not start the worker of user %s for a publish", owner_id)
            return self._failed(owner_id, row, actor, "worker_unavailable")
        if int(ep.user_id) != owner_id:  # never another user's worker
            return self._failed(owner_id, row, actor, "invalid")
        request_body = json.dumps({"share_id": row["id"], "scope_rev": row["scope_rev"], "money_view": row["money_view"],
                                   "views": row["views"], "expected_plan_id": row["plan_id"]}).encode()
        try:
            status, ctype, data = self._call(ep, "POST", SNAPSHOT_PATH, body=request_body, timeout=self._timeout,
                                             max_bytes=self.max_bytes + 1, headers={PUBLISH_HEADER: "1"})
        except Exception:  # noqa: BLE001 - timeouts and connection errors alike
            LOG.warning("share snapshot request failed for user %s", owner_id, exc_info=True)
            return self._failed(owner_id, row, actor, "failed")
        try:
            doc = validate_record(status, ctype, data, row, self.max_bytes)
        except PublishError as exc:
            if exc.code == "plan_missing":  # decision 7: the plan is gone, so its shares go too
                self.shares.revoke_plan(owner_id, row["plan_id"], now=self._clock(), actor=actor)
            return self._failed(owner_id, row, actor, exc.code)
        body = json.dumps(doc, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(body) > self.max_bytes:
            return self._failed(owner_id, row, actor, "too_large")
        digest = hashlib.sha256(body).hexdigest()
        try:
            self.shares.write_body(row["id"], body)
        except Exception:  # noqa: BLE001
            LOG.exception("could not store share %s", row["id"])
            return self._failed(owner_id, row, actor, "failed")
        if self.after_store is not None:
            self.after_store(row["id"])
        if not self.shares.mark_published(row["id"], row["scope_rev"], digest, len(body), self._clock()):
            # A revoke or a scope change won the race: what was just written must not survive (C15).
            current = self.shares.owner_get(owner_id, row["id"])
            if current is None or current.get("snapshot_sha256") != digest:
                self.shares.delete_body(row["id"])
            return self._failed(owner_id, row, actor, "lost_race")
        self._audit("share_published", actor=actor, target_user_id=row["grantee_user_id"],
                    details=f"share {row['id']} rev {row['scope_rev']} bytes {len(body)}")
        return PublishResult(True, "published", len(body))

    def _failed(self, owner_id: int, row: dict, actor: Actor, code: str) -> PublishResult:
        self._audit("share_publish_failed", actor=actor, target_user_id=row["grantee_user_id"],
                    details=f"share {row['id']} reason {code}")
        return PublishResult(False, code)

    def refresh_owner(self, owner_id: int, endpoint: Endpoint, *, actor: Actor) -> dict:
        """Phase 8's hook (decision 10): after a scheduled update, republish the owner's active shares whose plan is
        the active one. Shares of another plan are skipped (the worker answers plan_not_active)."""
        report = {"published": 0, "skipped": 0, "failed": 0}
        for row in self.shares.owner_list(owner_id, self._clock()):
            if row["state"] != "active" or row["expired"]:
                continue
            try:
                result = self.publish(owner_id, row["id"], actor=actor, endpoint=endpoint, rate_limit=False)
            except ShareNotFound:
                continue
            if result.ok:
                report["published"] += 1
            elif result.code == "plan_not_active":
                report["skipped"] += 1
            else:
                report["failed"] += 1
        return report


def plan_delete_hook(shares: ShareStore, actor: Actor, clock: Callable[[], float] = time.time):
    """The proxy's after-forward hook: a successful ``POST /api/plans/delete`` revokes that plan's shares
    (decision 7). The plan id comes from the request the owner's own worker just accepted."""

    def hook(req, identity, resp) -> None:  # noqa: ANN001
        if req.method != "POST" or req.path != "/api/plans/delete" or resp.status_code != 200:
            return
        try:
            plan_id = str((json.loads(req.body or b"{}") or {}).get("plan_id") or "").strip()
        except (ValueError, AttributeError):
            return
        if plan_id:
            shares.revoke_plan(int(identity.user_id), plan_id, now=clock(), actor=actor)
    return hook
