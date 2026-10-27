"""In-memory remote sessions with a 10-minute idle timeout.

Only person-driven activity extends a session: the page reports how long ago the person last
touched it, so the 5 s ping and background polling never keep it alive.
"""
from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass

IDLE_SECONDS = 600.0


@dataclass
class Session:
    token: str
    user_id: int
    last_active: float


class SessionTable:
    def __init__(self, clock=time.monotonic, idle_seconds: float = IDLE_SECONDS) -> None:
        self._clock = clock
        self._idle = idle_seconds
        self._lock = threading.Lock()
        self._sessions: dict[str, Session] = {}
        self.expired_user_ids: list[int] = []  # drained by the caller to log timeouts

    def create(self, user_id: int) -> str:
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._sessions[token] = Session(token, user_id, self._clock())
        return token

    def get(self, token: str | None) -> Session | None:
        if not token:
            return None
        with self._lock:
            sess = self._sessions.get(token)
            if sess is None:
                return None
            if self._clock() - sess.last_active >= self._idle:
                del self._sessions[token]
                self.expired_user_ids.append(sess.user_id)
                return None
            return sess

    def note_interaction(self, token: str, idle_ms: int) -> None:
        with self._lock:
            sess = self._sessions.get(token)
            if sess is not None:
                sess.last_active = max(sess.last_active, self._clock() - max(0, idle_ms) / 1000.0)

    def end(self, token: str | None) -> None:
        with self._lock:
            self._sessions.pop(token or "", None)

    def end_user(self, user_id: int) -> None:
        with self._lock:
            for token in [t for t, s in self._sessions.items() if s.user_id == user_id]:
                del self._sessions[token]
