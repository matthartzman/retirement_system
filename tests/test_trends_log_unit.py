"""Ticket 306: the append-only JSONL trend log overwrites same-date entries
(safe re-run/retry) rather than duplicating them, and survives a corrupted
line without losing the rest of the history.
"""
from __future__ import annotations

from financial_trends_reporter.trends_log import append_or_replace_entry, read_history


def test_append_new_entries_accumulate(tmp_path):
    log_path = tmp_path / "log.jsonl"
    append_or_replace_entry(log_path, {"as_of_date": "2026-01-01", "net_worth": {"total": 100}})
    append_or_replace_entry(log_path, {"as_of_date": "2026-01-02", "net_worth": {"total": 101}})
    history = read_history(log_path)
    assert [e["as_of_date"] for e in history] == ["2026-01-01", "2026-01-02"]


def test_same_date_rerun_overwrites_not_duplicates(tmp_path):
    log_path = tmp_path / "log.jsonl"
    append_or_replace_entry(log_path, {"as_of_date": "2026-01-01", "net_worth": {"total": 100}})
    append_or_replace_entry(log_path, {"as_of_date": "2026-01-01", "net_worth": {"total": 105}})
    history = read_history(log_path)
    assert len(history) == 1
    assert history[0]["net_worth"]["total"] == 105


def test_history_is_sorted_by_date_regardless_of_write_order(tmp_path):
    log_path = tmp_path / "log.jsonl"
    append_or_replace_entry(log_path, {"as_of_date": "2026-01-05"})
    append_or_replace_entry(log_path, {"as_of_date": "2026-01-01"})
    history = read_history(log_path)
    assert [e["as_of_date"] for e in history] == ["2026-01-01", "2026-01-05"]


def test_missing_log_file_reads_as_empty_history(tmp_path):
    assert read_history(tmp_path / "does_not_exist.jsonl") == []


def test_entry_without_as_of_date_is_rejected(tmp_path):
    import pytest

    with pytest.raises(ValueError):
        append_or_replace_entry(tmp_path / "log.jsonl", {"net_worth": {"total": 1}})


def test_a_corrupted_line_does_not_lose_the_rest_of_the_history(tmp_path):
    log_path = tmp_path / "log.jsonl"
    log_path.write_text(
        '{"as_of_date": "2026-01-01", "net_worth": {"total": 100}}\n'
        "not valid json\n"
        '{"as_of_date": "2026-01-02", "net_worth": {"total": 101}}\n',
        encoding="utf-8",
    )
    history = read_history(log_path)
    assert [e["as_of_date"] for e in history] == ["2026-01-01", "2026-01-02"]
