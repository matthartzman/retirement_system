"""Time the projection engine on the current host (Android plan, Phase 3.1).

Runs the deterministic projection and a Monte Carlo pass against the active
plan data and prints wall-clock timings plus the return model in use, so the
same command gives comparable numbers on a desktop, a CI runner, or an Android
device (via Termux/adb shell). Use it to pick a sensible
RETIREMENT_SYSTEM_MOBILE_MC_SIMS_CAP for a given phone.

Usage:
    python tools/profile_projection.py [--mc-sims N] [--repeat K]
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mc-sims", type=int, default=200,
                        help="Monte Carlo paths to time (default 200; scale linearly for larger counts)")
    parser.add_argument("--repeat", type=int, default=3,
                        help="deterministic-projection repetitions to average (default 3)")
    args = parser.parse_args()

    from src import platform_runtime
    from src.data_io import load_csv, parse_client
    from src.plan_config import ensure_engine_config
    from src.planning_engines import monte_carlo_exact_scalar, project

    root = platform_runtime.workspace_root()
    caps = platform_runtime.capabilities()
    print(f"platform={caps['platform']} is_mobile={caps['is_mobile']} build_mode={caps['build_mode']}")

    csv_path = root / "input" / "client_data.csv"
    if not csv_path.exists():
        print(f"No plan data at {csv_path} — load or save a plan first.", file=sys.stderr)
        return 1

    c = ensure_engine_config(parse_client(load_csv(csv_path), ""), source="profile")
    mobile_cap = platform_runtime.mobile_mc_sims_cap()
    print(f"mc_sims (configured)={c.get('mc_sims')} mc_sensitivity_sims={c.get('mc_sensitivity_sims')} "
          f"mobile_cap={mobile_cap if mobile_cap is not None else 'none'}")

    times = []
    for _ in range(max(1, args.repeat)):
        t0 = time.perf_counter()
        rows = project(dict(c))
        times.append(time.perf_counter() - t0)
    print(f"deterministic projection ({len(rows)} years): "
          f"best {min(times) * 1000:.0f} ms / avg {sum(times) / len(times) * 1000:.0f} ms over {len(times)} runs")

    mc_c = dict(c)
    mc_c["mc_sims"] = max(1, args.mc_sims)
    mc_c["mc_sensitivity_sims"] = 1  # time the core paths, not the sensitivity grid
    t0 = time.perf_counter()
    result = monte_carlo_exact_scalar(mc_c, n_sims=mc_c["mc_sims"])
    mc_elapsed = time.perf_counter() - t0
    per_path_ms = mc_elapsed / mc_c["mc_sims"] * 1000
    print(f"monte carlo ({mc_c['mc_sims']} paths): {mc_elapsed:.1f} s total, {per_path_ms:.1f} ms/path "
          f"(~{per_path_ms:.1f} s per 1000 paths)")
    print(f"return model: {(result or {}).get('portfolio_return_model', 'unknown')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
