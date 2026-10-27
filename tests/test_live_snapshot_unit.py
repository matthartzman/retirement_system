"""Live Snapshot step 2: market hours, the shared quote cache, year-end baseline prices."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

import pytest

from financial_trends_reporter import live_snapshot as ls


def _et(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=ls.EASTERN)


# ---- market calendar ----

@pytest.mark.parametrize("when, state", [
    (_et(2026, 10, 27, 3, 59), "closed"),
    (_et(2026, 10, 27, 4, 0), "pre"),
    (_et(2026, 10, 27, 9, 29), "pre"),
    (_et(2026, 10, 27, 9, 30), "open"),
    (_et(2026, 10, 27, 15, 59), "open"),
    (_et(2026, 10, 27, 16, 0), "post"),
    (_et(2026, 10, 27, 20, 0), "closed"),
    (_et(2026, 10, 31, 11, 0), "closed"),   # Saturday
    (_et(2026, 11, 26, 11, 0), "closed"),   # Thanksgiving
    (_et(2026, 11, 27, 12, 59), "open"),    # early close day
    (_et(2026, 11, 27, 13, 0), "post"),
])
def test_market_state(when, state):
    assert ls.market_status(when)["state"] == state


def test_market_status_accepts_utc():
    assert ls.market_status(datetime(2026, 10, 27, 15, 18, tzinfo=timezone.utc))["state"] == "open"


def test_market_status_reports_early_close():
    assert ls.market_status(_et(2026, 11, 27, 10, 0))["early_close"] is True
    assert ls.market_status(_et(2026, 11, 30, 10, 0))["early_close"] is False


def test_trading_day_helpers():
    assert ls.last_trading_day_on_or_before(date(2026, 1, 4)) == date(2026, 1, 2)   # Sunday -> Friday
    assert ls.last_trading_day_on_or_before(date(2025, 12, 31)) == date(2025, 12, 31)
    assert ls.next_trading_day_after(date(2025, 12, 31)) == date(2026, 1, 2)       # skips New Year's Day
    assert ls.previous_trading_day(date(2026, 1, 20)) == date(2026, 1, 16)          # MLK Monday in between


@pytest.mark.parametrize("utc, offset_hours", [
    (datetime(2026, 3, 8, 6, 59, tzinfo=timezone.utc), -5),    # 01:59 EST, just before the March change
    (datetime(2026, 3, 8, 7, 0, tzinfo=timezone.utc), -4),     # 03:00 EDT
    (datetime(2026, 11, 1, 5, 59, tzinfo=timezone.utc), -4),   # 01:59 EDT
    (datetime(2026, 11, 1, 7, 0, tzinfo=timezone.utc), -5),    # 02:00 EST, after the November change
    (datetime(2027, 3, 14, 7, 0, tzinfo=timezone.utc), -4),
])
def test_eastern_dst_rule(utc, offset_hours):
    assert utc.astimezone(ls.EASTERN).utcoffset().total_seconds() == offset_hours * 3600


def test_eastern_matches_zoneinfo_where_tzdata_is_installed():
    zoneinfo = pytest.importorskip("zoneinfo")
    try:
        real = zoneinfo.ZoneInfo("America/New_York")
    except zoneinfo.ZoneInfoNotFoundError:
        pytest.skip("no time-zone database on this machine (the reason EASTERN exists)")
    t = datetime(2025, 1, 1, tzinfo=timezone.utc)
    while t.year < 2028:
        local = t.astimezone(real)
        change_day = local.date() in (ls._nth_sunday(local.year, 3, 2), ls._nth_sunday(local.year, 11, 1))
        if not (change_day and 1 <= local.hour <= 3):   # the documented approximate hour; markets are shut
            assert t.astimezone(ls.EASTERN).replace(tzinfo=None) == local.replace(tzinfo=None, fold=0), t
        t += timedelta(minutes=30)


def test_no_zoneinfo_dependency():
    # Windows has no system time-zone database; ZoneInfo there needs tzdata, which CI lacks.
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    for rel in ("financial_trends_reporter/live_snapshot.py", "src/market_data.py"):
        text = (root / rel).read_text(encoding="utf-8")
        assert "import zoneinfo" not in text and "from zoneinfo" not in text, rel


def test_session_open_utc_follows_dst():
    assert ls.session_open_utc(date(2026, 1, 2)) == datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc)
    assert ls.session_open_utc(date(2026, 7, 1)) == datetime(2026, 7, 1, 13, 30, tzinfo=timezone.utc)
    assert ls.session_close_utc(date(2026, 7, 1)) == datetime(2026, 7, 1, 20, 0, tzinfo=timezone.utc)
    assert ls.session_close_utc(date(2026, 11, 27)) == datetime(2026, 11, 27, 18, 0, tzinfo=timezone.utc)


# ---- shared quote cache ----

class _Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def _fetcher(calls):
    def fetch(symbols):
        symbols = sorted(set(symbols))
        calls.append(symbols)
        return {s: {"symbol": s, "price": 10.0 + len(calls)} for s in symbols}
    return fetch


def test_cache_reuses_within_ttl_and_refetches_after():
    calls, clock = [], _Clock()
    cache = ls.LiveQuoteCache(fetch=_fetcher(calls), ttl=30, clock=clock)
    assert cache.get(["ITOT", "IXUS"])["ITOT"]["price"] == 11.0
    clock.t += 29
    assert cache.get(["ITOT"])["ITOT"]["price"] == 11.0
    assert len(calls) == 1
    clock.t += 2
    assert cache.get(["ITOT"])["ITOT"]["price"] == 12.0


def test_cache_fetches_only_missing_symbols():
    calls, clock = [], _Clock()
    cache = ls.LiveQuoteCache(fetch=_fetcher(calls), ttl=30, clock=clock)
    cache.get(["ITOT"])
    out = cache.get(["ITOT", "AVUV"])
    assert calls == [["ITOT"], ["AVUV"]]
    assert set(out) == {"ITOT", "AVUV"}


def test_force_refresh_is_rate_limited():
    calls, clock = [], _Clock()
    cache = ls.LiveQuoteCache(fetch=_fetcher(calls), ttl=30, min_force_interval=10, clock=clock)
    cache.get(["ITOT"])
    clock.t += 5
    cache.get(["ITOT"], force=True)
    assert len(calls) == 1
    clock.t += 6
    cache.get(["ITOT"], force=True)
    assert len(calls) == 2


def test_cache_fetched_at_reports_oldest_symbol():
    calls, clock = [], _Clock()
    cache = ls.LiveQuoteCache(fetch=_fetcher(calls), ttl=30, clock=clock)
    cache.get(["ITOT"])
    clock.t += 10
    cache.get(["ITOT", "AVUV"])
    assert cache.age_seconds(["ITOT", "AVUV"]) == 10


# ---- year-end baseline prices ----

def test_baseline_date_is_last_trading_day_of_prior_year():
    assert ls.baseline_date(2026) == date(2025, 12, 31)
    assert ls.baseline_date(2028) == date(2027, 12, 31)


def test_baseline_order_snapshot_then_history_then_missing(tmp_path):
    history_calls = []

    def snapshots(symbols, after_utc, before_utc):
        assert (after_utc, before_utc) == ("2025-12-31 21:00:00", "2026-01-02 14:30:00")
        return {"ITOT": 140.0} if "ITOT" in symbols else {}

    def closes(symbol, start, end):
        history_calls.append(symbol)
        return {"2025-12-30": 60.0, "2025-12-31": 61.0, "2026-01-02": 62.0} if symbol == "IXUS" else {}

    out = ls.baseline_prices(["ITOT", "IXUS", "ZZZZ", "CASH"], 2026, tmp_path, snapshots=snapshots, closes=closes)
    assert out["baseline_date"] == "2025-12-31"
    assert out["prices"]["ITOT"] == {"price": 140.0, "source": "price_snapshot"}
    assert out["prices"]["IXUS"] == {"price": 61.0, "source": "yahoo_history"}
    assert out["prices"]["CASH"] == {"price": 1.0, "source": "cash"}
    assert out["missing"] == ["ZZZZ"]
    assert sorted(history_calls) == ["IXUS", "ZZZZ"]


def test_baseline_persists_and_reuses_disk_cache(tmp_path):
    ls.baseline_prices(["IXUS"], 2026, tmp_path, snapshots=lambda s, a, b: {}, closes=lambda s, a, b: {"2025-12-31": 61.0})
    saved = json.loads((tmp_path / "baseline_prices_2026.json").read_text())
    assert saved["prices"]["IXUS"]["price"] == 61.0

    def boom(*a):
        raise AssertionError("should come from the disk cache")

    out = ls.baseline_prices(["IXUS"], 2026, tmp_path, snapshots=boom, closes=boom)
    assert out["prices"]["IXUS"]["price"] == 61.0


def test_baseline_missing_symbols_are_retried_next_time(tmp_path):
    ls.baseline_prices(["ZZZZ"], 2026, tmp_path, snapshots=lambda s, a, b: {}, closes=lambda s, a, b: {})
    out = ls.baseline_prices(["ZZZZ"], 2026, tmp_path, snapshots=lambda s, a, b: {}, closes=lambda s, a, b: {"2025-12-31": 5.0})
    assert out["prices"]["ZZZZ"]["price"] == 5.0 and out["missing"] == []


def test_baseline_survives_corrupt_cache_and_history_errors(tmp_path):
    (tmp_path / "baseline_prices_2026.json").write_text("{not json")

    def broken(*a):
        raise OSError("offline")

    out = ls.baseline_prices(["IXUS"], 2026, tmp_path, snapshots=broken, closes=broken)
    assert out["missing"] == ["IXUS"]


# ---- previous close fallback ----

def test_previous_closes_from_snapshots_uses_prior_session():
    seen = {}

    def snapshots(symbols, after_utc, before_utc):
        seen["window"] = (after_utc, before_utc)
        return {"ITOT": 150.0}

    out = ls.previous_closes(["ITOT"], date(2026, 10, 27), snapshots=snapshots)
    # between the previous session's close and today's open
    assert seen["window"] == ("2026-10-26 20:00:00", "2026-10-27 13:30:00")
    assert out == {"ITOT": 150.0}


def test_previous_closes_on_weekend_uses_thursday_close():
    seen = {}

    def snapshots(symbols, after_utc, before_utc):
        seen["window"] = (after_utc, before_utc)
        return {}

    ls.previous_closes(["ITOT"], date(2026, 10, 31), snapshots=snapshots)   # Saturday
    assert seen["window"] == ("2026-10-29 20:00:00", "2026-10-30 13:30:00")
