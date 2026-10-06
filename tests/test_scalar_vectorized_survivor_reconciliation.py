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
longer holds on the current frozen fixture (measured 2026-09-30 before the replay-funding change, seed 123:
n=800 scalar 0.611, gap ON 0.180 vs OFF 0.139).
On this fixture the vectorized engine is already optimistic versus the
scalar engine (~0.80 vs ~0.61, the known tax_drag approximation), and
survivor economics moves it further in that same direction, so the
gap widens. That assertion is kept as a strict xfail so it is still
measured every run and flips to a hard failure the day it starts passing;
the loose sanity bound remains a normal assertion.

Resolved 2026-09-30 (documentation/archive/reports/
N1_MC_PARITY_RESIDUAL_DIAGNOSTIC_2026-09-30.md): the strict xfail is gone.
The premise was sound but the gap it measured was dominated by other
vectorized-engine defects (tax funding dropped, tier-ordered bucket allocation,
Roth barred from non-essential tiers, and no credit-shelter-trust
sequestration at first death). With the headline funding decision replaying the
deterministic engine's bucket draws and the trust modelled, the measured gap on
this fixture is scalar 0.611 vs vectorized ON 0.650 / OFF 0.670 (n=800, seed
123): ON narrows it, as originally intended.
"""

from __future__ import annotations

from tests.plan_fixture import plan_config
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
    c = plan_config()
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


def test_survivor_economics_narrows_scalar_vectorized_gap(reconciliation):
    # Primary acceptance evidence for the phase that wired survivor economics
    # into the vectorized engine: ON must narrow the gap to the scalar
    # engine's (correct) answer relative to OFF. Strict inequality -- a flat
    # tie would mean the fix isn't engaging. Holds again (was a strict xfail
    # 2026-09-30) now that the vectorized engine models the credit-shelter
    # trust at first death: survivor economics raises success, the trust
    # sequestration lowers it, and ON lands closest to the scalar engine.
    r = reconciliation
    assert r["gap_on"] < r["gap_off"], (
        f"survivor economics ON ({r['gap_on']:.4f} gap to scalar) did not narrow the gap "
        f"relative to OFF ({r['gap_off']:.4f}) -- the fix may not be engaging on this fixture"
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
