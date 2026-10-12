from pathlib import Path


def test_workbook_filename_root_defaults_and_reads_configured_value():
    from src.system_config import workbook_filename_root

    assert workbook_filename_root({}) == "Retirement Workbook"
    configured = {"System Configuration": {"Downloads": {"filename_root": "My Plan"}}}
    assert workbook_filename_root(configured) == "My Plan"

    blank = {"System Configuration": {"Downloads": {"filename_root": "   "}}}
    assert workbook_filename_root(blank) == "Retirement Workbook"


def test_workbook_desktop_download_folder_defaults_to_blank():
    from src.system_config import workbook_desktop_download_folder

    assert workbook_desktop_download_folder({}) == ""
    configured = {"System Configuration": {"Downloads": {"desktop_download_folder": "C:/Users/me/Downloads"}}}
    assert workbook_desktop_download_folder(configured) == "C:/Users/me/Downloads"


def test_upsert_system_setting_inserts_new_row(tmp_path):
    from src.system_config import upsert_system_setting, load_system_config, workbook_filename_root

    p = tmp_path / "app.db"
    upsert_system_setting(p, "Downloads", "filename_root", "Smith Plan", units="text", notes="Root name for downloaded workbook files.")
    assert p.exists()
    data = load_system_config(p)
    assert workbook_filename_root(data) == "Smith Plan"


def test_upsert_system_setting_updates_existing_row_without_disturbing_others(tmp_path):
    from src.system_config import setting_key, stored_settings, upsert_system_setting, load_system_config, system_setting

    p = tmp_path / "app.db"
    upsert_system_setting(p, "Downloads", "filename_root", "Old Name")
    upsert_system_setting(p, "Runtime", "app_mode", "LOCAL")
    upsert_system_setting(p, "Downloads", "filename_root", "New Name")
    data = load_system_config(p)
    assert system_setting(data, "Downloads", "filename_root") == "New Name"
    assert system_setting(data, "Runtime", "app_mode") == "LOCAL"
    # One settings key per row; a value equal to its default is not stored.
    assert stored_settings(p) == {("System Configuration", "Downloads", "filename_root"): "New Name"}
    assert setting_key("System Configuration", "Downloads", "filename_root") == "System Configuration|Downloads|filename_root"


def test_upsert_system_setting_creates_app_db_if_missing(tmp_path):
    from src.system_config import upsert_system_setting, load_system_config, workbook_desktop_download_folder

    p = tmp_path / "does_not_exist_yet" / "app.db"
    upsert_system_setting(p, "Downloads", "desktop_download_folder", "D:/Reports")
    assert workbook_desktop_download_folder(load_system_config(p)) == "D:/Reports"


def test_fresh_install_reads_defaults_without_creating_app_db(tmp_path):
    from src.system_config import SYSTEM_DEFAULTS, load_system_config, setting

    p = tmp_path / "app.db"
    data = load_system_config(p)
    assert not p.exists()
    for sec, sub, lbl, value, _u, _n in SYSTEM_DEFAULTS:
        assert setting(data, sec, sub, lbl) == value


def test_split_setting_key_keeps_a_separator_inside_the_subsection():
    from src.system_config import setting_key, split_setting_key

    assert split_setting_key(setting_key("A", "x|y", "z")) == ("A", "x|y", "z")
    assert split_setting_key("prefs.theme") is None
