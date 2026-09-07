# N1 Parity: Per-Path Per-Owner Tax/RMD Engine — Design

**Status:** In progress. Chosen path: Option (a) from the N1 diagnostic
(`N1_MC_PARITY_DIAGNOSTIC_2026-09-07.md`) — genuine per-path, per-owner
RMD/tax recomputation inside `_mc_vectorized_projection`, rather than a
disclosed-tolerance workaround.

## Why the diagnostic's patches kept failing

Every one of the six diagnostic attempts patched the vectorized cascade's
*allocation* of a fixed, pre-computed dollar need across buckets. None of
them could fix the *need* itself, because the vectorized engine has no
per-path state for the two things that actually drive it in the real
(`exact_scalar`) engine:

1. **A single combined `pretax` balance for the household.** No `h_pretax` /
   `w_pretax` split. RMD divisors are age- and per-owner-dependent
   (Uniform Lifetime by default, Joint Life when the spouse is the sole
   beneficiary and >10 years younger — `rmd_divisor()`,
   `planning_engines.py:843`). A blended household divisor is a
   structurally different (and provably wrong, per Finding 7) function of
   balance and age.
2. **No per-path AGI/bracket state.** `withdraw_pretax_elective`'s two-pass
   bracket cap depends on that year's *own* AGI, which depends on that
   path's own income/withdrawal history — not the deterministic baseline's.

Both are consequences of the same design choice: the vectorized engine
replays ONE deterministic baseline trajectory (scaled), rather than
maintaining independent state per path. Closing the gap means giving the
two RMD/tax-relevant quantities (pretax balance, AGI) real per-path,
per-owner state, while leaving everything else (spending cascade order,
survivor blending, return/inflation sampling) as-is.

## Phasing

**Phase 1 — per-owner pretax balances + real per-path RMD.**
- Split `_mc_bucket_starting_balances` pretax total into `h_pretax` /
  `w_pretax` using `account_registry[*].owner_idx` (mirrors
  `rmd_ids_by_owner`).
- Split the deterministic baseline's pretax withdrawal/deposit/conversion
  flows (`_mc_row_bucket_flows`) into h/w shares using each row's own
  `h_ira_total_wd` / `w_ira_total_wd` (and analogous deposit/conversion
  fields) so the *shape* of the baseline split carries into the vectorized
  replay before RMD divergence is introduced.
- Each path/year: compute RMD directly from that path's own `h_pretax[i]`
  / `w_pretax[i]` and each spouse's age via `rmd_divisor()`, mirroring
  `compute_rmds()` (Uniform Lifetime only in Phase 1 — Joint Life /
  QLAC carve-out deferred to Phase 3, since the diagnostic household
  doesn't exercise them and they're pure additive precision once Phase 1
  is proven).
  Handle death: when a spouse dies, that spouse's own `*_pretax` bucket
  merges into the survivor's, mirroring `apply_rmds`'s post-death handling.
- Mandatory RMD forces a withdrawal (net of that path's own tax_drag) BEFORE
  the elective tier cascade for that year, same order as the real engine
  (`compute_rmds` → `apply_rmds` runs before elective withdrawals in
  `project()`).
- Validate against `test_exact_scalar_oracle_agrees_with_vectorized_default_within_tolerance`
  after every sub-step; keep only sub-steps that measurably help.

**Phase 2 — per-path AGI-aware bracket cap for elective pretax withdrawals.**
- Track a per-path running AGI proxy (income streams + RMD + realized
  elective pretax withdrawals + realized conversions, using the same
  fields Finding 6 exposed: `agi_before_elective_pretax_wd`,
  `pretax_elective_bracket_ceiling`).
- Cap each path's own elective pretax draw at
  `min(bracket_top_24, irmaa_threshold) - path's own AGI`, two-pass
  (capped then uncapped), mirroring `withdraw_pretax_elective`.

**Phase 3 — precision/edge cases**, only if Phase 1+2 close most of the
gap: Joint Life divisor for a much-younger sole-beneficiary spouse, QLAC
premium carve-out from the RMD base, per-owner Roth/taxable splits if the
remaining error is traced there.

## Non-goals

- Not reimplementing `exact_scalar`'s full per-year `project()` call inside
  the vectorized loop — that would just make `vectorized` an alias for
  `exact_scalar` and defeat its purpose (speed). The goal is to give the
  two RMD/tax-relevant state variables real per-path fidelity while keeping
  everything else a fast, vectorized approximation.
- Not changing `exact_scalar` itself, or the deterministic `project()`
  engine — both remain the source of truth.

## Test protocol (unchanged from the diagnostic)

Every sub-step is validated against the real 200-sim stochastic parity
test, never guessed:
`tests/test_monte_carlo_default_engine_mode.py::test_exact_scalar_oracle_agrees_with_vectorized_default_within_tolerance`
plus the deterministic no-randomness harness (flat returns, no death, no
wellness shocks) for isolating mechanics from sampling noise, as used
throughout the diagnostic (`mc_diag*.py` scripts).

---

## Phase 1 implementation results (2026-09-07)

**Status: partially shipped.** The additive per-owner balance/flow
plumbing (bullet 1 of Phase 1) is kept -- it is bit-identical (proven, not
assumed) to the pre-Phase-1 engine and gives a future attempt a working
foundation. The RMD-forcing recursion itself (bullets 2-4 of Phase 1) was
implemented in full, tested rigorously, found to make the target metric
measurably *worse* at the official gate seed, and reverted, following the
diagnostic's own "keep only what measurably helps" discipline.

### What was built and kept

- `_mc_bucket_starting_balances`: splits the `pretax` starting balance into
  `h_pretax`/`w_pretax` using each account's registry `owner_idx` (mirrors
  `core.py`'s `ids_by_owner`). `pretax` itself is kept, unchanged, as
  `h_pretax + w_pretax`.
- `_mc_row_bucket_flows`: splits each year's deterministic-baseline pretax
  withdrawal/deposit/conversion flows into `h_pretax`/`w_pretax` using the
  same per-account `owner_idx`, and additionally exposes `rmd_h`/`rmd_w`
  (the baseline's own per-owner RMD for that year, already on
  `deterministic_engine.py`'s rows) and `h_ira_elective`/`w_ira_elective`
  (the baseline's elective-only, non-RMD pretax withdrawal split) as
  extra scalar fields.
- `_mc_effective_row_flows` and `_mc_survivor_bucket_flows`: propagate all
  of the above through survivor-death blending exactly like every other
  flow field, so a path that switches to a survivor-period trajectory
  after its own sampled first death still carries a correctly owner-split
  pretax balance and the new scalar fields.

Verified bit-identical to pre-Phase-1 `HEAD` on the parity test (3.5pp,
byte-for-byte the same success rates) before any RMD-forcing code was
added -- this plumbing changes no existing behavior on its own, only adds
state nothing reads yet.

### What was built, tested, and reverted: genuine per-path per-owner RMD forcing

Implemented in `_mc_vectorized_projection`:

1. Each path/year, each spouse's age (`h_dob_yr`/`w_dob_yr` + calendar
   year) and RMD eligibility (`h_rmd_start_age`/`w_rmd_start_age`/
   `rmd_start_age`, default 75) were computed, `rmd_divisor()` applied
   (Uniform Lifetime only, per Phase 1 scope), and each path's own real RMD
   computed from that path's own **live, diverged** `h_pretax`/`w_pretax`
   balance -- the exact mechanism Finding 7 in the diagnostic was missing a
   per-owner split for.
2. **Double-draw avoidance (the key correction Finding 7 didn't have):** a
   deterministic-baseline year's RMD is already fully embedded in
   `eff['withdrawals']['pretax']` (an RMD is just a pretax-account
   withdrawal, indistinguishable at the account level from an elective
   one), so forcing the *entire* path-specific RMD on top of the existing
   cascade replay double-draws the baseline's own share. Only the
   **incremental delta** -- `max(0, path's own RMD - baseline's own scaled
   RMD for that year)` -- was force-withdrawn before the elective cascade;
   any of its after-tax proceeds the cascade didn't need were reinvested
   into taxable rather than discarded.
3. Spousal rollover on death: mirrors `apply_death_transition` -- in the
   sampled death year (last year that spouse is still "alive" per the
   `year <= death_yr` convention `compute_rmds` itself uses), the deceased's
   remaining `h_pretax`/`w_pretax` balance merges into the survivor's.
4. Every operation that touches the combined `pretax` bucket (elective
   cascade draw, deposits, Roth conversions, market growth incl. asset-
   location tilts) was mirrored onto `h_pretax`/`w_pretax` so they never
   desync from the combined balance -- growth specifically by inferring the
   *effective* rate `_mc_apply_bucket_growth` just applied (diffed, not
   duplicated), so a future tilt change can't silently break the split.

**First attempt (forcing the FULL RMD, not just the delta) was much worse**
-- caught immediately by the deterministic harness before ever reaching the
stochastic test: `pretax` ended up **higher**, not lower, than the
baseline-replay figure by end of plan (a genuine double-draw: the same
dollars debited once by the new forced RMD and again by the pre-existing
cascade replaying its own baseline-embedded RMD figure). Diagnosed and
fixed by switching to the incremental-delta approach (point 2 above) before
running the stochastic test at all -- exactly the harness's intended use.

**Second bug, also caught by the harness before the stochastic test:** the
first version of the "reinvest unneeded RMD proceeds into taxable" step
pooled the extra-RMD money into the SAME `income_avail` pool as ordinary
`income_funding` from the start, then reinvested whatever was left of the
combined pool. Since `income_funding` alone routinely has leftover after
funding tiers (pre-Phase-1, that leftover was simply discarded, by
construction, every year) that ordinary leftover got misattributed to the
RMD fix and reinvested too -- inflating `taxable`/`total` in EVERY year,
including years over a decade before either spouse's RMD start age. Fixed
by keeping the extra-RMD pool separate and consuming `income_funding`
first, exactly reproducing its old (no-reinvestment) behavior, with only
the genuinely new extra-RMD pool's leftover banked.

**With both bugs fixed, deterministic-harness result:** `pretax` no longer
wildly overshoots the baseline late in the plan the way the pre-fix and the
diagnostic's original Finding 7 (household-blended) version did, but a
large, *pre-existing* `taxable`/`total` divergence (present in unmodified
`HEAD`, confirmed by re-running the same harness against the unmodified
code -- not introduced by this change) dominates the picture and this
change does not fix it (out of scope: that gap is the tax-cascade
double-count/drop territory the diagnostic's Findings 2-4 describe, not an
RMD issue).

**Stochastic parity-test result (the actual gate): measurably worse at
every seed tested except one, and worse at the official gate seed:**

| Seed | Sims | Baseline (`HEAD`) | With Phase 1 RMD forcing | Delta |
|---|---|---|---|---|
| 2026 (official gate) | 200 | 3.50pp | 4.00pp | **+0.50pp (worse)** |
| 2026 | 2000 | 0.20pp | 0.80pp | **+0.60pp (worse)** |
| 1 | 200 | 4.00pp | 4.50pp | **+0.50pp (worse)** |
| 42 | 200 | 2.00pp | 1.50pp | -0.50pp (better) |
| 777 | 200 | 1.50pp | 1.50pp | 0.00pp (no change) |

Every number above came from an actual run of the official test's own
`monte_carlo(...)` call (`mc_sims`/seed varied as shown), not estimated.
The official gate (seed 2026, 200 sims, the exact test CI runs) still
*passes* with Phase 1's RMD forcing (4.00pp < 5pp), but the discipline
mandated for this work is "keep only what measurably helps," evaluated at
that same official gate -- and it measurably does not: 3.50pp -> 4.00pp is
a regression, not an improvement, consistent with (smaller than, but the
same direction as) every prior diagnostic attempt that touched a real
dollar amount rather than pure bucket-routing (Findings 2 alone, the first
combined tax attempt, and Finding 7 itself all moved the metric backward
too). The other seeds are a mixed bag (3 worse, 1 better, 1 unchanged) --
consistent with a genuinely small, roughly zero-mean effect on this
specific household fixture rather than a directionally reliable
improvement.

**Reverted.** Per this project's standing discipline (see the diagnostic's
"why nothing shipped" and Finding 7's own revert), the RMD-forcing
recursion in `_mc_vectorized_projection` was reverted back to
byte-identical `HEAD` behavior (re-confirmed: parity test back to exactly
3.50pp at seed 2026/200 sims after the revert). Only the additive,
bit-identical-on-its-own balance/flow plumbing described above was kept.

### Was the mechanism itself wrong, or is this household just not RMD-bound enough to show the fix?

The RMD mechanics implemented here are more correct than anything
previously in the vectorized engine (genuine per-path, per-owner,
balance-and-age-driven RMD with proper delta-based double-draw avoidance
and spousal-death rollover, versus literally zero RMD modeling before this
attempt). That the fix is *correct* and still doesn't reliably improve the
aggregate success-rate metric is consistent with Finding 6's own
conclusion in the diagnostic: a routing/timing-accurate fix does not
necessarily move a metric that is only sensitive to the *total* dollar
trajectory, and any residual imprecision it does introduce (the
elective-vs-RMD owner-split ratio is still an approximation, `tax_drag`
still isn't RMD-aware) is enough to roughly cancel out whatever the
correction bought at this specific fixture's scale of RMD exposure
relative to total spending need.

### Recommendation on Phase 2

**Do not proceed to Phase 2 (AGI-aware bracket cap) on the current
evidence.** Phase 2 was scoped as an incremental refinement ON TOP OF a
Phase 1 that measurably closed part of the gap; Phase 1 as implemented
did not do that -- it left the official metric slightly worse, mixed
across seeds. Building Phase 2's materially larger AGI-tracking/two-pass
bracket-cap machinery on top of a foundation that hasn't demonstrated
value would repeat the diagnostic's own lesson (Finding 6: a correctly
implemented, real fix can still fail to move this metric) at higher
engineering cost, with no new evidence Phase 2 would fare any better.

This closes out five (now six, counting this attempt) independent,
rigorously-tested hypotheses for what drives the residual vectorized/
exact_scalar gap, each mechanically well-justified, each implemented and
measured rather than guessed, and none of which reliably improved the
gate metric except the tax-cascade double-count/drop fix (Findings 2-4,
still unshipped as of this writing). The diagnostic's own final
recommendation stands and is reinforced, not undermined, by this attempt:
either (a) accept the vectorized engine as a disclosed, bounded-tolerance
approximation and land Findings 2-4 on their own merits, or (b) commit to
the much larger engineering investment of genuine per-path tax
recomputation approaching `exact_scalar`'s own cost -- a product/
architecture decision for whoever owns that tradeoff, not a further
engineering patch. The per-owner balance/flow plumbing kept here is
useful groundwork if (b) is ever chosen, but Phase 1 alone, even done
carefully and correctly, was not sufficient to justify continuing further
down this specific path on its own.
