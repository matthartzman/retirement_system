"""WI-203 (QA-005/FIN-010): trends log write side -- atomic, quarantines bad lines."""
import json

from financial_trends_reporter import trends_log
from financial_trends_reporter.trends_log import append_or_replace_entry, read_history, rejected_path


def test_two_days_same_through_date_keep_two_lines(tmp_path):
    log = tmp_path / "data" / "log.jsonl"
    for day in ("2026-01-19", "2026-01-20"):
        append_or_replace_entry(log, {"as_of_date": day, "data_through_date": "2026-01-15", "net_worth": {"total": 1}})
    hist = read_history(log)
    assert [e["as_of_date"] for e in hist] == ["2026-01-19", "2026-01-20"]
    assert {e["data_through_date"] for e in hist} == {"2026-01-15"}


def test_bad_line_is_quarantined_not_dropped_on_append(tmp_path):
    log = tmp_path / "log.jsonl"
    log.write_text('{"as_of_date": "2026-01-01"}\n{"as_of_date": "2026-01-0\n[1, 2]\n', encoding="utf-8")
    append_or_replace_entry(log, {"as_of_date": "2026-01-02"})
    assert [e["as_of_date"] for e in read_history(log)] == ["2026-01-01", "2026-01-02"]
    rejected = rejected_path(log).read_text(encoding="utf-8").splitlines()
    assert rejected == ['{"as_of_date": "2026-01-0', "[1, 2]"]
    # a further append does not re-quarantine or lose anything
    append_or_replace_entry(log, {"as_of_date": "2026-01-03"})
    assert rejected_path(log).read_text(encoding="utf-8").splitlines() == rejected


def test_write_is_atomic_and_failure_keeps_prior_file(tmp_path, monkeypatch):
    log = tmp_path / "log.jsonl"
    append_or_replace_entry(log, {"as_of_date": "2026-01-01"})
    calls = []
    real = trends_log.write_text_atomic

    def spy(*a, **k):
        calls.append(a)
        return real(*a, **k)

    monkeypatch.setattr(trends_log, "write_text_atomic", spy)
    append_or_replace_entry(log, {"as_of_date": "2026-01-02"})
    assert calls, "append must go through write_text_atomic"

    def boom(*a, **k):
        raise OSError("disk")

    monkeypatch.setattr(trends_log, "write_text_atomic", boom)
    try:
        append_or_replace_entry(log, {"as_of_date": "2026-01-03"})
    except OSError:
        pass
    lines = log.read_text(encoding="utf-8").splitlines()
    assert [json.loads(x)["as_of_date"] for x in lines] == ["2026-01-01", "2026-01-02"]
