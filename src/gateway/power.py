"""No-sleep policy for the always-on server: AC standby and hibernate timeouts set to "never".

``show`` reads, ``apply`` changes (the caller must pass ``confirmed=True``: the owner approves first) and saves
the previous values to a file so ``revert`` puts them back.  Uses ``powercfg`` on the active scheme.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

SETTINGS = {"standby": ("SUB_SLEEP", "STANDBYIDLE", "standby-timeout-ac"),
            "hibernate": ("SUB_SLEEP", "HIBERNATEIDLE", "hibernate-timeout-ac")}
_AC = re.compile(r"Current AC Power Setting Index:\s*(0x[0-9a-fA-F]+)")


class PowerError(RuntimeError):
    pass


def parse_ac_seconds(text: str) -> int | None:
    m = _AC.search(text or "")
    return int(m.group(1), 16) if m else None


def read_policy(run=subprocess.run) -> dict[str, int | None]:
    out: dict[str, int | None] = {}
    for name, (sub, setting, _) in SETTINGS.items():
        r = run(["powercfg", "/q", "SCHEME_CURRENT", sub, setting], capture_output=True, text=True, timeout=20)
        out[name] = parse_ac_seconds(getattr(r, "stdout", ""))
    return out


def sleeps(policy: dict[str, int | None]) -> bool:
    """True when the machine would still sleep or hibernate on AC (0 means never)."""
    return any(v != 0 for v in policy.values())


def apply_policy(saved_to: Path, *, confirmed: bool, run=subprocess.run) -> dict:
    if not confirmed:
        raise PowerError("the power plan is changed only with the owner's approval; pass --yes")
    before = read_policy(run)
    if any(v is None for v in before.values()):
        raise PowerError("could not read the current power plan, so it was not changed")
    saved_to = Path(saved_to)
    if not saved_to.exists():  # keep the ORIGINAL values across repeated applies
        saved_to.parent.mkdir(parents=True, exist_ok=True)
        saved_to.write_text(json.dumps(before), encoding="utf-8")
    for _, (_, _, flag) in SETTINGS.items():
        r = run(["powercfg", "/change", flag, "0"], capture_output=True, text=True, timeout=20)
        if getattr(r, "returncode", 0) != 0:
            raise PowerError(f"powercfg refused {flag} (is this an elevated shell?)")
    return {"before": before, "after": read_policy(run)}


def revert_policy(saved_from: Path, *, confirmed: bool, run=subprocess.run) -> dict:
    if not confirmed:
        raise PowerError("pass --yes to restore the saved power plan")
    saved_from = Path(saved_from)
    try:
        before = json.loads(saved_from.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise PowerError("there is no saved power plan to restore") from None
    for name, (_, _, flag) in SETTINGS.items():
        minutes = int(before.get(name) or 0) // 60
        r = run(["powercfg", "/change", flag, str(minutes)], capture_output=True, text=True, timeout=20)
        if getattr(r, "returncode", 0) != 0:
            raise PowerError(f"powercfg refused {flag} (is this an elevated shell?)")
    saved_from.unlink(missing_ok=True)
    return {"restored": before, "now": read_policy(run)}
