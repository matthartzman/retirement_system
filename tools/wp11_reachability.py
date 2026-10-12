"""WP11.1 reachability check: where is each dead-code candidate still referenced?

Run: python tools/wp11_reachability.py [--md]
A candidate is deletable only if every hit sits in its own definition or in
a doc/spec. Hits under src/legacy_conversion, tools/rehearse_conversion.py or
verify.py are the converter's: they pin the candidate until unit 11.6.
"""
from __future__ import annotations
import re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = [
    "export_latest_plan", "latest_plan_input", "local_plan_registry", "DEFAULT_CLIENTS_CSV",
    "forecast_package", "build_jobs", "live_pricing_test_results",
    "load_clients_csv", "upsert_client", "sync_clients_csv_to_sqlite", "list_clients", "get_client",
    "allow_csv_write", "clients_file", "build_queue_enabled", "server_side_path_roots",
    "secrets_store", "master_key", "config_backend",
]
SKIP = ("docs/superpowers/", "documentation/archive/", "node_modules/", ".git/", "tools/wp11_reachability.py", "documentation/reference/WP11_REACHABILITY.md")


def hits(name: str) -> list[str]:
    out = subprocess.run(["git", "grep", "-nw", name], cwd=ROOT, capture_output=True, text=True).stdout
    rows = [l for l in out.splitlines() if not l.startswith(SKIP)]
    return rows


def main() -> None:
    md = "--md" in sys.argv
    if md:
        print("# WP11.1 reachability summary\n\nOutput of `tools/wp11_reachability.py` (files per candidate; converter files flagged).\n")
    for name in CANDIDATES:
        rows = hits(name)
        files = sorted({r.split(":", 1)[0] for r in rows})
        conv = [f for f in files if f.startswith("src/legacy_conversion") or "rehearse_conversion" in f]
        print(f"{'- ' if md else ''}{name}: {len(rows)} hits in {len(files)} files" + (f"; CONVERTER: {conv}" if conv else ""))
        if not md:
            for f in files:
                print(f"    {f}")


if __name__ == "__main__":
    main()
