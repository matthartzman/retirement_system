"""Verified backup of the legacy originals before a conversion activates anything (WP10.3).

``<workspace>/backups/pre_conversion_<ts>/``::

    files/<path relative to the workspace>   byte copies of the originals (a database outside
                                             the workspace, ``extra["legacy_db"]``, goes to
                                             ``files/external/<name>``)
    manifest.json                            {"format", "created_at", "verified",
                                              "secrets_included", "files": [{"path", "source",
                                              "size", "sha256"}]}

What is copied (:func:`backup_paths`): every original a conversion READS: ``input/``, a
``client_files/`` folder, ``system_config.csv``, the legacy database and its ``-wal``, an old
demo's ``*.before_demo`` backups, an old-format database the caller picked
(``extra["legacy_db"]``). ``local_state/secrets.local.json`` only when the user opted in
(``extra["backup_legacy_secrets"]``): a copy of it is another plain-text copy of the API keys.

Verification: each original is hashed as it is copied and must equal the hash taken when the
conversion started (else the original changed under us: abort); then every copy is read back and
its hash compared with the manifest. Only then is ``"verified": true`` written (atomically). A
backup that fails is left as it is (its manifest says ``"verified": false``) and the conversion
stops before anything becomes live.

Reuse: a later attempt (a conversion that was blocked and is run again) reuses the newest verified
backup whose manifest lists exactly the same originals byte for byte (re-reading its copies first),
so retries do not pile up copies.

Nothing here deletes or modifies an original. :func:`removal_candidates` only LISTS legacy files
this version no longer reads, for the UI to offer once the plan has run for a while.
"""
from __future__ import annotations

import json
import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from .runner import file_sha256

BACKUP_ROOT = "backups"
PREFIX = "pre_conversion_"
MANIFEST = "manifest.json"
FORMAT = "legacy_conversion.backup/v1"
REMOVABLE_AFTER_DAYS = 30


@dataclass
class BackupResult:
    path: Path | None = None
    files: int = 0
    bytes: int = 0
    verified: bool = False
    reused: bool = False
    secrets_included: bool = False
    error: str = ""

    def as_dict(self, workspace: Path | None = None) -> dict[str, Any]:
        shown: str | None = None
        if self.path is not None:
            shown = str(self.path)
            if workspace is not None:
                try:
                    shown = Path(self.path).relative_to(workspace).as_posix()
                except ValueError:
                    pass
        out = {"path": shown, "files": self.files, "bytes": self.bytes, "verified": self.verified,
               "reused": self.reused, "secrets_included": self.secrets_included}
        if self.error:
            out["error"] = self.error
        return out


def backup_paths(workspace: str | Path, extra: Mapping[str, Any] | None = None) -> list[Path]:
    """The originals a conversion reads (files or folders; missing ones are fine)."""
    from . import sources  # noqa: PLC0415

    ws = Path(workspace)
    extra = extra or {}
    db = sources.legacy_db_path(ws)
    seed = ws / (sources.PLAN_FILE_NAME + sources.BEFORE_DEMO)
    paths = [ws / "input", ws / "client_files", ws / "system_config.csv", seed, seed.with_name(seed.name + "-wal")]
    for p in (db, db.with_name(db.name + sources.BEFORE_DEMO)):
        paths += [p, p.with_name(p.name + "-wal")]
    paths += [db.parent / (n + sources.BEFORE_DEMO) for n in sources.ALL_FILES]
    if extra.get("legacy_db"):
        p = Path(extra["legacy_db"])
        paths += [p, p.with_name(p.name + "-wal")]
    if extra.get("backup_legacy_secrets"):
        paths.append(ws / "local_state" / "secrets.local.json")
    return paths


def _files(paths: Iterable[Path]) -> list[Path]:
    out: list[Path] = []
    for root in paths:
        root = Path(root)
        if root.is_file():
            out.append(root)
        elif root.is_dir():
            out += sorted(p for p in root.rglob("*") if p.is_file())
    return sorted(dict.fromkeys(out))


def _relative(workspace: Path, f: Path) -> str:
    try:
        return f.resolve().relative_to(workspace.resolve()).as_posix()
    except ValueError:
        return f"external/{f.name}"


def plan_backup(workspace: str | Path, extra: Mapping[str, Any] | None = None) -> dict[str, int]:
    """What a backup would hold (``{"files", "bytes"}``), for a dry run."""
    files = _files(backup_paths(workspace, extra))
    return {"files": len(files), "bytes": sum(f.stat().st_size for f in files)}


def _write_manifest(folder: Path, manifest: dict[str, Any]) -> None:
    tmp = folder / (MANIFEST + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
    os.replace(tmp, folder / MANIFEST)


def _read_manifest(folder: Path) -> dict[str, Any] | None:
    try:
        with open(folder / MANIFEST, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and data.get("format") == FORMAT else None


def _verify_copies(folder: Path, entries: list[dict[str, Any]]) -> int:
    """Number of copies whose size or hash differs from the manifest (a missing copy counts)."""
    bad = 0
    for e in entries:
        copy = folder / "files" / e["path"]
        if not copy.is_file() or copy.stat().st_size != e["size"] or file_sha256(copy) != e["sha256"]:
            bad += 1
    return bad


def _unique_folder(root: Path, stamp: str) -> Path:
    folder = root / f"{PREFIX}{stamp}"
    n = 1
    while folder.exists():
        folder = root / f"{PREFIX}{stamp}_{n}"
        n += 1
    return folder


def _reusable(root: Path, wanted: list[dict[str, Any]], secrets: bool) -> Path | None:
    if not root.is_dir():
        return None
    key = sorted((e["path"], e["size"], e["sha256"]) for e in wanted)
    for folder in sorted((p for p in root.glob(PREFIX + "*") if p.is_dir()), reverse=True):
        m = _read_manifest(folder)
        if not m or not m.get("verified") or bool(m.get("secrets_included")) != secrets:
            continue
        if sorted((e["path"], e["size"], e["sha256"]) for e in m.get("files", [])) == key:
            return folder
    return None


def ensure_backup(workspace: str | Path, snapshot: Mapping[str, tuple[int, str]], *,
                  extra: Mapping[str, Any] | None = None, stamp: str | None = None) -> BackupResult:
    """A verified backup of the originals (see the module docstring). ``snapshot`` is the
    conversion's ``{path: (size, sha256)}`` of its guard set taken at the start; an original
    that is not in it, or differs from it, aborts the backup (``error="source_changed"``)."""
    ws = Path(workspace)
    extra = extra or {}
    secrets = bool(extra.get("backup_legacy_secrets"))
    files = _files(backup_paths(ws, extra))
    wanted: list[dict[str, Any]] = []
    for f in files:
        size, digest = snapshot.get(str(f)) or (None, None)
        if digest is None:  # not in the guard set (the secrets file when deletion was asked)
            size, digest = f.stat().st_size, file_sha256(f)
        wanted.append({"path": _relative(ws, f), "source": str(f), "size": size, "sha256": digest})
    root = ws / BACKUP_ROOT
    res = BackupResult(files=len(wanted), bytes=sum(e["size"] for e in wanted), secrets_included=secrets)
    found = _reusable(root, wanted, secrets)
    if found is not None and _verify_copies(found, wanted) == 0:
        res.path, res.verified, res.reused = found, True, True
        return res
    folder = _unique_folder(root, stamp or time.strftime("%Y%m%d_%H%M%S"))
    res.path = folder
    manifest = {"format": FORMAT, "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "verified": False,
                "secrets_included": secrets, "files": [{k: e[k] for k in ("path", "size", "sha256")} for e in wanted]}
    try:
        (folder / "files").mkdir(parents=True)
        _write_manifest(folder, manifest)
        for e in wanted:
            dest = folder / "files" / e["path"]
            dest.parent.mkdir(parents=True, exist_ok=True)
            copy_file(Path(e["source"]), dest)
            if file_sha256(Path(e["source"])) != e["sha256"]:
                res.error = "source_changed"
                return res
        bad = _verify_copies(folder, wanted)
        if bad:
            res.error = f"hash_mismatch:{bad}"
            return res
        manifest["verified"] = True
        manifest["verified_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        _write_manifest(folder, manifest)
    except OSError as exc:
        res.error = f"copy_failed:{type(exc).__name__}"
        return res
    res.verified = True
    return res


def copy_file(src: Path, dest: Path) -> None:
    """Byte copy of one original (never opened for writing; modification time kept)."""
    shutil.copy2(src, dest)


def removal_candidates(workspace: str | Path, plan_backup_name: str | None = None) -> dict[str, Any]:
    """Legacy files this version no longer reads, offered for removal after
    ``REMOVABLE_AFTER_DAYS`` (the converter never removes anything): ``system_config.csv``, an
    old demo's ``*.before_demo`` backups and the plan copy kept by the conversion. ``input/`` and
    the legacy database are not offered (this version still reads them)."""
    from . import sources  # noqa: PLC0415

    ws = Path(workspace)
    db = sources.legacy_db_path(ws)
    seed = ws / (sources.PLAN_FILE_NAME + sources.BEFORE_DEMO)
    candidates = [ws / "system_config.csv", seed, seed.with_name(seed.name + "-wal"),
                  db.with_name(db.name + sources.BEFORE_DEMO), db.with_name(db.name + sources.BEFORE_DEMO + "-wal"),
                  *(db.parent / (n + sources.BEFORE_DEMO) for n in sources.ALL_FILES)]
    if plan_backup_name:
        candidates.append(ws / plan_backup_name)
    paths = [_relative(ws, p) for p in candidates if p.is_file()]
    return {"after_days": REMOVABLE_AFTER_DAYS, "paths": paths} if paths else {}
