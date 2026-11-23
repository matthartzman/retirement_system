"""In-memory remote sessions with a 10-minute idle timeout and a 12-hour absolute lifetime.

Only person-driven activity extends a session: the page reports how long ago the person last
touched it, so the 5 s ping and background polling never keep it alive.

Security review F-04: the server cannot tell a real touch from a client that always reports ``idle_ms=0`` (a stolen
cookie can lie), so the idle report can only ever extend the session up to ABSOLUTE_SECONDS after sign-in, a hard cap
no report can move. The report is also clamped to ``0..idle`` and can never move ``last_active`` backwards.
"""
from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass

IDLE_SECONDS = 600.0
ABSOLUTE_SECONDS = 12 * 3600.0  # a session ends this long after sign-in however active it looks


@dataclass
class Session:
    token: str
    user_id: int
    last_active: float
    created: float = 0.0
    epoch: int = 0  # the person's session_epoch at sign-in; the gate ends the session if it has moved


class SessionTable:
    def __init__(self, clock=time.monotonic, idle_seconds: float = IDLE_SECONDS,
                 absolute_seconds: float = ABSOLUTE_SECONDS) -> None:
        self._clock = clock
        self._idle = idle_seconds
        self._absolute = absolute_seconds
        self._lock = threading.Lock()
        self._sessions: dict[str, Session] = {}
        self.expired_user_ids: list[int] = []  # drained by the caller to log timeouts

    def create(self, user_id: int, epoch: int = 0) -> str:
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._sessions[token] = Session(token, user_id, (now := self._clock()), now, epoch)
        return token

    def get(self, token: str | None) -> Session | None:
        if not token:
            return None
        with self._lock:
            sess = self._sessions.get(token)
            if sess is None:
                return None
            now = self._clock()
            if now - sess.last_active >= self._idle or now - sess.created >= self._absolute:
                del self._sessions[token]
                self.expired_user_ids.append(sess.user_id)
                return None
            return sess

    def note_interaction(self, token: str, idle_ms: int) -> None:
        with self._lock:
            sess = self._sessions.get(token)
            if sess is not None:
                sess.last_active = max(sess.last_active, self._clock() - min(max(0, idle_ms) / 1000.0, self._idle))

    def set_epoch(self, token: str | None, epoch: int) -> None:
        with self._lock:
            sess = self._sessions.get(token or "")
            if sess is not None:
                sess.epoch = epoch

    def end(self, token: str | None) -> None:
        with self._lock:
            self._sessions.pop(token or "", None)

    def end_user(self, user_id: int) -> None:
        with self._lock:
            for token in [t for t, s in self._sessions.items() if s.user_id == user_id]:
                del self._sessions[token]
