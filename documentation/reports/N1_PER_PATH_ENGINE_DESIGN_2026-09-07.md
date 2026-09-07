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
