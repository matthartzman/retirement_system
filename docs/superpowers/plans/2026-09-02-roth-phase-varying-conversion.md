# Roth phase-varying conversion candidate (item 3.2 Option 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new, fully configurable `PHASE_VARYING` Roth conversion strategy — fills one bracket rate until the first Social Security claim year, a second rate until the second claim year (optional), then a third rate through the conversion window end — selectable directly via `roth_bracket_strategy` and included in the `OPTIMIZER_CHOOSES` full sweep.

**Architecture:** A `roth_phase_schedule` list of `(end_year, rate)` tuples flows from config → candidate spec `overrides` → `plan_roth_conversion`'s per-year rate resolution. A pre-existing gap (candidate `overrides` beyond `target_rate`/`fixed_amount` were never re-applied to the real config after winner selection) is fixed as part of this change since the new feature depends on it.

**Tech Stack:** Python 3.14, pytest. No new dependencies.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-09-02-roth-phase-varying-conversion-design.md` (read this first — it has the full rationale for every design decision below).
- Out of scope: window extension to plan end, DOB-aware/survivor window extension, the `400000` bracket-top fallback fix (separate line items in review finding F3/item 3.2).
- Do NOT edit `input/client_policy.csv` (gitignored live data) or `tests/fixtures/sample_plan_frozen/client_policy.csv` (golden-master fixture — editing it requires the regen ceremony in `documentation/GOLDEN_MASTER_RECOVERY_RUNBOOK.md`, which this change does not warrant since `_v(..., default)` already covers the missing-row case identically).
- Golden master must not move. Verify with `python -m tests.test_frozen_sample_plan_golden_master_regression` after each engine-touching task; if it reports different figures than before your change, STOP and investigate before continuing (per `documentation/CLAUDE.md`'s golden master maintenance section) — do not re-pin.
- Run the fast tier (`pytest tests/ -m "not slow" --tb=short -q`) after every task. Run the full suite (`pytest tests/ -n auto --tb=short -q`) at the end (Task 6), per `documentation/CLAUDE.md`'s testing-discipline table (this touches `src/planning_engines.py`, the tax/conversion engine).
- Every new test file follows the repo's naming convention: `test_<succinct_scope>_<type>.py`, no wave/item/phase number in the filename (`tests/test_no_tracking_id_test_names_regression.py` enforces this mechanically).

---

### Task 1: `_roth_resolve_target_rate` helper + wire into `plan_roth_conversion`

**Files:**
- Modify: `src/planning_engines.py:1877` (inside `plan_roth_conversion`)
- Modify: `src/planning_engines.py` (add new helper function just above `plan_roth_conversion`, i.e. immediately before line 1821 `def plan_roth_conversion(`)
- Test: `tests/test_roth_phase_varying_conversion_unit.py` (new file)

**Interfaces:**
- Produces: `_roth_resolve_target_rate(c: Mapping, year: int, default_rate: float) -> float`, module-level in `src/planning_engines.py`. Later tasks read `c['roth_phase_schedule']` (a `list[tuple[int, float]]`, ascending by `end_year`) as the input this function consumes.

- [x] **Step 1: Write the failing tests**

Create `tests/test_roth_phase_varying_conversion_unit.py`:

```python
"""Item 3.2 Option 2 (docs/superpowers/specs/2026-09-02-roth-phase-varying-
conversion-design.md): a configurable PHASE_VARYING Roth conversion strategy
that steps its target bracket rate down by Social Security claim year.
"""
from __future__ import annotations

import pytest

from conftest import TEST_INPUT_DIR
from src.data_io import load_csv, parse_client
import src.planning_engines as planning_engines
from src.planning_engines import (
    _roth_resolve_target_rate,
    optimize_roth_conversion_strategy,
    project,
)


def _base_config():
    c = parse_client(load_csv(TEST_INPUT_DIR / "client_data.csv"), "")
    c["roth_policy"] = "none"
    c["plan_end"] = min(int(c["plan_end"]), int(c["plan_start"]) + 10)
    c["mc_sensitivity_sims"] = 1
    c["mc_wellness_shocks"] = False
    return c


def test_resolve_target_rate_no_schedule_returns_default():
    assert _roth_resolve_target_rate({}, 2030, 0.24) == 0.24


def test_resolve_target_rate_picks_first_boundary_at_or_after_year():
    c = {"roth_phase_schedule": [(2030, 0.24), (2035, 0.22), (2040, 0.12)]}
    assert _roth_resolve_target_rate(c, 2025, 0.99) == 0.24
    assert _roth_resolve_target_rate(c, 2030, 0.99) == 0.24
    assert _roth_resolve_target_rate(c, 2031, 0.99) == 0.22
    assert _roth_resolve_target_rate(c, 2035, 0.99) == 0.22


def test_resolve_target_rate_uses_last_rate_past_final_boundary():
    c = {"roth_phase_schedule": [(2030, 0.24), (2035, 0.22)]}
    assert _roth_resolve_target_rate(c, 2036, 0.99) == 0.22
    assert _roth_resolve_target_rate(c, 2099, 0.99) == 0.22


def test_resolve_target_rate_single_tuple_schedule():
    c = {"roth_phase_schedule": [(2030, 0.24)]}
    assert _roth_resolve_target_rate(c, 2025, 0.99) == 0.24
    assert _roth_resolve_target_rate(c, 2031, 0.99) == 0.24


def test_plan_roth_conversion_flat_rate_unaffected_by_new_helper():
    # No roth_phase_schedule set (every existing candidate) -- confirm the
    # rewrite of the target_rate line in plan_roth_conversion changed nothing
    # about default flat-rate fill_to_bracket behavior.
    c = _base_config()
    c["roth_policy"] = "fill_to_bracket"
    c["roth_bracket_strategy"] = "FILL_TARGET_BRACKET"
    rows = project(c)
    assert any(float(r.get("roth_conversion", 0.0) or 0.0) > 0 for r in rows)
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_roth_phase_varying_conversion_unit.py -v`
Expected: `ImportError: cannot import name '_roth_resolve_target_rate'` (function does not exist yet). The last test may also fail/error for the same import reason — that's fine, all failures are expected at this point.

- [x] **Step 3: Add the helper and wire it in**

In `src/planning_engines.py`, immediately before `def plan_roth_conversion(` (currently line 1821), add:

```python
def _roth_resolve_target_rate(c: Mapping, year: int, default_rate: float) -> float:
    """Return the Roth target bracket rate for `year`.

    `c['roth_phase_schedule']`, when present, is a list of `(end_year, rate)`
    tuples in ascending `end_year` order. The rate for the first tuple whose
    `end_year >= year` applies; years beyond the last tuple use its rate.
    Absent a schedule, every existing (flat-rate) candidate is unaffected.
    """
    schedule = c.get('roth_phase_schedule')
    if not schedule:
        return default_rate
    for end_year, rate in schedule:
        if year <= end_year:
            return float(rate)
    return float(schedule[-1][1])
```

Then inside `plan_roth_conversion`, replace the line (currently line 1877):

```python
    target_rate = float(c.get("roth_target_rate", c.get("roth_brk", 0.24)) or 0.24)
```

with:

```python
    target_rate = _roth_resolve_target_rate(
        c, year, float(c.get("roth_target_rate", c.get("roth_brk", 0.24)) or 0.24)
    )
```

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_roth_phase_varying_conversion_unit.py -v`
Expected: PASS (all 5 tests)

- [x] **Step 5: Golden master check**

Run: `python -m tests.test_frozen_sample_plan_golden_master_regression`
Expected: prints the same `PINNED_TERMINAL_NW`/`PINNED_LIFETIME_TAX` values already pinned in that file (no schedule is ever set today, so `_roth_resolve_target_rate` always falls into the `if not schedule: return default_rate` branch — byte-identical to the old line).

- [x] **Step 6: Fast tier**

Run: `pytest tests/ -m "not slow" --tb=short -q`
Expected: PASS, no new failures.

- [x] **Step 7: Commit**

```bash
git add src/planning_engines.py tests/test_roth_phase_varying_conversion_unit.py
git commit -m "$(cat <<'EOF'
Add _roth_resolve_target_rate for phase-varying Roth conversion rates (3.2 Option 2, step 1/5)

Introduces the per-year rate-resolution mechanism that later steps will
feed a roth_phase_schedule into. No behavior change today: absent a
schedule, this returns the same default_rate the old flat line computed.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: SS-claim-year computation + `PHASE_VARYING` candidate generation

**Files:**
- Modify: `src/planning_engines.py:2239-2302` (`_roth_strategy_candidate_specs`)
- Test: `tests/test_roth_phase_varying_conversion_unit.py` (append)

**Interfaces:**
- Consumes: nothing new from Task 1 (this task's code runs independently — Task 1's helper is consumed at scoring/projection time, not at spec-generation time).
- Produces: `_roth_strategy_candidate_specs(c)` now yields an additional spec dict `{'label': ..., 'policy': 'fill_to_bracket', 'strategy_code': 'PHASE_VARYING', 'target_rate': None, 'fixed_amount': None, 'overrides': {'roth_phase_schedule': [...]}}` whenever `full_set` is true or `selected == 'PHASE_VARYING'`. Later tasks (3, 4) rely on `strategy_code == 'PHASE_VARYING'` and the `roth_phase_schedule` override key.
- Consumes new config keys (read via `c.get(key, default)`, so no data_io.py change is required for this task to work standalone): `roth_phase_rate_1`/`roth_phase_rate_2`/`roth_phase_rate_3` (floats, defaults `0.24`/`0.22`/`0.12`), `roth_phase_count` (int, default `3`), plus existing `h_dob_yr`/`w_dob_yr`/`h_ss_claim_age`/`w_ss_claim_age`/`members` (already set by `parse_client`).

- [x] **Step 1: Write the failing tests**

Append to `tests/test_roth_phase_varying_conversion_unit.py`:

```python
from src.planning_engines import _roth_strategy_candidate_specs, conversion_window_end_year


def _phase_varying_spec(specs):
    matches = [s for s in specs if s.get('strategy_code') == 'PHASE_VARYING']
    assert len(matches) == 1, f"expected exactly one PHASE_VARYING spec, got {len(matches)}"
    return matches[0]


def test_phase_varying_absent_when_bracket_strategy_is_something_else():
    c = _base_config()
    c["roth_bracket_strategy"] = "FILL_TARGET_BRACKET"
    specs = _roth_strategy_candidate_specs(c)
    assert not any(s.get('strategy_code') == 'PHASE_VARYING' for s in specs)


def test_phase_varying_present_in_full_optimizer_sweep():
    c = _base_config()
    c["roth_bracket_strategy"] = "OPTIMIZER_CHOOSES"
    specs = _roth_strategy_candidate_specs(c)
    spec = _phase_varying_spec(specs)
    assert spec['policy'] == 'fill_to_bracket'
    assert spec['target_rate'] is None
    assert 'roth_phase_schedule' in spec['overrides']


def test_phase_varying_selectable_directly():
    c = _base_config()
    c["roth_bracket_strategy"] = "PHASE_VARYING"
    specs = _roth_strategy_candidate_specs(c)
    assert len(specs) == 1
    _phase_varying_spec(specs)


def test_phase_varying_three_phase_schedule_for_couple_with_distinct_claim_years():
    # Frozen fixture: h_dob_yr=1962, w_dob_yr=1961, both claim_age=69 ->
    # w claims 2030, h claims 2031 (distinct years, w first).
    c = _base_config()
    c["roth_bracket_strategy"] = "PHASE_VARYING"
    c["roth_phase_count"] = 3
    spec = _phase_varying_spec(_roth_strategy_candidate_specs(c))
    schedule = spec['overrides']['roth_phase_schedule']
    window_end = conversion_window_end_year(c)
    assert schedule == [(2030, 0.24), (2031, 0.22), (window_end, 0.12)]


def test_phase_varying_two_phase_schedule_when_configured():
    c = _base_config()
    c["roth_bracket_strategy"] = "PHASE_VARYING"
    c["roth_phase_count"] = 2
    spec = _phase_varying_spec(_roth_strategy_candidate_specs(c))
    schedule = spec['overrides']['roth_phase_schedule']
    window_end = conversion_window_end_year(c)
    assert schedule == [(2030, 0.24), (window_end, 0.22)]


def test_phase_varying_three_phase_degrades_to_two_for_single_member_household():
    c = _base_config()
    c["roth_bracket_strategy"] = "PHASE_VARYING"
    c["roth_phase_count"] = 3
    c["members"] = [c["members"][0]]  # simulate single-member household
    spec = _phase_varying_spec(_roth_strategy_candidate_specs(c))
    schedule = spec['overrides']['roth_phase_schedule']
    window_end = conversion_window_end_year(c)
    assert schedule == [(2031, 0.24), (window_end, 0.22)]


def test_phase_varying_three_phase_degrades_to_two_for_same_claim_year_couple():
    c = _base_config()
    c["roth_bracket_strategy"] = "PHASE_VARYING"
    c["roth_phase_count"] = 3
    c["w_dob_yr"] = c["h_dob_yr"]
    c["w_ss_claim_age"] = c["h_ss_claim_age"]
    spec = _phase_varying_spec(_roth_strategy_candidate_specs(c))
    schedule = spec['overrides']['roth_phase_schedule']
    window_end = conversion_window_end_year(c)
    assert schedule == [(2031, 0.24), (window_end, 0.22)]


def test_phase_varying_uses_configured_rates():
    c = _base_config()
    c["roth_bracket_strategy"] = "PHASE_VARYING"
    c["roth_phase_count"] = 2
    c["roth_phase_rate_1"] = 0.32
    c["roth_phase_rate_2"] = 0.24
    spec = _phase_varying_spec(_roth_strategy_candidate_specs(c))
    schedule = spec['overrides']['roth_phase_schedule']
    assert schedule[0][1] == 0.32
    assert schedule[1][1] == 0.24


def test_phase_varying_minimal_config_never_crashes():
    # A hand-built Mapping missing h_dob_yr/h_ss_claim_age/members entirely
    # still yields a valid (if degenerate) schedule, never a crash.
    c = {"roth_bracket_strategy": "PHASE_VARYING", "roth_policy": "none",
         "plan_start": 2026, "roth_max_conversion_years": 10,
         "rmd_start_age": 75, "conv_window_offset": -1,
         "roth_fixed_amount": 50000, "roth_target_rate": 0.22}
    spec = _phase_varying_spec(_roth_strategy_candidate_specs(c))
    schedule = spec['overrides']['roth_phase_schedule']
    assert len(schedule) == 2
    assert schedule[0][1] == 0.24
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_roth_phase_varying_conversion_unit.py -v`
Expected: FAIL — no `PHASE_VARYING` spec is ever produced (`_phase_varying_spec` raises the assertion), and `test_phase_varying_selectable_directly` fails since `selected == 'PHASE_VARYING'` isn't a recognized value yet (falls through to the empty-specs `if not specs: add('No voluntary conversions', ...)` default, so `len(specs) == 1` may accidentally pass but the strategy_code will be `'NONE'`, not `'PHASE_VARYING'` — `_phase_varying_spec` catches that).

- [x] **Step 3: Implement candidate generation**

In `src/planning_engines.py`, inside `_roth_strategy_candidate_specs`, immediately after the line (currently line 2267):

```python
    selected = str(c.get('roth_bracket_strategy', 'OPTIMIZER_CHOOSES') or 'OPTIMIZER_CHOOSES').strip().upper()
```

add:

```python
    # c['h_ss_start']/c['w_ss_start'] do NOT exist on the canonical CSV-driven
    # `c` (parse_client() never sets them -- only the separate/legacy
    # build_plan_from_json() loader does). Compute directly from the fields
    # parse_client() does set: h_dob_yr/w_dob_yr, h_ss_claim_age/w_ss_claim_age,
    # and members (len 1 for a single-member household, 2 for a couple -- the
    # single-member path mirrors w_dob_yr onto h_dob_yr, so gate on
    # len(members) rather than comparing dob years).
    _ss_years = [int(c.get('h_dob_yr', 0) or 0) + int(c.get('h_ss_claim_age', 70) or 70)]
    if len(c.get('members', []) or []) > 1:
        _ss_years.append(int(c.get('w_dob_yr', 0) or 0) + int(c.get('w_ss_claim_age', 70) or 70))
    _ss_years = sorted(set(_ss_years))
    _window_end = conversion_window_end_year(c)

    def _phase_varying_schedule():
        r1 = float(c.get('roth_phase_rate_1', 0.24) or 0.24)
        r2 = float(c.get('roth_phase_rate_2', 0.22) or 0.22)
        r3 = float(c.get('roth_phase_rate_3', 0.12) or 0.12)
        phase_count = int(float(c.get('roth_phase_count', 3) or 3))
        first = _ss_years[0]
        if phase_count == 3 and len(_ss_years) >= 2:
            second = _ss_years[1]
            return [(first, r1), (second, r2), (_window_end, r3)]
        return [(first, r1), (_window_end, r2)]
```

Then, immediately after the existing `FIXED_DOLLAR` block (currently lines 2290-2293):

```python
    if full_set or selected == 'FIXED_DOLLAR':
        for amt in (25000.0, 50000.0, configured_fixed, 75000.0, 100000.0, 150000.0, 200000.0, 250000.0, 300000.0):
            if amt > 0:
                add(f'Fixed ${amt:,.0f}/yr', 'fixed_dollar', fixed_amount=amt, strategy_code=f'FIXED_DOLLAR_{int(amt)}')
```

add:

```python
    if full_set or selected == 'PHASE_VARYING':
        _sched = _phase_varying_schedule()
        _rates_label = ' → '.join(f'{int(r*100)}%' for _y, r in _sched)
        add(f'Phase-varying ({_rates_label} by SS claim year)', 'fill_to_bracket',
            strategy_code='PHASE_VARYING', overrides={'roth_phase_schedule': _sched})
```

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_roth_phase_varying_conversion_unit.py -v`
Expected: PASS (all tests from Task 1 and Task 2)

- [x] **Step 5: Golden master check**

Run: `python -m tests.test_frozen_sample_plan_golden_master_regression`
Expected: unchanged figures — the frozen fixture's `roth_bracket_strategy` is `FILL_TARGET_BRACKET` (not `OPTIMIZER_CHOOSES` or `PHASE_VARYING`), so `full_set` is `False` and `selected == 'PHASE_VARYING'` is `False`; the new `if` block's `add(...)` never executes for that fixture.

- [x] **Step 6: Fast tier**

Run: `pytest tests/ -m "not slow" --tb=short -q`
Expected: PASS, no new failures.

- [x] **Step 7: Commit**

```bash
git add src/planning_engines.py tests/test_roth_phase_varying_conversion_unit.py
git commit -m "$(cat <<'EOF'
Add PHASE_VARYING Roth conversion candidate generation (3.2 Option 2, step 2/5)

Computes SS claim years directly from parse_client()'s canonical fields
(h_dob_yr/w_dob_yr + h_ss_claim_age/w_ss_claim_age + members), since
h_ss_start/w_ss_start only exist on the separate build_plan_from_json()
loader. Generates a 2- or 3-phase schedule from configurable rates,
gracefully degrading 3-phase to 2-phase for a single-member household or
a couple claiming in the same year.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Config plumbing in `data_io.py`

**Files:**
- Modify: `src/data_io.py:1438-1446`
- Test: `tests/test_roth_phase_varying_conversion_unit.py` (append)

**Interfaces:**
- Consumes: none new.
- Produces: `parse_client(...)` now sets `c['roth_phase_rate_1']`/`c['roth_phase_rate_2']`/`c['roth_phase_rate_3']` (floats) and `c['roth_phase_count']` (int, `2` or `3`) on every parsed config, and accepts `'PHASE_VARYING'` as a valid `c['roth_bracket_strategy']` value. Task 2's `_roth_strategy_candidate_specs` already reads these same keys via `c.get(key, default)`, so this task only needs to confirm the real parser produces the same defaults (and would honor a CSV override, once one exists).

- [x] **Step 1: Write the failing tests**

Append to `tests/test_roth_phase_varying_conversion_unit.py`:

```python
def test_parse_client_sets_phase_config_defaults():
    c = _base_config()
    assert c['roth_phase_rate_1'] == pytest.approx(0.24)
    assert c['roth_phase_rate_2'] == pytest.approx(0.22)
    assert c['roth_phase_rate_3'] == pytest.approx(0.12)
    assert c['roth_phase_count'] == 3


def test_parse_client_accepts_phase_varying_as_bracket_strategy():
    from src.data_io import load_csv, parse_client as _parse_client
    raw = load_csv(TEST_INPUT_DIR / "client_data.csv")
    # Directly inject the CSV row parse_client() reads via _v(), mirroring
    # how the frozen fixture's own client_policy.csv rows are structured.
    raw['Withdrawal Policy']['Roth Conversion']['roth_bracket_strategy'] = 'PHASE_VARYING'
    c = _parse_client(raw, "")
    assert c['roth_bracket_strategy'] == 'PHASE_VARYING'
```

- [x] **Step 2: Run tests to verify they fail (partially)**

Run: `pytest tests/test_roth_phase_varying_conversion_unit.py -v`
Expected: `test_parse_client_sets_phase_config_defaults` FAILS with `KeyError: 'roth_phase_rate_1'`. `test_parse_client_accepts_phase_varying_as_bracket_strategy` FAILS because `'PHASE_VARYING'` isn't in the validation tuple yet, so it silently falls back to `'OPTIMIZER_CHOOSES'`.

(`load_csv()`, `src/data_io.py:275-292`, returns exactly `{section: {subsection: {label: value}}}` — confirmed by reading its source — so the direct-dict injection `raw['Withdrawal Policy']['Roth Conversion']['roth_bracket_strategy'] = 'PHASE_VARYING'` in the second test is correct as written.)

- [x] **Step 3: Implement the parsing**

In `src/data_io.py`, replace (currently lines 1438-1441):

```python
    _roth_bracket_strategy = str(_v(data,'Withdrawal Policy','Roth Conversion',
                                   'roth_bracket_strategy','OPTIMIZER_CHOOSES') or 'OPTIMIZER_CHOOSES').strip().upper()
    if _roth_bracket_strategy not in ('NONE','FILL_CURRENT_BRACKET','FILL_TARGET_BRACKET','PARTIAL_TARGET_BRACKET','IRMAA_GUARDED','SURVIVOR_TAX_AWARE','RMD_REDUCTION','LEGACY_TARGETED','OPTIMIZER_CHOOSES','FIXED_DOLLAR'):
        _roth_bracket_strategy = 'OPTIMIZER_CHOOSES'
```

with:

```python
    _roth_bracket_strategy = str(_v(data,'Withdrawal Policy','Roth Conversion',
                                   'roth_bracket_strategy','OPTIMIZER_CHOOSES') or 'OPTIMIZER_CHOOSES').strip().upper()
    if _roth_bracket_strategy not in ('NONE','FILL_CURRENT_BRACKET','FILL_TARGET_BRACKET','PARTIAL_TARGET_BRACKET','IRMAA_GUARDED','SURVIVOR_TAX_AWARE','RMD_REDUCTION','LEGACY_TARGETED','OPTIMIZER_CHOOSES','FIXED_DOLLAR','PHASE_VARYING'):
        _roth_bracket_strategy = 'OPTIMIZER_CHOOSES'
```

Then, immediately after the line (currently line 1446):

```python
    c['roth_target_rate'] = percent_to_float(_v(data,'Withdrawal Policy','Roth Conversion',
                                   'roth_target_bracket_rate','0.22'), 0.22)
```

add:

```python
    c['roth_phase_rate_1'] = percent_to_float(_v(data,'Withdrawal Policy','Roth Conversion',
                                   'roth_phase_first_bracket_rate','24.00%'), 0.24)
    c['roth_phase_rate_2'] = percent_to_float(_v(data,'Withdrawal Policy','Roth Conversion',
                                   'roth_phase_second_bracket_rate','22.00%'), 0.22)
    c['roth_phase_rate_3'] = percent_to_float(_v(data,'Withdrawal Policy','Roth Conversion',
                                   'roth_phase_third_bracket_rate','12.00%'), 0.12)
    try:
        c['roth_phase_count'] = int(_n(_v(data,'Withdrawal Policy','Roth Conversion',
                                   'roth_phase_count','3'), 3))
    except Exception:
        c['roth_phase_count'] = 3
    if c['roth_phase_count'] not in (2, 3):
        c['roth_phase_count'] = 3
```

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_roth_phase_varying_conversion_unit.py -v`
Expected: PASS (all tests from Tasks 1-3)

- [x] **Step 5: Golden master check**

Run: `python -m tests.test_frozen_sample_plan_golden_master_regression`
Expected: unchanged — new fields default to values equal to what `_phase_varying_schedule` already assumed via `c.get(key, default)` in Task 2, and the frozen fixture's `roth_bracket_strategy` stays `FILL_TARGET_BRACKET`.

- [x] **Step 6: Fast tier**

Run: `pytest tests/ -m "not slow" --tb=short -q`
Expected: PASS, no new failures.

- [x] **Step 7: Commit**

```bash
git add src/data_io.py tests/test_roth_phase_varying_conversion_unit.py
git commit -m "$(cat <<'EOF'
Parse phase-varying Roth conversion config fields in data_io.py (3.2 Option 2, step 3/5)

roth_phase_first/second/third_bracket_rate and roth_phase_count now parse
into c['roth_phase_rate_1/2/3'] and c['roth_phase_count'], matching the
defaults Task 2's candidate generator already assumed. PHASE_VARYING is
now a valid roth_bracket_strategy value.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Winner-overrides propagation fix

**Files:**
- Modify: `src/planning_engines.py:2813-2853` (`optimize_roth_conversion_strategy`)
- Test: `tests/test_roth_phase_varying_conversion_unit.py` (append)

**Interfaces:**
- Consumes: `_roth_strategy_candidate_specs` (Task 2) — this task's tests monkeypatch it directly for speed/determinism rather than relying on real scoring outcomes.
- Produces: after `optimize_roth_conversion_strategy(c)` returns, `c` carries every key in the selected candidate's `overrides` dict (not just `target_rate`/`fixed_amount`), in both the `auto_optimize` and explicit-selection branches.

- [x] **Step 1: Write the failing tests**

Append to `tests/test_roth_phase_varying_conversion_unit.py`:

```python
def _fake_specs_with_phase_varying_only(schedule):
    return [{
        'label': 'Phase test', 'policy': 'fill_to_bracket', 'strategy_code': 'PHASE_VARYING',
        'target_rate': None, 'fixed_amount': None,
        'overrides': {'roth_phase_schedule': schedule},
    }]


def test_auto_optimize_propagates_full_overrides_not_just_target_rate(monkeypatch):
    c = _base_config()
    c['roth_policy'] = 'optimize_terminal_tax'  # auto_optimize branch
    schedule = [(int(c['plan_start']) + 3, 0.24), (int(c['plan_start']) + 8, 0.12)]
    monkeypatch.setattr(
        planning_engines, '_roth_strategy_candidate_specs',
        lambda cfg: _fake_specs_with_phase_varying_only(schedule),
    )
    c = optimize_roth_conversion_strategy(c)
    assert c['roth_optimization']['selected_strategy_code'] == 'PHASE_VARYING'
    assert c['roth_phase_schedule'] == schedule


def test_direct_selection_propagates_full_overrides_not_just_target_rate(monkeypatch):
    c = _base_config()
    c['roth_policy'] = 'fill_to_bracket'  # explicit-selection branch (not auto_optimize)
    c['roth_bracket_strategy'] = 'PHASE_VARYING'
    schedule = [(int(c['plan_start']) + 3, 0.24), (int(c['plan_start']) + 8, 0.12)]
    monkeypatch.setattr(
        planning_engines, '_roth_strategy_candidate_specs',
        lambda cfg: _fake_specs_with_phase_varying_only(schedule),
    )
    c = optimize_roth_conversion_strategy(c)
    assert c['roth_optimization']['selected_strategy_code'] == 'PHASE_VARYING'
    assert c['roth_phase_schedule'] == schedule
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_roth_phase_varying_conversion_unit.py -v`
Expected: both new tests FAIL with `KeyError: 'roth_phase_schedule'` — `c['roth_optimization']['selected_strategy_code']` will already read `'PHASE_VARYING'` correctly (that part of the code is unaffected), but `c['roth_phase_schedule']` itself is never set on the real `c`.

- [x] **Step 3: Implement the fix**

In `src/planning_engines.py`, the `if auto_optimize: ... else: ...` block (currently lines 2815-2853) ends with:

```python
        c['roth_policy_requested'] = requested_policy

    # Item 4.3: surface the effective (derived-or-overridden) heir/terminal
```

Insert one line right after `c['roth_policy_requested'] = requested_policy` (the one that closes the `else` branch, i.e. immediately before the blank line and the `# Item 4.3` comment):

```python
        c['roth_policy_requested'] = requested_policy

    if selected.get('overrides'):
        c.update(selected['overrides'])

    # Item 4.3: surface the effective (derived-or-overridden) heir/terminal
```

Note the indentation: the new two lines sit at the same (outer) indent level as `if auto_optimize:`/`else:` themselves, not nested inside either branch — they run once, after both branches have set `selected`.

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_roth_phase_varying_conversion_unit.py -v`
Expected: PASS (all tests from Tasks 1-4)

- [x] **Step 5: Golden master check**

Run: `python -m tests.test_frozen_sample_plan_golden_master_regression`
Expected: unchanged. The frozen fixture's selected candidate (`FILL_TARGET_BRACKET_*`, built via `add(...)` with no `overrides=` argument) has `spec.get('overrides') or {}` == `{}`, so `c.update({})` is a no-op for it regardless of branch.

- [x] **Step 6: Fast tier**

Run: `pytest tests/ -m "not slow" --tb=short -q`
Expected: PASS, no new failures. Pay particular attention to any existing test involving `SURVIVOR_TAX_AWARE`, `RMD_REDUCTION`, or `LEGACY_TARGETED` selection — this fix now propagates their overrides too (previously silently dropped); if any existing test asserted the *old* (buggy) behavior, it will need updating to reflect the fix, not be treated as a regression to revert. Search first: `grep -rn "SURVIVOR_TAX_AWARE\|RMD_REDUCTION\|LEGACY_TARGETED" tests/`.

- [x] **Step 7: Commit**

```bash
git add src/planning_engines.py tests/test_roth_phase_varying_conversion_unit.py
git commit -m "$(cat <<'EOF'
Propagate winning Roth candidate's full overrides to the real config (3.2 Option 2, step 4/5)

optimize_roth_conversion_strategy() only ever re-applied target_rate/
fixed_amount from the selected candidate onto the real projection config,
in both the auto_optimize and explicit-selection branches -- any other
override (roth_survivor_tax_risk_weight, roth_max_conversion_years,
roth_legacy_objective_mode, and now roth_phase_schedule) was silently
dropped before the real projection ran. PHASE_VARYING needs this to work
at all when selected; this also retroactively fixes the same gap for
SURVIVOR_TAX_AWARE, RMD_REDUCTION, and LEGACY_TARGETED.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: UI and reference-data plumbing

**Files:**
- Modify: `src/server/app_core.py:753-779` (`ROTH_UI_PLAN_DATA_ROWS`), `src/server/app_core.py:1202-1217` (`_choice_options_for_config_row`'s `fixed` dict)
- Modify: `frontend/js/dashboard.js:2161-2172` (`roth_bracket_strategy` choice array), `frontend/js/dashboard.js:3020-3028` (`ROTH_PRIMARY_LABELS`), `frontend/js/dashboard.js:6341-6346` (STEP_HELP entries, insert after `roth_optimize_terminal_weight`)
- Modify: `input/demo/client_policy.csv`, `reference_data/schema.csv`
- Test: `tests/test_roth_user_ui_render_fix.py` (append)

**Interfaces:** none — this task is UI/config surface only, no new Python/JS functions.

- [x] **Step 1: Write the failing tests**

Append to `tests/test_roth_user_ui_render_fix.py`:

```python
def test_phase_varying_added_to_bracket_strategy_choice_enum():
    js = dashboard_js_text()
    assert '"PHASE_VARYING"' in js
    app_core = (ROOT / 'src/server/app_core.py').read_text(encoding='utf-8')
    assert '"PHASE_VARYING"' in app_core
    data_io = (ROOT / 'src/data_io.py').read_text(encoding='utf-8')
    assert "'PHASE_VARYING'" in data_io


def test_phase_varying_config_fields_present_in_schema_and_backfill():
    labels = set()
    with (ROOT / 'reference_data/schema.csv').open(newline='', encoding='utf-8') as f:
        for row in csv.reader(f):
            if len(row) > 2:
                labels.add(row[2])
    expected = {
        'roth_phase_first_bracket_rate', 'roth_phase_second_bracket_rate',
        'roth_phase_third_bracket_rate', 'roth_phase_count',
    }
    assert expected <= labels

    app_core = (ROOT / 'src/server/app_core.py').read_text(encoding='utf-8')
    for label in expected:
        assert label in app_core

    with (ROOT / 'input/demo/client_policy.csv').open(newline='', encoding='utf-8-sig') as f:
        demo_rows = list(csv.DictReader(f))
    demo_labels = {
        r['label'] for r in demo_rows
        if r['section'] == 'Withdrawal Policy' and r['subsection'] == 'Roth Conversion'
    }
    assert expected <= demo_labels


def test_phase_varying_labels_grouped_with_roth_primary_controls():
    js = dashboard_js_text()
    assert '"roth_phase_first_bracket_rate"' in js
    assert '"roth_phase_second_bracket_rate"' in js
    assert '"roth_phase_third_bracket_rate"' in js
    assert '"roth_phase_count"' in js
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_roth_user_ui_render_fix.py -v`
Expected: all three new tests FAIL (none of the strings exist yet).

- [x] **Step 3a: `src/server/app_core.py`**

Add `"PHASE_VARYING"` to the `roth_bracket_strategy` choice list at (currently line 1210):

```python
        "roth_bracket_strategy": ["NONE", "FILL_CURRENT_BRACKET", "FILL_TARGET_BRACKET", "PARTIAL_TARGET_BRACKET", "IRMAA_GUARDED", "SURVIVOR_TAX_AWARE", "RMD_REDUCTION", "LEGACY_TARGETED", "OPTIMIZER_CHOOSES", "FIXED_DOLLAR", "PHASE_VARYING"],
```

Update the row string at (currently line 757) inside `ROTH_UI_PLAN_DATA_ROWS`:

```python
    ["Withdrawal Policy", "Roth Conversion", "roth_bracket_strategy", "OPTIMIZER_CHOOSES", "choice", "NONE | FILL_CURRENT_BRACKET | FILL_TARGET_BRACKET | PARTIAL_TARGET_BRACKET | IRMAA_GUARDED | SURVIVOR_TAX_AWARE | RMD_REDUCTION | LEGACY_TARGETED | OPTIMIZER_CHOOSES | FIXED_DOLLAR | PHASE_VARYING; strategy family considered by the Roth optimizer."],
```

Then, immediately after the line (currently line 761):

```python
    ["Withdrawal Policy", "Roth Conversion", "roth_target_bracket_rate", "22.00%", "choice", "10.00% | 12.00% | 22.00% | 24.00% | 32.00% | 35.00% | 37.00%; Target marginal bracket ceiling used by bracket-fill policies."],
```

add:

```python
    ["Withdrawal Policy", "Roth Conversion", "roth_phase_first_bracket_rate", "24.00%", "choice", "10.00% | 12.00% | 22.00% | 24.00% | 32.00% | 35.00% | 37.00%; PHASE_VARYING strategy only -- bracket rate to fill until the first Social Security claim year."],
    ["Withdrawal Policy", "Roth Conversion", "roth_phase_second_bracket_rate", "22.00%", "choice", "10.00% | 12.00% | 22.00% | 24.00% | 32.00% | 35.00% | 37.00%; PHASE_VARYING strategy only -- bracket rate for the next phase (second SS claim year if roth_phase_count is 3, otherwise the window end)."],
    ["Withdrawal Policy", "Roth Conversion", "roth_phase_third_bracket_rate", "12.00%", "choice", "10.00% | 12.00% | 22.00% | 24.00% | 32.00% | 35.00% | 37.00%; PHASE_VARYING strategy only -- bracket rate for the final phase through the conversion window end. Unused when roth_phase_count is 2."],
    ["Withdrawal Policy", "Roth Conversion", "roth_phase_count", "3", "choice", "2 | 3; PHASE_VARYING strategy only -- number of rate phases. 2 steps down once, at the first SS claim year. 3 steps down twice, at each spouse's SS claim year (degrades to 2 automatically for a single-member household or same-year claimants)."],
```

**Step 3b: `frontend/js/dashboard.js`**

Add `"PHASE_VARYING"` to the `roth_bracket_strategy` array at (currently lines 2161-2172):

```javascript
    roth_bracket_strategy: [
      "NONE",
      "FILL_CURRENT_BRACKET",
      "FILL_TARGET_BRACKET",
      "PARTIAL_TARGET_BRACKET",
      "IRMAA_GUARDED",
      "SURVIVOR_TAX_AWARE",
      "RMD_REDUCTION",
      "LEGACY_TARGETED",
      "OPTIMIZER_CHOOSES",
      "FIXED_DOLLAR",
      "PHASE_VARYING",
    ],
```

Add the 4 new labels to `ROTH_PRIMARY_LABELS` at (currently lines 3020-3028), right after `"roth_bracket_strategy",`:

```javascript
const ROTH_PRIMARY_LABELS = [
  "roth_conversion_policy",
  "roth_bracket_strategy",
  "roth_phase_first_bracket_rate",
  "roth_phase_second_bracket_rate",
  "roth_phase_third_bracket_rate",
  "roth_phase_count",
  "roth_headroom_usage_pct",
  "roth_target_bracket_rate",
  "roth_fixed_annual_amount",
  "max_annual_conversion_pct_of_traditional_ira",
  "max_conversion_years",
];
```

Add STEP_HELP entries, inserted alphabetically between the `roth_optimize_terminal_weight` entry and the `roth_target_bracket_rate` entry (currently right after line 6345's closing `},`):

```javascript
  roth_phase_count: {
    purpose: "If you're using the PHASE_VARYING strategy, this is how many rate phases the plan uses: 2 (fill one rate until your Social Security claim, then a second rate) or 3 (fill one rate until the first spouse's SS claim, a second rate until the second spouse's claim, then a third rate).",
    impact: "3 phases lets the plan step your conversion rate down twice as each spouse's SS income arrives, narrowing your bracket headroom. 2 phases uses one step-down at the first claim year, which is simpler and fine for a single filer or spouses claiming in the same year.",
    consider: "Use 3 if you and your spouse claim Social Security in different years and want the plan to react to each one separately. Use 2 for a single filer or if you just want one clean step-down.",
  },
  roth_phase_first_bracket_rate: {
    purpose: "If you're using the PHASE_VARYING strategy, this is the tax bracket the plan fills with conversions before your first Social Security claim year, when you typically have the most bracket headroom.",
    impact: "A higher rate converts more aggressively in these early, lower-income years. A lower rate is more conservative.",
    consider: "This is usually the highest of the three phase rates, since pre-Social-Security years tend to have the most room before other income fills your bracket.",
  },
  roth_phase_second_bracket_rate: {
    purpose: "If you're using the PHASE_VARYING strategy, this is the tax bracket the plan fills after the first phase ends -- either through the second spouse's Social Security claim year (roth_phase_count = 3) or through the end of the conversion window (roth_phase_count = 2).",
    impact: "As Social Security income arrives, your remaining bracket headroom typically shrinks -- a lower rate here reflects that. A higher rate keeps converting aggressively despite the added income.",
    consider: "Usually set lower than roth_phase_first_bracket_rate, reflecting less headroom once Social Security income is flowing.",
  },
  roth_phase_third_bracket_rate: {
    purpose: "If you're using the PHASE_VARYING strategy with roth_phase_count = 3, this is the tax bracket the plan fills after both spouses have claimed Social Security, through the end of the conversion window. Unused when roth_phase_count = 2.",
    impact: "This is typically the most constrained phase -- both Social Security streams and any RMDs are competing for bracket room -- so a lower rate here is common.",
    consider: "Usually the lowest of the three phase rates. If RMDs are close behind, keep this conservative to avoid overshooting into a bracket you can't afford.",
  },
```

**Step 3c: `input/demo/client_policy.csv` and `reference_data/schema.csv`**

In `input/demo/client_policy.csv`, find the `roth_bracket_strategy` row and append ` | PHASE_VARYING` to its choice-list cell (before the trailing `; strategy family...` description text), matching the exact edit made to `ROTH_UI_PLAN_DATA_ROWS` in Step 3a. Then add 4 new rows immediately after the `roth_target_bracket_rate` row, matching that row's column format exactly (`Withdrawal Policy,Roth Conversion,<label>,<default>,choice,<choice-list>; <description>,`):

```csv
Withdrawal Policy,Roth Conversion,roth_phase_first_bracket_rate,24.00%,choice,10.00% | 12.00% | 22.00% | 24.00% | 32.00% | 35.00% | 37.00%; PHASE_VARYING strategy only -- bracket rate to fill until the first Social Security claim year.,
Withdrawal Policy,Roth Conversion,roth_phase_second_bracket_rate,22.00%,choice,10.00% | 12.00% | 22.00% | 24.00% | 32.00% | 35.00% | 37.00%; PHASE_VARYING strategy only -- bracket rate for the next phase (second SS claim year if roth_phase_count is 3, otherwise the window end).,
Withdrawal Policy,Roth Conversion,roth_phase_third_bracket_rate,12.00%,choice,10.00% | 12.00% | 22.00% | 24.00% | 32.00% | 35.00% | 37.00%; PHASE_VARYING strategy only -- bracket rate for the final phase through the conversion window end. Unused when roth_phase_count is 2.,
Withdrawal Policy,Roth Conversion,roth_phase_count,3,choice,2 | 3; PHASE_VARYING strategy only -- number of rate phases (degrades to 2 automatically for a single-member household or same-year claimants).,
```

In `reference_data/schema.csv`, find the `roth_bracket_strategy` row (currently line 115) and append `| PHASE_VARYING` to its choice list (9th column), matching the file's `Section,Subsection,label,type,required,default,min,max,help` format. Then add 4 new rows immediately after the `roth_target_bracket_rate` row (currently line 116):

```csv
Withdrawal Policy,Roth Conversion,roth_phase_first_bracket_rate,choice,FALSE,24.00%,,,"10.00% | 12.00% | 22.00% | 24.00% | 32.00% | 35.00% | 37.00%; PHASE_VARYING strategy only -- bracket rate to fill until the first Social Security claim year."
Withdrawal Policy,Roth Conversion,roth_phase_second_bracket_rate,choice,FALSE,22.00%,,,"10.00% | 12.00% | 22.00% | 24.00% | 32.00% | 35.00% | 37.00%; PHASE_VARYING strategy only -- bracket rate for the next phase (second SS claim year if roth_phase_count is 3, otherwise the window end)."
Withdrawal Policy,Roth Conversion,roth_phase_third_bracket_rate,choice,FALSE,12.00%,,,"10.00% | 12.00% | 22.00% | 24.00% | 32.00% | 35.00% | 37.00%; PHASE_VARYING strategy only -- bracket rate for the final phase through the conversion window end. Unused when roth_phase_count is 2."
Withdrawal Policy,Roth Conversion,roth_phase_count,choice,FALSE,3,,,"2 | 3; PHASE_VARYING strategy only -- number of rate phases (degrades to 2 automatically for a single-member household or same-year claimants)."
```

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_roth_user_ui_render_fix.py -v`
Expected: PASS (all tests, including the 3 new ones)

- [x] **Step 5: Fast tier**

Run: `pytest tests/ -m "not slow" --tb=short -q`
Expected: PASS, no new failures.

- [x] **Step 6: Commit**

```bash
git add src/server/app_core.py frontend/js/dashboard.js input/demo/client_policy.csv reference_data/schema.csv tests/test_roth_user_ui_render_fix.py
git commit -m "$(cat <<'EOF'
Wire PHASE_VARYING Roth strategy into UI, backfill, and reference schema (3.2 Option 2, step 5/5)

Adds PHASE_VARYING to every place the roth_bracket_strategy enum is
enumerated (dashboard.js dropdown, app_core.py choices + backfill rows),
groups its 4 new config fields with the other primary Roth controls in
the dashboard, and documents them in reference_data/schema.csv and
input/demo/client_policy.csv. Deliberately does not touch the gitignored
live input/client_policy.csv or the golden-master test fixture -- see
the design spec's "Deliberately not touched" note.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Final verification

**Files:** none (verification only)

**Interfaces:** none

- [x] **Step 1: Golden master, one more time**

Run: `python -m tests.test_frozen_sample_plan_golden_master_regression`
Expected: figures identical to the value pinned in `tests/test_frozen_sample_plan_golden_master_regression.py` before Task 1 started.

- [x] **Step 2: Fast tier**

Run: `pytest tests/ -m "not slow" --tb=short -q`
Expected: PASS, 0 failures.

- [x] **Step 3: Full suite**

Run: `pytest tests/ -n auto --tb=short -q`
Expected: PASS, 0 failures. If `pytest-xdist` isn't installed, fall back to `pytest tests/ --tb=short -q` (serial; slower but equivalent coverage).

- [x] **Step 4: Regression tooling**

Run: `python tools/run_regression.py`
Expected: PASS (static-analysis checks, e.g. dead-code/wave-number-in-filename scans, not exercised by pytest).

- [x] **Step 5: Confirm git status is clean**

Run: `git status`
Expected: working tree clean (everything from Tasks 1-5 already committed); no stray modified files (e.g. accidentally-touched `input/client_policy.csv` from a local run against the live workspace).

## Completion notes (deviations found during execution)

All 6 tasks completed and committed. Three deviations from the plan's expectations, all resolved:

1. **`tests/test_synthetic_golden_master.py` (mandatory gate) moved.** The plan's "no golden master risk" claim only checked the frozen sample-plan gate. This separate, mandatory synthetic gate has 9 scenarios that all default to `roth_bracket_strategy=OPTIMIZER_CHOOSES`, and `RMD_REDUCTION` wins that sweep in every one — so the Task 4 overrides-propagation fix (a real, confirmed bug fix) changed its pinned figures. Isolated via selective revert (reverting only the fix restores the old values exactly; `PHASE_VARYING` never wins any of these 9 scenarios) and confirmed internally consistent (fewer converted years → larger first RMD, lower lifetime tax, higher terminal NW — exactly what "a conversion-year cap that should apply is now actually applied" predicts). Regenerated and committed with user sign-off; documented in the design spec's Task 4 section.

2. **`pytest -n auto` (xdist parallel) produced ~30 spurious ERRORs** in workbook-build-dependent tests — the documented Windows file-lock flake pattern from `documentation/CLAUDE.md` ("If a failure under `-n auto` is a `PermissionError`/`WinError 5`..."). Confirmed by running one of the failing tests in isolation (passed) and by rerunning the full suite serially (`pytest tests/ --tb=short -q`, no `-n`), which showed only the 3 pre-existing failures below. Not a regression.

3. **3 pre-existing, unrelated test failures** present at the branch point (commit `111ecb0`, before any task started) and confirmed via `git log`/`git show` to belong to other in-progress work already merged into this branch, not to this change:
   - `test_after_tax_cap_gain_estate_regression.py::test_frontend_after_tax_description_mentions_capital_gains`
   - `test_dual_column_reporting_regression.py::test_sheet1_shows_terminal_nw_todays_dollars_row`
   - `test_frontend_size_ratchet.py::test_dashboard_js_does_not_grow` — already 48 lines over its ratchet before this branch (`git show 111ecb0:frontend/js/dashboard.js | wc -l` = 7552 vs. the 7504 max). Task 5's UI wiring added ~25 more lines on top (now 7577), making an already-broken ratchet moderately worse. Flagging for the user — not fixed here, since the fix (extracting dashboard.js content into a module) is unrelated, out-of-scope refactoring work.
   - `tools/run_regression.py` also has 1 pre-existing unrelated failure: `P1-B1: guarded setStep defined in navigation module` — the check's expected string (`"function setStep(ctx,id)"`) predates a parameter this repo's `setStep` already had (`ctx,id,opts`) at commit `111ecb0`, before this branch started.

Golden master (`tests/test_frozen_sample_plan_golden_master_regression.py`) verified unchanged after every task: `PINNED_TERMINAL_NW = 5763251.84`, `PINNED_LIFETIME_TAX = 1316887.09`.
