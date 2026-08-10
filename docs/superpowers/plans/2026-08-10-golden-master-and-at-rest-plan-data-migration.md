# Golden Master Recovery + At-Rest Plan Data Migration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Get `main` green on the frozen golden master, then build the persisted schema-version gate that lets Plan Data be migrated once at rest instead of re-normalized on every load — and use it to land the wellness→healthcare rename.

**Architecture:** Three independent phases, in dependency order. Phase 1 is a self-contained pin recovery on an already-red test. Phase 2 adds a `local_settings`-backed schema-version gate plus a one-shot runner that rewrites stored CSVs and DB content through the existing (but currently uncalled) `migrate_csv_content`. Phase 3 rides that gate to add the first *new* transform since husband/wife — the wellness label renames — as a data-at-rest-only change, with Python identifiers deliberately left alone.

**Tech Stack:** Python 3.14 (`py -3.14`), pytest + unittest, SQLite (stdlib `sqlite3`), CSV-sectioned Plan Data.

## Global Constraints

- Run all builds/tests with `py -3.14` — plain `python` is 3.12 here and lacks pytest/openpyxl.
- Set `RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS=1` on every test run to stop golden-master dollar drift between runs.
- This repo's suite mutates tracked files (`input/*.csv`, several `frontend/js/*.js`). After any broad run, check `git status` and `git checkout --` unintended changes. Capture pytest output to a FILE — a truncated tail hides FAILED lines.
- Do NOT rename Python identifiers in Phase 3. Data-at-rest labels only (scope decision, 2026-08-10).
- `migrate_rows` semantics are load-bearing: "current key wins" — a legacy row colliding with an existing current row is DROPPED, never overwritten. Every new transform must preserve this.
- Work on a branch off `main`; never commit directly to `main`.

---

## File Structure

| File | Responsibility | Phase |
|---|---|---|
| `tests/test_frozen_sample_plan_golden_master_regression.py` | Frozen-fixture pin; owns `PINNED_TERMINAL_NW` / `PINNED_LIFETIME_TAX` and the `__main__` regen block | 1 |
| `src/local_store.py` | Add `get_local_setting` / `set_local_setting` over the existing `local_settings` table | 2 |
| `src/plan_data_migration.py` | Add version gate + `migrate_plan_data_at_rest()` runner; later, wellness renames | 2, 3 |
| `tests/test_plan_data_migration.py` | Existing 5 tests; extended for the gate, runner, and wellness renames | 2, 3 |
| `src/server/app_core.py` | Call the migration once at startup | 2 |

---

## Phase 1 — Golden Master Recovery

**Current state (verified 2026-08-10 on `main` @ `ccb47c1`):**
`tests/test_frozen_sample_plan_golden_master_regression.py::FrozenSamplePlanGoldenMasterTests::test_frozen_plan_dollar_figures_are_exact` FAILS:
terminal NW `5,824,239.30` → `6,044,750.40` (**+$220,511.10**). `tests/test_synthetic_golden_master.py` passes.
The fixture is hermetic (`FROZEN_TODAY = "2026-08-04"`, self-contained frozen inputs, proven by the sibling isolation test), so this is an engine-behavior change, not data drift.

### Task 1: Identify the commit that moved the pin

**Files:**
- Read only: `src/projection_stages/deterministic_engine.py`, `src/planning_engines.py`
- Test: `tests/test_frozen_sample_plan_golden_master_regression.py`

**Interfaces:**
- Consumes: nothing (entry point)
- Produces: a confirmed culprit commit SHA + a one-line justification of whether the move is intentional. Task 2 quotes both in the pin comment.

The pin was last set 2026-08-05. Engine-touching commits landed 2026-08-10 in the "tickets 265-277" batch. Prime suspects, most to least likely:
- `ff8350d` Fix #276: individual-account withdrawal draw-order override (engine + API + UI)
- `e8eeb2e` Fix #270: DAF contribution recommendation engine (AGI/bracket/IRMAA/NIIT-aware)
- `355564d` Fix #268: don't annualize Income/Large Discretionary in spending summary

- [ ] **Step 1: Confirm the failure reproduces and capture the exact delta**

```bash
cd "C:/RetirementPlanning/Version 10"
git checkout -b fix/regen-frozen-golden-master main
RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS=1 py -3.14 -m pytest \
  tests/test_frozen_sample_plan_golden_master_regression.py -q > /tmp/gm_before.txt 2>&1
cat /tmp/gm_before.txt
```

Expected: 1 failed. The message names both numbers. Record them.

- [ ] **Step 2: Write the bisect predicate script**

Create `/tmp/gm_check.sh`:

```bash
#!/usr/bin/env bash
# exit 0 = good (pin matches), 1 = bad (pin moved), 125 = skip (build broken)
cd "C:/RetirementPlanning/Version 10" || exit 125
RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS=1 py -3.14 -m pytest \
  "tests/test_frozen_sample_plan_golden_master_regression.py::FrozenSamplePlanGoldenMasterTests::test_frozen_plan_dollar_figures_are_exact" \
  -q > /dev/null 2>&1
rc=$?
[ $rc -eq 0 ] && exit 0
[ $rc -eq 1 ] && exit 1
exit 125
```

- [ ] **Step 3: Run the bisect**

`531c883` (2026-08-06) predates the suspect batch and should be good; `main` is bad.

```bash
cd "C:/RetirementPlanning/Version 10"
chmod +x /tmp/gm_check.sh
git bisect start main 531c883
git bisect run /tmp/gm_check.sh
```

Expected: prints `<sha> is the first bad commit`. If `531c883` is itself bad, restart the bisect with an older good point (`3b1cedf`, then `52ffe60`).

- [ ] **Step 4: Reset bisect state**

```bash
git bisect reset
git status --porcelain   # must be clean; git checkout -- . if the suite mutated inputs
```

- [ ] **Step 5: Read the culprit and classify the change**

```bash
git show --stat <first-bad-sha>
git show <first-bad-sha> -- src/
```

Decide, and write down one sentence: **intentional** engine/tax-law evolution (→ Task 2 regenerates the pin), or an **unintended regression** (→ STOP; do not regenerate. Open a separate fix, since regenerating would bake the bug into the baseline).

A +$220.5k terminal-NW move on a withdrawal-ORDER change is plausible and intentional-looking: draw order shifts which accounts are depleted first, changing the tax drag and therefore terminal wealth. Confirm that story against the actual diff rather than assuming it.

- [ ] **Step 6: Commit nothing yet**

This task produces a finding, not a code change. Proceed to Task 2 only if the change is intentional.

---

### Task 2: Regenerate the pin with provenance

**Files:**
- Modify: `tests/test_frozen_sample_plan_golden_master_regression.py:117-118` (`PINNED_TERMINAL_NW`, `PINNED_LIFETIME_TAX`)
- Test: same file

**Interfaces:**
- Consumes: Task 1's culprit SHA + intentional/regression verdict
- Produces: a green frozen golden master on the branch. No API surface.

- [ ] **Step 1: Print the new pins from the file's own regen block**

The file ships a `__main__` regen path that reuses the exact frozen config and frozen prices.

```bash
cd "C:/RetirementPlanning/Version 10"
RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS=1 py -3.14 -m tests.test_frozen_sample_plan_golden_master_regression
```

Expected output, two lines:

```
PINNED_TERMINAL_NW = 6044750.4
PINNED_LIFETIME_TAX = <value>
```

- [ ] **Step 2: Update both constants and add a dated provenance comment**

Replace the two constants at `tests/test_frozen_sample_plan_golden_master_regression.py:117-118`. Keep the existing comment block above them and append a new dated entry in the same style the file already uses:

```python
# Regenerated 2026-08-10 (engine change, not data drift): <first-bad-sha>
# "<commit subject>" changed <one-line mechanism, e.g. per-account withdrawal
# draw order>, which shifts which accounts deplete first and therefore the
# lifetime tax drag. Frozen fixture is unchanged. Terminal NW 5,824,239.30 ->
# 6,044,750.40 (+220,511.10); lifetime tax <old> -> <new>.
PINNED_TERMINAL_NW = 6044750.40
PINNED_LIFETIME_TAX = <new value from Step 1>
```

- [ ] **Step 3: Verify the frozen golden master is green**

```bash
RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS=1 py -3.14 -m pytest \
  tests/test_frozen_sample_plan_golden_master_regression.py tests/test_synthetic_golden_master.py -q
```

Expected: all pass (8 tests).

- [ ] **Step 4: Verify no collateral damage across the other golden/structural suites**

```bash
RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS=1 py -3.14 -m pytest tests/ -q > /tmp/gm_full.txt 2>&1
tail -30 /tmp/gm_full.txt
grep -E "^FAILED|^ERROR" /tmp/gm_full.txt || echo "no failures"
git status --porcelain
```

Expected: no FAILED lines. If `input/` or `frontend/js/` files were mutated by the suite, `git checkout --` them before committing.

- [ ] **Step 5: Commit**

```bash
git add tests/test_frozen_sample_plan_golden_master_regression.py
git commit -m "test: regenerate frozen golden-master pins after <sha> engine change

Terminal NW 5,824,239.30 -> 6,044,750.40 (+220,511.10) and lifetime tax
<old> -> <new>. Bisected to <sha> (<subject>); the frozen fixture is
unchanged, so this is deliberate engine evolution, not data drift."
```

---

## Phase 2 — Persisted Startup Migration + Version Gate

**Why this exists:** `PLAN_DATA_SCHEMA_VERSION = 2` sits in `src/plan_data_migration.py:24` with **no consumer anywhere in `src/`**, and `migrate_csv_content` has **no caller**. Today `migrate_sectioned_data` normalizes legacy shapes on every single load (called at `src/data_io.py:647` and `src/domain_models.py:196`) but never rewrites data at rest — so legacy rows live forever and every future transform pays the per-load cost. This phase makes migration happen once and stick.

### Task 3: `local_settings` get/set helpers

**Files:**
- Modify: `src/local_store.py` (append after `latest_sectioned_data`, ~line 204)
- Test: `tests/test_local_store_settings.py` (create)

**Interfaces:**
- Consumes: existing `local_settings` table (`src/local_store.py:74`), `_resolve()`, `init_local_store()`, `now_utc()`
- Produces:
  - `get_local_setting(key: str, default: Any = None, db_path: str | Path | None = None) -> Any`
  - `set_local_setting(key: str, value: Any, db_path: str | Path | None = None) -> None`

The `local_settings` table already exists but has **zero helper functions** — it is declared and never used. Both helpers JSON-round-trip the value so ints, strings, and dicts all work.

- [ ] **Step 1: Write the failing test**

Create `tests/test_local_store_settings.py`:

```python
"""local_settings is a declared-but-unused table; these pin the accessors."""
from __future__ import annotations

import tempfile
from pathlib import Path

from src.local_store import get_local_setting, set_local_setting


def _db() -> Path:
    return Path(tempfile.mkdtemp()) / "test_store.sqlite"


def test_missing_key_returns_default():
    assert get_local_setting("nope", 7, db_path=_db()) == 7


def test_roundtrip_int():
    p = _db()
    set_local_setting("schema", 3, db_path=p)
    assert get_local_setting("schema", 0, db_path=p) == 3


def test_set_overwrites_existing_key():
    p = _db()
    set_local_setting("schema", 2, db_path=p)
    set_local_setting("schema", 5, db_path=p)
    assert get_local_setting("schema", 0, db_path=p) == 5


def test_roundtrip_dict_survives_json():
    p = _db()
    set_local_setting("meta", {"a": 1, "b": [2, 3]}, db_path=p)
    assert get_local_setting("meta", None, db_path=p) == {"a": 1, "b": [2, 3]}


def test_corrupt_value_falls_back_to_default():
    import sqlite3
    from src.local_store import init_local_store, now_utc
    p = _db()
    init_local_store(p)
    with sqlite3.connect(p) as con:
        con.execute(
            "INSERT INTO local_settings(key, value_json, updated_at) VALUES(?,?,?)",
            ("bad", "{not json", now_utc()),
        )
    assert get_local_setting("bad", "fallback", db_path=p) == "fallback"
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
py -3.14 -m pytest tests/test_local_store_settings.py -q
```

Expected: FAIL — `ImportError: cannot import name 'get_local_setting'`.

- [ ] **Step 3: Implement both helpers**

Append to `src/local_store.py` (`json`, `sqlite3`, `Path`, `Any` are already imported at the top):

```python
def get_local_setting(key: str, default: Any = None, db_path: str | Path | None = None) -> Any:
    """Read a JSON-encoded value from the local_settings key-value table.

    Returns ``default`` when the key is absent OR its stored JSON is corrupt --
    a settings row must never be able to crash startup.
    """
    p = _resolve(db_path)
    init_local_store(p)
    with sqlite3.connect(p) as con:
        row = con.execute(
            "SELECT value_json FROM local_settings WHERE key = ?", (key,)
        ).fetchone()
    if row is None:
        return default
    try:
        return json.loads(row[0])
    except (ValueError, TypeError):
        return default


def set_local_setting(key: str, value: Any, db_path: str | Path | None = None) -> None:
    """Upsert a JSON-encoded value into local_settings."""
    p = _resolve(db_path)
    init_local_store(p)
    with sqlite3.connect(p) as con:
        con.execute(
            "INSERT INTO local_settings(key, value_json, updated_at) VALUES(?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET "
            "value_json = excluded.value_json, updated_at = excluded.updated_at",
            (key, json.dumps(value), now_utc()),
        )
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
py -3.14 -m pytest tests/test_local_store_settings.py -q
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/local_store.py tests/test_local_store_settings.py
git commit -m "feat: add get/set helpers for the local_settings table"
```

---

### Task 4: Schema-version gate

**Files:**
- Modify: `src/plan_data_migration.py` (append after `migrate_sectioned_data`, ~line 156)
- Test: `tests/test_plan_data_migration.py` (append)

**Interfaces:**
- Consumes: `get_local_setting` / `set_local_setting` (Task 3); existing `PLAN_DATA_SCHEMA_VERSION` (`src/plan_data_migration.py:24`)
- Produces:
  - `PLAN_DATA_SCHEMA_KEY: str` (constant `"plan_data_schema_version"`)
  - `stored_schema_version(db_path=None) -> int`
  - `set_stored_schema_version(version: int, db_path=None) -> None`
  - `needs_migration(db_path=None) -> bool`

A never-migrated store reports version 0, so `needs_migration()` is True on first run and False once stamped. The import of `local_store` is deferred inside the functions — `plan_data_migration` is imported by `data_io` at module load, and a top-level import would create a cycle.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_plan_data_migration.py`:

```python
def test_unstamped_store_reports_version_zero():
    import tempfile
    from pathlib import Path
    from src.plan_data_migration import stored_schema_version
    db = Path(tempfile.mkdtemp()) / "s.sqlite"
    assert stored_schema_version(db_path=db) == 0


def test_needs_migration_is_true_before_and_false_after_stamping():
    import tempfile
    from pathlib import Path
    from src.plan_data_migration import (
        PLAN_DATA_SCHEMA_VERSION, needs_migration, set_stored_schema_version,
    )
    db = Path(tempfile.mkdtemp()) / "s.sqlite"
    assert needs_migration(db_path=db) is True
    set_stored_schema_version(PLAN_DATA_SCHEMA_VERSION, db_path=db)
    assert needs_migration(db_path=db) is False


def test_stale_version_still_needs_migration():
    import tempfile
    from pathlib import Path
    from src.plan_data_migration import (
        PLAN_DATA_SCHEMA_VERSION, needs_migration, set_stored_schema_version,
    )
    db = Path(tempfile.mkdtemp()) / "s.sqlite"
    set_stored_schema_version(PLAN_DATA_SCHEMA_VERSION - 1, db_path=db)
    assert needs_migration(db_path=db) is True
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
py -3.14 -m pytest tests/test_plan_data_migration.py -q
```

Expected: FAIL — `ImportError: cannot import name 'stored_schema_version'`.

- [ ] **Step 3: Implement the gate**

Append to `src/plan_data_migration.py`:

```python
# Key under which the applied schema version is stamped in local_settings. A
# store that has never been migrated has no row and reads back as 0.
PLAN_DATA_SCHEMA_KEY = "plan_data_schema_version"


def stored_schema_version(db_path=None) -> int:
    """Schema version already applied to the data at rest (0 = never migrated).

    ``local_store`` is imported lazily: ``plan_data_migration`` is imported at
    module load by ``data_io``, and a top-level import here would be circular.
    """
    from .local_store import get_local_setting
    try:
        return int(get_local_setting(PLAN_DATA_SCHEMA_KEY, 0, db_path=db_path) or 0)
    except (TypeError, ValueError):
        return 0


def set_stored_schema_version(version: int, db_path=None) -> None:
    """Stamp the applied schema version after a successful migration."""
    from .local_store import set_local_setting
    set_local_setting(PLAN_DATA_SCHEMA_KEY, int(version), db_path=db_path)


def needs_migration(db_path=None) -> bool:
    """True when the data at rest predates PLAN_DATA_SCHEMA_VERSION."""
    return stored_schema_version(db_path=db_path) < PLAN_DATA_SCHEMA_VERSION
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
py -3.14 -m pytest tests/test_plan_data_migration.py -q
```

Expected: 8 passed (5 existing + 3 new).

- [ ] **Step 5: Commit**

```bash
git add src/plan_data_migration.py tests/test_plan_data_migration.py
git commit -m "feat: add persisted plan-data schema version gate"
```

---

### Task 5: One-shot at-rest migration runner

**Files:**
- Modify: `src/plan_data_migration.py` (append after `needs_migration`)
- Test: `tests/test_plan_data_migration.py` (append)

**Interfaces:**
- Consumes: `migrate_csv_content` (`src/plan_data_migration.py:108`, currently uncalled), `needs_migration` / `set_stored_schema_version` (Task 4)
- Produces: `migrate_plan_data_at_rest(input_dir, db_path=None, dry_run=False) -> dict` returning
  `{"migrated": {filename: changed_count}, "total_changed": int, "skipped": bool}`

Rewrites each sectioned Plan Data CSV in place through `migrate_csv_content`, then stamps the version. Files with 0 changes are never rewritten, so mtimes and the `plan_data_manifest.json` hashes stay stable for untouched files. `dry_run=True` reports without writing — needed by Task 6's logging and safe to call anywhere.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_plan_data_migration.py`:

```python
def _legacy_csv() -> str:
    return (
        "section,subsection,label,value,units,notes\n"
        "Household,,husband_name,Matt,text,\n"
        "Household,,wife_dob,1975-01-01,date,\n"
    )


def test_runner_rewrites_legacy_csv_and_stamps_version():
    import tempfile
    from pathlib import Path
    from src.plan_data_migration import (
        PLAN_DATA_SCHEMA_VERSION, migrate_plan_data_at_rest, stored_schema_version,
    )
    work = Path(tempfile.mkdtemp())
    db = work / "s.sqlite"
    (work / "client_household.csv").write_text(_legacy_csv(), encoding="utf-8")

    report = migrate_plan_data_at_rest(work, db_path=db)

    text = (work / "client_household.csv").read_text(encoding="utf-8")
    assert "member_1_name" in text and "husband_name" not in text
    assert "member_2_dob" in text and "wife_dob" not in text
    assert report["total_changed"] == 2
    assert stored_schema_version(db_path=db) == PLAN_DATA_SCHEMA_VERSION


def test_runner_is_idempotent_and_skips_when_already_current():
    import tempfile
    from pathlib import Path
    from src.plan_data_migration import migrate_plan_data_at_rest
    work = Path(tempfile.mkdtemp())
    db = work / "s.sqlite"
    (work / "client_household.csv").write_text(_legacy_csv(), encoding="utf-8")

    migrate_plan_data_at_rest(work, db_path=db)
    first = (work / "client_household.csv").read_text(encoding="utf-8")
    second_report = migrate_plan_data_at_rest(work, db_path=db)

    assert second_report["skipped"] is True
    assert (work / "client_household.csv").read_text(encoding="utf-8") == first


def test_dry_run_reports_without_writing():
    import tempfile
    from pathlib import Path
    from src.plan_data_migration import migrate_plan_data_at_rest, stored_schema_version
    work = Path(tempfile.mkdtemp())
    db = work / "s.sqlite"
    (work / "client_household.csv").write_text(_legacy_csv(), encoding="utf-8")

    report = migrate_plan_data_at_rest(work, db_path=db, dry_run=True)

    assert report["total_changed"] == 2
    assert "husband_name" in (work / "client_household.csv").read_text(encoding="utf-8")
    assert stored_schema_version(db_path=db) == 0


def test_already_current_file_is_not_rewritten():
    import tempfile
    from pathlib import Path
    from src.plan_data_migration import migrate_plan_data_at_rest
    work = Path(tempfile.mkdtemp())
    db = work / "s.sqlite"
    current = (
        "section,subsection,label,value,units,notes\n"
        "Household,,member_1_name,Matt,text,\n"
    )
    target = work / "client_household.csv"
    target.write_text(current, encoding="utf-8")
    before_mtime = target.stat().st_mtime_ns

    report = migrate_plan_data_at_rest(work, db_path=db)

    assert report["total_changed"] == 0
    assert target.stat().st_mtime_ns == before_mtime
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
py -3.14 -m pytest tests/test_plan_data_migration.py -q
```

Expected: FAIL — `ImportError: cannot import name 'migrate_plan_data_at_rest'`.

- [ ] **Step 3: Implement the runner**

Append to `src/plan_data_migration.py`:

```python
def migrate_plan_data_at_rest(input_dir, db_path=None, dry_run: bool = False) -> dict:
    """Migrate every sectioned Plan Data CSV under ``input_dir`` once, in place.

    Returns ``{"migrated": {name: changed}, "total_changed": int, "skipped": bool}``.

    Only files that actually change are rewritten, so untouched files keep their
    mtime and their plan_data_manifest.json hash. When the store is already
    stamped at the current schema version this is a no-op (``skipped=True``).
    ``dry_run=True`` reports what would change without writing or stamping.
    """
    from pathlib import Path

    if not dry_run and not needs_migration(db_path=db_path):
        return {"migrated": {}, "total_changed": 0, "skipped": True}

    root = Path(input_dir)
    migrated: dict = {}
    total = 0
    for path in sorted(root.glob("*.csv")):
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        new_content, changed = migrate_csv_content(content)
        if not changed:
            continue
        migrated[path.name] = changed
        total += changed
        if not dry_run:
            path.write_text(new_content, encoding="utf-8", newline="")

    if not dry_run:
        set_stored_schema_version(PLAN_DATA_SCHEMA_VERSION, db_path=db_path)
    return {"migrated": migrated, "total_changed": total, "skipped": False}
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
py -3.14 -m pytest tests/test_plan_data_migration.py -q
```

Expected: 12 passed.

- [ ] **Step 5: Commit**

```bash
git add src/plan_data_migration.py tests/test_plan_data_migration.py
git commit -m "feat: add one-shot at-rest plan data migration runner"
```

---

### Task 6: Wire the migration into startup

**Files:**
- Modify: `src/server/app_core.py` (startup path)
- Test: `tests/test_plan_data_migration.py` (append)

**Interfaces:**
- Consumes: `migrate_plan_data_at_rest` (Task 5)
- Produces: `run_startup_plan_data_migration() -> dict` — same report shape as the runner; safe to call repeatedly.

Startup must never be blocked by a migration failure: a corrupt CSV should degrade to the existing per-load `migrate_sectioned_data` normalization, not a dead server.

- [ ] **Step 1: Locate the startup hook**

```bash
cd "C:/RetirementPlanning/Version 10"
grep -n "def create_app\|startup\|init_local_store" src/server/app_core.py | head -20
```

Note the function that already runs once at boot; the call goes at its end, after store init.

- [ ] **Step 2: Write the failing test**

Append to `tests/test_plan_data_migration.py`:

```python
def test_startup_migration_is_safe_when_input_dir_is_missing():
    """A missing/unreadable input dir must not raise -- startup would die."""
    import tempfile
    from pathlib import Path
    from src.plan_data_migration import migrate_plan_data_at_rest
    work = Path(tempfile.mkdtemp())
    report = migrate_plan_data_at_rest(work / "does_not_exist", db_path=work / "s.sqlite")
    assert report["total_changed"] == 0


def test_startup_migration_survives_an_undecodable_csv():
    import tempfile
    from pathlib import Path
    from src.plan_data_migration import migrate_plan_data_at_rest
    work = Path(tempfile.mkdtemp())
    (work / "broken.csv").write_bytes(b"\xff\xfe\x00\x00not utf8")
    (work / "client_household.csv").write_text(
        "section,subsection,label,value,units,notes\n"
        "Household,,husband_name,Matt,text,\n",
        encoding="utf-8",
    )
    report = migrate_plan_data_at_rest(work, db_path=work / "s.sqlite")
    assert report["total_changed"] == 1  # good file still migrated
```

- [ ] **Step 3: Run the test to verify it fails or passes**

```bash
py -3.14 -m pytest tests/test_plan_data_migration.py -q
```

Expected: PASS if Task 5's `except (OSError, UnicodeDecodeError)` and `glob` already cover these; if either FAILS, fix `migrate_plan_data_at_rest` (a missing dir makes `glob` yield nothing — confirm, don't assume) before continuing.

- [ ] **Step 4: Add the startup wrapper**

Append to `src/plan_data_migration.py`:

```python
def run_startup_plan_data_migration(input_dir=None, db_path=None) -> dict:
    """Startup entry point: migrate stored Plan Data once, never fatally.

    Any failure degrades to the existing per-load ``migrate_sectioned_data``
    normalization, which still yields correct reads -- a bad CSV must not stop
    the server from booting.
    """
    try:
        if input_dir is None:
            from .platform_runtime import PROJECT_ROOT
            input_dir = PROJECT_ROOT / "input"
        return migrate_plan_data_at_rest(input_dir, db_path=db_path)
    except Exception:
        return {"migrated": {}, "total_changed": 0, "skipped": True}
```

Verify the `PROJECT_ROOT` import path first — `src/local_store.py` imports `platform_runtime`; confirm it exposes `PROJECT_ROOT`:

```bash
grep -n "PROJECT_ROOT" src/platform_runtime.py | head -3
```

If the name differs, use whatever `local_store.py` uses to locate the project root.

- [ ] **Step 5: Call it from startup**

In `src/server/app_core.py`, at the end of the boot function found in Step 1:

```python
    from ..plan_data_migration import run_startup_plan_data_migration
    _migration_report = run_startup_plan_data_migration()
    if _migration_report["total_changed"]:
        print(f"Plan Data migrated at rest: {_migration_report['migrated']}")
```

- [ ] **Step 6: Verify the server still boots and the suite is green**

```bash
RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS=1 py -3.14 -m pytest tests/ -q > /tmp/p2.txt 2>&1
grep -E "^FAILED|^ERROR" /tmp/p2.txt || echo "no failures"
git status --porcelain
```

Expected: no FAILED lines. **Critically**: confirm `input/*.csv` were NOT rewritten by the startup migration during the run — the live plan is already in current shape, so `total_changed` should be 0 against real inputs. If `git status` shows migrated `input/` files, inspect the diff before committing; that means real legacy rows were found and the rewrite is legitimate but must be reviewed.

- [ ] **Step 7: Commit**

```bash
git add src/plan_data_migration.py src/server/app_core.py tests/test_plan_data_migration.py
git commit -m "feat: run the at-rest plan data migration once at startup"
```

---

## Phase 3 — wellness → healthcare (Data at Rest Only)

**Scope decision (2026-08-10):** data-at-rest labels only. Python identifiers are explicitly OUT of scope — ~140 occurrences across `src/` (60 in `projection_stages/deterministic_engine.py`, 25 in `planning_engines.py`, 13 each in `sheets_stress.py` / `sheets_projection_cashflow.py`) carry real engine-regression risk against the pins Phase 1 just reset. Renaming CSV labels while leaving the Python identifiers alone is safe **only** because `migrate_sectioned_data` maps old→new on load, so the engine keeps reading the key it always read.

**This phase is decision-gated.** Task 7 produces the inventory; do not write transforms before its output is reviewed.

### Task 7: Inventory the wellness namespaces and choose the rename set

**Files:**
- Read only: `input/*.csv`
- Create: `docs/superpowers/plans/2026-08-10-wellness-rename-inventory.md`

**Interfaces:**
- Consumes: nothing
- Produces: the exact `{(section, subsection): {old_label: new_label}}` mapping Task 8 pastes into `_LABEL_RENAMES`.

At least three distinct namespaces exist and they are NOT one rename:
1. Monte Carlo shock params in `client_household.csv` — `wellness_cost_shocks`, `wellness_shock_annual_prob`, `wellness_shock_mean_cost` (section `Model Constants`, subsection `Monte Carlo`)
2. The spending category `pre65_wellness_premium` (appears in `client_spending_taxonomy.csv`, `spending_category_map.csv`, `client_spending_budget.csv`)
3. Prose in `notes` columns and section headers (e.g. "Wellness Budget Detail") — **not** keys; renaming these changes no behavior and can be done freely or skipped

- [ ] **Step 1: Dump every wellness-bearing row with its full key**

```bash
cd "C:/RetirementPlanning/Version 10"
for f in input/*.csv; do
  awk -F, -v F="$f" 'tolower($0) ~ /wellness/ {print F": "$1" | "$2" | "$3}' "$f"
done | sort -u
```

- [ ] **Step 2: Separate keys from prose**

Column 3 is the `label` (the key). A wellness hit in columns 4+ only (`notes`) is prose. Build two lists.

- [ ] **Step 3: Write the inventory document**

Record, for each real key: file, section, subsection, old label, proposed new label, and every `src/` reader of that key (`grep -rn "<label>" src/`). A key with an `src/` reader is safe to rename at rest ONLY because the load-path migration remaps it — note that reader explicitly so the next engineer sees why the Python side is untouched.

- [ ] **Step 4: Get the rename set approved**

Present the inventory. Confirm the new label names (`healthcare_cost_shocks`, `pre65_healthcare_premium`, …) and whether prose is in or out. **Stop here** until confirmed.

- [ ] **Step 5: Commit the inventory**

```bash
git add docs/superpowers/plans/2026-08-10-wellness-rename-inventory.md
git commit -m "docs: inventory the wellness->healthcare rename surface"
```

---

### Task 8: Add the wellness label renames

**Files:**
- Modify: `src/plan_data_migration.py:28-45` (`_LABEL_RENAMES`)
- Test: `tests/test_plan_data_migration.py` (append)

**Interfaces:**
- Consumes: Task 7's approved mapping; existing `_LABEL_RENAMES` / `_target_key` machinery
- Produces: no new functions — extends the existing table, so `migrate_rows`, `migrate_csv_content`, `migrate_sectioned_data`, and the Task 5 runner all pick it up for free.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_plan_data_migration.py`, substituting Task 7's approved labels:

```python
def test_wellness_monte_carlo_params_migrate_to_healthcare():
    from src.plan_data_migration import migrate_rows
    rows = [
        ["section", "subsection", "label", "value", "units", "notes"],
        ["Model Constants", "Monte Carlo", "wellness_cost_shocks", "TRUE", "boolean", ""],
        ["Model Constants", "Monte Carlo", "wellness_shock_mean_cost", "$150,000", "USD", ""],
    ]
    out, changed = migrate_rows(rows)
    labels = [r[2] for r in out]
    assert "healthcare_cost_shocks" in labels
    assert "healthcare_shock_mean_cost" in labels
    assert not any("wellness" in l for l in labels)
    assert changed == 2


def test_wellness_migration_respects_current_key_wins():
    """A legacy row colliding with an existing current row is DROPPED."""
    from src.plan_data_migration import migrate_rows
    rows = [
        ["section", "subsection", "label", "value", "units", "notes"],
        ["Model Constants", "Monte Carlo", "healthcare_cost_shocks", "FALSE", "boolean", ""],
        ["Model Constants", "Monte Carlo", "wellness_cost_shocks", "TRUE", "boolean", ""],
    ]
    out, _ = migrate_rows(rows)
    values = [r[3] for r in out if r[2] == "healthcare_cost_shocks"]
    assert values == ["FALSE"]  # current row survived, legacy dropped


def test_wellness_migration_applies_to_sectioned_data_too():
    from src.plan_data_migration import migrate_sectioned_data
    data = {"Model Constants": {"Monte Carlo": {"wellness_cost_shocks": "TRUE"}}}
    out, changed = migrate_sectioned_data(data)
    assert out["Model Constants"]["Monte Carlo"]["healthcare_cost_shocks"] == "TRUE"
    assert "wellness_cost_shocks" not in out["Model Constants"]["Monte Carlo"]
    assert changed == 1
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
py -3.14 -m pytest tests/test_plan_data_migration.py -q -k wellness
```

Expected: FAIL — labels still contain `wellness`.

- [ ] **Step 3: Extend `_LABEL_RENAMES`**

Add to the dict at `src/plan_data_migration.py:28`, using Task 7's approved set:

```python
    ("Model Constants", "Monte Carlo"): {
        "wellness_cost_shocks": "healthcare_cost_shocks",
        "wellness_shock_annual_prob": "healthcare_shock_annual_prob",
        "wellness_shock_mean_cost": "healthcare_shock_mean_cost",
    },
```

Note: `("Model Constants", "Retirement")` already exists as a separate key — add this as a NEW entry, do not overwrite it.

- [ ] **Step 4: Run the test to verify it passes**

```bash
py -3.14 -m pytest tests/test_plan_data_migration.py -q
```

Expected: all pass (15 tests).

- [ ] **Step 5: Commit**

```bash
git add src/plan_data_migration.py tests/test_plan_data_migration.py
git commit -m "feat: migrate wellness_* plan-data labels to healthcare_*"
```

---

### Task 9: Bump the schema version and migrate the live data

**Files:**
- Modify: `src/plan_data_migration.py:24` (`PLAN_DATA_SCHEMA_VERSION`)
- Modify: `input/*.csv` (the actual rewrite)
- Modify: `input/plan_data_manifest.json` (hashes change for rewritten files)

**Interfaces:**
- Consumes: Tasks 4-6 (gate + runner + startup wiring), Task 8 (the renames)
- Produces: live Plan Data at schema version 3.

Bumping the version is what makes already-stamped stores re-run. Without it, any store stamped at 2 by Phase 2 would skip the new wellness transform forever.

- [ ] **Step 1: Bump the version**

At `src/plan_data_migration.py:24`:

```python
# Bump when a new transform is added so the version-gated startup migration
# re-runs against already-stored plans.
# v3 (2026-08-10): wellness_* -> healthcare_* label renames.
PLAN_DATA_SCHEMA_VERSION = 3
```

- [ ] **Step 2: Dry-run against the real input directory first**

```bash
cd "C:/RetirementPlanning/Version 10"
py -3.14 -c "
from pathlib import Path
from src.plan_data_migration import migrate_plan_data_at_rest
r = migrate_plan_data_at_rest(Path('input'), dry_run=True)
print(r)
"
```

Expected: a report naming each affected CSV and its change count. Confirm the file list matches Task 7's inventory. **If a file appears that the inventory did not predict, stop and re-check the mapping.**

- [ ] **Step 3: Apply for real**

```bash
py -3.14 -c "
from pathlib import Path
from src.plan_data_migration import migrate_plan_data_at_rest
print(migrate_plan_data_at_rest(Path('input')))
"
git diff --stat -- input/
```

- [ ] **Step 4: Regenerate the Plan Data manifest**

The manifest hashes CSV bytes, so every rewritten file invalidates it.

```bash
grep -rn "def main\|__main__" tools/check_plan_data_sync.py | head -5
py -3.14 tools/check_plan_data_sync.py --regenerate 2>&1 | tail -5
```

If `--regenerate` is not a supported flag, read the tool for its documented regeneration path and use that.

- [ ] **Step 5: Full suite, twice**

Run twice: the first proves correctness, the second proves the migration is idempotent and did not leave the store re-migrating on every boot.

```bash
RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS=1 py -3.14 -m pytest tests/ -q > /tmp/p3a.txt 2>&1
grep -E "^FAILED|^ERROR" /tmp/p3a.txt || echo "run 1 clean"
RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS=1 py -3.14 -m pytest tests/ -q > /tmp/p3b.txt 2>&1
grep -E "^FAILED|^ERROR" /tmp/p3b.txt || echo "run 2 clean"
```

Expected: no FAILED lines in either. The frozen golden master must still match Phase 1's pins — the wellness rename is a pure key rename with a load-path remap, so terminal NW **must not move**. If it does, the rename hit a key the engine reads under a different path; revert and revisit Task 7.

- [ ] **Step 6: Commit**

```bash
git add src/plan_data_migration.py input/ tests/
git commit -m "feat: bump plan data schema to v3 and migrate wellness->healthcare at rest

Rewrites the stored Plan Data CSVs through the v3 transform and regenerates
plan_data_manifest.json. Python identifiers are deliberately unchanged --
migrate_sectioned_data remaps old->new on load, so the engine keeps reading
the keys it always read. Frozen golden-master pins unchanged, as expected
for a pure key rename."
```

---

## Self-Review

**Spec coverage:**
- Golden master red on `main` → Tasks 1-2 ✓
- Persisted startup migration + version gate → Tasks 3-6 ✓
- wellness→healthcare → Tasks 7-9, data-at-rest scope per the 2026-08-10 decision ✓

**Known gaps, deliberately left open:**
- Task 6 Step 1 requires locating the boot function in `app_core.py` rather than naming a line — the file was not read while writing this plan, so a hardcoded line number would be a guess. The grep is exact.
- Task 9 Step 4's manifest regeneration flag is unverified; the step says to read the tool if the flag is wrong rather than inventing one.
- Task 8's new labels are placeholders pending Task 7 approval; every occurrence is marked "substitute Task 7's approved labels" rather than presented as final.

**Type consistency:** `migrate_plan_data_at_rest` returns the same `{"migrated", "total_changed", "skipped"}` dict in Tasks 5, 6, and 9. `stored_schema_version` / `set_stored_schema_version` / `needs_migration` keep the same `db_path=None` keyword across Tasks 4-6. `get_local_setting(key, default, db_path)` matches its Task 3 definition at both Task 4 call sites.
