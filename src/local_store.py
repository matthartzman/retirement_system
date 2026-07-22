from __future__ import annotations

"""Local-only SQLite persistence for v10.

This store replaces CSV folders as the runtime source of truth while preserving
CSV/JSON/YAML as import-export adapters.  It intentionally contains no tenant,
workspace, user, role, token, or hosted identity concepts.
"""

from datetime import datetime, UTC
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from .domain_models import PlanInput, SectionedData, plan_input_from_sectioned_data
from . import platform_runtime

# PROJECT_ROOT is the code root; the SQLite store is writable data and hangs off
# the workspace root (== package root on desktop, app-private storage on mobile).
PROJECT_ROOT = platform_runtime.package_root()
DEFAULT_DB = platform_runtime.workspace_root() / "local_state" / "retirement_system_v10.db"

# Result snapshots are append-only debug/audit payloads (~400 KB each) that no
# read path consumes.  Without a cap they dominate the database file, and every
# auto-backup copies the whole file, so the cost is paid again per build.
DEFAULT_RESULT_SNAPSHOT_RETENTION = 10


def now_utc() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _resolve(db_path: str | Path | None = None) -> Path:
    p = Path(db_path or DEFAULT_DB)
    return p if p.is_absolute() else platform_runtime.workspace_root() / p


def init_local_store(db_path: str | Path | None = None) -> Path:
    p = _resolve(db_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(p) as con:
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


def save_plan_input(plan: PlanInput, source: str = "ui", db_path: str | Path | None = None, note: str = "") -> str:
    plan.validate()
    p = init_local_store(db_path)
    payload = plan.to_dict()
    sectioned = plan.to_sectioned_data()
    input_sha = _digest(payload)
    snapshot_id = input_sha[:16]
    with sqlite3.connect(p) as con:
        con.execute("""INSERT INTO plan_snapshots(snapshot_id, created_at, source, input_json, sectioned_json, input_sha256, note)
                       VALUES(?,?,?,?,?,?,?)
                       ON CONFLICT(snapshot_id) DO UPDATE SET source=excluded.source, input_json=excluded.input_json,
                         sectioned_json=excluded.sectioned_json, input_sha256=excluded.input_sha256, note=excluded.note""",
                    (snapshot_id, now_utc(), source, json.dumps(payload, indent=2, sort_keys=True), json.dumps(sectioned, sort_keys=True), input_sha, note))
        con.execute("DELETE FROM plan_members WHERE snapshot_id=?", (snapshot_id,))
        con.execute("DELETE FROM plan_accounts WHERE snapshot_id=?", (snapshot_id,))
        con.execute("DELETE FROM plan_income_streams WHERE snapshot_id=?", (snapshot_id,))
        con.execute("DELETE FROM plan_spending_policy WHERE snapshot_id=?", (snapshot_id,))
        for m in plan.members:
            con.execute("INSERT INTO plan_members(snapshot_id, member_id, display_name, birth_year, owner_role) VALUES(?,?,?,?,?)",
                        (snapshot_id, m.id, m.display_name, m.birth_year, m.owner_role))
        for a in plan.accounts:
            con.execute("""INSERT INTO plan_accounts(snapshot_id, account_id, display_name, owner_id, account_type, tax_treatment, current_value_cents, prior_year_end_value_cents)
                           VALUES(?,?,?,?,?,?,?,?)""",
                        (snapshot_id, a.id, a.display_name, a.owner_id, a.account_type, a.tax_treatment, a.current_value_cents, a.prior_year_end_value_cents))
        for s in plan.income_streams:
            con.execute("""INSERT INTO plan_income_streams(snapshot_id, income_id, label, owner_id, income_type, annual_amount_cents, start_year, end_year, inflation_index)
                           VALUES(?,?,?,?,?,?,?,?,?)""",
                        (snapshot_id, s.id, s.label, s.owner_id, s.income_type, s.annual_amount_cents, s.start_year, s.end_year, s.inflation_index))
        sp = plan.spending_policy
        con.execute("""INSERT INTO plan_spending_policy(snapshot_id, annual_core_spending_cents, core_growth_method, manual_core_growth_rate, annual_mortgage_cents, annual_real_estate_tax_cents, real_estate_tax_growth_rate)
                       VALUES(?,?,?,?,?,?,?)""",
                    (snapshot_id, sp.annual_core_spending_cents, sp.core_growth_method, str(sp.manual_core_growth_rate), sp.annual_mortgage_cents, sp.annual_real_estate_tax_cents, str(sp.real_estate_tax_growth_rate)))
    return snapshot_id


def import_sectioned_plan(data: SectionedData, source: str = "csv_import", db_path: str | Path | None = None) -> str:
    return save_plan_input(plan_input_from_sectioned_data(data), source=source, db_path=db_path)


def latest_plan_input(db_path: str | Path | None = None) -> PlanInput | None:
    p = _resolve(db_path)
    if not p.exists():
        return None
    with sqlite3.connect(p) as con:
        # created_at has only second precision (now_utc() truncates to seconds),
        # so two saves landing in the same wall-clock second (routine for a
        # save-then-sync-then-build sequence) tie there; rowid -- monotonically
        # assigned per INSERT, unaffected by the ON CONFLICT UPDATE path since
        # that only fires for a repeat of identical content under the same
        # snapshot_id -- breaks the tie deterministically in favor of the
        # truly-latest snapshot instead of an arbitrary same-second one.
        row = con.execute("SELECT input_json FROM plan_snapshots ORDER BY created_at DESC, rowid DESC LIMIT 1").fetchone()
    if not row:
        return None
    raw = json.loads(row[0])
    tmp = p.parent / ".latest_plan_input.json"
    tmp.write_text(json.dumps(raw), encoding="utf-8")
    from .domain_models import plan_input_from_json
    return plan_input_from_json(tmp)


def latest_sectioned_data(db_path: str | Path | None = None) -> SectionedData:
    p = _resolve(db_path)
    if not p.exists():
        return {}
    with sqlite3.connect(p) as con:
        # See latest_plan_input() for why rowid breaks same-second created_at ties.
        row = con.execute("SELECT sectioned_json FROM plan_snapshots ORDER BY created_at DESC, rowid DESC LIMIT 1").fetchone()
    return json.loads(row[0]) if row else {}


def save_result_snapshot(result: dict[str, Any], event_log: list[dict[str, Any]] | None = None, plan_snapshot_id: str | None = None, db_path: str | Path | None = None) -> str:
    p = init_local_store(db_path)
    result_sha = _digest(result)
    result_id = result_sha[:16]
    with sqlite3.connect(p) as con:
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
    with sqlite3.connect(p) as con:
        return _prune_result_snapshots(con, keep)


def append_build_event(stage: str, event_type: str, detail: dict[str, Any] | None = None, build_id: str | None = None, db_path: str | Path | None = None) -> None:
    p = init_local_store(db_path)
    with sqlite3.connect(p) as con:
        con.execute("INSERT INTO build_events(created_at, build_id, stage, event_type, detail_json) VALUES(?,?,?,?,?)",
                    (now_utc(), build_id or "local", stage, event_type, json.dumps(detail or {}, sort_keys=True, default=str)))


def export_latest_plan_json(path: str | Path, db_path: str | Path | None = None) -> Path:
    plan = latest_plan_input(db_path)
    if plan is None:
        raise FileNotFoundError("No local v10 plan snapshot exists")
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(plan.to_json(), encoding="utf-8")
    return out


def latest_plan_snapshot(db_path: str | Path | None = None) -> dict[str, Any] | None:
    """Return the latest canonical local plan snapshot payload and relational summaries."""
    p = _resolve(db_path)
    if not p.exists():
        return None
    with sqlite3.connect(p) as con:
        row = con.execute("SELECT snapshot_id, created_at, source, input_json, sectioned_json, input_sha256 FROM plan_snapshots ORDER BY created_at DESC LIMIT 1").fetchone()
        if not row:
            return None
        snapshot_id, created_at, source, input_json, sectioned_json, input_sha = row
        members = [dict(zip(["snapshot_id","member_id","display_name","birth_year","owner_role"], r)) for r in con.execute("SELECT snapshot_id, member_id, display_name, birth_year, owner_role FROM plan_members WHERE snapshot_id=? ORDER BY member_id", (snapshot_id,)).fetchall()]
        accounts = [dict(zip(["snapshot_id","account_id","display_name","owner_id","account_type","tax_treatment","current_value_cents","prior_year_end_value_cents"], r)) for r in con.execute("SELECT snapshot_id, account_id, display_name, owner_id, account_type, tax_treatment, current_value_cents, prior_year_end_value_cents FROM plan_accounts WHERE snapshot_id=? ORDER BY account_id", (snapshot_id,)).fetchall()]
        income_streams = [dict(zip(["snapshot_id","income_id","label","owner_id","income_type","annual_amount_cents","start_year","end_year","inflation_index"], r)) for r in con.execute("SELECT snapshot_id, income_id, label, owner_id, income_type, annual_amount_cents, start_year, end_year, inflation_index FROM plan_income_streams WHERE snapshot_id=? ORDER BY income_id", (snapshot_id,)).fetchall()]
        spending = con.execute("SELECT annual_core_spending_cents, core_growth_method, manual_core_growth_rate, annual_mortgage_cents, annual_real_estate_tax_cents, real_estate_tax_growth_rate FROM plan_spending_policy WHERE snapshot_id=?", (snapshot_id,)).fetchone()
    return {
        "snapshot_id": snapshot_id,
        "created_at": created_at,
        "source": source,
        "input": json.loads(input_json),
        "sectioned_data": json.loads(sectioned_json),
        "input_sha256": input_sha,
        "members": members,
        "accounts": accounts,
        "income_streams": income_streams,
        "spending_policy": dict(zip(["annual_core_spending_cents","core_growth_method","manual_core_growth_rate","annual_mortgage_cents","annual_real_estate_tax_cents","real_estate_tax_growth_rate"], spending)) if spending else {},
    }


def export_latest_plan(path: str | Path, fmt: str = "json", db_path: str | Path | None = None) -> Path:
    """Losslessly export the canonical local plan snapshot to JSON/YAML/CSV adapter files."""
    snap = latest_plan_snapshot(db_path)
    if not snap:
        raise FileNotFoundError("No local v10 plan snapshot exists")
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fmt = (fmt or out.suffix.lstrip(".") or "json").lower()
    if fmt in {"yaml", "yml"}:
        try:
            import yaml  # type: ignore
            out.write_text(yaml.safe_dump(snap["input"], sort_keys=True, allow_unicode=True), encoding="utf-8")
        except Exception:
            out.write_text(json.dumps(snap["input"], indent=2, sort_keys=True), encoding="utf-8")
    elif fmt == "csv":
        import csv
        sectioned = snap["sectioned_data"]
        with out.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["section", "subsection", "label", "value"])
            w.writeheader()
            for section, subs in sectioned.items():
                for subsection, labels in subs.items():
                    for label, value in labels.items():
                        w.writerow({"section": section, "subsection": subsection, "label": label, "value": value})
    else:
        out.write_text(json.dumps(snap["input"], indent=2, sort_keys=True), encoding="utf-8")
    return out
