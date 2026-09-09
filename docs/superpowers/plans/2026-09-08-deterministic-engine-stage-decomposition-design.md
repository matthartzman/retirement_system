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
