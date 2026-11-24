"""F-03: the trend log is HMAC-signed per line with a signed head record; tampering, truncation and unsigned
injection are detected, quarantined and reported (never silently dropped); legacy and restored logs still read."""
from __future__ import annotations

import json
from pathlib import Path

from financial_trends_reporter import trends_log as tl


def _entry(day: str, nw: float = 1000.0) -> dict:
    return {"as_of_date": day, "net_worth": {"total": nw}}


def _fill(path: Path, days=("2026-01-01", "2026-01-02", "2026-01-03")) -> None:
    for i, d in enumerate(days):
        tl.append_or_replace_entry(path, _entry(d, 1000.0 + i))


def test_every_line_is_signed_and_reads_back_unchanged(tmp_path):
    log = tmp_path / "data" / "log.jsonl"
    _fill(log)
    raw = [json.loads(x) for x in log.read_text().splitlines()]
    assert all(tl.MAC_FIELD in r for r in raw)
    assert tl.read_history(log) == [_entry("2026-01-01", 1000.0), _entry("2026-01-02", 1001.0), _entry("2026-01-03", 1002.0)]
    assert tl.verify_log(log)["status"] == "ok" and tl.head_path(log).exists()


def test_key_is_owner_only_and_beside_the_log(tmp_path):
    log = tmp_path / "log.jsonl"
    _fill(log)
    key = tmp_path / "log.jsonl.key"
    assert key.exists() and (key.stat().st_mode & 0o077) == 0 or __import__("sys").platform == "win32"


def test_an_edited_balance_is_detected_quarantined_and_reported(tmp_path):
    log = tmp_path / "log.jsonl"
    _fill(log)
    lines = log.read_text().splitlines()
    forged = json.loads(lines[1])
    forged["net_worth"]["total"] = 999999.0  # tamper but keep the old signature
    lines[1] = json.dumps(forged, sort_keys=True)
    log.write_text("\n".join(lines) + "\n")
    got = tl.read_history(log)
    assert [e["as_of_date"] for e in got] == ["2026-01-01", "2026-01-03"]  # the forged day is not trusted
    summary = tl.integrity_summary(log)
    assert summary["status"] == "damaged" and summary["problems"]
    tl.append_or_replace_entry(log, _entry("2026-01-04"))  # the next write quarantines it
    assert "999999" in tl.rejected_path(log).read_text()
    assert tl.integrity_summary(log)["quarantined_ever"] >= 1
    assert tl.verify_log(log)["status"] == "ok"  # clean again, and the evidence stays in the sidecar
    assert json.loads(tl.integrity_path(log).read_text())


def test_truncation_and_deleted_lines_are_reported(tmp_path):
    log = tmp_path / "log.jsonl"
    _fill(log)
    lines = log.read_text().splitlines()
    log.write_text("\n".join(lines[:-1]) + "\n")  # the newest day vanishes
    report = tl.verify_log(log)
    assert report["status"] == "damaged" and any("missing or altered" in p for p in report["problems"])
    assert len(report["entries"]) == 2  # what remains is still individually valid


def test_unsigned_injection_into_a_signed_log_is_rejected(tmp_path):
    log = tmp_path / "log.jsonl"
    _fill(log)
    with log.open("a") as fh:
        fh.write(json.dumps(_entry("2099-01-01", 1.0)) + "\n")  # no signature
    assert "2099-01-01" not in [e["as_of_date"] for e in tl.read_history(log)]
    assert tl.verify_log(log)["bad"]


def test_a_legacy_unsigned_log_still_reads_and_is_signed_by_the_next_write(tmp_path):
    log = tmp_path / "log.jsonl"
    log.write_text(json.dumps(_entry("2025-12-30")) + "\n" + json.dumps(_entry("2025-12-31")) + "\n")
    assert tl.verify_log(log)["status"] == "legacy" and len(tl.read_history(log)) == 2
    tl.append_or_replace_entry(log, _entry("2026-01-01"))
    assert tl.verify_log(log)["status"] == "ok" and len(tl.read_history(log)) == 3


def test_a_log_restored_from_backup_without_its_key_is_accepted_once(tmp_path):
    src = tmp_path / "a" / "log.jsonl"
    _fill(src)
    dst = tmp_path / "b" / "log.jsonl"
    dst.parent.mkdir()
    dst.write_text(src.read_text())  # a backup carries the log, not the key or the head
    assert len(tl.read_history(dst)) == 3
    tl.append_or_replace_entry(dst, _entry("2026-01-04"))
    assert tl.verify_log(dst)["status"] == "ok" and len(tl.read_history(dst)) == 4


def test_a_bad_line_is_never_silently_lost(tmp_path):
    log = tmp_path / "log.jsonl"
    _fill(log)
    with log.open("a") as fh:
        fh.write("{this is not json\n")
    tl.append_or_replace_entry(log, _entry("2026-01-04"))
    assert "{this is not json" in tl.rejected_path(log).read_text()


def test_dry_run_prune_changes_nothing(tmp_path):
    log = tmp_path / "log.jsonl"
    _fill(log)
    lines = log.read_text().splitlines()
    log.write_text("\n".join(lines[:-1]) + "\n")
    before = (log.read_text(), tl.head_path(log).read_text(), tl.integrity_path(log).exists())
    assert tl.prune_entries(log, "2026-01-01", dry_run=True) == ["2026-01-01"]
    assert (log.read_text(), tl.head_path(log).read_text(), tl.integrity_path(log).exists()) == before


def test_prune_keeps_the_log_signed(tmp_path):
    log = tmp_path / "log.jsonl"
    _fill(log)
    tl.prune_entries(log, "2026-01-02", dry_run=False)
    assert tl.verify_log(log)["status"] == "ok" and [e["as_of_date"] for e in tl.read_history(log)] == ["2026-01-01", "2026-01-03"]
