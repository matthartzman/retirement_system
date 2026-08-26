# Contingent-Liability Funding Rules — Design

Optimization refactor, next increment after PR #64 (tier-priority MC
spending-cut reporting). **Design only — no code in this document.**
Picks up the "Not done" item in `documentation/OPTIMIZATION_REFACTOR_STATUS.md`:
*"Contingent-liability funding rules."* That doc gives no further detail
beyond the name — the plan itself never specified what a "funding rule"
should mean, so this document works it out from the engine's current
behavior before proposing one.

## What "contingent_liability" actually contains today

Two components feed `row['spend_by_tier']['contingent_liability']`
(`src/projection_stages/deterministic_engine.py:1764`):

```python
_tier_add('contingent_liability', ltc_prem_yr + wellness_shock_yr)
```

- **`ltc_prem_yr`** — a recurring, budgeted LTC insurance premium
  (`c['ltc_annual_prem']`). This is arguably misclassified: it's a known,
  scheduled expense like any other insurance premium (essential-tier
  material), not an irregular shock. It's tagged `contingent_liability`
  only because it exists to *hedge against* a contingent liability, not
  because paying it is itself contingent.
- **`wellness_shock_yr`** — a genuine irregular cost (LTC event, major
  medical, home modification), but it is **only ever non-zero inside a
  Monte Carlo path** (`c['wellness_shock_by_year']`, sampled per-path from
  `wellness_shock_annual_prob`/`wellness_shock_mean_cost` in
  `_mc_vectorized_inflation_health_paths`/the scalar per-path equivalent).
  The deterministic `project()` call that produces every pinned figure
  never populates `wellness_shock_by_year`, so `wellness_shock_yr` is
  always `0.0` in a single deterministic run.

**Confirmed on the frozen golden-master fixture**
(`tests/fixtures/sample_plan_frozen/`): no `ltc_annual_prem` is configured
in `client_assets.csv`, and the deterministic engine never samples
`wellness_shock_yr`. So `spend_by_tier['contingent_liability']` is `$0.00`
on the frozen fixture's deterministic run today — any funding-rule change
scoped to this tier is provably a no-op for the golden-master pins, the
same "confirmed inert on the pinned household" property every prior
increment in this project has required before shipping.

## What "funding rule" means today: nothing

`ltc_prem_yr` and `wellness_shock_yr` are summed straight into
`total_spend_need` (`deterministic_engine.py:1518-1519, 1717-1719`)
alongside every other spending component, with **no distinguishing
treatment** once they enter the cascade. The withdrawal cascade that
actually funds `total_spend_need` is, in order:

1. RMD (forced, already applied to income)
2. HSA — **scheduled window draw, not gap-dependent**
   (`withdraw_hsa_window`, Priority 2)
3. Pre-tax elective (Priority 3)
4. Taxable/trust, above the configured liquidity-reserve floor (Priority 4)
5. Priority 4b: final pre-tax settle-up
6. Priority 4c: **generic HSA gap-fill** (`withdraw_hsa_gap`) — draws
   remaining HSA balance against *whatever* residual `gap` still exists
   after 1-4b, not specifically medical/contingent dollars
7. Roth (last resort)
8. Home equity tap (eliminated; HELOC draw already inside withdrawals)

Nothing in this cascade knows which dollars of `gap` came from
`contingent_liability` spend versus essential/important/discretionary
spend — money is fungible by the time it reaches the cascade. HSA
participation is *incidental*: Priority 2 fires on a schedule (or,
in `spend_as_needed` mode, sized to that year's `wellness_cost` — see
below) regardless of contingent-liability spend, and Priority 4c only
fires as a last-resort gap-filler after taxable/pretax have already been
drawn, not as a first-resort for medical dollars specifically.

**One partial exception already exists, but only in the vectorized MC
engine's shock-handling** (`_mc_vectorized_projection`,
`planning_engines.py:4002-4004`):

```python
shock_need = shocks[:, j] * act
hsa_shock, shock_left = _mc_apply_withdrawal_bucket(balances, shock_need, 'hsa')
planned['taxable'] = planned['taxable'] + shock_left
```

Wellness-shock dollars specifically draw HSA first, spilling any excess to
taxable. This is real, deliberate precedent for "contingent-liability
dollars prefer HSA" — but it's isolated to the MC shock path; it doesn't
cover `ltc_prem_yr`, doesn't exist in the deterministic engine or the
scalar MC engine at all, and (per `withdraw_hsa_window`'s docstring) is
bypassed entirely when `hsa_withdrawal_mode` isn't `spend_as_needed` — the
frozen fixture itself is configured `smooth_window`, which ignores
wellness cost and just levels the balance across a fixed window regardless
of medical need.

## Why an explicit rule is the right next increment

HSA dollars are the one tax-advantaged vehicle in this codebase's account
registry literally designed for medical costs (tax-free in, tax-free out
for qualified expenses — LTC premiums up to IRS age-based limits and
medical shocks both qualify). Directing contingent-liability spend there
preferentially, ahead of taxable/pretax/Roth, is not just internally
consistent with the existing vectorized-MC-shock precedent above — it's
the financially correct behavior a real planner would recommend, and it's
the natural first "explicit state-dependent funding rule" the plan's
phrasing calls for: contingent-liability dollars get a *distinct* funding
priority instead of being invisible once summed into `total_spend_need`.

## Options considered

**Option A — HSA-preferential funding for contingent-liability dollars**
(recommended). Before Priority 2's scheduled draw or in a new dedicated
step ahead of Priority 3, draw available HSA balance against this year's
`ltc_prem_yr + wellness_shock_yr` specifically (bounded by the account's
qualified-expense availability, same `hsa_available_to_draw`-style bound
`withdraw_hsa_window`'s `requested` path already uses), then let any
un-covered residual fall through the existing cascade unchanged. Mirrors
the existing vectorized-MC-shock precedent, extends it consistently to
`ltc_prem_yr`, to the deterministic engine, and to the scalar MC engine
(which today gets this "for free" only insofar as it reruns `project()`
per path — i.e. it inherits whatever the deterministic engine does, so
fixing the deterministic engine fixes the scalar MC engine at the same
time). No new config field — reuses the existing `hsa_ids`/HSA-availability
machinery. **Provably inert on the frozen fixture** (contingent_liability
tier is $0 there), so the golden master pins do not move; real effect only
for households with `ltc_annual_prem` configured or (in MC only) a sampled
wellness shock.

**Option B — A dedicated contingent-liability reserve**, analogous to the
existing Liquidity Buffer's `reserve_account` mechanic (a segregated dollar
floor, held back from ordinary withdrawals, released only for contingent
spend). Requires a new config field (schema/UI/docs decision, same class
of complexity flagged separately for the "legacy floor" Not-done item) and
a new floor-composition rule interacting with the existing liquidity
buffer floor (same open question the Roth-conversion-tax-source design doc
flagged for a similar floor interaction — see
`docs/superpowers/plans/2026-08-17-roth-conversion-gap-design.md`, "Interaction
with the liquidity-buffer floor"). Larger scope; deferred.

**Option C — Reclassify `ltc_prem_yr` out of `contingent_liability`** into
`essential` (it's a scheduled premium, not a shock) and leave the funding
question to the shock-only remainder. Worth doing eventually for taxonomy
correctness, but doesn't by itself add any funding rule — it's a
relabeling, not a fix — and would need its own Phase-0-style regression
coverage (mirroring `tests/test_spending_tier_taxonomy.py`) to avoid
silently changing `spend_by_tier` percentages that other reporting (the
Phase 2 dashboard metrics) already reads. Out of scope for this
increment; noted as a legitimate follow-up.

## Recommendation

Ship Option A as the next increment. Concretely:

1. New helper in `planning_engines.py` (or `deterministic_engine.py`,
   colocated with the other named withdrawal-priority functions) —
   `fund_contingent_liability_from_hsa(c, bal, ltc_prem_yr, wellness_shock_yr,
   year, spend_floor_base)` — returns amount drawn, by-account breakdown,
   and residual un-covered contingent-liability dollars (folded back into
   `total_cash_need`'s existing gap so the rest of the cascade is
   unchanged).
2. Insert it in the deterministic cascade **before Priority 2's scheduled
   HSA draw** (contingent-liability need is the more specific claim on the
   HSA balance; the scheduled draw should size itself against whatever
   remains, not double-count).
3. Extend `_mc_vectorized_projection`'s existing shock-only HSA-first
   handling to also draw `ltc_prem_yr` (today it's shock-only), so the
   vectorized MC engine and the deterministic/scalar engines apply the
   same rule.
4. New regression test file (`tests/test_contingent_liability_hsa_funding_regression.py`,
   matching this repo's `test_<scope>_<type>.py` convention) covering: (a)
   HSA balance fully covers a configured `ltc_annual_prem` → HSA balance
   drops by that amount, taxable/pretax/Roth draws are unaffected; (b) HSA
   balance insufficient → HSA drained first, residual falls through the
   existing cascade unchanged in total; (c) no HSA balance / no `hsa_ids`
   → cascade is bit-identical to today (regression guard); (d) frozen
   golden master unmoved (confirms the $0 contingent-liability-on-fixture
   finding above holds after the change, not just before it).
5. Verify against the same discipline as every prior increment: targeted
   tests, full `-m "not slow"` diff against baseline, `-m slow` pass (this
   touches the withdrawal cascade, which the Phase 1 items 4-6 methodology
   lesson in `OPTIMIZATION_REFACTOR_STATUS.md` specifically warns needs an
   unfiltered pass), then push and check CI.

## Expected pin movement

**None expected.** The frozen fixture's `contingent_liability` tier is
$0.00 in the deterministic run (no `ltc_annual_prem` configured, no
sampled wellness shock in `project()`), so Option A's new funding step has
nothing to draw and is a complete no-op on the pinned household — to be
confirmed by running the golden-master regen script before and after and
diffing, not just asserted. Real effect is scoped to: (a) any household
configuring `ltc_annual_prem` > 0, where HSA balance now funds it
preferentially instead of falling into the generic cascade, and (b) Monte
Carlo `success_rate` for households with a sampled wellness shock, since
`ltc_prem_yr` joining the HSA-first treatment (previously shock-only)
changes which dollars draw HSA vs. taxable/pretax in MC paths that also
carry an LTC premium.

## Open question needing an explicit decision before implementation

`withdraw_hsa_window`'s `smooth_window`/`annual_pct` modes are indifferent
to actual medical need (they level or fixed-percent the balance on a
schedule) — see the frozen fixture, which uses `smooth_window`. Should the
new contingent-liability-first draw apply **regardless of
`hsa_withdrawal_mode`** (treating it as a distinct, higher-priority claim
that runs before the mode-specific scheduled draw touches whatever HSA
balance remains), or should it defer to a household's explicit
`hsa_withdrawal_mode` choice and only activate under `spend_as_needed`
(mirroring `withdraw_hsa_window`'s own mode-gating)? This document
recommends the former — a contingent-liability bill should not go unfunded
by HSA cash a scheduled `annual_pct` draw hasn't gotten to yet — but this
is a real behavior decision, not just an implementation detail, and should
be confirmed before writing the code.
