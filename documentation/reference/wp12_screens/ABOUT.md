# WP12.5 Rental Properties UI mockup (owner review)

Static HTML, fake data, real app CSS (`frontend/css/dashboard.css` inlined). No product code. Design: `docs/superpowers/specs/2026-10-05-rental-property-module-design.md` sections 3 and 6.
Open `rental_properties_mockup.html#<n>` (e.g. `#1_list`). Desktop 1280x900, mobile 390x844 (`wp12_desktop_<n>.png`, `wp12_mobile_<n>.png`). "Expert" badge = advanced field, shown only with "Show advanced".

| # | State | Shows |
|---|---|---|
| 1_list | Rental Properties page | Summary strip (net cash flow, taxable rental income, suspended losses, equity); 3 warnings (double count with Other Assets, passive-loss limit, converted home failing s.121); table with Open/Duplicate/Remove; Add property and Convert my home buttons. Mobile: table becomes cards |
| 2_detail_basics_standard | Detail, Basics | Standard fields only, Show advanced off |
| 3_detail_income | Income | Rent, vacancy, growth, start/end year |
| 4_detail_expenses_advanced | Expenses | Standard plus Expert (property tax growth) |
| 5_detail_financing_advanced | Financing | Loan terms (or link liability), term remaining is Expert |
| 6_detail_tax_advanced | Tax | All Expert: placed-in-service, depreciable basis, active participation, improvements, read-only engine results |
| 7_detail_sale | Sale | Sale year, price (appreciated or typed), selling cost, gain preview note |
| 8_detail_overrides_advanced | Overrides | Per-year grid (Expert); with advanced off the tab shows an "Expert feature" stub |
| 9_detail_converted_home | Detail, converted home | "Converted home only" group with computed depreciation basis |
| 10_convert_my_home | Convert action | Dialog pre-filled from plan home: year, value, basis, suggested rent, carrying costs moving to Schedule E, s.121 note |
| 11_feature_off | Feature off | "Off · 3 rows entered", engine ignores it, turn-on button |

## Open design questions for owner
1. Tax tab is entirely Expert. Should "active participation" (drives the $25k allowance) be Standard instead, since most owners qualify and it changes tax?
2. Summary strip year: fixed to next projection year, or selectable? Suspended losses: current balance or at end of plan?
3. Warnings: dismissible per warning (shown), or always visible until fixed? Should double-count match be name only, or name or value within ~5%?
4. Convert dialog suggested rent (0.52% of value/month) is a placeholder rule. Use it, ask for rent only, or no suggestion?
5. s.121 failure is shown as an error (red). Block conversion, or warn only (shown)?
6. Detail as full page with tabs (shown) vs side panel; mobile uses cards plus scrolling tabs.
7. Improvements list sits on Tax tab (Expert). Better as its own tab or on Basics?
8. Off state: offer "Preview what it would add" (shown) or just the switch?
9. Net yield definition shown: (rent - operating expenses) / value. Confirm, or use cash-on-cash or cap rate on cost?
10. Where the "Convert my home" entry also appears in Next Housing Move / Housing Comparison is not mocked.

## Owner decisions (2026-10-13)
1. Active participation: Standard field, default yes, with a plain-words hint.
2. Summary strip: year selectable (default first projection year); suspended loss = balance at the selected year end. (default, not asked)
3. Warnings dismissible per session; double-count match = same name OR value within 5%. (default)
4. Convert dialog: ask for rent only, no suggestion.
5. Failed section 121 test: warn only (red warning with the tax effect).
6. Detail: full page with tabs.
7. Improvements stay on the Tax tab. (default)
8. Off state keeps "Preview what it would add". (default)
9. Net yield = (rent - operating expenses) / value. (default)
10. "Convert my home" in Next Housing Move / Housing Comparison is handled in 12.8 with its own mockup. (default)

## WP12.8 housing entry (text mockup, no screenshot)
Shown only while Rental Properties is on; off, both screens are unchanged (Phase 1 text kept).
- **Optimize > Next Housing Move, Home Sale area:** note "Keeping your home and renting it out? [Convert my home to a rental] opens Rental Properties with the conversion year set to your next move; you enter the rent." The button opens screen 10_convert_my_home pre-filled; rent is asked there, no suggestion.
- **Where to live search, step 2 Current home:** Disposition gains "Keep and rent out" (Auto searches it too when a rent is known); a "Monthly rent if rented out" field (today's $, blank = the converted home's rent; never suggested). The "rental income is not modelled" note and help text are replaced.
- **Results row** for keep and rent out: current home "Keep and rent out"; notes "rented out from 2028; s.121 two-of-five: exclusion only if sold by 2031; s.1250 recapture: $X depreciation taken ..., taxed up to 25% on a sale" and a [Convert my home] button (year and typed rent pre-filled). A failing s.121 test is a note only.
- Housing Comparison is a workbook sheet with no page, so it has no entry; its sweep is unchanged.
