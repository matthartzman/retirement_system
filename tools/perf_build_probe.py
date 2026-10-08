"""Time a full workbook build and fingerprint its numeric output.

Always runs with live price providers disabled so two runs are comparable:
live quotes move between builds and would otherwise show up as output diffs.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Substring -> phase name. The build prints these markers on stdout already.
PHASE_MARKERS = [
    ("Parsing client data", "config_parse_and_roth_optimizer"),
    ("Running projection", "projection_and_monte_carlo"),
    ("Building workbook", "workbook_start"),
    ("Sheet 10 ", "sheet10_social_security"),
    ("Sheet 1 ", "sheet10_end_other_sheets"),
    ("Saving workbook", "save_and_dashboard"),
    ("Build complete", "done"),
]


def _stable_model_hash(data: dict) -> str:
    data = {k: v for k, v in data.items() if k != "generated_at"}
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    os.environ["RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS"] = "1"

    from src.build_entry import run_build

    t0 = time.perf_counter()
    marks: list[tuple[float, str]] = []
    buf = io.StringIO()

    class Tee:
        def write(self, data: str) -> None:
            buf.write(data)
            for needle, name in PHASE_MARKERS:
                if needle in data:
                    marks.append((time.perf_counter() - t0, name))

        def flush(self) -> None:
            pass

    with contextlib.redirect_stdout(Tee()):
        run_build()
    total = time.perf_counter() - t0

    phases: dict[str, float] = {}
    for i, (ts, name) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else total
        phases[name] = round(end - ts, 3)

    from src.active_plan import read_build_results

    stored = read_build_results() or {}
    result = {
        "total_s": round(total, 3),
        "phases": phases,
        "model_sha256": _stable_model_hash(stored["explorer"]),
        "summary_sha256": hashlib.sha256(
            json.dumps(stored["summary"], sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
    }
    Path(args.out).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
