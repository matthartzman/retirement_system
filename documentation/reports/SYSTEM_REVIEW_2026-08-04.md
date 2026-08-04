# System Review — 2026-08-04

**Scope:** the entire system · **Depth:** standard · **Run ID:** `wf_e2a38b46-904`

---

## ⚠️ Provenance and status of this document

This review was produced by the five-expert panel workflow. **36 of 39 agents completed**; the three
final opus stages — orchestrator synthesis, financial-planner sign-off, and orchestrator revision —
**failed on a session token limit** before writing anything.

What that means for how you read this:

| Stage | Status |
|---|---|
| Recon (engine / UI / tests+docs) | ✅ completed |
| Five expert reviews | ✅ completed — 45 findings, all with `file:line` evidence |
| Adversarial cross-check (28 verifiers) | ✅ completed — **0 refuted**, 4 citation corrections |
| Orchestrator synthesis | ❌ failed (session limit) → **reconstructed by the main orchestrator from the run journal** |
| Financial-planner sign-off | ❌ failed (session limit) → **deferred to after Wave 3 by decision — see §6** |
| Orchestrator revision | ❌ failed (session limit) → not applicable (no sign-off to apply) |

**Revision 2 (2026-08-04):** C3 and C4 were re-assessed at source level per Appendix B's caveat, and
the five open questions were decided. **The re-assessment changed the answer** — see §2.5. Effort
estimates are now calibrated to measured throughput (§4.0).

Every finding, option, and per-finding recommendation below is the verbatim work of the expert agents.
The **cross-expert conflict resolution, wave sequencing, and model assignments are the main
orchestrator's synthesis**, written after the fact from the cached journal — not the workflow's own
opus synthesis pass. The independent planner sign-off that this skill treats as non-negotiable
**has not happened**, so the sequencing in §4 should be treated as a strong draft, not a ratified plan.

---

## 1. Verdict

The panel's collective read: **this is a genuinely strong engine wrapped in a deliverable that
undersells it, tested by a suite that cannot see its own frontend, and carrying decomposition work
that was announced but not performed.**

The tax and estate plumbing drew explicit praise from the financial planner — SSA dual entitlement,
IRMAA with the statutory two-year lookback and SSA-44 relief, ACA PTC interaction with conversion
sizing, QCD with the AGI carve-out, AGI-limited DAF with five-year carryforward, CST funding, §1014
step-up regimes, SECURE 10-year heir-rate derivation, and an 81-pair Social Security sweep run through
the full projection rather than a break-even table. Their words: *"better than most commercial software."*

The problems are concentrated in three places, and they are not where you would guess:

1. **The first page of the client deliverable prints numbers that are wrong or hardcoded.** Two
   independent experts (financial planner, documentation) found this separately, from different
   angles, and both rated it critical.
2. **Five modelling simplifications quietly bound what the tool can conclude** — one return for every
   account, Gaussian mortality with a floor at 70, no medical deduction, an unindexed estate
   exemption, and nominal-only reporting.
3. **The decomposition is partly theater** — re-export shims onto the monoliths they were meant to
   replace, a star-import cycle, a 14-stage pipeline that runs one call, and a DB-canonical migration
   whose write API has been returning 403 since it was written.

### Finding counts

| Expert | Findings | Kept | Refuted | Critical | High |
|---|---:|---:|---:|---:|---:|
| Architect | 13 | 13 | 0 | 0 | 5 |
| Financial planner | 13 | 13 | 0 | 4 | 6 |
| Quality | 8 | 8 | 0 | 1 | 2 |
| Documentation | 6 | 6 | 0 | 1 | 2 |
| Usability | 5 | 5 | 0 | 0 | 2 |
| **Total** | **45** | **45** | **0** | **6** | **17** |

A 0/28 refutation rate is unusually clean. Read it with mild suspicion — it may indicate the
verifiers were insufficiently adversarial rather than that every finding is airtight. The four
corrections they *did* return (Appendix B) were all line-number precision, never substance.

---

## 2. The six critical findings

### C1 · Executive Summary prints a Roth number that contradicts the system's own optimizer
`sheets_summary.py:993` · financial planner + documentation, independently

```python
roth_benefit = sum(row.get('roth_conv',0)*0.22 for row in rows)   # approx
```

Published at line 1022 as the headline **"Estimated Tax Saved — Roth Strategy."** That is 22% of
*gross conversions* labelled as tax *saved* — conversions cost tax in the year taken. The system
already computes the defensible figure two sheets later: Sheet 11's candidate table compares lifetime
tax and after-tax terminal net worth across strategies (`sheets_strategy.py:390-435`). It is formatted
with the same `FMT_DOLLAR` as the exact model outputs directly above it, with nothing to distinguish
approximation from computation.

**Options:** (a) replace with the selected-vs-next-best delta from the Sheet 11 contract; (b) relabel
inline as "approx., flat 22% rate" and note it in the existing Release Notes block; (c) drop the row
from Headline Numbers entirely.

**Recommendation:** (a) — the planner called this *"non-negotiable — it is on the first page and
contradicts Sheet 11."* Ship (b) the same day if (a) needs a projection change, so the page is never
left silently wrong.

### C2 · Executive Summary hardcodes client-independent dollar figures
`sheets_summary.py:1035-1075` · financial planner + documentation

The Priority Recommendations block prints literal strings into a client-facing summary:
`'~$320K IL estate tax avoided on $4M (8% avg rate)'`, `'S-Corp reasonable salary $80K on $290K
income saves ~$30K SE tax'`, `'~$9,600 tax deduction at 24% marginal rate'`, `'Face value $250K–$500K'`,
`'$8,000–$15,000/yr premiums'`. They are gated on booleans but **the amounts never vary with the
household.** Sheet 14 computes the real, plan-specific number from `il_exempt` — a configurable field.
Whenever it differs from the coincidental $4M default, page 1 contradicts the sheet it cites.

**Options:** (a) compute every value from the analysis that already exists, or print rationale with no
figure; (b) demote to "Topics to review" with sheet cross-references, no dollar amounts;
(c) quarantine onto a labelled "illustrative examples" sheet.

**Recommendation:** (b) immediately — it is fast, removes every indefensible number, and matches how a
planner actually uses an agenda list — upgrading items to (a)'s computed values as each analysis is
wired in. For the CST figure specifically, documentation recommends extracting a **shared helper** so
Sheet 1 and Sheet 14 can never disagree again, explicitly rejecting copy-paste because
`glossary.py`'s own docstring records that this codebase already shipped a drift bug that way.

### C3 · Every account grows at one identical rate
`planning_engines.py:38-55` · financial planner · effort **L**

`_account_return()` reads `c['account_returns']`, which **is never populated anywhere in the repo** —
grep across `src/`, `tools/`, `tests/`, `input/` returns only the definition and a docstring saying
*"Future modules can populate…"*. In Monte Carlo, `return_by_year[year]` is returned first and
overrides any per-account rate. So asset location, bucket strategies, and the cash reserve are
**structurally inert** — while `sheets_qc_reference.py:272-330` ships an "Asset-Location Optimizer"
sheet quantifying savings the engine cannot produce.

**Options:** (a) per-account returns derived from actual holdings mapped to asset-class CMAs;
(b) **sleeve-level returns** (reserve/cash, fixed income, growth) with correlated MC paths;
(c) keep one rate but retire Sheet 24 and disclose the limitation.

**Recommendation:** (b) — captures the planner-relevant behavior (the cash reserve costs something,
bonds in the IRA suppress future RMD growth, the Roth compounds fastest) without rewriting the
vectorized MC around a per-holding covariance draw. **Ship (c)'s disclosure immediately as an interim**,
since Sheet 24 currently promises savings the engine cannot deliver.

⚠️ Golden-master regeneration unavoidable. See §3.1.
📉 **Effort revised L → M on re-assessment. See §2.5.**

### C4 · Longevity is a truncated normal — no simulated household dies before 70
`planning_engines.py:510-522` · financial planner · effort **M**

```python
sampled_age = rng.gauss(median_age, c.get('mortality_sigma', 4.5))   # clamped to max(70.0, …)
```

With μ=92, σ=4.5, modeled probability of death before 80 is **under 1%**, and the hard floor makes it
**exactly zero below 70**. The docstring concedes it is *"a placeholder for SSA/SOA table calibration."*
This single distribution drives the Social Security recommendation, the survivor stress test, and every
LTC and life-insurance conclusion. The SS sweep runs 81 full projections and then ranks them under one
assumed death age — the planner called that *"the weakest link in an otherwise strong analysis."*

**Options:** (a) embed SSA period life tables / SOA 2012 IAM with improvement scale, sample from the
hazard curve; (b) keep parametric but switch to Gompertz-Makeham, drop the floor, add joint-mortality
correlation; (c) leave the sampler, re-score decisions as probability-weighted across survival curves.

**Recommendation:** (a), with (c)'s age-conditional display layered on top — *"a real table is the only
version a planner can defend."*

📈 **Effort revised M → L, and the panel missed a second call site. See §2.5.**

---

### 2.5 · Re-assessment of C3 and C4 (revision 2)

Appendix B flagged that the 0/28 refutation rate warranted an independent second look at the two
expensive findings before committing. That look was performed at source level. **It changed the
answer in both directions — the panel had the relative effort backwards.**

#### C3 is cheaper than rated — every prerequisite already exists (L → M)

The planner's option (b) assumed sleeve-level returns meant building a sleeve taxonomy and reshaping
the Monte Carlo draw. Neither is true:

| Prerequisite | Panel assumption | Actual state |
|---|---|---|
| Per-account return hook | needs building | **exists** — `_account_return()` reads `c['account_returns']`; only the population is missing |
| Sleeve taxonomy | needs defining | **exists** — `reference_data/security_master.csv` already carries a `sleeve` column alongside `asset_class` |
| Per-account holdings | — | **exists** — `client_holdings.csv` maps account → symbol |
| Asset-class CMAs | needs sourcing | **exists** — `reference_data/capital_market_assumptions.csv` (return, vol, correlation per class) |
| MC per-class draw | *"must change shape from scalar to matrix"* | **already a matrix** — `planning_engines.py:2730-2733` draws `multivariate_normal(means, cov, size=(n_sims, n_years))` over asset classes, then collapses it with a single weight vector: `base_draws = raw.dot(wv)` |

That last row is the crux. The expensive part — the correlated multivariate draw across asset classes —
**already runs on every Monte Carlo**. Sleeve returns do not require a new draw; they require replacing
one weight vector with a small weight *matrix* (`raw.dot(W)`, W shaped n_classes × n_sleeves) and
routing each account to its sleeve column. The deterministic path has a single growth call site
(`deterministic_engine.py:2472`) whose per-account hook is already plumbed.

**Revised effort: M (1–2 days).** The work is a two-hop join (account → symbol → sleeve) and a dot
product, not an engine rewrite.

#### C4 is more expensive than rated, and a second Gaussian was missed (M → L)

The panel cited `sample_death_year()` at `planning_engines.py:510-522`. **There is a second,
independent copy of the same Gaussian** that the review did not mention:

```python
# planning_engines.py:2703-2719  —  _mc_vectorized_death_years()
h = _np.rint(h_dob + _np.clip(np_rng.normal(h_med, sigma, size=n_sims), 70.0, 110.0)).astype(int)
```

This is the vectorized path — **the one that actually produces the headline success rate.** A fix
applied only to the cited scalar function would leave every number a user sees unchanged while
appearing complete. That is a worse outcome than not starting, and it is exactly the failure mode the
review's own `source-text-grep-implementation-pinning` finding warns about: a change that looks done
because the thing you inspected changed.

Compounding it: `reference_data/` contains **no mortality table** — a repo-wide grep for
`life_table`/`qx`/`SOA` returns only code comments. Unlike C3, the reference data must be sourced,
committed, validated, and added to the annual-maintenance runbook alongside the tax-law dataset.

**Revised effort: L (3–5 days).** Two independent samplers must change together, plus new reference
data with an ongoing maintenance commitment.

#### What this changes

**Do C3 before C4.** The original plan ordered them 3.5 then 3.6 on the assumption C4 was cheaper.
Reversed: C3 is now the faster win, it unblocks the Sheet 24 disclosure being retired rather than
maintained, and it carries no new-reference-data commitment. C4 should be scheduled with its true
cost visible, and its acceptance criterion must explicitly name **both** samplers.

### C5 · Every headline number is nominal, and the Roth objective is internally inconsistent
`sheets_summary.py:1005-1010`, `planning_engines.py:1621` vs `:1776` · financial planner · effort **M**

`sheets_projection_tax.py:70-79` totals lifetime tax by **adding 2026 and 2058 dollars together**. In
the Roth objective, line 1621 present-values lifetime tax and 1766-1772 present-values estate tax, but
line 1776 uses **undiscounted** plan-end wealth — so the objective systematically over-rewards deferring
wealth into the far future relative to the taxes paid to get there.

**Recommendation:** dual-column nominal + today's-dollars reporting on Sheets 1/5/6/7/15 and the
dashboard tiles, plus deflating `after_tax_terminal_nw` with the same discount as the tax and estate
terms. The objective inconsistency *"is a one-line fix that should not wait."* Note this **will** reduce
optimizer-selected conversion sizes in long-horizon plans — correct direction, but it must land in
`GOLDEN_MASTER_CHANGELOG.md` or it reads as a regression.

### C6 · The 19,637-line frontend has zero DOM/browser test coverage
`package.json:7` · quality · effort **XL**

`npm test` runs 11 files against a hand-stubbed Node `vm` sandbox whose own comment says it
*"deliberately targets only the small set of functions that take explicit parameters and return a value
with no dependency on shared state"* — the other ~800 functions *"cannot be safely unit-tested in
isolation."* No Playwright/Puppeteer/Cypress/Selenium anywhere in the repo. A broken onclick handler, a
JS exception on render, or a navigation dead-end **would ship undetected through the entire suite.**

Compounding it: **141 of 228 test files** assert behavior by grepping source text
(`.read_text()` + `assert 'literal' in js`, 393 occurrences). Those tests pass when the matched code
path is dead, and pass through behavior-changing refactors that preserve strings.

**Recommendation:** Playwright over the 2–3 highest-value journeys (data entry → save → build → view
results). Separately, ban new substring-matching tests on executable frontend code via a lint rule —
cheap, and it stops the growth.

---

## 3. Cross-expert conflicts — resolved

The experts worked independently and four of their recommendations collide. Resolving these is the
main thing this section adds over reading the five reports separately.

### 3.1 Five engine changes each independently invalidate the golden master → **batch them**

`engine-single-return-all-accounts` (C3), `mortality-gaussian` (C4), `reporting-nominal-dollars` (C5),
`no-medical-expense-deduction`, and `estate-tax-il-only-unindexed` were each written as a standalone
change, and **each one says "expect golden-master movement, pre-brief it."** Sequenced naively that is
five separate regenerations, five changelog entries, and five windows where a regression cannot be
bisected cleanly.

**Resolution:** treat them as **one engine-correctness wave with a single golden-master regeneration at
the end.** Land each behind its own commit for bisectability, run the frozen-fixture gate between them
to confirm each moves only what it should, and regenerate baselines **once**. Per project memory, a
golden-master regeneration is *already pending* from the `_mode` column resolver fix — fold that in
rather than paying the cost twice. Use `RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS=1` throughout, or
pricing drift will contaminate the diff.

### 3.2 Playwright vs. ES-module migration → **tests first, and it is not close**

Quality wants a browser e2e layer (C6). The architect wants `frontend-single-global-namespace` (XL)
converted to ES modules, noting it *"is the only option that actually removes the load-order contract."*
These interact badly in one order and well in the other: an ES-module migration will invalidate a large
share of the 141 source-grep test files *and* there is no execution-level safety net to catch what
breaks.

**Resolution:** **Playwright first.** It is the only artifact that survives the refactor and can prove
the refactor was safe. The architect's own first recommendation — a **size ratchet** on `dashboard.js`
so the monolith cannot reabsorb extracted code — is cheap, independent, and should land alongside it.
ES modules come after, from the leaves inward.

### 3.3 Executive Summary: three findings, one file, one editor

C1, C2, and documentation's `unlabeled-flat-rate-roth-headline` all edit `sheets_summary.py:993-1075`.
Assigned to three workstreams they would conflict on every line.

**Resolution:** one **"Executive Summary truthfulness"** workstream owning that block end to end,
implementing the planner's and documentation's recommendations together. This is also the highest
value-per-hour work in the review — it is small, it is on page 1, and it is the only category where
*two experts independently reached the same critical verdict.*

### 3.4 Executive Summary content fixes vs. splitting `sheets_summary.py`

The architect's `reporting-facade-theater` (L) wants `sheets_summary.py` (2,957 lines) partitioned —
the same file §3.3 is editing.

**Resolution:** **content fixes first, split rebases onto them.** The content changes are ~50 lines and
fix a client-facing correctness defect rated critical by two experts; the split is a large structural
change with no user-visible benefit. Blocking a critical fix behind an L refactor inverts the priority.
The one piece of the architect's finding that should go *immediately and independently*:
delete `sheets_projection.py` — a shim onto a shim with **zero production callers**, kept alive only by
tests asserting the shim exists.

### 3.5 Accordion jump-fix vs. spending-domain tabs

Usability filed both `ui-accordion-breaks-jump-to-field` (S) and `ui-spending-domain-fragmentation` (L),
and notes the latter *"directly removes … the accordion-hiding bug."*

**Resolution:** ship the **S** fix now — as the generic `revealAndFocus()` helper (option 3), not the
one-call-site patch, because hidden-target focus is a bug *class* and other call sites share it. The L
tab migration remains worthwhile on its own merits and simply inherits a working helper.

---

## 4. Implementation plan

Waves are dependency-ordered. Items **within** a wave are independent and parallelizable. "Model" is
the *minimal effective* model for that item, not an upper bound.

### 4.0 Effort calibration

Estimates are **calibrated to this project's measured throughput**, not to abstract t-shirt sizes.

Measured over the trailing 12 weeks (`git log`): **~89 commits/week sustained** (62 / 125 / 97 / 89 / 73
across W27–W31), **one developer** (Matt) working with AI pairing, **median 3 files per commit**
(max 25). That is a high-velocity solo configuration — roughly 18 commits/day — where the binding
constraint is review-and-verify attention, not typing.

| Label | Calendar time | Shape at this velocity |
|---|---|---|
| **S** | ≤ ½ day | One focused session, 1–3 files, no baseline movement |
| **M** | 1–2 days | Multi-file, needs its own test, may touch a fixture |
| **L** | 3–5 days | Cross-cutting, moves the golden master, needs a changelog entry |
| **XL** | 2+ weeks | New tooling or a migration with a long tail of follow-ups |

Two caveats. First, golden-master items are **gated on verification, not authorship** — the diff review
dominates, so their calendar time is insensitive to velocity. Second, Wave 3 items are sequential by
design (§3.1); their days add rather than overlap.

### Wave 0 — Deliverable truthfulness · ~1–2 days · no engine risk

Everything here is wrong text or wrong numbers on client-facing output. None of it touches the
projection engine, so none of it moves the golden master.

| # | Item | Expert | Effort | Model |
|---|---|---|---|---|
| 0.1 | Executive Summary truthfulness block (C1 + C2 + flat-rate label) — **single owner, see §3.3** | planner + docs | M | opus |
| 0.2 | CST figure → shared helper so Sheet 1 and Sheet 14 cannot diverge | docs | S | sonnet |
| 0.3 | `advisor_readiness()` returns `status_label` + `status_note`; stop printing raw enums | docs | S | sonnet |
| 0.4 | Finish the glossary consolidation — fold `banners.js` terms into `src/glossary.py`, delete the third copy | docs | S | sonnet |
| 0.5 | Allocation-mode dropdown copy + rewrite `FIELD_HELP` to cover all five modes | docs | S | sonnet |
| 0.6 | PDF truncation marker + cover-page notice | docs | S | haiku |
| 0.7 | Sheet 24 asset-location disclosure — **interim, retired by 3.5** *(decided — §6 Q2: keep the sheet)* | planner | S | sonnet |

**Wave 0 total: ~3–4 working days.**

### Wave 1 — Cheap high-value fixes · parallel · no coupling

| # | Item | Expert | Effort | Model |
|---|---|---|---|---|
| 1.1 | Plan Forms API 403 → `write_config` + **AST test** asserting every `_require()` literal exists | architect | S | sonnet |
| 1.2 | Results Explorer mtime+size cache (426 KB JSON re-parsed on every click) | architect | S | sonnet |
| 1.3 | `_sync_config_backends()` memoize `load_csv` — halves 20 file reads per save | architect | M | sonnet |
| 1.4 | Generic `revealAndFocus()` helper — fixes jump-to-field bug class (§3.5) | usability | S | sonnet |
| 1.5 | Per-step "Saves automatically" / "Save required" badge | usability | S | sonnet |
| 1.6 | **Effective marginal rate** — ±$1,000 re-run incl. SS torpedo, IRMAA, NIIT, lost PTC | planner | S | opus |
| 1.7 | Extract tax-math unit tests → `test_core_tax_math.py` | quality | S | haiku |
| 1.8 | Delete duplicate admin click-handler test; consolidate admin-nav cluster to test_24+25 | quality | S/M | haiku |
| 1.9 | Delete `Phase5GoldenMasterEngineTests` (strictly weaker than the synthetic gate) | quality | S | sonnet |
| 1.10 | Delete `sheets_projection.py` — shim-on-a-shim, zero production callers (§3.4) | architect | S | haiku |

> 1.6 is flagged by the planner as *"the single highest-value-per-line change available."* A household in
> the 12% bracket with taxable Social Security can face a 22.2% effective marginal rate; the tool
> currently reports 12%.

### Wave 2 — Test infrastructure · **gates Waves 3 and 6**

| # | Item | Expert | Effort | Model |
|---|---|---|---|---|
| 2.1 | Playwright: 2–3 journeys (edit → save → build → view results) — **§3.2** | quality | XL | sonnet |
| 2.2 | Lint rule banning new substring assertions on executable frontend code | quality | S | haiku |
| 2.3 | `dashboard.js` size ratchet so the monolith cannot reabsorb extractions | architect | S | haiku |
| 2.4 | Five-tier pytest markers; split `test_phase5_validation_maturity.py` by tier | quality | L | sonnet |
| 2.5 | Sheet-table consistency test (safety net **before** the registry — §Wave 4) | architect | S | sonnet |

### Wave 3 — Engine correctness · **two bracketing regenerations** · §3.1

Sequential within the wave (each is bisectable). **Reordered per §2.5: C3 now precedes C4.**

| # | Item | Expert | Effort | Days | Model |
|---|---|---|---|---:|---|
| **3.0** | **Baseline regeneration — clear the pending `_mode` resolver regen so Wave 3 diffs are attributable** | — | M | 1–2 | opus |
| 3.1 | Index federal estate exemption by `brk_inf`; gate IL estate tax on residence state | planner | M | 1–2 | opus |
| 3.2 | §213 medical deduction with 7.5% AGI floor; route LTC shock into the pool | planner | M | 1–2 | opus |
| 3.3 | Roth objective: deflate `terminal_component` (one line, §C5) | planner | S | ½ | opus |
| 3.4 | Real-dollar **dual-column** reporting across Sheets 1/5/6/7/15 + dashboard *(decided — §6 Q3)* | planner | M | 1–2 | opus |
| 3.5 | **Sleeve-level per-account returns** (C3) — *was 3.5/L, now M and ordered first* | planner | **M** | 1–2 | opus |
| 3.6 | **SSA/SOA mortality table** (C4) — **must change *both* samplers; see §2.5** | planner | **L** | 3–5 | opus |
| 3.7 | Final golden-master regeneration + `GOLDEN_MASTER_CHANGELOG.md` entry covering 3.1–3.6 | — | M | 1–2 | opus |
| **3.8** | **Re-run the workflow's planner sign-off against this document** *(decided — §6 Q1)* | planner | S | ½ | opus |

**Wave 3 total: ~11–18 working days** (sequential — these do not overlap).

> **Why two regenerations (§6 Q5).** 3.0 clears the *already-pending* `_mode` resolver baseline before
> any new engine change lands. Without it, Wave 3's diff is a mixture of six new changes and one old
> one, and no individual change can be attributed or bisected. 3.7 then captures 3.1–3.6 against a
> clean baseline. Paying for two regenerations buys attributable diffs; folding them into one saves a
> day and forfeits that.
>
> **3.6 acceptance criterion:** the change is not complete until **both** `sample_death_year()`
> (`planning_engines.py:510`) **and** `_mc_vectorized_death_years()` (`planning_engines.py:2703`) draw
> from the table. Verify by asserting a non-zero count of simulated deaths before age 70 in the
> *vectorized* MC output, not the scalar path.
>
> Every item here moves client numbers. 3.1 and 3.6 move them in directions clients notice (lower
> estate tax; early-death paths appearing where none existed). The changelog entry is not optional.

### Wave 4 — Architecture debt · after Wave 2's safety net

| # | Item | Expert | Effort | Model |
|---|---|---|---|---|
| 4.1 | Remove `_we`/`_ce`/`_ie`/`_ge` aliases + duplicate mid-file imports | architect | S | sonnet |
| 4.2 | Replace `from ..planning_engines import *` with an explicit name list — **prerequisite for any split** | architect | M | opus |
| 4.3 | `SHEET_REGISTRY` deriving all five tables; replace the 30-branch ladder | architect | M | sonnet |
| 4.4 | Shared scenario runner + config-hash result cache (~20 reimplementations) | architect | M | opus |
| 4.5 | Delete dead SaaS/auth surface; keep `_require()` with enforced vocabulary | architect | M | sonnet |
| 4.6 | Retire the decorative 14-stage projection pipeline | architect | M | sonnet |
| 4.7 | Delete `engine_config_loader.py`; add a field-set guard test for `planning_workbench.py` | architect | S | haiku |
| 4.8 | Move `data_io`'s discovery pass into `report_compute.py` (parsing must not call the engine) | architect | M | opus |
| 4.9 | Server-layer star-imports → explicit lists, starting `security_audit.py:309` | architect | L | sonnet |
| 4.10 | Split `sheets_summary.py` one-module-per-sheet (rebases on Wave 0 — §3.4) | architect | L | sonnet |
| 4.11 | `_sync_config_backends()` → DB→CSV export only (the actual Phase 2 goal) | architect | M | opus |

### Wave 5 — New planner capability

| # | Item | Expert | Effort | Model |
|---|---|---|---|---|
| 5.1 | Sustainable-spending solve — bisect to a target success rate, 3 levels | planner | M | opus |
| 5.2 | Named withdrawal-sequencing strategies + comparison sheet | planner | L | opus |
| 5.3 | Life-insurance capital-needs from the survivor projection (fix double-count now) | planner | M | opus |
| 5.4 | Current-vs-proposed comparison report | planner | L | opus |
| 5.5 | Essential/discretionary spending split with a floor | planner | L | opus |
| 5.6 | LTC: state-adjusted costs, surviving-spouse scenario, modeled funding | planner | M | opus |

> 5.1 is the planner's top feature call: *"the most common client question"* — and the binary search to
> answer it **already exists** at `planning_engines.py:2994-3013`, currently captioned "diagnostic only."

### Wave 6 — UI restructure · after Wave 2

| # | Item | Expert | Effort | Model |
|---|---|---|---|---|
| 6.1 | Narrow-window layout — reuse the mobile drawer up to 1180px | usability | M | sonnet |
| 6.2 | Spending domain → tabbed workspace (mirrors Distribution Strategy) | usability | L | sonnet |
| 6.3 | Pinned+collapsible column groups for transaction/lot tables | usability | M | sonnet |
| 6.4 | `dashboard.js` → ES modules, leaves inward (§3.2) | architect | XL | opus |

---

## 5. If you only do five things

1. **Wave 0.1** — the Executive Summary's Roth headline contradicts Sheet 11 and its recommendation
   block prints another household's dollar figures. Two experts, independently, rated this critical.
   It is on page 1 of what you hand a client.
2. **Wave 1.6** — effective marginal rate. Smallest change with the largest planning consequence in the
   review; the tool currently tells a household in the SS torpedo that they're in the 12% bracket.
3. **Wave 2.1** — Playwright. A silently broken Save button ships today with a green suite.
4. **Wave 3.1 + 3.3** — estate-exemption indexation and the one-line objective deflator. Both are small,
   both currently bias every conversion recommendation.
5. **Wave 1.1** — the Plan Forms API has returned 403 since it was written and the only test asserts the
   route *string* exists. Fix it, and add the AST test that would have caught it.

---

## Appendix A — All 45 findings

<details>
<summary><b>Architect (13)</b> — <i>"much of the decomposition work is nominal rather than real"</i></summary>

| ID | Impact | Effort | Recommendation |
|---|---|---|---|
| `plan-forms-api-permanently-403` | high | S | `write_config` + AST test over every `_require()` literal |
| `csv-roundtrip-on-every-save` | high | M | Memoize now; DB→CSV export as follow-up |
| `results-explorer-reparses-per-request` | high | S | mtime+size keyed cache |
| `planning-engines-is-eight-concatenated-files` | high | L | Alias removal now; explicit imports before any split |
| `reporting-facade-theater` | high | L | One module per sheet; delete `sheets_projection.py` today |
| `sheet-identity-scattered-across-five-tables` | medium | M | Consistency test first, then `SHEET_REGISTRY` |
| `no-shared-scenario-runner` | medium | M | Shared runner keyed on post-override config hash |
| `server-namespace-by-star-import` | medium | L | Explicit lists, smallest surface first |
| `dead-saas-and-auth-surface` | medium | M | Delete auth machinery; keep `_require()` |
| `projection-pipeline-is-decorative` | medium | M | Retire the 14-stage facade |
| `orphaned-migration-scaffolding` | medium | S | Delete `engine_config_loader.py`; guard-test the workbench |
| `data-io-calls-the-engine` | medium | M | Move discovery into `report_compute.py` |
| `frontend-single-global-namespace` | medium | XL | Size ratchet now; ES modules from the leaves |

</details>

<details>
<summary><b>Financial planner (13)</b> — <i>"the tax and estate plumbing is better than most commercial software"</i></summary>

| ID | Impact | Effort | Recommendation |
|---|---|---|---|
| `engine-single-return-all-accounts` | **critical** | L | Sleeve-level returns; disclose immediately |
| `reporting-nominal-dollars-only` | **critical** | M | Dual-column + consistent objective deflator |
| `mortality-gaussian-not-life-table` | **critical** | M | Real SSA/SOA table + age-conditional display |
| `exec-summary-hardcoded-recommendations` | **critical** | M | Compute or omit; demote the block meanwhile |
| `no-sustainable-spending-solve` | high | M | Three success targets via the existing bisection |
| `no-medical-expense-deduction` | high | M | §213 with the 7.5% AGI floor |
| `life-insurance-rules-of-thumb` | high | M | Capital-needs from the survivor projection |
| `withdrawal-sequencing-not-comparable` | high | L | Named strategies, not free reordering |
| `marginal-rate-statutory-only` | high | S | Numerically differentiated effective rate |
| `estate-tax-engine-il-only-unindexed` | high | M | Index federal; gate state on residence |
| `no-dynamic-spending-policy` | medium | L | Essential/discretionary split with a floor |
| `ltc-scenarios-fixed-and-incomplete` | medium | M | State-adjusted, surviving-spouse, modeled funding |
| `no-current-vs-proposed-deliverable` | medium | L | Comparison report + snapshot diff |

</details>

<details>
<summary><b>Quality (8)</b> — <i>"a strong three-tier golden-master core; the problems are elsewhere"</i></summary>

| ID | Impact | Effort | Recommendation |
|---|---|---|---|
| `no-browser-execution-testing` | **critical** | XL | Playwright over 2–3 journeys |
| `source-text-grep-implementation-pinning` | high | XL | Ban new ones; retriage highest-churn clusters |
| `target-test-pyramid-and-consolidation-plan` | high | L | Five tiers via markers, not a directory reorg |
| `admin-nav-churn-cluster` | medium | M | Keep test_24+25, delete the superseded five |
| `buried-tax-math-unit-tests` | medium | S | Extract `test_core_tax_math.py` |
| `executive-summary-sheet-untested-by-name` | medium | M | Audit indirect coverage before adding tests |
| `golden-master-live-plan-duplication` | medium | S | Delete `Phase5GoldenMasterEngineTests` |
| `duplicate-admin-click-handler-test` | low | S | Delete the older copy |

</details>

<details>
<summary><b>Documentation (6)</b> — <i>"unusually well-crafted for a novice audience; defects are concentrated in high-traffic spots"</i></summary>

| ID | Impact | Effort | Recommendation |
|---|---|---|---|
| `exec-summary-hardcoded-cst-figures` | **critical** | S | Shared helper — never two copies |
| `raw-status-enum-leak` | high | S | `status_label` in `governance.py` |
| `allocation-mode-jargon-dropdown` | high | S | Reword labels **and** rewrite FIELD_HELP |
| `triple-glossary-drift` | medium | S | Fold banners-only terms in, delete the third copy |
| `unlabeled-flat-rate-roth-headline` | medium | S | Label now, compute later |
| `pdf-silent-cell-truncation` | low | S | Distinct marker + cover-page notice |

</details>

<details>
<summary><b>Usability (5)</b> — <i>"real investment in progressive disclosure, applied inconsistently"</i></summary>

| ID | Impact | Effort | Recommendation |
|---|---|---|---|
| `ui-narrow-window-off-fold` | high | M | Reuse the mobile drawer up to 1180px |
| `ui-accordion-breaks-jump-to-field` | high | S | Generic `revealAndFocus()` helper |
| `ui-spending-domain-fragmentation` | medium | L | Tabbed workspace, mirroring Distribution Strategy |
| `ui-inconsistent-wide-table-pattern` | medium | M | Apply the pinned+collapsible pattern |
| `ui-mixed-autosave-model-no-signal` | low | S | Per-step save-model badge |

</details>

---

## Appendix B — Cross-check results

28 findings (all critical/high/large) received an adversarial verifier instructed to **refute** them.
**0 were refuted.** Four returned line-number corrections that leave the substance intact:

| Finding | Correction |
|---|---|
| `no-sustainable-spending-solve` | `spend_base` inflation is `deterministic_engine.py:1005-1010`, not 1029-1035 |
| `no-dynamic-spending-policy` | Freeze-year check is `deterministic_engine.py:1004-1008`, not 1029-1035 |
| `results-explorer-reparses-per-request` | `report_service.py` lives under `src/server_services/` |
| `raw-status-enum-leak` | `dashboard.js:11270` is the tax-law-constants status, not `advisor_readiness` — supports the pattern, not the same value. Core claim confirmed by the two workbook sites. |

**Caveat worth recording:** a 0/28 refutation rate is high enough to warrant scepticism about verifier
adversariality. Findings whose remediation is expensive — C3 (sleeve returns) and C4 (mortality
tables) — are the ones where an independent second look would be worth its cost before committing.

> ✅ **That second look was performed (§2.5) and the caveat was justified.** C3's effort dropped
> (L → M) because four prerequisites the panel assumed were missing already exist; C4's rose
> (M → L) because the panel **missed a second mortality sampler** — the vectorized one that produces
> the headline success rate. Neither the original expert nor its adversarial verifier caught it.
> Treat the remaining un-re-assessed critical findings accordingly (§6, remaining question 1).

---

## 6. Decisions on the open questions

All five were decided on 2026-08-04. Recorded here because each changed the plan.

| # | Question | Decision | Effect on the plan |
|---|---|---|---|
| **Q1** | When to re-run the missing planner sign-off? | **After Wave 3**, not before | Added as **3.8**. Wave 3 proceeds on the orchestrator's sequencing; the planner reviews the engine changes *and* this document once the numbers have actually moved — a more informative review than signing off on a forecast. Accepts the risk that sign-off could invalidate Wave 3 work already done. |
| **Q2** | Suppress Sheet 24 until the engine can back it? | **No — keep it**, ship the disclosure | 0.7 confirmed as an interim, explicitly retired by 3.5. Justified by 3.5 now being **M rather than L** (§2.5) — the window during which the sheet is disclosed-but-unbacked is days, not weeks. |
| **Q3** | Real-terms default vs. dual column? | **Dual column** | 3.4 confirmed. Preserves the nominal anchor for users reconciling against statements. |
| **Q4** | Calibrate effort to actual throughput? | **Yes** | §4.0 added: measured ~89 commits/week, solo + AI, median 3 files/commit. All waves now carry day estimates. |
| **Q5** | Golden-master regeneration timing? | **Regenerate *before* Wave 3, and again after** | Added **3.0**. The pending `_mode` regen clears first so Wave 3's six engine changes diff against a clean baseline and stay individually attributable. |

### Remaining open questions

1. **Verifier adversariality is still unquantified.** The C3/C4 re-assessment (§2.5) found a real
   error the panel missed — a second mortality sampler — which suggests the 0/28 refutation rate does
   reflect insufficiently adversarial verification rather than airtight findings. The other four
   critical findings (C1, C2, C5, C6) have **not** had an equivalent source-level second look. C5's
   one-line objective fix is low-risk; **C6 (Playwright, XL) is the one worth re-assessing before
   committing**, on the same grounds C3/C4 were.
2. **Wave 5 has no sequencing rationale yet.** Its six items were ordered by the planner's own
   priority, not by dependency. 5.1 (sustainable spending) and 5.5 (essential/discretionary split)
   plausibly share machinery; that was not analyzed.
3. **`XL` items have no decomposition.** 2.1, 4.x, and 6.4 are estimated at 2+ weeks with no
   breakdown. They should each get their own planning pass before entering a wave.

---

## Appendix D — Method

- **Recon** (haiku ×3, parallel): engine, UI, tests+docs — so the five experts did not each re-derive
  the same layout.
- **Expert review** (×5, parallel, structured output): every finding required `file:line` evidence from
  files the agent actually opened, 2–3 real options with tradeoffs, and a recommendation.
- **Cross-check** (sonnet ×28, pipelined per-expert): each critical/high/large finding got a verifier
  instructed to refute it. Refuted findings would have moved to an appendix rather than vanishing.
- **Synthesis:** ❌ workflow stage failed — reconstructed by the main orchestrator from `journal.jsonl`.
- **Planner sign-off:** ❌ not performed. See Appendix C.
- **Constraints:** read-only; no source edits; no commits. **The test suite was never executed** —
  some tests overwrite files under `input/`. Experts read tests rather than running them.

**Cost:** 39 agents · 36 completed · 2,491,536 subagent tokens · 627 tool uses · 18m32s wall clock.

**Raw agent output:** `…/subagents/workflows/wf_e2a38b46-904/journal.jsonl`
**To resume the failed stages after the limit resets:**

```bash
echo 'Workflow({scriptPath: ".../system-review-wf_e2a38b46-904.js", resumeFromRunId: "wf_e2a38b46-904"})'
```
