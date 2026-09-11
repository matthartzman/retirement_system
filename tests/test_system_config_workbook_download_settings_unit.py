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

    p = tmp_path / "system_config.csv"
    upsert_system_setting(p, "Downloads", "filename_root", "Retirement Workbook", units="text", notes="Root name for downloaded workbook files.")
    assert p.exists()
    data = load_system_config(p)
    assert workbook_filename_root(data) == "Retirement Workbook"


def test_upsert_system_setting_updates_existing_row_without_disturbing_others(tmp_path):
    from src.system_config import upsert_system_setting, load_system_config, system_setting

    p = tmp_path / "system_config.csv"
    p.write_text(
        "section,subsection,label,value,units,notes\n"
        "System Configuration,Downloads,filename_root,Retirement Workbook,text,root name\n"
        "System Configuration,Runtime,app_mode,LOCAL,choice,mode\n",
        encoding="utf-8",
    )
    upsert_system_setting(p, "Downloads", "filename_root", "New Name")
    data = load_system_config(p)
    assert system_setting(data, "Downloads", "filename_root") == "New Name"
    # Unrelated row survives untouched.
    assert system_setting(data, "Runtime", "app_mode") == "LOCAL"
    # Only one Downloads/filename_root row exists after the update.
    lines = p.read_text(encoding="utf-8").strip().splitlines()
    assert sum(1 for ln in lines if "filename_root" in ln) == 1


def test_upsert_system_setting_creates_file_with_header_if_missing(tmp_path):
    from src.system_config import upsert_system_setting

    p = tmp_path / "does_not_exist_yet" / "system_config.csv"
    upsert_system_setting(p, "Downloads", "desktop_download_folder", "D:/Reports")
    lines = p.read_text(encoding="utf-8").strip().splitlines()
    assert lines[0] == "section,subsection,label,value,units,notes"
    assert "Downloads,desktop_download_folder,D:/Reports" in lines[1]
