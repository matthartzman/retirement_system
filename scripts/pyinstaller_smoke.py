#!/usr/bin/env python3
"""Real PyInstaller smoke test: build the frozen app, then run it.

Static spec checks (tests/test_frozen_build_spec_static_unit.py) cannot see a
missing hidden import or data file; only running the frozen binary can. This
script does, in an isolated environment:

  1. (default) creates a throwaway venv under .smoke_env/, installs
     requirements.txt (+ pyinstaller) and builds retirement_planner.spec into
     .smoke_env/dist -- never touching dist/ or the developer's workspace;
  2. ``retirement_planner --help`` exits 0;
  3. script-runner mode runs scripts/pyinstaller_smoke_probe.py inside the
     frozen interpreter (numpy/scipy/lxml/openpyxl imports, bundled ``src``,
     bundled demo plan, a real vectorized Monte Carlo run);
  4. run without the workspace override (LOCALAPPDATA/HOME pointed at a temp
     dir): user data and the secrets file must land in the per-user default
     workspace, never inside the bundle (scripts/pyinstaller_smoke_workspace_probe.py);
  5. server mode boots on a free port with an empty temp workspace, seeds it
     from the bundled demo, serves ``/`` and ``/api/status``, and stops.

Usage:
    python scripts/pyinstaller_smoke.py                  # fresh venv + build + run
    python scripts/pyinstaller_smoke.py --no-venv        # build with current interpreter
    python scripts/pyinstaller_smoke.py --skip-build --dist dist/retirement_planner
                                                         # test an existing build (CI)
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_DIR = ROOT / ".smoke_env"
EXE_NAME = "retirement_planner.exe" if sys.platform == "win32" else "retirement_planner"


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    print(f">>> {' '.join(map(str, cmd))}", flush=True)
    return subprocess.run(cmd, **kw)


def build(no_venv: bool, with_pywebview: bool) -> Path:
    py = sys.executable
    if not no_venv:
        venv = ENV_DIR / "venv"
        if not venv.exists():
            run([sys.executable, "-m", "venv", str(venv)], check=True)
        py = str(venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python"))
        reqs = [ln for ln in (ROOT / "requirements.txt").read_text().splitlines()
                if with_pywebview or "pywebview" not in ln]
        req_file = ENV_DIR / "requirements.smoke.txt"
        req_file.write_text("\n".join(reqs) + "\n")
        run([py, "-m", "pip", "install", "-q", "-r", str(req_file), "pyinstaller"], check=True)
    dist, work = ENV_DIR / "dist", ENV_DIR / "work"
    shutil.rmtree(dist, ignore_errors=True)
    run([py, "-m", "PyInstaller", str(ROOT / "retirement_planner.spec"), "--noconfirm",
         "--distpath", str(dist), "--workpath", str(work)], cwd=ROOT, check=True)
    return dist / "retirement_planner"


def isolated_env(workspace: Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("RETIREMENT_SYSTEM_")}
    env.update(
        RETIREMENT_SYSTEM_WORKSPACE_ROOT=str(workspace),
        RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS="1",
        RETIREMENT_SYSTEM_NO_AUTO_OPEN="1",
        BROWSER="true",
        PYTHONUNBUFFERED="1",
    )
    return env


def check_help(exe: Path, env: dict[str, str]) -> None:
    r = run([str(exe), "--help"], env=env, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, f"--help exited {r.returncode}\n{r.stdout}\n{r.stderr}"


def check_probe(exe: Path, env: dict[str, str]) -> None:
    probe = ROOT / "scripts" / "pyinstaller_smoke_probe.py"
    r = run([str(exe), str(probe)], env=env, capture_output=True, text=True, timeout=900)
    line = next((ln for ln in r.stdout.splitlines() if ln.startswith("SMOKE_PROBE_OK ")), None)
    assert r.returncode == 0 and line, f"probe failed ({r.returncode})\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}"
    info = json.loads(line.split(" ", 1)[1])
    assert info["frozen"] is True, f"probe did not run frozen: {info}"
    print(f"    probe ok: {info}")


def check_default_workspace(exe: Path, env: dict[str, str]) -> None:
    """Run without the workspace override: user data must land in the per-user
    default location (not the read-only bundle), including the secrets file."""
    home = Path(tempfile.mkdtemp(prefix="rp_smoke_home_"))
    try:
        env = {k: v for k, v in env.items() if k != "RETIREMENT_SYSTEM_WORKSPACE_ROOT"}
        env.update(LOCALAPPDATA=str(home), XDG_DATA_HOME=str(home), HOME=str(home), USERPROFILE=str(home))
        probe = ROOT / "scripts" / "pyinstaller_smoke_workspace_probe.py"
        r = run([str(exe), str(probe)], env=env, capture_output=True, text=True, timeout=300)
        line = next((ln for ln in r.stdout.splitlines() if ln.startswith("SMOKE_WORKSPACE_OK ")), None)
        assert r.returncode == 0 and line, f"workspace probe failed ({r.returncode})\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}"
        info = json.loads(line.split(" ", 1)[1])
        ws, pkg, sec = Path(info["workspace_root"]), Path(info["package_root"]), Path(info["secrets_path"])
        assert info["frozen"] is True, f"probe did not run frozen: {info}"
        assert home in ws.parents and ws != pkg, f"default workspace is not per-user: {info}"
        assert sec == ws / "local_state" / "secrets.local.json", f"secrets not under the workspace: {info}"
        assert pkg not in sec.parents, f"secrets landed inside the bundle: {info}"
        assert sec.is_file(), f"secrets file was not written: {sec}"
        assert (ws / "input" / "client_data.csv").is_file(), "default workspace was not seeded from bundled demo"
        assert (ws / "plan.rpx").is_file(), "default workspace plan file was not seeded from bundled demo"
        print(f"    default workspace ok: {ws}")
    finally:
        shutil.rmtree(home, ignore_errors=True)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def check_server(exe: Path, env: dict[str, str], workspace: Path) -> None:
    port = _free_port()
    env = {**env, "RETIREMENT_SYSTEM_DASHBOARD_PORT": str(port), "RETIREMENT_SYSTEM_DASHBOARD_HOST": "127.0.0.1"}
    log = (ENV_DIR / "server.log").open("w")
    proc = subprocess.Popen([str(exe), "--mode", "server"], env=env, stdout=log, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    try:
        deadline = time.time() + 120
        status = None
        while time.time() < deadline:
            if proc.poll() is not None:
                raise AssertionError(f"server exited early ({proc.returncode})")
            try:
                with urllib.request.urlopen(base + "/api/status", timeout=5) as resp:
                    status = json.loads(resp.read())
                    break
            except Exception:
                time.sleep(1)
        assert status is not None, "server never answered /api/status"
        with urllib.request.urlopen(base + "/", timeout=10) as resp:
            body = resp.read().decode("utf-8", "replace").lower()
            assert resp.status == 200 and "<html" in body, "/ did not serve the bundled frontend"
        assert (workspace / "input" / "client_data.csv").is_file(), "workspace was not seeded from bundled demo"
        assert (workspace / "plan.rpx").is_file(), "workspace plan file was not seeded from bundled demo"
        print(f"    server ok: /api/status keys={sorted(status)[:6]}")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--skip-build", action="store_true", help="test an existing build (needs --dist)")
    ap.add_argument("--dist", type=Path, help="onedir folder holding the frozen exe")
    ap.add_argument("--no-venv", action="store_true", help="build with the current interpreter")
    ap.add_argument("--with-pywebview", action="store_true", help="install pywebview (needs GTK/Qt on Linux)")
    args = ap.parse_args()

    ENV_DIR.mkdir(exist_ok=True)
    if args.skip_build:
        if not args.dist:
            ap.error("--skip-build requires --dist")
        dist = args.dist.resolve()
    else:
        dist = build(args.no_venv, args.with_pywebview)
    exe = dist / EXE_NAME
    assert exe.is_file(), f"frozen executable not found: {exe}"

    workspace = Path(tempfile.mkdtemp(prefix="rp_smoke_ws_"))
    env = isolated_env(workspace)
    try:
        for label, fn in (("help", lambda: check_help(exe, env)),
                          ("script-runner probe", lambda: check_probe(exe, env)),
                          ("default per-user workspace + secrets", lambda: check_default_workspace(exe, env)),
                          ("server mode", lambda: check_server(exe, env, workspace))):
            print(f"== {label}", flush=True)
            fn()
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
    print("PYINSTALLER SMOKE TEST PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
