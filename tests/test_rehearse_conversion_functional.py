"""WP4: tools/rehearse_conversion.py runs C3/C3b on a copy of a plan, read-only, and reports
counts and names only (never values), exiting 0 only on a full match."""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

import pytest

from tests.plan_fixture import fixture_dir

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("rehearse_conversion", ROOT / "tools" / "rehearse_conversion.py")
rehearse = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rehearse)


def _tree_hash(folder: Path) -> str:
    h = hashlib.sha256()
    for f in sorted(p for p in folder.rglob("*") if p.is_file()):
        h.update(f.name.encode())
        h.update(f.read_bytes())
    return h.hexdigest()


@pytest.mark.parametrize("fixture", ["sample_frozen", "demo"])
def test_fixture_plans_convert_and_match(fixture, tmp_path, capsys):
    out = tmp_path / "out"
    rc = rehearse.main([str(fixture_dir(fixture)), "--out", str(out), "--skip-engine"])
    text = capsys.readouterr().out
    assert rc == 0, text
    assert "[MATCH] sectioned data" in text and "[MATCH] engine config" in text
    assert "marker c3: present" in text and "RESULT: ALL MATCH" in text
    assert (out / "plan.rpx").is_file()


def test_originals_are_never_modified(tmp_path, capsys):
    src = tmp_path / "copy"
    src.mkdir()
    for f in fixture_dir("sample_frozen").iterdir():
        if f.is_file():
            (src / f.name).write_bytes(f.read_bytes())
    before = _tree_hash(src)
    assert rehearse.main([str(src), "--skip-engine"]) == 0
    capsys.readouterr()
    assert _tree_hash(src) == before


def test_report_never_prints_values(tmp_path, capsys):
    src = tmp_path / "copy"
    src.mkdir()
    for f in fixture_dir("sample_frozen").iterdir():
        if f.is_file():
            (src / f.name).write_bytes(f.read_bytes())
    sentinel = "SENTINEL_VALUE_XYZ"
    household = src / "client_household.csv"
    text = household.read_text(encoding="utf-8-sig")
    assert "Illinois" in text
    household.write_text(text.replace("Illinois", sentinel), encoding="utf-8")
    # The engine rejects the unknown state; its message quotes the value, the report must not.
    rc = rehearse.main([str(src), "--skip-engine", "--verbose-keys"])
    out = capsys.readouterr().out
    assert rc == 1 and "[ERROR]" in out and "ValueError" in out
    assert sentinel not in out


def test_diff_names_report_names_not_values(capsys):
    paths = rehearse._diff_names({"a": {"b": 1, "c": [1, 2]}}, {"a": {"b": 99, "c": [1, 3]}})
    assert rehearse._verdict("x", paths, verbose_keys=True) is False
    out = capsys.readouterr().out
    assert "99" not in out and "b" in out


def test_utf8_bom_in_custom_files_is_tolerated(tmp_path):
    p = tmp_path / "f.csv"
    p.write_bytes(b"\xef\xbb\xbfa,b\n1,2\n")
    assert rehearse._read_text(p).startswith("a,b")


def test_missing_plan_exits_with_a_message(tmp_path):
    with pytest.raises(SystemExit):
        rehearse.main([str(tmp_path)])
