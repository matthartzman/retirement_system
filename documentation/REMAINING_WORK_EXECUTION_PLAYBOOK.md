# Remaining Work Execution Playbook
**Status: F0-F2 Complete | F3/F4/F5 Ready to Execute**

Date: 2026-08-12
Plan Basis: `REMAINING_WORK_PLAN_2026-08-12.md`

---

## Executive Summary

Three phases remain, all unblocked:

| Phase | Type | Sessions | Effort | Notes |
|-------|------|----------|--------|-------|
| **F3** | Dashboard split (4 batches) | 4 fresh sessions | ~1 week | Serial within lane, one batch per session (R3) |
| **F4** | Engine sign-off | 1-2 sessions | ~1 day | After F1 (done); can start anytime |
| **F5** | At-rest migration | 1-3 sessions | ~5-7 days | Parallel-safe; independent |

**Parallelization:** F3, F4, F5 can run concurrently in separate worktrees. F3 batches are serial (each needs a fresh session).

---

## Phase F3: Dashboard Split (4 Batches)

**Status:** Tooling complete (F2.1-F2.3 done). Ready for cluster extraction.

### Current State
- `frontend/js/dashboard.js`: **11,447 lines**, 396 functions, 146 components
- **4 real clusters** ready for extraction (66 / 56 / 31 / 14 functions)
- **109-function singleton tail** deferred (out of scope per 2026-08-12 decision)

### F3 Execution: One Batch Per Fresh Session

#### **Batch F3.1** — Small Clusters 3–7
**Clusters:** recommendations/jump (14), income_streams (11), large_discretionary (9), death_benefits/illustrations (9), mc_stress (8)

```bash
# Fresh session 1: worktree wt/js-split

node tools/js_codemod/find_clusters.mjs
node tools/js_codemod/extract_batch.mjs \
  recommendations,income_streams,large_discretionary,death_benefits,mc_stress

# Verify
npm test 2>&1 | tee f3.1_test_output.log
# Live browser check: nav-integrity, field-save-persist, Results Explorer

# Commit + push
git add -A
git commit -m "F3.1: Extract 5 small clusters (recommendations, income streams, discretionary, death benefits, MC stress)"
```

**Expected:** dashboard.js ~10,300 lines after extraction. All tests green.

#### **Batch F3.2** — Cluster 2: Checklist/Closeout/Save-Load
**Cluster:** 31 functions

```bash
# Fresh session 2: same worktree wt/js-split

node tools/js_codemod/find_clusters.mjs
node tools/js_codemod/extract_batch.mjs checklist

# Verify
npm test 2>&1 | tee f3.2_test_output.log
# Live browser: save/load workflows

git add -A
git commit -m "F3.2: Extract cluster 2 (checklist, closeout, save-load)"
```

**Expected:** dashboard.js ~10,000 lines.

#### **Batch F3.3** — Cluster 1: Allocation/Optimizer
**Cluster:** 56 functions (highest cross-talk with engine UI)

```bash
# Fresh session 3: same worktree

node tools/js_codemod/find_clusters.mjs
node tools/js_codemod/extract_batch.mjs allocation_optimizer

# Verify (extra attention: live verify the optimizer panel works)
npm test 2>&1 | tee f3.3_test_output.log
# Live browser: allocation panel, optimizer recommendations

git add -A
git commit -m "F3.3: Extract cluster 1 (allocation, optimizer)"
```

**Expected:** dashboard.js ~9,600 lines. Optimizer panel renders correctly.

#### **Batch F3.4** — Cluster 0: YTD Tracking + Plan-Folder I/O
**Cluster:** 66 functions (largest; file-system/permission flows)

```bash
# Fresh session 4: same worktree

node tools/js_codemod/find_clusters.mjs
node tools/js_codemod/extract_batch.mjs ytd_tracker

# Full verification (this cluster is least test-covered)
npm test 2>&1 | tee f3.4_test_output.log
# Live browser: YTD fields, plan folder I/O (save plans, manage files)

git add -A
git commit -m "F3.4: Extract cluster 0 (YTD tracking, plan-folder I/O)"
```

**Expected:** dashboard.js ~6,000–7,000 lines. File-system operations work.

#### **Batch F3.6** — Close-Out
```bash
# After F3.4 landing:
# Lower ratchet, update manifest, document split as stopping at 4 clusters

git add tests/test_frontend_size_ratchet.py frontend/js/modules/phase3_module_manifest.js
git commit -m "F3.6: Lower ratchet, document dashboard split completion at 4-cluster line"
```

---

## Phase F4: Engine Sign-Off

**Status:** F1.1-F1.4 complete (per-account MC returns ready). Ready to verify.

### F4.1 — Re-run Automated Planner Sign-Off

```bash
# Main branch (or worktree wt/engine-c3-mc):
python -m pytest tests/test_recommendations_regression.py::PlanningSolveWave3Tests -xvs

# Check: success-rate outputs now show per-account MC divergence
# Compare pre/post F1.1 reports
```

**What to verify:**
- Terminal net worth unchanged (deterministic unchanged)
- Success rate reflects per-account returns (MC paths diverge by allocation)
- Sheet 24 asset-location interim disclosure removed

### F4.2 — Close Review's Open Questions

**Write up:** Three moot items from 2026-08-05 review:
1. Verifier adversariality (C1/C2/C5): Now addressed with §2 evidence
2. Wave 5 sequencing: All shipped
3. XL decomposition: Decomposed in practice (F2.1-F3.6 in flight)

**File:** `documentation/REVIEW_2026-08-05_CLOSEOUT.md`

### F4.3 — Verifier Adversariality Principle

**Write:** New rule based on §2 (frozen gate root-cause):
> "A verifier that agrees with the record has not verified anything."

The §2 analysis was internally sound but measured the same fallback path on every commit (visible only when environment changed). Document this principle and apply to all future verifications.

---

## Phase F5: At-Rest Plan-Data Migration

**Status:** Specification ready in `docs/superpowers/plans/2026-08-10-golden-master-and-at-rest-plan-data-migration.md`. Phase 1 done; Phases 2–3 untouched.

### Setup: Parallel Worktree
```bash
git worktree add wt/at-rest-migration origin/main
cd wt/at-rest-migration
```

### F5.1 — Phase 2: Version Gate + Migration Runner

**Implement:**
- `get_local_setting(key, default)` / `set_local_setting(key, value)`
- Version gate: `PLAN_DATA_SCHEMA_VERSION = 2` with consumer check
- `migrate_plan_data_at_rest()` runner, called once at startup

**Files to modify:**
- `src/local_plan_data_sync.py` (add migration runner)
- `src/local_state/` (add schema version tracking)

**Model:** sonnet · medium (spec'd task-by-task in migration doc)

### F5.2 — Phase 3: wellness → healthcare Data-At-Rest Relabeling

**Scope:** Three namespaces separately:
1. MC shock parameters (`mc_shock_wellness_*` → `mc_shock_healthcare_*`)
2. Pre-65 wellness premium (`pre65_wellness_premium` → `pre65_healthcare_premium`)
3. Prose (error messages, UI text)

**No Python identifier renames** — data-at-rest labels only.

**Effort:** 3–5 days
- **Opus · high** for scoping (~140 occurrences, three namespaces, one-way rewrite)
- **Sonnet · low** for execution of agreed list

---

## Dependency Graph & Sequencing

```
F0 (baseline)  ──┐
                 ├─→ F1 (engine)    ──→ F4 (sign-off)
                 ├─→ F2 (tooling)   ──→ F3 (split, 4 batches, serial)
                 └─→ F5 (migration, parallel-safe)

Worktrees:
  - wt/engine-c3-mc        (F1, F4 — golden-master owner)
  - wt/js-split            (F2, F3 — dashboard.js owner)
  - wt/at-rest-migration   (F5 — plan-data owner)

Note: F3.1-F3.4 are serial (each in a fresh session), but the three
worktrees can run in parallel.
```

---

## Hygiene & Environment

**For every session:**
```bash
export RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS=1
export RETIREMENT_SYSTEM_WORKSPACE_ROOT=...  # if testing in isolation

# Capture test output to file (truncated tail hides FAILED lines)
npm test 2>&1 | tee test_output.log

# After broad runs, check for mutations
git status input/
```

---

## Token & Session Policy (R3)

**One batch per fresh session, hard stop at batch boundary.**

- F3.1: ~30–40k tokens (extraction + full suite)
- F3.2: ~30–40k tokens
- F3.3: ~40–50k tokens (highest cross-talk)
- F3.4: ~50–60k tokens (largest cluster, file-system flows)

**Model choice within a batch:**
- Opus picks the cluster (cost: ~2–3k tokens) + triages runtime errors
- Sonnet does mechanical passes (cost: ~20–40k tokens per pass)

---

## Rollback & Recovery

**If a batch fails:**

1. **Before extraction:** Full suite passes, git is clean
2. **After extraction, before finish:** `git checkout frontend/js/dashboard.js` to revert
3. **After finish:** `git reset --hard` to undo all changes

**Before moving to the next batch:**
- All tests green (fast tier and full suite)
- `git status` shows no uncommitted changes
- `git log --oneline -5` shows clean commit history

---

## Next Steps (Recommended Order)

1. **Immediate:** Run full suite to confirm F0–F2 changes don't break anything
   ```bash
   npm test 2>&1 | tee baseline_verification.log
   ```

2. **Then:** Spin up three worktrees (or queue them)
   - F3.1 batch starts in wt/js-split
   - F4.1 starts (or queues) in wt/engine-c3-mc
   - F5.1 starts (or queues) in wt/at-rest-migration

3. **F3 batches:** Sequential, one per session. As each lands:
   - Run full suite
   - Commit + push
   - Start next batch in new session

4. **Consolidate:** Once all three lanes finish
   - Merge worktree branches → main
   - Run full suite one final time
   - Tag release / close wave

---

## Estimates

| Phase | Sessions | Estimated Time | Blocking |
|-------|----------|-----------------|----------|
| **F3** | 4 | 1 week | Each batch ~1–2 days, serial |
| **F4** | 1–2 | 1 day | After F1 (done); fast |
| **F5** | 1–3 | 5–7 days | Independent; can overlap F3 |
| **Total** | 6–9 | ~2 weeks (parallel) | None; all lanes clear |

---

## Contacts & Escalation

- **Questions on F3 cluster boundary decisions?** See `documentation/DASHBOARD_DECOMPOSITION_JOURNAL.md`
- **Questions on F4 verifier logic?** See `documentation/SYSTEM_REVIEW_2026-08-04.md` §2.5 / §C3
- **Questions on F5 migration spec?** See `docs/superpowers/plans/2026-08-10-golden-master-and-at-rest-plan-data-migration.md`

---

**End of Playbook**

Good luck! 🚀
