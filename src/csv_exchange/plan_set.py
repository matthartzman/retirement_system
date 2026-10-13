"""Plan-set import / export (design F section 6, P7.2 / WP9.2).

``export_plan_set(store)`` returns a zip (bytes) holding the plan CSV set (one file per
``PLAN_CSV_FILES`` part, the inverse of the ``plan_csv`` parse), the flat plan datasets
(holdings, YTD, spending set, liabilities ...) and a ``manifest.json``.
``import_plan_set(store, zip bytes | {name: text})`` is the other direction: it reads the
files (legacy names accepted: the part files, ``FLAT_DATASET_FILES`` names, Monarch outbox
names, any folder prefix, any case), previews every dataset with ``core.preview`` and commits
them all in ONE transaction with ``core.commit``. Zip I/O is in memory only.
"""
from __future__ import annotations

import csv
import io
import json
import posixpath
import zipfile
from typing import Any, Mapping, Sequence

from . import core, rental_csv
from .plan_csv import PLAN_CSV_FILES, part_file_for_section

MANIFEST_NAME = "manifest.json"
MANIFEST_SCHEMA = "csv_exchange_plan_set_v1"
EXPORT_GROUPS = ("plan_set", "holdings", "ytd", "spending")
MAX_ZIP_BYTES = 200 * 1024 * 1024        # uncompressed total; guards against zip bombs
_ZIP_TIME = (2020, 1, 1, 0, 0, 0)        # fixed so an export is byte-reproducible
_PLAN_HEADER = ("section", "subsection", "label", "value", "units", "notes")


# ------------------------------------------------------------------ plan rows <-> files
def split_plan_rows(rows: Sequence[Mapping[str, str]]) -> dict[str, str]:
    """Plan rows -> ``{part file: CSV text}`` (inverse of the plan CSV parse). Each row goes
    to its section's primary part file; files with no rows are omitted; row order is kept."""
    by_file: dict[str, list[Mapping[str, str]]] = {}
    for r in rows:
        by_file.setdefault(part_file_for_section(r.get("section", "")), []).append(r)
    out: dict[str, str] = {}
    for name in PLAN_CSV_FILES:
        if name not in by_file:
            continue
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(_PLAN_HEADER)
        for r in by_file[name]:
            w.writerow([r.get(c, "") for c in _PLAN_HEADER])
        out[name] = buf.getvalue()
    return out


# ------------------------------------------------------------------------------ export
def export_plan_set_files(store: Any) -> dict[str, str]:
    """The export as ``{file name: text}`` (no zip), manifest last."""
    files = split_plan_rows(core.current_rows(store, core.PLAN_ROWS))
    manifest: dict[str, Any] = {"schema": MANIFEST_SCHEMA, "files": {}, "datasets": {}}
    for name in files:
        manifest["files"][name] = "plan_rows"
    manifest["datasets"][core.PLAN_ROWS] = {
        "files": list(files), "rows": len(core.current_rows(store, core.PLAN_ROWS))}
    for spec in core.DATASETS.values():
        if spec.group not in EXPORT_GROUPS or spec.name == core.PLAN_ROWS or spec.mode != core.MODE_REPLACE:
            continue
        files[spec.files[0]] = core.export_dataset(store, spec.name)
        manifest["files"][spec.files[0]] = spec.name
        manifest["datasets"][spec.name] = {"files": [spec.files[0]], "rows": len(core.current_rows(store, spec.name))}
    rental_rows = rental_csv.current_rows(store) if hasattr(store, "rental") else []
    if rental_rows:   # kept while the feature is off; omitted when there are none (older exports unchanged)
        files.update(rental_csv.export_files(rental_rows))
        manifest["datasets"][rental_csv.DATASET] = {
            "files": list(rental_csv.FILES), "rows": sum(r["_file"] == rental_csv.PART_PROPERTY for r in rental_rows)}
        manifest["files"].update({f: rental_csv.DATASET for f in rental_csv.FILES})
    files[MANIFEST_NAME] = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    return files


def export_plan_set(store: Any) -> bytes:
    """The plan CSV set, holdings, YTD and spending set as zip bytes, with a manifest."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, text in export_plan_set_files(store).items():
            info = zipfile.ZipInfo(name, date_time=_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, text.encode("utf-8"))
    return buf.getvalue()


# ------------------------------------------------------------------------------ import
def read_plan_set(source: bytes | bytearray | Mapping[str, str]) -> dict[str, str]:
    """Zip bytes or ``{name: text}`` -> ``{base file name: text}`` (folders dropped, BOM removed)."""
    if isinstance(source, Mapping):
        raw = {str(k): str(v) for k, v in source.items()}
    else:
        try:
            zf = zipfile.ZipFile(io.BytesIO(bytes(source)))
        except zipfile.BadZipFile as exc:
            raise core.ImportRejected(f"not a zip file: {exc}") from exc
        with zf:
            infos = [i for i in zf.infolist() if not i.is_dir()]
            if sum(i.file_size for i in infos) > MAX_ZIP_BYTES:
                raise core.ImportRejected("zip is too large to import")
            raw = {i.filename: zf.read(i).decode("utf-8-sig", errors="replace").replace("\x00", "")
                   for i in infos}
    out: dict[str, str] = {}
    for name, text in raw.items():
        base = posixpath.basename(name.replace("\\", "/"))
        if base and not base.startswith((".", "__")):
            out[base] = text.lstrip("﻿")
    return out


def parse_plan_set(files: Mapping[str, str]) -> tuple[list[core.ParsedDataset], list[str]]:
    """Group files by dataset (``core.dataset_for_file``) and parse each. Returns the parsed
    datasets (writable only; plan rows first) and the ignored file names (manifest, unknown
    names, read-only reference files)."""
    groups: dict[str, dict[str, str]] = {}
    ignored: list[str] = []
    for name, text in files.items():
        spec = core.dataset_for_file(name)
        if spec is None or not spec.writable:
            if name.lower() != MANIFEST_NAME:
                ignored.append(name)
            continue
        groups.setdefault(spec.name, {})[name] = text
    parsed: list[core.ParsedDataset] = []
    for dname, texts in groups.items():
        if dname == core.PLAN_ROWS:   # read in PLAN_CSV_FILES order (the anchor first)
            order = {f.lower(): i for i, f in enumerate(PLAN_CSV_FILES)}
            texts = dict(sorted(texts.items(), key=lambda kv: order.get(kv[0].lower(), 99)))
        parsed.append(core.parse(texts, dname))
    parsed.sort(key=lambda p: p.name != core.PLAN_ROWS)
    return parsed, sorted(ignored)


def import_plan_set(store: Any, source: bytes | bytearray | Mapping[str, str], *,
                    dry_run: bool = False, allow_errors: bool = False) -> dict[str, Any]:
    """Preview every dataset in ``source`` (``core.preview``), then commit them all in one
    transaction (``core.commit``) unless ``dry_run``. Raises ``ImportRejected`` (nothing
    written) when any dataset has a validation error. Returns the previews, the ignored file
    names and, once committed, ``{dataset: rows now held}``."""
    parsed, ignored = parse_plan_set(read_plan_set(source))
    previews = {p.name: core.preview(store, p) for p in parsed}
    errors = sum(len(v["errors"]) for v in previews.values())
    result: dict[str, Any] = {
        "schema": "csv_exchange_plan_set_preview_v1", "datasets": previews, "ignored": ignored,
        "errors": errors, "will_write": bool(parsed) and not errors, "committed": None}
    if not dry_run and parsed:
        result["committed"] = core.commit(store, parsed, allow_errors=allow_errors)
    return result
