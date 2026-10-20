# Capital gains from sales in AGI, MAGI and IRMAA MAGI (H1)

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
