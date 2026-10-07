"""WP0.3: static data-file-I/O audit (report mode) with a one-way ratchet.

AST-scans ``src/`` for the calls that move plan data through files: ``csv.*``,
``json.load/dump``, ``yaml.*`` load/dump (import aliases resolved), builtin ``open()``
and ``Path.read_text/write_text/read_bytes/write_bytes``. The per-file
counts live in ``tests/fixtures/file_io_audit_baseline.json``. The test fails
if any file's count rises or a new file appears with calls; it never fails
because a count fell. When the count falls, lower the baseline:

    python tests/test_no_data_file_io_report_regression.py --record

The file-elimination phases (P1+) drive this number down; it can only go down.
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "tests" / "fixtures" / "file_io_audit_baseline.json"
SCAN_DIRS = ("src",)
# Files (or packages, with a trailing "/") exempt from the count; add with a reason, never to
# hide growth.
ALLOWLIST: dict[str, str] = {
    "src/csv_exchange/": "the one sanctioned CSV import/export package (design F section 6, WP4.1+)",
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


def _total(files: dict[str, dict[str, int]]) -> int:
    return sum(sum(c.values()) for c in files.values())


def record() -> None:
    files = scan()
    BASELINE.write_text(json.dumps({"total": _total(files), "files": files}, indent=1, sort_keys=True) + "\n",
                        encoding="utf-8")
    print(f"Wrote {BASELINE.relative_to(ROOT)}: {_total(files)} data-file I/O calls in {len(files)} files")


def test_data_file_io_count_has_not_grown():
    base = json.loads(BASELINE.read_text(encoding="utf-8"))
    live = scan()
    grew = []
    for rel, counts in live.items():
        old = base["files"].get(rel, {})
        for kind, n in counts.items():
            if n > old.get(kind, 0):
                grew.append(f"{rel}: {kind} {old.get(kind, 0)} -> {n}")
    assert not grew, (
        "data-file I/O calls increased (the file-elimination ratchet only goes down); "
        "route through the store layer instead:\n  " + "\n  ".join(grew)
    )
    assert _total(live) <= base["total"]


def test_allowlist_names_existing_paths():
    for path in ALLOWLIST:
        assert (ROOT / path).exists(), f"stale allowlist entry: {path}"


def test_baseline_matches_report_shape():
    base = json.loads(BASELINE.read_text(encoding="utf-8"))
    assert base["total"] == sum(sum(c.values()) for c in base["files"].values())
    assert base["total"] > 0


if __name__ == "__main__":
    if "--record" in sys.argv:
        record()
    else:
        print(json.dumps({"total": _total(scan())}))
