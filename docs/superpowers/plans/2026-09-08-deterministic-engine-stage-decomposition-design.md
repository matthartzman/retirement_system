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

- The internal decomposition of Stage 10 (Withdrawal Cascade) — flagged
  above as needing its own design pass once stages 1–9/11–14 are done and
  the pattern is proven.
- Any change to golden-master *pinned values* — this is a pure refactor;
  if any pinned value changes, that's a bug in the extraction, not a golden
  master update.
- Performance — `YearState` as a dataclass vs. dict has a marginal per-year
  allocation cost; not addressed here since correctness dominates for an XL
  refactor of tax-sensitive code.
