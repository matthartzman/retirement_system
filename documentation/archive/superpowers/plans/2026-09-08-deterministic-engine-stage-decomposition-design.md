# Ticket 3.10 — Deterministic engine decomposition: design

Status: design only, no extraction started. Written to scope the work before
any code changes, per the risk level (XL, high-risk) called out when this
ticket was triaged.

## Correcting the ticket's pointer

The ticket describes the target as "`project()` in `src/planning_engines.py`,
a ~4,000-line function body, with only TaxAssessment extracted (delegating to
`tax_kernel.py`)." That pointer is stale. As of `main`:

```python
# src/planning_engines.py:2431
def project(c):
    from .observability import observe
    from .projection_stages import run_deterministic_projection_stage
    with observe("projection.project", component="projection", config=c):
        return run_deterministic_projection_stage(c)
```

`project()` is already a 21-line orchestrator. The actual monolith is
**`run_deterministic_projection_stage()` in
`src/projection_stages/deterministic_engine.py:69–3283`** — the entire
3,283-line file is this one function. `planning_engines.py` (6,418 lines) is
mostly unrelated code (Monte Carlo engine, Roth candidate generation, event
dataclasses, tax tables) that happens to share the file with the historical
`project()` name.

**Action for whoever tracks the ticket list: repoint 3.10 at
`deterministic_engine.py:69`, not `planning_engines.py:2431`.**

## What "TaxAssessment" actually proved

The one existing extraction (`src/tax_kernel.py`) is not a stage extraction —
it's a **pure-function extraction of six closed-form tax primitives**
(`bracket_factor_for_year`, `irmaa_factor_for_year`, `irmaa_surcharge`,
`irmaa_tier`, `ltcg_tax_on_gain`, `rmd_divisor`). Each takes `c` and explicit
scalars and returns a value; none mutate `c`, `bal`, or any loop-carried
state. The call sites keep thin delegating closures at their original
location (`deterministic_engine.py:430-487`) for backward compatibility.

This precedent proves extraction is safe for **stateless calculations with no
side effects**. It proves nothing about extracting a stage that mutates
shared loop state — which is what all 13 remaining stages do. The design
below has to solve that problem; it can't just repeat the tax_kernel pattern
13 more times.

## Why this is genuinely XL/high-risk (not just "big")

`run_deterministic_projection_stage` has **one loop, no post-processing
step**: setup (lines 69–592, once), then `for year in range(plan_start,
plan_end+1):` (593–3282) with `rows.append(row)` as the loop's last
statement, then `return rows`. Every one of the 13 remaining stages runs
inside that single loop, and most of them read and write a set of shared
mutable locals seeded once in setup and threaded through the whole year:
`bal`, `bal_basis_free`, `home_val`, `home_equity`, `startup`, `note_bal`,
`cst_balance`/`cst_funded_total`, `first_death_done`, `filing`,
`hsa_bank_balance`, `daf_deduction_carryforward`, plus the per-year `row`
dict itself (built incrementally — later stages in the *same* iteration read
fields earlier stages in that iteration just wrote) and `event_log`.

Two stages are load-bearing warnings, not just complexity:

- **Stage 6 (Spending) computes RMD *sizing*; stage 7, ~270 lines later,
  applies it.** They're really one stage split by unrelated code in between.
- **Stage 10 (Withdrawal Cascade) is ~790 lines and is itself 8–10
  sub-stages** (HSA, elective pre-tax, taxable/trust, tax-loss harvesting,
  0%-bracket gain harvesting, cap-loss waterfall, DAF carryforward makeup,
  final HSA, Roth) glued together by **strict ordering invariants with an
  existing regression test guarding against reordering two of them**
  (`test_fixed_point_taxable_withdrawal_solver_runs_before_roth`), plus two
  internal fixed-point loops (LTCG/NIIT) and a documented "same shape as
  [HSA reimbursement], opposite sign" cross-reference to the DAF makeup pass.
  This one stage is a separate sub-project, not a same-day extraction.

## The golden master safety net does not cover this

Both golden-master suites call `project(c)` end-to-end but pin only
aggregate scalars:

- `test_frozen_sample_plan_golden_master_regression.py`: `warn_count`,
  validation `failures`, `rows[-1]['total_nw']`, `sum(total_tax)`.
- `test_synthetic_golden_master.py` (`synthetic_plans.project_metrics`):
  terminal net worth (total/liquid), lifetime tax, total Roth conversion,
  first-year tax, first RMD year/amount, first conversion year/amount,
  row count, plan start/end — per synthetic scenario.

**Neither pins any intermediate per-year field** — no `irmaa_tier`,
`ss_taxable`, `spend_by_tier`, individual account balances, effective
marginal rate, or event log contents. A stage refactor that changes an
internal field's name, timing, or value while preserving those ~10
terminal/aggregate numbers would pass both suites undetected. This matters
most exactly where extraction risk is highest (stages 6/7/9/10).

**Prerequisite, before any stage extraction starts:** add a full-row
snapshot regression test — dump `rows` (every per-year field) for 2-3
scenarios already covered by the synthetic golden master, pin them, and gate
every extraction PR on it staying byte-identical. This is cheap to add now
and is the only thing that makes "pure move, verified against golden master"
(the pattern that worked for ticket 3.13) actually true here.

## Stage inventory

Per-year unless noted. Coupling risk drives extraction order below.

| # | Stage | Lines | Per-year? | Coupling risk | Why |
|---|---|---|---|---|---|
| 0 | Setup/init | 69–592 | once | — | Not a stage; seeds all shared state |
| 1 | Deaths/filing status | 607–630 | yes | High | `filing`/`first_death_done` persist *across* years |
| 2 | Spousal rollover/CST funding | 632–680 | yes | High | Direct `bal` mutation + multi-year `cst_balance` |
| 3 | Appreciation/Divorce/QLAC | 681–750 | yes | Medium | Several bundled one-time events, fairly self-contained |
| 4 | Home value & sale | 751–882 | yes | High | Taxable gain computed here, **tax on it deferred ~1300 lines to stage 9** |
| 5 | Income (earned/401k/HSA/SS/annuities) | 883–1208 | yes | High | Largest block (325 lines); feeds ~15 locals into stage 9 |
| 6 | Spending (+ RMD sizing) | 1209–1674 | yes | High | RMD *sizing* lives here; ACA/wellness output is **revised again by stage 9** — a real read-then-patch cycle |
| 7 | RMDs (application) | 1675–1685 | yes | Medium alone | Only makes sense paired with stage 6, 270 lines away |
| 8 | Roth Conversions | 1686–1800 | yes | High | Duplicates stage 9's state-tax estimate in a local closure |
| 9 | AGI/Tax | 1801–2131 | yes | High | Closest analogue to TaxAssessment, but reads/patches earlier stages' `row` fields instead of being a pure function; its own `total_tax` is provisional until stage 12 |
| 9b | Spending tiers (reporting) | 1880–1937 | yes | **Low** | Documented as purely additive, never feeds back |
| 10 | Withdrawal Cascade | 2141–2931 | yes | **Very high** | 8–10 sub-stages, ordering-invariant regression test exists, two internal fixed points |
| 11 | Advanced modules post-pass (AMT etc.) | 2932–2963 | yes | Medium | |
| 12 | Effective marginal rate (diagnostic) | 2964–3055 | yes | **Low** | Read-only, exception-guarded, self-contained |
| 13 | Canonical cash-flow breakdown | 3056–3158 | yes | Low–Medium | Read-only by design but reads nearly everything |
| 14 | Portfolio growth (EOY) + net worth | 3159–3282 | yes | Medium | Last stage, depends on nearly every mutable local |

## Proposed stage interface

The tax_kernel pattern (stateless function, thin delegating shim) does not
fit stages that mutate shared loop state. Introducing 13 independent
closures-over-`c` modules would just relocate the coupling, not reduce it.

Proposed shape: a single explicit **mutable year-context object** (a
dataclass, e.g. `YearState`, already hinted at by the existing
`MutableYearState`/`create_initial_year_state` helpers referenced in
Setup — check whether that can be extended rather than introducing a second
context type) that carries every currently-implicit shared local (`bal`,
`filing`, `cst_balance`, `home_val`, ..., the in-progress `row` dict) as
named fields. Each stage becomes a function of the shape:

```python
def apply_<stage>(c: dict, year: int, state: YearState) -> None:
    ...  # reads state.*, c; mutates state in place (bal, row fields, etc.)
```

This keeps the same "shared mutable state" semantics the current code relies
on (no attempt to force purity where the domain is genuinely stateful — see
stage 6/9's read-then-patch relationship, which is a real modeling
dependency, not an accident) while making every stage's inputs/outputs
explicit and independently testable via `state` snapshots before/after.
`run_deterministic_projection_stage` becomes an ordered list of
`apply_<stage>(c, year, state)` calls inside the existing loop — the
loop itself does not move.

This is a design choice for review, not a decision to implement unilaterally
— flagging it explicitly since it introduces a new shared type that every
future stage extraction depends on getting right the first time.

## Extraction order (risk-ascending)

1. **Add the full-row snapshot regression test** (prerequisite, no code
   extraction, near-zero risk).
2. **Stage 12 (Effective marginal rate)** — read-only, exception-guarded,
   already isolated. Best first real extraction: proves the `YearState`
   pattern end-to-end at minimum risk.
3. **Stage 9b (Spending tiers)** — documented purely-additive, second
   extraction to confirm the pattern generalizes.
4. **Stage 13 (Cash-flow breakdown)** — read-only but reads everything;
   validates that `YearState` actually exposes what a late, wide-reading
   stage needs.
5. **Stage 3 (Appreciation/Divorce/QLAC)** and **Stage 11 (AMT post-pass)**
   — medium risk, fairly self-contained one-time/adjustment logic.
6. **Stages 1–2 (Deaths/filing, Spousal rollover/CST)** — high risk from
   cross-year state (`filing`, `cst_balance`), but conceptually simple once
   `YearState` carries that state explicitly instead of as bare closure
   locals.
7. **Stage 4 (Home sale)** paired conceptually with the home-sale-gain-tax
   portion of **Stage 9** — these two need to move together or the deferred
   `row['_home_sale_taxable_gain_pending']` handoff has no home.
8. **Stage 5 (Income)** and **Stage 6/7 (Spending + RMD sizing/application,
   merged into one real stage)** — largest remaining blocks; extract after
   the pattern is proven on 6 lower-risk stages.
9. **Stage 8 (Roth Conversions)** and **Stage 9 (AGI/Tax)** — extract
   together or in immediate sequence; stage 8 currently duplicates stage 9's
   state-tax estimate, which should collapse into one shared call once both
   are functions rather than closures.
10. **Stage 10 (Withdrawal Cascade)** — separate sub-project. Needs its own
    design pass to decompose the 8–10 internal sub-stages (this document
    does not attempt that level of detail) with the ordering-invariant test
    as a hard gate on every internal split, done last after the rest of the
    pattern is battle-tested.
11. **Stage 14 (Portfolio growth/net worth)** — last, since it depends on
    nearly every other stage's output.

Each numbered step above is its own PR, gated on: the new full-row snapshot
test staying identical, both existing golden masters staying green, and (for
any stage touching withdrawal/tax ordering) the existing ordering-invariant
regression test staying green.

## Explicitly out of scope for this document

- Any change to golden-master *pinned values* — this is a pure refactor;
  if any pinned value changes, that's a bug in the extraction, not a golden
  master update.
- Performance — `YearState` as a dataclass vs. dict has a marginal per-year
  allocation cost; not addressed here since correctness dominates for an XL
  refactor of tax-sensitive code.

---

## Addendum (2026-09-09): Stage 10 (Withdrawal Cascade) design pass

Status at the time of this addendum: **13 of 14 stages extracted** (all of
1–9, 11–14). This is the design pass for the last one, deferred until now
per the original document's own instruction ("needs its own design pass
once stages 1–9/11–14 are done and the pattern is proven").

### The block

`run_deterministic_projection_stage()` in `deterministic_engine.py`,
lines ~959–1748 (~790 lines, matching the original estimate almost
exactly). Everything after Stage 9 (AGI/Tax) and before the already-extracted
Stage 11 (AMT/equity-comp true-up).

### Sub-stage inventory (11 sub-stages, not 8–10 — the original estimate
undercounted by treating "LTCG/NIIT + TLH + gain-harvest + cap-loss" as one
unit; it's really 6 tightly-coupled pieces)

| # | Sub-stage | Lines | Loop? | Risk |
|---|---|---|---|---|
| 0 | Gap assembly + HELOC + liability amortization | 959–1050 | no | Low — seeds `gap`, the cascade's central threading variable |
| 1 | Priority 1b: HSA funds contingent liability | 1061–1094 | no | Low |
| 2 | Priority 2: HSA scheduled window draw | 1096–1103 | no | Low |
| 3 | HSA-reimbursement medical-deduction correction | 1105–1199 | no | **Very high** — the exact ordering this block's position guards is what the regression test exists for (see below) |
| 4 | Priority 3: pre-tax elective withdrawal (bracket-capped) | 1201–1316 | yes (IRA true-up) | High — near-duplicate of #7 |
| 5 | Priority 4: taxable/trust withdrawal | 1318–1332 | no | Low |
| 6 | LTCG/NIIT fixed point + TLH + gain-harvest + cap-loss waterfall | 1334–1528 | yes (investment-tax loop) | **Very high** — largest (195 lines), most tangled, two inline closures over 5+ shared mutables |
| 7 | Priority 4b: final pre-tax draw before Roth (cap override) | 1530–1628 | yes (IRA true-up, shares #4's pattern) | High — near-duplicate of #4 |
| 8 | DAF carryforward make-up pass | 1630–1699 | no | Medium — documented as the mirror-image of #3 ("same shape, opposite sign") |
| 9 | Priority 4c: final non-Roth HSA draw before Roth | 1700–1716 | no | Low |
| 10 | Priority 5: Roth withdrawal (last resort) | 1718–1732 | no | Low — but the *invariant* "nothing before this has left liquid pretax/HSA" is exactly what the regression test checks |
| 11 | Unfunded-gap / surplus sweep | 1733–1748 | no | Low |

### The regression this cascade already broke once

`tests/test_recommendations_functional.py::test_fixed_point_taxable_withdrawal_solver_runs_before_roth`
asserts three things every year: the LTCG/NIIT fixed point actually ran when
expected, it funded taxes via taxable draws, and — the load-bearing one —
**zero years where `roth_wd > 1` while `pretax_nw + hsa_nw > 1`**. History
(documented inline at lines 1113–1137): an earlier version placed sub-stage
3 (HSA-reimbursement netting) *after* Priority 4c instead of between
Priorities 2 and 3. That let the extra tax demand it creates land with
"only Roth left to fund it" — 10 years failed the invariant. A second,
independent regression (lines 1176–1186) came from writing `total_tax`
directly inside sub-stage 3 instead of updating `total_tax_pre_niit`; the
value was silently discarded by the later recombination
(`total_tax = total_tax_pre_niit + ltcg_tax + niit - tlh_ordinary_credit`),
producing a $178.21 residual caught by
`test_cashflow_breakdown_single_source_of_truth.py`.

**Both bugs were positional/ordering mistakes a type system or interface
contract would not have caught — they were caught by behavior-level
regression tests.** This is the strongest argument in the whole 3.10 effort
for treating any decomposition of this block as gated on those two tests
specifically, not just the two standing safety nets.

### Fixed-point loops (3, not 1 — the original document only described one)

All three share one config key, `c['tax_withdrawal_fixed_point_iterations']`
(default 3), and the same shape: bounded loop, early `break` on a negligible
delta, then an *unconditional* one-shot settle-up after the loop (even if it
hit its iteration cap) so the final increment's tax is never left untrued-up.

1. **Priority 3 IRA true-up** (1251–1292) — ordinary-tax delta vs.
   incremental pretax draw.
2. **LTCG/NIIT investment-tax loop** (1452–1483) — taxable/trust draw vs.
   LTCG+NIIT delta; the one already described in the original document.
3. **Priority 4b IRA true-up** (1555–1594) — structurally identical to #1,
   reusing its same helper function and the *same* iteration counter
   (`ira_tax_true_up_iterations` is cumulative across both).

### Internal state (candidates for an internal `YearState`-like object)

Unlike every stage extracted so far, this block's own internal sub-stages
share far more mutable state with EACH OTHER than any two already-extracted
stages ever shared: `gap`, `agi`/`taxable_inc`, `fed_tax`/`state_tax`,
`total_tax_pre_niit`/`total_tax` (rebuilt by recombination, not written
directly — itself an ordering hazard per the regression above),
`ltcg_gain`/`ltcg_tax`/`niit`, `available_losses`/`cap_loss_carryforward`
(the latter also crosses *year* boundaries), `item_ded`/`medical_ded`/`char`/`ded`,
`ira_wd`/`h_ira_elective`/`w_ira_elective`/`pretax_by_account` (accumulated
across #4 and #7), plus five per-account ledger dicts on `row` written
incrementally by nearly every sub-stage.

**This is the evidence the original document said would decide the
`YearState` question.** It decides it: a block this internally
interconnected is a legitimate case for a small, explicit, purpose-scoped
mutable context object — NOT the full engine-wide `YearState` (still not
needed for the boundary *between* stages, where a NamedTuple return has
worked every time), but a `CascadeState`-shaped object scoped to just this
block's own internal pipeline, passed by reference between its internal
sub-stage functions the same way `bal`/`row` already are. Building that
object's field list is >80% done by the "internal state" list above.

### Recommended approach: this is not one more extraction, it's a sub-project

Given the sub-stage count (11), the two independent fixed-point loops that
must stay correctly sequenced relative to sub-stage 3's exact position, and
a documented history of two distinct silent-regression bugs from exactly
this kind of reordering, **do not attempt this as a single extraction PR**,
even by the isolated-worktree-parallel pattern used for stages 1–9/11–14.
Recommended path, in order:

1. **Extract the 8 low-risk, no-loop, non-adjacent-to-#3 sub-stages
   first**, each as its own small PR, gated on both safety nets AND the
   `test_fixed_point_taxable_withdrawal_solver_runs_before_roth` /
   `test_cashflow_breakdown_single_source_of_truth` regression tests
   specifically: #0, #1, #2, #5, #9, #10, #11, and #8 (DAF make-up — medium
   risk but well-isolated and well-documented). This shrinks the inline
   block from ~790 to ~350 lines with the pattern already proven safe for
   9 of the 11 pieces, and produces the `CascadeState`-shaped context
   object's first working draft against low-stakes callers.
2. **#4 and #7 together** (the two near-duplicate IRA true-up
   priorities) — factor their shared true-up-loop-plus-settle-up pattern
   into one internal helper both call, since they already are
   near-identical code; this is a case where the extraction is also a
   legitimate, low-risk de-duplication, not just a relocation.
3. **#3 last among the "simple" pieces, on its own, with the ordering
   regression test as the explicit acceptance gate** — do not bundle it
   with anything else. Its function boundary must encode "runs after #2,
   before #4, nets only #1+#2's `hsa_wd`" as an explicit precondition in
   its own docstring and, ideally, an assertion or comment loud enough
   that a future edit cannot silently relocate it the same way the
   original regression happened.
4. **#6 (LTCG/NIIT + TLH + gain-harvest + cap-loss) is its own
   follow-up design pass**, not attempted here. At 195 lines with two
   inline closures over 5+ shared mutables, this needs the same kind of
   sub-stage inventory this addendum just did for the whole cascade,
   scoped to just this one block, before any extraction is attempted.
   Do not fold it into step 1–3's momentum.

Each step in 1–3 is its own PR/commit, verified the same way every prior
stage extraction in this ticket has been: both safety nets before and
after, plus (new, specific to this block) both regression tests named
above, plus a direct read of the diff confirming no dropped reassignment —
the same review process already used for the 13 stages done so far.

---

## Addendum (2026-09-09): Stage 10 sub-stage #6 (LTCG/NIIT/TLH/gain-harvest) design pass — step 4

Status at the time of this addendum: sub-stages #0–#2, #5, #8–#11 have been
extracted (`withdrawal_cascade_gap_assembly.py`,
`withdrawal_cascade_hsa_priority_draws.py`,
`withdrawal_cascade_taxable_trust.py`, `withdrawal_cascade_daf_makeup.py`,
`withdrawal_cascade_final_draws.py`). Sub-stages #3, #4, #6, #7 remain
inline. Step 2 (IRA true-up sub-stages #4/#7) is being extracted
concurrently, in a different worktree, by a separate agent — **this pass
does not touch #4 or #7's code**, only reads it as context for what #6 must
hand off to it. This is the "further, separate design pass for sub-stage #6"
step 1's original addendum called for in its point 4 (no code changes; that
document explicitly deferred this). Design only — no extraction attempted.

### 1. Exact structure

Current line numbers (shifted down from the ~1334–1528 range the prior
addendum cited, because step 1's extraction removed lines above this block):
**`deterministic_engine.py:1224–1418`, 195 lines**, sandwiched between the
already-extracted `apply_taxable_trust_withdrawal` call (sub-stage #5,
1214–1222) and the still-inline Priority 4b block (sub-stage #7, starting
1420). In order:

1. **Seed (1230–1232, no loop).** `ltcg_tax`/`ltcg_gain` are seeded from
   `home_sale_ltcg_tax`/`home_sale_ltcg_gain` (Stage 9's home-sale gain,
   computed ~700 lines earlier and carried forward unpaid until now — this
   is the "taxable gain computed in stage 4, tax deferred to stage 9"
   pattern the top-level design doc already flagged, except here the *tax*
   itself is further deferred from Stage 9 into this block). `niit` was
   already seeded by Stage 9 too (line 936, `niit = _stage9.niit`) and is
   read/updated here, not re-seeded.
2. **Tax-loss harvesting, "apply" mode only (1234–1265, no loop over years —
   loops over harvest-lot candidates).** Gated on `c['tlh_policy'] ==
   'apply'`. For each candidate lot from `_tlh.select_harvest_lots(...)`:
   realizes the loss, charges a transaction cost against `bal[account]`,
   and **mutates the lot object in place** (`_lot.cost_basis =
   market_value`, `_lot.purchase_date = f'{year}-01-01'`) — this is a
   side effect on an object living inside `c`'s lot engine, not on any
   local/`row`/`bal` scalar, and is easy to miss when inventorying "what
   this block writes." Produces `harvested_loss`, `tlh_txn_cost`, and
   `available_losses = cap_loss_carryforward + harvested_loss` (this-year
   pool = last year's rollover + this year's harvest).
3. **0%-bracket gain harvesting, "apply" mode only (1267–1302), same
   shape as #2 but selling winners instead of losers**, gated on
   `c['gain_harvest_policy'] == 'apply'`. Computes headroom from
   `taxable_inc` (already reflecting the year's Roth conversion decision —
   the block's docstring explicitly guarantees no double-booking of the
   0% bracket against the Roth guardrail), then does the identical
   basis-reset mutation on selected lots. Produces `gain_harvest_realized`,
   `gain_harvest_txn_cost`. TLH and gain-harvest are independent passes —
   neither reads the other's output — but both feed the same downstream
   `ltcg_gain`/`available_losses` accounting, and both use the *same*
   basis-reset technique on `c`'s lot objects, so a bug in one is easy to
   mistake for a bug in the other during review.
4. **Two inline closures (1304–1340)** — `_realize_taxable_gain(
   draws_by_account)` (closes over `bal_basis_free`, `year`, `c`; consumes
   basis-free dollars first, then computes taxable gain via the lot engine
   or the flat `trust_gain_fraction`) and `_refresh_investment_taxes()`
   (closes over `ltcg_tax`, `niit`, `total_tax` via `nonlocal`, plus reads
   `available_losses`, `taxable_inc`, `agi`, `filing`, `c`,
   `base_nii_without_ltcg`; recomputes LTCG tax net of losses and NIIT,
   returns the *incremental* tax delta since last call). These are not
   sub-sub-stages so much as shared helpers the rest of the block calls
   repeatedly — extracting #6 means these two closures must become
   ordinary functions (see §3, §5).
5. **Pre-loop settle-up (1342–1348, no loop, at most 2 calls).** If
   home-sale gain or a loss carryforward exists, refresh once
   unconditionally; if sub-stage #5 already drew from taxable/trust,
   realize that gain and refresh again. This happens *before* the fixed
   point below even starts — the fixed point only funds what's left after
   these two.
6. **The fixed-point loop itself (1350–1373)** — see §3.
7. **Capital-loss waterfall settle-up (1375–1398, no loop, unconditional,
   always runs whether the loop above hit 0 iterations or its cap).**
   Uses gain-offset first (`min(available_losses, ltcg_gain)`), then up to
   $3,000 of ordinary-income offset (valued at the current-year marginal
   rate via `_compute_fed_tax_path` bracket delta), then rolls the
   remainder into next year's `cap_loss_carryforward`. Produces
   `row['cap_loss_used']`, `row['cap_loss_carryforward']`,
   `row['tlh_ordinary_credit']`, `row['tlh_gain_offset_value']`,
   `row['tlh_tax_value']` — the last three are pure reporting (the annual
   dollar value of harvesting), consumed only by the Tax-Loss Harvesting
   sheet, never fed back into cascade math.
8. **Recombination (1410) and dependent row writes (1400–1418).**
   `total_tax = total_tax_pre_niit + ltcg_tax + niit -
   tlh_ordinary_credit` — the correct pattern (see §4). `net_income` and
   `total_cash_need` are then rebuilt from that `total_tax`, with an
   explicit comment (1413–1417) explaining *why* `total_cash_need` must be
   recomputed here rather than reusing the value `gap` was originally
   seeded from.

**Separable vs. intertwined:** #2 (TLH) and #3 (gain harvest) are the most
separable — each is a self-contained "loop over candidate lots, mutate
lot + bal, accumulate a scalar" pattern with no dependency on the fixed
point or on each other; either could become its own small pure-ish helper
(`bal`/`c`-mutating, but no closure over the fixed-point's variables) taking
`(c, bal, row, year)` and returning a small result. #4/#5/#6/#7/#8 are not
separable from each other — the closures in #4 are called from both #5 and
#6, `available_losses` computed in #2 feeds #7's waterfall math, and #8's
recombination depends on whatever `ltcg_tax`/`niit` value the loop in #6
last converged to. That five-piece core is the "195 lines, two closures,
5+ shared mutables" the prior addendum already called out — this pass
confirms it does not decompose further without threading a shared state
object through it (§5).

### 2. State inventory

**Reads, set earlier this year:**
`home_sale_ltcg_tax`/`home_sale_ltcg_gain` (Stage 9), `niit` (seeded by
Stage 9, then mutated here), `agi`, `taxable_inc`, `filing`, `year`,
`total_tax_pre_niit` (set by Priority 3, the still-inline sub-stage #4),
`trust_wd`/`trust_by_account` (sub-stage #5's `TaxableTrustWithdrawalResult`
— already exactly the right shape per that module's docstring, which
explicitly anticipated #6 adding to these fields on each fixed-point
iteration), `gap` (threaded from #5), `bal`, `bal_basis_free`,
`note_int_yr`/`portfolio_ordinary`/`portfolio_qualified` (Stage 5, income),
`row['_niit_ws_taxable']`/`row['_niit_hs_taxable']` (Stage 9), `spend`,
`c['model_niit']`, `c['tax_withdrawal_fixed_point_iterations']`,
`c['tlh_policy']`/`c['tlh_*']` config, `c['gain_harvest_policy']`/
`c['gain_harvest_*']` config, `c['lot_engine']`, `c['trust_gain_fraction']`.

**Cross-year state (seeded once before the outer per-year loop, at
`deterministic_engine.py:245`, from `year_state.cap_loss_carryforward` on
the `MutableYearState` dataclass — `src/projection_stages/year_state.py:29`):**
`cap_loss_carryforward` is a **plain float scalar**, not a dict entry. It
is read once per year (line 1265) and reassigned once per year (line 1382).
Critically, **it is never written back into `year_state`** — like every
other seeded-once scalar in this file (`home_val`, `startup`, `note_bal`,
`filing`, `first_death_done`, `cst_funded_total`, `cst_balance` — confirmed
by grep: `year_state.` appears only on the seed lines, never as an
assignment target), it persists across years purely because it is a local
variable in `run_deterministic_projection_stage`'s enclosing scope, which
survives from one iteration of the `for year in range(...)` loop to the
next. **This is the landmine for this extraction specifically:** the moment
sub-stage #6 becomes its own function called once per year, that implicit
persistence mechanism disappears. `cap_loss_carryforward` must be passed in
as a parameter and returned out explicitly (NamedTuple field), and the
*caller* (still the per-year loop in `deterministic_engine.py`, until/unless
someone later folds it into `year_state`) must reassign its own local from
the return value every year — exactly the pattern
`withdrawal_cascade_final_draws.py` already documents for
`hsa_bank_balance` ("the caller must reassign its own local from it on
every call"). Do not thread it through `year_state` instead unless every
other seeded-once scalar in the file is migrated the same way at the same
time — mixing the two persistence mechanisms for different variables in
the same function would be its own source of confusion.

**Reassigned here, read later this year (by later cascade sub-stages
#7/#8/#9, already extracted or concurrently being extracted):**
- `ltcg_tax`, `niit`, `total_tax` — read by sub-stage #7 (Priority 4b,
  concurrently being extracted) at its recombination line (current
  `deterministic_engine.py:1515`, `total_tax = total_tax_pre_niit +
  ltcg_tax + niit - tlh_ordinary_credit`) and by sub-stage #8's
  `apply_daf_carryforward_makeup(..., total_tax=total_tax, ...)` call.
  **This means sub-stage #6's extracted interface must return `ltcg_tax`,
  `niit`, and `tlh_ordinary_credit` individually, not just the
  recombined `total_tax`** — #7 needs to re-run the same recombination
  formula itself after its own tax true-up changes
  `total_tax_pre_niit`, so it needs the three addends, not just their
  sum. Coordinate this explicitly with whoever is extracting #4/#7
  concurrently: their function signature will need `ltcg_tax`, `niit`,
  `tlh_ordinary_credit` (and, transitively, `total_tax_pre_niit`, which
  #6 does *not* write) as inputs.
- `gap` — threaded onward to #7, standard pattern, already handled the
  same way by every other extracted sub-stage.
- `trust_wd`/`ht_wd`/`wt_wd`/`trust_by_account` — sub-stage #6 *adds to*
  these (fixed-point loop can draw more taxable/trust), so on extraction
  they become both inputs and outputs of #6's function, same as #5
  already documents ("can add to `trust_wd`/`ht_wd`/`wt_wd`/
  `trust_by_account` on each fixed-point iteration" — #5's docstring
  already names #6 as the reader/mutator; this confirms it from #6's
  side).
- `bal_basis_free`, `bal` — **dicts, mutated through reference**, no
  propagation hazard. `_realize_taxable_gain` mutates `bal_basis_free[aid]`
  in place; the TLH/gain-harvest loops mutate `bal[acct]` in place. These
  are safe under extraction with no special handling, unlike every scalar
  above.
- `row['cap_loss_used']`, `row['cap_loss_carryforward']`,
  `row['tlh_ordinary_credit']`, `row['tlh_gain_offset_value']`,
  `row['tlh_tax_value']`, `row['tlh_harvested_loss']`,
  `row['tlh_transaction_cost']`, `row['gain_harvest_realized']`,
  `row['gain_harvest_transaction_cost']`, `row['trust_wd']`,
  `row['h_trust_wd']`, `row['w_trust_wd']`, `row['ltcg_gain']`,
  `row['ltcg_tax']`, `row['niit']`, `row['investment_tax_iterations']`,
  `row['investment_tax_funded_by_taxable']`, `row['total_tax']`,
  `row['net_income']`, `row['total_cash_need']` — `row` is a dict,
  mutated through reference like everywhere else in the cascade; no
  propagation hazard as long as `row` continues to be passed by reference
  into the extracted function (the pattern every other sub-stage module
  already uses).
- **Not reassigned here despite being closely related:** `taxable_inc`
  and `agi` are only *read* by this block (headroom computation, NIIT
  MAGI, LTCG bracket lookup) — sub-stage #6 never writes them. Confirmed
  by grep: no `taxable_inc =` or `agi =` assignment anywhere in
  1224–1418. That responsibility stays with sub-stage #7 (Priority 4b)
  and #4 (Priority 3), which do mutate both.
- **Dead/vestigial:** `_refresh_investment_taxes` declares `nonlocal
  ltcg_tax, niit, total_tax` but its body only ever assigns `ltcg_tax`
  and `niit` — `total_tax` is named in the `nonlocal` statement but never
  written inside the closure (it's rebuilt afterward, once, by the
  explicit recombination at line 1410). Not a bug today (an unused
  `nonlocal` target is harmless), but worth a one-line cleanup at
  extraction time so a future reader doesn't assume the closure sets
  `total_tax` directly — that exact belief is what caused this file's
  documented $178.21 regression once already (see §4).

### 3. Fixed-point loop risk

This is the third of the three fixed points named in step 3's addendum.
Precise mechanics, current line numbers:

- **Not nested.** One `for _tax_iter in range(max_tax_iters)` loop
  (1351–1373), `max_tax_iters = c.get('tax_withdrawal_fixed_point_iterations',
  3)` (same config key as the other two fixed points, shared iteration
  budget philosophy but each loop has its own counter — this one is
  `investment_tax_iterations`, not shared with `ira_tax_true_up_iterations`
  the way sub-stages #4/#7 share theirs).
- **Two break conditions per iteration**, checked in order: (1) `if gap <=
  1e-6: break` at the top — nothing left to fund, stop; (2) `if add_wd <=
  1e-6: break` right after the withdrawal call — the taxable/trust bucket
  is exhausted (or capped), stop even if `gap` is still positive (the
  remaining gap becomes sub-stage #7/#4b's problem, funded from pre-tax).
- **What converges:** the taxable/trust withdrawal needed to fund the
  *incremental* LTCG+NIIT liability created by the *previous* withdrawal.
  Each iteration: withdraw `gap` from taxable/trust
  (`_legacy_pe.withdraw_taxable_trust`), realize the gain on that specific
  draw (`_realize_taxable_gain(add_by_account)` — only the *new* draw's
  accounts, not the whole cumulative `trust_by_account`), refresh
  LTCG/NIIT (`_refresh_investment_taxes()`, which returns only the
  *delta* since the last refresh — this is why the two pre-loop calls in
  §1 step 5 matter: they establish the "last refresh" baseline before the
  loop's own deltas start accumulating), and add that delta back onto
  `gap` for the next iteration to (attempt to) fund.
- **The "settle-up":** unlike the other two fixed points (which have an
  explicit, separately-commented "unconditional one-shot settle-up" block
  right after their loop), this one's settle-up is implicit and split
  across two things that already run unconditionally regardless of loop
  outcome: the capital-loss waterfall (§1 step 7, which finalizes
  `cap_loss_carryforward`/`tlh_ordinary_credit` using whatever
  `ltcg_gain`/`available_losses` the loop left behind) and the
  recombination (§1 step 8, `total_tax = total_tax_pre_niit + ltcg_tax +
  niit - tlh_ordinary_credit`). There is no separate "one more
  `_refresh_investment_taxes()` call after the loop" the way #4/#7 have
  one more `_ira_elective_ordinary_tax_delta()` call after theirs —
  because each loop iteration here already ends by calling
  `_refresh_investment_taxes()` itself (line 1372, *inside* the loop
  body, after the withdrawal), the last iteration (whether it stopped by
  break or by exhausting `max_tax_iters`) always leaves `ltcg_tax`/`niit`
  current as of the last withdrawal it made. The waterfall/recombination
  after the loop is not "one more correction pass" so much as "the
  reporting/rollup step that was always going to run once, independent of
  how many funding iterations happened."
- **TLH/gain-harvest sit entirely *outside* the fixed-point loop** — both
  run once, before the loop starts (§1 steps 2–3), and only affect the
  loop indirectly through `available_losses` (computed once, static for
  the whole loop — TLH does not re-harvest mid-loop) and through
  `ltcg_gain`'s starting value. **This is the key fact for extraction
  feasibility:** TLH and gain-harvesting can be pulled into helpers
  independent of the loop (they run once, produce scalars, done). The
  capital-loss waterfall, by contrast, sits *after* the loop but reads
  `ltcg_gain`/`available_losses` as the loop left them — it cannot be
  extracted independent of the loop's final state, only sequenced after
  it (which is what the current code already does; an extraction just
  needs to preserve that the waterfall runs after the loop's last
  iteration, not e.g. per-iteration).

### 4. Two historical regression bugs — landmine check for sub-stage #6

Re-reading both documented bugs (inline comments at
`deterministic_engine.py:1105–1137`, `~1176–1186`, both actually inside
sub-stage #3, not #6 — the bugs happened in the *neighboring* block, not
this one) against #6's actual code:

- **Roth-ordering bug (misplaced HSA-netting):** not reproducible inside
  #6 itself — #6 has no HSA interaction at all (HSA sub-stages are #1/#2/
  #3/#9, all elsewhere). The relevant risk for #6 is different: its
  *position* relative to #5 (must run after, consuming #5's `trust_wd`)
  and #7 (must run before, supplying `ltcg_tax`/`niit`/
  `tlh_ordinary_credit`) is load-bearing the same way #3's position is,
  just without an existing named regression test pinning it specifically
  (see §6 — this is a gap).
- **`total_tax` direct-write bug:** checked explicitly — **sub-stage #6
  does not write `total_tax` directly anywhere except via the
  recombination formula at line 1410**
  (`total_tax = total_tax_pre_niit + ltcg_tax + niit -
  tlh_ordinary_credit`), which *is* the correct recombination pattern (the
  same shape as the fix that resolved the original bug). Confirmed by
  grep: `total_tax` appears in this block only as the recombination
  target and as a read (`row['net_income'] = row.get('gross_income', agi)
  - total_tax`). **No direct-write landmine exists in #6 today.** The one
  adjacent risk (§2, "Dead/vestigial") is the unused `nonlocal total_tax`
  in `_refresh_investment_taxes` — not a bug, but exactly the kind of
  loose thread that made the original bug easy to introduce elsewhere
  (a future edit "helpfully" assigning `total_tax` inside that closure,
  believing the `nonlocal` declaration means it's expected to, would
  reintroduce the same class of bug). Recommend removing `total_tax` from
  that `nonlocal` statement at extraction time as a zero-risk drive-by
  fix, with a one-line comment explaining why (recombination happens
  once, explicitly, after the loop — not incrementally inside it).
- `taxable_inc`/`agi` are never written by #6 (§2) — so the second
  historical bug's *pattern* (writing a total instead of going through
  recombination) has no analog to check there; #6 simply doesn't touch
  those fields.

### 5. Recommended extraction design

**Interface:** a `WithdrawalCascadeInvestmentTaxResult` NamedTuple (naming
consistent with the other four extracted modules), fields: `gap`,
`ltcg_gain`, `ltcg_tax`, `niit`, `tlh_ordinary_credit`,
`cap_loss_carryforward` (the reassigned-cross-year scalar — returned every
call, caller reassigns its own local per §2), `trust_wd`, `ht_wd`, `wt_wd`,
`trust_by_account` (all four also inputs — this function both reads and
extends what #5 produced), `total_tax`, `investment_tax_iterations`,
`investment_tax_funded_by_taxable`. Inputs: `c`, `bal`, `bal_basis_free`,
`row`, `year`, `gap`, `agi`, `taxable_inc`, `filing`, `total_tax_pre_niit`,
`home_sale_ltcg_tax`, `home_sale_ltcg_gain`, `niit` (starting value from
Stage 9), `cap_loss_carryforward` (prior year's), `trust_wd`/`ht_wd`/
`wt_wd`/`trust_by_account` (from #5), the NII component scalars
(`note_int_yr`, `portfolio_ordinary`, `portfolio_qualified`,
`row['_niit_ws_taxable']`, `row['_niit_hs_taxable']`), `spend`, `emit`.

**A block-scoped state object is warranted here — more so than anywhere
else extracted so far, but scoped narrowly.** The prior addendum's
conclusion (a `CascadeState`-shaped object for the cascade's *internal*
pipeline, not the engine-wide `YearState`) applies most acutely to this
one sub-stage, because it's the only piece with two closures that need to
share live mutable state *within a single sub-stage's own extraction* (not
just across sub-stage boundaries, which the NamedTuple pattern already
handles fine for #0–#5/#8–#11). Recommend a small, private,
module-scoped dataclass — e.g. `_InvestmentTaxState` — with fields
`ltcg_tax`, `ltcg_gain`, `niit`, `available_losses`, `agi`, `taxable_inc`,
`filing`, `base_nii_without_ltcg`, constructed once at the top of the
extracted function and passed to `_realize_taxable_gain` and
`_refresh_investment_taxes` (now ordinary module-level or nested functions
taking `state` explicitly instead of closing over outer locals via
`nonlocal`). This keeps the closures' *shape* (mutate shared state,
functions with side effects) while making every read/write explicit at a
function boundary — exactly the tradeoff the top-level design doc already
argued for for the engine-wide case, applied here at the sub-stage scope
where it's actually needed. Do **not** widen this into a general-purpose
cascade-wide state object as part of this extraction — that's a separate,
larger decision the top-level document already deferred, and doing it here
as a side effect of this extraction would make this already-highest-risk
piece harder to review, not easier.

**Safe extraction order:** given TLH and gain-harvesting run outside the
loop and don't interact with each other, they are the two lowest-risk
sub-pieces *within* #6 and should be extracted first, as two small helper
functions (not necessarily separate PRs — small enough to land in the
same PR as long as they're separately reviewable diff hunks):
1. `_apply_tax_loss_harvesting(c, bal, row, year) -> (harvested_loss,
   tlh_txn_cost)` — pure loop over lots, no fixed-point interaction.
2. `_apply_gain_harvesting(c, bal, row, year, taxable_inc) -> (realized,
   txn_cost)` — same shape, one extra input (`taxable_inc`, read-only).
3. The fixed-point loop + its two closures + the pre-loop settle-up,
   as the `_InvestmentTaxState`-based core described above — this is the
   piece that cannot be split further without breaking the closures'
   shared-state contract.
4. The capital-loss waterfall + final recombination — could technically
   be its own helper (`_apply_cap_loss_waterfall_and_recombine`), since it
   only reads the loop's final `ltcg_gain`/`available_losses`/`ltcg_tax`/
   `niit`, but given it's already unconditional and runs exactly once
   right after the loop, folding it into the same function as step 3
   (rather than a fifth handoff) is lower-risk — fewer NamedTuple
   round-trips through which a field could be silently dropped.
   Net: **2 small pure helpers + 1 larger function covering the
   loop/waterfall/recombination core**, not 6 separate hand-offs.
   This still shrinks the inline block from 195 to a handful of call-site
   lines, without over-fragmenting the genuinely-coupled core.

Given this is explicitly the highest-risk remaining piece (flagged twice
now, once in the original document and once in step 3's addendum), and
given the two historical bugs both originated in the *neighboring*
sub-stage #3 from a positional mistake rather than a logic mistake, the
single highest-value safety measure for this specific extraction is not
more code review but the dedicated regression test in §6 below — land that
test *before* attempting the extraction, the same sequencing step 3's
addendum already used for sub-stage #3's positional guard.

### 6. Recommended regression-test coverage

**What exists today, checked directly:**
- `tests/test_tlh_unit.py`, `tests/test_gain_harvest_unit.py` — pure unit
  tests of the *helper* functions (`select_harvest_lots`,
  `compute_zero_bracket_headroom`, `select_gain_harvest_lots`,
  LTCG marginal-rate math) in `src/tax_loss_harvesting.py`/
  `src/gain_harvest.py`. These do **not** exercise
  `run_deterministic_projection_stage` at all — no coverage of the
  fixed-point loop, the waterfall, or the recombination.
- `tests/test_gain_harvest_zero_bracket.py`,
  `tests/test_tax_loss_harvesting_functional.py` — call `project(c)`
  end-to-end with `tlh_policy`/`gain_harvest_policy` set to `'apply'`,
  asserting on realized-gain/loss amounts, transaction costs, and
  qualitative behavior (e.g. harvesting reduces tax vs. a baseline run).
  These **do** exercise sub-stage #6 through the real engine, but assert
  loosely (deltas/qualitative comparisons), not exact pinned per-year
  values — a refactor that changed the block's *shape* while preserving
  these assertions' magnitudes could still pass.
- `tests/test_roth_ltcg_niit_guardrails.py` — tests the *Roth conversion*
  guardrail's use of LTCG/NIIT caps (a different code path, the Roth
  conversion sizing logic in sub-stage #8, not sub-stage #6's own
  LTCG/NIIT tax calculation). Not direct coverage of this block.
- `tests/test_ltcg_cross_implementation_equivalence_unit.py` — compares
  two LTCG tax implementations for equivalence; a pure-function test, not
  engine-integration.
- **The full-row snapshot test**
  (`tests/test_deterministic_engine_full_row_snapshot_regression.py`,
  fixture `tests/fixtures/deterministic_engine_full_row_snapshot_cases.json`)
  dumps every field of every row for its pinned scenarios, which — since
  it's a full dump, not a curated subset — already includes
  `ltcg_gain`/`ltcg_tax`/`niit`/`cap_loss_carryforward`/`cap_loss_used`/
  `tlh_ordinary_credit`/`tlh_gain_offset_value`/`tlh_tax_value`/
  `tlh_harvested_loss`/`tlh_transaction_cost`/`gain_harvest_realized`/
  `gain_harvest_transaction_cost`/`investment_tax_iterations`/
  `investment_tax_funded_by_taxable`/`trust_wd`/`total_tax` for whichever
  scenarios it covers. Checked which scenarios actually exercise this
  block: `tests/synthetic_plans.py`'s `tax_loss_harvesting` scenario sets
  `tlh_policy = 'apply'` and is covered by the synthetic golden master —
  but **checked directly against `SNAPSHOT_SCENARIOS`
  (`tests/test_deterministic_engine_full_row_snapshot_regression.py:90`):
  the full-row snapshot fixture currently pins only
  `baseline_balanced_couple`, `early_survivor_compression`, and
  `single_filer` — `tax_loss_harvesting` is NOT one of them.** So today,
  no snapshot test pins this block's exact per-year values at all; only
  the synthetic golden master's *terminal* metrics (lifetime tax, terminal
  net worth) cover the `tax_loss_harvesting` scenario, and those are far
  too coarse to catch an internal-mechanics regression in sub-stage #6.
  Separately, **no synthetic scenario sets
  `gain_harvest_policy = 'apply'`, and no scenario appears to seed an
  actual pre-existing `cap_loss_carryforward` balance from a prior year**
  (the carryforward path — losses arriving already-rolled-over from a
  previous year, as opposed to harvested fresh this year — is exercised
  by `test_tax_loss_harvesting_functional.py`'s standalone `project(c)`
  calls, not by the pinned snapshot/golden-master fixtures).
- `test_cashflow_breakdown_single_source_of_truth.py::
  test_breakdown_present_and_reconciles_to_surplus` is the general-purpose
  test that would catch a repeat of the $178.21 residual bug (it asserts
  the itemized tax breakdown sums to `row['total_tax']` for every row of
  every scenario the cashflow breakdown test suite covers) — already a
  hard gate per step 3's addendum, still applies here.
- No test named for `test_fixed_point_taxable_withdrawal_solver_runs_before_roth`
  specifically asserts anything about sub-stage #6's *internal* fixed
  point (it asserts the Roth-ordering invariant across the whole cascade,
  and that "the LTCG/NIIT fixed point actually ran when expected" — but
  not what value it converged to, nor how many iterations it took, nor
  the waterfall's split between gain-offset/ordinary-offset/carryforward).

**Gap and recommendation:** the existing nets check the *result* (final
`total_tax` reconciles, Roth never drawn early) but nothing pins sub-stage
#6's *intermediate* mechanics — the fixed-point's iteration count, the
waterfall's three-way split, or gain-harvesting's headroom computation
against a Roth-conversion-affected `taxable_inc` in the same year. Given
the two-independent-closures structure and the fact this is explicitly the
highest-risk remaining piece, **add one new scenario to the synthetic
plan library before extraction is attempted**: a plan that combines (a) a
non-zero starting `cap_loss_carryforward` (seed it directly via the
scenario override, not by relying on a prior year's harvest to produce
one — makes the carryforward-consumption path deterministic and testable
in isolation), (b) `tlh_policy = 'apply'` against underwater lots big
enough that harvested losses exceed the current year's gains (forces the
$3,000 ordinary-offset path and a non-zero rolled-forward remainder), and
(c) `gain_harvest_policy = 'apply'` in a year with headroom (exercises the
0%-bracket path). Register it with both the synthetic golden master *and*
the full-row snapshot fixture (`tools/regen_full_row_snapshot.py`) so its
per-year `cap_loss_used`/`cap_loss_carryforward`/`tlh_ordinary_credit`/
`gain_harvest_realized`/`investment_tax_iterations` values are pinned, not
just its terminal net worth. This, plus the two existing named regression
tests (§ "The regression this cascade already broke once" in the step-3
addendum) and both golden masters, is the recommended gate for the actual
extraction PR(s) — land the new scenario/pinned values *first*, confirm it
passes against the current inline code, then extract, then confirm
byte-identical snapshot values after.
