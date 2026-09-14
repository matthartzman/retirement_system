# HSA withdrawal optimizer — design and implementation plan

**Date:** 2026-08-17 · **Status:** design, open decisions resolved · **Revision:** 3

**Scope:** when and how much to withdraw from HSA accounts, phased by an optimizer and overridable
by the user.

**Stated assumptions and decisions:**
- Enough substantiated historical medical expenses exist to withdraw the **entire** balance tax-free
  in **any** year. Timing is unconstrained by current-year medical spending.
- **No future contributions.** The balance is a closed pool.
- **Beneficiary is the spouse**, with the cliff therefore falling at **second death** (contingent
  beneficiary assumed non-spouse).
- **Decided:** the HSA must be **fully consumed before second death**. This is a hard constraint, not
  an optimizer output.
- **Decided:** the terminal-cliff model and the optimizer ship **together**, not as separate releases.
- **Decided:** the objective **reuses** the Roth conversion objective, weights and
  `roth_tax_discount_rate`, plus one HSA-specific **residual-cliff** term (§3.1).
- **Decided:** surplus follows a **waterfall** — spending needs, then Roth conversion tax, then
  taxable (§3.2).
- **Decided:** the deadline defaults to the **90th-percentile** second-death year, configurable.

---

## 1. What the model gets wrong today, and what the constraint changes

### 1.1 The gap

An HSA is currently a *strictly dominant* asset in this engine:

| Stage | Modeled treatment | Where |
|---|---|---|
| Growth | Tax-free | `_mc_apply_bucket_growth` |
| Withdrawal | **Never enters AGI or taxable income** | `deterministic_engine.py:1851` |
| At death | **Not modeled at all.** `hsa_nw` flows into terminal net worth at 100¢ | `after_tax.py` |

`after_tax.py` discounts `pretax_nw` by an heir ordinary rate and `trust_nw` by basis/LTCG. **HSA
appears nowhere in it.** In reality, at second death the account stops being an HSA: the whole
balance is ordinary income to a non-spouse beneficiary **in that single year** — no stretch, no
basis, no step-up.

Spouse-as-primary removes the *first*-death cliff entirely (tax-free rollover). It does not remove
the second-death cliff. Avoiding that is exactly what the consume-before-second-death decision does.

### 1.2 How the constraint changes the problem

Unconstrained, the optimizer would have to *discover* that draining beats holding, and that discovery
is only possible once the cliff is modeled. Constrained, the question narrows to a better one:

> Given that the balance must reach zero by a deadline, **which years should the withdrawals land in**?

The terminal cliff stops being the objective's main term and becomes two smaller things:
1. **The justification** for the constraint — worth modeling so the plan can *show* what the
   constraint is buying rather than asserting it.
2. **A residual guard** — if the deadline is missed or the constraint proves infeasible, whatever
   remains gets taxed, and the plan should say so rather than silently valuing it at 100¢.

This is why shipping H1 separately buys less than it would have: with the constraint in force, a
well-behaved plan never pays the cliff, so H1 moves the headline number far less than it would in the
unconstrained design. Your call to combine them follows from your own constraint.

**One caveat, recorded rather than argued:** combining still means the correction to existing plans
and the new optimizer's effects land in one golden-master regeneration. If a number later looks
wrong, it cannot be attributed to one or the other without re-running an intermediate build. The
mitigation is H1.3's acceptance test, which pins the cliff's effect independently of the optimizer.

### 1.3 The non-obvious consequence: survivor years are worth more

With a spouse beneficiary the window spans a **filing-status change**. After the first death the
survivor files **Single**, with roughly half the bracket widths and a much lower IRMAA threshold. An
HSA dollar displaces a *higher*-taxed alternative dollar in those years.

So the optimal schedule is **not** a level drawdown. It weights toward:
- survivor years (compressed Single brackets),
- years brushing an IRMAA or ACA cliff,
- years with a large Roth conversion in flight,

subject to finishing by the deadline. A naive "divide the balance by remaining years" schedule — which
is what today's `smooth_window` mode does — is close to the worst reasonable answer, because it puts
equal weight on cheap early joint-filing years and expensive late survivor years.

---

## 2. Inputs the system does not have

### 2.1 Blocking

| # | Input | Status | Why decisive |
|---|---|---|---|
| ~~B1~~ | HSA beneficiary type | ✅ **Resolved** — spouse primary, non-spouse contingent | — |
| ~~B4~~ | Objective and weights | ✅ **Resolved** — reuse Roth + residual term (§3.1) | — |
| ~~B5~~ | Longevity assumption for the deadline | ✅ **Resolved** — default 90th-percentile second death, configurable (§2.2) | — |
| **B3** | Which spouse owns each HSA | ⚠️ **Verify on `account_registry`** | Determines which death is "first" for *that* account, and how much rolls over. The only remaining input assumed rather than confirmed |

### 2.2 B5 — the deadline is a genuine risk trade-off, not a lookup

The engine models mortality (`sample_death_year`, survivor logic), so it can produce a distribution.
It cannot tell you which point on it to plan against, and the two failure modes are asymmetric:

- **Deadline too early** (plan to median second death, both live longer) → the tax-free bucket is
  gone in the years the survivor most needs it, and every later dollar is taxable at Single rates.
  This is the *expensive* failure.
- **Deadline too late** (plan to 95th-percentile longevity, die sooner) → a residual is left and pays
  the cliff. This is the *bounded* failure — capped at the residual balance times the heir's rate.

Because the failures are asymmetric, the deadline defaults to a **conservative high-percentile
second-death year — the 90th** — rather than the median, and the residual term prices whatever is
left. That trades a small, bounded, disclosed cliff risk against a large, unbounded loss of tax-free
capacity in exactly the years it is scarcest.

**Resolved: `hsa_consume_by = second_death_p90`, configurable** (accepts any percentile or an
explicit year).

**Why the exact percentile matters less than it first appears.** Once the objective carries a
probability-weighted residual term (§3.1), the objective *already* pulls withdrawals earlier than a
p90 deadline requires — dying at the 30th percentile leaves a large taxable balance, and the term
prices that. So the constraint becomes a **backstop that shapes nothing in a well-behaved plan**,
while the objective does the actual shaping. Choosing p85 versus p90 should move most schedules very
little; a plan where it moves them a lot is a plan worth looking at, and the feasibility reporting in
§3.3 will say so.

### 2.3 Materially affects the answer

| # | Input | Why |
|---|---|---|
| **M1** | State HSA conformity | CA and NJ do not recognize HSAs — earnings taxable annually at state level, no state-level tax-free withdrawal. `state_residency` already exists; this is a conformity flag away |
| **M2** | Invested vs cash within the HSA | Sets the opportunity cost of withdrawing early. HSAs commonly hold a cash floor with only the excess invested; that floor is not represented |
| **M3** | Survivor filing-status transition year | Already modeled for other buckets — the HSA scheduler must consume it (§1.3) |

### 2.4 Waived by assumption, still carried in the design

| # | Input | Note |
|---|---|---|
| **W1** | Substantiated expense bank | Assumed unlimited. Model explicitly with an unlimited default so it can be tightened later without redesign |
| **W2** | Non-qualified withdrawal treatment | Post-65 ordinary income; pre-65 ordinary income **+ 20% penalty**. Never binds under W1, but must exist or the model silently permits penalty-free pre-65 raids |
| **W3** | Owner age per HSA | Only for W2's pre-65 branch |

### 2.5 Out of scope

Future contributions, HDHP eligibility, and contribution-limit indexing
(`family_annual_limit_base_year`, `index_hsa_limit`, `requires_hdhp`) are untouched.

---

## 3. Design

### 3.1 The withdrawal decision, as a constrained phasing problem

**Constraint:** cumulative withdrawals ≥ projected balance by the deadline year (B5); balance
reaches ~0 and stays there.

**Objective — reuse, plus one term.** The HSA optimizer scores against the **existing Roth
conversion objective**: `roth_objective_mode`, `roth_optimize_terminal_weight`,
`roth_optimize_lifetime_tax_weight`, and `roth_tax_discount_rate`. It does **not** get its own
objective mode or its own discount rate.

The reason is correctness, not economy. H3.3 requires HSA draws and Roth conversions to be scored
**jointly** — an HSA draw frees the bracket headroom a conversion consumes. Two objectives with
different weights or different discount rates make joint scoring ill-defined: the result would depend
on which optimizer ran first. One objective is the only formulation where the joint answer is stable.
Reuse also keeps a single consistent estate, since both optimizers already score against the same
after-tax terminal net worth.

**The one addition:** a **residual-cliff term** — the expected lump-sum tax on any balance still held
at death, probability-weighted over the modeled mortality distribution and discounted at
`roth_tax_discount_rate`. This term does not exist in the Roth objective and cannot be borrowed from
it, because inherited pre-tax balances get the 10-year stretch while an HSA does not.

**Why the residual term is load-bearing rather than a refinement.** Under the constraint, total
withdrawals are fixed, so the objective reduces mostly to present-valued lifetime tax. Two forces
push the drawdown **later** — tax-free compounding retained inside the HSA, and the higher
displacement value of survivor years (§1.3) — and only residual risk pushes it **earlier**. Omit the
residual term and both remaining forces point the same way: the optimizer back-loads the entire
balance into the final years before the deadline, maximizing exposure to an early death. **That
schedule would pass every feasibility and constraint test while being the worst realistic answer.**
H3.5 must reject it explicitly.

**Per-year scoring terms:**
- **Displacement value** — tax avoided on the alternative dollar (IRA at the marginal rate, or
  taxable at LTCG plus NIIT), *at that year's filing status*;
- **Cliff value** — IRMAA tier or ACA subsidy crossing avoided. Step functions, so this term
  dominates near a threshold;
- **Conversion complementarity** — an HSA draw lowers AGI, freeing bracket headroom for a Roth
  conversion the same year;
- **Carry cost** — tax-free compounding forgone by withdrawing sooner;
- **Residual risk** — as above.

### 3.2 Surplus waterfall

Draining by the deadline can produce more cash than the plan needs to spend. The surplus follows a
fixed priority order:

| Priority | Destination | Rationale |
|---|---|---|
| 1 | **Spending needs** | Displaces a taxed dollar. Always the highest-value use |
| 2 | **Tax on a larger Roth conversion** | The HSA draw just *created* the bracket headroom by lowering AGI. Paying conversion tax from outside the IRA is what makes a conversion efficient, and a tax-free bucket that must be drained anyway is the cheapest possible source of those dollars. Converts surplus into **tax-free** growth |
| 3 | **Taxable account** | Last resort. Preserves the constraint but the surplus grows taxable thereafter |
| — | *Bend the deadline* | **Never.** See §3.3 |

Priority 2 is the reason the joint scoring in H3.3 is not optional: without it the optimizer cannot
see that an HSA draw and a larger conversion are the same decision, and will route surplus to taxable
while leaving conversion headroom unused.

**Guardrail against over-conversion.** Priority 2 must not become a reason to convert more than the
Roth objective independently justifies. The surplus changes *how the tax is funded*, never *how much
conversion is worth doing*. H3.3's test must pin this: given identical inputs, the conversion amount
chosen with an HSA surplus available must not exceed the amount the Roth optimizer would choose on
its own merits with the same after-tax funding available from another source.

### 3.3 Feasibility, which must be an explicit outcome

The constraint can be infeasible: a large HSA against a short window and modest spending may not be
consumable without either non-qualified withdrawals or withdrawing more than the receipt bank
supports (once W1 stops being unlimited). The engine must **name** this rather than silently
approximating:

| Outcome | Behavior |
|---|---|
| Feasible | Schedule produced; residual 0 |
| Feasible only by exceeding spending needs | Schedule produced, surplus follows the §3.2 waterfall; **warn** that the drawdown has become partly an asset-location move rather than a spending move |
| Infeasible by the deadline | Best-effort schedule + explicit residual, with the cliff priced and disclosed. **Never silently relax the deadline** |

### 3.4 Optimizer-defines / user-overrides contract

Mirrors the existing Roth precedent, which already solves this in this codebase:
`roth_conversion_policy` carries an optimize value among manual ones; `roth_bracket_strategy` carries
an `OPTIMIZER_CHOOSES` sentinel; and `roth_optimize_terminal_pretax_tax_rate` documents the
**derived-unless-overridden** idiom.

| Layer | Mechanism | Precedence |
|---|---|---|
| Mode | `hsa_withdrawal_mode` gains **`optimize`** alongside `spend_as_needed`, `annual_pct`, `smooth_window` | — |
| Deadline | `hsa_consume_by` — default `second_death_p90`, accepts any percentile or explicit year | Hard constraint (backstop; §2.2) |
| Objective | **Reuses** `roth_objective_mode`, its weights and `roth_tax_discount_rate`, plus the residual-cliff term. No separate HSA objective mode or discount rate | — |
| Guardrails | `hsa_irmaa_guardrail_mode`, `hsa_min_ending_balance`, existing `hsa_withdrawal_start_year` / `_end_year` | Bound the optimizer |
| **Per-year schedule** | New flat table `client_hsa_schedule.csv`: `year, optimizer_amount, override_amount, locked, note` | **override > locked > optimizer > mode default** |

The per-year table follows the existing flat-table pattern (`client_holdings.csv`,
`client_liabilities.csv`, `client_spending_budget_lines.csv`) — stored in `client_files`, mirrored to
disk, no YAML counterpart.

**Round-trip behavior, the part that usually goes wrong:** the optimizer always writes
`optimizer_amount` for every year and **never** writes `override_amount`. User edits land only in
`override_amount`. Re-running therefore refreshes the optimizer's own column and **cannot silently
discard user intent**. `locked` pins a year so the optimizer plans *around* it. Clearing an override
is one action and visibly returns that year to optimizer control.

**Interaction with the constraint:** overrides can make the deadline unreachable. When they do, the
resolver reports infeasibility per §3.3 rather than quietly redistributing into locked or overridden
years — the user's numbers are honored, and the consequence is surfaced.

### 3.5 The functional change to today's behavior

Today `withdraw_hsa_window()` hard-links HSA withdrawals to current-year medical spending —
`spend_as_needed` draws only up to `wellness_cost`. Under the stated assumption that is wrong: it caps
the HSA at current-year medical spend when the receipt bank permits any amount.

The change decouples them and treats the HSA as a general tax-free bucket bounded by the expense bank
(W1, default unlimited). Existing modes keep their behavior and `spend_as_needed` stays the default,
so no existing plan moves until the user opts in.

### 3.6 Limits that ship with the output

Per the S1/P7 precedent, the constraints on what the number supports are stated on the sheet:

- The schedule shares the **Roth conversion objective and discount rate**. Changing either retunes
  HSA and conversion recommendations together — they are not independent dials.

- The schedule is optimized on the **deterministic** path, like the Roth optimizer. It is not
  re-optimized per Monte Carlo path, so the success rate does not reflect adapting the drawdown to
  realized returns.
- HSA draws are modeled at the **bucket** level in the vectorized MC, so a per-year schedule moves
  the success rate only through balances, not through any volatility channel.
- The deadline rests on a longevity percentile (B5). It is a planning choice, not a prediction, and
  the residual exposure if the household outlives it should be shown next to it.

---

## 4. Implementation plan

H1 and H3 ship together per the sequencing decision; they remain separate phases so the acceptance
tests stay attributable even though the release does not.

### Phase H0 — Inputs and schema (no behavior change)

| # | Item | Effort | Model |
|---|---|---|---|
| H0.1 | `hsa_beneficiary_type` per account (primary + contingent); verify owner on `account_registry` (B3) | S | sonnet · medium |
| H0.2 | `hsa_consume_by` deadline setting, longevity-percentile aware; default `second_death_p90` | S | **opus · medium** — it is the risk dial |
| H0.3 | `hsa_substantiated_expense_bank` (unlimited default) + `hsa_nonqualified_treatment` (W1, W2) | S | sonnet · low |
| H0.4 | State HSA-conformity flag keyed to existing state-residency data (M1) | S | sonnet · medium |
| H0.5 | Schema rows + `tools/check_plan_data_sync.py --write` | S | haiku · low |

### Phase H1 — Terminal cliff · moves client numbers

| # | Item | Effort | Model |
|---|---|---|---|
| H1.1 | `hsa_terminal_tax()` in `after_tax.py` — **single-year lump**, not a 10-year slice. Assert in code why `effective_heir_ten_year_rate` is not reused | M | **opus · high** |
| H1.2 | Wire into after-tax terminal NW and the Roth objective so both optimizers see one estate | M | opus · high |
| H1.3 | Acceptance test pinning the cliff **independently of the optimizer** — this is what preserves attribution given the combined release. Demonstrate red first | S | **opus · high** — the test is the deliverable |

### Phase H2 — Decouple withdrawal from current-year medical spend

| # | Item | Effort | Model |
|---|---|---|---|
| H2.1 | Rework `withdraw_hsa_window` / `withdraw_hsa_gap` to draw against the expense bank rather than `wellness_cost`, preserving all existing mode behavior | M | opus · medium |
| H2.2 | Pre-65 penalty branch (W2/W3) — unreachable under the default, present and tested | S | sonnet · medium |

### Phase H3 — Constrained phasing optimizer

| # | Item | Effort | Model |
|---|---|---|---|
| H3.1 | `optimize` mode + objective/guardrail schema, mirroring the Roth idiom including derived-unless-overridden defaults | S | sonnet · medium |
| H3.2 | Scoring and schedule search under the terminal-zero constraint; reuse the Roth optimizer's discounting rather than a parallel implementation | L | **opus · high** |
| H3.3 | **Joint scoring with Roth conversions** — an HSA draw frees bracket headroom a conversion can use; scored separately, the headroom is double-counted. Includes the §3.2 surplus waterfall and its over-conversion guardrail | L | **opus · high** — the most likely correctness bug in the feature |
| H3.3b | Test the surplus waterfall ordering, and that surplus changes only how conversion tax is **funded**, never how much conversion is done (§3.2) | S | opus · high |
| H3.4 | Feasibility outcomes (§3.3) as explicit, tested states — including the "never silently relax the deadline" rule | M | opus · high |
| H3.5 | Two tests naming the wrong implementations they must reject: (a) the optimizer beats `smooth_window` **specifically by weighting survivor years** (§1.3), not merely by differing; (b) it does **not** back-load the balance into the final pre-deadline years — the failure mode that appears if the residual term is missing or mis-weighted (§3.1) | M | **opus · high** |

### Phase H4 — Override surface

| # | Item | Effort | Model |
|---|---|---|---|
| H4.1 | `client_hsa_schedule.csv` flat table, DB-canonical, following `client_liabilities.csv` | M | sonnet · medium |
| H4.2 | Precedence resolver (override > locked > optimizer > mode) as one tested pure function, not scattered conditionals | S | **opus · medium** — precedence bugs are silent |
| H4.3 | Round-trip test: overrides survive an optimizer re-run; locked years are planned around; clearing returns control; **overrides that break feasibility report it** | S | **opus · high** — this is the contract |
| H4.4 | UI: per-year table showing optimizer vs override side by side with the delta, plus feasibility status | M | sonnet · medium |

### Phase H5 — Reporting and disclosure

| # | Item | Effort | Model |
|---|---|---|---|
| H5.1 | HSA drawdown schedule, deadline, and residual exposure on the relevant sheet, with §3.6's limits stated | M | sonnet · medium |
| H5.2 | Disclosure guard test, red-first, mirroring `test_monte_carlo_sheet_discloses_the_asset_location_modeling_limit` | S | sonnet · medium |
| H5.3 | Single golden-master regeneration + changelog entry covering H1+H3 together, naming both effects | S | opus · medium |

### Sequencing

```
H0 ──> H1 ──┐
            ├──> H2 ──> H3 ──> H4 ──> H5   (H1+H3 released together)
            │              ^ H3.3 is the risk concentration
            └─ H1.3 pins the cliff independently,
               preserving attribution inside the combined release
```

---

## 5. Decisions and what remains

### 5.1 Resolved

| # | Decision | Rationale |
|---|---|---|
| B1 | Spouse primary, non-spouse contingent; **consume before second death** as a hard constraint | User's designation and instruction |
| — | Terminal cliff and optimizer **ship together** | Under the constraint a well-behaved plan never pays the cliff, so separating them buys less attribution than it would unconstrained. H1.3 preserves what attribution remains |
| B4 | **Reuse** the Roth objective, weights and discount rate, **plus a residual-cliff term** | One objective is the only formulation where H3.3's joint scoring is stable. The residual term is load-bearing, not a refinement — without it the optimizer back-loads everything (§3.1) |
| — | Surplus waterfall: **spending → Roth conversion tax → taxable**; deadline never bends | Converts surplus into tax-free rather than taxable growth, using headroom the HSA draw itself created (§3.2) |
| B5 | `hsa_consume_by = second_death_p90`, configurable | Failure modes are asymmetric (§2.2). With the residual term active this is a backstop, not the primary driver — which is why p85 vs p90 should barely move most schedules |

### 5.2 Still open

1. **B3 — which spouse owns each HSA.** Expected to be on `account_registry`; assumed, not confirmed.
   Verify in H0.1 before relying on the first-death rollover logic.
2. **M1 scope.** Full state-conformity modeling, or a CA/NJ special case with a warning elsewhere?
   Only matters if the household has, or may acquire, residency in a non-conforming state.

### 5.3 Risk concentration

Two items carry most of the correctness risk and are the reason H3 is billed opus · high throughout:

- **H3.3 — joint HSA/Roth scoring.** Scored separately, bracket headroom is double-counted and the
  surplus waterfall's priority 2 cannot work at all.
- **H3.5(b) — the back-loading rejection test.** If the residual term is missing or mis-weighted, the
  optimizer produces a schedule that satisfies every constraint and feasibility check while being the
  worst realistic answer. Nothing else in the plan would catch it.
