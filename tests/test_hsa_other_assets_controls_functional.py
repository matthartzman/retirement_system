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
    assert "HSA withdrawal policy" in data_io
    assert "hsa_withdrawal_mode" in data_io
    assert "c['hsa_win_start'], c['hsa_win_end'] = c['hsa_win_end'], c['hsa_win_start']" in data_io
    engine = read("src/projection_stages/deterministic_engine.py")
    assert "withdraw_hsa_window(c, bal, year" in engine
    assert "row['hsa_wd']" in engine
