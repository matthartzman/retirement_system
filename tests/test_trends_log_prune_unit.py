"""prune_entries: dry run changes nothing; apply drops the date range, keeps a .bak."""
from __future__ import annotations

from financial_trends_reporter.trends_log import append_or_replace_entry, prune_entries, read_history


def _log(tmp_path):
    p = tmp_path / "log.jsonl"
    for d in ("2026-10-07", "2026-10-08", "2026-10-09", "2026-10-12"):
        append_or_replace_entry(p, {"as_of_date": d})
    return p


def test_dry_run_changes_nothing(tmp_path):
    p = _log(tmp_path)
    assert prune_entries(p, "2026-10-08", "2026-10-09") == ["2026-10-08", "2026-10-09"]
    assert len(read_history(p)) == 4
    assert not p.with_name(p.name + ".bak").exists()


def test_apply_removes_range_and_keeps_backup(tmp_path):
    p = _log(tmp_path)
    prune_entries(p, "2026-10-08", "2026-10-12", dry_run=False)
    assert [e["as_of_date"] for e in read_history(p)] == ["2026-10-07"]
    assert len(p.with_name(p.name + ".bak").read_text().splitlines()) == 4


def test_single_date_and_no_match(tmp_path):
    p = _log(tmp_path)
    assert prune_entries(p, "2026-10-09", dry_run=False) == ["2026-10-09"]
    assert prune_entries(p, "2027-01-01", dry_run=False) == []
