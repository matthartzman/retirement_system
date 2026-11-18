"""Shares (Phase 9): rows in ``gateway.db`` and record bodies under ``<data_root>/shares/``.

See ``documentation/future/multi-user-shared-view-design.md`` sections 5.2 (data model), 5.5 (storage), 5.6 and 5.8
(selection) and 7 (lifecycle). Every query that serves a person is scoped by the session's own user id: an owner query
includes ``owner_user_id = <owner>`` and a viewer query includes ``grantee_user_id = <viewer>``. A share id is a random
128-bit value that only picks within that set; it is never a capability.

A body is served only when its SHA-256 equals the row's ``snapshot_sha256`` and its embedded ``share_id`` and
``scope_rev`` equal the row's (C14). Audit events carry ids, revisions and counts only (C32).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import sqlite3
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from . import fsguard
from .store import MEMBER, Actor, GatewayStore

SHARE_ID_RE = re.compile(r"^[0-9a-f]{32}$")
VIEW_NAMES = ("live", "trends", "projections")
MONEY_VIEWS = ("percent", "dollars")
TITLE_MAX = 60
NAME_MAX = 200
MAX_SHARES_PER_OWNER = 10
DEFAULT_DAYS = 90
MAX_DAYS = 365
RETENTION_SECONDS = 90 * 86400  # revoked and expired rows (with their access log) are purged after this
ACCESS_LOG_EVERY_SECONDS = 10 * 60
DAY = 86400.0
# Unicode format characters that reorder or hide text (bidi overrides and isolates, zero-width marks).
_BIDI = {chr(c) for c in (0x200B, 0x200C, 0x200D, 0x200E, 0x200F, 0x202A, 0x202B, 0x202C, 0x202D, 0x202E,
                          0x2066, 0x2067, 0x2068, 0x2069, 0xFEFF)}


class ShareError(ValueError):
    """A refusal whose message is safe to show the owner."""


class ShareNotFound(ShareError):
    """No such share for this person (one uniform answer, whatever the reason)."""


class ShareLimit(ShareError):
    """A limit was reached (shares per owner, publishing too often)."""


def clean_text(value: object, limit: int = NAME_MAX) -> str:
    """NFC, with control, bidi-override and zero-width characters removed, trimmed and capped (C24)."""
    text = unicodedata.normalize("NFC", str(value if value is not None else ""))
    text = "".join(c for c in text if c not in _BIDI and unicodedata.category(c) not in ("Cc", "Cf", "Cs", "Co"))
    return text.strip()[:limit]


def check_title(title: object) -> str:
    if not isinstance(title, str):
        raise ShareError("Give the shared view a title.")
    cleaned = clean_text(title, TITLE_MAX)
    if not cleaned:
        raise ShareError("Give the shared view a title.")
    return cleaned


def check_scope(money_view: object, views: object) -> tuple[str, list[str]]:
    if money_view not in MONEY_VIEWS:
        raise ShareError("Choose percent or dollars.")
    if not isinstance(views, list) or not views or any(v not in VIEW_NAMES for v in views) or len(set(views)) != len(views):
        raise ShareError("Choose at least one of Snapshot, Trends and Projections.")
    return str(money_view), [v for v in VIEW_NAMES if v in views]  # canonical order


def check_days(days: object, max_days: int) -> int:
    if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= int(max_days):
        raise ShareError(f"A shared view can last 1 to {int(max_days)} days.")
    return days


def valid_share_id(value: object) -> bool:
    return isinstance(value, str) and bool(SHARE_ID_RE.match(value))


@dataclass(frozen=True)
class ShareSettings:
    max_shares_per_owner: int = MAX_SHARES_PER_OWNER
    default_days: int = DEFAULT_DAYS
    max_days: int = MAX_DAYS
    max_bytes: int = 8 * 1024 * 1024


class ShareStore:
    """Share rows (through the gateway store's connections) and the bodies folder."""

    def __init__(self, store: GatewayStore, shares_dir: Path | None, settings: ShareSettings | None = None) -> None:
        self.store = store
        self.dir = Path(shares_dir) if shares_dir is not None else None
        self.settings = settings or ShareSettings()

    # ---- rows: owner side (every query is scoped by owner_user_id) ----
    @staticmethod
    def _row(r: sqlite3.Row | None) -> dict | None:
        if r is None:
            return None
        d = dict(r)
        d["views"] = json.loads(d["views"])
        return d

    @staticmethod
    def _usable_member(conn: sqlite3.Connection, uid: int, now: float) -> bool:
        r = conn.execute("SELECT kind, disabled, expires_at FROM users WHERE id=?", (int(uid),)).fetchone()
        return (r is not None and r["kind"] == MEMBER and not r["disabled"]
                and (r["expires_at"] is None or now < r["expires_at"]))

    def create(self, owner_id: int, *, viewer_id: object, title: object, money_view: object, views: object,
               expires_in_days: object, plan_id: str, now: float, actor: Actor) -> str:
        """A new active, unpublished row. The grantee must be a viewer the owner sponsors (C29)."""
        t = check_title(title)
        mv, vs = check_scope(money_view, views)
        days = check_days(expires_in_days, self.settings.max_days)
        if isinstance(viewer_id, bool) or not isinstance(viewer_id, int):
            raise ShareNotFound("That viewer was not found.")
        sid = secrets.token_hex(16)
        with self.store._tx() as conn:
            if not self._usable_member(conn, owner_id, now):
                raise ShareNotFound("That viewer was not found.")
            g = conn.execute("SELECT id, kind, sponsor_user_id FROM users WHERE id=?", (int(viewer_id),)).fetchone()
            if g is None or g["kind"] == MEMBER or g["sponsor_user_id"] != int(owner_id):
                raise ShareNotFound("That viewer was not found.")
            n = int(conn.execute("SELECT COUNT(*) FROM shares WHERE owner_user_id=? AND state<>'revoked'",
                                 (int(owner_id),)).fetchone()[0])
            if self.settings.max_shares_per_owner and n >= self.settings.max_shares_per_owner:
                raise ShareLimit(f"You can have at most {self.settings.max_shares_per_owner} shared views.")
            conn.execute("INSERT INTO shares(id, owner_user_id, grantee_user_id, plan_id, title, money_view, views,"
                         " created_at, updated_at, expires_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                         (sid, int(owner_id), int(viewer_id), clean_text(plan_id, 64), t, mv, json.dumps(vs), now, now,
                          now + days * DAY))
            self.store.audit("share_created", now=now, actor=actor, target_user_id=int(viewer_id),
                             details=f"share {sid}", conn=conn)
        return sid

    def owner_get(self, owner_id: int, share_id: object) -> dict | None:
        if not valid_share_id(share_id):
            return None
        rows = self.store._read("SELECT * FROM shares WHERE id=? AND owner_user_id=?", (share_id, int(owner_id)))
        return self._row(rows[0]) if rows else None

    def owner_list(self, owner_id: int, now: float) -> list[dict]:
        rows = self.store._read(
            "SELECT s.*, u.display_name AS viewer_name, (SELECT MAX(at) FROM share_access_log l WHERE l.share_id = s.id)"
            " AS last_viewed FROM shares s JOIN users u ON u.id = s.grantee_user_id WHERE s.owner_user_id=?"
            " ORDER BY s.created_at", (int(owner_id),))
        out = []
        for r in rows:
            d = self._row(r)
            d["expired"] = now >= d["expires_at"]
            out.append(d)
        return out

    def sponsored_viewers(self, owner_id: int, now: float) -> list[dict]:
        rows = self.store._read(
            "SELECT u.id, u.display_name, u.expires_at, u.disabled, t.enrolled_at FROM users u"
            " LEFT JOIN totp_secrets t ON t.user_id = u.id WHERE u.sponsor_user_id=? AND u.kind<>'member'"
            " ORDER BY u.display_name", (int(owner_id),))
        return [{"id": r["id"], "display_name": r["display_name"], "expires_at": r["expires_at"],
                 "expired": r["expires_at"] is not None and now >= r["expires_at"], "disabled": bool(r["disabled"]),
                 "enrolled": r["enrolled_at"] is not None} for r in rows]

    def _owner_update(self, owner_id: int, share_id: object, sets: str, params: tuple, *, where: str = "",
                      event: str, details: str, now: float, actor: Actor) -> dict:
        if not valid_share_id(share_id):
            raise ShareNotFound("Not found.")
        with self.store._tx() as conn:
            row = conn.execute("SELECT * FROM shares WHERE id=? AND owner_user_id=?" + where,
                               (share_id, int(owner_id))).fetchone()
            if row is None:
                raise ShareNotFound("Not found.")
            conn.execute(f"UPDATE shares SET {sets}, updated_at=? WHERE id=?", (*params, now, share_id))
            self.store.audit(event, now=now, actor=actor, target_user_id=row["grantee_user_id"],
                             details=f"share {share_id}{details}", conn=conn)
            return self._row(conn.execute("SELECT * FROM shares WHERE id=?", (share_id,)).fetchone())

    def revoke(self, owner_id: int, share_id: object, *, now: float, actor: Actor) -> dict:
        row = self._owner_update(owner_id, share_id, "state='revoked', state_reason='revoked', published_at=NULL",
                                 (), where=" AND state<>'revoked'", event="share_revoked", details="", now=now,
                                 actor=actor)
        self.delete_body(row["id"])  # after the commit: the row no longer serves it either way (C13)
        return row

    def set_scope(self, owner_id: int, share_id: object, *, money_view: object, views: object, now: float,
                  actor: Actor) -> dict:
        """New scope: the old body is deleted first and the revision moves on, so only a republish serves again."""
        mv, vs = check_scope(money_view, views)
        if self.owner_get(owner_id, share_id) is None:
            raise ShareNotFound("Not found.")
        self.delete_body(str(share_id))
        row = self._owner_update(owner_id, share_id,
                                 "money_view=?, views=?, scope_rev=scope_rev+1, published_at=NULL, published_rev=NULL,"
                                 " snapshot_sha256=NULL, snapshot_bytes=NULL", (mv, json.dumps(vs)),
                                 where=" AND state<>'revoked'", event="share_scope_changed", details="", now=now,
                                 actor=actor)
        self.delete_body(row["id"])  # again, in case a publish of the old scope landed in between
        return row

    def set_expiry(self, owner_id: int, share_id: object, *, expires_in_days: object, now: float, actor: Actor) -> dict:
        days = check_days(expires_in_days, self.settings.max_days)
        return self._owner_update(owner_id, share_id, "expires_at=?, state_reason=CASE WHEN state_reason='expired'"
                                  " THEN '' ELSE state_reason END", (now + days * DAY,), where=" AND state<>'revoked'",
                                  event="share_expiry_changed", details=f" days {days}", now=now, actor=actor)

    def enable(self, owner_id: int, share_id: object, *, now: float, actor: Actor) -> dict:
        return self._owner_update(owner_id, share_id, "state='active', state_reason=''", (),
                                  where=" AND state='suspended'", event="share_enabled", details="", now=now,
                                  actor=actor)

    def access_log(self, owner_id: int, share_id: object, now: float) -> list[dict] | None:
        if self.owner_get(owner_id, share_id) is None:
            return None
        rows = self.store._read(
            "SELECT l.at, u.display_name FROM share_access_log l LEFT JOIN users u ON u.id = l.viewer_user_id"
            " WHERE l.share_id=? AND l.at > ? ORDER BY l.at DESC LIMIT 500", (share_id, now - RETENTION_SECONDS))
        return [{"at": r["at"], "viewer": r["display_name"] or ""} for r in rows]

    # ---- rows: viewer side (every query is scoped by grantee_user_id) ----
    _SERVABLE = (" FROM shares s JOIN users o ON o.id = s.owner_user_id JOIN users g ON g.id = s.grantee_user_id"
                 " WHERE s.grantee_user_id=? AND s.state='active' AND s.expires_at > ? AND s.published_at IS NOT NULL"
                 " AND s.snapshot_sha256 IS NOT NULL AND o.kind='member' AND o.disabled=0"
                 " AND (o.expires_at IS NULL OR o.expires_at > ?) AND g.kind<>'member' AND g.disabled=0")

    def viewer_list(self, viewer_id: int, now: float) -> list[dict]:
        rows = self.store._read("SELECT s.*, o.display_name AS owner_name" + self._SERVABLE + " ORDER BY s.published_at DESC",
                                (int(viewer_id), now, now))
        return [self._row(r) for r in rows]

    def viewer_get(self, viewer_id: int, share_id: object, now: float) -> dict | None:
        """The share only when this viewer may see it now (C5, C12); None for every other case alike (C6)."""
        if not valid_share_id(share_id):
            return None
        rows = self.store._read("SELECT s.*, o.display_name AS owner_name" + self._SERVABLE + " AND s.id=?",
                                (int(viewer_id), now, now, share_id))
        return self._row(rows[0]) if rows else None

    def log_access(self, share_id: str, viewer_id: int, now: float) -> bool:
        """One row per viewer and share at most every 10 minutes; True when a row was written."""
        with self.store._tx() as conn:
            recent = conn.execute("SELECT 1 FROM share_access_log WHERE share_id=? AND viewer_user_id=? AND at > ?",
                                  (share_id, int(viewer_id), now - ACCESS_LOG_EVERY_SECONDS)).fetchone()
            if recent is not None:
                return False
            conn.execute("INSERT INTO share_access_log(share_id, viewer_user_id, at) VALUES (?,?,?)",
                         (share_id, int(viewer_id), now))
            return True

    # ---- publishing (the gateway publisher calls these) ----
    def publish_target(self, owner_id: int, share_id: object) -> dict | None:
        """The row a publish may render: the owner's own, active share (else None, one uniform answer)."""
        row = self.owner_get(owner_id, share_id)
        return row if row is not None and row["state"] == "active" else None

    def mark_published(self, share_id: str, scope_rev: int, sha256: str, nbytes: int, now: float) -> bool:
        """Conditional commit (C15): only while the share is still active at the revision that was rendered."""
        with self.store._tx() as conn:
            cur = conn.execute("UPDATE shares SET published_at=?, published_rev=?, snapshot_sha256=?, snapshot_bytes=?,"
                               " updated_at=? WHERE id=? AND state='active' AND scope_rev=?",
                               (now, int(scope_rev), sha256, int(nbytes), now, share_id, int(scope_rev)))
            return cur.rowcount == 1

    def set_plan(self, share_id: str, plan_id: str) -> None:
        with self.store._tx() as conn:
            conn.execute("UPDATE shares SET plan_id=? WHERE id=? AND plan_id=''", (clean_text(plan_id, 64), share_id))

    def revoke_plan(self, owner_id: int, plan_id: str, *, now: float, actor: Actor) -> int:
        """Deleting a plan revokes its shares (decision 7). Returns how many were revoked."""
        rows = self.store._read("SELECT id FROM shares WHERE owner_user_id=? AND plan_id=? AND state<>'revoked'",
                                (int(owner_id), str(plan_id)))
        for r in rows:
            try:
                self._owner_update(owner_id, r["id"], "state='revoked', state_reason='plan deleted', published_at=NULL",
                                   (), where=" AND state<>'revoked'", event="share_revoked", details=" reason plan deleted",
                                   now=now, actor=actor)
            except ShareNotFound:
                continue
            self.delete_body(r["id"])
        return len(rows)

    def active_for_plan(self, owner_id: int, plan_id: str) -> list[dict]:
        rows = self.store._read("SELECT * FROM shares WHERE owner_user_id=? AND plan_id=? AND state='active'",
                                (int(owner_id), str(plan_id)))
        return [self._row(r) for r in rows]

    # ---- bodies ----
    def body_path(self, share_id: str) -> Path:
        if self.dir is None:
            raise RuntimeError("no shares folder is configured")
        if not valid_share_id(share_id):
            raise ValueError("not a share id")
        return self.dir / f"{share_id}.json"

    def write_body(self, share_id: str, data: bytes) -> Path:
        """Atomic: a temporary file, fsync, then ``os.replace``."""
        path = self.body_path(share_id)
        self.dir.mkdir(parents=True, exist_ok=True)
        if fsguard.has_reparse_point(path, self.dir):
            raise RuntimeError("the shares folder holds a link")
        tmp = path.with_name(path.name + ".tmp")
        with open(tmp, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
        return path

    def delete_body(self, share_id: str) -> None:
        if self.dir is None or not valid_share_id(share_id):
            return
        for p in (self.body_path(share_id), self.body_path(share_id).with_name(f"{share_id}.json.tmp")):
            try:
                p.unlink()
            except FileNotFoundError:
                pass

    def read_body(self, row: dict) -> bytes | None:
        """The stored body when it matches its row (digest, size, embedded id and revision), else None (C14)."""
        if self.dir is None or not row.get("snapshot_sha256"):
            return None
        path = self.body_path(row["id"])
        if fsguard.has_reparse_point(path, self.dir):
            return None
        try:
            with open(path, "rb") as fh:
                data = fh.read(int(self.settings.max_bytes) + 1)
        except OSError:
            return None
        if len(data) > self.settings.max_bytes or len(data) != row.get("snapshot_bytes"):
            return None
        if not secrets.compare_digest(hashlib.sha256(data).hexdigest(), str(row["snapshot_sha256"])):
            return None
        try:
            doc = json.loads(data)
        except ValueError:
            return None
        if not isinstance(doc, dict) or doc.get("share_id") != row["id"] or doc.get("scope_rev") != row["scope_rev"] \
                or row.get("published_rev") != row["scope_rev"]:
            return None
        return data

    # ---- housekeeping (hourly) ----
    def housekeeping(self, now: float, actor: Actor) -> dict:
        """Delete bodies nothing may serve, audit each expiry once, purge old revoked and expired rows."""
        report = {"bodies_deleted": 0, "expired": 0, "purged": 0}
        with self.store._tx() as conn:
            for r in conn.execute("SELECT id, grantee_user_id FROM shares WHERE state='active' AND expires_at <= ?"
                                  " AND state_reason<>'expired'", (now,)).fetchall():
                conn.execute("UPDATE shares SET state_reason='expired', updated_at=? WHERE id=?", (now, r["id"]))
                self.store.audit("share_expired", now=now, actor=actor, target_user_id=r["grantee_user_id"],
                                 details=f"share {r['id']}", conn=conn)
                report["expired"] += 1
            cut = now - RETENTION_SECONDS
            cur = conn.execute("DELETE FROM shares WHERE (state='revoked' AND updated_at <= ?) OR expires_at <= ?",
                               (cut, cut))
            report["purged"] = cur.rowcount
        if self.dir is None or not self.dir.is_dir():
            return report
        servable = {r["id"]: r for r in self.store._read(
            "SELECT id, published_at FROM shares WHERE state<>'revoked' AND expires_at > ? AND published_at IS NOT NULL",
            (now,))}
        for entry in os.scandir(self.dir):
            name = entry.name
            sid = name[:-5] if name.endswith(".json") else name[:-9] if name.endswith(".json.tmp") else ""
            if name.endswith(".json") and valid_share_id(sid) and sid in servable:
                continue
            if entry.is_dir(follow_symlinks=False):
                continue
            try:
                os.unlink(entry.path)
                report["bodies_deleted"] += 1
            except OSError:
                pass
        return report

    def purge_owner(self, owner_id: int) -> int:
        """Bodies of an owner who is being deleted (the rows cascade with the account). Returns how many."""
        n = 0
        for r in self.store._read("SELECT id FROM shares WHERE owner_user_id=?", (int(owner_id),)):
            self.delete_body(r["id"])
            n += 1
        return n
