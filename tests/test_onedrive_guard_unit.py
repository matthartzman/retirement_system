"""Both scheduled headless jobs (Monarch auto-import, financial trends
reporter) read files under paths that are commonly OneDrive-synced on
Windows; a truncated or not-fully-downloaded file must be caught before
import rather than silently corrupting plan data.
"""
from __future__ import annotations

from src import onedrive_guard as guard


def test_missing_file_is_unsafe(tmp_path):
    err = guard.check_file_is_safe_to_read(tmp_path / "missing.csv")
    assert err and "does not exist" in err


def test_zero_byte_file_is_unsafe(tmp_path):
    p = tmp_path / "empty.csv"
    p.write_text("", encoding="utf-8")
    err = guard.check_file_is_safe_to_read(p)
    assert err and "zero bytes" in err


def test_normal_file_is_safe(tmp_path):
    p = tmp_path / "ok.csv"
    p.write_text("Date,Amount\n2026-01-01,-10\n", encoding="utf-8")
    assert guard.check_file_is_safe_to_read(p) is None


def test_is_onedrive_placeholder_is_false_on_non_windows(tmp_path):
    p = tmp_path / "ok.csv"
    p.write_text("data", encoding="utf-8")
    assert guard.is_onedrive_placeholder(p) is False


def test_check_files_safe_to_read_collects_all_errors(tmp_path):
    ok = tmp_path / "ok.csv"
    ok.write_text("data", encoding="utf-8")
    empty = tmp_path / "empty.csv"
    empty.write_text("", encoding="utf-8")
    errors = guard.check_files_safe_to_read([ok, empty, tmp_path / "missing.csv"])
    assert len(errors) == 2
