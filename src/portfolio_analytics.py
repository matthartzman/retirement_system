from __future__ import annotations
"""Portfolio analytics for Version 7.

Supports historical price snapshots and drift analysis using a security master
so ticker-level holdings can be mapped to asset-class targets.
"""

import csv
from datetime import datetime, timezone
import json
import sqlite3
from pathlib import Path
from typing import Dict, List, Tuple, Any

from .config_backend import init_sqlite, DEFAULT_DB

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_HOLDINGS = PROJECT_ROOT / "input" / "client_holdings.csv"
DEFAULT_TARGETS = PROJECT_ROOT / "input" / "target_allocation.csv"
DEFAULT_SECURITY_MASTER = PROJECT_ROOT / "reference_data" / "security_master.csv"
PRICING_FREEZE_SCHEMA = "pricing_snapshot_freeze_v1"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _ensure_pricing_freeze_table(con: sqlite3.Connection) -> None:
    con.execute("""CREATE TABLE IF NOT EXISTS pricing_snapshot_freezes(
        workspace_id TEXT PRIMARY KEY,
        active INTEGER NOT NULL DEFAULT 1,
        frozen_at TEXT NOT NULL,
        source TEXT,
        snapshot_json TEXT NOT NULL
    )""")


def _freeze_payload_from_latest(latest: Dict[str, dict], *, workspace_id: str, source: str) -> dict[str, Any]:
    symbols: dict[str, dict[str, Any]] = {}
    for sym, row in sorted((latest or {}).items()):
        price = _num(row.get("price"), 0.0)
        if price <= 0:
            continue
        symbols[str(sym).upper()] = {
            "symbol": str(sym).upper(),
            "price": price,
            "source": str(row.get("source") or ""),
            "as_of": str(row.get("as_of") or ""),
            "snapshot_id": row.get("snapshot_id"),
        }
    return {
        "schema": PRICING_FREEZE_SCHEMA,
        "workspace_id": workspace_id,
        "frozen_at": _utc_now_iso(),
        "source": source,
        "symbol_count": len(symbols),
        "symbols": symbols,
    }


def freeze_latest_pricing_snapshot(workspace_id: str = "local", db_path: str | Path = DEFAULT_DB, *, source: str = "latest_price_snapshots") -> dict[str, Any]:
    """Freeze the current latest per-symbol price snapshots for reproducible builds.

    The freeze copies latest prices into a single JSON contract so later live price
    refreshes cannot move an advisor report until the user explicitly unfreezes.
    """
    p = init_sqlite(db_path)
    latest = load_latest_snapshots(workspace_id=workspace_id, db_path=p)
    payload = _freeze_payload_from_latest(latest, workspace_id=workspace_id, source=source)
    if not payload.get("symbol_count"):
        return {
            "success": False,
            "active": False,
            "schema": PRICING_FREEZE_SCHEMA,
            "workspace_id": workspace_id,
            "error": "No saved price snapshots are available to freeze. Refresh prices first.",
            "latest_count": 0,
        }
    with sqlite3.connect(p) as con:
        _ensure_pricing_freeze_table(con)
        con.execute(
            """INSERT INTO pricing_snapshot_freezes(workspace_id, active, frozen_at, source, snapshot_json)
               VALUES(?,?,?,?,?)
               ON CONFLICT(workspace_id) DO UPDATE SET active=excluded.active, frozen_at=excluded.frozen_at, source=excluded.source, snapshot_json=excluded.snapshot_json""",
            (workspace_id, 1, payload["frozen_at"], source, json.dumps(payload, sort_keys=True)),
        )
    return {"success": True, "active": True, **payload}


def unfreeze_pricing_snapshot(workspace_id: str = "local", db_path: str | Path = DEFAULT_DB) -> dict[str, Any]:
    p = init_sqlite(db_path)
    now = _utc_now_iso()
    with sqlite3.connect(p) as con:
        _ensure_pricing_freeze_table(con)
        con.execute(
            "UPDATE pricing_snapshot_freezes SET active=0, frozen_at=?, source=COALESCE(source, 'latest_price_snapshots') WHERE workspace_id=?",
            (now, workspace_id),
        )
    return {"success": True, "schema": PRICING_FREEZE_SCHEMA, "workspace_id": workspace_id, "active": False, "unfrozen_at": now}


def pricing_freeze_status(workspace_id: str = "local", db_path: str | Path = DEFAULT_DB, include_prices: bool = True) -> dict[str, Any]:
    p = Path(db_path)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    if not p.exists():
        return {
            "success": True,
            "schema": PRICING_FREEZE_SCHEMA,
            "workspace_id": workspace_id,
            "active": False,
            "latest_count": 0,
            "prices": {} if include_prices else None,
        }
    latest_count = len(load_latest_snapshots(workspace_id=workspace_id, db_path=p))
    try:
        with sqlite3.connect(p) as con:
            table = con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pricing_snapshot_freezes'").fetchone()
            if table:
                row = con.execute(
                    "SELECT active, frozen_at, source, snapshot_json FROM pricing_snapshot_freezes WHERE workspace_id=?",
                    (workspace_id,),
                ).fetchone()
            else:
                row = None
    except sqlite3.Error:
        row = None
    if not row or not int(row[0] or 0):
        return {
            "success": True,
            "schema": PRICING_FREEZE_SCHEMA,
            "workspace_id": workspace_id,
            "active": False,
            "latest_count": latest_count,
            "prices": {} if include_prices else None,
        }
    try:
        payload = json.loads(row[3] or "{}")
    except Exception:
        payload = {}
    symbols = payload.get("symbols") if isinstance(payload, dict) else {}
    prices = {str(sym).upper(): _num((rec or {}).get("price"), 0.0) for sym, rec in (symbols or {}).items() if _num((rec or {}).get("price"), 0.0) > 0}
    result = {
        "success": True,
        "schema": PRICING_FREEZE_SCHEMA,
        "workspace_id": workspace_id,
        "active": True,
        "frozen_at": str(row[1] or payload.get("frozen_at") or ""),
        "source": str(row[2] or payload.get("source") or ""),
        "symbol_count": len(prices),
        "latest_count": latest_count,
    }
    if include_prices:
        result["prices"] = prices
        result["symbols"] = symbols or {}
    return result


def frozen_price_lookup(workspace_id: str = "local", db_path: str | Path = DEFAULT_DB) -> Dict[str, float]:
    status = pricing_freeze_status(workspace_id=workspace_id, db_path=db_path, include_prices=True)
    return dict(status.get("prices") or {}) if status.get("active") else {}


def _num(value: object, default: float = 0.0) -> float:
    try:
        s = str(value or "").replace("$", "").replace(",", "").replace("%", "").strip()
        return float(s)
    except Exception:
        return default


def _pct(value: object) -> float:
    raw = _num(value, 0.0)
    return raw / 100.0 if raw > 1 else raw


def snapshot_prices(prices: Dict[str, float], sources: Dict[str, str] | None = None, workspace_id: str = "local", db_path: str | Path = DEFAULT_DB) -> int:
    """Write non-zero price snapshots only.

    Version 7 deliberately skips missing/zero values so nightly refresh cannot
    pollute historical snapshots with unusable prices.
    """
    p = init_sqlite(db_path)
    sources = sources or {}
    n = 0
    with sqlite3.connect(p) as con:
        for sym, px in prices.items():
            try:
                f = float(px)
            except Exception:
                continue
            if f <= 0:
                continue
            con.execute(
                "INSERT INTO price_snapshots(workspace_id, symbol, price, source, status) VALUES(?,?,?,?,?)",
                (workspace_id, sym.upper(), f, sources.get(sym.upper(), sources.get(sym, "")), "OK"),
            )
            n += 1
    return n


def load_latest_snapshots(workspace_id: str = "local", db_path: str | Path = DEFAULT_DB) -> Dict[str, dict]:
    p = Path(db_path)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    out: Dict[str, dict] = {}
    if not p.exists():
        return out
    with sqlite3.connect(p) as con:
        con.row_factory = sqlite3.Row
        for row in con.execute(
            """SELECT ps.* FROM price_snapshots ps
               JOIN (
                   SELECT symbol, MAX(as_of) AS max_as_of
                   FROM price_snapshots
                   WHERE workspace_id=? AND price > 0
                   GROUP BY symbol
               ) x ON ps.symbol=x.symbol AND ps.as_of=x.max_as_of
               WHERE ps.workspace_id=?""",
            (workspace_id, workspace_id),
        ):
            out[row["symbol"]] = dict(row)
    return out


def read_security_master(path: str | Path = DEFAULT_SECURITY_MASTER) -> Dict[str, dict]:
    p = Path(path)
    result: Dict[str, dict] = {}
    if not p.exists():
        return result
    with p.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            symbol = (row.get("symbol") or row.get("ticker") or "").strip().upper()
            if not symbol:
                continue
            result[symbol] = {
                "asset_class": (row.get("asset_class") or "UNKNOWN").strip().upper(),
                "sleeve": (row.get("sleeve") or "").strip(),
                "region": (row.get("region") or "").strip(),
                "style": (row.get("style") or "").strip(),
                "notes": (row.get("notes") or "").strip(),
            }
    return result


def read_targets(path: str | Path = DEFAULT_TARGETS) -> Dict[str, float]:
    p = Path(path)
    targets: Dict[str, float] = {}
    if not p.exists():
        return targets
    with p.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            key = (row.get("asset_class") or row.get("ticker") or row.get("symbol") or "").strip().upper()
            value = row.get("target_pct") or row.get("target") or ""
            if key:
                targets[key] = _pct(value)
    return targets


def _latest_price_lookup(workspace_id: str = "local", db_path: str | Path = DEFAULT_DB) -> Dict[str, float]:
    snaps = load_latest_snapshots(workspace_id=workspace_id, db_path=db_path)
    return {sym.upper(): _num(row.get("price"), 0.0) for sym, row in snaps.items() if _num(row.get("price"), 0.0) > 0}


def holdings_market_values(
    holdings_csv: str | Path = DEFAULT_HOLDINGS,
    security_master_csv: str | Path = DEFAULT_SECURITY_MASTER,
    workspace_id: str = "local",
    db_path: str | Path = DEFAULT_DB,
) -> Tuple[Dict[str, float], Dict[str, dict]]:
    """Return asset-class dollar totals and per-symbol diagnostics.

    Price hierarchy for drift only: explicit market_value -> latest snapshot ->
    price column -> purchase_price/cost_basis_per_share. This avoids live network
    calls in drift analysis while still using nightly snapshots when available.
    """
    p = Path(holdings_csv)
    if not p.exists():
        return {}, {}
    master = read_security_master(security_master_csv)
    latest = _latest_price_lookup(workspace_id=workspace_id, db_path=db_path)
    totals: Dict[str, float] = {}
    details: Dict[str, dict] = {}
    with p.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            symbol = (row.get("ticker") or row.get("symbol") or "").strip().upper()
            if not symbol:
                continue
            shares = _num(row.get("shares"), 0.0)
            explicit_mv = _num(row.get("market_value") or row.get("value"), 0.0)
            if explicit_mv > 0:
                mv = explicit_mv
                price_source = "holdings_market_value"
                price = mv / shares if shares else mv
            else:
                price = latest.get(symbol) or _num(row.get("price"), 0.0) or _num(row.get("cost_basis_per_share"), 0.0) or _num(row.get("purchase_price"), 0.0)
                price_source = "latest_snapshot" if symbol in latest else "holdings_price_or_purchase_price"
                mv = shares * price
            if mv <= 0:
                continue
            asset_class = (row.get("asset_class") or master.get(symbol, {}).get("asset_class") or ("CASH" if symbol == "CASH" else "UNKNOWN")).strip().upper()
            totals[asset_class] = totals.get(asset_class, 0.0) + mv
            d = details.setdefault(symbol, {"symbol": symbol, "asset_class": asset_class, "market_value": 0.0, "shares": 0.0, "price_source": price_source})
            d["market_value"] += mv
            d["shares"] += shares
            d["price"] = price
            d["price_source"] = price_source if d.get("price_source") == price_source else "mixed"
    return totals, details


def holdings_allocation(
    holdings_csv: str | Path = DEFAULT_HOLDINGS,
    security_master_csv: str | Path = DEFAULT_SECURITY_MASTER,
    workspace_id: str = "local",
    db_path: str | Path = DEFAULT_DB,
) -> Dict[str, float]:
    totals, _ = holdings_market_values(holdings_csv, security_master_csv, workspace_id, db_path)
    grand = sum(totals.values())
    return {k: (v / grand if grand else 0.0) for k, v in totals.items()}


def analyze_drift(
    target_file: str | Path = DEFAULT_TARGETS,
    holdings_csv: str | Path = DEFAULT_HOLDINGS,
    security_master_csv: str | Path = DEFAULT_SECURITY_MASTER,
    threshold_pct: float = 0.05,
    workspace_id: str = "local",
    db_path: str | Path = DEFAULT_DB,
) -> List[dict]:
    targets = read_targets(target_file)
    totals, details = holdings_market_values(holdings_csv, security_master_csv, workspace_id, db_path)
    grand = sum(totals.values())
    actual = {k: (v / grand if grand else 0.0) for k, v in totals.items()}
    rows: List[dict] = []
    for k in sorted(set(targets) | set(actual)):
        a = actual.get(k, 0.0)
        t = targets.get(k, 0.0)
        drift = a - t
        rows.append({
            "bucket": k,
            "actual_pct": round(a * 100, 2),
            "target_pct": round(t * 100, 2),
            "drift_pct": round(drift * 100, 2),
            "market_value": round(totals.get(k, 0.0), 2),
            "outside_threshold": abs(drift) >= threshold_pct,
        })
    if any(row["bucket"] == "UNKNOWN" for row in rows):
        rows.append({
            "bucket": "__WARNING__",
            "actual_pct": 0,
            "target_pct": 0,
            "drift_pct": 0,
            "market_value": 0,
            "outside_threshold": False,
            "message": "Some holdings are not mapped in security_master.csv.",
        })
    return rows
