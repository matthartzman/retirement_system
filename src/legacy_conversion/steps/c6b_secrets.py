"""Conversion step C6b: ``local_state/secrets.local.json`` -> the OS credential store.

Calls ``secrets_store.migrate_legacy_secrets_file(path, delete_file=...)`` (WP8.2): every key is
written, read back and compared. The plain file is deleted only when the caller passes
``delete=True`` (the converter's ``extra["delete_legacy_secrets"]``, set after the user confirmed
in the first-launch UI) AND every key verified; otherwise it stays.

No credential store (``SecretStoreUnavailable``): the conversion does not fail. The step reports
``status: converted_with_warning`` (``warning: secret_store_unavailable``), leaves the plain
file untouched and does NOT stamp its marker, so a later conversion run (which
``convert_workspace`` starts while the file exists and the marker is missing) tries again. The
app itself has no plain-text fallback (WP8.2): pricing runs without the key and shows its
warning until a credential store is available.

Marker: app.db setting ``legacy_conversion.c6b`` (secrets belong to the install, not the plan);
with the marker set the step runs again only to delete a file the user has since confirmed.
Key names only are reported, never values. Dry run reads nothing from the keyring and writes
nothing; it reports how many keys the file holds.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

STEP_ID = "C6b"
MARKER_KEY = "legacy_conversion.c6b"
LEGACY_FILE = Path("local_state") / "secrets.local.json"


@dataclass
class C6bReport:
    step: str
    skipped: bool
    found: bool = False
    keys: int = 0
    migrated: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    deleted: bool = False
    warning: str = ""

    def as_dict(self) -> dict[str, Any]:
        out = {"step": self.step, "skipped": self.skipped, "found": self.found, "keys": self.keys,
               "migrated": list(self.migrated), "failed": list(self.failed), "deleted": self.deleted}
        if self.warning:
            out["warning"] = self.warning
            out["status"] = "converted_with_warning"
        return out


def run(workspace: Path, app_db: Path, *, delete: bool = False, dry_run: bool = False) -> C6bReport:
    from ... import secrets_store  # noqa: PLC0415
    from ...app_state import open_app_store  # noqa: PLC0415

    path = Path(workspace) / LEGACY_FILE
    if Path(app_db).is_file():
        with open_app_store(app_db, readonly=True) as app:
            # Done before: run again only to delete the file the user has now confirmed.
            if app.get_setting(MARKER_KEY) is not None and not (delete and path.is_file()):
                return C6bReport(STEP_ID, skipped=True)
    if not path.is_file():
        return C6bReport(STEP_ID, skipped=True)
    rep = C6bReport(STEP_ID, skipped=False, found=True)
    if dry_run:
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            rep.keys = len(data) if isinstance(data, dict) else 0
        except (OSError, ValueError):
            rep.warning = "legacy_secrets_unreadable"
        return rep
    try:
        res = secrets_store.migrate_legacy_secrets_file(path, delete_file=bool(delete))
    except secrets_store.SecretStoreUnavailable:
        rep.warning = "secret_store_unavailable"
        return rep
    rep.migrated, rep.failed = list(res.get("migrated", [])), list(res.get("failed", []))
    rep.keys = len(rep.migrated) + len(rep.failed)
    rep.deleted = bool(res.get("deleted"))
    if res.get("error"):
        rep.warning = "legacy_secrets_unreadable"
        return rep
    if rep.failed:
        rep.warning = "some_keys_not_verified"
        return rep
    with open_app_store(app_db) as app:
        app.set_setting(MARKER_KEY, f"keys={rep.keys} deleted={int(rep.deleted)}")
    return rep
