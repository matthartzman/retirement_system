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
wellness shock. Gated on `hsa_withdrawal_mode` — see "Mode interaction"
below, which is load-bearing for this option and narrows where it fires.

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

## Mode interaction: defer to `hsa_withdrawal_mode`, do not override it

This was originally left open here with a recommendation to override the
mode. **That recommendation is withdrawn** — reading the existing
precedent reversed it.

`withdraw_hsa_gap` (`planning_engines.py:1112-1135`) already suppresses
unscheduled HSA draws: unconditionally under `optimize`, and before and
during the configured window under `smooth_window`/`annual_pct`. That
suppression is not arbitrary. Its own comment records a **real
user-reported bug (2026-08-20)**: a household entered a $2,000/yr
override, unscheduled gap-fills stacked on top of the scheduled draw, and
the account drained years before the household expected. The established
rule is that when a household configures a scheduled mode, *the schedule
is the sole authority on that year's draw*.

A contingent-liability draw layered on top of a scheduled draw
re-introduces exactly that defect shape. Two specifics that make the
override position untenable:

1. **It really is double-depletion, not self-correcting arithmetic.** With
   `smooth_window` (balance $80k, 8 years left → $10k scheduled) and a $40k
   shock, a CL-first draw makes that year's total $45k — 4.5x the
   household's chosen pace. The window still zeroes by its end year, but
   every subsequent year runs on a materially smaller balance.
2. **HSA dollars are not stranded during a window.** The scheduled draw
   already feeds HSA cash into the general pool every window year, and
   `total_spend_need` (which includes `ltc_prem_yr`/`wellness_shock_yr`)
   is funded from that pool. A CL-first rule would not unlock otherwise
   unreachable money during the window; it would only accelerate the
   schedule.

**Decision: reuse the gating `withdraw_hsa_gap` already has** rather than
inventing a second, competing rule.

| Mode | CL-first draw |
|---|---|
| `spend_as_needed` (the parse default) | Applies |
| `smooth_window` / `annual_pct` | Suppressed before and during the window; permitted after it ends |
| `optimize` | Suppressed (see below) |

This does not hollow out the increment. `ltc_prem_yr` receives **no**
HSA-preferential treatment in any engine or any mode today, and
`spend_as_needed` is the parse default for any household that has not
configured a window (`data_io.py:1273-1275`). Aligning the three engines —
the stated goal — is unaffected.

### `optimize` mode: suppressed here, but it belongs in the scheduler

Suppression under `optimize` is correct for a *different* reason than the
window modes, and the distinction matters to whoever picks this up next.

**`optimize` is reachable from real plan data.** `data_io.py:1274` admits
it in the allowed-modes tuple. Note that the 2026-08-19 entry in
`documentation/GOLDEN_MASTER_CHANGELOG.md` states `optimize` is coerced
back to `spend_as_needed` and therefore affects no household — **that
claim is stale**; the mode has since been admitted. Do not rely on it.

What is *not* wired is the search. Per `src/hsa_schedule.py`'s own module
docstring, `rerun_optimizer`/`build_schedule` are never called from the
projection pipeline: they need full per-year projection rows for tax
context (`score_year`'s `row` argument), which only exist after a
projection runs — deliberately deferred to a future two-pass sequence.
What *is* live is `resolve_year_amount`'s precedence ladder reading
`client_hsa_schedule.csv`, plus `generate_default_schedule`'s static
level-draw placeholder.

So under `optimize` today the year's draw comes from a schedule file that
knows nothing about contingent-liability need — and silently overriding it
is precisely the 2026-08-20 defect. But `optimize` is also the one mode
where contingent-liability need *should* influence the outcome, and the
right layer for that is the schedule itself: a scheduler that knows year
2033 carries a $40k LTC event and places HSA dollars into that year
produces a better plan than any post-hoc draw could.

**Hook for whoever wires the two-pass search:** `score_year` already
receives a projection `row`, and Phase 0 put `row['spend_by_tier']` —
including `contingent_liability` — on every row, so the signal is present
in the data the scorer gets.

> ⚠️ **Superseded.** This paragraph originally went on to recommend making
> that signal a scoring term. Follow-up research
> (`2026-08-26-hsa-schedule-search-contingent-liability-spec.md`) found
> that wrong; it was written here before `score_year` had been read.
> `score_year` prices tax efficiency — `(displacement + irmaa_cliff) *
> pv_factor`, where displacement is the marginal rate on the dollar the
> draw displaces. But a contingent-liability year is a *low* marginal-rate
> year: `ltc_prem_yr` and `wellness_shock_yr` both feed
> `medical_expense_yr` and generate an itemized deduction above the
> 7.5%-of-AGI floor (`deterministic_engine.py:1876`). A positive CL
> scoring term would therefore push draws toward the years the tax model
> has already priced as the *least* valuable to draw in — double-counting
> a signal the deduction already transmits, and transmitting it with the
> wrong sign.
>
> The suppression under `optimize` is still correct; only the proposed
> remedy was wrong. The real gap is that per-year tax-free draw capacity is
> not modeled at all (`hsa_expense_bank` is a single lifetime scalar
> defaulting to unlimited), so the model already permits tax-free draws in
> years with no qualified expense. See that spec for corrected options.

## Recommendation

Ship Option A as the next increment, gated by the mode-deference rule
above. Concretely:

1. New helper in `planning_engines.py` (or `deterministic_engine.py`,
   colocated with the other named withdrawal-priority functions) —
   `fund_contingent_liability_from_hsa(c, bal, ltc_prem_yr, wellness_shock_yr,
   year, spend_floor_base)` — returns amount drawn, by-account breakdown,
   and residual un-covered contingent-liability dollars (folded back into
   `total_cash_need`'s existing gap so the rest of the cascade is
   unchanged).
2. **Gate it on `hsa_withdrawal_mode` using the same predicate
   `withdraw_hsa_gap` already applies** (suppressed under `optimize`;
   suppressed before and during the window under
   `smooth_window`/`annual_pct`). Factor that predicate out of
   `withdraw_hsa_gap` into a shared helper rather than copying it, so the
   two call sites cannot drift — a silent divergence here is exactly the
   class of bug the 2026-08-20 fix was cleaning up.
3. Insert it in the deterministic cascade **before Priority 2's scheduled
   HSA draw**, so that under `spend_as_needed` (where it is active) the
   contingent-liability claim is satisfied first and the scheduled draw
   sizes itself against whatever remains. Under the gated-off modes this
   step is a no-op and Priority 2 behaves exactly as today.
4. Extend `_mc_vectorized_projection`'s existing shock-only HSA-first
   handling to also draw `ltc_prem_yr` (today it's shock-only), under the
   same gate, so the vectorized MC engine and the deterministic/scalar
   engines apply the same rule.
5. New regression test file (`tests/test_contingent_liability_hsa_funding_regression.py`,
   matching this repo's `test_<scope>_<type>.py` convention) covering: (a)
   under `spend_as_needed`, HSA balance fully covers a configured
   `ltc_annual_prem` → HSA balance drops by that amount, taxable/pretax/Roth
   draws are unaffected; (b) HSA balance insufficient → HSA drained first,
   residual falls through the existing cascade unchanged in total; (c) no
   HSA balance / no `hsa_ids` → cascade is bit-identical to today
   (regression guard); (d) **under `smooth_window`/`annual_pct` inside the
   window, and under `optimize`, the cascade is bit-identical to today** —
   the guard that the mode-deference decision above is actually honored,
   and the one most likely to catch a future refactor re-introducing the
   2026-08-20 defect; (e) frozen golden master unmoved (confirms the $0
   contingent-liability-on-fixture finding above holds after the change,
   not just before it).
6. Verify against the same discipline as every prior increment: targeted
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
diffing, not just asserted.

The mode-deference decision narrows the blast radius further, and in the
frozen fixture's favor twice over: the fixture sets
`hsa_withdrawal_mode = smooth_window` with a 2031-2040 window
(`client_assets.csv`), so even a household-shaped-like-the-fixture with an
LTC premium configured would see this step gated off inside that window.

Real effect is therefore scoped to:

- Households on `spend_as_needed` (the parse default) configuring
  `ltc_annual_prem` > 0, where HSA balance now funds it preferentially
  instead of falling into the generic cascade.
- Households on `smooth_window`/`annual_pct` **after** their window ends,
  same case as above — matching `withdraw_hsa_gap`'s own "any remaining
  HSA balance is fair game" rule for post-window years.
- Monte Carlo `success_rate` for those same households when a wellness
  shock is sampled, since `ltc_prem_yr` joining the HSA-first treatment
  (previously shock-only) changes which dollars draw HSA vs.
  taxable/pretax on paths that also carry an LTC premium.

Households on `optimize`, or inside an `annual_pct`/`smooth_window`
window, are bit-identical to today by construction — pinned by test (d)
above.

## Open questions

**None blocking.** The one open question this document originally carried
— whether the new draw overrides `hsa_withdrawal_mode` or defers to it —
was decided during review in favor of **deferring**, on the strength of
the 2026-08-20 double-depletion bug and the two specifics recorded under
"Mode interaction" above.

One item to confirm during implementation (narrowing, not blocking): the
deterministic engine calls `withdraw_hsa_window(..., wellness_cost=...)`.
If `wellness_cost` already includes `wellness_shock_yr` under
`spend_as_needed`, then shocks are already HSA-funded in that mode and the
genuinely-new coverage is `ltc_prem_yr` alone. Confirm from the call site
rather than assuming; it changes the size of the change, not its shape.
