# Wave 4 Implementation Plan — Security & Financial-Domain Corrections

**Source:** `documentation/reports/SYSTEM_REVIEW_2026-09-07.md`, §9 Wave 4 (W4-1..W4-5). This document turns that table into an executable plan: exact files, exact changes, verification steps, sequencing, and per-item model/effort sizing.

**Scope:** SEC-1 (wildcard CORS), N1 (MC parity gate), N2 (SS claim-age month precision), SEC-2 (Monarch `source_dir` path validation), SEC-3 (build-backup credential exclusion). All five are independent — disjoint files, no shared state — confirmed by re-reading each site below.

---

## 1. Options

| Option | Description | Verdict |
|---|---|---|
| **A. One session, five sequential edits** | Work items in a single pass, smallest/safest first, run the fast test tier once at the end (full suite once before push). | **Recommended.** Zero coordination overhead, one context, no duplicated file reads across agents. |
| **B. Five parallel subagents (one per item)** | Spawn a Task per item. | Rejected. These are 1-3 line diffs in disjoint files with no research burden left (this doc already located every site) — parallel agents would each re-read files this plan already quotes, burning tokens for zero speed gain on such small edits. |
| **C. Full suite after every item** | Run `pytest tests/ -n auto` five times. | Rejected. Only W4-3 (SS claim age) and W4-2 (MC parity) touch code the full suite's golden-master/parity tests cover; W4-1/4/5 are config/security edits with narrow, targeted tests. Run targeted tests per item, fast tier once after all five, full suite once before push — matches the CLAUDE.md testing-discipline table and avoids 4 redundant ~large runs. |

**Recommendation: Option A**, in the order below (safest/no-golden-master-impact items first, so a mistake on a later item never forces re-verifying an earlier one).

**Model/effort sizing:** every item here is a located, narrow, mechanical-or-small-logic change with the fix already specified by the review — none require open-ended design work. Use **Sonnet at low-to-medium effort** for the edits themselves (this is implementation of an already-designed fix, not exploration). Reserve higher effort only for W4-2's diagnostic sub-task (Option 1 in the review, explicitly deferred here — see §2.2) if it's pulled forward. Do not use Opus for this wave; nothing here requires it.

---

## 2. Per-item design

### 2.1 W4-1 — Delete wildcard CORS (SEC-1)

**Files:** `src/server/app_core.py:1962-1978` (`_local_cors`).

**Change:** Replace the unconditional `Access-Control-Allow-Origin: *` with an echo-only-on-exact-match. The UI is same-origin (served from the same host:port that serves `/api/...`), so no legitimate cross-origin caller exists.

```python
@app.after_request
def _local_cors(response):
    origin = request.headers.get("Origin")
    if origin and origin == request.host_url.rstrip("/"):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-API-Token, X-User-Id, X-User-Email, X-User-Role, X-Workspace-Id, X-Client-Id"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response
```

Same-origin requests (the normal case — no `Origin` header at all, or one that already matches) need no CORS header regardless; this only stops a *different*-origin page's `fetch()` from getting a permissive header back. Drop the bare `try/except: pass` — nothing here can raise except a malformed `request.host_url`, which should surface, not be swallowed.

**Pre-check (per review's open question 1):** confirm no launcher opens `frontend/index.html` via `file://`. `grep -rn "index.html" launchers/ src/desktop_app.py` — desktop mode uses PyWebView pointed at a served URL, not a raw `file://` path (per `documentation/CLAUDE.md`'s architecture section); server mode opens a browser tab to `127.0.0.1:5050`. Both are same-origin. No `file://` launcher exists — safe to proceed without a fallback branch for it.

**Verification:**
- Targeted: any existing route test exercising a normal request still passes (no test currently asserts on `Access-Control-Allow-Origin`; `grep -rn "Access-Control-Allow-Origin" tests/` first to confirm — if one exists, update its expectation).
- Manual/functional: from the running app, in-browser UI still loads and saves a field (same-origin fetch unaffected). A cross-origin fetch (e.g. from `https://example.com` console, if testable) now fails — this is the review's stated verification method; if no browser test environment is available this session, note it as unverified-by-execution rather than claiming it.

**Effort:** S. **Risk:** Low-Medium (stated in review). **Model:** Sonnet, low effort.

---

### 2.2 W4-2 — Restrict the MC parity gate; surface approximation status (N1)

**Files:** `tests/test_monte_carlo_default_engine_mode.py` (~line 38-92, `test_exact_scalar_oracle_agrees_with_vectorized_default_within_tolerance`); KPI-tile surface (locate via `grep -rn "success_rate_ci_low\|mc_approximation_status" frontend/js/` — likely `dashboard.js` or a decomp file rendering the MC KPI) and the workbook builder (`src/reporting/workbook_builder.py` or `summary_figures.py`, wherever `success_rate` is written to the summary sheet).

**Change, part 1 (test-only, do first — this is what "restricts the gate" means):** add a second test-only config that disables the two named approximation sources (home-equity contingency, survivor-bucket economics — both are named in `src/planning_engines.py` around lines 6127-6145) and asserts 1pp tolerance in that restricted configuration, while leaving the existing 5pp full-configuration test as a separately-labeled, wider-tolerance check (per the review's Option 2, not Option 1's full diagnostic — that's out of scope for this wave per the recommendation "Option 2 immediately... Option 1 scheduled next").

First locate the actual config flags: `grep -n "home_equity_contingency\|survivor" src/planning_engines.py | grep -i "flag\|enable\|config\[" ` to find the exact `cfg[...]` keys gating those two mechanisms (do not guess the key names — read the ~6127-6145 block directly before writing the test).

```python
def test_exact_scalar_oracle_agrees_with_vectorized_within_1pp_when_approximations_disabled(self):
    """Narrower gate isolating the two NAMED approximation sources
    (home-equity contingency, survivor-bucket economics; planning_engines.py
    ~6127-6145) from the full-configuration 5pp gate above. This is the
    meaningful regression gate: it should stay near 0pp and flag drift the
    moment either named approximation's behavior changes, independent of
    the wider, disclosed 5pp full-config gap (see N1, system review
    2026-09-07)."""
    data = load_csv(TEST_INPUT_DIR / "client_data.csv")
    cfg = prepare_config_from_sectioned_data(data, "")
    cfg["mc_sims"] = 200
    cfg["mc_sensitivity_sims"] = 1
    cfg["<home_equity_flag>"] = False   # exact key from the grep above
    cfg["<survivor_economics_flag>"] = False
    ... # same vec/scalar comparison as the existing test, assertLessEqual(drift_pp, 1.0)
```

**Change, part 2 (disclosure):** add `mc_approximation_status` to whatever payload the KPI tile / workbook summary already reads success_rate from, rendering a small "±Xpp approximate" badge when status is `APPROXIMATE_PENDING_SCALAR_PARITY`. Locate the exact render site before writing code — do not assume a component exists.

**Sequencing:** write and run the new test FIRST, in isolation (`pytest tests/test_monte_carlo_default_engine_mode.py -q`), before touching any UI/workbook code — if the isolated-approximations config doesn't actually converge to ~1pp, that's new information (the review's attribution, per its own open question 2, is docstring-based, not independently re-derived) and changes what "Option 2" even means here; stop and report rather than proceeding to the UI change on an unverified premise.

**Verification:** new test passes at ≤1pp; existing 5pp test untouched and still passes; KPI tile/workbook shows the badge when status is approximate (visual/manual check — flag as unverified-by-execution if no browser session is run this pass).

**Effort:** S-M. **Risk:** Low. **Model:** Sonnet, medium effort (requires reading the approximation-flag code before guessing key names, and locating the KPI/workbook render site — some search, but no architectural judgment).

---

### 2.3 W4-3 — SS claim-age month precision (N2)

**Files:** `src/data_io.py:430-451` (`_ss_claim_from_date_or_age`), `frontend/js/dashboard_decomp_income_streams.js:58-64` (`ssClaimAgeFromDate`).

**Design confirmed by reading both consumers first:**
- `src/projection_stages/deterministic_engine.py:498-507` (`_ss_claim_factor`) already accepts a **fractional** `claim_age` — `months = int(round((float(claim_age or fra) - fra) * 12))` — so no change is needed there; it was built to handle exactly this input and is currently being fed an integer.
- `frontend/js/dashboard_decomp_income_streams.js:79-85` (`ssClaimFactor`) is the same fractional-capable logic in JS, confirming the review's "already month-denominated" note. This is **Option (a)** from the review — compute a fractional claim age at the one derivation site, let the existing factor functions interpolate. No new interpolation logic needed anywhere.

**Python change** (`src/data_io.py:446-451`):
```python
def _ss_claim_from_date_or_age(data, person, dob_yr, dob_month, legacy_default_age):
    parsed = _month_year_parts(_v(data, 'Social Security', person, 'claim_date', ''))
    if parsed:
        claim_year, claim_month = parsed
        claim_age = (claim_year - dob_yr) + (claim_month - dob_month) / 12.0
        return claim_age, claim_year, claim_month
    claim_age = int(_n(_v(data, 'Social Security', person, 'claim_age', legacy_default_age), 70))
    return claim_age, dob_yr + claim_age, dob_month
```
Update the docstring's "claim_year - dob_yr" line to describe the fractional derivation.

Check every consumer of the returned `claim_age` for an assumption it's an integer before landing this — `grep -n "ss_claim_age\|h_claim_age\|w_claim_age" src/*.py src/projection_stages/*.py`. The two known consumers (`data_io.py:713-714`'s `max(62, min(70, ...))` table-index clamp, and `deterministic_engine.py:1061-1063`'s identical clamp before the table lookup) explicitly `int(...)` the value for the **table** lookup (correct — `ss_benefit_age_NN` fields are per-integer-year) but must fall through to `_ss_claim_factor`'s fractional path when no exact-age table entry exists, i.e. the `int()` clamp must stay scoped to the table-lookup fallback key, not overwrite the fractional value used by `_ss_claim_factor` itself. Read `deterministic_engine.py:1081-1082` again after the data_io.py change to confirm `h_claim_age`/`w_claim_age` (the ints, used for the table dict `.get()`) and the value passed into `_ss_claim_factor` are handled as two distinct variables, not the same one reused — from the current read, line 1061-1062 already produces the int for the table lookup separately from what would need to carry the fraction through; this is the one place in this item that needs code-level care rather than a mechanical edit, because introducing a fractional `h_claim_age`/`w_claim_age` upstream must not silently break the `int(c.get('h_ss_claim_age', ...))` cast at line 1061 (it won't — `int()` on a float truncates, which is fine for the table-index use — but confirm no other unguarded arithmetic assumes integer claim age before landing).

**JS change** (`dashboard_decomp_income_streams.js:58-64`):
```javascript
export function ssClaimAgeFromDate(person, claimDateRow) {
  const dob = ssPersonDobParts(person);
  const raw = String((claimDateRow ? valOf(claimDateRow) : "") || "").trim();
  const m = raw.match(/^(\d{1,2})\/(\d{4})$/);
  if (m && dob) return (Number(m[2]) - dob.year) + (Number(m[1]) - dob.month) / 12;
  return 70;
}
```
`ssMonthlyAtClaimAgeCell` (line 90-93) already does `Math.round(ssClaimAgeFromDate(...) || 70)` before the table-lookup clamp — same shape as the Python side, no change needed there; it now rounds a fractional age to the nearest integer for the table key, which is correct (nearest whole-year SSA-quoted entry), while the FRA-derived fallback path (line 118, `ssClaimFactor(age, fra)`) is passed the **rounded** `age`, not the fraction — for full parity with the corrected Python engine (which now feeds `_ss_claim_factor` the true fraction, not a rounded one), pass the unrounded `ssClaimAgeFromDate(...)` result into `ssClaimFactor` at line 118 instead of the rounded `age` variable, keeping `age` (rounded) only for the table-key lookups at lines 90-99 and 112. Re-read lines 88-120 at implementation time to make this split precisely — don't guess the variable boundary from this summary alone.

**Golden-master impact (per review + CLAUDE.md's Golden master maintenance section):** this changes engine output for any fixture where claim month ≠ birth month. Do NOT hand-edit the pins.
1. Add the unit test first: `1960-11` DOB, `claim_date=03/2027` → claim_age `66 + (3-11)/12 = 65.33` (recompute exactly at implementation time — the review's stated expectation is "66y4m", i.e. 66.33, which corresponds to a claim 4 months after the Nov birthday, e.g. claim_date 03/2027 relative to a **later** DOB year than 1960 — recheck the review's exact figures at write-time rather than trusting this note's arithmetic) landing strictly between the age-66 and age-67 factors.
2. Check whether `tests/fixtures/sample_plan_frozen`'s frozen household has a `claim_date` at all, and whether its claim month differs from its birth month — if not, the golden master pins may be unaffected and no regen is needed; confirm before assuming a regen is required.
3. If affected: regenerate via `py -3.14 tools/regen_golden_master.py regen --reason "N2: SS claim-age month precision fix"` (per `documentation/GOLDEN_MASTER_RECOVERY_RUNBOOK.md` — never hand-edit `PINNED_TERMINAL_NW`/`PINNED_LIFETIME_TAX`).
4. Add an entry to `documentation/GOLDEN_MASTER_CHANGELOG.md` describing this as a **correction** (per the review's planner sign-off in §14), not silent drift.

**Verification:** new unit test passes; `pytest tests/ -m "not slow" --tb=short -q` (fast tier) green; full suite before push per CLAUDE.md's table (golden-master fixture touched).

**Effort:** S (mechanical edit at the two known sites) but **treat the golden-master step as its own checkpoint** — don't bundle it into the same commit-verification pass as W4-1/4/5. **Risk:** Medium (explicitly moves pinned figures). **Model:** Sonnet, medium effort — the fix itself is small, but the consumer-audit (confirming no unguarded integer assumption elsewhere) needs a careful read, not a guess.

---

### 2.4 W4-4 — Confine Monarch `source_dir` to the workspace root (SEC-2)

**Files:** `src/monarch_autoupdate.py:60-67` (`resolve_source_dir`), `:93-104` (`save_policy`), `src/server/plan_routes.py:370-386` (`monarch_autoupdate_config` route).

**Design (review's Option 2 + Option 1's route validation, combined per the review's recommendation):** stop deriving the *interpreter* from `source_dir` at all — pin the extractor directory to a fixed, known-safe location, and let `source_dir` configure only the *output* subfolder it already conceptually represents (`DEFAULT_SOURCE_DIR = "Monarch Extractor/output"`). Combine with route-level path confinement so a browser-supplied `source_dir` can never resolve outside the workspace root.

**Change 1 — `src/monarch_autoupdate.py`:** add a validator used by both `save_policy` and (transitively) `resolve_source_dir`:
```python
def _validate_source_dir(base_dir: str | Path, raw: str) -> Path:
    p = Path(raw).expanduser()
    resolved = p if p.is_absolute() else (Path(base_dir) / p).resolve()
    workspace_root = Path(base_dir).resolve()
    try:
        resolved.relative_to(workspace_root)
    except ValueError:
        raise ValueError(f"source_dir must resolve under the workspace root ({workspace_root}); got {resolved}")
    return resolved
```
Call it from `resolve_source_dir` (replacing the current unguarded resolve) and from `save_policy` before persisting (raise/reject rather than silently accepting an out-of-root path).

**Change 2 — interpreter resolution (`src/monarch_autoimport_job.py:23-35`, `_resolve_extractor_python`):** this function already takes `extractor_dir` as a parameter separate from the configurable `source_dir` — confirm its caller (search `_resolve_extractor_python(` call sites) currently passes something derived from `source_dir` rather than a fixed path; if so, change the caller to pass a fixed, non-configurable extractor directory (the shipped `Monarch Extractor/` at the workspace root, not `source_dir`-relative) so `source_dir` can no longer influence which interpreter executes at all — this is the review's Option 2 ("stop deriving the interpreter from data").

**Change 3 — route (`src/server/plan_routes.py:370-386`):** wrap the `monarch_autoupdate.save_policy(WORKSPACE_ROOT, body)` call in a try/except for the new `ValueError`, returning `400` with the error message — this is what the review's stated verification method ("a config POST with an out-of-workspace `source_dir` is rejected with 400") requires; currently the route has no validation path to reject through.

**Verification:** new unit test in a new/existing `tests/test_monarch_autoupdate_*.py` — POST-equivalent (or direct `save_policy` call) with `source_dir="../../etc"` raises/rejects; default-path config still round-trips; existing Monarch tests (`grep -rln "monarch_autoupdate\|monarch_autoimport" tests/`) still pass.

**Effort:** S. **Risk:** Low (default path unaffected — confirm with the new test). **Model:** Sonnet, low-medium effort (requires tracing the caller of `_resolve_extractor_python` before editing — one grep, not exploratory).

---

### 2.5 W4-5 — Exclude credentials/session data from build backup (SEC-3)

**Files:** `tools/backup_to_onedrive.py:36` (`EXCLUDE_DIRS`), plus a file-level (not dir-level) exclusion for `secrets.local.json`.

**Change:**
```python
EXCLUDE_DIRS = {"build", "__pycache__", ".pytest_cache", ".git", "monarch-browser", ".venv"}
EXCLUDE_FILES = {"secrets.local.json"}
```
Locate the zip-write loop (read past line 60 — not yet shown above) and add a filename check against `EXCLUDE_FILES` alongside the existing dir-name check, e.g. `if path.name in EXCLUDE_FILES: continue` at whatever point the current code does `if part in EXCLUDE_DIRS: skip`. Also update the module docstring's line 18 ("The zip contains EVERYTHING... only throwaway caches are skipped") since credentials/PII are now deliberately excluded too — that line is now inaccurate and was itself cited as background for how the gap went unnoticed.

**Verification:** run `python tools/backup_to_onedrive.py` (or the relevant unit test if one exists — `grep -rln "backup_to_onedrive" tests/`) and inspect the resulting zip's namelist for absence of `monarch-browser/`, `.venv/`, `secrets.local.json` — this is exactly the review's stated verification method.

**Effort:** S. **Risk:** None (excluded items are runtime state, not backup-restorable content, per the review). **Model:** Sonnet, low effort.

---

## 3. Sequencing and test plan

Execute in this order (independent items, but sequenced safest-first so an issue in a later item never invalidates verification already done on an earlier one):

1. **W4-5** (backup exclusion) — zero code-path risk, fastest to verify.
2. **W4-4** (Monarch path validation) — isolated subsystem, own test file.
3. **W4-1** (CORS) — one function, verify same-origin UI still works.
4. **W4-2** (MC parity gate) — test-only + one disclosure surface; run in isolation before touching UI.
5. **W4-3** (SS claim-age) — last, because it's the only item that may require a golden-master regen; doing it last means the regen step isn't blocking verification of the other four.

**After each item:** run its own targeted test file only (`pytest tests/test_<file>.py -q`).

**After all five:** fast tier once — `pytest tests/ -m "not slow" --tb=short -q`.

**Before push (per CLAUDE.md, since W4-3 touches a golden-master fixture):** full suite — `pytest tests/ -n auto --tb=short -q`.

**Changelog / status-record updates required by the review itself (§7, process fix):** none of Wave 4's items require a Wave 2/3 status-record correction (that's W4-9, Wave 5) — but `documentation/GOLDEN_MASTER_CHANGELOG.md` does need the W4-3 entry per §2.3 step 4 above if the fixture is affected.

---

## 4. Explicitly out of scope for this wave

- N1's full root-cause diagnostic (review's Option 1) — scheduled next per the review's own recommendation; W4-2 here only does Option 2 (gate restriction) + Option 3 (disclosure).
- Everything in Wave 5 (ARC-1, UX-101, DOC-201, ARC-2/N7/N8/ARC-3 status corrections, N4, N5, N3, DOC-203, QUA-301, UX-102/106, UX-105, UX-103/104, N6) — separate wave, no dependency on Wave 4's completion.
