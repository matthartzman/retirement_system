# WI-022 impact table: FIN-003 and FIN-001 on the frozen sample plan

**DRAFT — pending planner agreement.** Nothing here authorises a re-pin. No engine, tax code, golden or pin was changed to produce these figures.

- Source items: SYSTEM_REVIEW_2026-10-19.md section 9 (WI-022), findings FIN-001 and FIN-003 (section 5); phasing from SYSTEM_REVIEW_2026-10-19_WAVE0_DECISIONS.md (FIN-001: phase 1 IRMAA MAGI only, reported separately from phase 2 NIIT / ACA MAGI / Social Security taxation).
- Plan measured: the synthetic frozen sample plan (`tests/fixtures/csv_exchange/sample_plan_frozen/`), MFJ, 2026 to 2056, frozen prices. All dollar figures below are for that synthetic plan only.
- Method: the documented golden `measure` mode (`tools/regen_golden_master.py measure`, which runs the pin file's own regen block) executed in a throwaway copy of the repository outside the worktree, with the fixes prototyped there behind environment switches. The committed repository measures MATCH against its pins (terminal NW 5,300,872.54, lifetime tax 1,270,016.83). The prototype patch is not committed.

## 1. Headline table

| Scenario (prototype) | Terminal NW | Delta NW | Lifetime tax | Delta tax |
|---|---:|---:|---:|---:|
| Baseline (= current pins) | 5,300,872.54 | 0.00 | 1,270,016.83 | 0.00 |
| FIN-001 phase 1 only: IRMAA MAGI | 5,300,872.54 | 0.00 | 1,270,016.83 | 0.00 |
| FIN-001 phase 2 only: NIIT MAGI | 5,299,778.40 | -1,094.14 | 1,270,225.26 | +208.43 |
| FIN-001 phase 1 + NIIT (as measured) | 5,299,778.40 | -1,094.14 | 1,270,225.26 | +208.43 |
| FIN-003 only: qualified-dividend stacking | 5,388,234.61 | +87,362.07 | 1,231,758.70 | -38,258.13 |
| Net of FIN-001 (IRMAA + NIIT) and FIN-003 | 5,386,332.59 | +85,460.05 | 1,232,452.47 | -37,564.36 |

Sum of the two separate effects is NW +86,267.93 and tax -38,049.70; the combined run differs by NW -807.88 and tax +485.34 (interaction through changed withdrawals and balances).

## 2. FIN-001, reported separately as the owner decided

**Phase 1, IRMAA MAGI only (brokerage net gain added to the year's IRMAA MAGI, read by the two-year lookback).** Effect on the frozen plan: nil. Lifetime IRMAA surcharge is 89,501.60 before and after, and no year changes IRMAA tier. The plan realizes small brokerage gains (largest 14,979 in 2047, 14,376 in 2048; most years under 8,000). The largest lookback MAGI shift is +14,979 (2047 gain into the 2049 lookback) and it stays inside the same tier. Caveat: a plan sitting near a tier edge, or with larger drawdowns, would move; the frozen plan is not that case.

**Phase 2, NIIT (brokerage net gain added to the NIIT MAGI inside the cascade fixed point).** Lifetime NIIT 18,477.90 to 18,751.67 (+273.77); lifetime LTCG tax 4,312.80 to 4,320.62 (+7.82). Years that move materially: 2027 NIIT 1,140.00 to 1,357.33 and 2028 NIIT 1,444.00 to 1,505.32. Net effect is small, probably because in most gain years the plan's MAGI is already above the threshold by more than the net investment income (so the NII term, not the MAGI term, binds); not separately verified.

**Not measured (phase 2 remainder):** ACA premium-credit MAGI, taxable Social Security (provisional income) and the senior-deduction phase-out. They were not prototyped; the plan's exposure to them is therefore unquantified. CPA review is recommended for these.

## 3. FIN-003 (qualified dividends at 0/15/20%)

Prototype: in the federal-tax function used by every stage, dividends are removed from the ordinary stack and taxed with the kernel's `ltcg_tax_on_gain` stacked on top of ordinary taxable income; the cascade gain stack already sat above the dividends (its base `taxable_inc` includes them), so the gain call site was left unchanged in the prototype.

Result: federal tax down 38,258.13 over the plan (3.0% of lifetime tax); terminal NW up 87,362.07. Lifetime NIIT falls to 17,337.95 and LTCG tax rises to 4,669.40 (second-order effects through changed withdrawals and balances; not decomposed). Year 2026 federal-plus-gain tax falls by 782.46 (99,718.70 to 98,936.24); most other years fall by roughly 700 to 2,200, with one outlier (2056, -8,325.15) that was not investigated.

Closed-form check (committed tests): MFJ 80k ordinary + 30k qualified dividends + 20k gain. Today the dividends are taxed as ordinary income: 13,624.00 on 110k plus 3,000.00 gain = 16,624.00. Target: 9,104.00 ordinary on 80k, 1,665.00 on dividends (18,900 at 0%, 11,100 at 15%), 3,000.00 on the gain = 13,769.00. Overstatement today 2,855.00 a year at that profile, consistent with the review's "roughly $2 to 3k" illustration.

## 4. What the prototype did not cover (must be part of WI-023 / WI-024)

- Roth LTCG cap (`planning_engines.py` 2325-2352), `ltcg_marginal_rate` callers (`tlh.py`), `after_tax.py` callers and effective-marginal-rate reporting still use the old base. Roth and TLH decisions in the prototype therefore did not respond to the new stack; real re-pin figures will differ somewhat.
- Phase 2 convergence: the NIIT change was applied in the existing fixed-point iterations without a separate convergence study; a closed-form convergence test is still owed.
- Net gain used in the IRMAA/NIIT add-on is the cascade gain less recorded loss usage and less the home-sale gain already in AGI; wash/ordinary-loss edge cases were not exercised.
- Only the deterministic path was measured. The Monte Carlo engine reuses deterministic rows and inherits the effect; paired-path tests were not run.

## 5. Items for planner agreement before any pin changes (WI-023)

1. Accept or amend the direction and size: FIN-003 dominates (about -38.3k tax / +87.4k NW); FIN-001 phase 1 is nil on this plan and phase 2 NIIT is about +0.2k tax. The two are released together per the review, so the re-pin target is the net row (NW +85,460.05, tax -37,564.36, subject to the gaps in section 4).
2. Decide whether the pin moves in one step (net) or two (FIN-003, then FIN-001 phase 1, then phase 2) as the Wave 0 decision allows; phase 1 would be a no-op re-pin on this plan.
3. LTCG band constants: the frozen plan carries model constants `ltcg_0pct_top_mfj_base_year` 96,700 and 15% top 600,050 (2025 values via `data_io.py` defaults), while the verified 2026 dataset has 98,900 and 613,700. The engine indexes the model constants as if they were 2026 values. The prototype used the plan's constants unchanged. Decide whether WI-023 also aligns the constants to the dataset (this would shift the figures again).
4. Confirm ACA, Social Security and senior-phase-out effects are measured as a separate phase 2b (not prototyped here) and whether CPA review of the sample outputs happens before or after the re-pin.
5. Confirm the xfail fixtures in `tests/test_wi022_fin001_fin003_closed_form_fixtures.py` encode the intended conventions (NIIT target passes MAGI that includes the gain; IRMAA MAGI >= AGI + brokerage net gain; dividend tax = ordinary on the rest + preferential stack).

## 6. Prototype description (for reproducibility; not committed)

Three local edits in a scratch copy, each behind an environment switch: (a) the engine's federal-tax closure splits the year's qualified dividends out of the ordinary stack and adds `tax_kernel.ltcg_tax_on_gain` on them (switch for FIN-003); (b) after the investment-tax cascade, brokerage net gain is added to `irmaa_magi_current` (FIN-001 phase 1); (c) `_refresh_investment_taxes` passes `state.agi` plus the brokerage net gain to `niit_tax` (FIN-001 NIIT). Each scenario in section 1 is one `measure` run with the relevant switches.
