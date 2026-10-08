from __future__ import annotations

"""Feature-owned portfolio analytics service helpers.

The HTTP route layer supplies workspace/runtime context.  This module owns the
request-independent work for running local portfolio analysis tools and reading
result artifacts so route modules remain thin adapters.
"""

import json
import re
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


def drift_payload(
    *,
    base_dir: Path,
    output_dir: Path,
    system_config_csv: Path,
    max_build_seconds: int | float,
) -> dict[str, Any]:
    """Run the local portfolio drift analyzer and return its JSON rows."""
    env = os.environ.copy()
    env["RETIREMENT_SYSTEM_SYSTEM_CONFIG_CSV"] = str(system_config_csv)
    env["PYTHONIOENCODING"] = env.get("PYTHONIOENCODING", "utf-8:replace")
    result = subprocess.run(
        [sys.executable, str(base_dir / "tools" / "analyze_drift.py")],
        cwd=str(base_dir),
        capture_output=True,
        text=True,
        timeout=max_build_seconds,
        env=env,
    )
    rows: list[Any] = []
    text = (result.stdout or "").strip()
    tops = [m.start() for m in re.finditer(r"^\[$", text, re.M)]  # the rows are the last top-level array
    try:
        loaded = json.loads(text[tops[-1]:] if tops else text) if text else []
        rows = loaded if isinstance(loaded, list) else []
    except Exception as exc:  # noqa: BLE001 - preserve route-era resilience
        return {
            "success": False,
            "rows": [],
            "stderr": f"portfolio drift output was not valid JSON: {exc}",
            "returncode": result.returncode,
        }
    return {"success": result.returncode == 0, "rows": rows, "stderr": result.stderr[-1000:], "returncode": result.returncode}
