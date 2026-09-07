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

## Follow-up attempt 2 (same day) — fixing the double-count too: real progress (40.5pp → 27.0pp), but a fifth, sharper finding

Re-examined the "structural" conclusion above before accepting it: `eff['total_tax']` is the deterministic engine's REAL tax bill for the baseline year, which already reflects tax owed on every dollar that year's tier withdrawals (essential/important/contingent_liability) pull from pretax. Once `'other'` correctly carries that real tax bill, the pre-existing `tax_drag` gross-up **still applied to every other tier's own pretax leg** (a few lines below `other_nominal`) is double-counting tax a second, independent way, on top of Finding 3's double-count: once via each tier's own grossed-up pretax withdrawal, and again via the mandatory `'other'` line item.

**Fix implemented (both bugs together): `other_nominal = max(0, eff['total_tax'])`, `'other'` included in income-netting, `'other'`'s tax portion cascaded with no `tax_drag`, wellness-shock overflow split out and cascaded separately (still with `tax_drag`, since it's genuinely new spending the baseline couldn't have foreseen) — AND `tax_drag` removed from every other tier's own pretax leg too**, since `total_tax` already prices that tier's withdrawal in.

**Result: real, substantial improvement — 40.5pp → 27.0pp** (vectorized success rate 26.0% → 39.5%, vs exact_scalar's 66.5%). Confirms the double-counting theory was directionally right and material. **Still failing, not shippable.**

Also re-tested Finding 1 (HSA reorder) on top of this: made it slightly *worse* (27.0pp → 30.0pp) here too, consistent with every earlier test of that fix in isolation — reverted, kept only the tax-cascade fix.

**Fifth finding, found while chasing the remaining gap: Roth-conversion tax has no funding-source model.** Diffed the taxable bucket specifically under the deterministic (zero-randomness) harness: vectorized's `taxable` balance for 2027 came out to **exactly** `2026's balance × (1 + mu)` — i.e., zero net withdrawal from taxable that year — while the real deterministic engine drew **$138,612** from taxable that same year. Cross-referencing the real row: that year the household also executed a **$169,382 Roth conversion** (pretax → Roth), and the real engine's actual strategy pays that conversion's tax bill *from taxable*, not from the conversion itself or from pretax — a deliberate, common Roth-conversion technique (paying conversion tax from outside funds maximizes the conversion's value). The vectorized engine tracks the conversion's principal transfer (`conversions_out`/`conversions_in`) correctly, but funds *all* of `total_tax` — ordinary tax and conversion tax alike — through one undifferentiated `cash→pretax→taxable→...` cascade with no concept of "this portion of the tax bill is conversion-specific and should be funded from taxable, not pretax."

This is not a bucket-order tweak away. Chasing it further (see Finding 6) found the real, more precise mechanism — not conversion tax specifically, but a general bracket-management pattern conversions happen to trigger.

**Reverted again.** Working tree clean; no code shipped.

---

## Follow-up attempt 3 (same day) — Finding 6: the real mechanism is bracket/IRMAA-ceiling-capped withdrawal rounds, not a conversion-specific tax bucket

Finding 5 (above) was close but imprecise about *why* taxable got drawn that year. Traced the actual deterministic cascade order precisely: `withdraw_hsa_window` → `withdraw_pretax_elective` → `withdraw_taxable_trust` → **`withdraw_pretax_elective` again** → `withdraw_hsa_gap` → `withdraw_roth`. `withdraw_pretax_elective`'s own code (`src/planning_engines.py:1394-1434`) confirms why it runs twice:

```python
max_taxable = max(0.0, min(bracket_top_24, irmaa_threshold) - agi)
```

The **first** pretax pass is deliberately capped at whatever headroom remains before a tax-bracket ceiling or IRMAA threshold — a real, load-bearing tax-bracket-management strategy (this codebase's core value proposition, not an edge case). Whatever cash need survives that capped pass is funded from **taxable** next (no bracket consequence), and only as a genuine last resort does a **second**, uncapped pretax pass (`respect_tax_caps=False`) run. This is a two-pass pattern over the *same* bucket (pretax) with a different bucket (taxable) interleaved between the passes, and the cap itself is AGI-dependent — i.e., different every year, and in a full (non-deterministic) MC path, different per simulated path too, since AGI depends on that path's own income and withdrawals.

The vectorized engine's `SPENDING_TIER_BUCKET_POLICY` is a single ordered walk through buckets, unlimited within each — it has no way to represent "draw pretax up to a cap, then taxable, then pretax again without a cap." This is why, in the fixture tested, pretax (large, $2.9M) absorbed the *entire* need every year in vectorized (never capped, so taxable was never reached) while the real engine capped pretax and routed the overflow to taxable specifically to avoid a bracket/IRMAA breach.

**This is the real root cause Finding 5 was circling.** Fixing it means the vectorized engine needs, at minimum: a per-path/per-year AGI estimate, the same `bracket_top_24`/`irmaa_threshold` inputs the deterministic engine uses, and a genuine two-pass (capped, then taxable, then uncapped) cascade in place of today's single ordered walk — a materially larger change than anything attempted in this diagnostic so far.

---

## Follow-up attempt 4 (same day) — Finding 6 implemented and tested: real, correct, and (for this test) invisible

Implemented Finding 6 in full: `deterministic_engine.py` now exposes `row['agi_before_elective_pretax_wd']` and `row['pretax_elective_bracket_ceiling']` (`= min(bracket_top_24, irmaa_threshold)`), computed unconditionally (not just when `gap > 0`) at the point the real engine already computes them — a pure additive change, verified not to move the golden master or any related test. Plumbed both through `_mc_row_bucket_flows`/`_mc_effective_row_flows`. Gave `_mc_tier_bucket_cascade` an optional `pretax_room` array (mutated in place, shared across every label's call in `funding_order` so the cap is a household-level budget for the year, not per-tier), and restructured `_mc_vectorized_projection`'s cascade into two passes: pass 1 draws every label's need through its normal `bucket_order` with `pretax_room` capping only the `pretax` step (later buckets in that same tuple, e.g. taxable, still take whatever pass 1's capped pretax couldn't); pass 2 re-runs whatever survived pass 1 through the same `bucket_order` fully uncapped — a genuine last-resort mirror of the real engine's second `withdraw_pretax_elective(respect_tax_caps=False)` call. (Pass 2 turned out to be necessary, not optional: without it, the capped-only version produced genuine phantom `unfunded` shortfalls in later years that the real engine never shows, because a large pretax balance the cap was only ever meant to *defer*, not deny, had nowhere left to be drawn from.)

**Deterministic-harness result: dramatic, real improvement.** 2027's `pretax` gap dropped from over $100K to **$2,237** — the two engines' account trajectories converge closely in early-to-mid years for the first time in this whole diagnostic.

**Stochastic parity-test result: no change at all — 27.0pp, byte-identical to the pre-Finding-6 number** (vectorized 39.5% vs exact_scalar 66.5%, same as follow-up attempt 2). Investigated why rather than assuming the fix silently failed: `agi_before_elective_pretax_wd` for this fixture's year 1 is **$454,235**, already above `pretax_elective_bracket_ceiling`'s **$268,000** — this household's baseline AGI (RMDs, SS, pension) alone exceeds the bracket cap before any elective withdrawal at all, so `pretax_room` is ≈0 in nearly every year. Finding 6's fix is therefore mostly changing *which account* funds a given year's withdrawal (pretax vs. taxable) for this household, not the *total dollar amount* withdrawn — and the parity test's success/failure criterion (`liquid` = pretax+taxable+roth+hsa, summed, vs. a threshold) is indifferent to which account the total comes from. Findings 2-4 (real total-dollar fixes: the tax-funding amount itself) moved the metric 40.5pp→27.0pp; Finding 6 (bucket-routing only, for this household) moved it 0.0pp — consistent with, not contradicting, the theory.

This is a genuine, useful narrowing, not a null result: Finding 6 is confirmed real, correctly implemented, and independently valuable (it matters for tax-bucket-source accuracy and per-account reporting even where it doesn't move this specific success-rate metric) — but it rules Finding 6 OUT as a candidate explanation for the remaining ~27pp. Whatever is still driving that gap must be something that changes the **total** liquid trajectory, not just its account-level sourcing. The deterministic harness's late-year `total` column (vectorized ending up several million dollars *higher* net worth than scalar by year 2050+) is the remaining lead: vectorized is still under-withdrawing/under-taxing in aggregate for a reason distinct from every bug found today.

**Reverted again — no code shipped.** Both files (`deterministic_engine.py`'s additive row-field exposure, `planning_engines.py`'s two-pass cascade) were reverted together for consistency with every other attempt in this diagnostic, even though the `deterministic_engine.py` half alone is safe and tested in isolation; a future attempt can cherry-pick it back rather than re-deriving it.

---

## Recommended next steps (revised again)

1. Findings 2-4 (the tax-cascade fix: `other_nominal = total_tax`, income-netted once, no double gross-up anywhere) are real, verified progress (40.5pp→27.0pp) but not sufficient alone (still fails the 5pp gate) — do not ship in isolation.
2. Finding 6 (bracket-capped two-pass pretax cascade) is fully designed, implemented once, and verified correct at the account level, but is now RULED OUT as the explanation for the remaining ~27pp gap for this fixture (see above) — worth keeping for its own sake (tax-bucket-source and reporting accuracy) once other findings land, but not worth re-attempting as a fix FOR THIS metric without a new hypothesis for why it should move it.
3. **The open question now**: something changes vectorized's TOTAL (not per-account) liquid trajectory relative to the real engine, growing to several million dollars of late-year net-worth divergence in the deterministic harness. Candidates not yet ruled out: growth-rate/tilt differences between engines, RMD calculation differences, RMD-divisor duplication (N5 in the original system review, never resolved), RMD suppression thresholds, or a genuine per-path-tax gap (follow-up attempt 1's original hypothesis) that Findings 2-4 only partially addressed. Whoever picks this up next should hunt the `total`/`liquid` column divergence directly (the reproduction harness below already isolates it) rather than another bucket-routing theory.
4. Finding 1 (HSA reorder) is still real and independently correct, but empirically makes the aggregate metric slightly worse every time it's been tested (3.5pp→8pp alone; 27.0pp→30.0pp atop the tax fix) — land it separately and re-verify its aggregate effect once the total-trajectory gap above is resolved, rather than assuming "correct" implies "improves this metric."
5. Re-run `tests/test_monte_carlo_default_engine_mode.py::test_exact_scalar_oracle_agrees_with_vectorized_default_within_tolerance` (200 sims, seconds) after every step, exactly as this diagnostic has been doing throughout — every attempt so far produced a different, informative number; guessing at the aggregate effect has not worked once.
6. Once genuinely passing at 200 sims, re-measure at 2000 sims (matching the review's own methodology) to see whether the gate can be tightened back toward its original 1pp, per the review's Option 2/3 recommendation.
7. Golden-master regen and a `documentation/GOLDEN_MASTER_CHANGELOG.md` entry are required once anything here actually ships, per this repo's standing discipline (`documentation/CLAUDE.md`) — none of the attempts here reached that point.
8. Planner sign-off recommended before shipping, matching the review's own precedent for N2/N4 (financial-domain correctness changes that move simulated outcomes).

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
