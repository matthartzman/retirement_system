# WI-022 impact table: FIN-003 and FIN-001 on the frozen sample plan

**AGREED by planner (owner sign-off in session) and re-pinned for WI-023 (section 7); sections 1-6 remain the WI-022 draft record.** Nothing here authorises a re-pin. No engine, tax code, golden or pin was changed to produce these figures.

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


---

## 7. WI-023 as implemented (FIN-003) — AGREED by planner (owner sign-off in session) and re-pinned

Nothing in this section re-pins anything. `PINNED_*`, `golden_master_engine_cases.json` and `tests/fixtures/golden_phase_baseline/` are untouched; figures below come from `tools/regen_golden_master.py measure` and `tools/golden_compare.py` (live capture compared with the committed baseline). Branch `claude/wave2-eng`, commits prefixed `WI-023:`.

### 7.1 What changed

Stack order, bottom to top: ordinary taxable income, then qualified dividends, then realized gains. The ordinary schedule excludes the dividends; dividends and gains are taxed 0/15/20% by position. Qualified dividends stay in NII for NIIT (unchanged).

- `src/tax_kernel.py`: new `split_qualified_dividends` and `fed_tax_with_qualified` (ordinary tax on the rest plus `ltcg_tax_on_gain` on the dividends stacked above it); `ltcg_marginal_rate` documents that its stack base includes dividends.
- `src/projection_stages/deterministic_engine.py`: the engine's `_compute_fed_tax_path` is now dividend-aware. The year loop registers that year's `portfolio_qualified` right after the portfolio income split, so every stage that prices a taxable-income level through this function sees the same stack (stage 9 `fed_tax`, Roth planner `base_tax_est`, IRA elective true-up, DAF and HSA corrections, capital-loss offset value, effective marginal rate). The plain ordinary-schedule function is kept as `_ordinary_fed_tax_path`.
- LTCG band tops (decision 3): `data_io.py` now seeds `ltcg_0_top` / `ltcg_15_top` from the verified 2026 dataset by filing status (98,900 / 613,700 for MFJ). The two legacy 2025 values in the Model Constants rows (96,700 / 600,050) are treated as unset; any other explicit value is kept as a client override. Fallback literals in `planning_engines.py`, `tlh.py`, `gain_harvest.py`, `sheets_tax_capacity.py` and the JSON branch of `data_io.py` updated to the same numbers. The frozen fixture CSV is unchanged (still carries 96,700 / 600,050) and now resolves to the dataset.

### 7.2 Call sites (decision 2)

| Site | Result |
|---|---|
| Stage 9 `fed_tax` (`roth_conversion_and_agi_tax.py` ~811) | Changed via the dividend-aware closure |
| Cascade LTCG stack (`withdrawal_cascade_investment_tax.py` ~226) and NIIT call (~233) | Already correct, unchanged: `state.taxable_inc` includes the dividends, so the gain stacks above them; NII already includes them. NIIT MAGI (FIN-001) deliberately untouched. Locked by tests. |
| Cascade capital-loss offset value (~368) | Prices through the dividend-aware function (changed via closure) |
| `ltcg_marginal_rate` callers (`tlh.py`, scan inputs in `sheets_summary_builder.py` / `sheets_strategy.py`) | Pass the row's `taxable_inc` (dividends included): correct, unchanged. Gain-harvest 0% headroom and the tax-capacity sheet room use the same base. |
| Roth LTCG cap (`planning_engines.py` ~2340) | Reviewed: `pre_agi` already contains the dividends and the tops come from the dataset, so it is consistent with the stack. Left on the AGI basis (see 7.5). Locked by a test. |
| IRA elective gross-up marginal rate (`withdrawal_cascade_ira_true_up.py`) | Now reads the bracket at taxable income less dividends (the next ordinary dollar sits on the ordinary stack) |
| Unrecaptured 1250 cap (`rental_property.py`) | Now measured on the ordinary stack with the ordinary-only tax function |
| Reported statutory marginal rate (`sheets_projection_tax.py`) and bracket room (`sheets_tax_capacity.py`) | Ordinary stack |
| `after_tax.py` | Heir slices and HSA cliff are ordinary-income slices with no dividends: unchanged. Terminal-gain stack uses the terminal row's `taxable_inc` (dividends included): correct, unchanged. |
| Effective marginal rate (`effective_marginal_rate.py`) | Unchanged code; its +1,000 probe now runs through the dividend-aware function, so it correctly includes a dividend moving from the 0% to the 15% band. |

### 7.3 Measured deltas

`measure` (frozen sample plan, frozen prices; the pin path):

| | Terminal NW | Lifetime tax | Roth conversions |
|---|---:|---:|---:|
| Before (= current pins) | 5,300,872.54 | 1,270,016.83 | 125,000 (2026 only) |
| After WI-023 | 5,388,267.55 | 1,231,854.27 | 125,000 (unchanged) |
| Delta | +87,395.01 | -38,162.56 | 0 |
| WI-022 FIN-003 prototype | +87,362.07 | -38,258.13 | |
| After minus prototype | +32.94 | +95.57 | |

Lifetime components, before to after: federal 1,091,276.28 to 1,053,484.36; LTCG 4,312.80 to 4,661.02; NIIT 18,477.90 to 17,370.45; state 57,268.26 to 57,656.84. Year 2026: federal-plus-gain tax falls 782.46, identical to the prototype. Isolating the other changes: with the dividend stacking switched off, the band-top alignment, the ordinary-stack marginal rate and the 1250 change alone move terminal NW by +817.73 and lifetime tax by -484 (the band alignment alone is under 1). The prototype-to-implementation gap (+32.94 / +95.57) is therefore band alignment plus second-order path effects.

`golden_compare` pipeline (the app path the phase baseline uses; Roth policy resolved by the build): committed baseline to live: terminal NW 5,429,963.80 to 5,516,217.14 (+86,253.34); lifetime tax 1,156,879.26 to 1,124,452.80 (-32,426.46); Roth conversions 600,175.26 to 598,627.59 (-1,547.67). KPIs that move: after-tax terminal NW 4,434,138.49 to 4,514,788.19; KPI lifetime tax 1,027,067.04 to 996,583.87; NPV future taxes 679,944.53 to 662,830.39; terminal estate tax 271,916.59 to 279,514.00; terminal Roth NW 466,210.24 to 538,108.34; total Roth conversions 603,665.78 to 602,143.21.

### 7.4 The 2056 outlier (about -8,325 in one year)

Reproduced exactly (2056 total tax -8,326). It is not a bug in the stacking; it is two things at once.
1. Size. The survivor (Single since 2055) sells the home in 2056 (net proceeds 2,995,776, no gain after the 250,000 exclusion) and the proceeds land in the taxable account (Member_2_Trust 2,946,234 at year end), so the portfolio-income split yields 45,619 of qualified dividends against 0 in 2054 and 2055 and 4,498 to 19,872 in the years before. Taxable income is 119,811; ordinary part 74,192 (tax 8,453.86). Old: all 119,811 ordinary, federal tax 16,780. New: 8,454. The saving is about 18% of 45.6k, in line with other years' ratio scaled to a dividend 2.5 to 10 times larger and a filer with fewer 0% dollars.
2. A pre-existing filing-status defect that this change exposes. `tax_kernel.ltcg_tax_on_gain` reads `c['ltcg_0_top']`, seeded once from the plan's original MFJ status, so the Single survivor year is stacked on MFJ band tops. At bracket factor 1.8114 the 0% top used is 179,144; the Single 0% top would be 49,450 x 1.8114 = 89,572. With the MFJ tops all 45,619 of dividends are taxed at 0% (preferential tax 0.00); with Single tops it would be 4,535.92, and the 2056 drop would be -3,790 rather than -8,326. The Roth cap already looks tops up per year's filing (`_roth_ltcg_thresholds_base`); the kernel does not. Fixed afterwards on planner instruction: see 7.8.

Secondary effect worth knowing: 2047 total tax rises +6,160 (2048 falls 2,062, 2049 falls 1,692). The lower tax in earlier years changes balances, and in 2047 the elective IRA draw rises from 16,937 to 49,051 while the taxable draw falls from 175,609 to 147,492 (NIIT 0 to 646). It is a withdrawal-mix timing shift caused by the dividend change itself (it persists with the marginal-rate change reverted and with old band tops), not a separate defect. The prototype had the same total.

### 7.5 Flagged, not changed

- Roth LTCG cap compares pre-deduction AGI with taxable-income band tops (conservative, pre-existing). Measuring from AGI less the standard deduction was tried and reverted: through the `golden_compare` pipeline it adds about 142k of conversions over the conversion window (600,175 to 742,002), terminal NW 5,561,837.88 and lifetime tax 1,097,119.55, an effect well beyond FIN-003. Planner decision.
- Survivor-year LTCG band tops: fixed, see 7.8 (home-sale and AMT/equity-comp gain stacks still use the seeded status).
- N2 (qualified-dividend overstatement notice): the WI-010a notices are not implemented on this branch (only the approved wording exists in `SYSTEM_REVIEW_2026-10-19_WAVE1_NOTICE_WORDING.md`), so there is no N2 code or preflight test to retire. When WI-010a is built, N2 must not ship: its retirement trigger (this fix) has already occurred.
- FIN-001 (brokerage-gain MAGI, NIIT MAGI) untouched; its xfails remain.

### 7.6 Tests

New `tests/test_wi023_qualified_dividend_stacking_regression.py`: dividends plus a realized gain together (hand value 13,769.00), the 15% to 20% straddle (3,315.00 + 2,000.00), the zero-band case, the cascade call site (3,000.00 versus 165.00 if dividends were left out of the base), NIIT with dividends in NII (1,900.00 versus 760.00 without), the MAGI-bound NIIT case (760.00), the Roth LTCG cap (98,900 - 50,000), dataset band tops on the frozen plan, and a per-year engine check that `fed_tax` equals ordinary-on-the-rest plus the dividend stack. The FIN-003 xfail in `tests/test_wi022_fin001_fin003_closed_form_fixtures.py` is removed (it now passes); the FIN-001 xfails remain.

### 7.7 Tests that fail because pins are stale (expected, not hidden)

Full suite run in four parallel shards on this branch, every failure then compared against a clean copy of the base commit (`dba71bd`). Failures that are pins or baselines made stale by this change:

| Test | Why |
|---|---|
| `tests/test_frozen_sample_plan_golden_master_regression.py::FrozenSamplePlanGoldenMasterTests::test_frozen_plan_dollar_figures_are_exact` | `PINNED_TERMINAL_NW` 5,300,872.54 vs computed 5,388,267.55; `PINNED_LIFETIME_TAX` 1,270,016.83 vs computed 1,231,854.27 |
| `tests/test_phase_golden_equality_regression.py::test_live_output_equals_baseline[sample_frozen]` | Committed baseline is stale (`golden_compare compare` shows the diffs from engine row 0 onward). This test also fails on the clean base in this environment because gitignored `input/` is absent, so it does not by itself show the staleness; the `golden_compare` run does. |
| `tests/test_phase_golden_equality_regression.py::test_live_output_equals_baseline[demo]` | Fails on the clean base here (no `input/demo`); could not be evaluated, expected to be stale for the same reason. |

One test needed a convention update, not a pin: `tests/test_effective_marginal_rate_regression.py` compared the effective marginal rate with the statutory bracket read at full taxable income; it now reads the bracket of the next ordinary dollar (taxable income less qualified dividends), matching the reported marginal rate.

Failures identical on the clean base (not caused by this change): dashboard codemod and extract-module tool tests, optional-module gating and rental/divorce/housing workbook-build tests, efficient frontier and tangency Sharpe tests, `test_real_loss_aware_mode_regression.py`, `test_tax_aware_rebalance_functional.py` (global optimizer), `test_roth_result_panel_payload_functional.py`, `test_social_security_apply_payload_functional.py`, results-model contract fixture, skip-count ratchet, architecture diagram freshness, test-file-suffix count. A few tests (tax-loss harvesting scanner, withdrawal-sequencing comparison) failed only while four shards ran concurrently and pass when run alone on this branch; two workbook-build files (`test_all_modules_off_build_functional.py`, `test_engine_module_gate_agrees_with_sheets_regression.py`) exceed the shard timeout and were compared one-to-one with the base separately.


### 7.8 Update: band tops follow the filing status in force for the year

Planner decision before any re-pin. `tax_kernel.ltcg_band_tops(c, filing)` returns the dataset tops for the year's filing status when it differs from the plan's seeded status (seeded values, including client overrides, are kept otherwise). `ltcg_tax_on_gain` and `fed_tax_with_qualified` take an optional `filing`; the engine's dividend stacking, the cascade LTCG refresh and capital-loss offset value, and the rental-sale LTCG now pass the year's filing. Home-sale and equity-comp (AMT) gain stacks still use the seeded status (no 2056 effect on the frozen plan; follow-up).

Closed form (tests): 2056, bracket factor 1.02^30 = 1.811362, Single 0% top 49,450 x 1.811362 = 89,572; 74,192 ordinary + 45,619 dividends: (45,619 - 15,380.3) x 15% = 4,535.9 of dividend tax; a 10,000 gain above them 1,500; MFJ control on the same inputs 0.00. The engine's 2056 `fed_tax` is 12,989.77 (8,453.86 ordinary + 4,535.9), versus 8,453.86 at 8e2b347.

| | Terminal NW | Lifetime tax | Roth conversions |
|---|---:|---:|---:|
| Pins (unchanged) | 5,300,872.54 | 1,270,016.83 | 125,000 |
| `measure` at 8e2b347 | 5,388,267.55 | 1,231,854.27 | 125,000 |
| `measure` now | 5,383,495.40 | 1,236,390.19 | 125,000 |
| Delta vs pins now | +82,622.86 | -33,626.64 | 0 |
| Change vs 8e2b347 | -4,772.15 | +4,535.92 | 0 |

`golden_compare` pipeline: terminal NW 5,511,444.98 (was 5,516,217.14 at 8e2b347; baseline 5,429,963.80, now +81,481.18); lifetime tax 1,128,988.71 (was 1,124,452.80; baseline 1,156,879.26, now -27,890.55); Roth conversions 598,627.59 (unchanged from 8e2b347; baseline 600,175.26). The 2056 saving is now about -3,790, as predicted. Stale-pin tests are the same three listed in 7.7; no pin or baseline was edited.

### 7.9 Update: home-sale and AMT/equity-comp gain stacks follow the year's filing

Planner decision before any re-pin. `resolve_home_sale_gain_tax` (called from stage 9 with the year's `filing`) and `apply_amt_and_equity_comp_true_up` now pass the year's filing to `tax_kernel.ltcg_tax_on_gain`, the same helper as 7.8. Every LTCG/dividend stack in the engine now uses the filing status in force for the year.

Closed form (new `tests/test_wi023_gain_stacks_filing_regression.py`): 2056, factor 1.811362, 20,000 gain on 119,811 taxable income. Single 0% top 89,572 gives 3,000.00 for both the home-sale and the equity-comp stack; MFJ control (0% top 179,144) gives 0.00.

Frozen-plan figures did NOT move versus 322021d: `measure` 5,383,495.40 / 1,236,390.19 (+82,622.86 / -33,626.64 vs pins), Roth conversions 125,000; `golden_compare` pipeline 5,511,444.98 / 1,128,988.71 / 598,627.59, identical to 7.8 (the frozen plan has no taxable home-sale or equity-comp gain in a Single year). Stale-pin tests unchanged (7.7).

Non-slow tier (`pytest tests -m "not slow and not nightly" -n 4`): 23 failures. 22 are identical to the clean-base failures listed in 7.7 (dashboard codemod/extract tools, efficient-frontier and Sharpe tests, real-loss-aware, results-model contract, skip-count ratchet, architecture diagram, tax-aware rebalance optimizer, test-suffix count, cash-flow chart compaction). The 23rd is the stale golden-master pin `test_frozen_plan_dollar_figures_are_exact`. The phase-golden-equality tests are slow-marked and not in this tier. The earlier parallel-only TLH and withdrawal-sequencing failures did not recur.

### 7.10 Re-pin

Done through the documented tools only: `tools/regen_golden_master.py regen --reason` (entry added to `documentation/reference/GOLDEN_MASTER_CHANGELOG.md`) and `tools/golden_compare.py record --plan sample_frozen --reason` for the phase baseline. New pins: `PINNED_TERMINAL_NW` 5,383,495.40, `PINNED_LIFETIME_TAX` 1,236,390.19. The demo baseline could not be regenerated here (no `input/demo`) and still needs recording where that plan exists.
