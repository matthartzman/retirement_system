"""WP11.3: static data-file-I/O audit, enforcing.

AST-scans ``src/`` for the calls that move plan data through files: ``csv.*``,
``json.load/dump``, ``yaml.*`` load/dump (import aliases resolved), builtin ``open()``
and ``Path.read_text/write_text/read_bytes/write_bytes``. Zero such calls are allowed
outside ``ALLOWLIST``; every allowlisted file or package carries a one-line reason.
Plan data lives in the plan file and app.db; a new file here needs a reason or a store call.
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "tests" / "fixtures" / "file_io_audit_baseline.json"
SCAN_DIRS = ("src",)
# Files (or packages, with a trailing "/") exempt from the audit. Add with a reason, never to
# hide plan data moving through files.
ALLOWLIST: dict[str, str] = {
    "src/csv_exchange/": "the one sanctioned CSV import/export package (design F section 6)",
    "src/broker_activity/": "pure parsers of broker history files uploaded by the user (text in, rows out; no file access)",
    "src/legacy_conversion/": "one-time legacy source reader (removed with the converter, unit 11.6)",
    "src/data_io.py": "load_csv: the old loader path the converter's verify.py compares against (removed with 11.6)",
    "src/plan_data_migration.py": "reads legacy files to migrate old plan data forward (removed with 11.6)",
    "src/local_backup_scheduler.py": "reads the legacy backup settings file once and the backup manifest (migrates into app.db)",
    "src/monarch_autoupdate.py": "reads the legacy Monarch auto-update state file once (migrates into app.db)",
    "src/server_services/base_service.py": "reads the legacy data/prefs.json once (migrates into app.db)",
    "src/secrets_store.py": "reads the legacy plain-text secrets file only to migrate it into the OS credential store",
    "src/reporting/workbook_format_config.py": "reads the legacy workbook format file once (migrates into app.db)",
    "src/desktop_api.py": "writes a file the user picked in a Save dialog (exports and downloads)",
    "src/server/workbook_routes.py": "reads a generated output file for download/compare; not plan data",
    "src/reporting/projection_tables.py": "writes the build's projection_tables.json output (Trends Recent Projections); not plan data",
    "src/http_runtime/wsgi_facade.py": "serves static frontend assets",
    "src/reporting/dashboard.py": "writes the generated HTML report to the per-plan output folder",
    "src/market_data.py": "price cache file and in-memory CSV text from market-data providers; not plan data",
    "src/domain_models.py": "reads a user-supplied JSON model definition by path (a file the user picked)",
    "src/monarch_import.py": "reads the Monarch export file the user picked (import source)",
    "src/monarch_mapping_seed.py": "reads the user-supplied Monarch-to-app mapping CSV (one-time seed import)",
    "src/monarch_balances_import.py": "reads the Monarch Extractor's balances.csv (import source), like monarch_import.py",
    "src/server_services/admin_service.py": "CSV text for the Admin raw-file view and export of the legacy system files",
    "src/server_services/spending_service.py": "reads/writes a spending upload the user picked (import source)",
    "src/server_services/ytd_service.py": "reads the YTD file the user picked (import source)",
}


def _allowlisted(rel: str) -> bool:
    return any(rel == p or (p.endswith("/") and rel.startswith(p)) for p in ALLOWLIST)

_JSON = {"load", "dump"}
_PATH_IO = {"read_text", "write_text", "read_bytes", "write_bytes"}
_YAML = {"load", "safe_load", "load_all", "safe_load_all", "dump", "safe_dump", "dump_all", "safe_dump_all"}


def _aliases(tree: ast.AST) -> dict[str, str]:
    """Local name -> csv/json/yaml for ``import csv as _csv`` style imports."""
    out: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name in ("csv", "json", "yaml"):
                    out[a.asname or a.name] = a.name
    return out


def _call_kind(node: ast.Call, aliases: dict[str, str]) -> str | None:
    fn = node.func
    if isinstance(fn, ast.Name):
        return "open" if fn.id == "open" else None
    if isinstance(fn, ast.Attribute):
        if isinstance(fn.value, ast.Name) and fn.value.id in aliases:
            mod, attr = aliases[fn.value.id], fn.attr
            if mod == "csv":
                return "csv"
            if mod == "json" and attr in _JSON:
                return "json"
            if mod == "yaml" and attr in _YAML:
                return "yaml"
        elif fn.attr in _PATH_IO:
            return "path_io"
    return None


def scan(root: Path = ROOT) -> dict[str, dict[str, int]]:
    """{relative_path: {kind: count}} for every scanned file with any hit."""
    out: dict[str, dict[str, int]] = {}
    for d in SCAN_DIRS:
        for f in sorted((root / d).rglob("*.py")):
            rel = f.relative_to(root).as_posix()
            if _allowlisted(rel):
                continue
            tree = ast.parse(f.read_text(encoding="utf-8"), filename=rel)
            counts: dict[str, int] = {}
            aliases = _aliases(tree)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    kind = _call_kind(node, aliases)
                    if kind:
                        counts[kind] = counts.get(kind, 0) + 1
            if counts:
                out[rel] = dict(sorted(counts.items()))
    return out


def test_no_data_file_io_outside_the_allowlist():
    live = scan()
    assert not live, (
        "data-file I/O outside the allowlist (plan data goes through the store layer; if the file is "
        "justified, add it to ALLOWLIST with a reason):\n  " + "\n  ".join(f"{k}: {v}" for k, v in live.items())
    )


def test_allowlist_names_existing_paths_with_reasons():
    for path, reason in ALLOWLIST.items():
        assert (ROOT / path).exists(), f"stale allowlist entry: {path}"
        assert len(reason.strip()) > 10, f"allowlist entry needs a reason: {path}"


def test_allowlist_has_no_unused_entries():
    """An allowlisted file that no longer does file I/O must leave the list."""
    import ast as _ast  # noqa: PLC0415
    unused = []
    for path in ALLOWLIST:
        if path.endswith("/"):
            continue
        tree = _ast.parse((ROOT / path).read_text(encoding="utf-8"))
        al = _aliases(tree)
        if not any(isinstance(n, _ast.Call) and _call_kind(n, al) for n in _ast.walk(tree)):
            unused.append(path)
    assert not unused, f"remove from ALLOWLIST (no file I/O left): {unused}"


if __name__ == "__main__":
    print(json.dumps(scan(), indent=1))
