# Demo Plan Data (#240)

Fictional household — **Alex & Morgan Rivera**, Illinois — sized to exercise the
core engine end-to-end and safe to show to prospects, colleagues, or on a
screen share.

**Every figure in these files is invented.** No date of birth, income, Social
Security estimate, annuity contract, holding lot, account balance, note
receivable, property value, budget amount or budget-line name, target
allocation, bank/card account name, vendor name, or spending category in this
folder is copied from the advisor's own plan. Illinois is retained as the
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
your real plan (DB + `client_data.csv` + the budget recovery seed)
automatically, applies these files, and **Open Current Plan** restores it. The
backup file's existence is the source of truth for whether a demo is active, so
a crash or restart cannot clobber it.

To apply the files by hand instead, copy every `input/demo/*.csv` over the
matching `input/*.csv` — after backing up your own plan.

## What is here, and why

- **Every file the demo swaps has a counterpart in this folder.** That is
  `local_plan_data_sync.PLAN_DATA_CSV_FILES` + `YTD_PLAN_DATA_FILES` +
  `demo_plan_service.TEXT_BACKUP_FILES`. A file missing from here is *not*
  replaced, so your real one stays live for the whole demo —
  `test_demo_covers_every_file_open_demo_plan_applies` fails the build if the
  set ever drifts.
- `client_spending_budget.recovery_seed.csv` is here because
  `spending_tracker.load_unified_budget()` silently merges the seed into the
  budget whenever the category rows total zero. With the real seed still on
  disk that merge would pull your own annualized actuals into the demo's
  budget, so demo mode swaps it too and restores it from its own text backup.
- `ytd_blend_enabled` is **FALSE** here on purpose. The YTD files *are* swapped
  (#248), but the blend stays off so the demo's current-year projection is
  driven by the demo's own figures rather than a partial year of transactions.
- No JSON/YAML companions live here. Those are derived from `client_data.csv`;
  regenerate with `python tools/check_plan_data_sync.py --write` if you need
  them.

## The persistent demo slot

`input/demo/` is the **seed** -- the fixtures Open Demo Plan copies from the
first time you open the demo, or after a reset. Once opened, further edits
live in a separate working copy at `local_state/demo_plan/`, captured
automatically each time you click **Open Current Plan**. The next **Open
Demo Plan** reseeds from that working copy, not from this folder, so demo
edits now persist across sessions instead of being discarded.

`local_state/demo_plan/` is never committed and is not `input/demo/` -- the
anti-leak tests in `tests/test_demo_plan_data_is_fictional.py` only ever
read this folder, so a populated slot can never satisfy them even if you've
customized the demo heavily.

Click **Reset Demo to Defaults** to delete the slot and start the demo over
from these shipped fixtures. It refuses while a demo is currently open --
close it with **Open Current Plan** first.

`tests/test_demo_plan_data_is_fictional.py` fails the build if any of this data
ever starts matching the live plan again.
