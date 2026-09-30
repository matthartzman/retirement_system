"""Frozen-build regression: API keys must be written to the per-user workspace.

`secrets_store` used to resolve its file from the package location. In a
PyInstaller build that is the read-only, rebuild-wiped bundle folder, so keys
saved through the app (WI-206) were lost on the next rebuild and could sit in a
shareable directory. The real frozen executable is exercised by
scripts/pyinstaller_smoke.py in the CI build job; this test simulates the frozen
flag in a subprocess so the same probe logic is checked on every test run.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "scripts" / "pyinstaller_smoke_workspace_probe.py"


def test_default_frozen_workspace_holds_secrets_and_seed(tmp_path):
    env = {k: v for k, v in os.environ.items() if not k.startswith("RETIREMENT_SYSTEM_")}
    env.update(LOCALAPPDATA=str(tmp_path), XDG_DATA_HOME=str(tmp_path), HOME=str(tmp_path),
               USERPROFILE=str(tmp_path), PYTHONPATH=str(ROOT))
    code = f"import sys, runpy; sys.frozen = True; runpy.run_path({str(PROBE)!r}, run_name='__main__')"
    r = subprocess.run([sys.executable, "-c", code], env=env, cwd=ROOT, capture_output=True, text=True, timeout=120)
    line = next((ln for ln in r.stdout.splitlines() if ln.startswith("SMOKE_WORKSPACE_OK ")), None)
    assert r.returncode == 0 and line, f"probe failed\n{r.stdout[-1500:]}\n{r.stderr[-1500:]}"
    info = json.loads(line.split(" ", 1)[1])
    ws, pkg, sec = Path(info["workspace_root"]), Path(info["package_root"]), Path(info["secrets_path"])
    assert tmp_path in ws.parents and ws != pkg
    assert sec == ws / "local_state" / "secrets.local.json" and sec.is_file()
    assert pkg not in sec.parents
    assert (ws / "input" / "client_data.csv").is_file()
    # Nothing was written into the project (stand-in for the bundle) by the probe.
    assert not (ROOT / "local_state" / "secrets.local.json").exists() or \
        "smoke_probe_key" not in (ROOT / "local_state" / "secrets.local.json").read_text(encoding="utf-8")
