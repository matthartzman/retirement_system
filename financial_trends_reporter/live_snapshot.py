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
from datetime import date, datetime, time as dtime, timedelta, timezone, tzinfo
from pathlib import Path
from typing import Any, Callable, Iterable

_APP_ROOT = Path(__file__).resolve().parent
_REPO_ROOT = _APP_ROOT.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _nth_sunday(year: int, month: int, n: int) -> date:
    first = date(year, month, 1)
    return first + timedelta(days=(6 - first.weekday()) % 7 + 7 * (n - 1))


class _UsEastern(tzinfo):
    """America/New_York without zoneinfo: Windows has no system time-zone database, so
    ZoneInfo needs the tzdata package, which is not a dependency (and absent on CI). US rule
    since 2007: daylight time from 2:00 on the second Sunday of March to 2:00 on the first
    Sunday of November. The hour around each change is approximate; markets are shut then."""

    def utcoffset(self, dt):
        return timedelta(hours=-5) + self.dst(dt)

    def dst(self, dt):
        if dt is None:
            return timedelta(0)
        naive = dt.replace(tzinfo=None)
        start = datetime.combine(_nth_sunday(naive.year, 3, 2), dtime(2, 0))
        end = datetime.combine(_nth_sunday(naive.year, 11, 1), dtime(2, 0))
        return timedelta(hours=1) if start <= naive < end else timedelta(0)

    def tzname(self, dt):
        return "EDT" if self.dst(dt) else "EST"


EASTERN = _UsEastern()

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


def start_day_for(scope_from: Any, today: date) -> date:
    """Start Value date for the page's Time scope: the close before its first day (so YTD, from 1/1, is the
    12/31 close). A missing, unreadable or not-yet-past first day means year to date."""
    try:
        first = date.fromisoformat(str(scope_from or "").strip()[:10])
    except ValueError:
        return baseline_date(today.year)
    if first >= today:
        return baseline_date(today.year)
    return last_trading_day_on_or_before(first - timedelta(days=1))


def scope_prices(symbols: Iterable[str], day: date, *, closes_on_day: Callable) -> dict[str, Any]:
    """``baseline_prices``' shape for any other start day, from that day's closes (kept in memory)."""
    wanted = sorted({str(s).strip().upper() for s in symbols if str(s).strip()})
    found = _safe(closes_on_day, wanted, day, default={})
    prices = {s: {"price": float(found[s]), "source": "close"} for s in wanted if found.get(s)}
    return {"baseline_date": day.isoformat(), "prices": prices, "missing": [s for s in wanted if s not in prices]}


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


_CLOSES_ON: dict[tuple[str, str], tuple[float, float | None]] = {}
CLOSES_MISS_RETRY_SECONDS = 600


def closes_on(symbols: Iterable[str], day: date, *, snapshots: Callable = _default_snapshots,
              closes: Callable = _default_closes, clock: Callable = time.monotonic) -> dict[str, float]:
    """Closing prices on trading day ``day`` (an imported balance's own date): a stored snapshot taken
    between that close and the next open, else daily history. Kept in memory; a miss is retried after
    ``CLOSES_MISS_RETRY_SECONDS`` so the 60 s poll doesn't refetch it."""
    wanted = sorted({str(s).strip().upper() for s in symbols if str(s).strip()} - {""})
    key_day, now = day.isoformat(), clock()
    out: dict[str, float] = {}
    todo = []
    for sym in wanted:
        hit = _CLOSES_ON.get((sym, key_day))
        if hit and (hit[1] is not None or now - hit[0] < CLOSES_MISS_RETRY_SECONDS):
            if hit[1] is not None:
                out[sym] = hit[1]
        else:
            todo.append(sym)
    if todo:
        after, before = _between_sessions(day)
        found = {str(k).upper(): float(v) for k, v in _safe(snapshots, todo, after, before, default={}).items() if v and float(v) > 0}
        for sym in [t for t in todo if t not in found]:
            history = _safe(closes, sym, day - timedelta(days=10), day + timedelta(days=1), default={})
            on_or_before = sorted((d, px) for d, px in history.items() if d <= key_day and px and float(px) > 0)
            if on_or_before:
                found[sym] = float(on_or_before[-1][1])
        for sym in todo:
            _CLOSES_ON[(sym, key_day)] = (now, found.get(sym))
        out.update(found)
    return out


def imported_balance_days(monarch: dict | None, today: date) -> list[date]:
    """Trading days whose closes the reconciliation needs: an imported liquid balance older than the
    previous session, which today's day move can't back out."""
    prior = previous_trading_day(last_trading_day_on_or_before(today))
    out = set()
    for r in (monarch or {}).get("by_account") or []:
        if str(r.get("type") or "") in MONARCH_LIQUID_TYPES and r.get("as_of"):
            d = last_trading_day_on_or_before(date.fromisoformat(str(r["as_of"])))
            if d < prior:
                out.add(d)
    return sorted(out)


# ---- valuation, grouping, returns, tax, roll-up (pure: every input is passed in) ----

KIND_ORDER = ("Equity", "Fixed Income", "Real Estate", "Commodities", "Alternatives", "Cash")
MONARCH_LIQUID_TYPES = frozenset({"Retirement", "Investment", "HSA"})
MONARCH_DEBT_TYPES = frozenset({"Loan", "Credit card"})
RECONCILE_FLAG_PCT = 0.01
RECONCILE_ACCOUNT_FLAG_USD = 100.0
RECONCILE_MATCH_PCT = 0.05
ANNUALIZE_MIN_DAYS = 90


def _num(value: Any) -> float:
    try:
        return float(str(value).replace("$", "").replace(",", "").strip() or 0)
    except ValueError:
        return 0.0


def _is_cash_symbol(symbol: str) -> bool:
    """CASH and CASH (T-BILL)-style lots: valued at $1 a unit (a T-bill accretes to par)."""
    return symbol.startswith("CASH")


def classify_symbol(symbol: str, security_master: dict[str, dict]) -> tuple[str, str | None]:
    """(asset class, equity sub-class or None) from the shipped security master."""
    if _is_cash_symbol(symbol):
        return "Cash", None
    row = security_master.get(symbol) or {}
    asset_class = str(row.get("asset_class") or "").upper()
    style = str(row.get("style") or "").lower()
    if "EQUITY" in asset_class:
        if "small" in style and "value" in style:
            return "Equity", "Small-Cap Value"
        if "INTERNATIONAL" in asset_class or "EMERGING" in asset_class:
            return "Equity", "International Equity"
        return "Equity", "US Total Equity"
    if any(k in asset_class for k in ("BOND", "FIXED", "TREASUR", "TIPS", "MUNI")):
        return "Fixed Income", None
    if "COMMODIT" in asset_class:
        return "Commodities", None
    if asset_class == "CASH":
        return "Cash", None
    return "Other", None


def account_tax_type(account: str) -> str:
    """pre_tax / roth / taxable / hsa / cash / tax_free / unknown, from the plan's account naming."""
    from src.core import ACCOUNT_TYPES, _infer_type
    try:
        return ACCOUNT_TYPES[_infer_type(account)]["tax"]
    except (ValueError, KeyError):
        return "unknown"


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    return None if numerator is None or not denominator else numerator / denominator


def _annualized(return_pct: float | None, days: int) -> float | None:
    if return_pct is None or days < ANNUALIZE_MIN_DAYS or return_pct <= -1:
        return None
    return (1 + return_pct) ** (365 / days) - 1


def _positions(lots, quotes, baseline, security_master, baseline_day: date, today: date):
    """One valued row per lot in a liquid (non-checking) account, plus the symbols priced from a fallback.

    Modified Dietz over the lots: a lot held at the baseline contributes its baseline value to
    ``start``; one bought since is ``new_money`` (shares x purchase price) on its purchase date,
    time-weighted into ``weighted``; a reinvested dividend is neither, so all of it is gain."""
    base_prices = {k: _num(v.get("price")) for k, v in (baseline.get("prices") or {}).items()}
    period = (today - baseline_day).days or 1
    out, stale = [], set()
    for lot in lots:
        account = str(lot.get("account") or "").strip()
        symbol = str(lot.get("symbol") or lot.get("ticker") or "").strip().upper()
        shares = _num(lot.get("shares"))
        tax = account_tax_type(account)
        if not symbol or not shares or tax == "cash":
            continue
        purchase_price = _num(lot.get("purchase_price"))
        try:
            bought = date.fromisoformat(str(lot.get("purchase_date") or "").strip())
        except ValueError:
            bought = None
        held_at_baseline = bought is None or bought <= baseline_day
        if _is_cash_symbol(symbol):
            price, previous, base = 1.0, 1.0, 1.0
        else:
            quote = quotes.get(symbol) or {}
            price, previous = quote.get("price"), quote.get("previous_close")
            base = base_prices.get(symbol) or 0.0
            if not price:
                stale.add(symbol)
                price, previous = (base or purchase_price), None
            elif quote.get("stale"):
                stale.add(symbol)
        reinvested = str(lot.get("lot_type") or "").strip().lower().startswith("reinvest") and not held_at_baseline
        start = new_money = weighted = 0.0
        if held_at_baseline:
            start = shares * (base or purchase_price or price)
        elif not reinvested:
            new_money = shares * (purchase_price or base or price)
            weighted = new_money * max(0, (today - bought).days) / period
        asset_class, subclass = classify_symbol(symbol, security_master)
        out.append({
            "account": account, "symbol": symbol, "tax": tax, "asset_class": asset_class, "subclass": subclass,
            "current": shares * price, "start": start, "new_money": new_money, "weighted": weighted,
            "basis": shares * purchase_price if purchase_price else shares * price,
            "day": (shares * (price - previous)) if previous else None,
            "unclassified": asset_class == "Other",
            "title": str((security_master.get(symbol) or {}).get("notes") or "").strip(),
            "purchase_date": bought.isoformat() if bought else None, "shares": shares,
            "purchase_price": purchase_price, "reinvested": reinvested,
        })
    return out, sorted(stale)


def _summarize(name: str, members: list[dict], total_current: float, total_gain: float, days: int) -> dict:
    current = sum(m["current"] for m in members)
    start = sum(m["start"] for m in members)
    new_money = sum(m["new_money"] for m in members)
    known = [m["day"] for m in members if m["day"] is not None]
    day = sum(known) if known else None
    gain = current - start - new_money
    ret = _ratio(gain, start + sum(m["weighted"] for m in members))
    row = {"name": name, "start": round(start, 2), "new_money": round(new_money, 2), "current": round(current, 2),
           "share": _ratio(current, total_current),
           "day": None if day is None else round(day, 2), "day_pct": None if day is None else _ratio(day, current - day),
           "market_gain": round(gain, 2), "return_pct": ret, "share_of_gain": _ratio(gain, total_gain),
           "annualized_pct": _annualized(ret, days)}
    return row


def _position_rows(positions: list[dict]) -> list[dict]:
    """One row per lot for the page's Group By: everything it needs to total any grouping itself with the
    same formulas as ``_summarize`` (gain = current - start - new money; return over start + weighted new
    money; share and share of gain over the totals). Full precision, so a regrouped total matches the
    server's own groups; the page rounds for display. ``day`` is null when the lot has no previous close."""
    return [{"account": p["account"], "symbol": p["symbol"], "title": p["title"], "asset_class": p["asset_class"],
             "subclass": p["subclass"], "purchase_date": p["purchase_date"], "shares": p["shares"],
             "purchase_price": p["purchase_price"], "reinvested": p["reinvested"],
             "start": p["start"], "new_money": p["new_money"], "weighted": p["weighted"],
             "current": p["current"], "day": p["day"]} for p in positions]


def _checking_net_flows(accounts, flows_daily, liquid_accounts: set[str], baseline_day: date, today: date) -> float | None:
    """Net contributions through checking since the baseline (from_checking - to_checking) for the
    investment accounts mapped to liquid holdings accounts; None when no account is mapped.

    Shown for information only: the 12/31 statement balances plus these flows cannot give the
    return, because money also moves straight between accounts (an IRA rolled into an annuity,
    a Roth conversion) without passing through checking."""
    mapped = [str(a.get("account") or "") for a in accounts if str(a.get("role") or "") == "Investment"
              and str(a.get("mapped_investment_account") or "") in liquid_accounts]
    if not mapped:
        return None
    net = 0.0
    for name in mapped:
        for day_text, cell in (flows_daily.get(name) or {}).items():
            try:
                d = date.fromisoformat(day_text)
            except ValueError:
                continue
            if baseline_day < d <= today:
                net += _num(cell.get("from_checking")) - _num(cell.get("to_checking"))
    return net


def _hints(members: list[dict], value_then, delta: float, as_of: str | None, stale: set[str]) -> list[dict]:
    """Why a flagged account may disagree with Monarch, in the design's order (4.1): lots bought after
    Monarch's balance date, symbols priced from a fallback, one lot (else one symbol's total) worth
    within 5% of the gap, and which side is higher."""
    hints: list[dict] = []
    later = [m for m in members if as_of and m["purchase_date"] and m["purchase_date"] > as_of]
    if later:
        hints.append({"kind": "after_balance_date", "count": len(later), "value": round(sum(value_then(m) for m in later), 2)})
    old = sorted({m["symbol"] for m in members if m["symbol"] in stale})
    if old:
        hints.append({"kind": "stale_prices", "symbols": old})
    gap = abs(delta)

    def closest(candidates):
        near = [c for c in candidates if abs(c["value"] - gap) <= RECONCILE_MATCH_PCT * gap]
        return min(near, key=lambda c: abs(c["value"] - gap)) if near else None

    match = closest([{"symbol": m["symbol"], "shares": m["shares"], "purchase_date": m["purchase_date"],
                      "value": value_then(m)} for m in members])
    if match is None:
        by_symbol: dict[str, list[dict]] = {}
        for m in members:
            by_symbol.setdefault(m["symbol"], []).append(m)
        match = closest([{"symbol": s, "shares": sum(m["shares"] for m in ms), "purchase_date": None,
                          "value": sum(value_then(m) for m in ms)} for s, ms in sorted(by_symbol.items())])
    if match is not None:
        hints.append({"kind": "matches_position", **match, "value": round(match["value"], 2)})
    hints.append({"kind": "direction", "higher": "holdings" if delta > 0 else "monarch"})
    return hints


def _reconcile_accounts(positions: list[dict], stale: list[str], accounts, monarch: dict | None,
                        back_off: bool, today: date, closes_by_day: dict[str, dict[str, float]] | None = None) -> dict[str, Any]:
    """Holdings vs. Monarch account by account (design 4.1), through each Monarch account's
    ``mapped_investment_account``. Only Monarch liquid-type accounts take part. Each holdings value
    is backed off by its lots' day moves when Monarch is from an earlier day (the total's rule), so
    the account rows plus the unmapped holdings foot to the total's holdings value."""
    def value_then(p: dict) -> float:
        return p["current"] - ((p["day"] or 0.0) if back_off else 0.0)

    mapping: dict[str, str] = {}
    for a in accounts or []:
        name, target = str(a.get("account") or "").strip(), str(a.get("mapped_investment_account") or "").strip()
        if name and target:
            mapping.setdefault(name, target)
    by_holdings: dict[str, list[dict]] = {}
    for p in positions:
        by_holdings.setdefault(p["account"], []).append(p)

    matched: dict[str, list[tuple[str, float]]] = {}
    unmapped_monarch = []
    for r in (monarch or {}).get("by_account") or []:
        if str(r.get("type") or "") not in MONARCH_LIQUID_TYPES:
            continue
        name, value = str(r.get("account") or "").strip(), _num(r.get("value"))
        if name in mapping:
            matched.setdefault(mapping[name], []).append((name, value, str(r.get("as_of") or "") or None))
        else:
            unmapped_monarch.append({"name": name, "value": round(value, 2)})

    as_of, stale_set = (monarch or {}).get("latest_date"), set(stale)
    session = last_trading_day_on_or_before(today)
    prior = previous_trading_day(session)
    closes_by_day = closes_by_day or {}

    def valuer(balance_day: str | None):
        """Value each lot at the close of the imported balance's own day, so a balance that synced
        late compares like with like. Returns (value function, symbols with no close that day)."""
        if not balance_day:
            return value_then, set()
        d = last_trading_day_on_or_before(date.fromisoformat(balance_day))
        if d >= session:
            return (lambda p: p["current"]), set()
        if d == prior:
            return (lambda p: p["current"] - (p["day"] or 0.0)), set()
        closes = closes_by_day.get(d.isoformat()) or {}
        missing: set[str] = set()

        def at_close(p: dict) -> float:
            if _is_cash_symbol(p["symbol"]):
                return p["current"]
            px = closes.get(p["symbol"])
            if not px:
                missing.add(p["symbol"])
                return p["current"] - (p["day"] or 0.0)
            return p["shares"] * px
        return at_close, missing

    rows, footing = [], 0.0
    for holdings_account, names in matched.items():
        members = by_holdings.get(holdings_account, [])   # empty when every lot was sold: holdings 0
        dates = [d for _, _, d in names if d]
        balance_day = min(dates) if dates else as_of     # several imported accounts: the oldest balance
        value_at, missing = valuer(balance_day)
        held = sum(value_at(m) for m in members)
        monarch_value = sum(v for _, v, _ in names)
        delta = held - monarch_value
        delta_pct = _ratio(delta, monarch_value)
        # Both over 1% and over $100; with no Monarch balance to divide by, the $ test alone decides.
        flag = abs(delta) > RECONCILE_ACCOUNT_FLAG_USD and (delta_pct is None or abs(delta_pct) > RECONCILE_FLAG_PCT)
        footing += held
        rows.append({"holdings_account": holdings_account, "monarch_accounts": [n for n, _, _ in names],
                     "holdings_value": round(held, 2), "monarch_value": round(monarch_value, 2),
                     "delta": round(delta, 2), "delta_pct": delta_pct, "flag": flag,
                     # More than a session old: the row says when it last synced (fresh rows say nothing).
                     "balance_as_of": balance_day,
                     "balance_stale": bool(balance_day) and balance_day < prior.isoformat(),
                     "hints": _hints(members, value_at, delta, balance_day, stale_set | missing) if flag else []})
    rows.sort(key=lambda r: (-abs(r["delta"]), r["holdings_account"]))   # largest gap first

    unmapped_holdings = []
    for account, members in by_holdings.items():
        if account not in matched:
            held = sum(value_then(m) for m in members)
            footing += held
            unmapped_holdings.append({"account": account, "value": round(held, 2)})
    unmapped_holdings.sort(key=lambda r: (-r["value"], r["account"]))
    unmapped_monarch.sort(key=lambda r: (-r["value"], r["name"]))
    return {"accounts": rows, "unmapped_monarch": unmapped_monarch, "unmapped_holdings": unmapped_holdings,
            "footing": round(footing, 2),
            "monarch_stale": bool(as_of) and as_of < previous_trading_day(today).isoformat()}


TAX_TREATMENTS = frozenset({"pre_tax", "after_tax", "none"})


def _by_name(mapping: dict[str, Any] | None, name: str) -> Any:
    """``mapping[name]``, matching the account name ignoring case."""
    if not mapping:
        return None
    if name in mapping:
        return mapping[name]
    folded = name.casefold()
    return next((v for k, v in mapping.items() if str(k).casefold() == folded), None)


def non_liquid_tax_treatment(name: str, kind: str, overrides: dict[str, str] | None = None) -> str:
    """How a non-liquid row is taxed when paid out.

    pre_tax: the whole value is ordinary income (the pension, and the joint annuities, bought
    with IRA money). after_tax: only growth above the after-tax premium is (the single-life
    annuities). none: everything else. ``overrides`` (settings, by exact account name) win."""
    chosen = _by_name(overrides, name)
    if chosen in TAX_TREATMENTS:
        return chosen
    if kind != "Annuity/Pension":
        return "none"
    lowered = name.lower()
    return "pre_tax" if "pension" in lowered or "joint" in lowered else "after_tax"


def note_interest_to_come(name: str, note_items: list[dict] | None, today: date) -> tuple[str, float] | None:
    """(Planner note name, interest still to be paid) for a non-liquid row that is one of the Planner's
    Note Receivable items, matched when the row's name starts with the note's name ("RedMane Note Jan 2026"
    is "RedMane Note"). The imported balance is the remaining payments, so only their interest is income;
    principal comes back untaxed. Payments are annual and early in the year, so this year's is counted as paid."""
    folded = name.casefold()
    for note in note_items or []:
        note_name = str(note.get("name") or "").strip()
        if note_name and folded.startswith(note_name.casefold()):
            interest = sum(_num(v) for y, v in (note.get("interest_by_year") or {}).items() if int(y) > today.year)
            return note_name, interest
    return None


def _monarch_sections(monarch: dict | None, tax_overrides: dict[str, str] | None = None) -> dict[str, Any]:
    """Non-liquid assets, checking and debt from the latest Monarch balances (by account type)."""
    rows = (monarch or {}).get("by_account") or []
    as_of = (monarch or {}).get("latest_date")
    non_liquid, debt, checking, liquid_total = [], [], [], 0.0
    for r in rows:
        kind, name, value = str(r.get("type") or ""), str(r.get("account") or ""), _num(r.get("value"))
        if kind in MONARCH_LIQUID_TYPES:
            liquid_total += value
        elif kind == "Annuity/Pension":
            non_liquid.append({"name": name, "kind": "Fixed Income", "value": value, "type": kind})
        elif kind == "Real estate":
            non_liquid.append({"name": name, "kind": "Real Estate", "value": value, "type": kind})
        elif kind == "Other":
            # A note or loan receivable is fixed income; startup equity, vehicles, art are alternatives.
            fixed = any(w in name.lower() for w in ("note", "loan", "bond"))
            non_liquid.append({"name": name, "kind": "Fixed Income" if fixed else "Alternatives", "value": value, "type": kind})
        elif kind in MONARCH_DEBT_TYPES and value:
            debt.append({"name": name, "value": -value, "type": kind})
        elif kind == "Cash" and value > 0:
            checking.append({"name": name, "value": value})
    for r in non_liquid:
        r["tax_treatment"] = non_liquid_tax_treatment(r["name"], r["type"], tax_overrides)
    non_liquid.sort(key=lambda r: -r["value"])
    debt.sort(key=lambda r: -r["value"])
    total_nl = sum(r["value"] for r in non_liquid)
    for r in non_liquid:
        r["share"] = _ratio(r["value"], total_nl)
    return {"as_of": as_of, "liquid_total": liquid_total if monarch else None,
            "non_liquid": {"rows": non_liquid, "total": total_nl, "as_of": as_of},
            "debt": {"rows": debt, "total": sum(r["value"] for r in debt), "as_of": as_of},
            "checking": {"rows": checking, "total": sum(r["value"] for r in checking), "as_of": as_of}}


def _planner_tax(cfg: dict, today: date, ordinary: float, positions: list[dict], tax_rates: dict) -> dict[str, Any] | None:
    """The Retirement Planner's own after-tax method (``src.after_tax``) applied to today's balances, so this
    page and the Planner's reports estimate tax the same way: the heirs' 10-year bracket rate on pre-tax money,
    LTCG + NIIT + state on taxable-account gains (basis from the lots, no step-up: both owners are alive today)
    and the HSA cliff. Rates set in ``live_snapshot_settings.json`` still win. None when the Planner cannot
    price it (the page then falls back to flat rates)."""
    from types import SimpleNamespace
    from src import after_tax

    explicit = set(tax_rates.get("explicit") or [])
    try:
        taxable: dict[str, dict[str, list[float]]] = {}
        for p in positions:
            if p["tax"] != "taxable":
                continue
            basis = p["current"] if _is_cash_symbol(p["symbol"]) else p["basis"]
            mv_basis = taxable.setdefault(p["account"], {}).setdefault(p["symbol"], [0.0, 0.0])
            mv_basis[0] += p["current"]
            mv_basis[1] += basis
        # One stub lot per account + symbol (qty 1, so its price is the market value); the Planner reads the
        # basis ratio from it. Keyed by account too, since the same symbol can sit in two accounts.
        lots = {a: {f"{a}|{s}": [SimpleNamespace(qty=1.0, cost_basis=v[1])] for s, v in syms.items()} for a, syms in taxable.items()}
        prices = {f"{a}|{s}": v[0] for a, syms in taxable.items() for s, v in syms.items()}
        c = dict(cfg)
        c["taxable_ids"] = list(taxable)
        c["lot_engine"] = SimpleNamespace(lots=lots, prices=prices)
        year = today.year
        terminal = {"year": year, "trust_nw": 0.0, "pretax_nw": ordinary,
                    "hsa_nw": sum(p["current"] for p in positions if p["tax"] == "hsa"),
                    **{a: sum(v[0] for v in syms.values()) for a, syms in taxable.items()}}
        gains = after_tax.estimate_terminal_taxable_deferred_cap_gain_tax(c, terminal)
        rate = after_tax.resolve_terminal_pretax_rate(c, ordinary, year)
        hsa_tax = after_tax.hsa_terminal_tax(c, terminal["hsa_nw"], year)
    except Exception:  # noqa: BLE001 - an unreadable or partial plan must not take the page down
        return None
    ordinary_rate = tax_rates["pre_tax_rate"] if "pre_tax_rate" in explicit else rate
    ltcg = (gains["terminal_taxable_unrealized_gain_est"] * tax_rates["ltcg_rate"] if "ltcg_rate" in explicit
            else gains["terminal_deferred_taxable_cap_gain_tax"])
    return {"method": "planner", "pre_tax_rate": round(ordinary_rate, 4), "ordinary_tax": round(ordinary * ordinary_rate, 2),
            "unrealized_gain": round(gains["terminal_taxable_unrealized_gain_est"], 2), "ltcg_tax": round(ltcg, 2),
            "ltcg_rate": tax_rates["ltcg_rate"] if "ltcg_rate" in explicit else None,
            "ltcg_detail": {"federal": round(gains["terminal_deferred_ltcg_tax"], 2),
                            "niit": round(gains["terminal_deferred_niit_tax"], 2),
                            "state": round(gains["terminal_deferred_state_cap_gain_tax"], 2)},
            "hsa_balance": round(terminal["hsa_nw"], 2), "hsa_tax": round(hsa_tax, 2),
            "rate_source": "settings" if "pre_tax_rate" in explicit else "planner"}


def compute(*, lots, quotes, baseline, security_master, accounts, flows_daily, monarch, tax_rates, today: date, planner_cfg: dict | None = None,
            closes_by_day: dict[str, dict[str, float]] | None = None) -> dict[str, Any]:
    """The Live Snapshot body (design 4.3) from already-loaded inputs. Pure, so tests pin every formula.

    Returns at every level (total, class, ticker) are Modified Dietz over the current lots (see
    ``_positions``): robust to trades and to money moving between accounts, but blind to gains on
    lots sold during the year, which leave the holdings table."""
    baseline_day = date.fromisoformat(baseline["baseline_date"])
    days = (today - baseline_day).days
    positions, stale = _positions(lots, quotes, baseline, security_master, baseline_day, today)

    total = _summarize("Total", positions, 0.0, 0.0, days)
    current = total["current"]
    checking_flows = _checking_net_flows(accounts or [], flows_daily or {}, {p["account"] for p in positions}, baseline_day, today)
    liquid = {
        **{k: total[k] for k in ("start", "new_money", "current", "market_gain", "return_pct", "annualized_pct", "day", "day_pct")},
        "checking_net_flows": None if checking_flows is None else round(checking_flows, 2),
        "stale_symbols": stale, "unclassified_symbols": sorted({p["symbol"] for p in positions if p["unclassified"]}),
        "positions": _position_rows(positions),
    }
    day = total["day"]

    sections = _monarch_sections(monarch, tax_rates.get("non_liquid_tax"))
    reconciliation = None
    if sections["liquid_total"] is not None:
        # Monarch holds the last imported day's close; compare like with like.
        yesterday = bool(sections["as_of"]) and sections["as_of"] < today.isoformat()
        compare = current - (day or 0.0) if yesterday else current
        delta = _ratio(compare - sections["liquid_total"], sections["liquid_total"])
        reconciliation = {"holdings_value": round(compare, 2), "monarch_value": round(sections["liquid_total"], 2),
                          "monarch_as_of": sections["as_of"], "delta_pct": delta,
                          "flag": delta is None or abs(delta) > RECONCILE_FLAG_PCT,
                          **_reconcile_accounts(positions, stale, accounts, monarch, yesterday, today, closes_by_day)}

    pre_tax_balance = sum(p["current"] for p in positions if p["tax"] == "pre_tax")
    unrealized = sum(max(0.0, p["current"] - p["basis"]) for p in positions
                     if p["tax"] == "taxable" and not _is_cash_symbol(p["symbol"]))
    pre_rate, ltcg_rate = _num(tax_rates.get("pre_tax_rate")), _num(tax_rates.get("ltcg_rate"))
    basis = tax_rates.get("annuity_basis") or {}
    pre_tax_nl = annuity_gain = note_interest = 0.0
    basis_missing, note_rows = [], []
    note_items = (planner_cfg or {}).get("note_items")
    for r in sections["non_liquid"]["rows"]:
        # A Planner note with no explicit treatment: its future interest is ordinary income.
        note = note_interest_to_come(r["name"], note_items, today) if r["tax_treatment"] == "none" else None
        if note and _by_name(tax_rates.get("non_liquid_tax"), r["name"]) is None:
            r["tax_treatment"] = "note_interest"
            interest = min(note[1], max(0.0, r["value"]))
            note_interest += interest
            note_rows.append({"name": r["name"], "note": note[0], "interest": round(interest, 2)})
        elif r["tax_treatment"] == "pre_tax":
            pre_tax_nl += r["value"]
        elif r["tax_treatment"] == "after_tax":
            premium = _by_name(basis, r["name"])
            if premium is not None:
                annuity_gain += max(0.0, r["value"] - _num(premium))
            else:
                basis_missing.append(r["name"])  # premium unknown: not taxed, listed so the page can say so
    ordinary = pre_tax_balance + pre_tax_nl + annuity_gain + note_interest
    flat_total = ordinary * pre_rate + unrealized * ltcg_rate
    tax = {"pre_tax_balance": round(pre_tax_balance, 2), "pre_tax_non_liquid": round(pre_tax_nl, 2),
           "annuity_taxable_gain": round(annuity_gain, 2), "basis_missing": basis_missing,
           "note_interest": round(note_interest, 2), "note_rows": note_rows, "pre_tax_rate": pre_rate,
           "unrealized_gain": round(unrealized, 2), "ltcg_rate": ltcg_rate,
           "ordinary_tax": round(ordinary * pre_rate, 2), "ltcg_tax": round(unrealized * ltcg_rate, 2),
           "hsa_balance": 0.0, "hsa_tax": 0.0, "method": "flat", "flat_total": round(flat_total, 2),
           "total": round(flat_total, 2)}
    planner = _planner_tax(planner_cfg, today, ordinary, positions, tax_rates) if planner_cfg else None
    if planner:
        tax.update(planner)
        tax["total"] = round(tax["ordinary_tax"] + tax["ltcg_tax"] + tax["hsa_tax"], 2)

    by_kind: dict[str, float] = {}
    for p in positions:
        kind = "Alternatives" if p["asset_class"] == "Other" else p["asset_class"]
        by_kind[kind] = by_kind.get(kind, 0.0) + p["current"]
    for r in sections["non_liquid"]["rows"]:
        by_kind[r["kind"]] = by_kind.get(r["kind"], 0.0) + r["value"]
    if sections["checking"]["total"]:
        by_kind["Cash"] = by_kind.get("Cash", 0.0) + sections["checking"]["total"]
    gross = current + sections["checking"]["total"] + sections["non_liquid"]["total"]
    net_assets = gross - sections["debt"]["total"]
    totals = {"gross_assets": round(gross, 2), "net_assets": round(net_assets, 2),
              "after_tax_net_worth": round(net_assets - tax["total"], 2),
              "by_kind": {k: round(by_kind[k], 2) for k in KIND_ORDER if by_kind.get(k)}}

    return {"baseline_date": baseline["baseline_date"], "days": days, "year_fraction": days / 365,
            "liquid": liquid, "reconciliation": reconciliation, "non_liquid": sections["non_liquid"],
            "checking": sections["checking"], "debt": sections["debt"], "tax": tax, "totals": totals}


# ---- inputs and the /api/live-snapshot body ----

INDICES = (("^GSPC", "S&P 500"), ("^DJI", "Dow"), ("^IXIC", "Nasdaq"))
DELAYED_MINUTES = 15
DEFAULT_PRE_TAX_RATE = 0.25
DEFAULT_LTCG_RATE = 0.15
SETTINGS_FILENAME = "live_snapshot_settings.json"
INPUTS_TTL_SECONDS = 600

_DEFAULT_QUOTES = LiveQuoteCache()
_inputs_cache: dict[tuple, tuple[float, dict]] = {}
_inputs_lock = threading.Lock()


def _rate(value: Any) -> float | None:
    text = str(value if value is not None else "").strip()
    if not text:
        return None
    number = _num(text.rstrip("%"))
    return number / 100 if text.endswith("%") or number > 1 else number


SETUP_TREATMENTS = {"Taxed in full": "pre_tax", "Taxed above premium": "after_tax", "Not taxed": "none"}


def setup_tax_inputs(input_dir: str | Path, aliases: dict[str, str] | None = None) -> tuple[dict[str, str], dict[str, float]]:
    """({account: pre_tax|after_tax|none}, {account: after-tax premium}) from the Planner's Accounts & Sources
    rows (Tax Treatment / After-Tax Premium columns), matched to the imported account by name.
    ``aliases`` ({imported account name: setup row name}) adds the accounts matched on the reconcile page."""
    from src import ytd_tracking

    treatment: dict[str, str] = {}
    premium: dict[str, float] = {}
    for row in ytd_tracking.read_account_setup(input_dir):
        name = str(row.get("Account") or "").strip()
        if not name:
            continue
        if row.get("Tax Treatment") in SETUP_TREATMENTS:
            treatment[name] = SETUP_TREATMENTS[row["Tax Treatment"]]
        if str(row.get("After-Tax Premium") or "").strip():
            premium[name] = ytd_tracking.parse_money(row["After-Tax Premium"])
    folded_t = {k.casefold(): v for k, v in treatment.items()}
    folded_p = {k.casefold(): v for k, v in premium.items()}
    for imported, setup_name in (aliases or {}).items():
        if setup_name.casefold() in folded_t:
            treatment.setdefault(imported, folded_t[setup_name.casefold()])
        if setup_name.casefold() in folded_p:
            premium.setdefault(imported, folded_p[setup_name.casefold()])
    return treatment, premium


def saved_setup_aliases(base_dir: Path, balances_db: Path) -> dict[str, str]:
    """{imported account display name: Accounts & Sources row name}: the matches saved in the Trends account
    registry, and those saved on the Planner's reconcile page (which win)."""
    from . import account_registry

    try:
        accounts = account_registry.list_accounts(balances_db)
    except Exception:  # no balances store yet
        return {}
    aliases = {a["display_name"]: a["app_account"] for a in accounts if a.get("app_account")}
    try:
        from src import active_plan
        from src.reconcile import MAP_SETUP

        names = {a["account_key"]: a["display_name"] for a in accounts}
        with active_plan.workspace_store(base_dir) as store:
            mapping = store.monarch.mapping()
        aliases.update({names[key]: m["ref"] for key, m in mapping.items()
                        if m.get("kind") == MAP_SETUP and m.get("ref") and key in names})
    except Exception:  # no plan store: the registry matches still apply
        pass
    return aliases


def tax_rates(data_dir: str | Path, *, plan_ltcg: Any = "") -> dict[str, float]:
    """Rates for the estimated tax line. The plan has no rate for pre-tax balances, so it defaults
    to 25%; LTCG comes from the plan's tax-aware trades setting. ``live_snapshot_settings.json``
    in the data folder overrides either."""
    rates: dict[str, Any] = {"pre_tax_rate": DEFAULT_PRE_TAX_RATE, "ltcg_rate": _rate(plan_ltcg) or DEFAULT_LTCG_RATE,
                             "annuity_basis": {}, "non_liquid_tax": {}, "explicit": []}
    try:
        saved = json.loads((Path(data_dir) / SETTINGS_FILENAME).read_text(encoding="utf-8"))
        for key in ("pre_tax_rate", "ltcg_rate"):
            if _rate(saved.get(key)) is not None:
                rates[key] = _rate(saved.get(key))
                rates["explicit"].append(key)
        # {Monarch account name: after-tax premium} for the single-life annuities.
        rates["annuity_basis"] = {str(k): _num(v) for k, v in (saved.get("annuity_basis") or {}).items()}
        # {Monarch account name: pre_tax | after_tax | none}, overriding the name-based default.
        rates["non_liquid_tax"] = {str(k): v for k, v in (saved.get("non_liquid_tax") or {}).items() if v in TAX_TREATMENTS}
    except (OSError, ValueError, AttributeError):
        pass
    return rates


def _load_inputs_uncached(base_dir: Path, log_path: Path, balances_db: Path) -> dict[str, Any]:
    from src import portfolio_analytics
    from src.active_plan import dataset_rows_for_input_dir
    from . import balance_series
    from .trends_log import read_history
    from .trends_metrics import _plan_rows

    history = read_history(log_path)
    latest = history[-1] if history else {}
    plan = _plan_rows(base_dir, base_dir / "local_state" / "retirement_system_v10.db", "")
    return {
        "lots": dataset_rows_for_input_dir(base_dir / "input", "holdings"),
        "security_master": portfolio_analytics.read_security_master(),
        "accounts": (latest.get("holdings") or {}).get("by_account") or [],
        "flows_daily": latest.get("investment_flows_daily") or {},
        "log_as_of": latest.get("as_of_date"),
        "monarch": balance_series.snapshot_summary(balances_db),
        "tax_rates": _with_setup_tax(tax_rates(log_path.parent, plan_ltcg=plan.get(("Rebalancing", "Tax-aware Trades", "ltcg_rate"), "")),
                                     base_dir, balances_db),
        "people": household_nicknames(plan),
        "planner_cfg": planner_config(base_dir),
    }


def planner_config(base_dir: Path) -> dict[str, Any] | None:
    """The Planner's engine config for the plan (no live pricing, no projection run), or None when the plan
    cannot be built (e.g. a date of birth is missing): tax then falls back to flat rates."""
    try:
        from src.active_plan import peek_plan_data_for_input_dir
        from src.data_io import parse_client

        return parse_client(peek_plan_data_for_input_dir(base_dir / "input"), "", skip_live_pricing=True)
    except Exception:  # noqa: BLE001
        return None


def _with_setup_tax(rates: dict[str, Any], base_dir: Path, balances_db: Path) -> dict[str, Any]:
    """The Planner's per-account tax inputs, under the settings file's explicit per-account overrides."""
    treatment, premium = setup_tax_inputs(base_dir / "input", saved_setup_aliases(base_dir, balances_db))
    rates["non_liquid_tax"] = {**treatment, **rates.get("non_liquid_tax", {})}
    rates["annuity_basis"] = {**premium, **rates.get("annuity_basis", {})}
    return rates


def household_nicknames(plan: dict[tuple[str, str, str], str]) -> dict[str, str]:
    """{"h_nick", "w_nick"} from Plan Data's Household rows, the same nicknames the planner's reports use."""
    from src.parsing.client_sections import nickname

    return {key: nickname(plan.get(("Household", "", f"{member}_nickname"), ""), plan.get(("Household", "", f"{member}_name"), ""))
            for key, member in (("h_nick", "member_1"), ("w_nick", "member_2"))}


def account_labels(accounts, people: dict[str, str]) -> dict[str, str]:
    """{holdings account id: display label}, e.g. Member_1_401k -> "Matt 401k". The id stays the data key."""
    from src.person_labels import display_account

    return {a: display_account(a, people) for a in sorted({str(a or "").strip() for a in accounts} - {""})}


def load_inputs(base_dir: str | Path, log_path: str | Path, balances_db: str | Path, *, clock=time.monotonic) -> dict[str, Any]:
    """Everything except prices, cached ``INPUTS_TTL_SECONDS`` (it changes a few times a day at most).
    A failure is returned as ``{"error": ...}`` so the page can say what is missing."""
    key = (str(base_dir), str(log_path), str(balances_db))
    with _inputs_lock:
        hit = _inputs_cache.get(key)
        if hit and clock() - hit[0] < INPUTS_TTL_SECONDS:
            return hit[1]
        try:
            inputs = _load_inputs_uncached(Path(base_dir), Path(log_path), Path(balances_db))
        except Exception as exc:  # noqa: BLE001 - a locked store or bad file must not take the page down
            return {"error": f"{exc.__class__.__name__}: {exc}"}
        _inputs_cache[key] = (clock(), inputs)
        return inputs


def clear_inputs_cache() -> None:
    """Drop cached inputs (the reporter calls this after a run writes a new log entry)."""
    with _inputs_lock:
        _inputs_cache.clear()


def build(*, inputs: dict[str, Any], data_dir: str | Path, quote_cache=None, now: datetime | None = None,
          force: bool = False, previous_close_lookup: Callable | None = None,
          close_lookup: Callable | None = None, start_from: Any = None) -> dict[str, Any]:
    """The /api/live-snapshot body: header (time, market state, indices) plus ``compute()``.

    ``start_from`` is the first day of the page's Time scope; Start values, gains and returns are
    measured from the close before it (``start_day_for``). Balance-sheet figures are always today's."""
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(EASTERN).date()
    head: dict[str, Any] = {"as_of": now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                            "market": market_status(now), "delayed_minutes": DELAYED_MINUTES}
    if inputs.get("error"):
        return {**head, "error": inputs["error"]}
    quote_cache = quote_cache or _DEFAULT_QUOTES
    previous_close_lookup = previous_close_lookup or (lambda symbols, day: previous_closes(symbols, day))

    holdings = sorted({str(l.get("symbol") or "").strip().upper() for l in inputs["lots"]} - {""})
    priced = [s for s in holdings if not _is_cash_symbol(s)]
    symbols = priced + [s for s, _ in INDICES]
    quotes = {k: dict(v) for k, v in quote_cache.get(symbols, force=force).items()}
    need_previous = [s for s in symbols if quotes.get(s, {}).get("price") and not quotes[s].get("previous_close")]
    if need_previous:
        for sym, px in previous_close_lookup(need_previous, today).items():
            quotes.setdefault(sym, {})["previous_close"] = px

    close_lookup = close_lookup or closes_on
    start_day = start_day_for(start_from, today)
    baseline = (baseline_prices(priced, today.year, data_dir) if start_day == baseline_date(today.year)
                else scope_prices(priced, start_day, closes_on_day=close_lookup))
    closes_by_day = {d.isoformat(): close_lookup(priced, d) for d in imported_balance_days(inputs["monarch"], today)}
    body = compute(lots=inputs["lots"], quotes=quotes, baseline=baseline, security_master=inputs["security_master"],
                   accounts=inputs["accounts"], flows_daily=inputs["flows_daily"], monarch=inputs["monarch"],
                   tax_rates=inputs["tax_rates"], planner_cfg=inputs.get("planner_cfg"), today=today, closes_by_day=closes_by_day)
    indices = []
    for sym, label in INDICES:
        q = quotes.get(sym) or {}
        price, prev = q.get("price"), q.get("previous_close")
        indices.append({"symbol": sym, "label": label, "price": price,
                        "day_pct": (price / prev - 1) if price and prev else None, "stale": bool(q.get("stale", True))})
    labels = account_labels((l.get("account") for l in inputs["lots"]), inputs.get("people") or {})
    return {**head, **body, "indices": indices, "account_labels": labels, "quotes_age_seconds": quote_cache.age_seconds(symbols),
            "baseline_missing": baseline["missing"], "flows_as_of": inputs.get("log_as_of")}
