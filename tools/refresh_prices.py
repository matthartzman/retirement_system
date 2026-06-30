from __future__ import annotations
"""Refresh market prices and write historical snapshots.

Version 7 uses the same production pricing engine/cache as workbook generation.
It seeds holdings cost-basis fallbacks from client_holdings.csv and deliberately
skips zero/missing prices to avoid polluting historical snapshots.
"""

from pathlib import Path
import argparse
import csv
import json
import os
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import market_data
from src.config_backend import load_active_config, setting
from src.portfolio_analytics import snapshot_prices
from src.workspace_context import candidate_input_files, first_existing, workspace_output_dir


def _num(value: object, default: float = 0.0) -> float:
    try:
        return float(str(value or "").replace("$", "").replace(",", "").strip())
    except Exception:
        return default


def load_holdings_symbols_and_fallbacks(path: Path):
    symbols = []
    basis = {}
    qty = {}
    if not path.exists():
        return symbols, {}
    with path.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            sym = (row.get("ticker") or row.get("symbol") or "").strip().upper()
            if not sym:
                continue
            if sym not in symbols:
                symbols.append(sym)
            shares = _num(row.get("shares"), 0.0)
            purchase_price = _num(row.get("purchase_price") or row.get("price") or row.get("cost_basis_per_share"), 0.0)
            if shares > 0 and purchase_price > 0 and sym != "CASH":
                basis[sym] = basis.get(sym, 0.0) + shares * purchase_price
                qty[sym] = qty.get(sym, 0.0) + shares
    fallbacks = {sym: basis[sym] / qty[sym] for sym in basis if qty.get(sym, 0) > 0}
    return symbols, fallbacks


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh market prices using the production pricing router.")
    parser.add_argument("--mode", choices=["LIVE", "CACHE", "OFFLINE"], default=os.getenv("RETIREMENT_SYSTEM_PRICE_REFRESH_MODE", "LIVE").upper(), help="Pricing mode for this refresh. Default LIVE bypasses cache first so Refresh Prices actually refreshes.")
    parser.add_argument("--respect-config", action="store_true", help="Use configured Market Pricing mode instead of forcing LIVE refresh mode.")
    args = parser.parse_args()

    data, meta = load_active_config()
    configured_mode = setting(data, "Market Pricing", "Holdings", "pricing_mode", "CACHE") or "CACHE"
    refresh_mode = configured_mode if args.respect_config else (args.mode if args.mode in {"LIVE", "CACHE", "OFFLINE"} else "LIVE")
    market_data.configure_api_keys(
        fmp_api_key=setting(data, "Market Pricing", "API", "fmp_api_key", ""),
        alpha_vantage_api_key=setting(data, "Market Pricing", "API", "alpha_vantage_api_key", ""),
    )
    market_data.configure_holdings_pricing(
        mode=refresh_mode,
        cache_hours=setting(data, "Market Pricing", "Holdings", "cache_hours", "24"),
    )
    market_data.configure_transport(
        timeout_seconds=os.getenv("RETIREMENT_SYSTEM_PRICE_TIMEOUT_SECONDS", "4"),
        max_retries=os.getenv("RETIREMENT_SYSTEM_PRICE_MAX_RETRIES", "1"),
    )
    market_data.reset_pricing_runtime_state(clear_failures=True, clear_provider_failures=True)

    workspace_id = meta.get("workspace_id", "local")
    holdings = first_existing(candidate_input_files("client_holdings.csv", workspace_id, ROOT)) or (ROOT / "input" / "client_holdings.csv")
    symbols, fallbacks = load_holdings_symbols_and_fallbacks(holdings)
    market_data.set_fallback_prices(fallbacks)

    prices = {}
    warnings = []
    for symbol in symbols:
        price = market_data.fetch_price(symbol)
        if price and price > 0:
            prices[symbol] = price
        else:
            warnings.append(f"{symbol}: no usable price; skipped snapshot")

    out_dir = workspace_output_dir(workspace_id, ROOT)
    out_dir.mkdir(parents=True, exist_ok=True)
    snapshot_error = ""
    count = 0
    try:
        count = snapshot_prices(prices, market_data.PRICE_SOURCE_CACHE, workspace_id=workspace_id)
    except Exception as exc:
        # Surface snapshot/schema failures without hiding whether live pricing
        # itself worked.  Older upgraded SQLite DBs have been seen with stale
        # price_snapshots columns; init_sqlite now migrates that schema, but
        # this keeps the refresh result truthful if persistence fails.
        snapshot_error = repr(exc)

    diag = market_data.write_pricing_diagnostics(out_dir / "pricing_diagnostics.json", print_report=False)
    sources = {str(k): str(v) for k, v in market_data.PRICE_SOURCE_CACHE.items()}
    live_prices = {sym: px for sym, px in prices.items() if "_live" in sources.get(sym, "") or sources.get(sym, "") in {"financial_modeling_prep_live", "yahoo_live", "alpha_vantage_live", "stooq_live"}}
    cache_prices = {sym: px for sym, px in prices.items() if "cache" in sources.get(sym, "").lower()}
    fallback_prices = {sym: px for sym, px in prices.items() if any(tok in sources.get(sym, "").lower() for tok in ("fallback", "cost_basis"))}
    provider_failure_summary = {}
    for failure in diag.get("failures", []) or []:
        provider = str(failure.get("provider") or "unknown")
        cause = str(failure.get("cause") or "")
        provider_failure_summary.setdefault(provider, cause)

    result = {
        "version": "9",
        "workspace_id": workspace_id,
        "config_backend": meta.get("backend"),
        "configured_pricing_mode": configured_mode,
        "refresh_pricing_mode": refresh_mode,
        "provider_selection_order": diag.get("provider_order"),
        "symbols_requested": len(symbols),
        "prices_resolved": len(prices),
        "live_prices_resolved": len(live_prices),
        "cache_prices_resolved": len(cache_prices),
        "fallback_prices_resolved": len(fallback_prices),
        "live_pricing_working": bool(live_prices),
        "snapshots_written": count,
        "snapshot_error": snapshot_error,
        "prices": prices,
        "sources": sources,
        "warnings": warnings,
        "cache_path": diag.get("cache_path"),
        "pricing_best_guess_cause": diag.get("best_guess_cause"),
        "provider_failure_summary": provider_failure_summary,
        "effective_api_key_sources": diag.get("effective_api_key_sources"),
        "proxy_environment_present": diag.get("proxy_environment_present"),
        "proxy_environment_keys": diag.get("proxy_environment_keys"),
    }
    out = out_dir / "price_refresh_result.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    # If the user requested a real-time refresh, no live quotes means the
    # real-time part did not work even if cache/cost-basis fallback produced
    # portfolio values.  Return 2 so the UI can show the diagnostic payload as a
    # pricing warning instead of a generic crash.
    if not prices or snapshot_error:
        return 1
    if refresh_mode == "LIVE" and not live_prices:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
