"""Remote sessions end at an absolute lifetime and a client cannot keep one alive with idle_ms=0 (security review F-04)."""
from __future__ import annotations

from financial_trends_reporter.sessions import ABSOLUTE_SECONDS, IDLE_SECONDS, SessionTable


def test_idle_zero_pings_cannot_outlive_the_absolute_lifetime():
    now = [0.0]
    table = SessionTable(clock=lambda: now[0])
    token = table.create(1)
    while now[0] < ABSOLUTE_SECONDS - 60:
        now[0] += 60
        assert table.get(token) is not None
        table.note_interaction(token, 0)
    now[0] = ABSOLUTE_SECONDS + 1
    table.note_interaction(token, 0)
    assert table.get(token) is None
    assert table.expired_user_ids == [1]


def test_normal_idle_timeout_still_applies():
    now = [0.0]
    table = SessionTable(clock=lambda: now[0])
    token = table.create(1)
    now[0] = IDLE_SECONDS - 1
    assert table.get(token) is not None
    now[0] = IDLE_SECONDS + 1  # no interaction in between
    assert table.get(token) is None


def test_reported_interaction_extends_within_the_lifetime():
    now = [0.0]
    table = SessionTable(clock=lambda: now[0])
    token = table.create(1)
    now[0] = IDLE_SECONDS - 5
    table.note_interaction(token, 1000)
    now[0] = 2 * IDLE_SECONDS - 100
    assert table.get(token) is not None


def test_a_report_cannot_move_activity_backwards_or_claim_a_future_touch():
    now = [0.0]
    table = SessionTable(clock=lambda: now[0])
    token = table.create(1)
    now[0] = 100.0
    table.note_interaction(token, 10**9)  # absurd idle: no effect
    table.note_interaction(token, -5_000)  # negative: treated as 0, never in the future
    assert table.get(token).last_active == 100.0
