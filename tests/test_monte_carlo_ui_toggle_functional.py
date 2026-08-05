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
    assert "Simple — Quick Vectorized" in text
    assert "Complex — Advanced Exact Scalar" in text

    # A7 (Wave 3 item 3.12): the twelve near-identical _ensure_*_ui_plan_data_rows
    # functions were replaced by one declarative PLAN_DATA_BACKFILL_ENTRIES
    # table over src/plan_data_backfill.py's batched engine - assert the row
    # set is actually wired into that table (behavioral coverage of the
    # backfill itself lives in tests/test_plan_data_backfill.py).
    import src.server.app_core as ac
    assert any(
        entry.rows is ac.MONTE_CARLO_UI_PLAN_DATA_ROWS
        for entry in ac.PLAN_DATA_BACKFILL_ENTRIES
    )


def test_engine_accepts_only_canonical_monte_carlo_modes():
    text = (ROOT / "src" / "data_io.py").read_text(encoding="utf-8")
    assert "'advanced_exact_scalar': 'exact_scalar'" in text
    assert "'quick_vectorized': 'vectorized'" in text
    assert "'simple': 'vectorized'" not in text
    assert "'complex': 'exact_scalar'" not in text
