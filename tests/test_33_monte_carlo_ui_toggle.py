from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_user_ui_has_simple_complex_monte_carlo_toggle():
    js = (ROOT / "frontend" / "js" / "dashboard.js").read_text(encoding="utf-8")
    css = (ROOT / "frontend" / "css" / "dashboard.css").read_text(encoding="utf-8")
    index = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    assert "function mcEngineToggleHtml" in js
    assert "setMcEngineMode('quick_vectorized')" in js
    assert "setMcEngineMode('advanced_exact_scalar')" in js
    assert "Simple" in js and "Complex" in js
    assert "mc-mode-toggle" in css
    assert "js/dashboard.js?v=" in index


def test_monte_carlo_engine_row_is_backfilled_into_plan_data():
    text = (ROOT / "src" / "server" / "app_core.py").read_text(encoding="utf-8")
    assert "MONTE_CARLO_UI_PLAN_DATA_ROWS" in text
    assert "\"Model Constants\", \"Monte Carlo\", \"mc_engine_mode\"" in text
    assert "mc_engine_mode" in text
    assert "_ensure_monte_carlo_ui_plan_data_rows()" in text
    assert "Simple — Quick Vectorized" in text
    assert "Complex — Advanced Exact Scalar" in text


def test_engine_accepts_only_canonical_monte_carlo_modes():
    text = (ROOT / "src" / "data_io.py").read_text(encoding="utf-8")
    assert "'advanced_exact_scalar': 'exact_scalar'" in text
    assert "'quick_vectorized': 'vectorized'" in text
    assert "'simple': 'vectorized'" not in text
    assert "'complex': 'exact_scalar'" not in text
