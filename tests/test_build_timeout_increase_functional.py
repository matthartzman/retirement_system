from pathlib import Path
import importlib
import os

from _decomp_dashboard import dashboard_js_text

ROOT = Path(__file__).resolve().parents[1]


def test_system_config_default_build_timeout_is_30_minutes():
    from src.system_config import SYSTEM_DEFAULTS
    assert ('System Configuration', 'Runtime', 'max_build_seconds', '1800') in {r[:4] for r in SYSTEM_DEFAULTS}


def test_runtime_config_defaults_and_env_override(monkeypatch, tmp_path):
    from src import runtime_config
    app_db = tmp_path / 'app.db'  # missing: a fresh install reads the built-in defaults
    cfg = runtime_config.load_runtime_config(app_db)
    assert cfg.max_build_seconds == 1800
    monkeypatch.setenv('RETIREMENT_SYSTEM_MAX_BUILD_SECONDS', '2400')
    cfg = runtime_config.load_runtime_config(app_db)
    assert cfg.max_build_seconds == 2400


def test_dashboard_polling_outlasts_default_server_timeout():
    js = dashboard_js_text()
    assert 'for (let i = 0; i < 1600; i++)' in js
    assert 'Build progress polling timed out after about 40 minutes' in js
