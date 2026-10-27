from __future__ import annotations

"""Live Snapshot view: live (delayed) valuation of liquid holdings plus the balance-sheet roll-up.

Step 2 pieces: the NYSE session calendar, the quote cache every /api/live-snapshot request
shares, and the prior year-end ("Start Value") prices. Design:
documentation/future/superpowers/plans/2026-10-27-live-snapshot-design.md.
"""

import json
import sys
import threading
import time
from datetime import date, datetime, time as dtime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable
from zoneinfo import ZoneInfo

_APP_ROOT = Path(__file__).resolve().parent
_REPO_ROOT = _APP_ROOT.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

EASTERN = ZoneInfo("America/New_York")

# NYSE full-day closures and 1 pm early closes. Static per year (design 4.2: a full exchange
# calendar is a v2 item); add the next year's dates each December.
NYSE_HOLIDAYS = frozenset(date.fromisoformat(d) for d in (
    "2025-01-01", "2025-01-09", "2025-01-20", "2025-02-17", "2025-04-18", "2025-05-26", "2025-06-19",
    "2025-07-04", "2025-09-01", "2025-11-27", "2025-12-25",
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25", "2026-06-19", "2026-07-03",
    "2026-09-07", "2026-11-26", "2026-12-25",
    "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31", "2027-06-18", "2027-07-05",
    "2027-09-06", "2027-11-25", "2027-12-24",
))
NYSE_EARLY_CLOSES = frozenset(date.fromisoformat(d) for d in (
    "2025-07-03", "2025-11-28", "2025-12-24", "2026-11-27", "2026-12-24", "2027-11-26",
))

PRE_MARKET_OPEN = dtime(4, 0)
REGULAR_OPEN = dtime(9, 30)
REGULAR_CLOSE = dtime(16, 0)
EARLY_CLOSE = dtime(13, 0)
POST_MARKET_CLOSE = dtime(20, 0)


# ---- market calendar ----

def is_trading_day(d: date) -> bool:
    return d.weekday() < 5 and d not in NYSE_HOLIDAYS


def last_trading_day_on_or_before(d: date) -> date:
    while not is_trading_day(d):
        d -= timedelta(days=1)
    return d


def previous_trading_day(d: date) -> date:
    return last_trading_day_on_or_before(d - timedelta(days=1))


def next_trading_day_after(d: date) -> date:
    d += timedelta(days=1)
    while not is_trading_day(d):
        d += timedelta(days=1)
    return d


def _session_close_time(d: date) -> dtime:
    return EARLY_CLOSE if d in NYSE_EARLY_CLOSES else REGULAR_CLOSE


def session_open_utc(d: date) -> datetime:
    return datetime.combine(d, REGULAR_OPEN, tzinfo=EASTERN).astimezone(timezone.utc)


def session_close_utc(d: date) -> datetime:
    return datetime.combine(d, _session_close_time(d), tzinfo=EASTERN).astimezone(timezone.utc)


def market_status(now: datetime | None = None) -> dict[str, Any]:
    """``state``: pre (4:00-9:30 ET), open, post (to 20:00 ET) or closed; weekends and holidays closed."""
    local = (now or datetime.now(timezone.utc)).astimezone(EASTERN)
    d, t = local.date(), local.time()
    early = d in NYSE_EARLY_CLOSES
    if not is_trading_day(d) or t < PRE_MARKET_OPEN or t >= POST_MARKET_CLOSE:
        state = "closed"
    elif t < REGULAR_OPEN:
        state = "pre"
    elif t < _session_close_time(d):
        state = "open"
    else:
        state = "post"
    return {"state": state, "early_close": early, "trading_day": is_trading_day(d)}


def _sql_utc(dt: datetime) -> str:
    """The price_snapshots.as_of format (SQLite CURRENT_TIMESTAMP, UTC)."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


# ---- shared quote cache ----

def _default_fetch(symbols: Iterable[str]) -> dict[str, dict[str, Any]]:
    from src import market_data
    return market_data.quote_details(symbols)


class LiveQuoteCache:
    """Per-symbol quotes kept ``ttl`` seconds and shared by every request, so several tabs or a
    Refresh-now click never multiply provider calls. One lock: concurrent requests wait for the
    fetch in flight instead of starting their own. ``force`` (Refresh now) still refetches at
    most once per ``min_force_interval`` seconds."""

    def __init__(self, fetch: Callable[[Iterable[str]], dict] = _default_fetch, *, ttl: float = 30.0,
                 min_force_interval: float = 10.0, clock: Callable[[], float] = time.monotonic):
        self._fetch = fetch
        self._ttl = ttl
        self._min_force_interval = min_force_interval
        self._clock = clock
        self._lock = threading.Lock()
        self._quotes: dict[str, tuple[float, dict[str, Any]]] = {}

    def get(self, symbols: Iterable[str], *, force: bool = False) -> dict[str, dict[str, Any]]:
        wanted = sorted({str(s).strip().upper() for s in symbols if str(s).strip()})
        with self._lock:
            now = self._clock()
            limit = self._min_force_interval if force else self._ttl
            stale = [s for s in wanted if s not in self._quotes or now - self._quotes[s][0] >= limit]
            if stale:
                for sym, quote in (self._fetch(stale) or {}).items():
                    self._quotes[str(sym).upper()] = (now, quote)
            return {s: self._quotes[s][1] for s in wanted if s in self._quotes}

    def age_seconds(self, symbols: Iterable[str]) -> float | None:
        """Age of the oldest cached quote among ``symbols`` (None when none is cached)."""
        with self._lock:
            times = [self._quotes[s][0] for s in (str(x).upper() for x in symbols) if s in self._quotes]
            return (self._clock() - min(times)) if times else None


# ---- prior year-end ("Start Value") and previous-close prices ----

def _default_snapshots(symbols: list[str], after_utc: str, before_utc: str) -> dict[str, float]:
    from src import portfolio_analytics
    return portfolio_analytics.snapshot_prices_between(symbols, after_utc, before_utc)


def _default_closes(symbol: str, start: date, end: date) -> dict[str, float]:
    from src import market_data
    return market_data.daily_closes(symbol, start, end)


def _safe(fn, *args, default):
    try:
        return fn(*args) or default
    except Exception:  # noqa: BLE001 - an offline provider or locked DB just leaves symbols missing
        return default


def _between_sessions(d: date) -> tuple[str, str]:
    """(after, before) UTC bounds in which a stored snapshot equals ``d``'s closing price."""
    return _sql_utc(session_close_utc(d)), _sql_utc(session_open_utc(next_trading_day_after(d)))


def baseline_date(year: int) -> date:
    """Start Value date for ``year``: the prior year's last trading day."""
    return last_trading_day_on_or_before(date(year - 1, 12, 31))


def baseline_prices(symbols: Iterable[str], year: int, data_dir: str | Path, *,
                    snapshots: Callable = _default_snapshots, closes: Callable = _default_closes) -> dict[str, Any]:
    """Closing prices on ``baseline_date(year)``.

    Order per symbol: the on-disk cache (``baseline_prices_<year>.json``, kept for good), a stored
    price snapshot taken between that close and the next open, then Yahoo daily history. Symbols
    found nowhere are listed in ``missing`` and retried on the next call. Never raises.
    """
    day = baseline_date(year)
    path = Path(data_dir) / f"baseline_prices_{year}.json"
    cached: dict[str, dict[str, Any]] = {}
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
        if saved.get("baseline_date") == day.isoformat():
            cached = {k: v for k, v in (saved.get("prices") or {}).items() if isinstance(v, dict) and v.get("price")}
    except (OSError, ValueError, AttributeError):
        cached = {}

    wanted = sorted({str(s).strip().upper() for s in symbols if str(s).strip()})
    prices = {s: cached[s] for s in wanted if s in cached}
    if "CASH" in wanted:
        prices["CASH"] = {"price": 1.0, "source": "cash"}
    todo = [s for s in wanted if s not in prices]
    found_new = False

    if todo:
        after, before = _between_sessions(day)
        for sym, px in _safe(snapshots, todo, after, before, default={}).items():
            sym = str(sym).upper()
            if sym in todo and px and float(px) > 0:
                prices[sym] = {"price": float(px), "source": "price_snapshot"}
                found_new = True
        for sym in [s for s in todo if s not in prices]:
            history = _safe(closes, sym, day - timedelta(days=10), day + timedelta(days=1), default={})
            on_or_before = sorted((d, px) for d, px in history.items() if d <= day.isoformat() and px and float(px) > 0)
            if on_or_before:
                prices[sym] = {"price": float(on_or_before[-1][1]), "source": "yahoo_history"}
                found_new = True

    if found_new:
        keep = {**cached, **{k: v for k, v in prices.items() if k != "CASH"}}
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"baseline_date": day.isoformat(), "prices": keep}, indent=1, sort_keys=True), encoding="utf-8")
            tmp.replace(path)
        except OSError:
            pass  # a read-only data dir only costs a refetch next time

    return {"baseline_date": day.isoformat(), "prices": prices, "missing": [s for s in wanted if s not in prices]}


def previous_closes(symbols: Iterable[str], today: date, *, snapshots: Callable = _default_snapshots) -> dict[str, float]:
    """Previous-session closes from stored snapshots, for symbols whose live quote came without
    one (every provider but Yahoo). Empty when no snapshot fell between that close and today's open."""
    wanted = sorted({str(s).strip().upper() for s in symbols if str(s).strip()})
    if not wanted:
        return {}
    # The latest session's previous close: on a weekend, Friday's price compares with Thursday's
    # close, as Yahoo's previousClose does.
    prior = previous_trading_day(last_trading_day_on_or_before(today))
    after, before = _between_sessions(prior)
    found = _safe(snapshots, wanted, after, before, default={})
    return {str(k).upper(): float(v) for k, v in found.items() if v and float(v) > 0}
