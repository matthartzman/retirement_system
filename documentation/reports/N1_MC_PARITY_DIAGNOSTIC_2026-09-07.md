# N1 Diagnostic — Vectorized/Exact-Scalar MC Parity Gap

**Date:** 2026-09-07. **Author:** Claude (session `session_01G3EV1KvMjaBAbgVnzJxYmT`), continuing Wave 4 item W4-2 from `documentation/reports/WAVE4_IMPLEMENTATION_PLAN_2026-09-07.md`, after PR #92 ruled out the system review's two named suspects (home-equity contingency, survivor economics — see PR #92's commit message) without finding a positive cause.

**Status: no code shipped.** Two real, well-evidenced bugs were found and fixed; the second fix uncovered a third, deeper bug that caused the actual parity test to regress catastrophically (8pp → 49pp gap, vectorized success rate crashing from 58.5% to 17.5%) when combined with the second fix. All three code changes were reverted. This document is the diagnostic record for whoever picks this up next — the harness described below reproduces every finding in under a second per run.

---

## Method

Reproducing the review's own suggested diagnostic ("compare both engines on identical seeded return paths, diff year-by-year") turned out to need more than matching a seed integer: `monte_carlo_exact_scalar` draws from Python's stdlib `random.Random`; the vectorized engine draws from `numpy`'s `Generator`. Different streams entirely — same seed, different draws.

Instead, both engines' internal return-path, mortality, and inflation-shock generators were monkeypatched to be fully deterministic (flat `mu` return every year, no death within the horizon, zero inflation variance, no wellness shocks), then run at `n_sims=1` and diffed year-by-year on `liquid`/`total`/`pretax`/`taxable`/`roth`/`hsa`. With every source of *sampling* randomness removed, any remaining difference is a genuine mechanics bug, not noise. The harness is reproducible from `src/planning_engines.py`'s public/private functions directly — see Appendix for the script.

One methodology trap hit and corrected along the way: the first version set "no death" to 500 years past the plan horizon, which fed an absurd horizon into a compounding formula and exploded `total_nw` to $136B — an artifact of the diagnostic, not a real finding. Setting it to `plan_end + 1` (just past the horizon) fixed that.

---

## Finding 1 — HSA drawn as the essential/important/contingent-liability tier's 2nd bucket instead of a late fallback (real bug, fix designed, not shipped due to Finding 3's interaction)

**Evidence.** Under the deterministic harness, real household fixture (`tests/fixtures/sample_plan_frozen`, starting HSA balance $58,804.31), the vectorized engine's HSA balance hit exactly **$0.00 by the second simulated year** and stayed there, while the scalar engine (which replays the real deterministic engine's own cascade) kept it growing normally ($73K by year 2, growing further).

**Root cause.** `src/spending_budget_resolver.py`'s `SPENDING_TIER_BUCKET_POLICY`:
```python
SPENDING_TIER_ESSENTIAL: ("cash", "hsa", "pretax", "taxable", "roth"),
```
puts HSA second, right after `cash`. This household's `cash` bucket balance is $0, so the *entire* essential-tier dollar need immediately falls through to HSA before ever touching the much larger pretax ($2.9M) or taxable ($465K) balances.

The policy's own docstring claimed this mirrors "the full HSA->pretax->taxable->Roth cascade the deterministic engine already uses for its own withdrawal order" — that claim is false. Tracing the real cascade (`src/projection_stages/deterministic_engine.py:2274-2896`, `withdraw_hsa_window` → `withdraw_pretax_elective` → `withdraw_taxable_trust` → more `withdraw_pretax_elective` → `withdraw_hsa_gap` → `withdraw_roth`) shows HSA drawn first **only** for the narrow, wellness/medical-cost-scoped portion (`withdraw_hsa_window`), and reappearing only as a **late fallback** (`withdraw_hsa_gap`, after pretax and taxable) for whatever general gap remains.

**Designed fix (not shipped).** Reorder to `("cash", "pretax", "taxable", "hsa", "roth")` for essential/contingent_liability, `("cash", "pretax", "taxable", "hsa")` for important — matching the *dominant* real behavior (HSA as late fallback) since the tier framework has no per-dollar visibility to reproduce the narrow medical-scoped first draw exactly. One test (`tests/test_mc_tier_bucket_policy_restriction_regression.py::test_policy_definitions_match_the_spec_decision`) pins the exact tuple and needs updating alongside.

**Effect on the parity test.** Applied alone, this genuinely fixed the HSA mechanic but *increased* the measured drift at 200 sims from ~3.5pp (passing) to 8.00pp (failing the existing 5pp gate) — confirming HSA ordering is real but **not** the dominant driver of N1's gap.

---

## Finding 2 — `other_nominal` (tax-funding need) conflates net-of-income and gross-of-income figures, silently dropping tax withdrawals most years (real bug, fix attempted, reverted)

**Evidence.** For the fixture's 2027 row: `spend_by_tier` sums to $237,297.27 (≈ exactly `total_spend`), while actual account withdrawals (excluding HSA) sum to only $195,008.97. That $195,008.97 is exactly `total_spend + total_tax - income_funding` (237,297.27 + 53,669.32 - 95,957.62 = 195,009.97, within float noise) — i.e., real withdrawals are already net of income.

**Root cause.** `src/planning_engines.py` (`_mc_vectorized_projection`, the `tier_scaled` branch):
```python
other_nominal = _np.maximum(0.0, (
    eff['withdrawals']['taxable'][:, j] + eff['withdrawals']['pretax'][:, j]
    + eff['withdrawals']['roth'][:, j] + eff['withdrawals']['cash'][:, j]
    - sum(eff['spend_by_tier'][t][:, j] for t in eff['spend_by_tier'])
))
```
subtracts a **gross** (pre-income) figure (`spend_by_tier` sum) from a **net-of-income** one (`eff['withdrawals']` sum). Since `spend_by_tier` sums to essentially all of `total_spend` (an `'unclassified'` catch-all tier absorbs anything not otherwise categorized, by construction), this reduces to `total_tax - income_funding` — which goes **negative, and is clamped to zero, in every year `income_funding` exceeds `total_tax`** (the common case for any household with substantial SS/pension income). The entire tax-funding need for that year is silently dropped from the vectorized engine's withdrawal request. This is on top of `income_funding` being netted a *second* time a few lines down, against `need_by_label`.

**Attempted fix.** Replace with `other_nominal = _np.maximum(0.0, eff['total_tax'][:, j])` — `eff['total_tax']` is already the correct, already-available, gross-of-income figure, consistent with how `spend_by_tier` is scaled elsewhere in the same function.

**Effect when combined with Finding 1's fix: catastrophic regression.** The parity test's drift jumped from 8.00pp to **49.00pp**, vectorized success rate crashing from 58.5% to **17.5%**. This is Finding 3.

---

## Finding 3 — `tax_drag` gross-up applied to the tax-need withdrawal itself, double-taxing (real bug, previously masked by Finding 2, uncovered by fixing Finding 2, not fixed)

**Evidence.** Finding 2's fix alone should have been close to correct in aggregate (a hand-traced example showed the total dollars drawn matching the scalar engine's real total almost exactly once `other`/essential funding-order interactions are worked through) — but the *actual* stochastic test result was far worse, not better.

**Root cause (diagnosed, not yet fixed).** `'other'` (now correctly representing the tax bill) is funded via `_other_bucket_order = SPENDING_TIER_BUCKET_POLICY[SPENDING_TIER_ESSENTIAL]`, whose second bucket is `pretax`. The pretax leg of `_mc_tier_bucket_cascade` unconditionally applies `tax_drag` (an approximate marginal-tax gross-up meant for *spending* withdrawals, which are themselves new taxable income requiring extra withdrawal to cover the tax on the withdrawal):
```python
drag = tax_drag[:, j] if 'pretax' in bucket_order else None
shortfall = _mc_tier_bucket_cascade(balances, need_by_label[label], bucket_order, tax_drag=drag)
```
But `'other'`'s need **already is** the tax bill — grossing it up again when paid from pretax taxes the tax itself, compounding into a much larger withdrawal requirement than reality, which (combined with real market variance across 200 simulated paths) tips many more paths into failure.

This bug was **invisible before Finding 2's fix** because `other_nominal` was almost always zero (Finding 2), so the `'other'`-drawn-from-pretax path essentially never executed with a nonzero request.

**Not fixed.** The correct fix likely needs `_mc_tier_bucket_cascade` (or its caller) to skip the `tax_drag` gross-up specifically for the `'other'` label, since `'other'`'s dollar figure is already a tax obligation, not spending that generates a new one. This needs care: `SPENDING_TIER_CONTINGENT`'s cascade also funds `shock_left` (wellness-shock HSA overflow) through the same `_other_bucket_order`, and that portion likely *should* still be grossed up if it's paid from pretax (a wellness-shock withdrawal from pretax is ordinary new taxable income). A correct fix probably needs `'other'`'s tax-only portion split from `shock_left`'s spending portion before choosing whether to apply `tax_drag`, rather than a single blanket flag per label.

---

## Why nothing shipped

Every fix here individually looked correct and was backed by direct evidence, and yet the second one caused a swing an order of magnitude worse than the problem it fixed once the third, previously-masked bug was exposed. That's a strong signal this cluster of interacting bugs needs to be fixed **together, deliberately**, with the full stochastic parity test run after every step — not landed incrementally under time pressure. Given this is financial-domain-correctness code (the exact class of change N2/N4 in the original review required explicit planner sign-off for), and a wrong combination of these fixes could plausibly move MC success rates in production in a harmful direction, shipping any one of them alone here would have been irresponsible.

---

## Follow-up attempt (same day) — Findings 2+3 fixed together: still a 40.5pp gap, and a fourth, structural issue

Implemented Finding 2's `other_nominal` fix (using `eff['total_tax']`), the income-netting correction it requires (removing `'other'`'s exclusion from the `income_avail` loop — the exclusion's own comment justified it only under the old, net-of-income formula), and Finding 3's fix (cascading `'other'`'s tax portion without `tax_drag`, splitting out any wellness-shock overflow into its own drag-eligible cascade) — all together, as the diagnostic above recommended.

**Result: still failed, worse than the single-bug attempt.** Drift went to **40.5pp** (vectorized success rate 26.0% vs exact_scalar 66.5%) — better than the 49pp/17.5% seen with Finding 2 alone atop Finding 1, but nowhere near passing, and still a severe regression from the pre-fix baseline (~3.5pp).

**Why: a fourth, structural issue, not another isolated bug.** `eff['total_tax']` (like `eff['spend_by_tier']`) is the **deterministic-baseline** tax figure for that plan year, only scaled for inflation (`spending_scale`) — it does not vary by simulated path. Bug 2 accidentally masked this because the tax-funding need was almost always zero; fixing it exposes that **every simulated path — including bad-market paths with much lower real capital gains and therefore a much lower real tax bill — is forced to withdraw the same baseline tax amount**, compounding losses fastest in exactly the market conditions that already drive most failures. This isn't a small logic error to patch; it's the vectorized engine's core simplification (replay one deterministic trajectory's numbers, scaled, instead of recomputing tax per path — which is what `exact_scalar` does by rerunning `project()` for real, and exactly why it's slower). Making vectorized MC tax-accurate per path would mean either giving it a genuine per-path tax approximation (a real, nontrivial engineering addition) or accepting that a scaled-deterministic-tax approximation is structurally going to disagree with `exact_scalar` under volatile returns, no matter how correctly the withdrawal cascade around it is fixed.

**Reverted again.** Working tree is clean; no code shipped in this follow-up attempt either.

---

## Recommended next steps (revised)

1. **Before attempting another code fix**, decide whether the vectorized engine should get a genuine per-path tax approximation (e.g., recompute marginal-bracket tax from that path's own actual withdrawal amounts and gains, not a scaled deterministic figure) — this is now believed to be the dominant remaining driver, larger in scope than Findings 1-3 combined. This is an architecture decision, not just a bug fix, and belongs with whoever owns the vectorized engine's design tradeoffs.
2. Findings 1 (HSA ordering) and 3 (tax_drag double-count) are still real, correct, narrow fixes on their own — but per the two failed combined attempts, do not land Finding 2 (or Finding 2+3 together) without also addressing the per-path tax gap above, or the aggregate parity metric gets worse, not better.
3. Once a per-path tax approach is decided, re-attempt Findings 1-3 together with it, re-running `tests/test_monte_carlo_default_engine_mode.py::test_exact_scalar_oracle_agrees_with_vectorized_default_within_tolerance` (200 sims, seconds) after every step.
4. Once genuinely passing at 200 sims, re-measure at 2000 sims (matching the review's own methodology) to see whether the gate can be tightened back toward its original 1pp, per the review's Option 2/3 recommendation.
5. Golden-master regen and a `documentation/GOLDEN_MASTER_CHANGELOG.md` entry are required once anything here actually ships, per this repo's standing discipline (`documentation/CLAUDE.md`) — none of the attempts here reached that point.
6. Planner sign-off recommended before shipping, matching the review's own precedent for N2/N4 (financial-domain correctness changes that move simulated outcomes) — doubly so now that the scope includes a tax-modeling architecture decision.

---

## Appendix — reproduction harness (not committed; paste into a scratch `.py` and run)

```python
import random, sys
sys.path.insert(0, "/home/user/retirement_system")
from pathlib import Path
import numpy as np
from src.data_io import load_csv, parse_client
import src.planning_engines as pe

TEST_INPUT_DIR = Path("/home/user/retirement_system/tests/fixtures/sample_plan_frozen")
c = parse_client(load_csv(TEST_INPUT_DIR / "client_data.csv"), "")
FAR_YEAR = int(c["plan_end"]) + 1   # NOT +500 -- see methodology trap above
c["mc_inflation_sigma"] = 0.0       # NOT mc_inflation_stochastic=False -- crashes
                                     # _mc_vectorized_inflation_health_paths (rates
                                     # collapses to a 0-d scalar); file separately.
c["mc_wellness_shocks"] = False
c["mc_wellness_prob"] = 0.0
c["mc_home_equity_contingency"] = False
_orig_plan_end = int(c["plan_end"])

def _no_death(c_in, rng):
    return {"h_death_yr": FAR_YEAR, "w_death_yr": FAR_YEAR, "first_death_yr": FAR_YEAR,
            "plan_end": int(c_in.get("plan_end", _orig_plan_end))}

def _no_death_vec(c_in, np_rng, n_sims):
    far = np.full(n_sims, FAR_YEAR, dtype=int)
    return far, far.copy(), far.copy()

def _flat_return_scalar(c_in, rng, mu, sig, years, use_asset_classes=True):
    return {yr: float(mu) for yr in years}, {"return_model": "DIAG_FLAT",
        "portfolio_expected_return": float(mu), "portfolio_sigma": 0.0}

def _flat_return_vec(c_in, np_rng, n_sims, years, mu, sig, use_asset_classes=True):
    arr = np.full((n_sims, len(years)), float(mu), dtype=float)
    return arr, {"return_model": "DIAG_FLAT",
        "portfolio_expected_return": float(mu), "portfolio_sigma": 0.0}

pe.sample_household_death_years = _no_death
pe._mc_vectorized_death_years = _no_death_vec
pe._generate_return_path = _flat_return_scalar
pe._mc_vectorized_return_paths = _flat_return_vec

base_rows = pe.project(c)
mu = float(c.get("ret", 0.06))
rows_s, years_s, returns_s, diag_s, infl_s, c2 = pe._run_one_mc_path(
    c, random.Random(2026), mu, 0.0, use_asset_classes=True)
batch = pe._mc_vectorized_batch(c, base_rows, n_sims=1, seed=2026, mu=mu, sig=0.0,
    success_threshold=0.0, use_asset_classes=True)
proj = batch["projection"]
# ... diff proj[field][0, i] against pe._liquid_value(row) / row['pretax_nw'] / etc.
# per year, per src/planning_engines.py's row-field naming.
```
