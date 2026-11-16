"""Parallel build starts from one user must not each take a place in the queue (each holds up to 64 MiB)."""
from __future__ import annotations

import pytest

from src.gateway.build_queue import AlreadyQueued, BuildQueue

pytestmark = pytest.mark.unit


def test_a_second_queued_start_from_the_same_user_is_refused():
    q = BuildQueue(1, max_build_seconds=60, clock=lambda: 1000.0)
    assert q.try_acquire(1)  # the only slot is taken
    q.enqueue_unique(2, b"{}", "application/json")
    with pytest.raises(AlreadyQueued):
        q.enqueue_unique(2, b"{}", "application/json")  # same user again, as parallel requests would
    with pytest.raises(AlreadyQueued):
        q.enqueue_unique(1, b"{}", "application/json")  # a user who is already building
    assert q.waiting_count() == 1
