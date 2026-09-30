"""Phase 1 items 4-6 (optimization refactor) acceptance criterion: "scalar
and vectorized engines agree within defined tolerances on selected
fixed-seed fixtures."

monte_carlo_exact_scalar already gets survivor economics exactly right (it
reruns the full deterministic engine per path with that path's own sampled
death years). Before this phase, the vectorized engine ignored first death
entirely, so its success_rate could differ materially from the scalar
engine's for a two-spouse household with survivor-sensitive inputs. This
test runs both engines end-to-end (the real monte_carlo()/
monte_carlo_exact_scalar() entry points, not the low-level helpers) on the
same fixed-seed fixture and asserts survivor economics being ON strictly
narrows the scalar-vs-vectorized success-rate gap relative to it being OFF.

NOTE on the absolute size of the remaining gap: the vectorized engine still
approximates tax with a single blended tax_drag ratio (Phase 3 of the
optimization-refactor plan -- "state-contingent tax approximation" -- is not
yet implemented), so a real double-digit-percentage-point gap can and does
remain even with survivor economics fully wired in (empirically ~0.11 vs.
~0.135 at this fixture/seed). This test is deliberately about THIS phase's
specific contribution (closing the survivor-economics portion of that gap),
not full scalar/vectorized agreement, which is Phase 3's job.

WI-404 (system review 2026-09-25-2, QA-006): this test used to sit behind
``@unittest.skipUnless(RUN_SLOW_MC_RECONCILIATION)``, an env var nothing in
the repo ever set, so it never ran. It now carries ``@pytest.mark.nightly``
(an engine-equivalence check -- the local fast tier and the nightly workflow
run it, the PR-tier CI filter skips it) and a reduced default path count
(``RETIREMENT_SURVIVOR_RECON_SIMS``, default 200; the old opt-in used 800),
with one Monte Carlo run shared by both assertions.

Running it again surfaced that the strict "ON narrows the gap" criterion no
longer holds on the current frozen fixture (measured 2026-09-30, seed 123:
n=800 scalar 0.611, gap ON 0.180 vs OFF 0.139; n=200 seeds 1/7/42 agree).
On this fixture the vectorized engine is already optimistic versus the
scalar engine (~0.80 vs ~0.61, the known tax_drag approximation), and
survivor economics moves it further in that same direction, so the
gap widens. That assertion is kept as a strict xfail so it is still
measured every run and flips to a hard failure the day it starts passing;
the loose sanity bound remains a normal assertion.

Resolved 2026-09-30 (documentation/archive/reports/
N1_MC_PARITY_RESIDUAL_DIAGNOSTIC_2026-09-30.md): the strict "ON narrows the
gap" premise is retired. It conflated two things. (1) Survivor economics
(spending step-down, survivor SS benefit, filing-status change) can only relieve
funding pressure, so it MUST raise the vectorized success rate -- ON > OFF on
identical paths, measured +2.0..+5.5pp over five seeds at n=200. (2) The level
bias against the scalar engine (~+17pp on this roth_policy=none fixture) is
pre-existing and comes from other components (tier-cascade tax funding, bucket
allocation order, and the credit-shelter-trust sequestration at first death
that the vectorized engine does not model), none of which survivor economics
touches. On a deterministic-replay skeleton with the credit-shelter
sequestration added, survivor economics ON lands within 0.2pp of the scalar
engine (paired-path agreement 96%), i.e. the survivor adjustment is directionally
correct; it just cannot be judged by a gap it was never responsible for. The test now asserts
the direction (ON >= OFF on the same seed, hence the same sampled paths) and
keeps the loose sanity bound.
"""

from __future__ import annotations

import copy
import os

import pytest

from conftest import TEST_INPUT_DIR
from src.data_io import load_csv, parse_client
from src.planning_engines import monte_carlo, monte_carlo_exact_scalar, project

pytestmark = pytest.mark.nightly

N_SIMS = int(os.environ.get("RETIREMENT_SURVIVOR_RECON_SIMS", "200"))
SEED = 123


def _base_config(n_sims: int):
    c = parse_client(load_csv(TEST_INPUT_DIR / "client_data.csv"), "")
    c["roth_policy"] = "none"
    c["plan_end"] = int(c["plan_start"]) + 30
    c["mc_sensitivity_sims"] = 1
    c["mc_wellness_shocks"] = False
    c["mc_sims"] = n_sims
    return c


@pytest.fixture(scope="module")
def reconciliation():
    c_on = _base_config(N_SIMS)
    base_rows = project(c_on)

    scalar_res = monte_carlo_exact_scalar(c_on, n_sims=N_SIMS, seed=SEED, base_rows=base_rows)
    vector_on_res = monte_carlo(c_on, n_sims=N_SIMS, seed=SEED, base_rows=base_rows)

    c_off = copy.deepcopy(c_on)
    c_off["mc_vectorized_survivor_economics"] = False
    vector_off_res = monte_carlo(c_off, n_sims=N_SIMS, seed=SEED, base_rows=base_rows)

    scalar_rate = scalar_res["success_rate"]
    return {
        "scalar_rate": scalar_rate,
        "scalar_se": scalar_res["success_rate_standard_error"],
        "vector_on_rate": vector_on_res["success_rate"],
        "vector_off_rate": vector_off_res["success_rate"],
        "gap_on": abs(scalar_rate - vector_on_res["success_rate"]),
        "gap_off": abs(scalar_rate - vector_off_res["success_rate"]),
    }


def test_survivor_economics_raises_vectorized_success(reconciliation):
    # Same seed => the ON and OFF runs sample identical returns, inflation and
    # death years, so the difference isolates the survivor adjustment. It can
    # only relieve pressure (lower survivor spending, survivor SS benefit), so
    # ON must not be below OFF; strictly above means the wiring is engaging.
    r = reconciliation
    assert r["vector_on_rate"] > r["vector_off_rate"], (
        f"survivor economics ON ({r['vector_on_rate']:.4f}) did not raise vectorized success above "
        f"OFF ({r['vector_off_rate']:.4f}) -- the survivor adjustment may not be engaging on this fixture"
    )


def test_success_rate_agrees_within_loose_sanity_bound(reconciliation):
    # Loose sanity bound, not a tight-agreement bar: guards against a FUTURE
    # regression making things much worse, without demanding scalar/vectorized
    # parity this phase never promised (full agreement is Phase 3's job, once
    # the vectorized engine's tax_drag approximation is state-contingent).
    r = reconciliation
    loose_bound = max(0.20, 10.0 * r["scalar_se"])
    assert r["gap_on"] <= loose_bound, (
        f"scalar success_rate {r['scalar_rate']:.4f} vs vectorized (survivor economics ON) "
        f"{r['vector_on_rate']:.4f}: gap {r['gap_on']:.4f} exceeds the loose sanity bound {loose_bound:.4f}"
    )
