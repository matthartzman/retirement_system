from __future__ import annotations

"""Feature-owned portfolio analytics service helpers.

The HTTP route layer supplies workspace/runtime context.  This module owns the
request-independent work for running local portfolio analysis tools and reading
result artifacts so route modules remain thin adapters.
"""

import json
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
    out = output_dir / "portfolio_drift.json"
    rows: list[Any] = []
    if out.exists():
        try:
            loaded = json.loads(out.read_text(encoding="utf-8"))
            rows = loaded if isinstance(loaded, list) else []
        except Exception as exc:  # noqa: BLE001 - preserve route-era resilience
            return {
                "success": False,
                "rows": [],
                "stderr": f"portfolio_drift.json was not valid JSON: {exc}",
                "returncode": result.returncode,
            }
    return {"success": result.returncode == 0, "rows": rows, "stderr": result.stderr[-1000:], "returncode": result.returncode}
