"""Run the CI `fast-gates` job locally, before pushing.

Mirrors .github/workflows/ci.yml `fast-gates` step for step, plus the two
`test`-job checks that repeatedly failed there (architecture-diagram freshness
and the frontend size ratchet are already in the static set; the docs-status
check is too). Review of 40 failed CI runs (2026-10-22..11-05) found the same
cheap checks failing again and again, each discovered only after a CI round trip:

  * test_design_documents_declare_a_status      (new doc without `Status:` line)
  * test_system_architecture_diagram_freshness  (structural change, diagram not regenerated)
  * test_frontend_size_ratchet                  (frontend/js grew past the ceiling)
  * test_freeze_frontend_source_grep            (new test asserting on frontend source text)
  * test_no_data_file_io_enforcing              (new data-file I/O outside the allowlist)

Usage:  python tools/fast_gates.py            # all gates, stops on first failure
        python tools/fast_gates.py --keep-going
Exit code 0 = safe to push.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_ENGINE_IMPORT = re.compile(r"^\s*(import|from)\s+(src|numpy|openpyxl|scipy|matplotlib)", re.M)

# Always run, even if the import heuristic would classify them as non-static:
# these are the files that fail CI most often.
ALWAYS = [
    "tests/test_documentation_status_and_layout_regression.py",
    "tests/test_system_architecture_diagram_freshness_regression.py",
    "tests/test_frontend_size_ratchet.py",
    "tests/test_freeze_frontend_source_grep.py",
    "tests/test_no_data_file_io_enforcing_regression.py",
]


def static_test_files() -> list[str]:
    files = []
    for f in sorted((ROOT / "tests").glob("test_*.py")):
        if not _ENGINE_IMPORT.search(f.read_text(encoding="utf-8", errors="replace")):
            files.append(f.relative_to(ROOT).as_posix())
    for f in ALWAYS:
        if f not in files and (ROOT / f).exists():
            files.append(f)
    return files


def run(label: str, cmd: list[str]) -> bool:
    print(f"\n=== {label}\n$ {' '.join(cmd[:6])}{' ...' if len(cmd) > 6 else ''}", flush=True)
    return subprocess.run(cmd, cwd=ROOT).returncode == 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep-going", action="store_true", help="run every gate even after a failure")
    args = ap.parse_args()

    py = sys.executable
    gates = [
        ("Account-number scan", [py, "tools/check_no_account_numbers.py"]),
        ("ruff", [py, "-m", "ruff", "check", "src/", "tests/"]),
        (
            "Static source-text tests",
            [py, "-m", "pytest", *static_test_files(), "-m", "not slow and not nightly", "--tb=short", "-q", "-rfE"],
        ),
        ("Static regression checks", [py, "tools/run_regression.py"]),
    ]
    failed = []
    for label, cmd in gates:
        if not run(label, cmd):
            failed.append(label)
            if not args.keep_going:
                break
    if failed:
        print(f"\nFAST GATES FAILED: {', '.join(failed)}\n"
              "Fix these before pushing -- they are the same checks CI's fast-gates job runs.")
        return 1
    print("\nFast gates passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
