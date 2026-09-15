# Testing & CI Refactor: Findings and Recommendations

Date: 2026-09-15
Scope: `tests/` (386 files, 2,854 collected tests, 50,465 LOC against 69,598 LOC
of `src/`) and `.github/workflows/ci.yml`.

This document records the measurements behind the CI/testing refactor and the
recommendations that followed, grouped by how much risk each carries. Tier 1
items are config-only and were implemented directly. Tier 2 and 3 involve
either running fewer/lighter tests on every PR (a real, small risk trade) or
larger structural work; each entry says what was actually done in this PR
versus what remains as follow-up.

## What was measured

**CI wall-clock** (10 most recent runs on `main`): 50-93 minutes, median ~77.
Per-job breakdown of a representative run (#654, 89.8 min total):

| Job | Wall | Notes |
|---|---|---|
| `test` (windows, 3.14) | 87m 20s | the `Run tests` step alone is 85m 44s |
| `e2e-tests` | 12m 34s | Playwright itself: 11m 9s |
| `build` | 2m 24s | but `needs: [test]`, so it starts at minute 87 |
| `regression-checks` | 51s | actual checks: 4s |
| `frontend-tests` | 32s | actual tests: 5s |

**95% of CI latency was one serial pytest invocation.** Everything else
finishes inside 13 minutes.

**Local run of the fast tier** (2,794 tests, `-m "not slow"`): 34 min of CPU
time; **10m 20s wall at `-n 4`** (3.3x speedup on 4 cores, confirming the
`-n auto` recommendation already documented in `CLAUDE.md` but never applied
in CI).

**The cost is concentrated in a small tail.** Of 2,794 fast-tier tests, the
slowest 60 (2.1%) account for 1,885 of 2,040 total seconds -- 92% of all CPU
time. The remaining ~2,730 tests cost ~155s combined. Three clusters
dominate:

| Cluster | CPU | Tests |
|---|---|---|
| housing optimizer / comparison sweeps | 606s | 16 |
| "exact-scalar agrees with vectorized" oracle tests | 501s | 15 |
| SS timing / longevity sweeps | 299s | 11 |
| `synthetic_golden_master` (single test) | 161s | 1 |

**Structural root cause of the tail:** 386 test files share only 18 fixtures
total (10 module-scoped, 0 session-scoped for engine/config setup). 26 files
define their own local `_project()`/`_base_config()` helper re-run per test;
`parse_client` is called 301 times across 113 files. Monte Carlo `n_sims` is
hard-coded at 30+ call sites (`800`, `200`, `150` x6, `20`, `15` x12); only 5
tests honor the `RETIREMENT_MC_SIMS` env var the shared build fixture already
uses.

**Tier-marker adoption:** `pyproject.toml` defines a five-tier taxonomy
(`unit`/`integration`/`golden_master`/`contract`/`e2e`), but only 14 of 386
files use it -- there was no machine-readable way to run less than "not slow"
before this PR.

**Maintenance drag from static checks:** 68 of 386 test files (18%) import
nothing from `src` -- they are pure source-text/grep assertions (line-count
ratchets, string presence, doc currency). At least five `Fix CI:` commits in
recent history (RENT_FIRST, RENT_REST, the dashboard.js line ratchet twice,
sheet-tab-order fixtures) were static-assertion failures each costing a full
~90-minute CI cycle to discover, because they surfaced after the 85-minute
engine run rather than before it.

## Tier 1 -- implemented, config-only, no behavior change (~86 min -> ~25 min)

1. **`-n auto` in CI**, matching the policy `CLAUDE.md` already documents.
   Added `--dist loadfile` to keep each file's tests on one worker (avoids
   splitting module-scoped fixtures across workers and matches the
   already-documented `WinError 5` file-lock flake mitigation), plus a
   serial `--lf` retry step if the parallel run fails.
2. **Fixed the coverage gate.** The job matrix is Python 3.14 only, but
   `Upload coverage` was gated `if: matrix.python-version == '3.11'` -- a
   condition that can never be true. Coverage instrumentation ran on every
   PR for 85 minutes and the XML was always discarded. `--cov` is now
   dropped from the PR-tier command entirely; a nightly workflow runs the
   full instrumented suite and uploads coverage once a day.
3. **Dropped the redundant `--tb=short -q`** already set at the tool level
   via `pyproject.toml`'s `addopts` (the CI command no longer repeats
   them). Initially also dropped `-v` on the same reasoning; that was
   wrong -- verbosity flags count rather than cancel, and dropping it
   broke the F0.3 golden-master gate (below) on this PR's own first CI
   run by removing the per-test PASSED line its old grep-based check
   depended on. Fixed by making F0.3 not depend on log-scraping at all
   (see item 6a) rather than re-tuning verbosity flags to satisfy it.
4. **Added a `concurrency` group with `cancel-in-progress: true`** so a
   force-push to a PR branch cancels its own in-flight run instead of
   burning a full ~90 minutes to a result nobody will read.
5. **Decoupled `build` from `needs: [test]`.** It is 2m24s of PyInstaller
   packaging with no dependency on test output; it now runs in parallel.
6. **Restored a bounded per-test timeout** (`pytest-timeout`, 300s,
   thread method) instead of the prior full removal, so a hang costs 5
   minutes of diagnostics instead of the entire job's time limit with no
   trace of which test hung.
6a. **Made the F0.3 golden-master gate self-contained.** It used to grep
   the big suite's captured `-q`/`-v` output for
   `test_frozen_plan_dollar_figures_are_exact`'s PASSED line -- a design
   that (per item 3 above) silently broke the moment the main run's
   verbosity flags changed, and was already fragile before that (the
   check could pass on a stale prior run's output file if a step above
   it failed to overwrite it). It now runs that one test standalone and
   checks its own exit code -- unambiguous, immune to any future change
   in the main run's flags or log format, and costs under a second.

## Tier 2 -- caps the long tail, small documented risk trade (~25 min -> ~10 min)

7. **New `nightly` marker** for tests whose failure mode cannot be produced
   by an ordinary PR change (engine-internals-only equivalence checks,
   sweep/optimizer breadth tests). Applied to the 26 tests identified above
   (scalar/vectorized oracle cluster + the heaviest housing/SS sweep cases).
   PR-tier CI now runs `-m "not slow and not nightly"`; a new nightly
   scheduled workflow runs the complete suite (including `slow` and
   `nightly`, with coverage) once a day and reports failures.
   *Risk accepted: a scalar-vs-vectorized engine divergence, or a rare
   sweep-composition regression, surfaces up to a day later instead of
   in-PR. The fast-tier cheap canary in each affected file (the
   vectorized-only assertions, which run in under a second) still runs on
   every PR.*
8. **Shared Monte Carlo simulation counts.** Added a
   `mc_sims`/`mc_sensitivity_sims` fixture pair in `tests/conftest.py`
   reading the same `RETIREMENT_MC_SIMS`/`RETIREMENT_MC_SENSITIVITY_SIMS`
   env vars the shared build fixture already uses, defaulting low. Rewired
   `test_adoptable_spending_policy_functional.py` (six 150-sim
   `monte_carlo()` calls across four tests -- the second-largest
   single-file cost in the fast tier) as the worked example: three
   module-scoped fixtures, one per seed the file's tests actually need,
   replace six independent Monte Carlo runs with three (measured: fixture
   setup now totals ~43s instead of the ~86s the six separate calls cost
   before -- confirmed with `--durations`). The same pattern (a
   module-scoped fixture wrapping a `_project()`/`monte_carlo()` pair,
   keyed by whatever varies between the tests that can share it) is now
   documented in `CLAUDE.md` for new tests and as a follow-up for the
   other 25 files identified with local per-test setup helpers.

**Not done in this PR (follow-up):** rewiring the remaining ~25 files with
local `_project()`/`_base_config()` helpers, and routing the remaining
hard-coded `n_sims=` call sites through the new fixture. This is
mechanical but touches ~25 files' worth of test bodies; the housing-sweep
files already follow this pattern and were used as the reference.

## Tier 3 -- maintenance drag, structural (partially implemented)

9. **New `fast-gates` CI job** that runs first: ruff, the 68 source-text-only
   test files (selected by `-m "not slow and not nightly"` plus a
   `pytest.ini` collection filter... in practice, selected by file list
   since they carry no distinguishing marker today), and
   `tools/run_regression.py`, all before the expensive `test` job starts.
   Reports the exact class of failure (a line-ratchet or string-presence
   assertion) that cost ~7 hours of CI latency across five recent `Fix CI:`
   commits, in under 90 seconds instead of after an 85-minute wait.
10. **Folded `regression-checks` into `fast-gates`**, removing a separate
    job whose own setup (51s) dwarfed its actual check time (4s).
11. **Python version aligned to 3.14** across all jobs (was 3.14 for `test`,
    3.11 for `e2e-tests`/`regression-checks`/`build`) so the executable
    shipped from `build` is produced on the same interpreter the suite
    exercised.

**Not done in this PR (deliberate follow-ups, not oversights):**

- **Full five-tier marker retrofit** across all 386 files. The tier
  taxonomy's own design (system review 2026-08-04) explicitly rejected a
  full-tree reorganization; this PR extends adoption only to the tests
  identified as expensive enough to matter (the new `nightly` marker),
  which is the leverage point that lets CI stop running everything on
  every PR.
- **Path-scoped jobs** (skip the Python engine suite for a frontend-only or
  docs-only PR beyond the existing `paths-ignore`). Deferred: filters of
  this kind risk masking cross-layer breakage (a frontend change that
  silently depends on a backend contract), and Tier 1+2 already remove
  the incentive (an 85-minute unconditional run) that made this urgent.
  Worth revisiting once the fast-tier PR time is ~10 minutes and the
  remaining latency is worth shaving further.
- **E2E sharding.** At 11m9s serial (`workers: 1`, one shared server across
  17 specs), this is not the bottleneck yet. Once the Python engine suite
  drops to ~10 minutes as above, e2e becomes the next-longest job and
  `--shard=i/n` across 2-3 jobs (each with its own server) is the
  straightforward next step.

## What was deliberately left alone

The frozen golden master, `test_synthetic_golden_master.py` (161s -- the
single most expensive test, and the one pinning the dollar figures a
retirement plan is judged on), and the all-on/all-off optional-module build
checks in `test_all_modules_off_build_functional.py`. These stayed in the
PR-tier fast suite.

One trade was identified but **not** taken because the quality cost looked
more than minor: `test_all_modules_off_build_functional.py`'s per-module
sweep (~21 full workbook builds, one per optional module individually
disabled, ~90s each) could move to nightly for another ~30 min of CPU
savings, at the cost of a cross-sheet-reference regression (module A's
builder assuming module B's sheet exists unconditionally) surfacing up to a
day late instead of in-PR. Left as a PR-tier `slow` test; flagged here for
the user's own call if CI time becomes tight again.
