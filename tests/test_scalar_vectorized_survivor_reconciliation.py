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

Running it again surfaced that the original criterion -- "survivor economics
ON strictly narrows the scalar-vs-vectorized success-rate gap" -- does not
hold on the current frozen fixture (measured 2026-09-30, seed 123: n=800
scalar 0.611, vectorized ON ~0.79 / OFF ~0.75, so gap ON 0.180 vs OFF 0.139;
n=200 seeds 1/7/42 agree). The premise conflated two effects. The vectorized
engine is already optimistic versus the scalar engine (the known tax_drag
approximation, tracked separately), so a *correct* survivor adjustment, which
lowers household spending after a first death and therefore raises success,
lifts an already-high rate and widens the gap. The test now asserts what
survivor economics is actually for: turning it ON moves the vectorized success
rate in the survivor-expected direction (not down) and the gap to the scalar
engine stays within the loose sanity bound. Closing the level bias itself is
tracked in documentation/reference/BACKLOG.md (vectorized/scalar parity).
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


def test_survivor_economics_raises_vectorized_success_rate(reconciliation):
    # Survivor economics cuts household spending after a first death, so with it
    # ON the vectorized success rate must not fall below the OFF rate. (It is
    # deliberately NOT asserted to narrow the gap to the scalar engine: see the
    # module docstring.)
    r = reconciliation
    assert r["vector_on_rate"] >= r["vector_off_rate"], (
        f"survivor economics ON ({r['vector_on_rate']:.4f}) lowered the vectorized "
        f"success rate relative to OFF ({r['vector_off_rate']:.4f}); the survivor "
        f"adjustment is expected to lower spending and so raise success"
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
