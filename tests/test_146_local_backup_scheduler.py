from __future__ import annotations

from datetime import datetime, timezone
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.local_backup_scheduler import (
    SCHEMA,
    load_policy,
    run_backup,
    save_policy,
    scheduler_status,
)


def _make_db(path: Path, value: str = "ok") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE IF NOT EXISTS t(v TEXT)")
    con.execute("INSERT INTO t(v) VALUES(?)", (value,))
    con.commit()
    con.close()


def test_default_policy_is_disabled_and_side_effect_free(tmp_path: Path) -> None:
    db = tmp_path / "local_state" / "retirement_system_v10.db"
    _make_db(db)

    status = scheduler_status(tmp_path, db)

    assert status["schema"] == SCHEMA
    assert status["policy"]["enabled"] is False
    assert status["due"] is False
    assert not (tmp_path / "saved_plans" / "auto_backups").exists()


def test_manual_backup_creates_rpx_and_manifest(tmp_path: Path) -> None:
    db = tmp_path / "local_state" / "retirement_system_v10.db"
    _make_db(db)
    save_policy(tmp_path, {"enabled": True, "cadence": "daily", "retention_count": 3})

    result = run_backup(tmp_path, db, trigger="manual", force=True, now=datetime(2026, 6, 26, 12, 0, tzinfo=timezone.utc))

    assert result["schema"] == SCHEMA
    assert result["created"] is True
    assert result["backup"]["filename"].endswith(".rpx")
    backup_path = Path(result["backup"]["path"])
    manifest_path = Path(result["backup"]["manifest_path"])
    assert backup_path.exists()
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema"] == SCHEMA
    assert manifest["trigger"] == "manual"
    assert len(manifest["sha256"]) == 64


def test_daily_backup_skips_when_already_current(tmp_path: Path) -> None:
    db = tmp_path / "local_state" / "retirement_system_v10.db"
    _make_db(db)
    save_policy(tmp_path, {"enabled": True, "cadence": "daily", "retention_count": 3})
    now = datetime(2026, 6, 26, 12, 0, tzinfo=timezone.utc)
    first = run_backup(tmp_path, db, trigger="save", force=False, now=now)
    second = run_backup(tmp_path, db, trigger="save", force=False, now=now)

    assert first["created"] is True
    assert second["created"] is False
    assert second["skipped"] is True
    assert second["skip_reason"] == "already_backed_up_today"


def test_retention_prunes_oldest_backups(tmp_path: Path) -> None:
    db = tmp_path / "local_state" / "retirement_system_v10.db"
    _make_db(db)
    save_policy(tmp_path, {"enabled": True, "cadence": "per_build", "retention_count": 2})

    for day in (24, 25, 26):
        result = run_backup(tmp_path, db, trigger="build", force=False, now=datetime(2026, 6, day, 12, 0, tzinfo=timezone.utc))
        assert result["success"] is True

    status = scheduler_status(tmp_path, db)
    assert status["backup_count"] == 2
    names = [item.name for item in (tmp_path / "saved_plans" / "auto_backups").glob("*.rpx")]
    assert len(names) == 2
    assert all("20260624" not in name for name in names)


def test_policy_normalizes_retention_and_cadence(tmp_path: Path) -> None:
    saved = save_policy(tmp_path, {"enabled": True, "cadence": "bogus", "retention_count": 200})
    loaded = load_policy(tmp_path)

    assert saved["policy"]["cadence"] == "daily"
    assert loaded["policy"]["retention_count"] == 60
