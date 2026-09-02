# Roth phase-varying conversion candidate (item 3.2 Option 2)

Date: 2026-09-02
Status: Approved for planning

## Background

`documentation/reports/SYSTEM_REVIEW_2026-08-31.md` §Wave 3, item 3.2 bundles several
Roth-conversion-window fixes under finding F3. Option 2 of that item —
"Add explicit named phase candidates (e.g. 'fill 24% until SS claim, then 22% to RMD
age')" — was explicitly deferred as separately-scoped follow-on work; the rest of 3.2
(window extension to plan end, DOB-aware window, survivor-window extension, the
hardcoded `400000` bracket-top fallback fix) is **out of scope** for this spec.

Today, every Roth conversion strategy candidate in
`_roth_strategy_candidate_specs()` ([src/planning_engines.py:2239](../../../src/planning_engines.py))
applies one constant target bracket rate (or one fixed dollar amount) across the
entire conversion window. No candidate varies its rate by phase of retirement, even
though planners routinely describe strategies exactly that way — fill a higher
bracket while pre-Social-Security headroom is large, then step down once SS income
narrows that headroom.

## Goal

Add one new, fully user-configurable Roth conversion strategy — `PHASE_VARYING` —
that fills a configured bracket rate up through each member's Social Security claim
year, then steps down to the next configured rate, with either one or two step-downs
(configurable). It must be:
- selectable directly as `roth_bracket_strategy=PHASE_VARYING` (like
  `FILL_CURRENT_BRACKET` today), and
- included automatically whenever `roth_bracket_strategy=OPTIMIZER_CHOOSES` runs the
  full candidate sweep.

## Non-goals

- Extending the conversion window itself (3.2 Option 1 / the rest of finding F3).
- Fixing the `400000` bracket-top fallback (separate line item in the same review row).
- A phase boundary anywhere other than Social Security claim year (RMD-age or
  survivor-transition phase splits are not requested here).
- Multiple hardcoded named candidates (e.g. a fixed "24→22" and a separate fixed
  "22→12"). Superseded by one configurable candidate once rates became
  user-configurable — see "Design evolution" below.

## Design evolution (why one candidate, not three)

The original design (three fixed named candidates: 2-phase-high 24→22, 2-phase-low
22→12, 3-phase-staggered 24→22→12) was revised after the user asked for the rates
and step count to be configurable. Once rates are config-driven, generating three
separate hardcoded-rate candidates alongside a configurable one would be redundant
and confusing. A single configurable candidate, selectable directly, is consistent
with how every other named strategy in this file works (e.g.
`FILL_CURRENT_BRACKET` uses `c['roth_target_rate']` rather than hardcoding a rate).

## Configuration

Four new rows under `Withdrawal Policy / Roth Conversion` in `client_policy.csv`
(and its mirrors — see "Files touched"):

| CSV label | Default | Type | Parsed into |
|---|---|---|---|
| `roth_phase_first_bracket_rate` | `24.00%` | percent choice (same rate list as `roth_target_bracket_rate`: 10/12/22/24/32/35/37%) | `c['roth_phase_rate_1']` |
| `roth_phase_second_bracket_rate` | `22.00%` | percent choice | `c['roth_phase_rate_2']` |
| `roth_phase_third_bracket_rate` | `12.00%` | percent choice | `c['roth_phase_rate_3']` |
| `roth_phase_count` | `3` | choice: `2 \| 3` | `c['roth_phase_count']` |

`roth_phase_count=2`: fill `roth_phase_rate_1` until the first SS claim year, then
`roth_phase_rate_2` through the window end. `roth_phase_rate_3` is unused.

`roth_phase_count=3`: fill `roth_phase_rate_1` until the first SS claim year, then
`roth_phase_rate_2` until the second SS claim year, then `roth_phase_rate_3` through
the window end. If the household has only one distinct SS claim year available (a
single-member household, or both members claiming in the same year), this degrades
to the same schedule as `roth_phase_count=2` using `roth_phase_rate_1`/`roth_phase_rate_2`
(the second boundary collapses onto the first, so `roth_phase_rate_2` never has a
year range to apply to — `roth_phase_rate_3` is silently unused for that household,
not an error).

`PHASE_VARYING` is added as a 10th value to the existing `roth_bracket_strategy`
choice enum (`NONE | FILL_CURRENT_BRACKET | FILL_TARGET_BRACKET |
PARTIAL_TARGET_BRACKET | IRMAA_GUARDED | SURVIVOR_TAX_AWARE | RMD_REDUCTION |
LEGACY_TARGETED | OPTIMIZER_CHOOSES | FIXED_DOLLAR`).

## Engine changes (`src/planning_engines.py`)

### 1. Rate resolution inside `plan_roth_conversion`

Add a module-level helper:

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

Replace the current line

```python
target_rate = float(c.get("roth_target_rate", c.get("roth_brk", 0.24)) or 0.24)
```

with

```python
target_rate = _roth_resolve_target_rate(
    c, year, float(c.get("roth_target_rate", c.get("roth_brk", 0.24)) or 0.24)
)
```

No other line in `plan_roth_conversion` needs to change — `top_target`,
`bracket_room`, and everything downstream already key off `target_rate`.

### 2. Candidate generation inside `_roth_strategy_candidate_specs`

Compute once, near the top of the function (after `selected`/`full_set` are
established):

```python
_ss_years = sorted({int(y) for y in (c.get('h_ss_start'), c.get('w_ss_start')) if y and int(y) < 9999})
_window_end = conversion_window_end_year(c)

def _phase_varying_schedule():
    if not _ss_years:
        return None
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

Then, alongside the other `if full_set or selected == '...':` blocks:

```python
if full_set or selected == 'PHASE_VARYING':
    _sched = _phase_varying_schedule()
    if _sched:
        _rates_label = ' → '.join(f'{int(r*100)}%' for _y, r in _sched)
        add(f'Phase-varying ({_rates_label} by SS claim year)', 'fill_to_bracket',
            strategy_code='PHASE_VARYING', overrides={'roth_phase_schedule': _sched})
```

`target_rate` is intentionally left `None` in the `add(...)` call (this candidate
has no single rate); the existing `spec.get('target_rate') is not None` guards at
call sites already handle `None` correctly (they just skip setting
`roth_target_rate`/`roth_brk` from the spec, which is correct here — the schedule
overrides them).

If `_ss_years` is empty (no SS claim data at all — a legacy/synthetic config), no
`PHASE_VARYING` candidate is added, even if explicitly selected via
`roth_bracket_strategy` — degrade to no voluntary conversions is *not* automatic
here, so add a defensive fallback: when `selected == 'PHASE_VARYING'` and `_sched`
is `None`, fall through to behave like `FILL_CURRENT_BRACKET` (reuse
`configured_target`) rather than silently producing zero candidates. This mirrors
how other strategies never produce an empty candidate list for an explicit
selection.

### 3. Winner-overrides propagation fix

`selected['overrides']` (built in `_roth_strategy_candidate_specs`) is only ever
applied to a scratch copy `c2` during scoring (`run_scenario(base, overrides)`,
[planning_engines.py:2790](../../../src/planning_engines.py)) — the real `c` used
for the final projection never receives it, in **either** branch:

- `auto_optimize` (`OPTIMIZER_CHOOSES`) branch: re-applies only
  `selected['target_rate']`/`selected['fixed_amount']` onto `c`
  ([planning_engines.py:2820-2824](../../../src/planning_engines.py)).
- `else` (explicit `roth_bracket_strategy` selection) branch: doesn't touch `c`
  from `selected` at all beyond what was already there — `selected` is used only
  to populate the disclosure/reporting dict below.

So today, any strategy whose candidate spec carries an `overrides` entry beyond
`target_rate`/`fixed_amount` — `SURVIVOR_TAX_AWARE` (`roth_survivor_tax_risk_weight`),
`RMD_REDUCTION` (`roth_max_conversion_years`), `LEGACY_TARGETED`
(`roth_legacy_objective_mode`) — has that override silently dropped before the real
projection runs, whether it's chosen by the optimizer or picked directly by the
planner. `PHASE_VARYING`'s `roth_phase_schedule` would hit the exact same gap.

Fix: after `selected` is finalized (i.e. after the `if auto_optimize: ... else: ...`
block, both branches converged), add one unconditional line:

```python
if selected.get('overrides'):
    c.update(selected['overrides'])
```

This covers both branches in one place and retroactively fixes the silent-drop bug
for the three existing strategies as well as `PHASE_VARYING`, for both direct
selection and `OPTIMIZER_CHOOSES`. No golden master risk: the frozen fixture pins
`roth_bracket_strategy=FILL_TARGET_BRACKET`, whose candidate spec carries no
`overrides` beyond `target_rate` (`{}` after the `target_rate`/`fixed_amount`
keys are excluded — `add()` for `FILL_TARGET_BRACKET_*` passes no `overrides`
argument), so `c.update({})` is a no-op for that fixture regardless of branch.

## Files touched

- `src/planning_engines.py` — `_roth_resolve_target_rate`, `_roth_strategy_candidate_specs`,
  `optimize_roth_conversion_strategy` (as above)
- `src/data_io.py` — parse the 4 new config fields into `c`; add `PHASE_VARYING` to
  the `roth_bracket_strategy` validation list (~line 1440)
- `src/server/app_core.py` — default-row seed string (~line 757) and choices list
  (~line 1210) both gain `PHASE_VARYING`; add the 4 new default rows to the seed table
- `frontend/js/dashboard.js` — `roth_bracket_strategy` dropdown array (~line 2161)
  gains `"PHASE_VARYING"`; add UI rows/help text for the 4 new fields following the
  existing pattern for `roth_target_bracket_rate` et al.
- `input/client_policy.csv`, `input/demo/client_policy.csv`,
  `tests/fixtures/sample_plan_frozen/client_policy.csv`, `reference_data/schema.csv`
  — append `PHASE_VARYING` to the existing choice string on the
  `roth_bracket_strategy` row; add the 4 new rows
- `python tools/check_plan_data_sync.py --write` — resync `plan_data_manifest`
  after the schema change

## Testing

- `_roth_resolve_target_rate`: no schedule → `default_rate`; year before/at/after
  each boundary; single-tuple schedule.
- `_phase_varying_schedule` / `_roth_strategy_candidate_specs`:
  - `roth_phase_count=2` → 2-tuple schedule ending at the first SS claim year.
  - `roth_phase_count=3` with two distinct claim years → 3-tuple schedule.
  - `roth_phase_count=3` with one claim year (or a single-member household) →
    degrades to the 2-tuple schedule.
  - No SS claim data at all: `PHASE_VARYING` absent from `full_set`; explicit
    selection falls back to `FILL_CURRENT_BRACKET`-equivalent behavior rather than
    an empty candidate list.
  - Candidate present in the full sweep only when `roth_bracket_strategy=OPTIMIZER_CHOOSES`
    (or explicitly `PHASE_VARYING`), matching the `full_set`/`selected` gating used
    by every other strategy.
- Overrides propagation, both branches:
  - construct a household where `PHASE_VARYING` is the top-scoring candidate under
    `OPTIMIZER_CHOOSES`; assert `c['roth_phase_schedule']` after
    `optimize_roth_conversion_strategy` matches the winning candidate's schedule
    (not silently absent).
  - construct a household with `roth_bracket_strategy=PHASE_VARYING` selected
    directly (`roth_conversion_policy=fill_to_bracket`); assert
    `c['roth_phase_schedule']` is set after the call, not just present in the
    disclosure dict.
- Golden master: run `tests/test_frozen_sample_plan_golden_master_regression.py`
  unchanged — expect no pin movement (fixture uses `FILL_TARGET_BRACKET`).
- Fast tier (`pytest tests/ -m "not slow" --tb=short -q`) at minimum; full suite
  (`pytest tests/ -n auto --tb=short -q`) before calling the task done, since this
  touches the tax/conversion engine directly.
