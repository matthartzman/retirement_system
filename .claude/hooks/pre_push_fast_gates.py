"""PreToolUse guard: run the CI fast-gates locally before any `git push`.

Review of 40 failed CI runs showed the same cheap static checks (doc Status
line, architecture-diagram freshness, frontend size ratchet, frontend-source
grep freeze, data-file I/O allowlist) failing repeatedly, each found only after
a CI round trip. This hook blocks the push (exit 2, message goes back to the
model) when `python tools/fast_gates.py` fails, so the fix lands in the same
push instead of a follow-up `Fix CI:` commit.

Bypass deliberately by setting SKIP_FAST_GATES=1 in the command, e.g.
`SKIP_FAST_GATES=1 git push` -- only for pushes that touch nothing the gates
cover and where the gates are known-broken on main.
"""
import json
import re
import subprocess
import sys


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    cmd = (data.get("tool_input") or {}).get("command", "")
    if not re.search(r"(^|[;&|]\s*)git\s+(-C\s+\S+\s+)?push\b", cmd):
        return 0
    if "SKIP_FAST_GATES=1" in cmd or "--delete" in cmd:
        return 0
    proc = subprocess.run(
        [sys.executable, "tools/fast_gates.py"], capture_output=True, text=True
    )
    if proc.returncode == 0:
        return 0
    tail = (proc.stdout + proc.stderr).strip().splitlines()[-40:]
    sys.stderr.write(
        "Push blocked: local fast-gates failed (same checks as CI fast-gates).\n"
        "Fix the failures below, then push again.\n\n" + "\n".join(tail) + "\n"
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
