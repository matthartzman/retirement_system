from pathlib import Path

from conftest import dashboard_js_sources

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_hsa_withdrawal_timing_lives_on_other_assets_page():
    js = dashboard_js_sources()
    assert "function renderHsaPolicyOnOtherAssets" in js
    # #213: consolidated into one collapsible "HSA" section (was up to 4
    # separate <details>); withdrawal timing is the first sub-block inside it.
    assert "<details><summary>HSA</summary>" in js
    assert "choose how the HSA is used in Cash Flow" in js
    # #213: start year must sort before end year (was reversed by the
    # generic dependency sort's alphabetical tie-break, "end" < "start").
    assert 'norm(r.label) === "hsa_withdrawal_start_year"\n        ? 0' in js
    assert 'case "assets_special":\n        return (\n          (sec === "Other Assets" && sub.startsWith("other_asset")) ||\n          (sec === "HSA Policy" && sub !== "window")' in js
    assert 'case "withdrawal_strategy":\n        return sec === "Withdrawal Policy" && sub !== "roth_conversion";' in js
    assert "HSA withdrawal timing is controlled on Other → Other assets" in js


def test_hsa_window_is_normalized_before_cashflow_projection():
    data_io = read("src/data_io.py")
    # Ticket 312: the HSA Policy scalar parsing (mode, window, and the
    # window-swap normalization) moved from parse_client's own body into
    # src/parsing/hsa_policy.py's parse_hsa_policy(); data_io.py re-exports
    # it and merges its result into c via parse_hsa_policy(data, ...), so
    # the field/logic checks themselves live against the new module.
    assert "parse_hsa_policy" in data_io
    hsa_policy = read("src/parsing/hsa_policy.py")
    assert "hsa_withdrawal_mode" in hsa_policy
    assert "hsa_win_start, hsa_win_end = hsa_win_end, hsa_win_start" in hsa_policy
    # Ticket 3.10: this logic moved into withdrawal_cascade_hsa_priority_draws.py
    # (design doc Stage 10 addendum, sub-stages #1-#2) when
    # deterministic_engine.py's inline withdrawal cascade was decomposed
    # into stage modules.
    engine = read("src/projection_stages/withdrawal_cascade_hsa_priority_draws.py")
    assert "withdraw_hsa_window(c, bal, year" in engine
    assert "row['hsa_wd']" in engine
