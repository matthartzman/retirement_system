# N1 Residual Diagnostic — Vectorized vs. Exact-Scalar MC Success-Rate Gap

**Date:** 2026-09-30. **Base:** `claude/amazing-thompson-xjimi9` (PR #153) @ `43bd5c6`. **Successor to:** `N1_MC_PARITY_DIAGNOSTIC_2026-09-07.md` / `N1_PER_PATH_ENGINE_DESIGN_2026-09-07.md`.

**Status: no engine change shipped.** The gap is now decomposed component by component, with measured contributions. One combination (a deterministic-replay skeleton plus credit-shelter-trust sequestration) reproduces the scalar engine to within 1pp on both roth policies and 96% path-level agreement, but adopting it reverses an owner-approved product decision (tier bucket restrictions) and moves headline MC outputs, so it is proposed, not shipped. What did ship: a paired-path regression test that replaces noisy gates with a low-noise one, a corrected premise for the survivor reconciliation test (the strict xfail is retired), and a measurement note on the 10pp drift gate. The experiment patch that produced every number below is committed alongside this report.

---

## 1. Headline

| Fixture / config (frozen sample plan, 30-yr horizon, wellness shocks off) | scalar | vectorized (survivor ON) | signed gap (vec − scalar) |
|---|---|---|---|
| `roth_policy=none`, n=800, seed 123 (the survivor reconciliation test) | 0.611 | 0.791 (OFF: 0.750) | **+18.0pp** (OFF +13.9) |
| default `roth_policy=fill_to_bracket`, n=800, seed 123 | 0.675 | 0.625 (OFF: 0.574) | **−5.0pp** |
| same, **identical paths**, n=1000, seed 11, `none` | 0.631 | 0.804 | +17.3pp (path agreement 82.7%) |
| same, **identical paths**, n=1000, seed 11, default | 0.673 | 0.609 | −6.4pp (path agreement 90.8%) |

Three facts the earlier framing missed:

1. **The two gaps have opposite signs and different causes.** Under `roth_policy=none` the vectorized engine is ~17pp too optimistic. Under the default policy (the regime the 10pp drift gate runs in) it is ~5pp too *pessimistic*. The small default-regime gap is a net of two large offsetting biases (§3), not evidence the engine is nearly right.
2. **The 10pp drift gate is mostly sampling noise.** The two engines draw from different RNG streams (stdlib `random` vs numpy), so a 200-path success-rate difference has ~4.8pp standard error. The gate reads exactly 10.00pp at n=200/seed 2026 (vec 0.565 vs scalar 0.665), 4.6pp at n=800/seed 2026, 4.0pp at n=800/seed 7. The "5→10pp growth over four changes" in the gate's docstring is largely this noise plus a true bias of about −4 to −6pp.
3. **Return generation is not a component.** 4,000 draws from each generator: annual mean 6.63% vs 6.70%, std 12.2% vs 12.2%, lag-1 autocorrelation 0.155 vs 0.150, 31-year geometric-mean percentiles within 0.15pp. Sampled paths in the two engines are statistically equivalent; the gap is mechanics.

## 2. Method

- **Paired-path harness** (now `tests/test_scalar_vectorized_paired_path_agreement_regression.py::_paired_success`). One set of paths (death years, asset-class returns, inflation/medical/SS/bracket indices) is sampled with the vectorized generators and fed to both engines: `_mc_vectorized_projection` for the vectorized side, and `_clone_for_mc` + injected `return_by_year` / index dicts + `project()` for the scalar side. Any disagreement is a mechanics difference, with no sampling noise. This is the single most useful new tool: it converts an unattributable ±5pp gap into per-path evidence (which paths, which year, which bucket).
- **Deterministic flat harness** (the 09-07 method, still valid): flat returns, no deaths, `n_sims=1`, year-by-year account diff.
- **Experiment flags** (`N1_MC_PARITY_RESIDUAL_EXPERIMENTS_2026-09-30.patch`, *not applied to the tree*): `c['_x_mode']` tokens toggle each candidate change so it can be measured alone and in combination — `other` (tax-funding need), `nodrag` (drop the pretax gross-up), `hsa` (HSA as late fallback), `rothall` (let Roth back every tier), `replay` (bypass the tier cascade and replay the deterministic per-bucket draws), `cst` (credit-shelter sequestration at first death), `ptax` (tax = fixed part + marginal on pretax draw). Apply with `git apply` on `43bd5c6`.

## 3. Components

All figures: paired n=1000, seed 11, survivor economics ON, signed vec − scalar success in percentage points, changes measured **one at a time on the shipping engine** unless noted. Interactions are strong (§3.8), so these do not sum.

| # | Component | effect on vec success, `none` (gap +17.3) | effect, default (gap −6.4) | verdict |
|---|---|---|---|---|
| A | Tax-funding need dropped (`other_nominal` ≡ 0) **+** blended `tax_drag` gross-up (coupled, §3.1) | fix both: −18.6 → gap **−1.3**, agree 92.5% | fix both: −20.1 → gap **−26.5** | real bug; fix is regime-dependent |
| B | HSA ordered 2nd instead of late fallback (§3.2) | −4.0 | −5.5 | real bug (small) |
| C | Tier policy bars Roth from `important`/`discretionary` (§3.3) | +8.6 if lifted | **+27.2** if lifted | **by design** (owner decision); dominant offset |
| D | Bucket allocation follows tier policy, not the deterministic engine's order (§3.4) | see replay row | see replay row | structural |
| E | Credit-shelter trust sequesters taxable/cash at first death, not modeled (§3.5) | −0.7 alone; −5.7 on a replay skeleton | −0.9 alone; −2.3 on replay | real, well understood |
| F | Survivor economics ON vs OFF (§3.6) | +4.6 | +6.1 | correct direction; not a source of the gap |
| G | Residual: per-path tax/RMD convexity (§3.7) | replay+E: gap **−0.2**, agree **96.2%** | replay+E: gap **−0.9**, agree **96.5%** | small, unfixed |

Replay skeleton = faithfully replay the deterministic engine's per-bucket withdrawals (scaled by path inflation), fall back to any bucket on shortfall, no tax gross-up — i.e. the pre-tier-cascade branch (`tier_scaled == {}`) minus `tax_drag`:

| variant | none: vec / gap / agree | default: vec / gap / agree |
|---|---|---|
| shipping engine | 0.804 / +17.3 / 82.7% | 0.609 / −6.4 / 90.8% |
| replay, drag on | 0.476 / −15.5 / 84.3% | 0.527 / −14.6 / 85.2% |
| replay, no drag | 0.686 / +5.5 / 93.1% | 0.687 / +1.4 / 96.0% |
| **replay, no drag, + CST** | **0.629 / −0.2 / 96.2%** | **0.664 / −0.9 / 96.5%** |
| replay no drag, survivor OFF | 0.648 / +1.7 / 96.5% | 0.657 / −1.6 / 96.0% |

(scalar: 0.631 / 0.673.)

### 3.1 Tax funding: `other_nominal` is still ≡ 0, and `tax_drag` papers over it (09-07 Findings 2/3, re-confirmed)

`_mc_vectorized_projection` still computes `other_nominal = max(0, Σwithdrawals − Σspend_by_tier)`. `spend_by_tier` sums to `total_spend` (gross of income) while withdrawals are net of income, so this is `tax − income_funding`, clamped at 0. Measured on the frozen plan: **`other_nominal` is exactly 0 in every one of 31 years**. Across the horizon the tier cascade requests Σ max(0, S−I) = $3.81M of account draws against the deterministic engine's own $5.26M — a 27% under-draw, i.e. essentially all of the tax bill. The pretax `tax_drag` gross-up (`total_tax / gross_income`, 0.02–0.27, applied to pretax draws only) recovers part of that by accident. With `drag` removed and `other = max(0, tax − max(0, income − S))` (tax funded net of income left over after the spending tiers, no second gross-up — the correct accounting identity), the deterministic flat harness (`none` regime, HSA fix also applied) lands within $35K of the scalar liquid trajectory through 2034 and $0.22–0.46M by 2038–2046 (the shipping engine: +$0.23M at 2030, +$0.84M at 2038, +$1.5M at 2044; residual composition drift is §3.4), and under `roth_policy=none` the paired success rate matches the scalar engine (0.618 vs 0.631).

This fix reproduces 09-07's outcome in the default regime — success collapses to 0.41 (gap −26.5). That is not a new bug in the fix; it is Component C (§3.3) becoming visible once the optimism that was masking it is removed. 09-07 attributed it to "the fifth structural issue"; the paired data says it is the tier policy's Roth exclusion (with Roth allowed too, the combination is 0.74–0.77 in both regimes).

### 3.2 HSA ordering (09-07 Finding 1, re-confirmed)

`SPENDING_TIER_BUCKET_POLICY[essential/contingent]` draws HSA second. Deterministic flat harness: vectorized HSA is **$0 by 2029** while the scalar engine's grows to ~$92K by 2029. Moving HSA to a late fallback lowers success 4.0pp (`none`) / 5.5pp (default) on the shipping engine — right direction against the optimistic regime, wrong against the pessimistic one. Pinned by `test_policy_definitions_match_the_spec_decision`; a deliberate edit.

### 3.3 Tier policy bars Roth from `important`/`discretionary` — by design, and the dominant offset

`SPENDING_TIER_BUCKET_POLICY` (`important`: cash/hsa/pretax/taxable; `discretionary`: cash/taxable/pretax) is an owner-approved product decision (recorded in `OPTIMIZATION_REFACTOR_STATUS.md`; pinned by `tests/test_mc_tier_bucket_policy_restriction_regression.py`). The scalar engine's cascade ends with `withdraw_roth` for any gap. So a path that has run out of pretax/taxable but holds a large Roth balance is **funded** in the scalar engine and **failed** in the vectorized one. Letting Roth back the two tiers raises vectorized success by +8.6pp (`none`) and +27.2pp (default) — Roth is the large account under `fill_to_bracket` conversions. **This is a definitional difference in what "success" means, not an approximation error.** It is not a bug to fix without the owner deciding whether the headline success rate should reflect "funded as asked" (scalar's meaning) or "funded within tier buckets" (vectorized's meaning); today the two engines answer different questions and are compared as though they answered the same one.

### 3.4 Bucket allocation order

The vectorized cascade walks each tier's bucket tuple; the deterministic engine does HSA-window → bracket-capped pretax → taxable → uncapped pretax → HSA gap → Roth. On the frozen plan (2035, flat returns) the vectorized engine holds pretax $2.07M / taxable $0.13M against the scalar engine's $1.41M / $0.82M: same total, different composition. Composition matters because (a) it decides what taxable-account sequestration (E) can remove, (b) it decides how much stays tax-deferred and later faces RMDs, and (c) `discretionary` drains taxable first. The replay skeleton (`replay, no drag`) tracks the scalar trajectory to within $11K per bucket through 2034 in the flat harness and cuts the shipping engine's gap from +17.3 to +5.5pp (`none`) and −6.4 to +1.4pp (default). It is what makes E measurable.

### 3.5 Credit-shelter trust at first death (new)

`apply_spousal_rollover_and_cst_funding` moves up to `min(cs_amount, il_cst_shelter_cap)` ($4M on this plan; `cs_enabled=True`) from the survivor's **taxable and cash** accounts into a trust that is "not available to the survivor withdrawal cascade" and is excluded from `_liquid_value`. Example, paired path 56 (wife dies 2037): scalar taxable $799K → $0 that year, `cst_balance` $745K, liquid −$1.4M in one year (−$0.68M of it market); the vectorized engine's survivor-bucket *flows* (spend, tax, income, withdrawals) match the scalar row to within a few percent that same year (tax within 15%), but its balances still contain the money. `_mc_survivor_bucket_flows` captures the survivor's flows but not this asset transfer. The fix is small and well understood: capture `rows2[year_idx]['cst_funded_yr']` per (spouse, year) bucket and, in the year a path's first death occurs, remove `min(cst_funded, path taxable + cash)` (taxable first, then cash) from the balances. Applied alone it is nearly invisible on the shipping engine (−0.7pp) because the tier order has already spent the taxable account by then (§3.4); on the replay skeleton it is −5.7pp (`none`) and −2.3pp (default). This is why survivor-economics ON overshoots without it (§3.6).

### 3.6 Survivor economics: correct direction, innocent of the gap

Same seed ⇒ same sampled paths ⇒ ON vs OFF isolates the adjustment. ON > OFF on all five seeds tried (n=200: +3.0, +3.5, +2.0, +4.0, +5.5pp; n=1000 paired: +4.6 `none`, +6.1 default). It can only relieve pressure (lower survivor spending, survivor SS benefit), so this is the expected sign. On the replay skeleton with CST added, ON sits 0.2pp (`none`) / 0.9pp (default) from the scalar engine, closer in level than OFF on the same skeleton (1.7 / 1.6pp). The old strict xfail ("ON narrows the gap") failed because it attributed the ~17pp level bias to a feature that does not cause it; ON adds to the optimism only because E, which offsets it, is missing.

### 3.7 Residual: per-path tax and RMD convexity (not fixed)

After replay + CST the remaining disagreement is 3.5–3.8% of paths and ≤1pp of level. Mechanism, measured on scalar paths: real tax paid by year vs the baseline the vectorized engine replays — 2050 mean $26K vs $4K baseline (p90 $58K): in good markets pretax stays large past the baseline's depletion year and RMD tax appears; 2042 p10 $10.6K vs $42.9K: in bad markets pretax is gone and tax collapses. The vectorized engine holds tax at baseline (scaled by inflation) in both tails. A `tax = fixed part + marginal × pretax draw` split (`ptax` flag) captured part of it (`none`: 0.707 vs 0.640 scalar, agree 93.0% at n=600, vs the fixed-tax `other_nodrag` 0.640/94.0% — i.e. no clear gain) and is not recommended without further evidence. RMD recomputation from the live pretax balance (09-07 Finding 7) was not re-tried: on a replay skeleton the remaining error is already ~1pp.

### 3.8 Why nothing composes simply

Measured on the shipping engine, single changes: A-fix (`other_nodrag`) fixes `none` and wrecks default; C-lift (`rothall`) does the opposite; B and E each nudge both regimes the same direction. The default-regime "small gap" is C's +27pp pessimism cancelling A-and-E's optimism, which is why every prior partial fix (09-07's five attempts) moved the gate metric the wrong way. Fix A+C+E together (`other_nodrag_hsa_rothall_cst`: 0.767 / 0.739, agree 86.4% / 93.4%) and the engine is still 8–14pp optimistic because bucket allocation (D) is still tier-ordered. Only replacing D as well (the replay skeleton) closes both regimes.

## 4. Recommendation

1. **Owner decision needed first (Component C).** Should the vectorized headline success rate mean "funded as asked" (scalar's definition; Roth is a last resort for any spending) or "funded within tier bucket restrictions" (today's vectorized definition)? If the latter, the scalar engine (used as the validation oracle) is measuring something else and the oracle gate cannot be tightened no matter how good the mechanics get; the restriction should then be applied to the scalar oracle's attribution (`_mc_scalar_tier_bucket_reconstruction` already exists) or reported as a separate "within-policy" success rate rather than folded into the headline.
2. **Smallest correct fixes, in order** (each independently reviewable; do not batch, per the golden-master discipline):
   1. **E — credit-shelter sequestration** (§3.5): ~15 lines in `_mc_survivor_bucket_flows` + the projection loop. Correct on its own merits, but on the shipping engine it moves default-regime drift the wrong way by ~1pp, so ship it *with* step 3.
   2. **B — HSA late fallback** (§3.2): one policy tuple + one test pin; only after step 1 of this list, so its −4 to −5pp is measured against a correct baseline.
   3. **D+A — replace the tier-ordered bucket allocation with the deterministic replay (fallback-any-bucket) for the funding decision, keep the tier cascade for attribution** (§3.1, §3.4): this is the change that closes both regimes (gap −0.2/−0.9pp, agree 96%). It removes `tax_drag` from the funding decision (the replayed deterministic withdrawals already contain the tax), which resolves A. Tier reporting (`spend_*_real`, `essential_fully_funded_probability`) would move to post-hoc attribution — the approach `_mc_tier_priority_retained` / the pre-Option-B reconstruction used — and this depends on the §4.1 decision.
3. **Do not** re-attempt RMD forcing or bracket-capped pretax rounds (09-07 Findings 6/7) for this metric; the replay skeleton inherits the deterministic engine's own bracket and RMD behaviour.
4. **Gate.** Do not tighten the 10pp gate on the current engine (n=200 noise is 4.8pp; true default-regime bias is −4 to −6pp). Measured basis for a future tightening: after steps 1–3, paired n=1000 gap is within ±1pp on both policies and paired agreement ≥96%; at that point raise the paired-path floor from 0.77/0.85 to ~0.93/0.93 and, if the independent-sample gate is kept, tighten it only together with a larger n (its standard error is 4.8pp at n=200 and 2.4pp at n=800, so a gate below ~2×SE flakes). **Owner approval is required to change the gate** (per the widening history in its docstring); no tolerance was changed here.
5. **Golden masters / MC outputs.** Steps 1–3 change headline MC success rates (in the direction that makes them closer to the scalar engine: `none` −17pp, default +5pp). They do not touch the deterministic projection, so `PINNED_TERMINAL_NW` / `PINNED_LIFETIME_TAX` should not move, but any pinned MC figure will; each step needs the hand-verified delta and planner-style note per CLAUDE.md. For a planner reviewer: the user-visible effect is that plans with credit-shelter trusts and Roth-heavy conversion strategies will report a **higher** success rate than today (the default fixture: 0.61 → ~0.66), and plans with `roth_policy=none` a **lower** one (0.80 → ~0.63); both are moves toward the full deterministic engine's own answer.

## 5. What shipped in this PR

- `tests/test_scalar_vectorized_paired_path_agreement_regression.py` (nightly): paired-path floors at the *measured* current state (agreement ≥0.77 `none`, ≥0.85 default at n=200; measured 0.815–0.85 and 0.91–0.915). A real degradation of path-level fidelity now fails without flaking on RNG noise; raise the floors as §4 lands.
- `tests/test_scalar_vectorized_survivor_reconciliation.py`: the strict xfail is retired. New premise: survivor economics ON > OFF on identical paths (§3.6); the loose sanity bound stays. Docstring records the resolution.
- `tests/test_monte_carlo_default_engine_mode.py`: docstring-only measurement note on the drift gate (§1 fact 2). Tolerance unchanged.
- This report and `N1_MC_PARITY_RESIDUAL_EXPERIMENTS_2026-09-30.patch`.
- **No `src/` change**, so no golden-master delta and no `GOLDEN_MASTER_CHANGELOG.md` entry; `tools/regen_golden_master.py` was not run.

## 6. Caveats

Single frozen household (couple, `cs_enabled`, $1.66M pretax / $0.52M taxable / $0.46M Roth at plan start); numbers will differ for other plans, especially single-person plans (no survivor or CST effects) and plans without conversions. Wellness shocks are off in all paired runs (the drift gate has them on; the sampled shocks are the same in both engines' definition but were not injected into the scalar side). n=1000 paired runs carry ~1.5pp standard error on the level and ~1pp on agreement; components under ~2pp (E alone, `cst`) are directionally supported but not individually significant on the shipping engine. The default-regime numbers use the engine's default `roth_policy` (`fill_to_bracket`); other policies were not run. The flat-return deterministic harness is not exactly deterministic in the scalar engine (sampled-inflation indices still differ slightly from the base projection), so absolute dollar diffs in §3.1/3.4 are indicative to ~±5%.
