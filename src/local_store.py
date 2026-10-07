from __future__ import annotations

"""Local-only SQLite persistence for v11.

Local settings, result and KPI snapshots and build events. The sectioned plan
snapshots (``plan_snapshots`` and its summary tables) are no longer written or read
since WP4.2: the plan rows live in the plan file (``src/active_plan.py``). Their tables
stay in the schema until the one-time conversion (WP10) has read them. It intentionally
contains no tenant, workspace, user, role, token, or hosted identity concepts.
"""

from datetime import datetime, UTC
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from . import platform_runtime
from .sqlite_util import connect as closing_connect

# PROJECT_ROOT is the code root; the SQLite store is writable data and hangs off
# the workspace root (== package root on desktop, app-private storage on mobile).
PROJECT_ROOT = platform_runtime.package_root()
DEFAULT_DB = platform_runtime.workspace_root() / "local_state" / "retirement_system_v10.db"

# Result snapshots are append-only debug/audit payloads (~400 KB each) that no
# read path consumes.  Without a cap they dominate the database file, and every
# auto-backup copies the whole file, so the cost is paid again per build.
DEFAULT_RESULT_SNAPSHOT_RETENTION = 10

# KPI snapshots are a small dated series of headline build outputs (Wave 1 item
# 1.15 -- documentation/archive/reports/SYSTEM_REVIEW_2026-08-31.md, finding F13 and
# the §3.2 cross-cutting note on why this must exist before the engine/policy
# changes that move "probability of success"). Kept at the same retention
# depth as the local_state/*.db.version_* backup convention documented in
# CLAUDE.md's "Backup naming conventions" section, rather than inventing a
# separate policy.
DEFAULT_KPI_SNAPSHOT_RETENTION = 10

# Headline KPI fields tracked per snapshot -- deliberately just the numbers
# already computed into plan_summary.json / the Monte Carlo result, not a new
# derivation. See src/reporting/workbook_builder.py's plan-summary block for
# where each of these comes from.
KPI_SNAPSHOT_METRICS = (
    "probability_of_success",
    "terminal_nw_deterministic",
    "terminal_nw_mc_median",
    "terminal_nw_mc_p10",
    "terminal_nw_mc_p90",
    "lifetime_tax",
    "lcv",
    "eltr",
    "fcv",
    "eftr",
    "total_roth_conversions",
    "after_tax_terminal_nw",
    "npv_future_taxes",
    "terminal_nw_mc_p5",
)


def now_utc() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _resolve(db_path: str | Path | None = None) -> Path:
    p = Path(db_path or DEFAULT_DB)
    return p if p.is_absolute() else platform_runtime.workspace_root() / p


def init_local_store(db_path: str | Path | None = None) -> Path:
    p = _resolve(db_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with closing_connect(p) as con:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=NORMAL")
        con.execute("""CREATE TABLE IF NOT EXISTS plan_snapshots(
            snapshot_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            source TEXT NOT NULL,
            input_json TEXT NOT NULL,
            sectioned_json TEXT NOT NULL,
            result_json TEXT,
            input_sha256 TEXT NOT NULL,
            result_sha256 TEXT,
            note TEXT
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS result_snapshots(
            result_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            plan_snapshot_id TEXT,
            result_json TEXT NOT NULL,
            event_log_json TEXT NOT NULL,
            result_sha256 TEXT NOT NULL,
            FOREIGN KEY(plan_snapshot_id) REFERENCES plan_snapshots(snapshot_id)
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS build_events(
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            build_id TEXT,
            stage TEXT,
            event_type TEXT,
            detail_json TEXT NOT NULL
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS local_settings(
            key TEXT PRIMARY KEY,
            value_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS plan_members(
            snapshot_id TEXT NOT NULL,
            member_id TEXT NOT NULL,
            display_name TEXT,
            birth_year INTEGER,
            owner_role TEXT,
            PRIMARY KEY(snapshot_id, member_id),
            FOREIGN KEY(snapshot_id) REFERENCES plan_snapshots(snapshot_id)
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS plan_accounts(
            snapshot_id TEXT NOT NULL,
            account_id TEXT NOT NULL,
            display_name TEXT,
            owner_id TEXT,
            account_type TEXT,
            tax_treatment TEXT,
            current_value_cents INTEGER,
            prior_year_end_value_cents INTEGER,
            PRIMARY KEY(snapshot_id, account_id),
            FOREIGN KEY(snapshot_id) REFERENCES plan_snapshots(snapshot_id)
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS plan_income_streams(
            snapshot_id TEXT NOT NULL,
            income_id TEXT NOT NULL,
            label TEXT,
            owner_id TEXT,
            income_type TEXT,
            annual_amount_cents INTEGER,
            start_year INTEGER,
            end_year INTEGER,
            inflation_index TEXT,
            PRIMARY KEY(snapshot_id, income_id),
            FOREIGN KEY(snapshot_id) REFERENCES plan_snapshots(snapshot_id)
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS kpi_snapshots(
            snapshot_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            build_id TEXT,
            probability_of_success REAL,
            terminal_nw_deterministic REAL,
            terminal_nw_mc_median REAL,
            terminal_nw_mc_p10 REAL,
            terminal_nw_mc_p90 REAL,
            lifetime_tax REAL,
            lcv REAL,
            eltr REAL,
            fcv REAL,
            eftr REAL,
            total_roth_conversions REAL,
            after_tax_terminal_nw REAL,
            npv_future_taxes REAL,
            terminal_nw_mc_p5 REAL,
            kpi_json TEXT NOT NULL
        )""")
        # #293: the two columns above were added after the table already shipped -- CREATE
        # TABLE IF NOT EXISTS above is a no-op against an existing db file,
        # so an existing kpi_snapshots table needs an explicit ALTER (same
        # pattern as config_backend.py's price_snapshots.workspace_id
        # migration) or every insert against a pre-#293 db fails with
        # "no such column".
        kpi_cols = [r[1] for r in con.execute("PRAGMA table_info(kpi_snapshots)").fetchall()]
        if "npv_future_taxes" not in kpi_cols:
            con.execute("ALTER TABLE kpi_snapshots ADD COLUMN npv_future_taxes REAL")
        if "terminal_nw_mc_p5" not in kpi_cols:
            con.execute("ALTER TABLE kpi_snapshots ADD COLUMN terminal_nw_mc_p5 REAL")
        con.execute("""CREATE TABLE IF NOT EXISTS plan_spending_policy(
            snapshot_id TEXT PRIMARY KEY,
            annual_core_spending_cents INTEGER,
            core_growth_method TEXT,
            manual_core_growth_rate TEXT,
            annual_mortgage_cents INTEGER,
            annual_real_estate_tax_cents INTEGER,
            real_estate_tax_growth_rate TEXT,
            FOREIGN KEY(snapshot_id) REFERENCES plan_snapshots(snapshot_id)
        )""")
    return p


def _stable_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _digest(obj: Any) -> str:
    return hashlib.sha256(_stable_json(obj).encode("utf-8")).hexdigest()


def get_local_setting(key: str, default: Any = None, db_path: str | Path | None = None) -> Any:
    """Read one JSON-encoded value out of the local_settings table.

    Returns `default` when the store does not exist yet, the key is absent, or
    the stored value will not parse. That last case is deliberate rather than
    lax: the first consumer of this is the plan-data schema-version gate, which
    runs during startup, and a JSONDecodeError there would refuse to open a
    database the user can otherwise still use. Treating an unreadable version
    marker as "not migrated yet" is safe, because the migration itself is
    idempotent.
    """
    p = _resolve(db_path)
    if not p.exists():
        return default
    with closing_connect(p) as con:
        row = con.execute("SELECT value_json FROM local_settings WHERE key=?", (key,)).fetchone()
    if not row:
        return default
    try:
        return json.loads(row[0])
    except (TypeError, ValueError):
        return default


def set_local_setting(key: str, value: Any, db_path: str | Path | None = None) -> None:
    """Write one JSON-encoded value to local_settings, upserting on the key."""
    p = init_local_store(db_path)
    with closing_connect(p) as con:
        con.execute(
            "INSERT INTO local_settings(key, value_json, updated_at) VALUES(?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, updated_at=excluded.updated_at",
            (key, json.dumps(value, sort_keys=True, default=str), now_utc()),
        )


def save_result_snapshot(result: dict[str, Any], event_log: list[dict[str, Any]] | None = None, plan_snapshot_id: str | None = None, db_path: str | Path | None = None) -> str:
    p = init_local_store(db_path)
    result_sha = _digest(result)
    result_id = result_sha[:16]
    with closing_connect(p) as con:
        con.execute("""INSERT INTO result_snapshots(result_id, created_at, plan_snapshot_id, result_json, event_log_json, result_sha256)
                       VALUES(?,?,?,?,?,?)
                       ON CONFLICT(result_id) DO UPDATE SET result_json=excluded.result_json,
                         event_log_json=excluded.event_log_json, result_sha256=excluded.result_sha256""",
                    (result_id, now_utc(), plan_snapshot_id, json.dumps(result, sort_keys=True, default=str), json.dumps(event_log or [], sort_keys=True, default=str), result_sha))
        _prune_result_snapshots(con)
    return result_id


def _prune_result_snapshots(con: sqlite3.Connection, keep: int = DEFAULT_RESULT_SNAPSHOT_RETENTION) -> int:
    """Delete all but the newest ``keep`` result snapshots. Returns rows removed.

    ``created_at`` has second precision, so ``result_id`` breaks ties to keep the
    ordering total and the retained set deterministic.
    """
    keep = max(1, int(keep))
    cur = con.execute(
        """DELETE FROM result_snapshots WHERE result_id NOT IN (
               SELECT result_id FROM result_snapshots
               ORDER BY created_at DESC, result_id DESC LIMIT ?
           )""",
        (keep,),
    )
    return cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0


def prune_result_snapshots(keep: int = DEFAULT_RESULT_SNAPSHOT_RETENTION, db_path: str | Path | None = None) -> int:
    """Public entrypoint to trim accumulated result snapshots."""
    p = _resolve(db_path)
    if not p.exists():
        return 0
    with closing_connect(p) as con:
        return _prune_result_snapshots(con, keep)


def save_kpi_snapshot(
    kpis: dict[str, Any],
    build_id: str = "",
    created_at: str | None = None,
    db_path: str | Path | None = None,
) -> str:
    """Append one dated headline-KPI snapshot (Wave 1 item 1.15).

    Append-only, like ``save_result_snapshot``: a build never overwrites a
    prior snapshot, it adds a new row, then prunes back to
    ``DEFAULT_KPI_SNAPSHOT_RETENTION`` rows (the same "keep the last 10"
    convention CLAUDE.md documents for ``local_state/*.db.version_*``
    backups). ``created_at`` defaults to the real wall clock but accepts an
    explicit override so a build running under
    ``RETIREMENT_SYSTEM_FROZEN_TODAY`` can date the snapshot by the plan's
    projection basis date rather than the moment the build subprocess
    happened to run -- this is what makes two builds of the same plan a week
    apart produce a comparable, sensibly-dated pair of rows instead of two
    rows a few seconds apart under today's real date.

    Only the metrics in ``KPI_SNAPSHOT_METRICS`` are indexed into columns for
    cheap SQL comparison; the full ``kpis`` dict is preserved verbatim in
    ``kpi_json`` so a future (Wave 3) attribution pass has everything that was
    known at archive time, not just today's shortlist.
    """
    p = init_local_store(db_path)
    created = created_at or now_utc()
    snapshot_id = hashlib.sha256(f"{created}:{build_id}:{_stable_json(kpis)}".encode("utf-8")).hexdigest()[:16]
    payload = dict(kpis)
    payload["build_id"] = build_id
    payload["created_at"] = created
    with closing_connect(p) as con:
        con.execute(
            """INSERT INTO kpi_snapshots(
                   snapshot_id, created_at, build_id, probability_of_success,
                   terminal_nw_deterministic, terminal_nw_mc_median, terminal_nw_mc_p10,
                   terminal_nw_mc_p90, lifetime_tax, lcv, eltr, fcv, eftr,
                   total_roth_conversions, after_tax_terminal_nw,
                   npv_future_taxes, terminal_nw_mc_p5, kpi_json
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(snapshot_id) DO NOTHING""",
            (
                snapshot_id,
                created,
                build_id or None,
                kpis.get("probability_of_success"),
                kpis.get("terminal_nw_deterministic"),
                kpis.get("terminal_nw_mc_median"),
                kpis.get("terminal_nw_mc_p10"),
                kpis.get("terminal_nw_mc_p90"),
                kpis.get("lifetime_tax"),
                kpis.get("lcv"),
                kpis.get("eltr"),
                kpis.get("fcv"),
                kpis.get("eftr"),
                kpis.get("total_roth_conversions"),
                kpis.get("after_tax_terminal_nw"),
                kpis.get("npv_future_taxes"),
                kpis.get("terminal_nw_mc_p5"),
                json.dumps(payload, sort_keys=True, default=str),
            ),
        )
        _prune_kpi_snapshots(con)
    return snapshot_id


def _prune_kpi_snapshots(con: sqlite3.Connection, keep: int = DEFAULT_KPI_SNAPSHOT_RETENTION) -> int:
    """Delete all but the newest ``keep`` KPI snapshots. Returns rows removed.

    ``created_at`` has second precision (or is caller-supplied, e.g. a plain
    date under a frozen clock), so ``snapshot_id`` breaks ties to keep the
    ordering total and the retained set deterministic -- mirroring
    ``_prune_result_snapshots``.
    """
    keep = max(1, int(keep))
    cur = con.execute(
        """DELETE FROM kpi_snapshots WHERE snapshot_id NOT IN (
               SELECT snapshot_id FROM kpi_snapshots
               ORDER BY created_at DESC, snapshot_id DESC LIMIT ?
           )""",
        (keep,),
    )
    return cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0


def prune_kpi_snapshots(keep: int = DEFAULT_KPI_SNAPSHOT_RETENTION, db_path: str | Path | None = None) -> int:
    """Public entrypoint to trim accumulated KPI snapshots."""
    p = _resolve(db_path)
    if not p.exists():
        return 0
    with closing_connect(p) as con:
        return _prune_kpi_snapshots(con, keep)


def _kpi_row_to_payload(row: tuple) -> dict[str, Any]:
    snapshot_id, created_at, build_id, kpi_json = row
    try:
        payload = json.loads(kpi_json)
    except Exception:
        payload = {}
    payload["snapshot_id"] = snapshot_id
    payload["created_at"] = created_at
    payload["build_id"] = build_id
    return payload


def list_kpi_snapshots(limit: int = DEFAULT_KPI_SNAPSHOT_RETENTION, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    """Newest-first list of archived KPI snapshots (for a "history" view)."""
    p = _resolve(db_path)
    if not p.exists():
        return []
    with closing_connect(p) as con:
        rows = con.execute(
            "SELECT snapshot_id, created_at, build_id, kpi_json FROM kpi_snapshots ORDER BY created_at DESC, snapshot_id DESC LIMIT ?",
            (max(1, int(limit)),),
        ).fetchall()
    return [_kpi_row_to_payload(r) for r in rows]


def get_kpi_snapshot(snapshot_id: str, db_path: str | Path | None = None) -> dict[str, Any] | None:
    p = _resolve(db_path)
    if not p.exists() or not snapshot_id:
        return None
    with closing_connect(p) as con:
        row = con.execute(
            "SELECT snapshot_id, created_at, build_id, kpi_json FROM kpi_snapshots WHERE snapshot_id=?",
            (snapshot_id,),
        ).fetchone()
    return _kpi_row_to_payload(row) if row else None


def get_kpi_snapshot_by_build_id(build_id: str, db_path: str | Path | None = None) -> dict[str, Any] | None:
    """Latest snapshot recorded for a given build id, when that is a more
    convenient handle than the content-derived snapshot_id (e.g. tests that
    set RETIREMENT_SYSTEM_BUILD_ID explicitly)."""
    p = _resolve(db_path)
    if not p.exists() or not build_id:
        return None
    with closing_connect(p) as con:
        row = con.execute(
            "SELECT snapshot_id, created_at, build_id, kpi_json FROM kpi_snapshots WHERE build_id=? ORDER BY created_at DESC, snapshot_id DESC LIMIT 1",
            (build_id,),
        ).fetchone()
    return _kpi_row_to_payload(row) if row else None


def compare_kpi_snapshots(
    from_id: str | None = None,
    to_id: str | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any] | None:
    """Wave-1-scoped raw before/after diff of headline KPIs between two builds.

    Deliberately no attribution (market vs. spending vs. assumption change) --
    that is Wave 3's job once a real snapshot series exists to validate it
    against (documentation/archive/reports/SYSTEM_REVIEW_2026-08-31.md, F13). This
    only ever reports *what* changed.

    When ``from_id``/``to_id`` are omitted, compares the two most recent
    snapshots (``to`` = latest, ``from`` = the one immediately before it).
    Returns ``None`` when fewer than two snapshots are available, or a
    requested id does not resolve to a stored snapshot.
    """
    to_snap = get_kpi_snapshot(to_id, db_path=db_path) if to_id else None
    from_snap = get_kpi_snapshot(from_id, db_path=db_path) if from_id else None
    if to_snap is None or from_snap is None:
        recent = list_kpi_snapshots(limit=2, db_path=db_path)
        if to_snap is None:
            to_snap = recent[0] if len(recent) >= 1 else None
        if from_snap is None:
            from_snap = recent[1] if len(recent) >= 2 else None
    if not to_snap or not from_snap:
        return None
    diff: dict[str, Any] = {}
    for key in KPI_SNAPSHOT_METRICS:
        before = from_snap.get(key)
        after = to_snap.get(key)
        delta = None
        pct_change = None
        if isinstance(before, (int, float)) and isinstance(after, (int, float)) and not isinstance(before, bool) and not isinstance(after, bool):
            delta = after - before
            pct_change = (delta / before) if before else None
        diff[key] = {"from": before, "to": after, "delta": delta, "pct_change": pct_change}
    return {
        "success": True,
        "schema": "kpi_snapshot_compare_v1",
        "from": {"snapshot_id": from_snap.get("snapshot_id"), "created_at": from_snap.get("created_at"), "build_id": from_snap.get("build_id")},
        "to": {"snapshot_id": to_snap.get("snapshot_id"), "created_at": to_snap.get("created_at"), "build_id": to_snap.get("build_id")},
        "diff": diff,
    }


def append_build_event(stage: str, event_type: str, detail: dict[str, Any] | None = None, build_id: str | None = None, db_path: str | Path | None = None) -> None:
    p = init_local_store(db_path)
    with closing_connect(p) as con:
        con.execute("INSERT INTO build_events(created_at, build_id, stage, event_type, detail_json) VALUES(?,?,?,?,?)",
                    (now_utc(), build_id or "local", stage, event_type, json.dumps(detail or {}, sort_keys=True, default=str)))
