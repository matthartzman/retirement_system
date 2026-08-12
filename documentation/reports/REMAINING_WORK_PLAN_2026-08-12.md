# Remaining Work Plan — 2026-08-12

**Basis:** progress audit of `documentation/reports/SYSTEM_REVIEW_2026-08-04.md` against the repo at
`origin/main` (`a2693ea`), plus a live fast-tier test run and CI history.

**Status: F0.1 and F0.2 are DONE (branch `fix/frozen-golden-master-gate`). Everything else is
proposed and unexecuted.**

**Scope decision (2026-08-12):** the 141-function singleton tail is **out of scope for this cycle** —
F3.5 is deferred, F3 stops after the four real clusters. See §4/F3.

---

## 1. Progress audit — where the 2026-08-04 review actually stands

141 commits landed between 2026-08-04 and today. The review's waves are **almost entirely done**.

| Wave | Items | Status |
|---|---|---|
| 0 — Deliverable truthfulness | 0.1–0.7 | ✅ complete (verified in review §7.2) |
| 1 — Cheap high-value fixes | 1.1–1.10 | ✅ complete |
| 2 — Test infrastructure | 2.1–2.5 | ✅ complete (Playwright, ratchet, markers, lint gate) |
| 3 — Engine correctness | 3.0–3.7 | ✅ landed — **3.5 only half-landed, see F1**; 3.8 not done |
| 4 — Architecture debt | 4.1–4.10 | ✅ complete; **4.11 reverted and closed won't-fix** (`7d1ca0f`, `511cb35`) |
| 5 — New planner capability | 5.1–5.6 | ✅ complete (Sheets 15/37, sustainable-spending solve, LTC, life insurance) |
| 6 — UI restructure | 6.1–6.3 | ✅ complete |
| 6.4 — `dashboard.js` split | in progress | 🟡 **~35% done — the main open workstream** |

### What is genuinely left

Four things, in descending order of how much they cost you if ignored:

1. **The mandatory golden-master gate is not trustworthy.** (§2, F0)
2. **`dashboard.js` domain split is 35% through a ~12-cluster job** whose per-pass cost is dominated by
   test breakage, not by the extraction. (§4)
3. **Wave 3.5 (C3, per-account returns) never reached the Monte Carlo path** — the headline success
   rate still uses one return for every account, which is the exact defect the finding named. (F1)
4. **At-rest plan-data migration Phase 2/3** from `docs/superpowers/plans/2026-08-10-…-migration.md`
   never started (version gate + `wellness → healthcare`). (F5)

---

## 2. RESOLVED — the frozen gate was measuring the machine, not the fixture

> **Executed 2026-08-12 on branch `fix/frozen-golden-master-gate`. This section records the outcome;
> the original statement of the symptom follows in §2.1.**

**Root cause.** `src/data_io.py:1033` (`parse_client`) passed the spending-budget resolver an explicit
`root=Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))` — the repo root, computed
from `__file__`. Everything reached through that root ignored `RETIREMENT_SYSTEM_WORKSPACE_ROOT`, so
`client_spending_budget.csv`, `client_spending_taxonomy.csv`, and `client_optional_functions.csv` were
always read from the repo's `input/`. The frozen fixture ships its own copies of all three; they were
never read. It is the **same landmine class** the test file's docstring describes as fixed — it was
removed for holdings/liabilities and left in place here.

**Why the two environments disagreed.** `/input/*` is gitignored, so that directory's contents are a
property of the *checkout*, not the commit:

| Environment | What the resolver found | Terminal NW |
|---|---|---|
| Fresh checkout / worktree / CI | nothing → legacy fallback values | 6,044,750.40 |
| A warm working copy | the developer's **live** plan | 5,824,239.30 |

Neither reading involves the fixture. Confirmed by running `a2693ea` in both a warm working copy and
a clean worktree, and by an audit-hook trace of every file opened during the frozen build.

**This overturns the 2026-08-10 conclusion** recorded in the changelog and in project memory (*"the pin
never matched; verified by bisect and per-commit measurement across two interpreters and CI"*). That
analysis was internally sound — but every measurement it cites was taken in a fresh-checkout
environment, so all of them measured the same fallback path. The agreement proved a shared
environment, not a correct pin. **Bisect cannot see a defect that is constant across all commits**, and
it was applied to a question ("which commit moved it?") that presupposed a commit had.

**What was done (F0.1 + F0.2):**
- `src/data_io.py` — dropped the hardcoded `root=`. With no env var set, resolution is byte-identical
  to the old behavior in both source and frozen mode (`workspace_root()` → `package_root()` →
  `parents[1]`), so normal desktop/server runs are unchanged. **This is a production fix, not a test
  fix**: any run under a custom workspace root — the e2e server, a multi-workspace build — was
  resolving spending against the wrong directory.
- Pins re-generated to **5,824,239.30 / 1,290,848.91**, now identical in a warm working copy *and* a
  clean worktree — the first pin this gate has carried that describes the fixture.
- New guardrail `test_frozen_build_reads_its_own_spending_budget_not_the_live_one`, verified red
  before the fix and green after, in both environments. The existing holdings guardrail structurally
  could not catch this: it only covers files resolved through `candidate_input_files`, and the
  spending budget does not go through that path.
- `GOLDEN_MASTER_CHANGELOG.md` entry superseding the 2026-08-10 one.

**Follow-ups this surfaced (not executed — F0.3/F0.4 were out of the requested scope):**
- `tests/test_repo_hygiene_guards.py::test_no_tracked_file_is_gitignored` fails on
  `.claude/settings.local.json`. Pre-existing on `origin/main`, unrelated to this work — the file has
  been force-added since `73378f5`, and the guard that flags it landed yesterday in `3363f73`.
- **The wider class is unaudited.** This was the second hardcoded-`root=` escape found in the same
  codebase. A repo-wide sweep for `root=`/`__file__`-derived path bases that bypass `workspace_root()`
  is worth one focused pass (**sonnet · low effort**), since each one is invisible until an
  environment differs.

### 2.1 Original symptom (as first observed)

Measured today, `main` @ `78a7eb2` (and `origin/main` — **no engine file differs between them**):

```
tests/test_frozen_sample_plan_golden_master_regression.py
  terminal NW computes 5,824,239.30, pinned 6,044,750.40   (-$220,511.10)
```

Reproduced identically under **Python 3.12 and 3.14** locally. Meanwhile CI job
`test (windows-latest, 3.14)` reported **success** on run `31555649612`, at a commit with the same
pins and the same engine. The test has no skip guard and CI runs `pytest tests/` unfiltered.

So one of these is true, and both are serious:

- the "hermetic" frozen fixture is **still reading something from the local machine** — the prime
  suspect is `local_state/retirement_system_v10.db`, which became the canonical plan-data read path
  in the DB-canonical switch and is absent on a CI runner (the docstring's documented landmine was
  about `input/`, and it was fixed for `input/` only); or
- the value legitimately moved by −$220.5k when the withdrawal gross/net fix landed (`91ab5fe`,
  `7a263e6`) and the pin was never updated, with CI green for an unrelated environmental reason.

Either way the project's **only mandatory dollar-exact gate currently proves nothing**, and every
number-moving item below (F1 especially) is unattributable until it is fixed. This is the single
prerequisite for the rest of the plan.

Note this also contradicts the standing memory note (*"the pin never matched, corrected 2026-08-10"*)
— that conclusion was right on 08-10 and has been overtaken by the withdrawal-semantics commits.

---

## 3. Strategy — what this plan optimizes for

Your constraints were: **minimize rework, testing cost, and tokens.** Four rules follow, and they
drive every assignment in §4.

**R1 — Buy the test-repointing tool before doing the bulk work.**
Measured on the spending-taxonomy pass: extraction is cheap, the *test-breakage fix loop* is the cost
(~10 source-text tests break per cluster, each needing a fix-verify cycle). 27 test files still
`read_text()` `dashboard.js` directly. Repointing all of them **once**, plus a guard test that blocks
new ones, converts ~10×9 remaining fix cycles into ~0. This is the highest-ROI item in the plan and it
is mechanical.

**R2 — Batch extractions 3–4 deep, one full-suite run per batch.**
The full suite is the only reliable detector (targeted greps found breakage in three waves and cost
three cycles where one would do). Batching amortizes it. After R1 lands, batching is safe because the
breakage class it detects has mostly been eliminated.

**R3 — One batch per *fresh session*, never two in one.**
Context is resent every turn, so in-session cost grows quadratically. This dominates model choice:
a Sonnet session that runs long is more expensive than an Opus session that stays short.

**R4 — Serialize anything that rewrites `dashboard.js`; parallelize only across disjoint file sets.**
Two worktrees both extracting clusters will conflict irreconcilably (both rewrite the same 12k-line
file and the same manifest/ratchet/census artifacts). Engine work and split work *can* run in parallel
worktrees — they share only `tests/`, and even there they touch disjoint files.

Standing hygiene for every task: `RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS=1`, capture pytest
output to a **file** (a truncated tail hides FAILED lines), and `git status` on `input/` after any
broad run (the suite mutates tracked plan files).

---

## 4. The plan

Phases are dependency-ordered. Items inside a phase are parallel-safe unless noted.

### Phase F0 — Restore the baseline · blocks everything that moves a number

| # | Item | Effort | Model · reasoning effort | Worktree |
|---|---|---|---|---|
| ✅ F0.1 | Root-cause the local-red / CI-green split | M · ½ day actual | **opus · high** | branch |
| ✅ F0.2 | Fix + re-pin + guardrail test + changelog | S · ½ day actual | **opus · high** | branch |
| F0.3 | Add a CI assertion that the frozen gate **executed** rather than merely reporting success. §2 was a gate that passed while proving nothing; a green tick is not evidence a test ran. | S | sonnet · medium | main |
| F0.4 | Confirm CI e2e is green after `b9fc8c1`; if not, fix the remaining flake class. Run `31590099383` was in flight during this audit. | S | sonnet · medium | main |
| F0.5 | Repo-wide sweep for other `__file__`-derived path bases that bypass `workspace_root()` (§2 follow-ups) | S | sonnet · low | main |

> **Why opus·high on F0.1 was the right call, in hindsight.** Four hypotheses were wrong before the
> right one landed (DB bleed, `input/` bleed, an engine commit, a Python-version split), and the
> prior written record — the changelog and project memory — actively pointed the wrong way. The
> decisive step was refusing to accept "bisect says X" from a previous session and re-measuring the
> good endpoint in a clean worktree. A cheaper model following the recorded conclusion would have
> re-pinned to 6,044,750.40 and shipped the bug back.

> Do **not** start F1 or F5 before F0.2 lands. Both move client numbers and neither is attributable
> against a gate that disagrees with itself.

### Phase F1 — Finish C3 (per-account returns in Monte Carlo) · the one incomplete engine item

Wave 3.5 (`cc20738`) populated `c['account_returns']` from real holdings — but only for the
deterministic path. `planning_engines.py:51-52` still gives `return_by_year[year]` precedence, so in
Monte Carlo **every account still grows at one identical rate**, and MC collapses the correlated
multivariate draw with a single weight vector (`base_draws = raw.dot(wv)`, `:2871`). The headline
success rate — the number the Social Security sweep, survivor stress, and LTC conclusions rank on —
is unchanged by Wave 3.5. This is the exact failure mode §2.5 of the review warned about: *a change
that looks done because the thing you inspected changed.*

| # | Item | Effort | Model · reasoning effort | Worktree |
|---|---|---|---|---|
| F1.1 | Replace the MC weight **vector** with a weight **matrix** (`raw.dot(W)`, `W` = n_classes × n_sleeves) and route each account to its sleeve column; make `_account_return` prefer the per-account sleeve path over `return_by_year`. | M · 1–2 days | **opus · high** — moves every client dollar and the headline success rate | `wt/engine-c3-mc` |
| F1.2 | Acceptance test that fails on the *old* behavior: assert MC per-account terminal balances **diverge** across sleeves for a fixture with a cash reserve + a growth Roth. Name both paths explicitly, as 3.6's criterion did. | S | opus · high — the test is the deliverable; a weak one re-creates the half-fix | same |
| F1.3 | Golden-master regeneration + changelog entry. | S | opus · medium | same |
| F1.4 | Retire the Sheet 24 asset-location interim disclosure (Wave 0.7 was explicitly scoped as retired by 3.5). | S | sonnet · low | same |

### Phase F2 — Tooling before bulk split work · unlocks Phase F3's economics

| # | Item | Effort | Model · reasoning effort | Worktree |
|---|---|---|---|---|
| F2.1 | **Sweep all 27 test files that raw-read `dashboard.js` onto `tests/_decomp_dashboard.dashboard_js_text()`.** Mechanical, one pass, one full-suite verification. | M · 1 day | **sonnet · low** — a known edit repeated 27×; effort buys nothing | `wt/js-split` |
| F2.2 | Guard test: any test file reading `frontend/js/dashboard.js` directly fails, with the fix named in the message. Prune the now-inert entries from `tests/fixtures/frontend_source_grep_baseline.json` (82 entries today). | S | sonnet · medium — the allowed-exceptions list needs judgement | same |
| F2.3 | `extract_batch.mjs` — drives N clusters through `extract_module` + `finish_extraction` in one invocation, then prints one consolidated report. Refuses to proceed if any per-cluster verification fails, so a bad cluster can't hide inside a batch. | S/M | sonnet · medium | same |
| ~~F2.4~~ | ~~Nav-step affinity grouping for the singleton tail~~ — **dropped with F3.5** (§scope decision). Re-open only if the tail is revived. | — | — | — |

> F2.1+F2.2 are the R1 investment. Estimated payback: ~9 remaining passes × ~10 broken tests ×
> a fix-verify cycle each, collapsed to one sweep.

### Phase F3 — Complete the `dashboard.js` domain split · serial, one batch per fresh session

State at `origin/main`: `dashboard.js` is **12,304 lines** (from 19,661), 460 functions,
184 components, 4 clusters extracted. Remaining shape: four real clusters, five small ones, and a
141-function singleton tail.

| Batch | Contents | Effort | Model · reasoning effort | Session |
|---|---|---|---|---|
| F3.1 | Small clusters 3–7: recommendations/jump (14), income streams (11), large-discretionary (9), death-benefits/illustrations (9), MC/stress options (8) — disjoint domains, batch all five | M | sonnet · medium (opus · medium for cluster pick + error triage) | one |
| F3.2 | Cluster 2 — checklist / closeout / save-load (33) | M | sonnet · medium | one |
| F3.3 | Cluster 1 — allocation / optimizer (56). Highest cross-talk with engine-facing UI; verify the optimizer panel live. | L | **opus · medium** — mechanically routine, but the blast radius is wide | one |
| F3.4 | Cluster 0 — YTD tracking + plan-folder I/O (80). Largest, and it owns file-system/permission flows Playwright covers only partly. **Do last.** | L | **opus · high** — file-system and permission flows are the least test-covered surface in the app | one |
| ~~F3.5~~ | ~~Singleton tail (141 functions) → themed modules~~ — **DEFERRED, 2026-08-12 scope decision.** Worst effort-to-benefit ratio in the plan; `dashboard.js` lands at ~7–8k lines instead of ~4k, at roughly half the sessions. | — | — | — |
| F3.6 | Close-out: lower the ratchet to final, update `phase3_module_manifest.js`, record the split as stopping at the four-cluster line (not "complete") against the Wave 6.4 scope doc | S | haiku · low | — |

Per batch, unchanged from the established recipe: re-run `find_clusters.mjs` first (every extraction
changes the graph) → `extract_module --check` → real → `finish_extraction` → **full suite immediately**
→ live browser check of the affected panels. Model split within a batch: **opus picks the cluster and
triages any newly-surfaced runtime error** (calling a function for the first time can expose latent
bugs that were never reachable); **sonnet does the mechanical passes**.

Target with F3.5 deferred: `dashboard.js` at **~7,000–8,000 lines** — the four real clusters out, the
141-function singleton tail left in place alongside boot, `STEPS`, `renderMain` dispatch, and shared
state. Down from 19,661 at the review, 12,304 today. The size ratchet keeps that from regressing, so
stopping here is a stable resting point rather than an abandoned migration — say so in F3.6's
manifest note, so a future reader doesn't mistake the tail for work that was forgotten.

### Phase F4 — Sign-off and review close-out

| # | Item | Effort | Model · reasoning effort | Worktree |
|---|---|---|---|---|
| F4.1 | Wave 3.8 — re-run the workflow's **automated** planner sign-off against the finished engine work. The 2026-08-05 sign-off was a manual stand-in taken under a session-limit block, and it predates F1. | S | opus · high — it is a review, and its whole value is catching what the last one missed | main |
| F4.2 | Close the review's three remaining open questions in writing: verifier adversariality (C1/C2/C5 never got a second look), Wave 5 sequencing (moot — all shipped), XL decomposition (moot — 2.1/4.x/6.4 all decomposed in practice). | S | sonnet · medium | main |
| F4.3 | **New:** re-open the verifier-adversariality question with §2 as evidence. A 0/28 refutation rate has now produced two misses — the second mortality sampler (§2.5 of the review) and the pin analysis this plan overturned. Both were *confirmations of a prior conclusion* rather than independent re-derivations. Worth one written rule: a verifier that agrees with the record has not verified anything. | S | opus · high | main |

### Phase F5 — At-rest plan-data migration · independent, parallel-safe

Resumes `docs/superpowers/plans/2026-08-10-golden-master-and-at-rest-plan-data-migration.md`
(Phase 1 done; Phases 2–3 untouched — `PLAN_DATA_SCHEMA_VERSION = 2` still has **no consumer**).

| # | Item | Effort | Model · reasoning effort | Worktree |
|---|---|---|---|---|
| F5.1 | Phase 2: `get_local_setting`/`set_local_setting`, version gate, `migrate_plan_data_at_rest()` runner, called once at startup | M · 1–2 days | sonnet · medium — the plan doc already specifies it task-by-task | `wt/at-rest-migration` |
| F5.2 | Phase 3: `wellness → healthcare` **data-at-rest labels only** — scope the three namespaces separately (MC shock params, `pre65_wellness_premium`, prose). No Python identifier renames. | L · 3–5 days | **opus · high** for scoping (~140 occurrences, three namespaces, a one-way rewrite of user data) → **sonnet · low** to execute the agreed list | same |

---

## 5. Sequencing, worktrees, and cost

```
F0 ──┬─> F1 (engine)          worktree wt/engine-c3-mc      ← golden-master owner
     ├─> F2 ──> F3 (js split) worktree wt/js-split          ← dashboard.js owner
     └─> F5 (migration)       worktree wt/at-rest-migration  ← plan-data owner
                              F4 after F1
```

Three worktrees may run concurrently **after F0** because each owns a disjoint blast radius: the
engine + golden fixtures, `frontend/js/` + frontend tests, and `src/plan_data_migration.py` + plan
CSVs. Nothing outside its own lane is edited. Do **not** open a second worktree inside the split lane.

⚠ Known trap: a worktree running the app still writes `local_state/retirement_system_v10.db` in the
**main** repo. Any live browser verification in the split lane touches the same DB the engine lane's
golden master may be reading — F0.1 may prove that matters. Until F0.2 lands, do not run the app from
a worktree while an engine-lane test run is in flight.

**Model and reasoning-effort policy.** Model and effort are separate dials and this plan sets them
separately — most of the wasted spend in a project like this comes from running a strong model at high
effort on work that is fully specified, or a cheap one on work where being wrong is expensive.

| | Use | Items |
|---|---|---|
| **opus · high** | The answer is not known and the prior record may be wrong. Diagnosis, adversarial review, one-way data rewrites. | F0.1, F0.2, F1.1, F1.2, F3.4, F4.1, F4.3, F5.2 (scoping) |
| **opus · medium** | The path is known but the blast radius is wide — judgement is about consequences, not discovery. | F1.3, F3.3, cluster selection and error triage inside every F3 batch |
| **sonnet · medium** | Specified work with local judgement calls (which exceptions to allow, how to split a stage). | F0.3, F0.4, F2.2, F2.3, F3.1, F3.2, F4.2, F5.1 |
| **sonnet · low** | The edit is known and repeated; reasoning adds tokens, not correctness. | F2.1, F1.4, F0.5, F5.2 (execution) |
| **haiku · low** | Bookkeeping with a verifiable output. | F3.6 |

Three rules that matter more than the table:

1. **Never let a cheap tier close a question the record already answered.** F0.1's whole value was
   re-measuring something two prior sessions had recorded as settled. Any item whose job is to
   *re-check* something gets opus · high regardless of how small the diff turns out to be.
2. **Effort down, not model down, when work is specified.** A sonnet · low pass over a written task
   list is cheaper *and* more predictable than opus · low, and far cheaper than sonnet · high.
3. **Session length beats both dials** (R3). A single batch held to one fresh session dominates any
   model choice made inside it.

**Rough calendar:** ~~F0 ~1.5 days~~ (done in ~1) · F1 ~2–3 days · F2 ~1.5 days · F3 **~4 sessions
across ~1 week** (was 6–8 across 2 weeks, before F3.5 was deferred) · F4 ~1 day · F5 ~5–7 days.
Split and migration lanes overlap, so **~2 weeks** wall clock if run in parallel, ~3.5 weeks serial.

**Token policy:** one batch per session and a hard stop at the batch boundary is worth more than any
model downgrade — R3 dominates. Second-biggest lever is F2.1, which removes the multi-round
fix-verify loops that currently make each split session long.

---

## 6. Open decisions

1. ~~F0.1's outcome changes F1's cost.~~ **Resolved** — it was a hardcoded `root=`, not a DB bleed
   (§2). F1's cost estimate stands, and it now runs against a baseline that means something.
2. ~~F3's end target.~~ **Decided 2026-08-12: stop after the four real clusters, defer the 141
   singletons.** F3.5 and F2.4 struck.
3. **Whether F5 runs at all this cycle.** Still open. It is real debt but nothing user-visible is
   blocked on it; the most deferrable phase here.
4. **New — how far to chase the `root=` class (F0.5).** §2 was the second instance found. One sweep
   would close it; skipping it accepts that the next one also surfaces only when an environment
   differs, which is the most expensive way to find this bug.

---

## 7. Execution log

**2026-08-12 — F0.1 + F0.2, branch `fix/frozen-golden-master-gate`** (opus · high)

Changed: `src/data_io.py` (one line), `tests/test_frozen_sample_plan_golden_master_regression.py`
(re-pin + provenance + new guardrail + `withhold=` parameter on `_frozen_config`),
`documentation/GOLDEN_MASTER_CHANGELOG.md` (superseding entry).

Verification: frozen file 3/3 green; guardrail confirmed red before the fix and green after, in both
a warm working copy and a clean worktree at `a2693ea`; fast tier green apart from the pre-existing,
unrelated `.claude/settings.local.json` hygiene failure; full suite run under `-n auto`.

Method note worth keeping: the first four hypotheses were wrong, and the written record pointed at
the wrong one. What broke it open was an **audit-hook trace of every file the "hermetic" build
opened** — cheaper than any amount of reading, and it named the offending path in one run. Reach for
that earlier next time a test's answer depends on the machine.
