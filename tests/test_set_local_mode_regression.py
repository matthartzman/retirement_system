"""Regression: tools/set_local_mode.py writes the local-mode settings to app.db (WP8.1)."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load():
    spec = importlib.util.spec_from_file_location("set_local_mode", ROOT / "tools" / "set_local_mode.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_reset_writes_local_mode_settings_and_keeps_others(tmp_path):
    from src.system_config import load_system_config, set_system_settings, stored_settings, system_setting

    app_db = tmp_path / "app.db"
    set_system_settings({("System Configuration", "Dashboard", "port"): "6060",
                         ("System Configuration", "Downloads", "filename_root"): "Mine"}, app_db)
    assert _load().main(app_db) == 0
    data = load_system_config(app_db)
    assert system_setting(data, "Dashboard", "port") == "5050"
    assert system_setting(data, "Security", "session_cookie_secure") == "NO"
    assert system_setting(data, "Downloads", "filename_root") == "Mine"
    # values equal to the built-in defaults are unset, not stored
    assert ("System Configuration", "Dashboard", "port") not in stored_settings(app_db)


def test_no_system_config_csv_is_written(tmp_path):
    _load().main(tmp_path / "app.db")
    assert sorted(p.name for p in tmp_path.iterdir() if not p.name.startswith("app.db")) == []
