# Annuity and pension values from the plan, not Monarch (design + plan)

2026-10-29. Approved by the user in chat ("build this recommendation").

Status: implemented (PR #328).

## Why

Current Snapshot and the Trends net-worth chart value each annuity/pension account at the balance typed into
Monarch by hand. Recent Projections values the same contract at the engine's present value (remaining payments
discounted at `annuity_pv_discount_rate`, PR #326). The two drifted by $620k (Matt's joint annuity:
$1,269,216 in Monarch vs $840,200 in the plan). Two hand-maintained copies of one number will keep drifting.

## Goal

One source: an annuity or pension account the plan can identify is valued at the plan's figure everywhere the
Trends app shows Monarch balances (Current Snapshot non-liquid rows and totals, the Net Worth chart, the daily
log's Monarch figures, the percent-of-net-worth basis). Anything the plan cannot identify keeps its Monarch balance.

Non-goals: changing the engine's valuation; editing Monarch; valuing the RedMane note or other private assets
from the plan (separate decision).

## How

**The match (already configured, nothing new to set up).** Monarch account -> plan account (the Trends registry's
`app_account`, or the Planner reconcile page's match, which wins: `live_snapshot.saved_setup_aliases`) -> that
Accounts & Sources row's `Mapped Investment Account` (an Income Streams subsection) -> the engine's PV column:

| Income stream | Projection column |
|---|---|
| Member 1 Joint Annuity | H Joint PV |
| Member 2 Joint Annuity | W Joint PV |
| Member 1 Single Annuity | H Single PV (QLAC folded in, as the engine does) |
| Member 2 Single Annuity | W Single PV |
| Member 2 Pension | Pension PV |

**The value.** The first (plan-start) row of the latest build's `projection_tables.json`, read through
`projections.load` (so a build left over from another plan or build is ignored). These are exactly the numbers
Recent Projections shows. No build, or a column the build lacks -> no override for that account.

**Where it applies.** One new module, `financial_trends_reporter/plan_annuity_values.py`:
`account_values(base_dir, balances_db) -> {account_key: value}`. `balance_series.snapshot_summary` and
`balances_payload` take an optional `plan_values` and, after building the daily series, replace each mapped
account's non-zero values with the plan value (the account's open/closed window is unchanged; client-side
re-summing on toggle changes keeps working because the series itself carries the value). Every caller passes it:
`live_snapshot`, `trends_metrics`, `main` (balances route) and `percent_view.scale_basis`. Overridden detail rows
carry `source: "plan"`; Current Snapshot's non-liquid table labels them.

**Ambiguity rule (my call).** Two Monarch accounts matched to the same stream: neither is overridden (keeps
Monarch), rather than guessing a split.

**History (my call).** The chart's past days for a mapped account show today's plan value (the series is
replaced, not only the last day), so the switch does not draw a cliff. Earlier log entries are untouched.

## Steps (all Sonnet-class work at medium effort; light usage overall)

1. Tests first: mapping + override unit tests over a temp balance store and a stub projection doc. Light.
2. `plan_annuity_values.py` + `balance_series` parameter + four callers. Light (small files; `live_snapshot.py`
   is ~1,100 lines, edit by grep, do not read whole).
3. Non-liquid "plan value" label in `live_snapshot.js`. Light.
4. Verify against the user's data (Matt joint 840,200 in Current Snapshot), run trends tests + fast suite.
   Moderate (the fast suite is ~35 min; run in the background).

Check `/usage` against these after step 4.
