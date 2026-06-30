#!/usr/bin/env python3
from __future__ import annotations

"""Validate that an overlay zip can be applied cleanly to a pristine package.

Usage:
    python tools/validate_clean_overlay.py --base "Version 10 - ChatpGPT.zip" --overlay overlay.zip

The script extracts the base package to a temporary directory, overlays changed
files, then runs dependency-light smoke checks against the stdlib runtime and
static JavaScript.  It is intentionally local/offline and does not require Flask.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

CANONICAL_ROUTES = (
    "/api/ping",
    "/api/runtime",
    "/api/build/preflight",
    "/api/summary",
    "/api/contracts",
)


def _extract(zip_path: Path, dest: Path) -> None:
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest)


def _project_root(extract_dir: Path) -> Path:
    if (extract_dir / "main.py").exists() and (extract_dir / "src").exists():
        return extract_dir
    candidates = [p for p in extract_dir.iterdir() if p.is_dir() and (p / "main.py").exists() and (p / "src").exists()]
    if len(candidates) == 1:
        return candidates[0]
    raise SystemExit(f"Could not identify project root under {extract_dir}")


def _overlay(overlay_zip: Path, root: Path) -> None:
    with zipfile.ZipFile(overlay_zip) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename.replace("\\", "/")
            if name.startswith("/") or ".." in Path(name).parts:
                raise SystemExit(f"Unsafe overlay path: {info.filename}")
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)


def _run(cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> dict:
    proc = subprocess.run(cmd, cwd=str(cwd), text=True, capture_output=True, env=env)
    return {"cmd": cmd, "returncode": proc.returncode, "stdout": proc.stdout[-4000:], "stderr": proc.stderr[-4000:]}


def _route_smoke(root: Path) -> dict:
    code = """
import json
from src.server import app
out = {}
client = app.test_client()
for path in %r:
    resp = client.get(path)
    out[path] = {"status": resp.status_code, "body": resp.get_data(as_text=True)[:200]}
print(json.dumps(out, sort_keys=True))
""" % (CANONICAL_ROUTES,)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root)
    result = _run([sys.executable, "-c", code], root, env=env)
    result["routes"] = {}
    if result["returncode"] == 0:
        result["routes"] = json.loads(result["stdout"] or "{}")
        bad = {p: r for p, r in result["routes"].items() if int(r.get("status", 0)) >= 400}
        if bad:
            result["returncode"] = 1
            result["stderr"] += "\nBad route statuses: " + json.dumps(bad, sort_keys=True)
    return result


def validate(base_zip: Path, overlay_zip: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="retirement_overlay_validate_") as tmp:
        tmp_path = Path(tmp)
        _extract(base_zip, tmp_path)
        root = _project_root(tmp_path)
        _overlay(overlay_zip, root)
        checks = []
        checks.append(_run([sys.executable, "-m", "py_compile", "src/api_contracts.py", "src/server/base_routes.py", "src/server_services/pricing_service.py", "src/server_services/holdings_service.py", "src/server_services/build_job_service.py", "src/server_services/report_service.py", "src/server_services/spending_service.py", "src/server_services/strategy_asset_service.py", "src/server_services/portfolio_service.py", "src/server_services/secret_service.py", "src/server/workbook_routes.py", "src/server/plan_routes.py"], root))
        checks.append(_route_smoke(root))
        if shutil.which("node"):
            checks.append(_run(["node", "--check", "frontend/js/dashboard.js"], root))
            checks.append(_run(["node", "--check", "frontend/js/api_client.js"], root))
            checks.append(_run(["node", "--check", "frontend/js/app_store.js"], root))
        ok = all(c["returncode"] == 0 for c in checks)
        return {"success": ok, "root": str(root), "checks": checks}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--overlay", required=True, type=Path)
    args = parser.parse_args()
    report = validate(args.base, args.overlay)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
