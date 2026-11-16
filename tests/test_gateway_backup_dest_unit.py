"""The one server-side path an admin sets: where backups may and may not go."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.gateway import backup_dest as bd

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _no_sync_env(monkeypatch, tmp_path):
    for name in bd.SYNC_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(bd, "profiles_root", lambda: tmp_path / "Users")


def test_accepts_a_plain_local_folder_and_creates_nothing(tmp_path):
    dest = bd.validate_backup_destination(tmp_path / "srv" / "backups")
    assert dest == Path(os.path.realpath(tmp_path / "srv" / "backups"))
    assert not dest.exists()


@pytest.mark.parametrize("bad", ["", "relative\\folder", "\\\\server\\share\\b", "//server/share/b"])
def test_refuses_empty_relative_and_network_paths(bad):
    with pytest.raises(bd.BackupDestinationError):
        bd.validate_backup_destination(bad)


def test_refuses_dotdot_and_drive_root(tmp_path):
    with pytest.raises(bd.BackupDestinationError):
        bd.validate_backup_destination(str(tmp_path / "a" / ".." / "b"))
    with pytest.raises(bd.BackupDestinationError):
        bd.validate_backup_destination(Path(tmp_path.anchor))


@pytest.mark.parametrize("folder", ["OneDrive", "OneDrive - Contoso", "Dropbox", "Google Drive", "iCloudDrive", "Box Sync"])
def test_refuses_synced_folder_names(tmp_path, folder):
    with pytest.raises(bd.BackupDestinationError, match="synced"):
        bd.validate_backup_destination(tmp_path / folder / "backups")


def test_refuses_inside_a_synced_root_from_the_environment(tmp_path, monkeypatch):
    root = tmp_path / "cloud"
    root.mkdir()
    monkeypatch.setenv("OneDrive", str(root))
    with pytest.raises(bd.BackupDestinationError, match="synced"):
        bd.validate_backup_destination(root / "deep" / "b")


def test_refuses_profile_data_install_and_key_folders(tmp_path):
    data, install, dest = tmp_path / "data", tmp_path / "app", tmp_path / "bk"
    with pytest.raises(bd.BackupDestinationError, match="profile"):
        bd.validate_backup_destination(tmp_path / "Users" / "me" / "bk")
    with pytest.raises(bd.BackupDestinationError, match="data"):
        bd.validate_backup_destination(data / "users" / "bk", data_root=data)
    with pytest.raises(bd.BackupDestinationError, match="data"):
        bd.validate_backup_destination(tmp_path, data_root=data)  # a parent of the data folder
    with pytest.raises(bd.BackupDestinationError, match="install"):
        bd.validate_backup_destination(install / "b", install_dir=install)
    with pytest.raises(bd.BackupDestinationError, match="key"):
        bd.validate_backup_destination(dest, key_file=dest / "backup.key")


def test_refuses_a_file_and_a_link_into_a_forbidden_tree(tmp_path):
    f = tmp_path / "afile"
    f.write_text("x")
    with pytest.raises(bd.BackupDestinationError, match="not a folder"):
        bd.validate_backup_destination(f)
    data = tmp_path / "data"
    data.mkdir()
    link = tmp_path / "link"
    try:
        os.symlink(data, link, target_is_directory=True)
    except (OSError, NotImplementedError):
        return  # no symlink privilege here: the resolved-path rule is covered by the cases above
    with pytest.raises(bd.BackupDestinationError, match="data"):
        bd.validate_backup_destination(link / "bk", data_root=data)


def test_key_location_rules(tmp_path):
    bk, data = tmp_path / "bk", tmp_path / "data"
    assert bd.validate_key_location(tmp_path / "keys" / "backup.key", backup_dir=bk, data_root=data)
    with pytest.raises(bd.BackupDestinationError):
        bd.validate_key_location(bk / "backup.key", backup_dir=bk)
    with pytest.raises(bd.BackupDestinationError):
        bd.validate_key_location(data / "backup.key", backup_dir=bk, data_root=data)
    with pytest.raises(bd.BackupDestinationError):
        bd.validate_key_location(tmp_path / "OneDrive" / "backup.key", backup_dir=bk)
    with pytest.raises(bd.BackupDestinationError):
        bd.validate_key_location(Path("backup.key"), backup_dir=bk)


def test_default_destination_is_under_programdata(monkeypatch):
    monkeypatch.setenv("ProgramData", r"C:\ProgramData")
    assert bd.default_backup_dir().parts[-2:] == ("RetirementPlannerGateway", "backups")
