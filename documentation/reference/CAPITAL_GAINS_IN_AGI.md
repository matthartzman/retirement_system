# Capital gains from sales in AGI, MAGI and IRMAA MAGI (H1)

Status (WI-024 phase 1, 2026-10-20): **investment-sale gains now count in IRMAA MAGI** (net realized brokerage gain after loss usage, read by the two-year lookback; see section 7). Phase 2 (WI-024, 2026-10-20) is also done: brokerage gains now count in NIIT MAGI (inside the cascade fixed-point loop), ACA MAGI and Social Security taxation. Plain-language summary: `release_notes/2026-10-engine-tax-correctness.md`.

Status: **approved 2026-10-13** (scope: home and rental sales only; other AGI-keyed rules stay as they are; sale-year vs lookback confirmed) and implemented. No golden value moved (no sale in any golden).
Rental constants were verified against 2025 rules by the household's tax preparer on 2026-10-13; this note
adds no new constants. Companion to `RENTAL_TAX_RULES.md` (section 4, the "excluded" simplification).

## 1. Before this change (the gap, for home and rental sales)

> Historical. This section describes the behaviour before H1 was implemented. For home and rental
> sales the engine now adds the taxable gain to AGI, NIIT MAGI and IRMAA MAGI
> (`src/projection_stages/deterministic_engine.py`, `sale_gain_in_agi`). The same gap **still exists** for
> gains realised by selling investments in taxable accounts (the withdrawal cascade's `ltcg_gain`, see
> section 5, decision 1), until that follow-up is built.

Before H1 the engine taxed the gain on a home sale or a rental sale as long-term capital gain (LTCG) in a separate
step (`resolve_home_sale_gain_tax`, `rental_property.apply_sale_tax`). That gain is **not** added to the
year's AGI. Everything that keys off AGI or MAGI therefore sees too little income in the sale year:

| What | Before H1 (home and rental sales) | Law |
|---|---|---|
| Reported AGI (sheets, `agi` column) | ordinary income only | Form 1040 line 11 includes the taxable gain (Schedule D) |
| IRMAA MAGI (`irmaa_magi_current`, read two years later) | AGI + tax-exempt interest, no gain | MAGI = AGI + tax-exempt interest; the gain is in AGI (42 USC 1395r(i); 20 CFR 418.1115) |
| NIIT threshold test (`niit_tax(nii, magi)`) | gain is in NII but not in MAGI, so NIIT is too low | IRC 1411(a)(1): 3.8% x lesser of NII and (MAGI - threshold) |
| Passive-loss phase-out MAGI, ACA MAGI, Social Security taxation | not touched | see section 5 |

Not an issue and unchanged: ordinary tax (the LTCG is stacked on ordinary taxable income and taxed once),
unrecaptured section 1250 gain on a rental sale (already inside ordinary income), a section 1231 loss
(already ordinary).

## 2. The rule

For every sale of the home or of a rental property in year Y:

`gain in AGI` = the **taxable** long-term gain after the section 121 exclusion
(`HomeSaleEconomics.taxable_gain`, plus the LTCG part of a rental sale). It excludes the section 121
excluded amount and the unrecaptured 1250 gain (already ordinary).

* Reported AGI(Y) = ordinary AGI(Y) + gain. The engine keeps the ordinary figure as `agi_ordinary` and uses
  it for the bracket maths (taxable income, std/itemized deduction, ordinary tax), so nothing is taxed twice.
* IRMAA MAGI(Y) = AGI(Y) + tax-exempt interest, now including the gain. The surcharge is assessed on the
  MAGI of the return filed **two years earlier**, so the gain raises the IRMAA tier in **Y+2** (the existing
  lookback, `core.irmaa_lookback_magi_and_filing`). Year Y and Y+1 premiums are unchanged by the sale.
* NIIT(Y) = 3.8% x min(NII incl. the gain, MAGI incl. the gain - threshold). Section 121 excluded gain is not
  NII (IRC 1411(c)(4)); only the taxable gain is.
* Roth-conversion and withdrawal sizing already read `irmaa_magi_current`, so they now see the sale-year
  income and react (the later-year moves in the report are that ripple).

## 3. Worked examples (MFJ, 2026 base-year IRMAA tiers 218k / 274k / 342k / 410k / 750k, NIIT threshold 250k)

| # | Inputs | Before | After | Rule |
|---|---|---|---|---|
| X1 | Home sale, gain 900,000, section 121 MFJ 500,000, ordinary AGI 200,000, other NII 0 | AGI 200,000; MAGI 200,000; NIIT 0; Y+2 tier 0 | taxable gain 400,000; AGI 600,000; NIIT 3.8% x min(400,000, 350,000) = 13,300; Y+2 MAGI 600,000 = tier 4 (410k to 750k) | IRC 61, 121, 1411; 20 CFR 418.1115 |
| X2 | Same but gain 480,000 (fully excluded) | no change | no change: taxable gain 0, nothing enters AGI | IRC 121(a) |
| X3 | Rental sale, gain 300,000 of which depreciation 25,000, ordinary AGI 150,000 | AGI 175,000 (1250 gain only) | AGI 175,000 + 275,000 LTCG = 450,000; Y+2 tier 4 | IRC 1(h)(6), 1250 |
| X4 | Rental sale at a loss | section 1231 loss in AGI | unchanged | IRC 1231 |
| X5 | Sale in 2029 | IRMAA tier in 2031 based on 2029 MAGI without the gain | 2031 uses 2029 MAGI with the gain; 2029 and 2030 premiums unchanged | 20 CFR 418.1115 |
| X6 | MFJ sale in year Y, one spouse dies in Y+1 | survivor Y+2 assessed on joint MAGI of Y vs MFJ table | same lookback, gain included | existing FIN-009 rule |

The fixtures below (section 4) reproduce X1 and X5: converted-home / home sale 2029 gives taxable gain
345,000 (AGI 296,000 to 641,000, NIIT 1,748 to 14,858 = +3.8% x 345,000, Y+2 tier 1 to 4).

## 4. Before / after (fixtures; engine run, `tools/h1_before_after.py`)

Frozen sample plan and demo plan: **no sale in either plan (home_sale_year 0, rental off): 0 moved numbers**;
`tools/golden_compare.py compare` stays green. Sale-year numbers move only in plans with a sale.

| Scenario | Moved cells | Sale-year change | IRMAA effect |
|---|---|---|---|
| home_sale_2029 (sample plan, home sold 2029) | 8 agi, 8 irmaa_magi_current, 25 niit, 28 total_tax, 6 irmaa_magi_used, 1 irmaa, 1 irmaa_tier, ... | AGI 296,000 to 641,000; NIIT 1,748 to 14,858; total tax +13,168 | 2031 tier 1 to 4, surcharge 2,916 to 16,126 |
| home_sale_2045 (home sold 2045) | 6 agi, 8 niit, 12 total_tax, 4 irmaa_magi_used, 1 irmaa, 1 irmaa_tier, ... | AGI 438,000 to 783,000; NIIT 7,144 to 15,332 | 2047 tier 1 to 4, surcharge 6,451 to 35,566 |
| converted_passes (convert 2027, sold 2029, passes 2-of-5) | same sale-year pattern | AGI 296,000 to 641,000 | 2031 tier 1 to 4 |
| converted_fails (sold 2033, fails 2-of-5, no exclusion) | 16 agi, 14 irmaa_magi_used, 24 total_tax | AGI 377,590 to 1,222,590 (+845,000); NIIT 4,848 to 36,958; total tax +32,486 | 2035 tier 2 to 5, surcharge 8,890 to 21,367 |
| rental_sale_recapture (rental sold 2035) | 7 agi, 21 total_tax | AGI 381,675 to 546,094 | 2037 tier 2 to 4, surcharge 9,806 to 21,595 |
| owner_shaped (converted home sold 2029 + rental sold 2035) | 25 agi, 28 total_tax | both sale years as above | 2031 tier 1 to 4; 2037 tier 2 to 4 |

Every moved cell for the fixtures is listed by scenario, year and column in `H1_BEFORE_AFTER_FIXTURES.txt`
beside this note (columns: agi, irmaa_magi_current, irmaa_magi_used, irmaa_tier, irmaa, niit, fed_tax,
state_tax, ltcg_gain, total_tax, taxable_inc). Later-year changes of a few hundred dollars come from the
optimizer re-sizing conversions and withdrawals once the sale-year MAGI is higher.
After approval the same counts will be produced for the golden workbook sheets and recorded in
`GOLDEN_MASTER_CHANGELOG`; for the owner's real plan only counts and column names will be reported.

## 5. Decisions (answered 2026-10-13: 1 home and rental sales only, 2 stay as they are, 3 confirmed)

1. **Scope.** Proposed: home sales and rental sales (the owner's decision). The same gap exists for LTCG
   realised by selling investments in taxable accounts (the cascade's `ltcg_gain`): that gain is also missing
   from AGI, MAGI and the NIIT threshold test. Fixing it moves **every** plan with taxable withdrawals,
   including the frozen sample and demo goldens. Recommendation: do it as a separate follow-up PR so this
   one stays reviewable; say if you want it folded in.
2. **Other AGI-keyed rules.** Proposed to leave unchanged in this PR and list as known simplifications:
   Social Security taxable share (gain belongs in provisional income), ACA premium credit MAGI, the
   passive-loss allowance phase-out MAGI, senior-bonus and student-loan phase-outs, medical 7.5% floor.
   Each would move more numbers; say which you want.
3. **Sale year vs lookback.** Confirm the reading in section 2: IRMAA is assessed two years after (no change
   to Y or Y+1), and the existing "first two plan years use the current year" fallback is unchanged.
4. **State tax.** Unchanged (rental design already taxes the whole gain as ordinary for state purposes; home
   gain state treatment is as today).

Not in scope: section 121 partial exclusions, installment sales, gifts, deaths (H5).

## 7. WI-024 phase 1: brokerage gains in IRMAA MAGI (FIN-001)

The net gain realized by selling taxable holdings in the withdrawal cascade (cascade `ltcg_gain` less capital-loss usage against gains, less the home/rental sale gain already added in H1) is added to `irmaa_magi_current` after the cascade settles (`deterministic_engine.py`, after Priority 4b); recorded on the row as `brokerage_gain_in_irmaa_magi`. Reported AGI, NIIT MAGI, ACA MAGI and Social Security taxation are unchanged (phase 2). The lookback already uses the prior return's own filing status (`irmaa_lookback_magi_and_filing`).

Closed form (`tests/test_wi024_irmaa_magi_brokerage_gain_regression.py`): MFJ, 2026 AGI 200,000 plus a 50,000 brokerage gain gives IRMAA MAGI 250,000; the 2028 tier-1 threshold is 218,000 x 1.025^3 = 234,762, rounded to 2,000 = 234,000, so 2028 is tier 1 (without the gain: tier 0).

Frozen sample plan: financial outputs do not move (terminal NW, lifetime tax, Roth conversions, lifetime IRMAA 86,777.60, every KPI and every IRMAA tier unchanged). Only 16 diagnostic cells per column change: `irmaa_magi_current`, `irmaa_magi_used` and the new `brokerage_gain_in_irmaa_magi` (largest shift +9,855 in 2027 into the 2029 lookback). The golden pins therefore hold; the phase-golden row baseline, which records those diagnostic cells, is stale for them.

## 8. State income tax on capital gains (2026-10-29)

Decision 4 above left state tax "as today", and today was wrong: the stage-9 state base
(`roth_conversion_and_agi_tax.py`, `investment_inc = note_int + portfolio_ordinary + portfolio_qualified`) never
carried a capital gain, and the cascade added only federal LTCG and NIIT. So in a state that taxes gains
(Illinois, 4.95% flat) every simulated taxable sale, every home-sale gain and every realized-ledger gain was
taxed federally only. Only a rental sale's long-term gain was state-taxed (`rental_property.apply_sale_tax`).

The investment-tax cascade now adds state tax on the year's net gain (losses netted first, rental long-term gain
excluded because the rental stage already taxed it), stacked on the stage-9 investment income plus that rental
gain, inside the same fixed point as LTCG/NIIT so the extra draw that pays it is funded. Row field
`state_tax_on_capital_gains`; it is a fixed addend in every later `total_tax_pre_niit` recombination and shows
under `state` in the cash-flow tax itemization. `row['state_tax']` stays the ordinary-income state tax.
Simplification: for graduated states the gain is stacked on the pre-Priority-3 ordinary base (same as the
rental adjustment). Tests: `tests/test_state_tax_on_capital_gains_engine_unit.py`.
