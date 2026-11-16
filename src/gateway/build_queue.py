"""The gateway-wide build queue: at most ``concurrency`` workbook builds at once across all users.

Phase 0 measured that CPU, not memory, limits builds (two at once each run about twice as slow), so
``POST /api/build/start`` is intercepted by the proxy. One build per user at a time. A start that finds a
free slot goes to the worker at once; otherwise it is queued under an id ``queued-<hex>`` that the
browser polls like a real job id, and the dispatcher forwards it when a slot frees. Pure bookkeeping:
no I/O and no threads here (the proxy drives it), so it is unit-testable with a fake clock.
"""
from __future__ import annotations

import secrets
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable

QUEUED_PREFIX = "queued-"


class AlreadyQueued(RuntimeError):
    """The user already has a build running or waiting."""

FINAL_STATUSES = frozenset({"done", "failed", "cancelled"})


@dataclass
class Waiting:
    queued_id: str
    user_id: int
    body: bytes
    content_type: str
    enqueued_at: float


@dataclass
class _Running:
    user_id: int
    job_id: str | None  # None while the start request is still on its way to the worker
    started_at: float
    queued_id: str | None = None


@dataclass
class _Alias:
    user_id: int
    real_id: str | None = None
    failure: dict | None = None
    cancelled: bool = False
    at: float = field(default_factory=time.time)


class BuildQueue:
    def __init__(self, concurrency: int = 2, *, max_build_seconds: float = 1800.0,
                 clock: Callable[[], float] = time.time) -> None:
        if concurrency < 1:
            raise ValueError("build concurrency must be at least 1")
        self.concurrency = int(concurrency)
        self.max_build_seconds = float(max_build_seconds)
        self._clock = clock
        self._lock = threading.RLock()
        self._running: dict[int, _Running] = {}
        self._waiting: deque[Waiting] = deque()
        self._aliases: dict[str, _Alias] = {}

    # ---- queries ----
    def has_build(self, user_id: int) -> bool:
        with self._lock:
            return user_id in self._running or any(w.user_id == user_id for w in self._waiting)

    def running(self) -> list[tuple[int, str | None, float]]:
        with self._lock:
            return [(r.user_id, r.job_id, r.started_at) for r in self._running.values()]

    def waiting_count(self) -> int:
        with self._lock:
            return len(self._waiting)

    def position(self, queued_id: str) -> int | None:
        with self._lock:
            for i, w in enumerate(self._waiting):
                if w.queued_id == queued_id:
                    return i + 1
            return None

    def _free(self) -> bool:
        return len(self._running) < self.concurrency

    # ---- immediate starts ----
    def try_acquire(self, user_id: int) -> bool:
        """Reserve a slot for a start going straight to the worker. False when none is free (or the
        user already has a build, which the caller should check first), or when others are waiting."""
        with self._lock:
            if user_id in self._running or self._waiting or not self._free():
                return False
            self._running[user_id] = _Running(user_id, None, self._clock())
            return True

    def started(self, user_id: int, job_id: str, queued_id: str | None = None) -> None:
        with self._lock:
            slot = self._running.get(user_id)
            if slot is None:  # pragma: no cover - defensive: reservation lost (worker gone meanwhile)
                slot = self._running[user_id] = _Running(user_id, None, self._clock())
            slot.job_id, slot.queued_id = str(job_id), queued_id
            if queued_id and queued_id in self._aliases:
                self._aliases[queued_id].real_id = str(job_id)

    def abandon(self, user_id: int, queued_id: str | None = None, failure: dict | None = None) -> None:
        """The start never became a build (the worker refused it or was unreachable)."""
        with self._lock:
            slot = self._running.get(user_id)
            if slot is not None and slot.job_id is None:
                del self._running[user_id]
            if queued_id and queued_id in self._aliases:
                self._aliases[queued_id].failure = failure or {"error": "The build could not be started."}

    # ---- queued starts ----
    def enqueue_unique(self, user_id: int, body: bytes, content_type: str) -> tuple[str, int]:
        """``enqueue`` for one user at most, checked and added under one lock (parallel starts race otherwise)."""
        with self._lock:
            if user_id in self._running or any(w.user_id == user_id for w in self._waiting):
                raise AlreadyQueued("a build is already running or waiting for this user")
            return self.enqueue(user_id, body, content_type)

    def enqueue(self, user_id: int, body: bytes, content_type: str) -> tuple[str, int]:
        with self._lock:
            qid = QUEUED_PREFIX + secrets.token_hex(8)
            self._waiting.append(Waiting(qid, user_id, bytes(body), content_type, self._clock()))
            self._aliases[qid] = _Alias(user_id, at=self._clock())
            return qid, len(self._waiting)

    def next_dispatch(self) -> Waiting | None:
        """Pop the oldest waiting start and reserve a slot for it, when one is free."""
        with self._lock:
            if not self._waiting or not self._free():
                return None
            w = self._waiting.popleft()
            self._running[w.user_id] = _Running(w.user_id, None, self._clock(), queued_id=w.queued_id)
            return w

    def cancel_queued(self, user_id: int, queued_id: str) -> bool:
        with self._lock:
            for w in list(self._waiting):
                if w.queued_id == queued_id and w.user_id == user_id:
                    self._waiting.remove(w)
                    self._aliases[queued_id].cancelled = True
                    return True
            return False

    def resolve(self, user_id: int, job_id: str) -> tuple[str, object]:
        """What a progress poll for ``job_id`` means: ``("queued", position)``, ``("forward", real_id)``,
        ``("failed", payload)``, ``("cancelled", None)`` or ``("unknown", None)`` (an id of another user,
        or one this gateway never issued)."""
        if not job_id.startswith(QUEUED_PREFIX):
            return "forward", job_id
        with self._lock:
            alias = self._aliases.get(job_id)
            if alias is None or alias.user_id != user_id:
                return "unknown", None
            if alias.cancelled:
                return "cancelled", None
            if alias.failure is not None:
                return "failed", alias.failure
            if alias.real_id:
                return "forward", alias.real_id
            pos = self.position(job_id)
            return ("queued", pos) if pos is not None else ("queued", 0)

    # ---- completion ----
    def finished(self, user_id: int, job_id: str | None = None) -> bool:
        """Release the user's slot (``job_id`` given: only when it is that job). True when released."""
        with self._lock:
            slot = self._running.get(user_id)
            if slot is None or (job_id is not None and slot.job_id != job_id):
                return False
            del self._running[user_id]
            return True

    def worker_gone(self, user_id: int) -> None:
        """The user's worker exited: its running build is over. Waiting starts stay queued."""
        with self._lock:
            slot = self._running.get(user_id)
            if slot is not None and slot.job_id is not None:
                del self._running[user_id]

    def drop_user(self, user_id: int) -> None:
        """The user was deleted or disabled: forget everything of theirs."""
        with self._lock:
            self._running.pop(user_id, None)
            self._waiting = deque(w for w in self._waiting if w.user_id != user_id)
            for qid in [q for q, a in self._aliases.items() if a.user_id == user_id]:
                del self._aliases[qid]

    def expire(self) -> list[int]:
        """Release slots held longer than ``max_build_seconds`` (a hung worker must not block others) and
        forget aliases older than a day. Returns the users whose slot was released."""
        now = self._clock()
        with self._lock:
            stale = [uid for uid, r in self._running.items() if now - r.started_at > self.max_build_seconds]
            for uid in stale:
                del self._running[uid]
            for qid in [q for q, a in self._aliases.items() if now - a.at > 86400]:
                del self._aliases[qid]
            return stale
