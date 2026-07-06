from __future__ import annotations
import sys as _sys


# ===== BEGIN market_data_providers.py =====

"""
market_data_providers.py — resilient multi-provider market-pricing router.

Provider order:
  CACHE mode: cache first even when stale, then live providers, then holdings cost basis only if no cache exists.
  LIVE mode: live providers first, then cache even when stale, then holdings cost basis only if no cache exists.
  OFFLINE mode: cache even when stale, then holdings cost basis only if no cache exists.

Live providers are Financial Modeling Prep, Yahoo Finance, Alpha Vantage, and Stooq.

Uses FMP, Yahoo, Alpha Vantage, and Stooq; no deprecated pricing vendor endpoints are used.
"""

import csv
import json
import math
import os
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
try:
    from .version import USER_AGENT, CACHE_SCHEMA_VERSION
except Exception:
    USER_AGENT = "RetirementPlanSystem/8.4 (+local-advisor-tool)"
    CACHE_SCHEMA_VERSION = "8.4"

try:
    import requests  # type: ignore
except Exception:  # pragma: no cover
    requests = None  # type: ignore

FMP_QUOTE_SHORT_URL = "https://financialmodelingprep.com/api/v3/quote-short/{symbol}?apikey={api_key}"
FMP_QUOTE_URL = "https://financialmodelingprep.com/api/v3/quote/{symbol}?apikey={api_key}"
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1d&interval=1d"
ALPHA_VANTAGE_QUOTE_URL = "https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={symbol}&apikey={api_key}"
STOOQ_QUOTE_URL = "https://stooq.com/q/l/?s={symbol}&f=sd2t2ohlcv&h&e=csv"
STOOQ_QUOTE_HTTP_URL = "http://stooq.com/q/l/?s={symbol}&f=sd2t2ohlcv&h&e=csv"
YAHOO_CHART_QUERY2_URL = "https://query2.finance.yahoo.com/v8/finance/chart/{symbol}?range=1d&interval=1d&includePrePost=false"
YAHOO_QUOTE_URL = "https://query1.finance.yahoo.com/v7/finance/quote?symbols={symbol}"
NASDAQ_INFO_URL = "https://api.nasdaq.com/api/quote/{symbol}/info?assetclass={asset_class}"

# Many public quote endpoints reject Python/library user agents even when the
# same URL works in a browser.  Keep the product UA in diagnostics, but send a
# browser-compatible UA on live quote requests so Yahoo/Nasdaq/Stooq do not
# fail purely because the desktop app is a Python process.
QUOTE_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36 RetirementPlanSystem"
)


def _clean_secret(value: object) -> Optional[str]:
    text = str(value or "").strip()
    if not text or text.upper() in {"YOUR_KEY", "YOUR_KEY_HERE", "REPLACE_ME", "NONE", "N/A", "NA"}:
        return None
    return text


def _secret_fingerprint(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    try:
        import hashlib
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    except Exception:
        return None


def _clean_symbol(symbol: str) -> str:
    return (symbol or "").strip().upper()


def _format_local_cache_timestamp(value: object) -> str:
    """Format cache timestamps as local MM/DD/YYYY hh:mm AM/PM for user-facing text.

    Diagnostics retain the raw UTC/ISO values for traceability, but workbook and
    UI-facing summary fields use this compact local-time label. Ranges generated
    by pricing_source_summary are supported as "start to end".
    """
    text = str(value or "").strip()
    if not text:
        return ""
    if " to " in text:
        parts = [part.strip() for part in text.split(" to ", 1)]
        formatted = [_format_local_cache_timestamp(part) for part in parts]
        if all(formatted):
            # Raw cache records can differ by seconds but format to the same
            # user-facing minute.  Showing "11:06 AM to 11:06 AM" looks like
            # a bug, so collapse identical formatted endpoints to one label.
            if formatted[0] == formatted[1]:
                return formatted[0]
            return f"{formatted[0]} to {formatted[1]}"
        return text
    try:
        from datetime import datetime, timezone
        normalized = text.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        local_dt = dt.astimezone()
        return local_dt.strftime("%m/%d/%Y %I:%M %p")
    except Exception:
        try:
            from datetime import datetime, timezone
            local_dt = datetime.fromtimestamp(float(text), tz=timezone.utc).astimezone()
            return local_dt.strftime("%m/%d/%Y %I:%M %p")
        except Exception:
            return text


def _is_good_price(value: object) -> bool:
    try:
        if value is None:
            return False
        text = str(value).strip()
        if not text or text.upper() in {"N/D", "NA", "N/A", "NULL", "NONE", "-", "--"}:
            return False
        f = float(text.replace(",", ""))  # type: ignore[arg-type]
        return math.isfinite(f) and f > 0
    except Exception:
        return False


def _to_price(value: object) -> Optional[float]:
    if not _is_good_price(value):
        return None
    return float(str(value).strip().replace(",", ""))


def _now() -> float:
    return time.time()




def _redact_url(url: str) -> str:
    for key in ("apikey=", "api_key="):
        if key in url.lower():
            parts = urllib.parse.urlsplit(url)
            q = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
            redacted = [(k, "***" if k.lower() in ("apikey", "api_key") else v) for k, v in q]
            return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(redacted), parts.fragment))
    return url


def _quote_headers(accept: str = "application/json,*/*") -> Dict[str, str]:
    return {
        "User-Agent": QUOTE_BROWSER_USER_AGENT,
        "Accept": accept,
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Connection": "close",
    }


def _parse_money_text(value: object) -> Optional[float]:
    text = str(value or "").strip()
    if not text:
        return None
    text = text.replace("$", "").replace(",", "").replace("USD", "").strip()
    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]
    return _to_price(text)


@dataclass
class MarketDataProvider:
    cache_path: str | Path = "output/market_price_cache.json"
    diagnostics_path: str | Path = "output/pricing_diagnostics.json"
    ttl_seconds: int = 24 * 60 * 60
    timeout_seconds: int = 8
    max_retries: int = 2
    fallback_prices: Dict[str, float] = field(default_factory=dict)
    frozen_prices: Dict[str, float] = field(default_factory=dict)
    frozen_metadata: Dict[str, object] = field(default_factory=dict)
    # Holdings pricing behavior is configured from multi_user/system_config.csv, not environment variables.
    # Valid modes:
    #   CACHE   = use a fresh cache first; fetch live only when cache is missing/stale
    #   LIVE    = fetch live first; fall back to cache/cost basis
    #   OFFLINE = never fetch live; use cache/cost basis only
    pricing_mode: str = "CACHE"
    use_live: bool = True
    cache_first: bool = True
    fmp_api_key: Optional[str] = None
    alpha_vantage_api_key: Optional[str] = None
    user_agent: str = USER_AGENT
    alpha_vantage_min_interval_seconds: float = 1.1

    def __post_init__(self) -> None:
        _project_root = Path(__file__).resolve().parent.parent
        self.cache_path = Path(self.cache_path)
        self.diagnostics_path = Path(self.diagnostics_path)
        try:
            self.timeout_seconds = max(1, int(float(os.getenv("RETIREMENT_SYSTEM_PRICE_TIMEOUT_SECONDS", str(self.timeout_seconds)))))
        except Exception:
            pass
        try:
            self.max_retries = max(1, int(float(os.getenv("RETIREMENT_SYSTEM_PRICE_MAX_RETRIES", str(self.max_retries)))))
        except Exception:
            pass
        if not self.cache_path.is_absolute():
            self.cache_path = _project_root / self.cache_path
        if not self.diagnostics_path.is_absolute():
            self.diagnostics_path = _project_root / self.diagnostics_path
        self.refresh_api_keys()
        self.cache: Dict[str, Dict[str, object]] = self._load_cache()
        self.failures: List[Dict[str, object]] = []
        self.sources: Dict[str, str] = {}
        self.prices: Dict[str, float] = {}
        self.provider_attempts: Dict[str, List[str]] = {}
        self._global_provider_failures: Dict[str, str] = {}
        self._last_alpha_vantage_call: float = 0.0

    def refresh_api_keys(self) -> None:
        """Load API keys from environment variables and the local secret store.

        Production desktop installs commonly start the local server from a shell
        or service wrapper that provides provider keys through environment
        variables.  Earlier builds documented that path but did not actually
        read it, so FMP/Alpha were silently skipped outside tests.  Precedence:
        explicit config/UI values, then environment, then encrypted secret store.
        """
        if not self.fmp_api_key:
            for name in ("RETIREMENT_SYSTEM_FMP_API_KEY", "FMP_API_KEY", "FINANCIAL_MODELING_PREP_API_KEY"):
                val = _clean_secret(os.environ.get(name))
                if val:
                    self.fmp_api_key = val
                    break
        if not self.alpha_vantage_api_key:
            for name in ("RETIREMENT_SYSTEM_ALPHA_VANTAGE_API_KEY", "ALPHA_VANTAGE_API_KEY"):
                val = _clean_secret(os.environ.get(name))
                if val:
                    self.alpha_vantage_api_key = val
                    break
        if not self.fmp_api_key or not self.alpha_vantage_api_key:
            try:
                from .secrets_store import get_secret
            except Exception:
                try:
                    from src.secrets_store import get_secret
                except Exception:
                    get_secret = None  # type: ignore
            if get_secret is not None:
                if not self.fmp_api_key:
                    self.fmp_api_key = _clean_secret(get_secret("fmp_api_key"))
                if not self.alpha_vantage_api_key:
                    self.alpha_vantage_api_key = _clean_secret(get_secret("alpha_vantage_api_key"))

    def api_key_sources(self) -> Dict[str, object]:
        def _source(kind: str) -> str:
            if kind == "fmp":
                if _clean_secret(os.environ.get("RETIREMENT_SYSTEM_FMP_API_KEY")):
                    return "RETIREMENT_SYSTEM_FMP_API_KEY"
                if _clean_secret(os.environ.get("FMP_API_KEY")):
                    return "FMP_API_KEY"
                if _clean_secret(os.environ.get("FINANCIAL_MODELING_PREP_API_KEY")):
                    return "FINANCIAL_MODELING_PREP_API_KEY"
                return "configured/secret-store" if self.fmp_api_key else "not configured"
            if _clean_secret(os.environ.get("RETIREMENT_SYSTEM_ALPHA_VANTAGE_API_KEY")):
                return "RETIREMENT_SYSTEM_ALPHA_VANTAGE_API_KEY"
            if _clean_secret(os.environ.get("ALPHA_VANTAGE_API_KEY")):
                return "ALPHA_VANTAGE_API_KEY"
            return "configured/secret-store" if self.alpha_vantage_api_key else "not configured"
        return {
            "fmp": _source("fmp"),
            "alpha_vantage": _source("alpha"),
            "fmp_fingerprint": _secret_fingerprint(self.fmp_api_key),
            "alpha_vantage_fingerprint": _secret_fingerprint(self.alpha_vantage_api_key),
        }

    def configure_transport(self, timeout_seconds: object | None = None, max_retries: object | None = None) -> None:
        if timeout_seconds is not None:
            try:
                self.timeout_seconds = max(1, int(float(timeout_seconds)))
            except Exception:
                pass
        if max_retries is not None:
            try:
                self.max_retries = max(1, int(float(max_retries)))
            except Exception:
                pass

    def configure_api_keys(self, fmp_api_key: object = "", alpha_vantage_api_key: object = "") -> None:
        """Apply API keys from multi_user/system_config.csv.

        CSV location:
          Market Pricing,API,fmp_api_key,<key>
          Market Pricing,API,alpha_vantage_api_key,<key>
        """
        before = (self.fmp_api_key, self.alpha_vantage_api_key)
        fmp_from_csv = _clean_secret(fmp_api_key)
        alpha_from_csv = _clean_secret(alpha_vantage_api_key)
        if fmp_from_csv:
            self.fmp_api_key = fmp_from_csv
        if alpha_from_csv:
            self.alpha_vantage_api_key = alpha_from_csv
        self.refresh_api_keys()
        if before != (self.fmp_api_key, self.alpha_vantage_api_key):
            self.reset_runtime_state(clear_failures=True, clear_provider_failures=True)

    def configure_holdings_pricing(self, mode: str = "CACHE", cache_hours: object = 24) -> None:
        """Apply holdings-pricing settings from multi_user/system_config.csv.

        mode values:
          CACHE   - use cached price first even when stale; call live providers only when no cache exists
          LIVE    - call live providers first, then fall back to cache even when stale, then cost basis
          OFFLINE - never call live providers; use cache even when stale, then cost basis only if no cache exists
          FROZEN  - use the saved pricing snapshot first for reproducible builds
        """
        mode_clean = str(mode or "CACHE").strip().upper()
        aliases = {
            "CACHE_FIRST": "CACHE",
            "CACHE-FIRST": "CACHE",
            "CACHED": "CACHE",
            "REALTIME": "LIVE",
            "REAL_TIME": "LIVE",
            "REAL-TIME": "LIVE",
            "NO": "OFFLINE",
            "FALSE": "OFFLINE",
            "OFF": "OFFLINE",
            "YES": "CACHE",
            "TRUE": "CACHE",
            "ON": "CACHE",
        }
        mode_clean = aliases.get(mode_clean, mode_clean)
        if mode_clean not in ("CACHE", "LIVE", "OFFLINE", "FROZEN"):
            mode_clean = "CACHE"
        try:
            hours = float(str(cache_hours).strip())
            if hours <= 0:
                hours = 24.0
        except Exception:
            hours = 24.0
        self.pricing_mode = mode_clean
        self.ttl_seconds = int(hours * 60 * 60)
        self.cache_first = mode_clean in ("CACHE", "FROZEN")
        self.use_live = mode_clean in ("CACHE", "LIVE")
        if mode_clean != "FROZEN":
            self.frozen_prices = {}
            self.frozen_metadata = {}
        # Treat each explicit configuration as the start of a new build/refresh
        # pricing run.  This prevents stale in-process quote memoization and
        # provider-wide failures from leaking across user actions.
        self.reset_runtime_state(clear_failures=True, clear_provider_failures=True)

    def _load_cache(self) -> Dict[str, Dict[str, object]]:
        try:
            if self.cache_path.exists():
                raw = json.loads(self.cache_path.read_text(encoding="utf-8"))
                return raw if isinstance(raw, dict) else {}
        except Exception:
            pass
        return {}

    def _save_cache(self) -> None:
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(json.dumps(self.cache, indent=2, sort_keys=True), encoding="utf-8")
        except Exception:
            pass

    def set_fallback_prices(self, prices: Dict[str, float]) -> None:
        for sym, px in prices.items():
            s = _clean_symbol(sym)
            if s and _is_good_price(px):
                self.fallback_prices[s] = float(px)

    def set_frozen_prices(self, prices: Dict[str, float], metadata: Dict[str, object] | None = None) -> None:
        frozen: Dict[str, float] = {}
        for sym, px in (prices or {}).items():
            s = _clean_symbol(sym)
            if s and _is_good_price(px):
                frozen[s] = float(px)
        self.frozen_prices = frozen
        self.frozen_metadata = dict(metadata or {})
        if frozen:
            self.pricing_mode = "FROZEN"
            self.cache_first = True
            self.use_live = False
        self.reset_runtime_state(clear_failures=True, clear_provider_failures=True)

    def reset_runtime_state(self, clear_failures: bool = True, clear_provider_failures: bool = True) -> None:
        """Clear per-run memoized quote state.

        The dashboard server is long-lived, while provider failures and quote
        lookups are per-build/per-refresh facts.  Without this reset, a transient
        DNS/rate-limit/provider failure can cause later refreshes to skip live
        sources until the server is restarted, and a cached in-memory quote can
        make the Refresh Prices action appear to do nothing.
        """
        self.sources = {}
        self.prices = {}
        self.provider_attempts = {}
        if clear_failures:
            self.failures = []
        if clear_provider_failures:
            self._global_provider_failures = {}

    def _cache_timestamp_epoch(self, rec: Dict[str, object]) -> float:
        """Return cache timestamp as epoch seconds. Supports v6 and v7 schemas."""
        raw = rec.get("timestamp_epoch", rec.get("timestamp", 0))
        try:
            return float(raw or 0)
        except Exception:
            pass
        # ISO fallback for external/manual cache files.
        text = str(rec.get("timestamp_iso") or rec.get("timestamp") or "").strip()
        if text.endswith(("Z", "z")):
            text = text[:-1] + "+00:00"
        try:
            from datetime import datetime, timezone
            dt = datetime.fromisoformat(text)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except Exception:
            return 0.0

    def _cache_record(self, symbol: str, price: float, source: str) -> Dict[str, object]:
        from datetime import datetime, timezone
        ts = _now()
        return {
            "symbol": symbol,
            "price": float(price),
            "provider": source,
            "source": source,
            "timestamp_epoch": ts,
            "timestamp_iso": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(),
            "ttl_hours": round(self.ttl_seconds / 3600, 2),
        }

    def _cached_price(self, symbol: str, allow_stale: bool = False) -> Optional[float]:
        rec = self.cache.get(symbol)
        if not isinstance(rec, dict):
            return None
        px = rec.get("price")
        ts = self._cache_timestamp_epoch(rec)
        if not _is_good_price(px):
            return None
        if allow_stale or (_now() - ts <= self.ttl_seconds):
            return float(px)  # type: ignore[arg-type]
        return None

    def _best_guess_cause(self, provider: str, exc: object | None = None, status_code: int | None = None, payload: object | None = None) -> str:
        text = "" if exc is None else str(exc)
        low = text.lower()
        if status_code in (401, 403):
            return f"{provider} rejected the request; likely invalid/missing API key, plan limit, or blocked network."
        if status_code == 404:
            return f"{provider} returned 404; ticker may be unsupported, delisted, or requires a provider-specific symbol."
        if status_code == 429:
            return f"{provider} rate limit exceeded; wait or use another provider/API key."
        if status_code and status_code >= 500:
            return f"{provider} returned a server error; usually temporary."
        if "timed out" in low or "timeout" in low:
            return f"Network timeout reaching {provider}; check firewall, VPN/proxy, DNS, or provider latency."
        if any(k in low for k in ["name or service", "nodename", "dns", "failed to resolve", "name resolution", "temporary failure in name resolution", "nameresolutionerror"]) or isinstance(exc, socket.gaierror):
            return f"DNS lookup failed for {provider}; check internet access, VPN/proxy, DNS, or corporate filtering."
        if "ssl" in low or "certificate" in low:
            return f"TLS/SSL verification failed for {provider}; check corporate proxy or certificate inspection."
        if "connection refused" in low or "network is unreachable" in low:
            return f"Network connection failed for {provider}; check internet, firewall, VPN, or proxy."
        if payload is not None:
            return f"{provider} response did not contain a usable price; ticker may be unsupported or provider quota/data is unavailable."
        return f"Unknown {provider} pricing failure."

    def _is_global_failure(self, cause: str | None) -> bool:
        if not cause:
            return False
        low = cause.lower()
        return any(k in low for k in ["dns lookup failed", "network timeout", "network connection failed", "tls/ssl", "firewall", "vpn", "proxy", "rate limit exceeded", "server error"])

    def _record_failure(self, symbol: str, provider: str, url: str, cause: str, detail: str = "", status_code: int | None = None) -> None:
        self.failures.append({
            "symbol": symbol,
            "provider": provider,
            "url": _redact_url(url),
            "status_code": status_code,
            "cause": cause,
            "detail": detail[:500],
            "timestamp": _now(),
        })

    def _urllib_json(self, provider: str, symbol: str, url: str) -> Tuple[Optional[object], Optional[str]]:
        try:
            req = urllib.request.Request(url, headers=_quote_headers("application/json,*/*"))
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as raw:
                return json.loads(raw.read().decode("utf-8", errors="replace")), None
        except urllib.error.HTTPError as exc:
            return None, self._best_guess_cause(provider, exc=exc, status_code=exc.code)
        except Exception as exc:
            return None, self._best_guess_cause(provider, exc=exc)

    def _get_json(self, provider: str, symbol: str, url: str) -> Tuple[Optional[object], Optional[str]]:
        """Fetch JSON with both requests and urllib transports.

        Some desktop environments configure proxies/certificates differently for
        requests and urllib.  Earlier builds used requests exclusively when it
        was installed, so a requests-only proxy/TLS failure made every JSON
        provider look broken even though urllib could still reach the network.
        """
        last_cause = ""
        for attempt in range(self.max_retries):
            if requests is not None:
                try:
                    resp = requests.get(url, timeout=self.timeout_seconds, headers=_quote_headers("application/json,*/*"))
                    if resp.status_code != 200:
                        cause = self._best_guess_cause(provider, status_code=resp.status_code)
                        self._record_failure(symbol, provider, url, cause, resp.text[:300], resp.status_code)
                        return None, cause
                    return resp.json(), None
                except Exception as exc:
                    last_cause = self._best_guess_cause(provider, exc=exc)
                    # Fall through to urllib before deciding the provider is
                    # globally unavailable.  This materially improves local
                    # Windows/macOS deployments behind proxies or TLS scanners.
                    payload, urllib_cause = self._urllib_json(provider + " urllib-fallback", symbol, url)
                    if urllib_cause is None:
                        return payload, None
                    self._record_failure(symbol, provider, url, last_cause, repr(exc))
                    self._record_failure(symbol, provider + " urllib-fallback", url, urllib_cause)
                    last_cause = urllib_cause or last_cause
            else:
                payload, cause = self._urllib_json(provider, symbol, url)
                if cause is None:
                    return payload, None
                self._record_failure(symbol, provider, url, cause)
                last_cause = cause

            if attempt + 1 >= self.max_retries or self._is_global_failure(last_cause):
                return None, last_cause or f"{provider} failed after retries."
            time.sleep(0.35 * (attempt + 1))
        return None, last_cause or f"{provider} failed after retries."

    def _fetch_fmp(self, symbol: str) -> Optional[float]:
        """Fetch FMP price. Try quote-short first because some free/basic keys
        can access it even when the richer quote endpoint returns 403.
        """
        self.refresh_api_keys()
        provider = "financial_modeling_prep"
        if not self.fmp_api_key:
            self._record_failure(symbol, provider, "", "FMP_API_KEY is not set; skipping Financial Modeling Prep.")
            return None
        if provider in self._global_provider_failures:
            self._record_failure(symbol, provider + "-skipped", "", f"Skipped after earlier global failure: {self._global_provider_failures[provider]}")
            return None

        endpoints = [
            ("quote-short", FMP_QUOTE_SHORT_URL),
            ("quote", FMP_QUOTE_URL),
        ]
        last_cause = None
        for endpoint_name, template in endpoints:
            url = template.format(symbol=urllib.parse.quote(symbol), api_key=urllib.parse.quote(self.fmp_api_key))
            payload, cause = self._get_json(f"Financial Modeling Prep {endpoint_name}", symbol, url)
            if cause:
                last_cause = cause
                # Do not mark 401/403 as global until both FMP endpoints fail; another
                # endpoint may be included in the current plan.
                if self._is_global_failure(cause) and not any(x in cause.lower() for x in ["rejected", "invalid/missing api key", "plan limit"]):
                    self._global_provider_failures[provider] = cause
                    return None
            try:
                if isinstance(payload, list) and payload:
                    rec = payload[0]
                    for key in ("price", "previousClose", "dayLow", "dayHigh"):
                        val = rec.get(key) if isinstance(rec, dict) else None
                        if _is_good_price(val):
                            return float(val)
                cause2 = self._best_guess_cause("Financial Modeling Prep", payload=payload)
                self._record_failure(symbol, f"{provider}:{endpoint_name}", url, cause2, json.dumps(payload)[:300] if payload is not None else "")
                last_cause = cause2
            except Exception as exc:
                last_cause = self._best_guess_cause("Financial Modeling Prep", exc=exc)
                self._record_failure(symbol, f"{provider}:{endpoint_name}", url, last_cause, repr(exc))
        if last_cause and self._is_global_failure(last_cause):
            self._global_provider_failures[provider] = last_cause
        return None

    def _fetch_alpha_vantage(self, symbol: str) -> Optional[float]:
        self.refresh_api_keys()
        provider = "alpha_vantage"
        if not self.alpha_vantage_api_key:
            self._record_failure(symbol, provider, "", "ALPHA_VANTAGE_API_KEY is not set; skipping Alpha Vantage.")
            return None
        if provider in self._global_provider_failures:
            self._record_failure(symbol, provider + "-skipped", "", f"Skipped after earlier global failure: {self._global_provider_failures[provider]}")
            return None
        # Respect Alpha Vantage free-tier burst guidance and reduce rate-limit noise.
        elapsed = _now() - getattr(self, "_last_alpha_vantage_call", 0.0)
        wait = max(0.0, self.alpha_vantage_min_interval_seconds - elapsed)
        if wait > 0:
            time.sleep(wait)
        self._last_alpha_vantage_call = _now()
        url = ALPHA_VANTAGE_QUOTE_URL.format(symbol=urllib.parse.quote(symbol), api_key=urllib.parse.quote(self.alpha_vantage_api_key))
        payload, cause = self._get_json("Alpha Vantage", symbol, url)
        if cause and self._is_global_failure(cause):
            self._global_provider_failures[provider] = cause
        try:
            if isinstance(payload, dict):
                if payload.get("Note"):
                    self._record_failure(symbol, provider, url, "Alpha Vantage rate limit message returned.", str(payload.get("Note")))
                    return None
                if payload.get("Information"):
                    self._record_failure(symbol, provider, url, "Alpha Vantage informational/limit message returned.", str(payload.get("Information")))
                    return None
                q = payload.get("Global Quote", {})
                for key in ("05. price", "08. previous close"):
                    val = q.get(key) if isinstance(q, dict) else None
                    if _is_good_price(val):
                        return float(val)
            cause2 = self._best_guess_cause("Alpha Vantage", payload=payload)
            self._record_failure(symbol, provider, url, cause2, json.dumps(payload)[:300] if payload is not None else "")
        except Exception as exc:
            self._record_failure(symbol, provider, url, self._best_guess_cause("Alpha Vantage", exc=exc), repr(exc))
        return None

    def _fetch_yahoo(self, symbol: str) -> Optional[float]:
        provider = "yahoo"
        if provider in self._global_provider_failures:
            self._record_failure(symbol, provider + "-skipped", "", f"Skipped after earlier global failure: {self._global_provider_failures[provider]}")
            return None
        request_symbol = _clean_symbol(symbol)
        endpoints = [
            ("chart-query1", YAHOO_CHART_URL.format(symbol=urllib.parse.quote(request_symbol))),
            ("chart-query2", YAHOO_CHART_QUERY2_URL.format(symbol=urllib.parse.quote(request_symbol))),
            ("quote", YAHOO_QUOTE_URL.format(symbol=urllib.parse.quote(request_symbol))),
        ]
        last_cause = None
        for endpoint_name, url in endpoints:
            payload, cause = self._get_json(f"Yahoo Finance {endpoint_name}", symbol, url)
            if cause:
                last_cause = cause
                if self._is_global_failure(cause):
                    # Continue to the alternate Yahoo host/endpoint before
                    # marking Yahoo unavailable for the whole refresh.
                    pass
            try:
                if isinstance(payload, dict):
                    if endpoint_name == "quote":
                        quote_result = (((payload.get("quoteResponse") or {}).get("result")) or [])
                        if isinstance(quote_result, list) and quote_result:
                            rec = quote_result[0] if isinstance(quote_result[0], dict) else {}
                            for key in ("regularMarketPrice", "postMarketPrice", "preMarketPrice", "regularMarketPreviousClose"):
                                px = _to_price(rec.get(key))
                                if px is not None:
                                    return px
                    chart = payload.get("chart", {})
                    if isinstance(chart, dict) and chart.get("error"):
                        self._record_failure(symbol, f"{provider}:{endpoint_name}", url, "Yahoo Finance returned provider error.", json.dumps(chart.get("error"))[:300])
                        continue
                    results = chart.get("result", []) if isinstance(chart, dict) else []
                    if isinstance(results, list) and results:
                        result = results[0] if isinstance(results[0], dict) else {}
                        meta = result.get("meta", {}) if isinstance(result, dict) else {}
                        if isinstance(meta, dict):
                            for key in ("regularMarketPrice", "postMarketPrice", "preMarketPrice", "previousClose", "chartPreviousClose"):
                                px = _to_price(meta.get(key))
                                if px is not None:
                                    return px
                        indicators = result.get("indicators", {}) if isinstance(result, dict) else {}
                        quote_rows = indicators.get("quote", []) if isinstance(indicators, dict) else []
                        if isinstance(quote_rows, list) and quote_rows:
                            closes = quote_rows[0].get("close", []) if isinstance(quote_rows[0], dict) else []
                            for raw in reversed(closes or []):
                                px = _to_price(raw)
                                if px is not None:
                                    return px
                if payload is not None:
                    cause2 = self._best_guess_cause("Yahoo Finance", payload=payload)
                    self._record_failure(symbol, f"{provider}:{endpoint_name}", url, cause2, json.dumps(payload)[:300])
                    last_cause = cause2
            except Exception as exc:
                last_cause = self._best_guess_cause("Yahoo Finance", exc=exc)
                self._record_failure(symbol, f"{provider}:{endpoint_name}", url, last_cause, repr(exc))
        if last_cause and self._is_global_failure(last_cause):
            self._global_provider_failures[provider] = last_cause
        return None

    def _fetch_nasdaq(self, symbol: str) -> Optional[float]:
        provider = "nasdaq"
        if provider in self._global_provider_failures:
            self._record_failure(symbol, provider + "-skipped", "", f"Skipped after earlier global failure: {self._global_provider_failures[provider]}")
            return None
        request_symbol = _clean_symbol(symbol)
        # ETFs and stocks both resolve with one of these asset classes.  Try ETF
        # first because this workbook's universe is ETF-heavy.
        last_cause = None
        for asset_class in ("etf", "stocks"):
            url = NASDAQ_INFO_URL.format(symbol=urllib.parse.quote(request_symbol), asset_class=asset_class)
            payload, cause = self._get_json(f"Nasdaq {asset_class}", symbol, url)
            if cause:
                last_cause = cause
            try:
                if isinstance(payload, dict):
                    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
                    primary = data.get("primaryData") if isinstance(data, dict) and isinstance(data.get("primaryData"), dict) else {}
                    for key in ("lastSalePrice", "netChange", "previousClose"):
                        px = _parse_money_text(primary.get(key))
                        if px is not None:
                            return px
                    # Some Nasdaq responses use a generic key/value table.
                    for value in data.values() if isinstance(data, dict) else []:
                        if isinstance(value, dict):
                            for key in ("lastSalePrice", "price", "value"):
                                px = _parse_money_text(value.get(key))
                                if px is not None:
                                    return px
                if payload is not None:
                    cause2 = self._best_guess_cause("Nasdaq", payload=payload)
                    self._record_failure(symbol, f"{provider}:{asset_class}", url, cause2, json.dumps(payload)[:300])
                    last_cause = cause2
            except Exception as exc:
                last_cause = self._best_guess_cause("Nasdaq", exc=exc)
                self._record_failure(symbol, f"{provider}:{asset_class}", url, last_cause, repr(exc))
        if last_cause and self._is_global_failure(last_cause):
            self._global_provider_failures[provider] = last_cause
        return None

    @staticmethod
    def _stooq_symbol(symbol: str) -> str:
        # Stooq-specific symbol mapping only. Other providers receive the original symbol.
        s = _clean_symbol(symbol).lower()
        if not s:
            return s
        if s.endswith(".us"):
            return s
        # Stooq generally expects US ETFs/stocks as lower-case ticker.us.
        # Class tickers like BRK.B become brk.b.us for Stooq only.
        if all(ch.isalnum() or ch in ".-" for ch in s):
            return f"{s}.us"
        return s

    @staticmethod
    def _parse_stooq_csv(text: str) -> Optional[float]:
        try:
            rows = list(csv.DictReader(StringIO(text)))
            if not rows:
                return None
            row = rows[0]
            row_symbol = str(row.get("Symbol", "")).strip().upper()
            if row_symbol in {"", "N/D", "NA", "N/A"}:
                return None
            close = row.get("Close") or row.get("close")
            return _to_price(close)
        except Exception:
            return None

    def _fetch_stooq(self, symbol: str) -> Optional[float]:
        provider = "stooq"
        if provider in self._global_provider_failures:
            self._record_failure(symbol, provider + "-skipped", "", f"Skipped after earlier global failure: {self._global_provider_failures[provider]}")
            return None
        stooq_symbol = self._stooq_symbol(symbol)
        urls = [
            STOOQ_QUOTE_URL.format(symbol=urllib.parse.quote(stooq_symbol)),
            STOOQ_QUOTE_HTTP_URL.format(symbol=urllib.parse.quote(stooq_symbol)),
        ]
        last_cause = None
        for url in urls:
            try:
                req = urllib.request.Request(url, headers=_quote_headers("text/csv,*/*"))
                with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                    body = resp.read().decode("utf-8", errors="replace")
                px = self._parse_stooq_csv(body)
                if _is_good_price(px):
                    return float(px)
                cause = "Stooq response did not contain a usable Close price; ticker may be unsupported or delayed data unavailable."
                self._record_failure(symbol, provider, url, cause, body[:300])
                last_cause = cause
            except urllib.error.HTTPError as exc:
                cause = self._best_guess_cause("Stooq", exc=exc, status_code=exc.code)
                self._record_failure(symbol, provider, url, cause, str(exc), exc.code)
                last_cause = cause
            except Exception as exc:
                cause = self._best_guess_cause("Stooq", exc=exc)
                self._record_failure(symbol, provider, url, cause, repr(exc))
                last_cause = cause
        if last_cause and self._is_global_failure(last_cause):
            self._global_provider_failures[provider] = last_cause
        return None


    def _probe_http_json(self, provider: str, symbol: str, url: str) -> Tuple[Optional[object], Optional[str], List[Dict[str, object]]]:
        """Verbose JSON probe used by the UI single-symbol pricing tester.

        This intentionally records the exact outbound command, transport used,
        status code, elapsed time, and a redacted response preview so a user can
        diagnose local DNS/proxy/TLS/provider issues without reading server logs.
        """
        attempts: List[Dict[str, object]] = []
        command = {
            "method": "GET",
            "url": _redact_url(url),
            "headers": _quote_headers("application/json,*/*"),
            "timeout_seconds": self.timeout_seconds,
        }
        last_cause = ""
        if requests is not None:
            started = _now()
            try:
                resp = requests.get(url, timeout=self.timeout_seconds, headers=_quote_headers("application/json,*/*"))
                elapsed_ms = int((_now() - started) * 1000)
                preview = (resp.text or "")[:900]
                attempt = {
                    "transport": "requests",
                    "command": command,
                    "status_code": resp.status_code,
                    "elapsed_ms": elapsed_ms,
                    "content_type": resp.headers.get("content-type", ""),
                    "response_preview": preview,
                }
                if resp.status_code != 200:
                    cause = self._best_guess_cause(provider, status_code=resp.status_code)
                    attempt["ok"] = False
                    attempt["cause"] = cause
                    attempts.append(attempt)
                    return None, cause, attempts
                try:
                    payload = resp.json()
                    attempt["ok"] = True
                    attempt["json_type"] = type(payload).__name__
                    attempts.append(attempt)
                    return payload, None, attempts
                except Exception as exc:
                    cause = f"{provider} returned HTTP 200 but response was not valid JSON: {exc}"
                    attempt["ok"] = False
                    attempt["cause"] = cause
                    attempts.append(attempt)
                    return None, cause, attempts
            except Exception as exc:
                elapsed_ms = int((_now() - started) * 1000)
                last_cause = self._best_guess_cause(provider, exc=exc)
                attempts.append({
                    "transport": "requests",
                    "command": command,
                    "ok": False,
                    "elapsed_ms": elapsed_ms,
                    "cause": last_cause,
                    "exception": repr(exc)[:500],
                })

        started = _now()
        try:
            req = urllib.request.Request(url, headers=_quote_headers("application/json,*/*"))
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as raw:
                body = raw.read().decode("utf-8", errors="replace")
                status_code = getattr(raw, "status", None) or getattr(raw, "code", None)
                headers = getattr(raw, "headers", {})
            elapsed_ms = int((_now() - started) * 1000)
            attempt = {
                "transport": "urllib",
                "command": command,
                "ok": True,
                "status_code": status_code,
                "elapsed_ms": elapsed_ms,
                "content_type": headers.get("content-type", "") if hasattr(headers, "get") else "",
                "response_preview": body[:900],
            }
            payload = json.loads(body)
            attempt["json_type"] = type(payload).__name__
            attempts.append(attempt)
            return payload, None, attempts
        except urllib.error.HTTPError as exc:
            elapsed_ms = int((_now() - started) * 1000)
            try:
                body = exc.read().decode("utf-8", errors="replace")
            except Exception:
                body = ""
            cause = self._best_guess_cause(provider, exc=exc, status_code=exc.code)
            attempts.append({
                "transport": "urllib",
                "command": command,
                "ok": False,
                "status_code": exc.code,
                "elapsed_ms": elapsed_ms,
                "cause": cause,
                "response_preview": body[:900],
            })
            return None, cause, attempts
        except Exception as exc:
            elapsed_ms = int((_now() - started) * 1000)
            cause = self._best_guess_cause(provider, exc=exc)
            attempts.append({
                "transport": "urllib",
                "command": command,
                "ok": False,
                "elapsed_ms": elapsed_ms,
                "cause": cause,
                "exception": repr(exc)[:500],
            })
            return None, cause or last_cause, attempts

    def _probe_http_text(self, provider: str, symbol: str, url: str, accept: str = "text/csv,*/*") -> Tuple[str, Optional[str], List[Dict[str, object]]]:
        attempts: List[Dict[str, object]] = []
        command = {
            "method": "GET",
            "url": _redact_url(url),
            "headers": _quote_headers(accept),
            "timeout_seconds": self.timeout_seconds,
        }
        started = _now()
        try:
            req = urllib.request.Request(url, headers=_quote_headers(accept))
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as raw:
                body = raw.read().decode("utf-8", errors="replace")
                status_code = getattr(raw, "status", None) or getattr(raw, "code", None)
                headers = getattr(raw, "headers", {})
            attempts.append({
                "transport": "urllib",
                "command": command,
                "ok": True,
                "status_code": status_code,
                "elapsed_ms": int((_now() - started) * 1000),
                "content_type": headers.get("content-type", "") if hasattr(headers, "get") else "",
                "response_preview": body[:900],
            })
            return body, None, attempts
        except urllib.error.HTTPError as exc:
            try:
                body = exc.read().decode("utf-8", errors="replace")
            except Exception:
                body = ""
            cause = self._best_guess_cause(provider, exc=exc, status_code=exc.code)
            attempts.append({
                "transport": "urllib",
                "command": command,
                "ok": False,
                "status_code": exc.code,
                "elapsed_ms": int((_now() - started) * 1000),
                "cause": cause,
                "response_preview": body[:900],
            })
            return "", cause, attempts
        except Exception as exc:
            cause = self._best_guess_cause(provider, exc=exc)
            attempts.append({
                "transport": "urllib",
                "command": command,
                "ok": False,
                "elapsed_ms": int((_now() - started) * 1000),
                "cause": cause,
                "exception": repr(exc)[:500],
            })
            return "", cause, attempts

    def _parse_fmp_payload(self, payload: object) -> Tuple[Optional[float], str]:
        if isinstance(payload, list) and payload:
            rec = payload[0]
            if isinstance(rec, dict):
                for key in ("price", "previousClose", "dayLow", "dayHigh"):
                    px = _to_price(rec.get(key))
                    if px is not None:
                        return px, f"Parsed {key} from first FMP record."
        return None, "FMP payload did not contain price, previousClose, dayLow, or dayHigh."

    def _parse_alpha_payload(self, payload: object) -> Tuple[Optional[float], str]:
        if isinstance(payload, dict):
            if payload.get("Note"):
                return None, "Alpha Vantage returned rate-limit Note."
            if payload.get("Information"):
                return None, "Alpha Vantage returned informational/limit message."
            q = payload.get("Global Quote", {})
            if isinstance(q, dict):
                for key in ("05. price", "08. previous close"):
                    px = _to_price(q.get(key))
                    if px is not None:
                        return px, f"Parsed {key} from Global Quote."
        return None, "Alpha Vantage payload did not contain a usable Global Quote price."

    def _parse_yahoo_payload(self, endpoint_name: str, payload: object) -> Tuple[Optional[float], str]:
        if not isinstance(payload, dict):
            return None, "Yahoo response was not a JSON object."
        if endpoint_name == "quote":
            quote_result = (((payload.get("quoteResponse") or {}).get("result")) or [])
            if isinstance(quote_result, list) and quote_result:
                rec = quote_result[0] if isinstance(quote_result[0], dict) else {}
                for key in ("regularMarketPrice", "postMarketPrice", "preMarketPrice", "regularMarketPreviousClose"):
                    px = _to_price(rec.get(key))
                    if px is not None:
                        return px, f"Parsed {key} from quoteResponse."
            return None, "Yahoo quoteResponse did not contain a usable price."
        chart = payload.get("chart", {})
        if isinstance(chart, dict) and chart.get("error"):
            return None, "Yahoo chart returned provider error: " + json.dumps(chart.get("error"))[:240]
        results = chart.get("result", []) if isinstance(chart, dict) else []
        if isinstance(results, list) and results:
            result = results[0] if isinstance(results[0], dict) else {}
            meta = result.get("meta", {}) if isinstance(result, dict) else {}
            if isinstance(meta, dict):
                for key in ("regularMarketPrice", "postMarketPrice", "preMarketPrice", "previousClose", "chartPreviousClose"):
                    px = _to_price(meta.get(key))
                    if px is not None:
                        return px, f"Parsed {key} from chart meta."
            indicators = result.get("indicators", {}) if isinstance(result, dict) else {}
            quote_rows = indicators.get("quote", []) if isinstance(indicators, dict) else []
            if isinstance(quote_rows, list) and quote_rows:
                closes = quote_rows[0].get("close", []) if isinstance(quote_rows[0], dict) else []
                for raw in reversed(closes or []):
                    px = _to_price(raw)
                    if px is not None:
                        return px, "Parsed last usable close from chart indicators.quote.close."
        return None, "Yahoo chart response did not contain a usable market price or close."

    def _parse_nasdaq_payload(self, payload: object) -> Tuple[Optional[float], str]:
        if isinstance(payload, dict):
            data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
            primary = data.get("primaryData") if isinstance(data, dict) and isinstance(data.get("primaryData"), dict) else {}
            for key in ("lastSalePrice", "netChange", "previousClose"):
                px = _parse_money_text(primary.get(key))
                if px is not None:
                    return px, f"Parsed {key} from Nasdaq primaryData."
            for value in data.values() if isinstance(data, dict) else []:
                if isinstance(value, dict):
                    for key in ("lastSalePrice", "price", "value"):
                        px = _parse_money_text(value.get(key))
                        if px is not None:
                            return px, f"Parsed {key} from Nasdaq data table."
        return None, "Nasdaq payload did not contain a usable last sale or previous close."

    def verbose_symbol_test(self, symbol: str, on_step=None) -> Dict[str, object]:
        """Run a single-symbol live-pricing diagnostic for the UI.

        The tester deliberately exercises every configured live channel instead
        of stopping at the first success.  The final selected price is still the
        first successful provider in normal provider order, so it mirrors the
        production router while exposing the complete command/response trace.
        """
        from datetime import datetime, timezone
        symbol = _clean_symbol(symbol)
        self.refresh_api_keys()
        self.reset_runtime_state(clear_failures=True, clear_provider_failures=True)
        result: Dict[str, object] = {
            "success": False,
            "symbol": symbol,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "pricing_mode_for_test": "LIVE_DIAGNOSTIC",
            "provider_order": list(self.live_provider_order),
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
            "requests_available": requests is not None,
            "effective_api_key_sources": self.api_key_sources(),
            "proxy_environment_present": any(os.environ.get(k) for k in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "REQUESTS_CA_BUNDLE", "SSL_CERT_FILE")),
            "proxy_environment_keys": [k for k in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "NO_PROXY", "REQUESTS_CA_BUNDLE", "SSL_CERT_FILE") if os.environ.get(k)],
            "cache_record": self.cache.get(symbol, {}),
            "steps": [],
            "selected_price": None,
            "selected_provider": "",
            "summary": "",
        }
        if not symbol:
            result["summary"] = "Enter a ticker symbol to test."
            return result
        if symbol == "CASH":
            result.update({"success": True, "selected_price": 1.0, "selected_provider": "cash", "summary": "CASH is hardcoded to 1.00 and does not call live quote services."})
            return result

        steps: List[Dict[str, object]] = []
        success_prices: List[Tuple[str, float]] = []

        def add_step(step: Dict[str, object]) -> None:
            step["step_number"] = len(steps) + 1
            steps.append(step)
            try:
                if on_step:
                    on_step(dict(step))
            except Exception:
                pass
            px = step.get("parsed_price")
            if _is_good_price(px):
                success_prices.append((str(step.get("provider") or step.get("endpoint") or "unknown"), float(px)))

        if not self.fmp_api_key:
            add_step({"provider": "financial_modeling_prep", "endpoint": "quote-short/quote", "enabled": False, "outcome": "skipped", "cause": "No FMP API key configured."})
        else:
            for endpoint_name, template in (("quote-short", FMP_QUOTE_SHORT_URL), ("quote", FMP_QUOTE_URL)):
                url = template.format(symbol=urllib.parse.quote(symbol), api_key=urllib.parse.quote(self.fmp_api_key))
                payload, cause, attempts = self._probe_http_json(f"Financial Modeling Prep {endpoint_name}", symbol, url)
                px, parse_note = self._parse_fmp_payload(payload)
                add_step({
                    "provider": "financial_modeling_prep",
                    "endpoint": endpoint_name,
                    "enabled": True,
                    "url": _redact_url(url),
                    "attempts": attempts,
                    "parsed_price": px,
                    "parse_note": parse_note,
                    "outcome": "success" if px is not None else "failed",
                    "cause": cause or ("" if px is not None else parse_note),
                })

        for endpoint_name, url in (
            ("chart-query1", YAHOO_CHART_URL.format(symbol=urllib.parse.quote(symbol))),
            ("chart-query2", YAHOO_CHART_QUERY2_URL.format(symbol=urllib.parse.quote(symbol))),
            ("quote", YAHOO_QUOTE_URL.format(symbol=urllib.parse.quote(symbol))),
        ):
            payload, cause, attempts = self._probe_http_json(f"Yahoo Finance {endpoint_name}", symbol, url)
            px, parse_note = self._parse_yahoo_payload(endpoint_name, payload)
            add_step({
                "provider": "yahoo",
                "endpoint": endpoint_name,
                "enabled": True,
                "url": _redact_url(url),
                "attempts": attempts,
                "parsed_price": px,
                "parse_note": parse_note,
                "outcome": "success" if px is not None else "failed",
                "cause": cause or ("" if px is not None else parse_note),
            })

        for asset_class in ("etf", "stocks"):
            url = NASDAQ_INFO_URL.format(symbol=urllib.parse.quote(symbol), asset_class=asset_class)
            payload, cause, attempts = self._probe_http_json(f"Nasdaq {asset_class}", symbol, url)
            px, parse_note = self._parse_nasdaq_payload(payload)
            add_step({
                "provider": "nasdaq",
                "endpoint": asset_class,
                "enabled": True,
                "url": _redact_url(url),
                "attempts": attempts,
                "parsed_price": px,
                "parse_note": parse_note,
                "outcome": "success" if px is not None else "failed",
                "cause": cause or ("" if px is not None else parse_note),
            })

        if not self.alpha_vantage_api_key:
            add_step({"provider": "alpha_vantage", "endpoint": "GLOBAL_QUOTE", "enabled": False, "outcome": "skipped", "cause": "No Alpha Vantage API key configured."})
        else:
            url = ALPHA_VANTAGE_QUOTE_URL.format(symbol=urllib.parse.quote(symbol), api_key=urllib.parse.quote(self.alpha_vantage_api_key))
            payload, cause, attempts = self._probe_http_json("Alpha Vantage", symbol, url)
            px, parse_note = self._parse_alpha_payload(payload)
            add_step({
                "provider": "alpha_vantage",
                "endpoint": "GLOBAL_QUOTE",
                "enabled": True,
                "url": _redact_url(url),
                "attempts": attempts,
                "parsed_price": px,
                "parse_note": parse_note,
                "outcome": "success" if px is not None else "failed",
                "cause": cause or ("" if px is not None else parse_note),
            })

        for url in (
            STOOQ_QUOTE_URL.format(symbol=urllib.parse.quote(self._stooq_symbol(symbol))),
            STOOQ_QUOTE_HTTP_URL.format(symbol=urllib.parse.quote(self._stooq_symbol(symbol))),
        ):
            body, cause, attempts = self._probe_http_text("Stooq", symbol, url, "text/csv,*/*")
            px = self._parse_stooq_csv(body)
            parse_note = "Parsed Close from Stooq CSV." if px is not None else "Stooq CSV did not contain a usable Close price."
            add_step({
                "provider": "stooq",
                "endpoint": "csv",
                "enabled": True,
                "url": _redact_url(url),
                "attempts": attempts,
                "parsed_price": px,
                "parse_note": parse_note,
                "outcome": "success" if px is not None else "failed",
                "cause": cause or ("" if px is not None else parse_note),
            })

        result["steps"] = steps
        if success_prices:
            selected_provider, selected_price = success_prices[0]
            result["success"] = True
            result["selected_provider"] = selected_provider
            result["selected_price"] = selected_price
            result["summary"] = f"Live pricing worked. First usable quote was {selected_provider} at {selected_price:.4f}."
        else:
            causes = [str(s.get("cause") or "") for s in steps if s.get("cause")]
            result["summary"] = causes[0] if causes else "No live provider returned a usable price."
        return result

    def _try_provider(self, provider_name: str, symbol: str) -> Optional[float]:
        self.provider_attempts.setdefault(symbol, []).append(provider_name)
        if provider_name == "financial_modeling_prep":
            return self._fetch_fmp(symbol)
        if provider_name == "yahoo":
            return self._fetch_yahoo(symbol)
        if provider_name == "alpha_vantage":
            return self._fetch_alpha_vantage(symbol)
        if provider_name == "nasdaq":
            return self._fetch_nasdaq(symbol)
        if provider_name == "stooq":
            return self._fetch_stooq(symbol)
        raise ValueError(provider_name)

    @property
    def live_provider_order(self) -> List[str]:
        return ["financial_modeling_prep", "yahoo", "nasdaq", "alpha_vantage", "stooq"]

    @property
    def provider_order(self) -> List[str]:
        if self.cache_first:
            return ["cache_any_age", *self.live_provider_order, "holdings_cost_basis_if_no_cache"]
        return [*self.live_provider_order, "cache_any_age", "holdings_cost_basis_if_no_cache"]

    def quote(self, symbol: str) -> float:
        symbol = _clean_symbol(symbol)
        if not symbol:
            return 0.0

        # Per-run memoization is critical: holdings often contain multiple tax lots
        # of the same ETF. Without this, one workbook build can repeatedly hit FMP,
        # Yahoo, Alpha Vantage, and Stooq for the same ticker.
        if symbol in self.prices:
            return self.prices[symbol]

        if symbol == "CASH":
            self.sources[symbol] = "cash"
            self.prices[symbol] = 1.0
            return 1.0

        frozen = self.frozen_prices.get(symbol)
        if _is_good_price(frozen):
            self.sources[symbol] = "frozen_snapshot"
            self.prices[symbol] = float(frozen)
            return float(frozen)
        if self.pricing_mode == "FROZEN" and self.frozen_prices:
            self._record_failure(symbol, "frozen_snapshot", "", "No frozen snapshot price was available for this symbol; falling back without live provider calls.")

        cached_fresh = self._cached_price(symbol)
        cached_any = self._cached_price(symbol, allow_stale=True)

        def cache_source_label() -> str:
            rec = self.cache.get(symbol, {})
            src = str(rec.get("source", "cache")) if isinstance(rec, dict) else "cache"
            if cached_fresh is not None:
                return f"fresh_cache_24h_from_{src}"
            return f"stale_cache_from_{src}"

        # CACHE and OFFLINE modes are intentionally cache-first even when the
        # quote is stale. Cost basis is only allowed when no cache record exists.
        if self.cache_first and cached_any is not None:
            self.sources[symbol] = cache_source_label()
            self.prices[symbol] = cached_any
            return cached_any

        disable_live_env = str(os.getenv("RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS", "") or "").strip().lower() in {"1", "true", "yes", "on"}
        if self.use_live and not disable_live_env:
            for provider in self.live_provider_order:
                px = self._try_provider(provider, symbol)
                if _is_good_price(px):
                    self.cache[symbol] = self._cache_record(symbol, float(px), provider)
                    self._save_cache()
                    self.sources[symbol] = provider + "_live"
                    self.prices[symbol] = float(px)
                    return float(px)
        elif self.use_live and disable_live_env:
            self._record_failure(symbol, "live_providers_skipped", "", "Live provider calls skipped by RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS for local/offline validation.")

        # LIVE mode reaches here when providers did not supply a usable quote.
        # Use the cache even if stale before considering holdings cost basis.
        if cached_any is not None:
            self.sources[symbol] = cache_source_label()
            self.prices[symbol] = cached_any
            return cached_any

        fallback = self.fallback_prices.get(symbol)
        if _is_good_price(fallback):
            self.sources[symbol] = "holdings_cost_basis_fallback"
            self.prices[symbol] = float(fallback)
            return float(fallback)

        self.sources[symbol] = "missing"
        self.prices[symbol] = 0.0
        self._record_failure(symbol, "fallback", "", "No live provider price, no cache, and no holdings cost-basis fallback were available.")
        return 0.0

    def quotes(self, symbols: Iterable[str]) -> Dict[str, float]:
        return {s: self.quote(s) for s in symbols}

    def _cache_iso_for_symbol(self, symbol: str) -> str:
        """Return the cached quote timestamp for a symbol, if available."""
        rec = self.cache.get(_clean_symbol(symbol), {})
        if not isinstance(rec, dict):
            return ""
        iso = str(rec.get("timestamp_iso") or "").strip()
        if iso:
            return iso
        epoch = self._cache_timestamp_epoch(rec)
        if epoch > 0:
            try:
                from datetime import datetime, timezone
                return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()
            except Exception:
                return ""
        return ""

    def _cache_expiry_iso_for_symbol(self, symbol: str) -> str:
        """Return the ISO timestamp at which a symbol's cached quote expires (timestamp + TTL)."""
        rec = self.cache.get(_clean_symbol(symbol), {})
        if not isinstance(rec, dict):
            return ""
        epoch = self._cache_timestamp_epoch(rec)
        if epoch <= 0:
            return ""
        try:
            from datetime import datetime, timezone
            return datetime.fromtimestamp(epoch + self.ttl_seconds, tz=timezone.utc).isoformat()
        except Exception:
            return ""

    def pricing_source_summary(self) -> Dict[str, object]:
        """Workbook-level summary of the actual price source used.

        The workbook can be built in LIVE, CACHE, or OFFLINE mode, but the
        actual per-security source may be mixed because individual symbols can
        fall back from live providers to cache or holdings cost basis. This
        summary is intentionally plain-English so it can be printed in the
        workbook and diagnostics.
        """
        sources = {str(sym): str(src) for sym, src in self.sources.items()}
        frozen_symbols = [sym for sym, src in sources.items() if src == "frozen_snapshot"]
        live_sources = {src for src in sources.values() if src.endswith("_live") or "_live" in src}
        cache_symbols = [sym for sym, src in sources.items() if "cache" in src]
        # CASH is hardcoded to $1.00 by design (see quote()) and never calls a
        # live provider — that is expected, permanent behavior, not a pricing
        # degradation, so it is excluded from offline/fallback reporting.
        offline_sources = {
            src for sym, src in sources.items()
            if sym != "CASH" and (src in {"holdings_cost_basis_fallback", "cash", "missing"} or "fallback" in src)
        }
        cache_as_of_by_symbol = {sym: self._cache_iso_for_symbol(sym) for sym in cache_symbols}
        cache_as_of_by_symbol_local = {
            sym: _format_local_cache_timestamp(ts)
            for sym, ts in cache_as_of_by_symbol.items()
            if ts
        }
        cache_as_of_values = sorted({v for v in cache_as_of_by_symbol.values() if v})
        if cache_as_of_values:
            if len(cache_as_of_values) == 1:
                cache_as_of = cache_as_of_values[0]
            else:
                cache_as_of = f"{cache_as_of_values[0]} to {cache_as_of_values[-1]}"
        else:
            cache_as_of = ""
        cache_as_of_local = _format_local_cache_timestamp(cache_as_of)

        cache_expiry_by_symbol = {sym: self._cache_expiry_iso_for_symbol(sym) for sym in cache_symbols}
        cache_expiry_values = sorted({v for v in cache_expiry_by_symbol.values() if v})
        if cache_expiry_values:
            cache_valid_until = cache_expiry_values[-1] if len(cache_expiry_values) == 1 else f"{cache_expiry_values[0]} to {cache_expiry_values[-1]}"
        else:
            cache_valid_until = ""
        cache_valid_until_local = _format_local_cache_timestamp(cache_valid_until)

        if frozen_symbols:
            category = "FROZEN"
            frozen_at = str(self.frozen_metadata.get("frozen_at") or "").strip()
            note = f"Frozen pricing snapshot was used for {len(frozen_symbols)} symbol{'' if len(frozen_symbols) == 1 else 's'}."
            if frozen_at:
                note += f" Snapshot frozen at {_format_local_cache_timestamp(frozen_at)}."
            if cache_symbols:
                note += " Some symbols fell back to cached quotes because they were not present in the frozen snapshot."
            if offline_sources:
                note += " Some symbols used offline fallback pricing; see Holdings Detail by Account for ticker-level sources."
        elif live_sources:
            category = "LIVE"
            providers = ", ".join(sorted(src.replace("_live", "") for src in live_sources))
            note = f"Live provider quotes were used during this workbook build ({providers})."
            if cache_symbols:
                note += f" Cached quotes were also used as of {cache_as_of_local or 'the cache timestamp on file'} because live pricing was not available for those symbols."
            if offline_sources:
                note += " Some symbols used offline fallback pricing; see Holdings Detail by Account for ticker-level sources."
        elif cache_symbols:
            category = "CACHE"
            ttl_hours = round(self.ttl_seconds / 3600, 2)
            any_stale = any(str(sources.get(sym, "")).startswith("stale_cache_from_") for sym in cache_symbols)
            live_was_attempted = self.use_live and not self.cache_first
            if live_was_attempted:
                # LIVE mode tried live providers first for these symbols and they failed.
                reason = "Live pricing was not available for these symbols, so the cached quote was used as a fallback."
            else:
                policy_phrase = (
                    "OFFLINE mode never calls live providers"
                    if self.pricing_mode == "OFFLINE"
                    else f"{self.pricing_mode} mode checks the cache before calling live providers"
                )
                if any_stale:
                    expired_at = f" (expired {cache_valid_until_local})" if cache_valid_until_local else ""
                    reason = f"{policy_phrase}; this cache passed its {ttl_hours}-hour TTL{expired_at} but was used anyway."
                elif cache_valid_until_local:
                    reason = f"{policy_phrase}; the cache is still valid until {cache_valid_until_local}."
                else:
                    reason = f"{policy_phrase}."
            note = f"Cached quotes were used as of {cache_as_of_local or 'the cache timestamp on file'}; cache TTL is {ttl_hours} hours. {reason}"
            if offline_sources:
                note += " Some symbols used offline fallback pricing; see Holdings Detail by Account for ticker-level sources."
        else:
            category = "OFFLINE"
            if self.pricing_mode == "OFFLINE":
                note = "OFFLINE pricing mode was selected; no live provider calls were made, so holdings cost-basis fallback/cash pricing was used where available."
            elif sources:
                note = "No live or cached market quotes were used for workbook holdings; offline fallback/cash pricing was used where available."
            else:
                note = f"Pricing mode is {self.pricing_mode}; no holding prices have been requested yet in this process."

        return {
            "category": category,
            "label": category,
            "pricing_mode": self.pricing_mode,
            "cache_as_of_utc": cache_as_of,
            "cache_as_of_local": cache_as_of_local,
            "cache_as_of_by_symbol": cache_as_of_by_symbol,
            "cache_as_of_by_symbol_local": cache_as_of_by_symbol_local,
            "cache_valid_until_utc": cache_valid_until,
            "cache_valid_until_local": cache_valid_until_local,
            "note": note,
            "source_counts": dict(sorted({src: list(sources.values()).count(src) for src in set(sources.values())}.items())),
        }

    def diagnostics(self) -> Dict[str, object]:
        self.refresh_api_keys()
        counts: Dict[str, int] = {}
        for src in self.sources.values():
            counts[src] = counts.get(src, 0) + 1
        failure_symbols = sorted({str(f.get("symbol")) for f in self.failures if f.get("symbol")})
        best_guess = "Market pricing succeeded for all requested symbols."
        if failure_symbols:
            causes = [str(f.get("cause", "")) for f in self.failures if f.get("cause")]
            use_causes = [c for c in causes if "api_key is not set" not in c.lower()] or causes
            best_guess = max(set(use_causes), key=use_causes.count) if use_causes else "At least one pricing provider failed."
        source_summary = self.pricing_source_summary()
        fallback_warning_symbols = sorted([sym for sym, src in self.sources.items() if any(tok in str(src).lower() for tok in ('fallback', 'stale', 'cost_basis', 'unknown'))])
        fallback_warning_share = (len(fallback_warning_symbols) / max(1, len(self.sources))) if self.sources else 0.0
        advisor_ready_pricing_blocked = fallback_warning_share > 0.10
        return {
            "provider_order": self.provider_order,
            "pricing_mode": self.pricing_mode,
            "live_enabled": self.use_live,
            "cache_first_enabled": self.cache_first,
            "cache_ttl_hours": round(self.ttl_seconds / 3600, 2),
            "csv_settings": {
                "file": "multi_user/system_config.csv",
                "section": "Market Pricing",
                "subsection": "Holdings",
                "pricing_mode": "CACHE | LIVE | OFFLINE",
                "cache_hours": "fresh-cache window in hours; default 24",
            },
            "requests_available": requests is not None,
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
            "fmp_api_key_configured": bool(self.fmp_api_key),
            "alpha_vantage_api_key_configured": bool(self.alpha_vantage_api_key),
            "yahoo_configured": True,
            "nasdaq_configured": True,
            "stooq_configured": True,
            "fmp_api_key_fingerprint": _secret_fingerprint(self.fmp_api_key),
            "alpha_vantage_api_key_fingerprint": _secret_fingerprint(self.alpha_vantage_api_key),
            "api_key_source": "UI/system_config.csv, environment variables, or encrypted secret store",
            "effective_api_key_sources": self.api_key_sources(),
            "proxy_environment_present": any(os.environ.get(k) for k in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "REQUESTS_CA_BUNDLE", "SSL_CERT_FILE")),
            "proxy_environment_keys": [k for k in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "NO_PROXY", "REQUESTS_CA_BUNDLE", "SSL_CERT_FILE") if os.environ.get(k)],
            "no_key_providers": ["yahoo", "nasdaq", "stooq"],
            "nasdaq_asset_classes": ["etf", "stocks"],
            "stooq_symbol_rule": "append .us only for Stooq calls; other providers receive original symbols",
            "api_key_csv_settings": {
                "file": "multi_user/system_config.csv",
                "section": "Market Pricing",
                "subsection": "API",
                "fmp_api_key": "Financial Modeling Prep key from UI/system_config.csv, RETIREMENT_SYSTEM_FMP_API_KEY, FMP_API_KEY, FINANCIAL_MODELING_PREP_API_KEY, or encrypted secret store",
                "alpha_vantage_api_key": "Alpha Vantage key from UI/system_config.csv, RETIREMENT_SYSTEM_ALPHA_VANTAGE_API_KEY, ALPHA_VANTAGE_API_KEY, or encrypted secret store",
            },
            "cache_schema_version": CACHE_SCHEMA_VERSION,
            "cache_path": str(self.cache_path),
            "diagnostics_path": str(self.diagnostics_path),
            "cached_symbols": sorted(self.cache.keys()),
            "fallback_symbols": sorted(self.fallback_prices.keys()),
            "frozen_pricing_active": bool(self.frozen_prices),
            "frozen_symbols": sorted(self.frozen_prices.keys()),
            "frozen_metadata": self.frozen_metadata,
            "source_counts": counts,
            "pricing_source_summary": source_summary,
            "pricing_source_category": source_summary.get("category"),
            "pricing_source_note": source_summary.get("note"),
            "cache_as_of_utc": source_summary.get("cache_as_of_utc"),
            "cache_as_of_local": source_summary.get("cache_as_of_local"),
            "cache_as_of_by_symbol": source_summary.get("cache_as_of_by_symbol", {}),
            "cache_as_of_by_symbol_local": source_summary.get("cache_as_of_by_symbol_local", {}),
            "prices": self.prices,
            "sources": self.sources,
            "provider_attempts": self.provider_attempts,
            "failure_symbols": failure_symbols,
            "failure_count": len(self.failures),
            "failures": self.failures[-75:],
            "best_guess_cause": best_guess,
            "fallback_warning_symbols": fallback_warning_symbols,
            "fallback_warning_share": fallback_warning_share,
            "advisor_ready_pricing_blocked": advisor_ready_pricing_blocked,
            "advisor_ready_pricing_message": "Advisor-ready status is blocked when fallback/stale pricing exceeds configured tolerance." if advisor_ready_pricing_blocked else "Pricing fallback share is within configured tolerance.",
        }

    def write_diagnostics(self, path: str | Path | None = None, print_report: bool = True) -> Dict[str, object]:
        diag = self.diagnostics()
        out = Path(path) if path else self.diagnostics_path
        try:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(diag, indent=2, sort_keys=True), encoding="utf-8")
        except Exception:
            pass
        if print_report:
            print("Market pricing summary:")
            print("  Provider order: " + " -> ".join(str(x) for x in diag.get("provider_order", [])))
            print(f"  Pricing mode: {diag.get('pricing_mode')} ({diag.get('cache_ttl_hours')}h cache TTL)")
            print(f"  FMP API key configured: {diag.get('fmp_api_key_configured')}")
            print(f"  Alpha Vantage API key configured: {diag.get('alpha_vantage_api_key_configured')}")
            print(f"  Yahoo configured: {diag.get('yahoo_configured')} (no API key)")
            print(f"  Nasdaq configured: {diag.get('nasdaq_configured')} (no API key)")
            print(f"  Stooq configured: {diag.get('stooq_configured')} (no API key; .us suffix only for Stooq)")
            print(f"  requests installed: {diag.get('requests_available')}")
            print(f"  Price sources: {diag.get('source_counts')}")
            if diag.get("failure_symbols"):
                print(f"WARN: One or more pricing providers failed for: {', '.join(diag.get('failure_symbols', []))}")
                print(f"WARN: Best guess: {diag.get('best_guess_cause')}")
                print(f"WARN: Fallback pricing was used where available. See {out} for ticker-level detail.")
        return diag


_DEFAULT_PROVIDER = MarketDataProvider()
PRICE_CACHE: Dict[str, float] = {}
PRICE_SOURCE_CACHE: Dict[str, str] = {}


def configure_holdings_pricing(mode: str = "CACHE", cache_hours: object = 24) -> None:
    _DEFAULT_PROVIDER.configure_holdings_pricing(mode=mode, cache_hours=cache_hours)

def configure_api_keys(fmp_api_key: object = "", alpha_vantage_api_key: object = "") -> None:
    _DEFAULT_PROVIDER.configure_api_keys(fmp_api_key=fmp_api_key, alpha_vantage_api_key=alpha_vantage_api_key)

def configure_transport(timeout_seconds: object | None = None, max_retries: object | None = None) -> None:
    _DEFAULT_PROVIDER.configure_transport(timeout_seconds=timeout_seconds, max_retries=max_retries)

def set_fallback_prices(prices: Dict[str, float]) -> None:
    _DEFAULT_PROVIDER.set_fallback_prices(prices)


def set_frozen_prices(prices: Dict[str, float], metadata: Dict[str, object] | None = None) -> None:
    _DEFAULT_PROVIDER.set_frozen_prices(prices, metadata=metadata)
    PRICE_CACHE.clear()
    PRICE_SOURCE_CACHE.clear()


def reset_pricing_runtime_state(clear_failures: bool = True, clear_provider_failures: bool = True) -> None:
    _DEFAULT_PROVIDER.reset_runtime_state(clear_failures=clear_failures, clear_provider_failures=clear_provider_failures)
    PRICE_CACHE.clear()
    PRICE_SOURCE_CACHE.clear()


def fetch_price(symbol: str, url_template: str = "") -> float:
    price = _DEFAULT_PROVIDER.quote(symbol)
    sym = _clean_symbol(symbol)
    PRICE_CACHE[sym] = price
    PRICE_SOURCE_CACHE[sym] = _DEFAULT_PROVIDER.sources.get(sym, "unknown")
    return price


def price_source(symbol: str) -> str:
    sym = _clean_symbol(symbol)
    if sym not in PRICE_SOURCE_CACHE:
        _DEFAULT_PROVIDER.quote(sym)
        PRICE_SOURCE_CACHE[sym] = _DEFAULT_PROVIDER.sources.get(sym, "unknown")
    return PRICE_SOURCE_CACHE.get(sym, "unknown")


def verbose_symbol_test(symbol: str) -> Dict[str, object]:
    return _DEFAULT_PROVIDER.verbose_symbol_test(symbol)


def pricing_diagnostics() -> Dict[str, object]:
    return _DEFAULT_PROVIDER.diagnostics()


def pricing_source_summary() -> Dict[str, object]:
    return _DEFAULT_PROVIDER.pricing_source_summary()


def write_pricing_diagnostics(path: str | Path | None = None, print_report: bool = True) -> Dict[str, object]:
    return _DEFAULT_PROVIDER.write_diagnostics(path=path, print_report=print_report)

# ===== END market_data_providers.py =====


# ===== BEGIN ml_forecast_models.py =====

"""
ml_forecast_models.py — lightweight ML-style forecasting models for planning.

No heavy dependencies are required. These models provide deterministic,
reproducible forecasts for returns, inflation, and portfolio paths using:
- random-walk baseline
- exponentially weighted moving average
- linear trend extrapolation
- simple ensemble blending

The output is designed for governance/audit and can be replaced later with
scikit-learn/statsmodels models without changing workbook integration points.
"""

import json
import math
import random
from dataclasses import dataclass, asdict
from pathlib import Path
from statistics import mean
from typing import Dict, Iterable, List, Sequence


def _finite_series(values: Iterable[float]) -> List[float]:
    out: List[float] = []
    for v in values:
        try:
            f = float(v)
            if math.isfinite(f):
                out.append(f)
        except Exception:
            pass
    return out


def ewma_forecast(values: Sequence[float], horizon: int, alpha: float = 0.35) -> List[float]:
    x = _finite_series(values)
    if not x:
        return [0.0] * horizon
    level = x[0]
    for v in x[1:]:
        level = alpha * v + (1 - alpha) * level
    return [level] * horizon


def linear_trend_forecast(values: Sequence[float], horizon: int) -> List[float]:
    x = _finite_series(values)
    n = len(x)
    if n == 0:
        return [0.0] * horizon
    if n == 1:
        return [x[0]] * horizon
    xs = list(range(n))
    mx, my = mean(xs), mean(x)
    denom = sum((i - mx) ** 2 for i in xs) or 1.0
    slope = sum((i - mx) * (y - my) for i, y in zip(xs, x)) / denom
    intercept = my - slope * mx
    return [intercept + slope * (n + i) for i in range(horizon)]


def random_walk_forecast(values: Sequence[float], horizon: int, seed: int = 42) -> List[float]:
    x = _finite_series(values)
    if not x:
        return [0.0] * horizon
    rng = random.Random(seed)
    diffs = [x[i] - x[i - 1] for i in range(1, len(x))]
    vol = (sum((d - (mean(diffs) if diffs else 0.0)) ** 2 for d in diffs) / max(1, len(diffs))) ** 0.5 if diffs else 0.0
    drift = mean(diffs) if diffs else 0.0
    cur = x[-1]
    out: List[float] = []
    for _ in range(horizon):
        cur = cur + drift + rng.gauss(0.0, vol)
        out.append(cur)
    return out


def ensemble_forecast(values: Sequence[float], horizon: int, seed: int = 42) -> Dict[str, object]:
    ew = ewma_forecast(values, horizon)
    lt = linear_trend_forecast(values, horizon)
    rw = random_walk_forecast(values, horizon, seed=seed)
    ens = [(0.45 * a + 0.35 * b + 0.20 * c) for a, b, c in zip(ew, lt, rw)]
    abs_err = []
    hist = _finite_series(values)
    if len(hist) >= 4:
        # simple rolling backtest on last 25% of observations
        cut = max(2, int(len(hist) * 0.75))
        train = hist[:cut]
        test = hist[cut:]
        pred = ensemble_forecast(train, len(test), seed=seed + 1)["ensemble"] if test else []
        abs_err = [abs(float(p) - float(t)) for p, t in zip(pred, test)]
    mae = mean(abs_err) if abs_err else 0.0
    return {
        "models": {"ewma": ew, "linear_trend": lt, "random_walk": rw},
        "ensemble": ens,
        "horizon": horizon,
        "backtest_mae": mae,
        "seed": seed,
    }


@dataclass
class ForecastPackage:
    return_forecast: Dict[str, object]
    inflation_forecast: Dict[str, object]
    metadata: Dict[str, object]

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)


def build_plan_forecasts(rows: Sequence[dict], c: dict, horizon: int = 10, seed: int = 42) -> ForecastPackage:
    # Use realized/model rows where available; fall back to assumptions.
    nw = [float(r.get("total_nw", 0.0)) for r in rows if r.get("total_nw") is not None]
    returns: List[float] = []
    for a, b in zip(nw, nw[1:]):
        if a > 0:
            returns.append((b / a) - 1.0)
    if not returns:
        returns = [float(c.get("ret", 0.06))]
    inflation = [float(c.get("inf", 0.025))] * max(4, min(12, len(rows) or 4))
    return ForecastPackage(
        return_forecast=ensemble_forecast(returns, horizon, seed=seed),
        inflation_forecast=ensemble_forecast(inflation, horizon, seed=seed + 1000),
        metadata={
            "engine": "lightweight_ensemble_v1",
            "horizon_years": horizon,
            "seed": seed,
            "source": "projection_rows_and_plan_assumptions",
        },
    )


def write_forecast_package(path: str | Path, rows: Sequence[dict], c: dict, horizon: int = 10, seed: int = 42) -> ForecastPackage:
    pkg = build_plan_forecasts(rows, c, horizon=horizon, seed=seed)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(pkg.to_json(), encoding="utf-8")
    return pkg

# ===== END ml_forecast_models.py =====
