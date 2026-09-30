"""Probe executed INSIDE the frozen build by scripts/pyinstaller_smoke.py.

Run WITHOUT ``RETIREMENT_SYSTEM_WORKSPACE_ROOT`` so the frozen build resolves its
real default per-user workspace (``%LOCALAPPDATA%\\RetirementPlanner`` on Windows,
else ``$XDG_DATA_HOME``/``~/.local/share``). Writes a secret and seeds the
workspace, then prints one ``SMOKE_WORKSPACE_OK {json}`` line with where things
landed, so the smoke test can assert user data never lands in the read-only,
rebuild-wiped bundle folder.
"""
from __future__ import annotations

import json
import sys

from src.platform_runtime import is_frozen, package_root, seed_frozen_workspace, workspace_root
from src.secrets_store import get_secret, secrets_path, set_secret

seeded = seed_frozen_workspace()
set_secret("smoke_probe_key", "smoke-value")
if get_secret("smoke_probe_key") != "smoke-value":
    raise SystemExit("secret did not round-trip")

print("SMOKE_WORKSPACE_OK " + json.dumps({
    "frozen": is_frozen() and bool(getattr(sys, "frozen", False)),
    "workspace_root": str(workspace_root()),
    "package_root": str(package_root()),
    "secrets_path": str(secrets_path()),
    "seeded": bool(seeded),
}))
