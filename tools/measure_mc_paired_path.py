#!/usr/bin/env python
"""Measure the vectorized replay headline against the exact scalar engine (WI-036).

For each (shape, Roth regime, seed) cell the SAME sampled paths go to both
engines (``tests/paired_path_harness.py``); the signed gap is vectorized minus
scalar success rate, in percentage points. Shapes are the synthetic golden-master
households so the study needs no client data and is reproducible.

    python tools/measure_mc_paired_path.py --n 1000 --seeds 11 5 3 --out result.json
    python tools/measure_mc_paired_path.py --n 40 --seeds 11 --shapes baseline_balanced_couple

Scalar runs cost roughly 0.3 s per path, so the full study takes about an hour
on four cores. Results are for the measurement document and the default-tier
bounds; this tool never writes a test fixture.
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DEFAULT_SHAPES = (
    "baseline_balanced_couple",
    "single_filer",
    "early_survivor_compression",
    "split_claiming_spousal",
    "depletion_thin_portfolio",
)


def build_config(shape: str, regime: str, n: int) -> dict:
    from src.data_io import build_plan_from_json
    from src.plan_config import ensure_engine_config
    from src.planning_engines import optimize_roth_conversion_strategy
    from tests.paired_path_harness import prepare_mc_config
    from tests.synthetic_plans import SCENARIOS

    sc = SCENARIOS[shape]
    plan = sc.plan()
    plan["assumptions"]["roth_policy"] = regime
    c = ensure_engine_config(build_plan_from_json(plan, ""), source="synthetic")
    if sc._override is not None:
        sc._override(c)
    if regime == "optimize_terminal_tax":
        c = ensure_engine_config(optimize_roth_conversion_strategy(c), source="synthetic.optimized")
    c["roth_policy"] = regime
    return prepare_mc_config(c, n)


def run_cell(task: tuple[str, str, int, int]) -> dict:
    shape, regime, seed, n = task
    from tests.golden_pricing import frozen_holdings_prices
    from tests.paired_path_harness import _paired_success

    with frozen_holdings_prices():
        scalar_ok, vec_ok = _paired_success(build_config(shape, regime, n), n, seed)
    return {
        "shape": shape, "regime": regime, "seed": seed, "n": n,
        "scalar": float(scalar_ok.mean()), "vectorized": float(vec_ok.mean()),
        "gap_pp": round(100.0 * float(vec_ok.mean() - scalar_ok.mean()), 2),
        "agreement": float((scalar_ok == vec_ok).mean()),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--n", type=int, default=1000)
    ap.add_argument("--seeds", type=int, nargs="+", default=[11, 5, 3])
    ap.add_argument("--shapes", nargs="+", default=list(DEFAULT_SHAPES))
    ap.add_argument("--regimes", nargs="+", default=["none", "fill_to_bracket", "optimize_terminal_tax"])
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 1)
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args()

    tasks = [(s, r, seed, a.n) for s, r, seed in itertools.product(a.shapes, a.regimes, a.seeds)]
    results = []
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        for res in pool.map(run_cell, tasks):
            results.append(res)
            print(f"{res['shape']:28s} {res['regime']:22s} seed={res['seed']:<3d} "
                  f"gap={res['gap_pp']:+6.2f}pp agree={res['agreement']:.3f}", flush=True)
            if a.out:
                a.out.write_text(json.dumps(results, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
