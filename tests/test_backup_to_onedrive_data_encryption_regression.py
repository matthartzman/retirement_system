"""X-13: the project backup holds no household data unless asked, then only as an encrypted archive; no personal
folder names are built in; and manage_secret.py (which crashed with NameError: _run) runs."""
from __future__ import annotations

import importlib
import io
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
bk = importlib.import_module("tools.backup_to_onedrive")


def _tree(root: Path) -> None:
    files = {
        "src/core.py": "pass\n", "README.md": "hi\n",
        "local_state/identity.db": "ID", "local_state/app.db": "APP", "local_state/retirement_system_v10.db": "db",
        "saved_plans/auto_backups/plan.rpx": "PLAN", "plan.rpx": "PLAN", "plan.rpx.version_20261101": "PLAN",
        "saved_plans/old.RPX": "PLAN",
        "Monarch Extractor/output/balances.csv": "date,account_key,account,balance\n",
        "financial_trends_reporter/data/monarch_balances.sqlite3": "B",
        "financial_trends_reporter/data/financial_trends_log.jsonl": "L",
        "financial_trends_reporter/data/financial_trends_log.jsonl.key": "K",
        "financial_trends_reporter/data/financial_trends_log.jsonl.head": "H",
        "Monarch Extractor/monarch-browser/Default/Cookies": "session",
    }
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")


def _names(root, **kw):
    return {p.relative_to(root).as_posix() for p in bk.iter_files(root, **kw)}


def test_default_archive_excludes_every_household_data_file(tmp_path):
    _tree(tmp_path)
    got = _names(tmp_path)
    assert got == {"src/core.py", "README.md"}


def test_include_data_adds_them_but_never_credentials(tmp_path):
    _tree(tmp_path)
    got = _names(tmp_path, include_data=True)
    assert {"local_state/identity.db", "plan.rpx", "plan.rpx.version_20261101", "saved_plans/old.RPX",
            "financial_trends_reporter/data/monarch_balances.sqlite3"} <= got
    assert not any("monarch-browser" in p for p in got)


def test_no_personal_name_or_path_is_built_in():
    text = (ROOT / "tools" / "backup_to_onedrive.py").read_text(encoding="utf-8")
    assert "Hartzman" not in text and "Vault" not in text and "5-Personal" not in text


def test_destination_prefers_override_then_existing_onedrive_folder_then_home(tmp_path, monkeypatch):
    monkeypatch.delenv("RP_BACKUP_DIR", raising=False)
    monkeypatch.delenv("OneDriveCommercial", raising=False)
    monkeypatch.setenv("OneDrive", str(tmp_path))
    monkeypatch.setattr(bk.Path, "home", classmethod(lambda cls: tmp_path / "home"))
    assert bk.resolve_backup_dir() == tmp_path / "home" / "RetirementPlannerBackups"  # no OneDrive "Retirement Planning"
    (tmp_path / "Retirement Planning").mkdir()
    assert bk.resolve_backup_dir() == tmp_path / "Retirement Planning" / "Backups"
    monkeypatch.setenv("RP_BACKUP_DIR", str(tmp_path / "x"))
    assert bk.resolve_backup_dir() == tmp_path / "x"


def _run_main(monkeypatch, tmp_path, args, *, root):
    monkeypatch.setattr(bk, "PROJECT_ROOT", root)
    monkeypatch.setenv("RP_BACKUP_DIR", str(tmp_path / "dest"))
    return bk.main(args)


def test_include_data_run_writes_only_an_encrypted_archive_that_round_trips(tmp_path, monkeypatch):
    root = tmp_path / "proj"
    _tree(root)
    pw = tmp_path / "pw.txt"
    pw.write_text("a long enough passphrase\n", encoding="utf-8")
    assert _run_main(monkeypatch, tmp_path, ["--include-data", "--passphrase-file", str(pw)], root=root) == 0
    out = list((tmp_path / "dest").iterdir())
    assert [p.suffixes[-2:] for p in out] == [[".zip", ".enc"]]
    raw = out[0].read_bytes()
    assert b"PLAN" not in raw and b"PK\x03\x04" not in raw and raw.startswith(bk.ENC_MAGIC)  # nothing readable in the clear
    plain = tmp_path / "back.zip"
    bk.decrypt_file(out[0], plain, "a long enough passphrase")
    with zipfile.ZipFile(plain) as zf:
        assert any(n.endswith("plan.rpx") for n in zf.namelist()) and zf.testzip() is None
    with pytest.raises(Exception):  # wrong passphrase
        bk.decrypt_file(out[0], tmp_path / "bad.zip", "a different passphrase!")
    assert not (tmp_path / "bad.zip").exists()


def test_include_data_without_a_passphrase_is_refused_and_writes_nothing(tmp_path, monkeypatch, capsys):
    root = tmp_path / "proj"
    _tree(root)
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))  # not a terminal
    assert _run_main(monkeypatch, tmp_path, ["--include-data"], root=root) == 2
    short = tmp_path / "short.txt"
    short.write_text("short", encoding="utf-8")
    assert _run_main(monkeypatch, tmp_path, ["--include-data", "--passphrase-file", str(short)], root=root) == 2
    assert not (tmp_path / "dest").exists() or not list((tmp_path / "dest").iterdir())


def test_default_run_writes_a_plain_zip_without_data(tmp_path, monkeypatch):
    root = tmp_path / "proj"
    _tree(root)
    assert _run_main(monkeypatch, tmp_path, [], root=root) == 0
    (zpath,) = list((tmp_path / "dest").iterdir())
    assert zpath.suffix == ".zip"
    with zipfile.ZipFile(zpath) as zf:
        assert sorted(n.split("/", 1)[1] for n in zf.namelist()) == ["README.md", "src/core.py"]


def test_manage_secret_runs_without_a_nameerror(monkeypatch, capsys):
    """``_run`` used to be defined below the ``__main__`` block, so running the tool raised NameError."""
    import runpy

    monkeypatch.setattr("src.secrets_store.get_secret", lambda name, ws: "a-value")
    monkeypatch.setattr(sys, "argv", ["manage_secret.py", "fmp_api_key", "--show"])
    runpy.run_path(str(ROOT / "tools" / "manage_secret.py"), run_name="__main__")  # must not raise
    out = capsys.readouterr().out
    assert "'configured': True" in out and "a-value" not in out  # only a fingerprint is printed
