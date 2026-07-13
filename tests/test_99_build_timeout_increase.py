from pathlib import Path
import importlib
import os

ROOT = Path(__file__).resolve().parents[1]


def test_system_config_default_build_timeout_is_30_minutes():
    text = (ROOT / 'system_config.csv').read_text(encoding='utf-8')
    assert 'System Configuration,Runtime,max_build_seconds,1800' in text


def test_runtime_config_defaults_and_env_override(monkeypatch):
    from src import runtime_config
    cfg = runtime_config.load_runtime_config(ROOT / 'system_config.csv')
    assert cfg.max_build_seconds == 1800
    monkeypatch.setenv('RETIREMENT_SYSTEM_MAX_BUILD_SECONDS', '2400')
    cfg = runtime_config.load_runtime_config(ROOT / 'system_config.csv')
    assert cfg.max_build_seconds == 2400


def test_dashboard_polling_outlasts_default_server_timeout():
    js = (ROOT / 'frontend' / 'js' / 'dashboard.js').read_text(encoding='utf-8')
    assert 'for (let i = 0; i < 1600; i++)' in js
    assert 'Build progress polling timed out after about 40 minutes' in js
