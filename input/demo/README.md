# Demo Plan Data (#240)

Fictional household — **Alex & Morgan Rivera**, Illinois — sized to exercise the
core engine end-to-end and safe to show to prospects, colleagues, or on a
screen share.

**Every figure in these files is invented.** No date of birth, income, Social
Security estimate, annuity contract, holding lot, account balance, note
receivable, property value, budget amount, vendor name, or spending category in
this folder is copied from the advisor's own plan. Illinois is retained as the
residence state on purpose: it is the only state the engine models an estate tax
for, so it is what makes the Estate Plan / Credit Shelter Trust / State Residency
sheets meaningful in a demo. Statutory constants that are the same for everyone
(Medicare Part B/D/G premiums, HSA and 401(k) limits, SS wage base, federal and
Illinois estate exemptions, gift exclusion) are also shared, as they should be.

## The fictional household

| | Alex | Morgan |
|---|---|---|
| Born | 1966 | 1967 |
| Retires | Jul 2029 | Jan 2030 |
| Plan horizon to age | 90 | 93 |
| Social Security claim age | 67 | 70 |
| PIA at FRA | $3,600/mo | $2,900/mo |

Roughly $5.1M invested across IRA / 401(k) / Roth / trust / HSA, a $950K home
with a $412.5K mortgage, a $320K private note receivable, four deferred
annuities, and $132K of core spending. The plan is comfortably funded across
2026-2060, so every sheet renders sensible numbers.

## To use it

In the app: **Settings -> Data & Maintenance -> Open Demo Plan**. That backs up
your real plan (DB + `client_data.csv`) automatically, applies these files, and
**Open Current Plan** restores it. The backup file's existence is the source of
truth for whether a demo is active, so a crash or restart cannot clobber it.

To apply the files by hand instead, copy every `input/demo/*.csv` over the
matching `input/*.csv` — after backing up your own plan.

## Two things to know

- `ytd_blend_enabled` is **FALSE** here on purpose. Your real
  `ytd_transactions.csv` is *not* swapped out by demo mode, so leaving the YTD
  blend on would mix your actual tracked income and spending into the demo's
  current-year projection.
- Only the core plan CSVs live here (the set in
  `local_plan_data_sync.PLAN_DATA_CSV_FILES`) — no JSON/YAML companions. Those
  are derived from `client_data.csv`; regenerate with
  `python tools/check_plan_data_sync.py --write` if you need them.

`tests/test_demo_plan_data_is_fictional.py` fails the build if any of this data
ever starts matching the live plan again.
