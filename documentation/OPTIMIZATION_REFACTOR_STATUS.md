# Optimization Refactor — Status

Tracks progress on the "Final Optimization Implementation Plan — Revised": a
multi-phase rewrite of the retirement system's Monte Carlo/tax/decision engine
toward a constrained, multi-objective, state-contingent policy framework
(replacing terminal-net-worth-only optimization with a Lifetime
Consumption-and-Transfer Value / LCV framing). Work happens on branch
`claude/plan-execution-tg1rps`, PR #59.

This document is the durable record of what's done and what's next — the
in-session planning notes Claude Code keeps locally do not survive a new
session or container, so treat this file as the source of truth when picking
the work back up.

## Done

### Phase 0 — Spending tier taxonomy
`SPENDING_TIERS` registry in `src/spending_budget_resolver.py`
(essential / important / discretionary / contingent_liability), emitted as
`row['spend_by_tier']` from `src/projection_stages/deterministic_engine.py`,
reconciling exactly to `row['total_spend']`.

### Phase 1 — Item 1: per-tier spend in both MC engines
Real, plan-start-dollar per-tier spend matrices propagated into both Monte
Carlo engines in `src/planning_engines.py` (`monte_carlo_exact_scalar` and
`_mc_vectorized_projection`, via `_mc_row_bucket_flows`).

### Phase 1 — Items 2–6: tax/gift fields + survivor economics
- Items 2–3: `row['gross_cash_flow_yr']` (deterministic engine) plus
  per-path tax/gross-cash-flow/gift-charity real-dollar distributions in
  both MC engines.
- Items 4–6: the **vectorized** engine was missing survivor economics
  entirely — every path used one deterministic trajectory regardless of
  when either spouse died, overstating survivor-period spending/benefits.
  (The scalar engine already got this right "for free" via its per-path
  `project()` rerun.) Fixed via `_mc_survivor_bucket_flows` (precomputes a
  small number of representative post-first-death trajectories) and
  `_mc_effective_row_flows` (blends them into each path via `bucket_id =
  spouse_first * n_years + year_idx`). On by default
  (`mc_vectorized_survivor_economics`, kept as an emergency kill switch).
- Adjacent bug fix: `sample_household_death_years` now sets
  `first_death_yr` (previously mistimed the Qualifying-Surviving-Spouse
  2-year filing window).
- **Performance regression caught and fixed**: `sheets_strategy.py`'s
  Social Security claim-age sweep called `monte_carlo()` 81 times per
  build, each independently rebuilding the survivor buckets (~4,500 extra
  `project()` calls per build) — this caused real `subprocess.TimeoutExpired`
  failures in CI (`test_all_modules_off_build_functional.py`, Windows job).
  Fixed by adding a `survivor_buckets=None` passthrough to `monte_carlo()`
  and building it once before the sweep's loop. See **Methodology lesson**
  below — this is why the fix is documented here at length.

### Phase 2 — Reporting-only MC dashboard metrics (partial)
All additive: each reads an engine's already-finalized output and never
feeds back into withdrawals, `unfunded`, `liquid`, `total`, `path_success`,
or `success_rate`.

| Metric | Where | Notes |
|---|---|---|
| `spending_priority_cut_check` | `planning_engines.py` | Extends `essential_discretionary_floor_check`'s 2-tier check into the full discretionary→important→essential cascade; wired into `sustainable_spending_solve` as `tiered_*` fields |
| `essential_fully_funded_probability` | both MC engines | Fraction of paths whose essential tier is never left unfunded |
| `probability_any_cut` + `cut_years_pct` / `max_annual_shortfall_real_pct` / `max_consecutive_cut_years_pct` / `cumulative_shortfall_real_pct` | both MC engines | Genuine per-path cut statistics from each path's own realized shortfall (not a single solved cut_frac scenario) |
| `liquidity_coverage_pct_by_year` + `worst_liquidity_coverage_ratio_pct` | both MC engines | `liquid / success_threshold`, i.e. how many times over the existing reserve floor is covered — re-labels a relationship the success/failure test already uses, rather than inventing a new floor concept |
| `after_tax_terminal_nw_pct` + `post_tax_inheritance_pct` | both MC engines | Reuses `estimate_after_tax_terminal_net_worth` (`src/after_tax.py`), the same helper the deterministic Roth-optimizer scoring path already calls. Scalar engine reuses the path's real per-account terminal row exactly; vectorized engine approximates via the same aggregate-taxable-balance fallback `estimate_terminal_taxable_deferred_cap_gain_tax` already has for accounts without per-lot cost basis |

| `survivor_period_applicable_probability` + `survivor_period_failure_probability` | both MC engines | Scopes the same funding-failure condition `path_success`/`_funding_success` already use to the years strictly after each path's own sampled first death, up to and including the second death. `None` for a single-person household or when no path in the batch has a survivor window |

All six are covered by dedicated regression test files (see
`tests/test_spending_priority_cut_check_regression.py`,
`tests/test_essential_fully_funded_probability_regression.py`,
`tests/test_mc_cut_statistics_regression.py`,
`tests/test_liquidity_coverage_distribution_regression.py`,
`tests/test_after_tax_legacy_value_distribution_regression.py`,
`tests/test_survivor_period_dashboard_rows_regression.py`) and were
verified against the full local suite, the `-m slow` build-functional suite,
and CI, with zero regressions against the pre-existing baseline failure set
(see below).

## Not done

- **Redirecting actual withdrawal amounts by tier priority** inside the MC
  engines (today's uniform `cut_mult` would become tier-prioritized). A much
  larger, riskier rewrite than the reporting-only additions above — treat as
  its own project, not a quick follow-on.
- **Contingent-liability funding rules.**
- **"Probability of meeting a user legacy floor"** — no `legacy_floor`-style
  config field exists anywhere in this codebase yet. Adding one needs a
  CSV-schema / UI / docs decision, not just a reporting-layer computation.
- **Phases 3–6 of the overall plan** (tax NPV / ELTR state-contingent tax
  modeling, LCV feasibility gate and scoring, adaptive policy guardrails,
  expanded stress scenarios) are entirely unimplemented.

## Verification discipline established this session

- A **pre-existing baseline failure set** was confirmed via `git stash`
  comparison against `main`: 7 `FAILED` + 8 `ERROR` (mostly
  `ValueError: residence_state is not set`, from real client `input/` data
  being gitignored in a sandboxed dev environment) plus one flaky assertion
  (`test_withdrawal_sequencing_comparison_regression.py::test_current_plan_is_the_lowest_tax_and_highest_terminal_of_the_four`).
  Locally (`-m "not slow"`) this set is 34 items total, once broader
  dashboard-codemod/tax-aware-rebalance/etc. tests unrelated to this repo's
  real-`input/`-data gap are included. Any verification pass should diff
  against this identity — matching test IDs, not just a raw failure count.
- **`test_all_modules_off_build_functional.py` is marked `@pytest.mark.slow`
  and is excluded by `-m "not slow"`, but CI runs it unfiltered.** This is
  exactly how the 81x survivor-bucket regression above went undetected
  locally for three pushed commits despite repeated "zero regressions"
  claims from `-m "not slow"` runs. **Run at least one `-m slow` (or fully
  unfiltered) pass before considering any change touching Monte Carlo
  engine performance fully verified.**
- `git status` on `input/` must be clean after every test run (real client
  data must never get staged).
- `RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS=1` for deterministic local
  test runs.
- A full, unfiltered background test run can appear to finish cleanly while
  actually truncated (e.g. a `timeout` wrapper cutting it off mid-summary).
  Confirm completion by checking for the final pytest summary line, not just
  the absence of visible failures.

## Resuming this work in a new session

1. `git fetch origin claude/plan-execution-tg1rps && git checkout claude/plan-execution-tg1rps`
   — recovers all code/tests/docs; the branch is kept fully pushed after
   every increment.
2. Check PR #59's CI status and this file's **Not done** section for the
   next increment.
3. Follow the verification discipline above — targeted regression tests
   first, then a full `-m "not slow"` suite diff against the baseline
   identity, then an `-m slow` pass for anything touching MC performance,
   then push and check CI (Windows job + `e2e-tests`; the latter is
   confirmed pre-existing base-red and unrelated to this work).
