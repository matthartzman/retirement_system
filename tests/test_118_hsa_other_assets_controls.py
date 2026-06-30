from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_hsa_withdrawal_timing_lives_on_other_assets_page():
    js = read("frontend/js/dashboard.js")
    assert "function renderHsaPolicyOnOtherAssets" in js
    assert "HSA Withdrawal Timing" in js
    assert "choose how the HSA is used in Cash Flow" in js
    assert "case 'assets_special':return ((sec==='Other Assets'&&sub.startsWith('other_asset'))||(sec==='HSA Policy'&&sub!=='window')" in js
    assert "case 'withdrawal_strategy':return (sec==='Withdrawal Policy'&&sub!=='roth_conversion');" in js
    assert "HSA withdrawal timing is controlled on Other → Other assets" in js


def test_hsa_window_is_normalized_before_cashflow_projection():
    data_io = read("src/data_io.py")
    assert "HSA withdrawal policy" in data_io
    assert "hsa_withdrawal_mode" in data_io
    assert "c['hsa_win_start'], c['hsa_win_end'] = c['hsa_win_end'], c['hsa_win_start']" in data_io
    engine = read("src/projection_stages/deterministic_engine.py")
    assert "withdraw_hsa_window(c, bal, year" in engine
    assert "row['hsa_wd']" in engine
