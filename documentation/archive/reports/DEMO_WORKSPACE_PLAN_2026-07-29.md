# Editable, persistent demo plan — scope and plan (2026-07-29)

**Question asked:** *"Can I modify demo data from the UI and have it saved in the
demo moving forward (like a separate plan)?"*

**Short answer:** Not today — `Open Current Plan` throws demo edits away by
design. But the gap is smaller than it looks, because the app already has most
of the machinery. This document records what exists, what is actually missing,
three options with honest costs, and a recommendation.

---

## 1. What the code actually does today

Every claim below was read out of the source, not inferred.

### 1.1 Demo mode is a swap, not a plan

`DemoPlanService` (`src/server_services/demo_plan_service.py`):

| Step | What happens |
|---|---|
| **Open Demo Plan** | One-time snapshot of the live SQLite DB to `<db>.before_demo`, plus separate text backups for `client_data.csv` and each `TEXT_BACKUP_FILES` entry. Then `input/demo/*.csv` is written through the **real plan-data write path** into the live slot. |
| **While open** | You are editing the live working copy. The demo is *not* sandboxed — it is simply what currently occupies the one plan slot. |
| **Open Current Plan** | `load_saved_db(<db>.before_demo)` swaps the whole DB back, `materialize()` rewrites the disk mirrors, the text backups are restored, and the backup files are deleted. |

Two consequences fall straight out of that design:

- **Demo edits are discarded.** Nothing reads the demo slot before the swap-back;
  there is no second slot for them to land in.
- **`input/demo/` is read-only to the app.** A repo-wide grep for writes into
  that directory returns nothing. Edits could never flow back to the fixtures
  even in principle.

"Is a demo active?" is derived from the *existence* of `<db>.before_demo`, not
from a flag — deliberately, so a crash cannot strand the real backup.

### 1.2 There is already a second-plan mechanism — `Save Plan As` / `Load Saved Plan`

`plan_file_service.save_as()` copies the current SQLite DB to a user-chosen
`.rpx` file; `load_file()` copies one back over the live DB, first stashing the
previous DB as `<db>.before_load_<ts>` (10 retained).

**This means demo edits are already persistable today**, via a route nobody has
framed that way: open the demo, edit it, `Save Plan As` → `my-demo.rpx`, and
`Load Saved Plan` it back whenever you want. It works because `save_as` snapshots
whatever is in the live slot, and during a demo that is the demo.

Both are **desktop-only** — they go through `window.pywebview.api.show_save_dialog`,
so they are unavailable in a browser session.

### 1.3 The multi-workspace seam exists but is vestigial

This is the single most important finding for costing the work.

- `src/workspace_context.py` — **every** function takes a `workspace_id`
  parameter and **ignores it**. `active_workspace_id()` is a hardcoded
  `return "local"`. `workspace_file()`, `workspace_input_dir()`, and
  `workspace_plan_data_dir()` all resolve to the one `input/` directory.
- `client_files` is keyed by `file_name` **alone**:
  ```sql
  CREATE TABLE IF NOT EXISTS client_files(
      file_name TEXT PRIMARY KEY, content TEXT NOT NULL, ...)
  ```
  `set_client_file()`/`get_client_file()` accept `workspace_id` and `client_id`
  and never put them in the SQL.
- ~174 references to `workspace_id` across `src/` already thread the parameter
  to the right places.

So the *plumbing* is laid and the *fittings* are blanked off. Turning on real
workspaces is mostly un-stubbing a resolver, not re-architecting call sites.

Two facilities make this materially cheaper still:

- `platform_runtime.workspace_root()` already honors a
  `RETIREMENT_SYSTEM_WORKSPACE_ROOT` env override — the entire writable tree is
  relocatable today.
- `_sqlite_db()` resolves from `runtime_config.sqlite_db` relative to that root —
  the DB path is already configurable.

### 1.4 The disk/DB duality is the real complexity

The SQLite store is canonical, but the engine reads plan data from **disk**
(`data_io`, `spending_tracker`, both via `_root()/"input"/...`). So every plan
swap must keep the DB *and* `input/*.csv` coherent — which is exactly why
`load_file` calls `materialize_workspace_files()` afterwards, and why
`DemoPlanService` needs `TEXT_BACKUP_FILES` for the files that live outside
`PLAN_DATA_CSV_FILES`.

Any workspace design must satisfy: **one active workspace ⇒ one coherent
(DB, input/ dir) pair.**

### 1.5 A known rough edge, worth folding in

`save_as` copies only the DB, and the `load-file` route materializes
`[n for n in PLAN_DATA_CSV_FILES if n != "client_data.csv"]` — `client_data.csv`
is explicitly excluded, and it is the one plan-data file that never lives in the
DB.

In practice the blast radius is small: readers load `client_data.csv` **and then**
every part file (`_client_data_csv_paths()` in both `data_io` and
`config_backend`), so the parts — which *are* materialized — override it for any
key they define. `client_data.csv` is a ~16-line anchor whose keys are duplicated
in `client_policy.csv`. It is a latent inconsistency rather than a live bug, but
any workspace work should close it rather than inherit it.

---

## 2. What is actually missing

Only two things, once the above is accounted for:

1. **A writable slot for the demo.** Somewhere that is not `input/demo/` (which
   ships in the repo and must stay pristine) and not the live plan slot.
2. **Plan identity.** Nothing labels the active plan. After
   `Save Plan As` → `Open Current Plan` → `Load Saved Plan`, the app shows demo
   content with `demoModeActive == false` and no `.before_demo` file — the demo
   is now indistinguishable from your real plan. That is the sharpest edge in
   the current workaround, and the thing most likely to cause a bad day.

---

## 3. Options

### Option A — Surface what already works (¼ day)

Document and sign-post the `Save Plan As` route for demos: a line in the demo
banner ("Editing the demo? *Save Plan As* to keep this version"), and a
`documentation/` note.

- **Pro:** near-zero cost, zero risk, ships today.
- **Con:** does not answer "saved in the demo moving forward" — you get a
  *separate file*, not a demo that remembers. Desktop-only. Leaves the identity
  confusion of §2.2 fully in place.
- **Verdict:** worth doing regardless, but not sufficient on its own.

### Option B — A writable demo slot (2–3 days) ← recommended

Give the demo one persistent home under `local_state/` and teach
`DemoPlanService` to prefer it.

- `Open Demo Plan` seeds from `local_state/demo_plan/` if present, else from
  `input/demo/` (first run, and after an explicit reset).
- `Open Current Plan` **captures** the demo slot into `local_state/demo_plan/`
  before swapping back, instead of discarding it.
- A `Reset Demo to Defaults` action deletes `local_state/demo_plan/` so the next
  open re-seeds from the shipped fixtures.

- **Pro:** answers the literal question; contained inside one service that is
  already well-tested; `input/demo/` stays pristine so the anti-leak tests keep
  their meaning; no schema change; no change to the single-active-plan model.
- **Con:** two plans, not N. Does not fix plan identity in general (though the
  demo banner already labels the demo case, which is the case that matters).
- **Risk:** moderate and localized — the capture step must not run when no demo
  is active, and must not clobber the real backup. Both are already-solved
  problems in this service.

### Option C — Real named workspaces / profiles (1.5–3 weeks)

Un-stub `workspace_context`: each profile gets
`profiles/<id>/{plan.db, input/}`; `active_workspace_id()` reads from settings;
a profile switcher in the UI; demo becomes a seeded profile like any other.

- **Pro:** the architecturally right answer. N plans, real identity, "Save Plan
  As" becomes a special case of "copy profile". Uses the seam as designed.
- **Con:** the disk/DB duality (§1.4) has to be made per-profile, which touches
  materialization, backup scheduling, build output paths, and the local backup
  scheduler. The `client_files` PK change is a migration. Every one of ~174
  `workspace_id` call sites becomes live code that must be *correct*, not just
  present.
- **Risk:** high. This is the change that can corrupt a real plan if a resolver
  returns the wrong root mid-write.

---

## 4. Recommendation

**Do A now and B next. Do not start C without a second driver.**

Option B answers what was actually asked, at a cost proportionate to it, inside
a service that already has the backup/restore invariants and test coverage. C is
the better architecture, but nothing currently in flight needs N plans — the
demo needs *one* extra slot. Building the general system to satisfy a two-slot
requirement is the expensive mistake here.

If a second driver appears — multiple households, before/after scenario
comparison, an advisor managing several clients — revisit C, and note that B is
not wasted: a persistent demo slot is trivially re-expressible as one profile.

---

## 5. Implementation plan for Option B

### Step 1 — Extract the slot layout (small, no behavior change)

Add to `demo_plan_service.py`:

```
DEMO_SLOT_DIR = "demo_plan"   # under the DB's parent (local_state/)
```

Add `demo_slot_dir` to `DemoPlanServiceContext` (defaulted, so existing
constructions and the tmp_path test harness keep working). Ship with the slot
unused, so this step is pure refactor.

### Step 2 — Seed preference on open

In `open_demo_payload()`, replace the single `demo_dir` read with a resolver:

```
source = slot_dir if (slot_dir / name).exists() else demo_dir
```

Per-file, not per-directory — so a fixture added to `input/demo/` in a later
release is still picked up by a user who already has a slot. This is the same
reason `TEXT_BACKUP_FILES` is a per-file list.

Report the chosen source per file in the existing `written[]` payload, so the
audit log shows which files came from the slot.

### Step 3 — Capture on restore

In `restore_current_payload()`, **before** the DB swap-back, read each demo file
through `read_plan_data_file` and write it into the slot. Guard conditions:

- only when `is_active()` — never capture when no demo is open;
- capture failures are non-fatal and audited, exactly as the existing text-backup
  failures are — a capture problem must never block the user from getting their
  real plan back. **This is the single most important invariant in the change.**

### Step 4 — Reset action

`POST /api/plan/reset-demo` → delete the slot directory. Wire a
`Reset Demo to Defaults` button into the demo banner, guarded by a confirm.
Refuse while a demo is open (the swap on close would immediately re-create it) —
return a clear error telling the user to close the demo first.

### Step 5 — Tests

Extend `tests/test_demo_plan_open_restore.py`, which already has the isolated
`tmp_path` harness:

- open → edit → restore → **open again** shows the edit;
- open → edit → restore → **reset** → open shows the shipped fixture;
- capture never runs when no demo is active;
- a capture failure still restores the real plan (inject a raising writer);
- a slot missing a file falls back to `input/demo/` for that file only.

Extend `tests/test_demo_plan_data_is_fictional.py` with the one that keeps the
privacy guarantee honest: **the slot is not the fixtures** — the anti-leak tests
must keep pointing at `input/demo/`, and a populated slot must not be able to
satisfy them.

### Step 6 — Documentation

Update `input/demo/README.md`: the fixtures are the *seed*, the slot is the
*working copy*, and `Reset Demo to Defaults` is how you get back to the seed.

### Sequencing note

Steps 1–3 are one PR (the feature). Steps 4–6 are a second (the affordance).
Splitting there keeps the risky part — the restore path — reviewable on its own.

---

## 6. Open questions for Matt

1. **Scope check:** is one persistent demo enough, or is the real want several
   named plans (a household you are prospecting, a what-if, your own)? That is
   the A/B-vs-C fork, and it is your call, not a technical one.
2. **Browser parity:** `Save Plan As` / `Load Saved Plan` are desktop-only. Should
   the demo slot work in a browser session too? (Option B does, for free — it
   needs no file dialog. Worth knowing if that matters.)
3. **Reset semantics:** should `Reset Demo to Defaults` be reachable while a demo
   is open (reset-and-reload in one click), or only from the real plan? The plan
   above assumes the latter as the safer default.
