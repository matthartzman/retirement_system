# Workbook Build Performance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cut the workbook build from ~37 s (live prices) / 32.7 s (frozen prices) to ~15–18 s without changing a single number in any build artifact.

**Architecture:** Five independent optimizations, each landing behind the repo's existing dollar-exact golden-master gates. Four are pure within-process memoization or I/O reuse (no behavior change by construction); the fifth moves the Sheet 10 claim-age sweep onto a process pool. No cross-build caching — that was evaluated and rejected (see "Rejected: cross-build caching" below).

**Tech Stack:** Python 3.12, openpyxl, numpy, `requests`, `concurrent.futures.ProcessPoolExecutor`, pytest/unittest.

## Global Constraints

- **No artifact may change.** `output/results_explorer_model.json` and `output/plan_summary.json` must be byte-identical before and after every task, except the `generated_at` field. Verified by `tools/perf_build_probe.py` (Task 0).
- **The dollar-exact golden masters are mandatory gates.** `tests/test_frozen_sample_plan_golden_master_regression.py`, `tests/test_synthetic_golden_master.py`, and `tests/test_deterministic_engine_full_row_snapshot_regression.py` must pass unchanged. Never hand-edit a pin; see `documentation/reference/GOLDEN_MASTER_RECOVERY_RUNBOOK.md`.
- **Always measure with prices frozen.** Set `RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS=1` for every timing and equivalence run. Live quotes change between builds (measured: AVUV 123.19 → 123.23, VTI 375.325 → 375.42 minutes apart) and will produce false diffs.
- **`src/planning_engines.py` is 6,418 lines and `src/market_data.py` is 1,828.** Read targeted line ranges (`sed -n 'A,Bp'`), never the whole file. Reading either in full wastes a large share of a session's context for no benefit.
- **Commit after every task.** Each task is independently revertable.

---

## Measured Baseline (2026-09-17, frozen prices, 12-core Windows 11)

Total: **32.72 s**. Phase breakdown from timestamped build log:

| Phase | Cost | Share |
|---|---|---|
| Config parse + Roth optimizer | 7.1 s | 22 % |
| Projection + validation + Monte Carlo | 4.7 s | 14 % |
| **Sheet 10 — Social Security sweep** | **15.9 s** | **49 %** |
| Other 30 sheets + QC + KPI | 5.0 s | 15 % |
| Save + XML patch + dashboard | 1.9 s | 6 % |

Hot spots (measured *without* cProfile — the profiler inflated these ~3.2× and mis-ranked them):

| Hot spot | Measured cost |
|---|---|
| `monte_carlo()` — 34 calls, almost all inside the Sheet 10 sweep | 17.3 s |
| `annuity_cash_income` re-computation (6.09 M calls) | ~5.8 s |
| `run_scenario()` — 250 calls | 7.0 s total (27.9 ms avg) |
| `_mc_survivor_bucket_flows` — 3 calls | 5.67 s (1.44 + 1.54 + 2.69) |
| `copy.deepcopy` inside `run_scenario` | 2.47 s |
| Live-price HTTP (LIVE mode only) | ~4.4 s |

Expected end state after all six tasks: **~15–18 s**.

## Rejected: cross-build caching

Evaluated and deliberately not planned. Reasons, all evidence-backed:

1. `_build_plan_input_fingerprint()` (`src/reporting/workbook_builder.py:71`) is already blind to this deployment's plan data. The last real `output/build_snapshot.json` tracks **one file, `system_config.csv`** — the 32 `client_*` names resolve to nothing because the workspace uses the SQLite backend and plan data lives in `client_files`, not `input/`.
2. LIVE pricing refetches every build, so an honest cache key almost never hits.
3. The user confirmed they change something on almost every build.

The safe half of the idea — memoize within one process, where staleness is structurally impossible — is Tasks 1 and 4.

---

### Task 0: Build performance + equivalence harness

Every later task needs one command that answers "is it faster?" and "did any number move?". Build it first.

**Files:**
- Create: `tools/perf_build_probe.py`

**Interfaces:**
- Produces: CLI `python tools/perf_build_probe.py --out <path.json>`. Writes JSON `{"total_s": float, "phases": {name: seconds}, "model_sha256": str, "summary_sha256": str}`. `model_sha256` is taken over `output/results_explorer_model.json` with the `generated_at` key removed, so it is stable across runs.
- Consumed by: Tasks 1–6, every "verify" step.

**Recommended model / effort:** Sonnet 5, low–medium effort.
**Usage estimate:** ~15–25 tool turns. Context driver: none significant — writes one new ~120-line file and runs it twice. **Light** relative to a 5-hour Pro session.

- [ ] **Step 1: Write the harness**

```python
"""Time a full workbook build and fingerprint its numeric output.

Always runs with live price providers disabled so two runs are comparable:
live quotes move between builds and would otherwise show up as output diffs.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Substring -> phase name. The build prints these markers on stdout already.
PHASE_MARKERS = [
    ("Parsing client data", "config_parse_and_roth_optimizer"),
    ("Running projection", "projection_and_monte_carlo"),
    ("Building workbook", "workbook_start"),
    ("Sheet 10 ", "sheet10_social_security"),
    ("Sheet 1 ", "sheet10_end_other_sheets"),
    ("Saving workbook", "save_and_dashboard"),
    ("Build complete", "done"),
]


def _stable_model_hash(path: Path) -> str:
    data = json.loads(path.read_text(encoding="utf-8"))
    data.pop("generated_at", None)
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    os.environ["RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS"] = "1"

    from src.build_entry import run_build

    t0 = time.perf_counter()
    marks: list[tuple[float, str]] = []
    buf = io.StringIO()

    class Tee:
        def write(self, data: str) -> None:
            buf.write(data)
            for needle, name in PHASE_MARKERS:
                if needle in data:
                    marks.append((time.perf_counter() - t0, name))

        def flush(self) -> None:
            pass

    with contextlib.redirect_stdout(Tee()):
        run_build()
    total = time.perf_counter() - t0

    phases: dict[str, float] = {}
    for i, (ts, name) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else total
        phases[name] = round(end - ts, 3)

    out_dir = ROOT / "output"
    result = {
        "total_s": round(total, 3),
        "phases": phases,
        "model_sha256": _stable_model_hash(out_dir / "results_explorer_model.json"),
        "summary_sha256": hashlib.sha256(
            (out_dir / "plan_summary.json").read_bytes()
        ).hexdigest(),
    }
    Path(args.out).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run it twice and confirm the hash is stable**

Run:
```bash
python tools/perf_build_probe.py --out /tmp/perf_a.json && python tools/perf_build_probe.py --out /tmp/perf_b.json
```
Expected: both files show the **same** `model_sha256` and `summary_sha256`. If they differ, stop — the harness is not isolating live pricing and no later measurement can be trusted.

- [ ] **Step 3: Record the baseline**

Run:
```bash
cp /tmp/perf_a.json docs/superpowers/plans/perf-baseline-2026-09-17.json
```

- [ ] **Step 4: Commit**

```bash
git add tools/perf_build_probe.py docs/superpowers/plans/perf-baseline-2026-09-17.json && git commit -m "perf(tooling): add build timing and output-equivalence probe"
```

---

### Task 1: Memoize annuity payment lookups (R1) — measured −5.8 s

`ann_pv_to_death` is an O(n²) triangle: for every projection year it re-walks payments from that year to death, per stream. 6,087,342 `annuity_cash_income` calls per build. The payment for a given `(stream, year)` does not depend on the PV start year, so it can be computed once.

**Critical scoping rule:** the memo must live on the per-projection config `c`, **not** on the stream dict. `run_scenario(..., mutate=...)` applies per-annuity-stream nested overrides (see `sheets_stress.py`), so a memo stored on a stream would survive the deepcopy and serve values for the *pre*-override stream. `project(c)` is entered exactly once per scenario, after all mutation is done, which makes `c` the only safe home.

**Files:**
- Modify: `src/projection_stages/portfolio_growth_and_net_worth.py` — imports block (top of file) and `ann_pv_to_death` at `:100-108`
- Test: `tests/test_annuity_pv_memo_regression.py` (create)

**Interfaces:**
- Produces: `_annuity_pmt(c, stream_key, stream, year) -> float` — module-level helper in `portfolio_growth_and_net_worth.py`. Reads/writes `c['_ann_pmt_memo']`, a `dict[tuple[str, int], float]`.
- Consumes: `annuity_cash_income(stream, year)` from `..planning_engines` (unchanged, already imported at the top of this module).

**Recommended model / effort:** Opus 5, medium effort. The correctness argument (memo scoping vs. `mutate=` overrides) is the hard part, not the code.
**Usage estimate:** ~25–40 tool turns. Context drivers: `src/core.py:1470-1515` (`annuity_cash_income`), `portfolio_growth_and_net_worth.py` (461 lines, reading in full is fine), plus 2–3 full-build verification runs at ~30 s each. **Moderate.**

- [ ] **Step 1: Write the failing test**

Create `tests/test_annuity_pv_memo_regression.py`:

```python
"""The annuity payment memo must be per-projection, never per-stream.

A memo attached to a stream dict would survive run_scenario's deepcopy and
serve pre-override values to a scenario that changed that stream -- silently
wrong numbers in every stress sheet. This pins the memo's scope.
"""
from __future__ import annotations

import unittest

from src.projection_stages.portfolio_growth_and_net_worth import _annuity_pmt


class AnnuityPmtMemoScope(unittest.TestCase):
    def _stream(self, init_pmt: float) -> dict:
        return {
            'first_yr': 2030, 'base': 0.0, 'div_rate': 0.0,
            'add_pct': 0.0, 'init_pmt': init_pmt,
        }

    def test_memo_is_keyed_per_config_not_shared_across_configs(self):
        stream_a = self._stream(100.0)
        c_a = {'wife_single': stream_a}
        first = _annuity_pmt(c_a, 'wife_single', stream_a, 2031)

        # A different scenario mutated the stream's payment. A correctly
        # scoped memo lives on the new config, so it must NOT return c_a's value.
        stream_b = self._stream(500.0)
        c_b = {'wife_single': stream_b}
        second = _annuity_pmt(c_b, 'wife_single', stream_b, 2031)

        self.assertAlmostEqual(first, 100.0 * 12)
        self.assertAlmostEqual(second, 500.0 * 12)

    def test_memo_does_not_write_to_the_stream_dict(self):
        stream = self._stream(100.0)
        c = {'wife_single': stream}
        before = set(stream)
        _annuity_pmt(c, 'wife_single', stream, 2031)
        self.assertEqual(
            set(stream) - before, set(),
            "memo must live on the config, not the stream",
        )

    def test_repeated_lookups_return_identical_values(self):
        stream = self._stream(100.0)
        c = {'wife_single': stream}
        vals = [_annuity_pmt(c, 'wife_single', stream, 2035) for _ in range(3)]
        self.assertEqual(len(set(vals)), 1)


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_annuity_pv_memo_regression.py -v`
Expected: FAIL — `ImportError: cannot import name '_annuity_pmt'`.

- [ ] **Step 3: Add the memo helper**

In `src/projection_stages/portfolio_growth_and_net_worth.py`, directly after the imports at the top of the file:

```python
def _annuity_pmt(c: dict, stream_key: str, stream: dict, year: int) -> float:
    """Memoized ``annuity_cash_income`` for one projection run.

    The memo lives on ``c`` -- the per-scenario config -- because ``project(c)``
    is entered once per scenario AFTER run_scenario applied any ``mutate=``
    overrides. Storing it on the stream dict instead would let a memo built
    before a per-stream override survive run_scenario's deepcopy and serve
    stale payments (sheets_stress.py mutates annuity streams this way).

    Exists purely to remove an O(n^2) re-walk: ann_pv_to_death below sums
    payments from each projection year through death, so the same
    (stream, year) payment was previously recomputed once per PV start year --
    6,087,342 annuity_cash_income calls in a single build.
    """
    memo = c.get('_ann_pmt_memo')
    if memo is None:
        memo = c['_ann_pmt_memo'] = {}
    key = (stream_key, year)
    val = memo.get(key)
    if val is None:
        val = memo[key] = annuity_cash_income(stream, year)
    return val
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_annuity_pv_memo_regression.py -v`
Expected: PASS, 3 tests.

- [ ] **Step 5: Route `ann_pv_to_death` through the memo**

Inside `apply_portfolio_growth_and_net_worth`, replace the existing `ann_pv_to_death` definition (currently at `:100-108`) with a version that takes the config key. Keep the discount arithmetic and its evaluation order **exactly** as-is so results stay bit-identical:

```python
    def ann_pv_to_death(stream_key, death_yr):
        """PV of annuity payments from current year through death_yr."""
        stream = c[stream_key]
        if year > death_yr:
            return 0.0
        pv = 0.0
        for y in range(year, death_yr + 1):
            pmt = _annuity_pmt(c, stream_key, stream, y)
            pv += pmt / ((1 + c['ret']) ** (y - year))
        return pv
```

Then update the seven call sites immediately below it to pass the key instead of the stream object:

```python
    w_single_val = (ann_pv_to_death('wife_single', c['w_death_yr']) +
                    (ann_pv_to_death('wife_qlac', c['w_death_yr']) if c['wife_qlac'].get('enabled') else 0)) if w_alive else 0
    h_single_val = (ann_pv_to_death('h_single', c['h_death_yr']) +
                    (ann_pv_to_death('h_qlac', c['h_death_yr']) if c['h_qlac'].get('enabled') else 0)) if h_alive else 0
    w_joint_val  = ann_pv_to_death('wife_joint', second_death) if (w_alive or h_alive)  else 0
    h_joint_val  = ann_pv_to_death('h_joint', second_death) if (h_alive or w_alive) else 0
    pension_val  = ann_pv_to_death('wife_pension', c['w_death_yr']) if w_alive else 0
```

Leave the death-benefit block below these lines (`if year == c['w_death_yr']: w_single_val += db.get('W_Single', 0)` and its siblings) untouched.

- [ ] **Step 6: Verify the build output is unchanged and faster**

Run:
```bash
python tools/perf_build_probe.py --out /tmp/perf_task1.json
```
Expected: `model_sha256` and `summary_sha256` **identical** to `docs/superpowers/plans/perf-baseline-2026-09-17.json`; `total_s` down roughly 5–6 s (baseline 32.7 s → ~26.9 s).

If the hashes differ, the memo is scoped wrong — do not proceed, and do not "accept" the new numbers.

- [ ] **Step 7: Run the mandatory golden-master gates**

Run:
```bash
python -m pytest tests/test_frozen_sample_plan_golden_master_regression.py tests/test_synthetic_golden_master.py tests/test_deterministic_engine_full_row_snapshot_regression.py -v
```
Expected: all PASS.

- [ ] **Step 8: Commit**

```bash
git add src/projection_stages/portfolio_growth_and_net_worth.py tests/test_annuity_pv_memo_regression.py && git commit -m "perf(projection): memoize annuity payments per projection run"
```

---

### Task 2: Reuse one HTTP session for price quotes (R5a) — ~2–3 s on LIVE builds

`market_data` calls bare `requests.get` per quote, so every request builds a new connection pool *and* a new `SSLContext`, reloading the CA bundle each time. Measured: 30 `load_verify_locations` calls per build.

**Files:**
- Modify: `src/market_data.py:521-545` (`_get_json`) and `src/market_data.py:825-835` (the second `requests.get` site)
- Test: `tests/test_market_data_session_reuse_unit.py` (create)

**Interfaces:**
- Produces: module-level `_session()` in `src/market_data.py`, returning a shared `requests.Session`, or `None` when `requests` is unavailable (the module already guards on `requests is not None`).

**Recommended model / effort:** Sonnet 5, low effort.
**Usage estimate:** ~10–15 tool turns. Context driver: **read only the two `requests.get` line ranges** — `market_data.py` is 1,828 lines and reading it whole is the main cost risk in this task. **Light.**

- [ ] **Step 1: Write the failing test**

Create `tests/test_market_data_session_reuse_unit.py`:

```python
"""Price fetches must share one requests.Session.

Each bare requests.get builds a fresh connection pool and SSLContext, which
re-reads the CA bundle -- measured at 30 CA-bundle loads in a single build.
"""
from __future__ import annotations

import unittest

import src.market_data as md


class SessionReuse(unittest.TestCase):
    def test_session_is_a_singleton(self):
        first = md._session()
        if first is None:
            self.skipTest("requests is not installed in this environment")
        self.assertIs(first, md._session())

    def test_session_exposes_get(self):
        sess = md._session()
        if sess is None:
            self.skipTest("requests is not installed in this environment")
        self.assertTrue(hasattr(sess, "get"))


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_market_data_session_reuse_unit.py -v`
Expected: FAIL — `AttributeError: module 'src.market_data' has no attribute '_session'`.

- [ ] **Step 3: Add the shared session**

Add near the top of `src/market_data.py`, after the `requests` import guard. If `threading` is not already imported in this module, add `import threading` to the stdlib import block first.

```python
_SESSION = None
_SESSION_LOCK = threading.Lock()


def _session():
    """One process-wide requests.Session for all quote fetches.

    Bare requests.get builds a new connection pool AND a new SSLContext per
    call, re-reading the CA bundle every time (measured: 30 CA-bundle loads
    per build, ~3s). Returns None when requests is unavailable so callers
    keep their existing urllib fallback path.
    """
    global _SESSION
    if requests is None:
        return None
    if _SESSION is None:
        with _SESSION_LOCK:
            if _SESSION is None:
                _SESSION = requests.Session()
    return _SESSION
```

- [ ] **Step 4: Route both call sites through it**

At `src/market_data.py:533`, replace:

```python
                    resp = requests.get(url, timeout=self.timeout_seconds, headers=_quote_headers("application/json,*/*"))
```

with:

```python
                    _sess = _session()
                    resp = _sess.get(url, timeout=self.timeout_seconds, headers=_quote_headers("application/json,*/*"))
```

Apply the identical change at `src/market_data.py:829`. Leave the surrounding `if requests is not None:` guards and the urllib fallback exactly as they are — the fallback is load-bearing for proxied desktops (see `_get_json`'s docstring).

- [ ] **Step 5: Run the tests**

Run:
```bash
python -m pytest tests/test_market_data_session_reuse_unit.py tests/test_market_data_module.py -v
```
Expected: all PASS.

- [ ] **Step 6: Verify output is unchanged, then time a live build**

Run:
```bash
python tools/perf_build_probe.py --out /tmp/perf_task2.json
```
Expected: hashes still identical to baseline. The probe freezes prices, so it will **not** show this task's gain — that is expected.

To see the gain, time one live build:
```bash
python tools/build_workbook.py
```
Expected: the `Parsing client data...` → `Selected Roth strategy` gap shrinks by ~2–3 s versus the ~7 s it takes with live pricing today.

- [ ] **Step 7: Commit**

```bash
git add src/market_data.py tests/test_market_data_session_reuse_unit.py && git commit -m "perf(market-data): share one requests.Session across quote fetches"
```

---

### Task 3: Cache repeated openpyxl style objects (R5b) — ~1 s

`write_cell` constructs a fresh `Font`, `Alignment`, `thin_border()` and `fill()` for every cell. The build writes ~16,500 cells through it, and openpyxl hashes each style object to de-duplicate it into the workbook's style table — 144,420 `IndexedList.add` calls.

**Caveat to verify, not assume:** openpyxl style objects are assigned by value into the workbook's shared style table, so sharing one instance across cells should be safe — but `thin_border()` and `fill()` may return objects openpyxl mutates on assignment. Step 5's hash check is what proves it. If the hash moves, **revert this task**; it is worth ~1 s and is not worth any risk.

**Files:**
- Modify: `src/reporting/workbook_common.py:101-115` (`write_cell`)
- Test: `tests/test_workbook_style_cache_unit.py` (create)

**Interfaces:**
- Produces: `_cached_font(bold, fg)`, `_cached_alignment(align)`, `_cached_fill(bg)`, `_cached_border()` — module-level `functools.lru_cache`-backed helpers in `workbook_common.py`.

**Recommended model / effort:** Sonnet 5, low–medium effort.
**Usage estimate:** ~15–25 tool turns. Context driver: `workbook_common.py` is 1,139 lines — read only `:1-160`. One full-build verification. **Light–moderate.**

- [ ] **Step 1: Write the failing test**

Create `tests/test_workbook_style_cache_unit.py`:

```python
"""Repeated cell styles should reuse one object instead of rebuilding it.

write_cell is called ~16,500 times per build; openpyxl hashes every style
object to de-duplicate it into the workbook style table.
"""
from __future__ import annotations

import unittest

from src.reporting import workbook_common as wc


class StyleCache(unittest.TestCase):
    def test_identical_font_requests_return_the_same_object(self):
        self.assertIs(wc._cached_font(True, '000000'), wc._cached_font(True, '000000'))

    def test_different_font_requests_return_different_objects(self):
        self.assertIsNot(wc._cached_font(True, '000000'), wc._cached_font(False, '000000'))

    def test_identical_alignment_requests_return_the_same_object(self):
        self.assertIs(wc._cached_alignment('left'), wc._cached_alignment('left'))

    def test_font_carries_the_requested_attributes(self):
        f = wc._cached_font(True, 'FF0000')
        self.assertEqual(f.name, 'Arial')
        self.assertEqual(f.size, 10)
        self.assertTrue(f.bold)


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_workbook_style_cache_unit.py -v`
Expected: FAIL — `AttributeError: module 'src.reporting.workbook_common' has no attribute '_cached_font'`.

- [ ] **Step 3: Add the cached constructors**

Add above `write_cell` in `src/reporting/workbook_common.py` (add `from functools import lru_cache` to the imports if absent):

```python
@lru_cache(maxsize=None)
def _cached_font(bold: bool, fg: str):
    return Font(name='Arial', bold=bold, color=fg, size=10)


@lru_cache(maxsize=None)
def _cached_alignment(align: str):
    return Alignment(horizontal=align, vertical='center')


@lru_cache(maxsize=None)
def _cached_fill(bg: str):
    return fill(bg)


@lru_cache(maxsize=None)
def _cached_border():
    return thin_border()
```

- [ ] **Step 4: Use them in `write_cell`**

Replace the body of `write_cell` with:

```python
def write_cell(ws, row, col, value, fmt=None, bold=False, bg=None, fg='000000',
               align='left', border=True):
    c = ws.cell(row=row, column=col, value=value)
    c.font = _cached_font(bold, fg)
    c.alignment = _cached_alignment(align)
    if border:
        c.border = _cached_border()
    if bg:
        c.fill = _cached_fill(bg)
    if fmt:
        c.number_format = fmt
    return c
```

- [ ] **Step 5: Verify output is unchanged and styles still render**

Run:
```bash
python tools/perf_build_probe.py --out /tmp/perf_task3.json
```
Expected: `model_sha256` / `summary_sha256` identical to baseline.

Then confirm the spreadsheet still carries fills:
```bash
python -c 'from openpyxl import load_workbook; wb = load_workbook("output/retirement_plan.xlsx"); ws = wb["Executive Summary"]; cells = [c for r in ws.iter_rows(min_row=1, max_row=12) for c in r if c.fill and c.fill.fgColor and c.fill.fgColor.rgb not in (None, "00000000")]; print("styled cells found:", len(cells)); assert cells, "style cache broke cell fills"'
```
Expected: a non-zero count.

- [ ] **Step 6: Run the workbook test suite**

Run: `python -m pytest tests/ -k "workbook" -q`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add src/reporting/workbook_common.py tests/test_workbook_style_cache_unit.py && git commit -m "perf(workbook): reuse openpyxl style objects across cells"
```

---

### Task 4: Deduplicate survivor-bucket builds (R4) — ~1.5–3 s

`_mc_survivor_bucket_flows` runs `2 * n_years` = 70 `run_scenario` calls. It is called three times per build — from the Roth optimizer (`planning_engines.py:3098`), from `monte_carlo` (`planning_engines.py:6222`), and from the Sheet 10 sweep (`sheets_strategy.py:309`) — costing 1.44 s + 1.54 s + 2.69 s.

**Measured caveat that shapes this task:** a probe showed all three calls share identical *death-timing* inputs, but they do **not** necessarily share identical configs — the Roth-optimizer call passes the pre-optimization `base`, while the other two pass the post-optimization `c`. Bucket flows come from a full `run_scenario` off that config, so Roth policy and spending genuinely change them. The cache key must therefore fingerprint everything `project()` reads, not just death years. Expect **1 of 3** calls to dedupe reliably; treat a second hit as a bonus.

**Files:**
- Modify: `src/planning_engines.py:4648-4740` (`_mc_survivor_bucket_flows`)
- Test: `tests/test_survivor_bucket_memo_regression.py` (create)

**Interfaces:**
- Produces: `_survivor_bucket_cache_key(c, base_rows) -> str` — module-level in `planning_engines.py`; memo held on `c['_survivor_bucket_memo']`.
- Consumes: `_mc_survivor_bucket_flows(c, base_rows)` signature is unchanged — all three call sites stay exactly as they are.

**Recommended model / effort:** Opus 5, medium–high effort. The key-completeness argument is the risk; the code is small.
**Usage estimate:** ~30–45 tool turns. Context drivers: targeted reads of `planning_engines.py` (**do not read all 6,418 lines** — use `sed -n '4648,4740p'` and `sed -n '3090,3105p'`), plus 2–3 full-build runs. **Moderate.**

**Flagged as the step most likely to need a second pass:** getting the fingerprint right is a judgment call. If the memo produces any hash drift in Step 6, prefer *narrowing* the key (making it miss more often) over shipping a key that might collide.

- [ ] **Step 1: Write the failing test**

Create `tests/test_survivor_bucket_memo_regression.py`:

```python
"""Survivor-bucket memoization must never serve buckets across different configs.

The three call sites do not all pass the same config: the Roth optimizer uses
the PRE-optimization base, while monte_carlo and the Sheet 10 sweep use the
post-optimization config. Bucket flows come from a full projection off that
config, so a key that ignores Roth policy would serve wrong trajectories.
"""
from __future__ import annotations

import unittest

from src.planning_engines import _survivor_bucket_cache_key


class SurvivorBucketCacheKey(unittest.TestCase):
    def _cfg(self, **over):
        base = {
            'members': [{'name': 'H'}, {'name': 'W'}],
            'plan_start': 2026, 'plan_end': 2060,
            'h_death_yr': 2055, 'w_death_yr': 2060,
            'roth_policy': 'fill_to_bracket', 'spend_base': 120000.0,
        }
        base.update(over)
        return base

    def _rows(self):
        return [{'year': y} for y in range(2026, 2061)]

    def test_same_config_produces_the_same_key(self):
        self.assertEqual(
            _survivor_bucket_cache_key(self._cfg(), self._rows()),
            _survivor_bucket_cache_key(self._cfg(), self._rows()),
        )

    def test_roth_policy_change_produces_a_different_key(self):
        a = _survivor_bucket_cache_key(self._cfg(), self._rows())
        b = _survivor_bucket_cache_key(self._cfg(roth_policy='none'), self._rows())
        self.assertNotEqual(a, b, "Roth policy changes bucket flows and must be in the key")

    def test_spending_change_produces_a_different_key(self):
        a = _survivor_bucket_cache_key(self._cfg(), self._rows())
        b = _survivor_bucket_cache_key(self._cfg(spend_base=200000.0), self._rows())
        self.assertNotEqual(a, b)

    def test_death_year_change_produces_a_different_key(self):
        a = _survivor_bucket_cache_key(self._cfg(), self._rows())
        b = _survivor_bucket_cache_key(self._cfg(h_death_yr=2040), self._rows())
        self.assertNotEqual(a, b)


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_survivor_bucket_memo_regression.py -v`
Expected: FAIL — `ImportError: cannot import name '_survivor_bucket_cache_key'`.

- [ ] **Step 3: Add the cache key**

Add immediately above `_mc_survivor_bucket_flows` in `src/planning_engines.py`:

```python
def _survivor_bucket_cache_key(c: dict, base_rows: list[dict]) -> str:
    """Fingerprint everything the survivor-bucket build actually depends on.

    The buckets are produced by 70 full run_scenario() projections off ``c``,
    so ANY config value the projection reads changes them -- not just the
    death years. This hashes the whole config with unhashable/derived entries
    dropped, deliberately erring toward MORE invalidation: a missed key would
    serve a different household's survivor trajectories, which is a silently
    wrong workbook, while an extra miss only costs ~1.5s.
    """
    import hashlib as _hashlib
    import json as _json

    # Derived outputs and memos -- never inputs to the bucket build. Including
    # them would make every key unique and defeat the memo entirely.
    skip = {
        '_survivor_bucket_memo', '_ann_pmt_memo', 'plan_result',
        'report_spec', 'roth_strategy_result', 'advisor_readiness',
    }
    payload = {k: v for k, v in c.items() if k not in skip}
    h = _hashlib.sha256(_json.dumps(payload, sort_keys=True, default=repr).encode('utf-8'))
    h.update(b'\0')
    h.update(_json.dumps([int(r['year']) for r in base_rows]).encode('utf-8'))
    return h.hexdigest()
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_survivor_bucket_memo_regression.py -v`
Expected: PASS, 4 tests.

- [ ] **Step 5: Wire the memo into `_mc_survivor_bucket_flows`**

At the very top of `_mc_survivor_bucket_flows`'s body — before the existing `members = c.get('members') or []` line — insert:

```python
    _key = _survivor_bucket_cache_key(c, base_rows)
    _memo = c.get('_survivor_bucket_memo')
    if _memo is None:
        _memo = c['_survivor_bucket_memo'] = {}
    if _key in _memo:
        return _memo[_key]
```

Then change the function's final `return {...}` so the result is stored:

```python
    _result = {
        'years': years,
        'n_years': n_years,
        'n_buckets': n_buckets,
        'plan_start': plan_start,
        'arrays': arrays,
        'spend_by_tier': tier_arrays,
    }
    _memo[_key] = _result
    return _result
```

The two early `return None` paths (single-person household, empty `base_rows`) stay as they are — they are already cheap.

- [ ] **Step 6: Verify output is unchanged and measure**

Run:
```bash
python tools/perf_build_probe.py --out /tmp/perf_task4.json
```
Expected: hashes identical to baseline; `total_s` down ~1.5–3 s from the Task 3 result.

- [ ] **Step 7: Run the survivor-economics gates**

Run:
```bash
python -m pytest tests/test_survivor_bucket_alignment.py tests/test_vectorized_mc_survivor_economics.py tests/test_scalar_vectorized_survivor_reconciliation.py tests/test_frozen_sample_plan_golden_master_regression.py -v
```
Expected: all PASS.

- [ ] **Step 8: Commit**

```bash
git add src/planning_engines.py tests/test_survivor_bucket_memo_regression.py && git commit -m "perf(mc): memoize survivor-bucket builds within a projection config"
```

---

### Task 5: Stop deep-copying dead weight into every scenario (R2) — ~1.5–2 s

`run_scenario` deep-copies the whole config 250 times per build (2.47 s). Probing showed the cost is dominated by one key: **`plan_result`, at ~11.7 ms of a 13–33 ms copy**. It is the previous build's entire result object, carried on the config and copied into every scenario that never reads it.

`sheets_strategy._safe_project_pair` already pops `plan_result` — but *inside* its `mutate` callback, which runs **after** the deepcopy, so it currently saves nothing.

**Files:**
- Modify: `src/planning_engines.py:2454-2487` (`run_scenario`)
- Test: `tests/test_run_scenario_copy_scope_regression.py` (create)

**Interfaces:**
- Produces: module-level `_SCENARIO_IRRELEVANT_KEYS: frozenset[str]` in `planning_engines.py`.
- Consumes/Produces: `run_scenario(base_config, overrides=None, mutate=None)` signature unchanged. Behavior change: keys in `_SCENARIO_IRRELEVANT_KEYS` are shared by reference into the copy rather than deep-copied; the caller's config is still never mutated.

**Recommended model / effort:** Sonnet 5, medium effort.
**Usage estimate:** ~20–30 tool turns. Context driver: `planning_engines.py:2454-2490` only, plus one full-build run. **Light–moderate.**

- [ ] **Step 1: Write the failing test**

Create `tests/test_run_scenario_copy_scope_regression.py`:

```python
"""run_scenario must not mutate its caller's config, and must not waste time
deep-copying derived result blobs that no projection stage reads.
"""
from __future__ import annotations

import unittest

from src.planning_engines import _SCENARIO_IRRELEVANT_KEYS, run_scenario


class ScenarioCopyScope(unittest.TestCase):
    def test_result_blobs_are_declared_irrelevant(self):
        self.assertIn('plan_result', _SCENARIO_IRRELEVANT_KEYS)
        self.assertIn('report_spec', _SCENARIO_IRRELEVANT_KEYS)

    def test_caller_config_is_never_mutated(self):
        def fake_project(c2):
            c2['spend_base'] = 999999.0
            c2.setdefault('nested', {})['touched'] = True
            return []

        import src.planning_engines as pe
        original = pe.project
        pe.project = fake_project
        try:
            base = {
                'spend_base': 100.0,
                'nested': {'touched': False},
                'plan_result': {'big': [1, 2, 3]},
            }
            run_scenario(base, overrides={'spend_base': 200.0})
        finally:
            pe.project = original

        self.assertEqual(base['spend_base'], 100.0)
        self.assertFalse(base['nested']['touched'], "scenario mutated the caller's nested dict")


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_run_scenario_copy_scope_regression.py -v`
Expected: FAIL — `ImportError: cannot import name '_SCENARIO_IRRELEVANT_KEYS'`.

- [ ] **Step 3: Implement the scoped copy**

Add above `run_scenario` in `src/planning_engines.py`:

```python
# Derived build outputs carried on the config that no projection stage reads.
# plan_result alone measured ~11.7ms of a 13-33ms run_scenario deepcopy, and
# run_scenario is called 250x per build. Shared by reference into the copy:
# a scenario never reads them, and the callers that want them gone
# (sheets_strategy._safe_project_pair) already pop them from the copy.
_SCENARIO_IRRELEVANT_KEYS = frozenset({
    'plan_result',
    'report_spec',
    'roth_strategy_result',
    'advisor_readiness',
})
```

Then replace `run_scenario`'s first line (`c2 = copy.deepcopy(base_config)`) with:

```python
    _carried = {k: base_config[k] for k in _SCENARIO_IRRELEVANT_KEYS if k in base_config}
    if _carried:
        _slim = {k: v for k, v in base_config.items() if k not in _SCENARIO_IRRELEVANT_KEYS}
        c2 = copy.deepcopy(_slim)
        # Re-attach by reference. Safe because no projection stage reads these,
        # and deep-copying them was the single largest cost in this function.
        c2.update(_carried)
    else:
        c2 = copy.deepcopy(base_config)
```

Leave the rest of the function (`overrides`, `mutate`, `return c2, project(c2)`) untouched, and leave its existing docstring's "No result cache" paragraph in place — it is still accurate.

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_run_scenario_copy_scope_regression.py -v`
Expected: PASS, 2 tests.

- [ ] **Step 5: Verify output is unchanged**

Run:
```bash
python tools/perf_build_probe.py --out /tmp/perf_task5.json
```
Expected: hashes identical to baseline; `total_s` down ~1.5–2 s from Task 4's result.

- [ ] **Step 6: Run the stress-sheet and scenario gates**

Run:
```bash
python -m pytest tests/test_expanded_stress_scenarios_regression.py tests/test_ltc_scenario_improvements_regression.py tests/test_allocation_scenarios_functional.py tests/test_frozen_sample_plan_golden_master_regression.py -v
```
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add src/planning_engines.py tests/test_run_scenario_copy_scope_regression.py && git commit -m "perf(engine): stop deep-copying derived result blobs into scenarios"
```

---

### Task 6: Parallelize the Sheet 10 claim-age sweep (R3) — ~8–12 s

Sheet 10 is 15.9 s of a 32.7 s build. Its cost is 34 `monte_carlo()` calls (17.3 s measured) plus their projections, one per scored claim-age pair. The pairs are fully independent.

**⚠ This is the disproportionately expensive task in this plan.** Reasons:
- `_safe_project_pair` passes a **closure** (`_mutate`) to `run_scenario`. Closures are not picklable, so Windows `spawn` workers cannot receive it. The pair evaluation must be refactored into a module-level function taking only picklable arguments before any pool can be used.
- Each spawned worker re-imports the whole reporting/projection stack (~2–3 s each). With 33 pairs at ~0.5 s of work apiece, the pool must be sized and reused carefully or startup cost eats the gain.
- Verification requires repeated ~27 s full builds, and process-pool bugs on Windows often surface only in a full build, not in unit tests.

**Scope-down option if this overruns:** cap the work instead of parallelizing it. `_COARSE_STEP` is already 2; raising it to 3, or setting `skip_mc=True` for coarse-pass pairs (the MC block is already documented in-code as purely informational and never feeds `objective_value`), would cut most of the 17.3 s with a ~20-line change. That changes disclosure-table contents, so it needs the user's sign-off — but it is the cheap escape hatch. **Decide between these before starting, not halfway through.**

**Files:**
- Create: `src/reporting/sheets_strategy_pair_worker.py`
- Modify: `src/reporting/sheets_strategy.py:323-500` (`_safe_project_pair` → thin adapter) and `:511-540` (the sweep fan-out)
- Test: `tests/test_ss_sweep_parallel_equivalence_regression.py` (create)

**Interfaces:**
- Produces: `evaluate_claim_age_pair(config: dict, spec: dict, settings: dict) -> dict` — module-level and picklable, in `sheets_strategy_pair_worker.py`. Returns the same dict shape `_safe_project_pair` returns today (`h_age`, `w_age`, `objective_value`, `rank_score`, `mc_success_rate`, `mc_p10_terminal_nw`, `feasibility_probability`, …). `spec` carries `h_age`, `w_age`, `h_mort_age`, `w_mort_age`, `skip_mc`; `settings` carries `SWEEP_MC_SIMS`, `SWEEP_MC_SEED`, `SS_SURVIVOR_WEIGHT`, `base_terminal`, `base_tax`, `base_ss`, `base_lcv`, `survivor_buckets`.
- Consumes: `run_scenario`, `monte_carlo`, `estimate_after_tax_terminal_net_worth`, `_roth_discount_rate`, `compute_baseline_lcv_and_eltr`, `LCV_FEASIBILITY_GATE_THRESHOLD` — all already importable at module level.

**Recommended model / effort:** Opus 5, high effort.
**Usage estimate:** ~50–80 tool turns. Context drivers: `sheets_strategy.py` is 2,511 lines and the sweep spans ~250 of them; expect several full-build test cycles at ~27 s each plus debugging spawn/pickling failures. **Heavy — this task could consume a large fraction of a 5-hour Pro session on its own. Run it as its own session with a fresh context.**

- [ ] **Step 1: Write the worker-contract test first**

Create `tests/test_ss_sweep_parallel_equivalence_regression.py`:

```python
"""The claim-age pair evaluator must be a picklable, module-level callable.

Windows spawns worker processes, so a closure (the shape this logic had
before) cannot cross the process boundary.
"""
from __future__ import annotations

import pickle
import unittest

from src.reporting.sheets_strategy_pair_worker import evaluate_claim_age_pair


class PairWorkerContract(unittest.TestCase):
    def test_worker_is_a_module_level_callable(self):
        self.assertTrue(callable(evaluate_claim_age_pair))
        self.assertEqual(
            evaluate_claim_age_pair.__module__,
            'src.reporting.sheets_strategy_pair_worker',
        )

    def test_worker_is_picklable(self):
        self.assertIs(pickle.loads(pickle.dumps(evaluate_claim_age_pair)),
                      evaluate_claim_age_pair)


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_ss_sweep_parallel_equivalence_regression.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.reporting.sheets_strategy_pair_worker'`.

- [ ] **Step 3: Extract the pair evaluator to a module-level function**

Create `src/reporting/sheets_strategy_pair_worker.py` containing `evaluate_claim_age_pair(config, spec, settings)`. Move the **entire** body of the current `_safe_project_pair` closure into it, replacing every captured variable with an explicit argument:

- `c` → `config`
- `h_age`, `w_age`, `h_mort_age`, `w_mort_age`, `skip_mc` → keys of `spec`
- `SWEEP_MC_SIMS`, `SWEEP_MC_SEED`, `SS_SURVIVOR_WEIGHT`, `base_terminal`, `base_tax`, `base_ss`, `base_lcv` → keys of `settings`
- `_survivor_buckets_for_sweep` → `settings['survivor_buckets']`

Preserve every comment in the moved code verbatim — several document root-caused bugs (the `h_mort_age` / `h_death_yr` derivation trap, the `w_mort_age == 0` sentinel, the `roth_policy` de-recursion). Do not paraphrase them.

Then, in `sheets_strategy.py`, build the settings dict **once** where `_survivor_buckets_for_sweep` and the `base_*` figures are already computed (just after `_base_metrics` / `base_lcv`), so both the serial adapter and the pool in Step 5 pass the identical object:

```python
    _sweep_settings = {
        'SWEEP_MC_SIMS': SWEEP_MC_SIMS,
        'SWEEP_MC_SEED': SWEEP_MC_SEED,
        'SS_SURVIVOR_WEIGHT': SS_SURVIVOR_WEIGHT,
        'base_terminal': base_terminal,
        'base_tax': base_tax,
        'base_ss': base_ss,
        'base_lcv': base_lcv,
        'survivor_buckets': _survivor_buckets_for_sweep,
    }
```

Then reduce `_safe_project_pair` to a thin adapter over the worker, so the serial and parallel paths share one implementation:

```python
    def _safe_project_pair(h_age, w_age, h_mort_age=None, w_mort_age=None, skip_mc=False):
        return evaluate_claim_age_pair(c, {
            'h_age': h_age, 'w_age': w_age,
            'h_mort_age': h_mort_age, 'w_mort_age': w_mort_age,
            'skip_mc': skip_mc,
        }, _sweep_settings)
```

Add the import at the top of `sheets_strategy.py`:

```python
from .sheets_strategy_pair_worker import evaluate_claim_age_pair
```

- [ ] **Step 4: Verify the serial path is unchanged, then commit the refactor alone**

Run:
```bash
python -m pytest tests/test_ss_sweep_parallel_equivalence_regression.py tests/test_ss_timing_score_survivor_weighted.py tests/test_aca_ptc_monte_carlo_and_ss_sweep_boundaries.py -v && python tools/perf_build_probe.py --out /tmp/perf_task6a.json
```
Expected: tests PASS; hashes identical to baseline.

This refactor is valuable on its own and is the safe rollback point if the pool does not pay off. Commit it before touching concurrency:

```bash
git add src/reporting/sheets_strategy.py src/reporting/sheets_strategy_pair_worker.py tests/test_ss_sweep_parallel_equivalence_regression.py && git commit -m "refactor(sheet10): extract claim-age pair evaluation to a picklable worker"
```

- [ ] **Step 5: Run the pairs on a process pool**

In `sheets_strategy.py`, add a parallel fan-out that fills the existing `_evaluated` cache, keeping results ordered by index so ranking stays deterministic. Add `import os` to the module imports if absent.

```python
    def _evaluate_pairs(specs: list[dict]) -> list[dict]:
        """Score claim-age pairs in parallel, filling the _evaluated cache.

        Results are collected BY INDEX, not by completion order: the sweep's
        rank_score normalization and tie-breaking both depend on a stable
        candidate order. Falls back to serial evaluation if a pool cannot be
        created (restricted/frozen environments, single-core hosts) -- a slow
        sheet is always better than a failed build.
        """
        pending = [s for s in specs if (s['h_age'], s['w_age']) not in _evaluated]
        if len(pending) > 1:
            try:
                from concurrent.futures import ProcessPoolExecutor
                workers = min(len(pending), max(1, (os.cpu_count() or 2) - 1))
                with ProcessPoolExecutor(max_workers=workers) as pool:
                    futures = [
                        pool.submit(evaluate_claim_age_pair, c, s, _sweep_settings)
                        for s in pending
                    ]
                    for s, fut in zip(pending, futures):
                        _evaluated[(s['h_age'], s['w_age'])] = fut.result()
            except Exception as _pool_exc:
                print(f'  Sheet 10: parallel sweep unavailable ({_pool_exc}); scoring serially.')
                for s in pending:
                    _evaluated[(s['h_age'], s['w_age'])] = _safe_project_pair(s['h_age'], s['w_age'])
        else:
            for s in pending:
                _evaluated[(s['h_age'], s['w_age'])] = _safe_project_pair(s['h_age'], s['w_age'])
        return [_evaluated[(s['h_age'], s['w_age'])] for s in specs]
```

Call `_evaluate_pairs(_coarse_pairs)` immediately before the first `strategy_sweep.run_sweep(...)` so the pool warms `_evaluated`; `run_sweep`'s own `_evaluate_pair` calls then all hit that cache. Do the same with `_evaluate_pairs(_refine_pairs)` before the second `run_sweep`.

- [ ] **Step 6: Verify identical output and measure**

Run:
```bash
python tools/perf_build_probe.py --out /tmp/perf_task6.json
```
Expected: `model_sha256` / `summary_sha256` **identical to baseline**; `phases.sheet10_social_security` down from ~15.9 s to ~4–7 s.

If the hashes differ, the most likely cause is a worker inheriting a different `TAX_REFERENCE_YEAR` or price cache than the parent. Confirm `RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS` and `TAX_REFERENCE_YEAR` are set in the environment *before* the pool is created, so spawned workers inherit them.

- [ ] **Step 7: Verify the serial fallback path still builds**

Run:
```bash
python -c 'import os, sys; os.environ["RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS"]="1"; sys.path.insert(0,"."); import concurrent.futures as cf; cf.ProcessPoolExecutor = None; from src.build_entry import run_build; run_build(); print("FALLBACK BUILD OK")'
```
Expected: prints `Sheet 10: parallel sweep unavailable ...; scoring serially.` and then `FALLBACK BUILD OK`.

- [ ] **Step 8: Run the full suite**

Run: `python -m pytest tests/ -q -x`
Expected: all PASS. This is the only task touching process lifecycle, so the full suite matters here.

- [ ] **Step 9: Commit**

```bash
git add src/reporting/sheets_strategy.py && git commit -m "perf(sheet10): score claim-age pairs on a process pool"
```

---

## Final verification

- [ ] **Confirm the end-to-end result**

Run:
```bash
python tools/perf_build_probe.py --out /tmp/perf_final.json
```
```bash
python -c 'import json; b=json.load(open("docs/superpowers/plans/perf-baseline-2026-09-17.json")); f=json.load(open("/tmp/perf_final.json")); assert b["model_sha256"]==f["model_sha256"] and b["summary_sha256"]==f["summary_sha256"], "OUTPUT CHANGED -- do not ship"; print(b["total_s"], "->", f["total_s"], "| output identical: yes")'
```
Expected: ~32.7 s → ~15–18 s, `output identical: yes`.

- [ ] **Run the full suite one final time**

Run: `python -m pytest tests/ -q`
Expected: all PASS.

## Usage budgeting note

These are relative estimates, not token counts. **Check `/usage` as you execute and compare against them:**

| Task | Model | Effort | Relative cost |
|---|---|---|---|
| 0 — harness | Sonnet 5 | low–med | Light |
| 1 — annuity memo | Opus 5 | medium | Moderate |
| 2 — HTTP session | Sonnet 5 | low | Light |
| 3 — style cache | Sonnet 5 | low–med | Light–moderate |
| 4 — bucket dedupe | Opus 5 | med–high | Moderate |
| 5 — scenario copy | Sonnet 5 | medium | Light–moderate |
| 6 — parallel sweep | Opus 5 | high | **Heavy — budget its own session** |

Tasks 0–5 together should fit comfortably in one 5-hour session. Task 6 should start fresh. If Task 6 exceeds roughly half a session without a passing hash comparison, stop and take the scope-down option in its header instead.
