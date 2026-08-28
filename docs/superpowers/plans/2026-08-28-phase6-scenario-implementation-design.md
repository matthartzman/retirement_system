# Phase 6 — Divorce/QDRO and SS Benefit-Cut Scenarios — Implementation Design

Follow-up to `docs/superpowers/plans/2026-08-27-phase6-expanded-stress-scenarios-spec.md`,
written while PR #80 (Phase 4 implementation) was in CI. That spec recommended
Option A (add specific scenarios to `sheets_stress.py`'s existing hardcoded
pattern) scoped to Divorce/QDRO and Social Security benefit-cut exposure, but
left "which scenario(s), specifically" and their mechanics as open product
questions. This document resolves the *mechanical* half — exactly what each
scenario needs, grounded in code now read rather than inferred — so a
sign-off round (mirroring Phase 4/5's "confirm the exact rule before code")
can be short and concrete instead of re-opening the whole design space.

**Spec/research only — no code in this document.**

## Finding: the two candidates are NOT equally cheap to build

The original Phase 6 spec treated Divorce/QDRO as "a stress-scenario
approximation... modeled via `run_scenario` overrides," implying it was in
the same league as the other Sheet 16 scenarios. Reading `build_sheet16`
(`sheets_stress.py:521-792`) and the deterministic engine's Social Security
calculation (`deterministic_engine.py:989-1063`) shows that is true for one
candidate and NOT the other.

### SS benefit-cut exposure: fully achievable with existing config fields, zero new schema

Every existing Sheet 16 scenario (`High Inflation`, `Low Return`, `Retire
Later`, etc.) works by calling the sheet's local `run_scenario(overrides)`
closure (`sheets_stress.py:538-541`, itself a thin wrapper over
`planning_engines.run_scenario`) with a dict of **existing** config field
overrides, then reading `rows[-1]['total_nw']` and summed `total_tax`.

Social Security benefits are computed from `c['h_ss_pia']`/`c['w_ss_pia']`
(`deterministic_engine.py:992-993`, falling back to a benefit table) —
already-existing, already-read config fields with no engine changes needed
to scale them. A benefit-cut scenario is therefore just:

```
nw_ss_cut, tax_ss_cut = run_scenario({
    'h_ss_pia': c['h_ss_pia'] * (1 - CUT_PCT),
    'w_ss_pia': c['w_ss_pia'] * (1 - CUT_PCT),
})
```

exactly the same shape as the existing `High Inflation`/`Low Return` rows,
with **zero new config fields, zero engine changes**. `CUT_PCT` is the one
open parameter (the widely-cited ~21% haircut tied to the OASI trust fund's
projected mid-2030s depletion is the obvious anchor, but the exact figure
and which year it's framed as taking effect are product decisions, not
engineering ones).

### Divorce/QDRO: a one-time asset split is equally cheap; ongoing alimony is NOT

- **One-time asset split** (the QDRO half): also achievable via a plain
  config override, no new engine code — `run_scenario` deep-copies `c`
  before applying overrides, so an override that reduces a specific
  account's starting balance (mirroring how the existing `Sell Home`
  scenario already manipulates account state via `home_sale_acct`/
  `home_sale_px`) works the same way: e.g. `{'balances': {**c['balances'],
  <account_id>: c['balances'][<account_id>] * (1 - SPLIT_PCT)}}`.
- **Ongoing alimony/support cash flow** (the "divorce" half beyond the
  asset split): **NOT achievable via override alone**. `spend_base` is a
  single flat scalar applied to every plan year via `_spending_factor(year)`
  (`deterministic_engine.py:1103`) — there is no year-range-scoped spend
  override anywhere in the engine (confirmed: no `alimony`, `one_time_
  transfer`, `extra_expense`, or per-year-range spend-delta field exists in
  `deterministic_engine.py`). Representing "an extra $X/yr from divorce
  year through year N, then nothing" would require either genuinely new
  engine logic (a bounded-year-range expense field) or a crude
  approximation (permanently raising `spend_base`, which is wrong for any
  plan where alimony ends before the plan does).

This means the original Phase 6 spec's framing — "a one-time asset split
plus ongoing alimony cash flow, modeled via `run_scenario` overrides" — was
only half right. The asset-split half fits this refactor's established
"reuse an existing pattern" discipline; the alimony half does not, and
building it properly is a small but real engine change (a new bounded-
duration expense field), not a config-only addition.

## Options for Divorce/QDRO specifically

**Option D1 — Asset-split only, no alimony (recommended for this
increment).** Model Divorce/QDRO as a one-time balance reduction on a
CSV-configurable account at a CSV-configurable year, with no ongoing
support payment. Honest about its own limitation (the sheet's scenario
description would say so explicitly, e.g. "asset division only; does not
model ongoing spousal support"). Fits the zero-new-engine-code, override-only
pattern every other Sheet 16 scenario uses.

**Option D2 — Asset split plus a permanent post-divorce spend increase.**
Approximates alimony as a `spend_base` increase from the divorce year
onward with no end date. Cheap (still just an override), but wrong in the
common case where support payments are time-limited — likely to produce a
misleading terminal-wealth number that understates the plan's real
resilience once alimony would have ended.

**Option D3 — Add a genuinely new bounded-duration expense field first,
then build the full scenario.** The financially correct approach (asset
split + time-limited alimony), but requires new engine code (a new
config field read by `deterministic_engine.py`, most likely modeled the
same shape as `client_spending_budget_lines.csv`'s existing `start_year`/
`end_year`/`amount_per_year` per-line pattern, or as a dedicated
`divorce_alimony_start_yr`/`end_yr`/`amount` triple) — a materially larger
change than anything else in Sheet 16, closer to the original Phase 6
spec's already-flagged Option C (implement Divorce/QDRO as a full module)
than to Option A's "add a scenario" framing.

## Recommendation

Ship **SS benefit-cut** and **Divorce/QDRO Option D1** (asset-split only)
together as the Phase 6 increment — both are genuinely zero-new-schema,
override-only additions matching every existing Sheet 16 scenario's shape,
consistent with the original spec's Option A recommendation. Treat
Option D2 as not worth building (cheap but produces a systematically
wrong number) and Option D3 (full alimony modeling) as an explicitly
separate, larger future item if a real need for it surfaces — the same
"ship the safe slice now, revisit the bigger one only if something demands
it" discipline this refactor has used at every prior phase.

## Open questions requiring sign-off before any code

1. **SS cut percentage and framing.** Recommend ~21% (OASI trust-fund
   depletion projection) as the default, CSV-configurable. Should the
   scenario also let the cut phase in at a specific year rather than
   applying from plan-start, or is a flat "apply the full cut for the
   whole plan" scenario (matching every other Sheet 16 scenario's
   single-shot, whole-plan-horizon shape) good enough?
2. **Divorce/QDRO split parameters.** Which account (a specific CSV-named
   account, or a household-wide percentage applied across all
   investment accounts)? What split percentage (50/50 is the common
   default assumption, but should it be CSV-configurable)? What year
   (a fixed near-term year, or CSV-configurable)?
3. **Confirm Option D1's limitation is acceptable for this increment** —
   i.e., that shipping an asset-split-only Divorce/QDRO scenario (no
   alimony) now, with Option D3's full alimony modeling explicitly
   deferred, is the right scope rather than waiting to build both pieces
   together.
