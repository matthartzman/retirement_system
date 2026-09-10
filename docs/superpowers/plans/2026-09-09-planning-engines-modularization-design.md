# planning_engines.py modularization — design

**Status:** design only. Nothing in this document has been implemented. §2.4 is
the one section backed by measurement rather than analysis — it settles the
feasibility question the first draft flagged as the risk to Tier 1, and §6, §7
and §9's question 4 were rewritten from its numbers.
**Date:** 2026-09-09
**Subject:** `src/planning_engines.py`, 6,418 lines
**Predecessors:** `docs/superpowers/plans/2026-09-08-deterministic-engine-stage-decomposition-design.md`
(ticket 3.10, Stages 1–10, complete as of commit `b1613c7`),
`documentation/SYSTEM_REVIEW_AND_REFACTOR_PLAN.md` Phase 2c (the analysis that
consolidated eight engine files into this one).

---

## 1. Where the file actually stands

Ticket 3.10 decomposed the **deterministic projection** out of this file into
`src/projection_stages/` — 17 modules, 6,591 lines, `project()` now a 21-line
orchestrator that delegates to `run_deterministic_projection_stage()`. That work
is done, and this document does not revisit it.

What it did *not* touch is the other 90% of the file. Measured today (`ast` over
top-level statements):

| Band | Defs | Lines | Share |
|---|---:|---:|---:|
| **Monte Carlo** (scalar + vectorized + shared sampling + dispatcher + spending-cut solve) | 41 | **3,120** | **49%** |
| **Roth strategy optimizer** (candidate sweep, LCV/ELTR scoring, ranking) | 7 | 761 | 12% |
| Withdrawal / HSA / liquidity / charitable mechanics | 20 | 781 | 12% |
| Conversion engine (plan/apply + IRMAA/LTCG/NIIT thresholds + guardrails + ACA) | 17 | 633 | 10% |
| Inheritance / death transition / mortality sampling | 19 | 424 | 7% |
| Growth & account returns | 6 | 199 | 3% |
| `project()` + `run_scenario()` (the public entry points) | 2 | 53 | 1% |
| Imports, module constants, comments, the `core` re-export block | — | 447 | 7% |

112 top-level defs: 41 public, 71 private.

**Monte Carlo is half this file, and it is two complete parallel
implementations of the same simulation** — `monte_carlo_exact_scalar` (576
lines, one function) and `_mc_vectorized_projection` + `_mc_vectorized_batch`
(757 lines), selected between by a 285-line `monte_carlo()` dispatcher on
`mc_engine_mode`. Neither has any caller outside this file except
`src/report_compute.py:20`.

That is the analogue of the dashboard.js finding: the thing that makes this file
hard to work in is not 112 tangled functions, it is one subsystem that was never
its own module.

### 1.1 The section markers lie

The file preserves `# ===== BEGIN/END <file>.py =====` markers from the Phase 2c
consolidation. **Three of the eight boundaries no longer describe the code
inside them**, and any plan that trusts them will cut in the wrong place:

* `monte_carlo_engine.py` (L2491–4489) opens with 773 lines that are not Monte
  Carlo at all — the entire Roth strategy optimizer (`_roth_strategy_metrics`,
  `optimize_roth_conversion_strategy`, `compute_baseline_lcv_and_eltr`,
  `compute_future_lcv_and_eftr`). It calls `monte_carlo()` to *score* candidates,
  which is presumably how it drifted here, but it is a strategy search, not a
  simulator.
* `growth_engine.py` (L30–338) contains `_mc_bucket_return_tilts` and
  `_mc_apply_bucket_growth` (L99–171, 71 lines) — vectorized-MC bucket helpers
  sitting 4,000 lines from the rest of the vectorized engine.
* `projection_engine.py` (L2413–2488) is now 53 lines of orchestrator plus the
  `from .core import *` re-export block (§2.2), the deterministic engine having
  moved to `projection_stages/`.

Bands in this document are derived from the AST and the call graph, not from the
markers. The markers should be deleted as each band moves, not preserved.

---

## 2. What blocks this today

### 2.1 The file's own header says not to

`src/planning_engines.py:8-14`:

> Do not re-split this file without first tracing cross-section calls (e.g. the
> Monte Carlo section calls `sample_household_death_years`, defined in the
> mortality_engine section, and `project()`, defined in the projection_engine
> section) — splitting naively reintroduces a circular import between whichever
> files end up on each side of the cut.

This warning is correct, still live, and is the central constraint of this
design. But it argues against a *naive* split, and the specific cycle it names
has a clean answer:

```
monte_carlo()  →  project()  →  projection_stages.deterministic_engine
                                            ↓
                                    imports planning_engines
```

The cycle exists because MC and `project()` are in the same file. **Move Monte
Carlo out and the cycle it describes disappears** rather than reappearing:
`src/monte_carlo/` would import `planning_engines` (for `project`,
`sample_household_death_years`, `apply_death_transition`, …) and nothing in
`planning_engines` would import `monte_carlo` — its only reference,
`monte_carlo()`, moves too.

The direction that must be preserved is the one already established by
`projection_stages`: **stage/consumer modules import `planning_engines`;
`planning_engines` imports them only inside a function body.** `project()`
already does exactly this (`from .projection_stages import
run_deterministic_projection_stage`, deferred inside the function). Every module
in this design follows that rule, and it should be asserted by a test rather
than left to convention (§6).

### 2.2 `from .core import *` — the laundering façade

`src/planning_engines.py:2423`:

```python
from .core import *  # noqa: F401,F403  # consolidated from engine_core
```

A wildcard re-export, 2,400 lines into the file, inside a section that no longer
contains what its marker claims. Consequences, all currently live:

**(a) Most of this module's apparent public API is not its own.** Of the 41
names other modules import from `planning_engines`, **23 are `core`'s**, reached
only through this wildcard:

```
EvConversion EvDeath EvGrowth EvHomeSale EvIncome EvRMD EvTax EvTransfer
EvWarning EvWithdraw FEDERAL_BRACKETS_BASE_YEAR FEDERAL_BRACKETS_MFJ
IRMAA_TIERS_BASE_YEAR STATE_TAX_RULES TAX_BASE_YEAR annuity_cash_income
irmaa_lookback_magi marginal_rate niit_tax salt_cap senior_bonus_deduction
social_security_taxable_amount state_income_tax
```

Six `projection_stages` modules import namedtuples and tax functions *from
`planning_engines`* that are defined in `core.py`. Only 17 of the 41 names are
genuinely owned by this module. (`ensure_engine_config` is a 24th pass-through,
laundered from `plan_config`.)

**(b) It silently clobbers a same-named definition, and the file patches it back
by hand.** `planning_engines` defines `_rmd_divisor_with_table_override` at
L865; `core` exports a narrower `rmd_divisor`; the wildcard overwrites the local
binding, so L2429 restores it:

```python
rmd_divisor = _rmd_divisor_with_table_override  # noqa: F811
```

This works. It is also a trap that only fires when someone adds a name to
`core.py` that collides with one here — and it will fail as a wrong *answer*,
not an import error.

**(c) It defeats static analysis of exactly the question this refactor needs
answered.** `deterministic_engine.py:39-45` already records this: it switched to
an explicit name list specifically because the wildcard produced "ambiguous/
unresolved names," and it calls that switch a *"prerequisite for any future split
of planning_engines.py."* That prerequisite has been met for one consumer. It has
not been met for the module itself.

**Replacing the wildcard with an explicit re-export list is Pass 0 of this
design** — before any code moves. It is the change that makes every subsequent
move analyzable, and it is independently valuable if the rest is never done.

### 2.3 The golden master does not cover Monte Carlo

`tests/test_synthetic_golden_master.py` is the gating engine baseline, and
`tests/synthetic_plans.py:465` shows what it pins: `project_metrics()` calls
`project()` and pins 13 deterministic scalars (terminal net worth, lifetime tax,
first RMD year, …). **No Monte Carlo output is pinned anywhere in it.**

The 3.10 design already flagged that the golden master under-covers the
deterministic engine. For MC the gap is total, and the obvious substitute is
weaker than it looks:

`tests/test_scalar_vectorized_survivor_reconciliation.py` runs both engines on a
fixed-seed fixture — but its own docstring is explicit that it is *not* an
equivalence oracle:

> a real double-digit-percentage-point gap can and does remain even with
> survivor economics fully wired in (empirically ~0.11 vs. ~0.135 at this
> fixture/seed). This test is deliberately about THIS phase's specific
> contribution … not full scalar/vectorized agreement, which is Phase 3's job.

So the two implementations **cannot** check each other to refactor tolerance, and
33 test files touch `monte_carlo` without pinning its numbers. **A fixed-seed MC
golden master is a hard prerequisite for Tier 1, not a nice-to-have** (§6).

### 2.4 Measured: the safety net is affordable (2026-09-09)

The first draft of this document flagged MC runtime as the open risk that could
sink Tier 1 — the scalar engine reruns the full deterministic projection per
path, so a pinned run looked like it might be too slow to gate a merge. That was
an estimate, and the estimate was wrong. Measured on the
`baseline_balanced_couple` synthetic scenario (33 projection years):

| Run | Time |
|---|---:|
| `project()` | **0.025s** |
| `Scenario.build()` (includes the Roth optimizer) | 11.78s |
| vectorized, `n_sims`=100 / 250 / 1000, `mc_sensitivity_sims=1` | 2.18 / 2.04 / **2.18s** |
| vectorized, `n_sims`=100 / 250 / 1000, `mc_sensitivity_sims=200` | 2.35 / 2.43 / **2.44s** |
| scalar, `n_sims`=10 / 25 / 50 / 100, `mc_sensitivity_sims=1` | 0.70 / 1.15 / 1.50 / **2.52s** |
| scalar, `n_sims`=50, `mc_sensitivity_sims=200` (the default) | **85.14s** |

Three findings, all of which change §6 and §7:

1. **`project()` is 25 ms.** "Reruns the projection per path" is true, but cheap:
   100 scalar paths cost ~2.5s, not minutes.
2. **The vectorized engine is flat in `n_sims`.** 100 paths and 1,000 paths both
   cost ~2.2s, so path count is not a cost lever — pin at a realistic count.
3. **The cost driver is the sensitivity grid, not the paths.** The 85s outlier is
   25 cells × 200 paths = 5,000 extra scalar projections. At
   `mc_sensitivity_sims=1` the same run is 2.5s, a 34× drop. This is an
   established pattern rather than a test-only hack:
   `optimize_roth_conversion_strategy` already sets `c2['mc_sensitivity_sims'] = 1`
   internally (`planning_engines.py:3115`) for exactly this reason.

**Determinism confirmed.** `monte_carlo_exact_scalar` seeds `random.Random(seed)`
(L3903, L3914) and `_mc_vectorized_batch` seeds `_np.random.default_rng(seed)`
(L5613). Both are locally constructed generators with no global state, so a
fixed-seed run is reproducible. CI is a single matrix entry (windows-latest,
Python 3.14), so there is no cross-platform float-stability exposure to manage.

To re-measure: build a scenario with `tests.synthetic_plans.SCENARIOS[name].build()`
inside `tests.golden_pricing.frozen_holdings_prices()`, pass its `project()` rows
as `base_rows=` so the timing excludes a second deterministic run, and redirect
stdout (both engines print a progress line per sensitivity-grid cell). Numbers
above are single runs on the developer machine, not a benchmark harness — treat
them as order-of-magnitude, which is all the decision needs.

**Cost context.** `test_synthetic_golden_master.py` already takes **125.4s** for
its 10 scenarios, nearly all of it `build()`'s Roth optimizer. MC pins are a
marginal addition to a test that already dominates its own file, not a new
tentpole.

---

## 3. Tier 1 — extract Monte Carlo (`src/monte_carlo/`)

3,120 lines, 49% of the file, one subsystem, one external caller. This is the
whole reason to do the project.

Proposed package, mirroring the `projection_stages/` convention already
established in this repo:

| Module | Lines | Contents |
|---|---:|---|
| `__init__.py` | ~10 | Re-export `monte_carlo`, `monte_carlo_exact_scalar` |
| `dispatch.py` | ~290 | `monte_carlo()` — engine-mode selection, config normalization, portfolio/asset-class inputs, result assembly |
| `sampling.py` | ~590 | `_sample_return`, `_generate_return_path`, `_regime_overlay`, `_sample_inflation_and_health_paths`, `_portfolio_asset_class_inputs`, `_percentiles`, `_success_rate_ci`, `_clone_for_mc`, `_funding_success*`, `_first_failure_year` |
| `scalar.py` | ~800 | `monte_carlo_exact_scalar`, `_run_one_mc_path`, `_mc_scalar_tier_bucket_reconstruction`, `_mc_scalar_guyton_klinger_shadow`, `_adjust_annuity_pmt_for_mc`, `_sensitivity_success_rate` |
| `bucket_flows.py` | ~350 | `_mc_bucket_starting_balances`, `_mc_row_bucket_flows`, `_mc_survivor_bucket_flows`, `_mc_effective_row_flows`, **plus `_mc_bucket_return_tilts` and `_mc_apply_bucket_growth`** (currently stranded at L99–171 in the growth section) |
| `vectorized.py` | ~1,085 | `_mc_vectorized_projection`, `_mc_vectorized_batch`, the `_mc_vectorized_*` path builders, `_mc_tier_bucket_cascade`, `_mc_tier_priority_retained`, `_max_consecutive_true_per_row` |
| `spending_cuts.py` | ~235 | `essential_discretionary_floor_check`, `spending_priority_cut_check`, `sustainable_spending_solve` |

**Import direction:** every module above imports from `planning_engines`,
`core`, and `plan_config`. Nothing in `planning_engines` imports
`monte_carlo` — `report_compute.py:20` is updated to import
`monte_carlo` from its new home. This is what removes, rather than relocates,
the cycle §2.1 warns about.

**Sub-ordering within Tier 1** — smallest blast radius first, so a mechanism
failure is diagnosable in isolation:

1. `sampling.py` + `bucket_flows.py` (pure helpers, no dispatcher change; also
   the pass that reunites the two stranded growth-section helpers with their
   subsystem)
2. `spending_cuts.py` (three public functions, self-contained)
3. `scalar.py` (the validation oracle — moved before the hot path so a mistake
   here cannot silently degrade production runs)
4. `vectorized.py`
5. `dispatch.py` + `__init__.py` + caller update

After Tier 1: 6,418 → **~3,200 lines**.

### 3.1 What Tier 1 deliberately does not do

It does not merge, reconcile, or delete either MC implementation. The two
engines disagree by design today (§2.3); closing that gap is the optimization
refactor's Phase 3 and is a *behavioural* project. Mixing it into a file move
would make every pinned-value change ambiguous between "the move broke it" and
"Phase 3 changed it." Extraction first, and the extraction must move bytes, not
edit them.

---

## 4. Tier 2 — the Roth strategy optimizer (`src/roth_strategy.py`)

761 lines, 7 defs, currently misfiled inside the `monte_carlo_engine.py` marker
(§1.1): `_roth_strategy_candidate_specs`, `_roth_strategy_comparison_specs`,
`_roth_legacy_mode_multiplier`, `_roth_strategy_metrics` (300 lines),
`compute_baseline_lcv_and_eltr`, `compute_future_lcv_and_eftr`,
`optimize_roth_conversion_strategy` (226 lines).

This is a strategy *search*: enumerate ~30 conversion policy candidates, score
each with `run_scenario()` + `monte_carlo()`, rank, apply the LCV feasibility
gate (`LCV_FEASIBILITY_GATE_THRESHOLD`, currently declared 3,000 lines away at
L50, inside the growth section, and also imported by
`src/reporting/sheets_strategy.py:265` — so it must stay importable, wherever it
lands), pick a winner. It sits at a strictly higher level
than everything else in the file — it *consumes* the engines rather than being
one.

`src/strategy_sweep.py` already extracted the shared enumerate→evaluate→rank→gate
shape out of this function and out of the SS claim-age sweep. Tier 2 finishes
that thought by giving the Roth-specific half its own module, next to
`src/withdrawal_strategy_comparison.py` (349 lines) and
`src/qlac_optimizer.py` / `src/daf_optimizer.py`, which are the same kind of
thing and already live at top level.

Depends on Tier 1 only in ordering convenience, not correctness: it imports
`monte_carlo` either way, and doing it after Tier 1 means importing from the new
package rather than editing the import twice.

After Tier 2: ~3,200 → **~2,440 lines**.

---

## 5. Tier 3 — the remaining engines, and the shape of the residue

What is left after Tiers 1–2 is ~2,440 lines of genuine account mechanics — and,
unlike the dashboard.js function tail, it is *already* four coherent domains with
clean internal boundaries:

| Candidate module | Lines | Public API |
|---|---:|---|
| `src/engine_withdrawal.py` | 781 | `hsa_available_to_draw`, `withdraw_hsa_window`, `withdraw_hsa_gap`, `hsa_unscheduled_draw_allowed`, `fund_contingent_liability_from_hsa`, `withdraw_pretax_elective`, `withdraw_taxable_trust`, `withdraw_roth`, `donate_taxable_in_kind`, `liquidity_buffer_for_year`, `liquidity_reserve_floor` |
| `src/engine_conversion.py` | 633 | `ConversionPlan`, `plan_roth_conversion`, `apply_roth_conversion`, `conversion_window_end_year`, `spending_guardrail_year`, `age_phased_spending_factor`, `aca_applicable_percentage`, `aca_premium_tax_credit`, + the `_roth_*_threshold_base` helpers |
| `src/engine_inheritance.py` | 424 | `InheritanceTransfer`, `InheritanceResult`, `beneficiary_titling_audit`, `apply_death_transition`, `sample_death_year`, `sample_household_death_years`, `_mortality_qx*` |
| `src/engine_growth.py` | 199 | `apply_end_of_year_growth`, `GrowthResult`, `investable_account_ids`, `_account_return*` |
| `src/engine_rmd.py` | 165 | `compute_rmds`, `apply_rmds`, `rmd_divisor`, `owner_account_ids` |

**Do not do Tier 3 until Tiers 1–2 have shipped and settled.** Three reasons,
and they are the difference between this being a good idea and a bad one:

1. **These are the modules `projection_stages/*` imports from.** Six stage
   modules plus `hsa_schedule.py`, `after_tax.py` and `optimization.py` reach
   into these names. Every one of those imports changes, and every change is a
   chance to reintroduce the cycle. Tier 1 has *one* external caller; Tier 3 has
   dozens.
2. **This is the code the golden master actually covers.** That is an argument
   for doing it (real safety net) and an argument for doing it *last* (the
   deterministic engine is the part where a wrong answer is a wrong financial
   plan, not a wrong probability).
3. **The residue after Tier 1–2 is a legible 2,400-line file**, not a monolith.
   If appetite runs out there, that is a defensible resting point — the same
   judgement the frontend project made at its four-cluster line.

If Tier 3 does happen, the endpoint is `planning_engines.py` as a **~200-line
explicit façade**: `project()`, `run_scenario()`, and a curated re-export block
that keeps every existing `from .planning_engines import X` working. Pass 0
(§2.2) is what makes that façade writable at all.

---

## 6. Verification

The 3.10 design's own conclusion applies here verbatim and harder: *the golden
master safety net does not cover this.* Three additions are prerequisites, not
follow-ups.

**P1 — a fixed-seed Monte Carlo golden master. Blocking for Tier 1.**
Extend `tests/test_synthetic_golden_master.py`'s fixture with an `mc_metrics()`
alongside `project_metrics()`, pinning `success_rate`, `first_failure_year`
percentiles, terminal-wealth percentiles,
`essential_fully_funded_probability`, and the spending-cut distribution. Without
P1, Tier 1 is a 3,120-line move of numerically sensitive code with **nothing**
asserting the numbers survive it.

§2.4 settles the feasibility question the first draft left open: this gates every
merge, it does not become a nightly job. The measured configuration:

| | `n_sims` | `mc_sensitivity_sims` | Per scenario | × 10 scenarios |
|---|---:|---:|---:|---:|
| vectorized | 1000 | 200 (the real default) | 2.44s | ~24s |
| scalar | 100 | 1 | 2.52s | ~25s |
| | | | | **~49s added** |

Against `test_synthetic_golden_master.py`'s existing 125.4s, that is +39% on one
test — not a new tentpole.

Four decisions, and the reasoning that picks them:

* **Pin both engines, not just the vectorized one.** The vectorized path is what
  production runs (`data_io.py` defaults unset plans to it), so pinning only that
  is superficially tempting — but §3's extraction order moves `scalar.py` (~800
  lines) at pass **1c**, *before* `vectorized.py` at **1d**. Pinning only the
  vectorized engine leaves the first code move entirely ungated, which inverts
  the point of the prerequisite.
* **Vectorized at the real default `mc_sensitivity_sims=200`.** The full grid
  costs +0.26s over `sens=1` (§2.4), so there is no reason to cheapen it and
  every reason to exercise the production code path.
* **Scalar at `mc_sensitivity_sims=1`.** 2.5s versus 85s, and it follows
  `optimize_roth_conversion_strategy`'s own precedent (`planning_engines.py:3115`)
  rather than inventing a test-only mode. **Known gap, to be stated in the
  fixture rather than glossed:** this leaves the *scalar* sensitivity-grid path
  (L4326–4334) unpinned. Cover it with a single scenario at
  `n_sims=10, mc_sensitivity_sims=10` instead of pretending the main pins reach
  it.
* **Round every pinned float.** `success_rate` is a count ratio and is already
  stable; the percentiles are not.

**The one real cost, and it is not runtime.** A pin at these path counts is
exquisitely sensitive to RNG *consumption order* — reorder two draws and the
success rate moves plausibly rather than obviously. That sensitivity is exactly
what should guard a 3,120-line move, and exactly what will churn pins on every
later behavioural change. So P1 is scoped to the risk window: **after Tier 1
lands, drop the scalar pins to 3 scenarios (~7s)** and keep the vectorized set.
Carrying maximum sensitivity permanently, once the code has stopped moving, buys
churn rather than safety.

Determinism is confirmed, not assumed — see §2.4's generator-seeding note.

**P2 — an import-direction test.** Assert that no module under
`src/monte_carlo/` (and later `src/engine_*.py`) is imported at *module scope* by
`planning_engines.py`, and that `planning_engines` appears in no import cycle
that isn't function-deferred. An AST walk over `src/`, in the style of
`deterministic_engine.py:39-45`'s explicit-name-list discipline. This is the
mechanical form of the header warning in §2.1 — today that warning is a comment,
and comments do not fail CI.

**P3 — a no-wildcard-import test.** After Pass 0, assert no `import *` anywhere
in `src/`. This is what stops §2.2(b)'s clobber-and-patch pattern from being
re-created.

Per-pass gate, in addition:

1. `pytest tests/test_synthetic_golden_master.py tests/test_golden_master_pin_provenance.py` — pinned values must not move. **If any pinned value changes, that is a bug in the extraction, not a golden-master update** (3.10's rule, carried forward).
2. `pytest tests/ -k "monte_carlo or mc_ or roth_strategy or scalar_vectorized"` — 33 MC-touching test files.
3. Full `pytest tests/` — 123 test files import `planning_engines`.
4. `tools/release_gate.py`.
5. A byte-level move check. The frontend project's `extract_module.mjs --check`
   earns its keep by reconstructing the original file from the *generated output*
   and diffing. There is no Python equivalent in this repo today. Building one is
   probably not worth it for ~10 moves; the cheap substitute is to require that
   each extraction commit's diff show **only** deletions from `planning_engines.py`
   and additions to the new module, with the moved text identical — verifiable by
   `git diff --stat` plus a manual `diff` of the extracted range against the new
   file. State that as a review rule for these commits.

---

## 7. Sequencing and budget

Turn estimates assume Opus 5 at high reasoning effort working agentically; one
turn is one prompt → one working stretch → one response, including running the
suite and fixing what breaks. They are anchored on ticket 3.10's own history,
where PR #104 carried seven low-coupling stages while Stage 10 needed a PR and
three design addenda to itself.

| Pass | Content | Turns | `planning_engines.py` after |
|---|---|---:|---:|
| **0** | Replace `from .core import *` with an explicit re-export list; add P3. Delete the three stale section markers this touches. No code moves. | 2–3 | ~6,420 |
| **P1** | Fixed-seed MC golden master (§6, configuration measured in §2.4). No code moves. | 3–4 | 6,420 |
| **P2** | Import-direction test against the current (already-cyclic-by-deferral) layout, so it is proven to pass before it has to guard a change. | 1–2 | 6,420 |
| | *prerequisite subtotal — zero lines moved* | **6–9** | |
| 1a | `sampling.py` + `bucket_flows.py`; also reunites the two helpers stranded at L99–171 | 2–3 | |
| 1b | `spending_cuts.py` — three self-contained public functions | 1–2 | |
| 1c | `scalar.py` — one 576-line function | 2–4 | |
| 1d | `vectorized.py` — 1,085 lines including a 552-line function | 3–5 | |
| 1e | `dispatch.py` + `__init__.py` + `report_compute.py:20` | 2–3 | |
| | **Tier 1 subtotal** | **10–17** | ~3,200 |
| 2 | `src/roth_strategy.py` | 2–4 | ~2,440 |
| 3 *(optional, later)* | Five `engine_*.py` modules + façade | 8–15 | ~200 |

All-in for prerequisites + Tier 1 + Tier 2: **~19–30 turns**. P1's estimate
dropped from the first draft's 4–7 because §2.4 answered the feasibility question
by measurement — what remains is pin generation against an existing fixture,
which is mechanical.

Passes 0–2 and P1–P3 are worth doing **even if Tier 3 never happens**. Pass 0 and
P1 are worth doing even if Tier 1 never happens: one removes a live correctness
trap, the other closes a real hole in the gating baseline. On value-per-turn,
those two are the highest-return work in this document — they are not refactoring
at all.

No line ratchet is proposed. The frontend has one
(`tests/test_frontend_size_ratchet.py`) because dashboard.js was actively
re-absorbing growth; there is no evidence of that here, and a ratchet on a file
whose remaining content is genuine per-year tax math would push new code into
worse homes rather than better ones. Revisit if this file grows after Tier 1.

---

## 8. Out of scope

* **Reconciling the two Monte Carlo engines.** That is the optimization
  refactor's Phase 3 ("state-contingent tax approximation"), it is behavioural,
  and §3.1 explains why it must not share a commit with the move.
* **Any change to pinned golden-master values.** Pure refactor.
* **Performance.** The vectorized engine's numpy hot loops are moved verbatim;
  `_np` is already hoisted to module scope (system review 4.1) and the new
  modules each import it the same way.
* **`src/data_io.py` (2,918) and `src/optimization.py` (2,157).** The next two
  largest files. Same class of problem, different analysis; not folded in here.
* **The `projection_stages/` package itself.** 3.10 owns it, Stage 10's own
  addendum already scopes what remains there.

---

## 9. Open questions for review

1. **Is `src/monte_carlo/` a package or one module?** 3,120 lines is too big for
   one file, and the six-module split above follows `projection_stages/`'s
   precedent. But `scalar.py` and `vectorized.py` are 800 and 1,085 lines
   respectively — still large. Splitting them further is possible but would cut
   inside `_mc_vectorized_projection` (552 lines, one function), which is a
   different and much riskier kind of change. This design says: package, six
   modules, no function-level surgery.
2. **Should Pass 0's explicit re-export list be a deprecation, or permanent?**
   The 23 laundered `core` names *should* be imported from `core` by their real
   consumers. Fixing that is ~30 import-line edits across `projection_stages/`
   and is cleaner, but it is a wide diff touching files 3.10 just stabilized.
   Recommendation: explicit re-export list now (narrow, safe), consumer cleanup
   as its own later pass.
3. **Does Tier 2 belong before Tier 1?** It is 761 lines vs 3,120 and touches
   less. The argument for MC first is that Tier 2's code calls `monte_carlo()`,
   so doing MC first means writing its import once. The argument for Roth first
   is a smaller first exercise of the whole pipeline. Either is defensible.
4. ~~**Is P1 achievable at acceptable CI cost?**~~ **Answered 2026-09-09 by
   measurement — see §2.4.** Yes: ~49s for both engines across all 10 synthetic
   scenarios, +39% on a test that already costs 125.4s. The premise behind the
   question was wrong — `project()` is 25 ms, so "reruns the projection per path"
   is cheap, and the expensive thing was the 25-cell × 200-path sensitivity grid,
   which is configurable and which `optimize_roth_conversion_strategy` already
   turns down internally. P1 gates every merge. Tier 1 proceeds.
5. **How long should P1's maximum-sensitivity pins stay?** §6 proposes relaxing
   the scalar pins to 3 scenarios once Tier 1 lands, on the grounds that
   RNG-consumption-order sensitivity is a refactor guard rather than a permanent
   property worth maintaining. Someone who expects continued behavioural work on
   the MC engines may reasonably want them relaxed sooner; someone who expects
   Tier 3 to follow may want them kept. Decide when Tier 1 closes, not now.

---

## 10. What this document does not claim

It does not claim the Phase 2c consolidation was wrong, or that the "do not
re-split" warning is obsolete. It claims the warning describes a cycle that runs
through `project()` and Monte Carlo — and that moving Monte Carlo out is the one
cut that *removes* that cycle rather than reproducing it, which is why it is
proposed first and alone. Tier 3 is where the warning still bites hardest, which
is why this design puts it last and marks it optional.
