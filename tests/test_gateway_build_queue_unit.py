"""The gateway-wide build queue: slots, one build per user, queued ids, completion and expiry."""
from __future__ import annotations

import pytest

from src.gateway.build_queue import QUEUED_PREFIX, BuildQueue

pytestmark = pytest.mark.unit


def _queue(n=2):
    now = [1000.0]
    return BuildQueue(n, max_build_seconds=60, clock=lambda: now[0]), now


def test_slots_are_shared_across_users_and_one_build_per_user():
    q, _ = _queue(2)
    assert q.try_acquire(1) and q.try_acquire(2)
    assert not q.try_acquire(3)  # both slots taken
    assert q.has_build(1) and not q.has_build(3)
    q.started(1, "job-a")
    assert q.finished(1, "other-job") is False  # only that user's own job releases it
    assert q.finished(1, "job-a") is True
    assert q.try_acquire(3)


def test_a_reservation_that_fails_frees_its_slot():
    q, _ = _queue(1)
    assert q.try_acquire(1)
    q.abandon(1)
    assert not q.has_build(1) and q.try_acquire(2)


def test_queued_builds_dispatch_in_order_when_a_slot_frees():
    q, _ = _queue(1)
    assert q.try_acquire(1)
    q.started(1, "job-1")
    qid2, pos2 = q.enqueue(2, b"{}", "application/json")
    qid3, pos3 = q.enqueue(3, b"{}", "application/json")
    assert qid2.startswith(QUEUED_PREFIX) and (pos2, pos3) == (1, 2)
    assert not q.try_acquire(4)  # never jump the queue
    assert q.resolve(2, qid2) == ("queued", 1) and q.resolve(3, qid3) == ("queued", 2)
    assert q.next_dispatch() is None  # still full
    q.finished(1, "job-1")
    w = q.next_dispatch()
    assert w.user_id == 2 and w.queued_id == qid2
    q.started(2, "job-2", queued_id=qid2)
    assert q.resolve(2, qid2) == ("forward", "job-2")
    assert q.resolve(3, qid3) == ("queued", 1)


def test_a_queued_id_belongs_to_its_user_only():
    q, _ = _queue(1)
    q.try_acquire(1)
    qid, _ = q.enqueue(2, b"", "application/json")
    assert q.resolve(3, qid) == ("unknown", None)
    assert q.cancel_queued(3, qid) is False
    assert q.resolve(2, QUEUED_PREFIX + "0" * 16) == ("unknown", None)
    assert q.resolve(2, "a-real-worker-id") == ("forward", "a-real-worker-id")


def test_cancel_and_dispatch_failure_are_reported_to_the_poller():
    q, _ = _queue(1)
    q.try_acquire(1)
    qid_a, _ = q.enqueue(2, b"", "application/json")
    qid_b, _ = q.enqueue(3, b"", "application/json")
    assert q.cancel_queued(2, qid_a) and q.resolve(2, qid_a) == ("cancelled", None)
    q.abandon(1)
    w = q.next_dispatch()
    assert w.queued_id == qid_b
    q.abandon(3, qid_b, {"error": "no plan data"})
    assert q.resolve(3, qid_b) == ("failed", {"error": "no plan data"})
    assert not q.has_build(3)


def test_worker_exit_releases_a_running_build_but_keeps_waiting_ones():
    q, _ = _queue(1)
    q.try_acquire(1)
    q.started(1, "job-1")
    q.enqueue(1, b"", "application/json")  # the proxy refuses this case; the queue tolerates it
    q.worker_gone(1)
    assert q.running() == [] and q.waiting_count() == 1


def test_drop_user_forgets_everything():
    q, _ = _queue(1)
    q.try_acquire(1)
    q.started(1, "j")
    qid, _ = q.enqueue(1, b"", "application/json")
    q.drop_user(1)
    assert not q.has_build(1) and q.resolve(1, qid) == ("unknown", None)


def test_a_hung_build_is_released_after_the_maximum_duration():
    q, now = _queue(1)
    q.try_acquire(1)
    q.started(1, "j")
    now[0] += 59
    assert q.expire() == []
    now[0] += 2
    assert q.expire() == [1] and q.try_acquire(2)


def test_concurrency_must_be_positive():
    with pytest.raises(ValueError):
        BuildQueue(0)
