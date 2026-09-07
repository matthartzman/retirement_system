"""System review 2026-09-07 SEC-3: `tools/backup_to_onedrive.py` used to
exclude only regenerable caches (build/__pycache__/.pytest_cache/.git),
which meant every rebuild zipped a live Monarch Extractor browser session
(a replayable login) and the plaintext secrets store into an unencrypted
archive pushed to OneDrive. This pins that both are now excluded, while
ordinary project files and plan data still get backed up.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
backup_to_onedrive = importlib.import_module("tools.backup_to_onedrive")


def _make_tree(root: Path) -> None:
    (root / "src").mkdir(parents=True)
    (root / "src" / "core.py").write_text("pass\n", encoding="utf-8")

    (root / "local_state").mkdir(parents=True)
    (root / "local_state" / "secrets.local.json").write_text("{}", encoding="utf-8")
    (root / "local_state" / "retirement_system_v10.db").write_text("db", encoding="utf-8")

    (root / "Monarch Extractor" / "monarch-browser" / "Default").mkdir(parents=True)
    (root / "Monarch Extractor" / "monarch-browser" / "Default" / "Cookies").write_text(
        "session", encoding="utf-8"
    )
    (root / "Monarch Extractor" / ".venv" / "lib").mkdir(parents=True)
    (root / "Monarch Extractor" / ".venv" / "lib" / "site.py").write_text("x", encoding="utf-8")
    (root / "Monarch Extractor" / "monarch_extract.py").write_text("x", encoding="utf-8")

    (root / "input").mkdir(parents=True)
    (root / "input" / "client_data.csv").write_text("household\n", encoding="utf-8")


def test_secrets_store_and_monarch_browser_profile_are_excluded(tmp_path):
    _make_tree(tmp_path)

    included = {p.relative_to(tmp_path).as_posix() for p in backup_to_onedrive.iter_files(tmp_path)}

    assert "local_state/secrets.local.json" not in included
    assert not any("monarch-browser" in p for p in included)
    assert not any("/.venv/" in p or p.startswith(".venv/") for p in included)

    # ordinary project and plan-data files are still backed up
    assert "src/core.py" in included
    assert "local_state/retirement_system_v10.db" in included
    assert "input/client_data.csv" in included
    assert "Monarch Extractor/monarch_extract.py" in included
