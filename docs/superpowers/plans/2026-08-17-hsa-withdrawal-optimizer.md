# HSA Withdrawal Optimizer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an optimizer choose the year-by-year HSA drawdown that consumes the balance before second death at the lowest present-valued tax cost, with the user able to override any year.

**Architecture:** Five phases in dependency order. H0 adds inputs. H1 makes the HSA's terminal tax cliff visible in `after_tax.py` — without it the optimizer's answer is "never withdraw," which is an artifact of a missing tax rule. H2 decouples HSA withdrawals from current-year medical spending. H3 adds the constrained phasing optimizer, sharing the existing Roth conversion objective so the two can be scored jointly. H4 adds the per-year override table. H5 reports and discloses.

**Tech Stack:** Python 3.12 (`python`) and 3.14 (`py -3.14`), pytest + unittest, SQLite (stdlib `sqlite3`), CSV-sectioned Plan Data, openpyxl for workbook sheets.

**Design spec:** `docs/superpowers/specs/2026-08-17-hsa-withdrawal-optimizer-design.md` (revision 3).

## Global Constraints

- Set `RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS=1` on **every** test run, or golden-master dollars drift between runs.
- **Capture pytest output to a FILE and read the summary lines.** A truncated tail hides FAILED lines, and a trailing `; echo "exit=$?"` reports the *echo's* status, not pytest's — that exact mistake produced a false "green" in this repo on 2026-08-17.
- This suite mutates tracked files. After any broad run, check `git status` on `input/` and `git checkout --` anything unintended.
- Both `python` (3.12) and `py -3.14` have pytest and openpyxl here. Either works; be consistent within a session.
- Work on a branch off `main`. Never commit directly to `main`.
- Follow this repo's model/effort policy (`documentation/reports/REMAINING_WORK_PLAN_2026-08-12.md` §5). Every task below carries an explicit assignment and a one-line reason.
- **Every new guard or acceptance test must be demonstrated failing before it is trusted** (planner sign-off 2026-08-17, §3 rule 2). "Passes on a clean tree" is compatible with a test that cannot fail.
- Do not rename existing Python identifiers. `hsa_wd`, `hsa_ids`, `hsa_nw` stay as they are.

---

## Model & Effort Assignments

| Tier | When | Tasks |
|---|---|---|
| **opus · high** | The answer is not known, or being wrong is expensive and silent. One-way tax rules, joint optimization, contract tests. | 2, 3, 8, 9, 10, 13 |
| **opus · medium** | Path is known, blast radius is wide. | 5, 7, 12, 15 |
| **sonnet · medium** | Specified work with local judgement calls. | 1, 4, 6, 11, 14 |
| **sonnet · low** | The edit is known and repeated. | — |
| **haiku · low** | Bookkeeping with a verifiable output. | 16 |

Three rules that outrank the table:
1. Any task whose job is to **re-check** something the record already answered gets opus · high regardless of diff size.
2. Effort down, not model down, when work is fully specified.
3. One task per fresh session beats any model choice made inside it.

---

## File Structure

| File | Responsibility | Tasks |
|---|---|---|
| `reference_data/schema.csv` | New HSA policy rows | 1, 8 |
| `src/data_io.py` | Parse new HSA settings onto `c` | 1 |
| `src/after_tax.py` | `hsa_terminal_tax()`; wire into after-tax terminal NW | 2, 3 |
| `src/hsa_schedule.py` | **New.** Scorer, constrained schedule search, precedence resolver, feasibility states | 8, 9, 10, 12 |
| `src/planning_engines.py` | Rework `withdraw_hsa_window` / `withdraw_hsa_gap`; call the resolver | 5, 6, 11 |
| `src/plan_data_registry.py` | Register `client_hsa_schedule.csv` as a flat table | 11 |
| `src/reporting/sheets_*.py` | Drawdown schedule + disclosure | 14, 15 |
| `frontend/js/dashboard_decomp_*.js` | Per-year override UI | 13 |
| `tests/test_hsa_terminal_tax_unit.py` | **New.** Lump-sum cliff maths | 2 |
| `tests/test_hsa_terminal_cliff_regression.py` | **New.** Cliff's effect on after-tax terminal NW, optimizer-independent | 3 |
| `tests/test_hsa_withdrawal_decoupling_regression.py` | **New.** Draw is no longer capped by `wellness_cost` | 5, 6 |
| `tests/test_hsa_optimizer_regression.py` | **New.** Survivor weighting, anti-back-loading, feasibility | 9, 10 |
| `tests/test_hsa_schedule_override_contract.py` | **New.** Precedence and round-trip | 12 |

---

## Phase H0 — Inputs and schema

### Task 1: HSA policy inputs

**Model · effort: sonnet · medium.** Fully specified schema and parse work, but the choice-value sets need judgement.

**Files:**
- Modify: `reference_data/schema.csv`
- Modify: `src/data_io.py` (near the existing HSA block that sets `c['hsa_ids']`, ~line 2232)
- Test: `tests/test_hsa_policy_inputs_unit.py` (create)

**Interfaces:**
- Produces: `c['hsa_beneficiary_type']` (`'spouse'|'non_spouse'|'estate'|'charity'`), `c['hsa_consume_by']` (str, default `'second_death_p90'`), `c['hsa_expense_bank']` (float or `None` for unlimited), `c['hsa_nonqualified_treatment']` (`'block'|'allow_taxable'`), `c['hsa_state_conformity']` (bool).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_hsa_policy_inputs_unit.py
import unittest
from src.data_io import load_csv, parse_client
from conftest import TEST_INPUT_DIR


class HsaPolicyInputsTests(unittest.TestCase):
    def test_defaults_are_present_and_conservative(self):
        c = parse_client(load_csv(TEST_INPUT_DIR / "client_data.csv"))
        self.assertEqual(c["hsa_beneficiary_type"], "spouse")
        self.assertEqual(c["hsa_consume_by"], "second_death_p90")
        self.assertIsNone(c["hsa_expense_bank"])  # None == unlimited
        self.assertEqual(c["hsa_nonqualified_treatment"], "block")
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS=1 python -m pytest tests/test_hsa_policy_inputs_unit.py -q`
Expected: FAIL — `KeyError: 'hsa_beneficiary_type'`.

- [ ] **Step 3: Add the schema rows**

Append to `reference_data/schema.csv` (columns are `Section,Subsection,key,type,required,default,min,max,help`):

```csv
HSA Policy,Beneficiary,hsa_beneficiary_type,choice,FALSE,spouse,,,spouse | non_spouse | estate | charity; a spouse inherits the HSA tax-free. Any other beneficiary makes the entire balance ordinary income to them in the single year of death - no 10-year stretch and no step-up.
HSA Policy,Withdrawals,hsa_consume_by,text,FALSE,second_death_p90,,,"Deadline for consuming the HSA: second_death_pNN for a longevity percentile, or an explicit year. Defaults to the 90th percentile because the failure modes are asymmetric - running out of tax-free capacity in survivor years is unbounded, leaving a residual is capped at balance x heir rate."
HSA Policy,Withdrawals,hsa_expense_bank,currency,FALSE,,0,,"Cumulative substantiated unreimbursed qualified medical expenses available to justify tax-free withdrawals. Blank means unlimited."
HSA Policy,Withdrawals,hsa_nonqualified_treatment,choice,FALSE,block,,,block | allow_taxable; whether withdrawals beyond the substantiated expense bank are permitted as ordinary income (plus a 20% penalty before age 65).
HSA Policy,Withdrawals,hsa_state_conformity,boolean,FALSE,TRUE,,,Whether the residence state recognizes HSAs. FALSE (California and New Jersey) means earnings are taxable at the state level annually and withdrawals are not state-tax-free.
```

- [ ] **Step 4: Parse them in `data_io.py`**

Immediately after the line that sets `c['hsa_ids']` (~2232):

```python
    c['hsa_beneficiary_type'] = str(_v(data, 'HSA Policy', 'Beneficiary',
                                       'hsa_beneficiary_type', 'spouse') or 'spouse').strip().lower()
    c['hsa_consume_by'] = str(_v(data, 'HSA Policy', 'Withdrawals',
                                 'hsa_consume_by', 'second_death_p90') or 'second_death_p90').strip()
    _bank = _v(data, 'HSA Policy', 'Withdrawals', 'hsa_expense_bank', '')
    c['hsa_expense_bank'] = None if str(_bank or '').strip() == '' else _n(_bank, 0.0)
    c['hsa_nonqualified_treatment'] = str(_v(data, 'HSA Policy', 'Withdrawals',
                                             'hsa_nonqualified_treatment', 'block') or 'block').strip().lower()
    c['hsa_state_conformity'] = _b(_v(data, 'HSA Policy', 'Withdrawals', 'hsa_state_conformity', 'TRUE'))
```

Match the surrounding helpers exactly — if this block uses different names than `_v` / `_n` / `_b`, use the local ones.

- [ ] **Step 5: Run the test and confirm it passes**

Run: `RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS=1 python -m pytest tests/test_hsa_policy_inputs_unit.py -q`
Expected: PASS.

- [ ] **Step 6: Resync the manifest and run the fast tier**

```bash
python tools/check_plan_data_sync.py --write
RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS=1 python -m pytest tests/ -m "not slow" -q > /tmp/h0.txt 2>&1
grep -E "^(FAILED|ERROR)" /tmp/h0.txt; tail -3 /tmp/h0.txt
```

Expected: no FAILED/ERROR lines. `git status input/` clean.

- [ ] **Step 7: Commit**

```bash
git add reference_data/schema.csv src/data_io.py tests/test_hsa_policy_inputs_unit.py
git commit -m "H0: HSA beneficiary, deadline, expense-bank and conformity inputs"
```

---

## Phase H1 — Terminal cliff

> **Attribution note.** Task 2 is a pure function and moves **no** projection number. Task 3 wires it into the Roth optimizer's objective, which changes which conversions get chosen and therefore **does** move the golden master. Keeping them in separate commits is what preserves attribution inside the combined H1+H3 release.

### Task 2: `hsa_terminal_tax()`

**Model · effort: opus · high.** A one-way tax rule where being wrong is silent and mis-prices every plan holding an HSA at death.

**Files:**
- Modify: `src/after_tax.py`
- Test: `tests/test_hsa_terminal_tax_unit.py` (create)

**Interfaces:**
- Consumes: `compute_fed_tax(amount, year, filing, brk_inf)` from `src.core`; `_f`, `_heir_filing_status` from this module.
- Produces: `hsa_terminal_tax(c, hsa_balance, terminal_year=None) -> float` — dollars of tax, not a rate.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_hsa_terminal_tax_unit.py
"""The HSA cliff is a single-year lump, which is why the 10-year-rule helper
cannot be reused: effective_heir_ten_year_rate spreads the balance over ten
slices, and that spreading is exactly what an inherited HSA does NOT get."""
import unittest

from src.after_tax import effective_heir_ten_year_rate, hsa_terminal_tax

BASE = {"roth_heir_filing_status": "Single", "brk_inf": 0.0,
        "plan_start": 2026, "plan_end": 2056}


class HsaTerminalTaxTests(unittest.TestCase):
    def test_spouse_beneficiary_owes_nothing(self):
        c = dict(BASE, hsa_beneficiary_type="spouse")
        self.assertEqual(hsa_terminal_tax(c, 500_000.0), 0.0)

    def test_charity_beneficiary_owes_nothing(self):
        c = dict(BASE, hsa_beneficiary_type="charity")
        self.assertEqual(hsa_terminal_tax(c, 500_000.0), 0.0)

    def test_zero_balance_owes_nothing(self):
        c = dict(BASE, hsa_beneficiary_type="non_spouse")
        self.assertEqual(hsa_terminal_tax(c, 0.0), 0.0)

    def test_non_spouse_lump_is_taxed_harder_than_a_ten_year_stretch(self):
        """The whole point of the finding. Same balance, same heir: one lump
        climbs into higher brackets than ten slices do."""
        c = dict(BASE, hsa_beneficiary_type="non_spouse")
        bal = 500_000.0
        lump = hsa_terminal_tax(c, bal)
        stretch = effective_heir_ten_year_rate(c, bal) * bal
        self.assertGreater(lump, stretch * 1.2,
                           "a single-year lump must cost materially more than a 10-year stretch")

    def test_effective_rate_rises_with_balance(self):
        c = dict(BASE, hsa_beneficiary_type="non_spouse")
        small = hsa_terminal_tax(c, 50_000.0) / 50_000.0
        large = hsa_terminal_tax(c, 800_000.0) / 800_000.0
        self.assertGreater(large, small)
```

- [ ] **Step 2: Run and confirm it fails**

Run: `RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS=1 python -m pytest tests/test_hsa_terminal_tax_unit.py -q`
Expected: FAIL — `ImportError: cannot import name 'hsa_terminal_tax'`.

- [ ] **Step 3: Implement**

Add to `src/after_tax.py`, directly below `effective_heir_ten_year_rate`:

```python
def hsa_terminal_tax(c: Mapping[str, Any], hsa_balance: Any,
                     terminal_year: Any = None) -> float:
    """Federal tax due on an HSA balance left at death, in dollars.

    A spouse beneficiary inherits the account AS an HSA -- fully tax-free, no
    event. Any other beneficiary is the cliff: the account ceases to be an HSA
    on the date of death and its entire fair-market value is ordinary income to
    the beneficiary IN THAT SINGLE YEAR. No SECURE 10-year stretch, no basis,
    no step-up.

    ``effective_heir_ten_year_rate`` is deliberately NOT reused. Its whole
    premise is spreading the balance across ten bracket-filling slices, and
    that spreading is precisely the relief an inherited HSA does not receive.
    Reusing it would understate this tax badly on large balances.
    """
    from .core import compute_fed_tax

    beneficiary = str(c.get("hsa_beneficiary_type", "spouse") or "spouse").strip().lower()
    if beneficiary in ("spouse", "charity"):
        return 0.0

    bal = max(0.0, _f(hsa_balance, 0.0))
    if bal <= 0:
        return 0.0

    filing = _heir_filing_status(c)
    brk_inf = _f(c.get("brk_inf", 0.0), 0.0)
    if terminal_year is None:
        terminal_year = c.get("plan_end", c.get("plan_start", 0))
    year0 = int(_f(terminal_year, 0.0))
    return max(0.0, compute_fed_tax(bal, year0, filing, brk_inf))
```

- [ ] **Step 4: Run and confirm it passes**

Run: `RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS=1 python -m pytest tests/test_hsa_terminal_tax_unit.py -q`
Expected: PASS, 5 tests.

- [ ] **Step 5: Confirm the golden master has NOT moved**

Run: `RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS=1 python -m pytest tests/test_frozen_sample_plan_golden_master_regression.py -q`
Expected: PASS. A pure function with no callers cannot move a projection. If this fails, something else is wrong — stop and investigate before continuing.

- [ ] **Step 6: Commit**

```bash
git add src/after_tax.py tests/test_hsa_terminal_tax_unit.py
git commit -m "H1.1: price the HSA terminal cliff as a single-year lump, not a 10-year stretch"
```

---

### Task 3: Wire the cliff into after-tax terminal net worth

**Model · effort: opus · high.** This is the task that moves every plan's numbers, and the record has been wrong about HSA treatment until now.

**Files:**
- Modify: `src/after_tax.py` (`estimate_terminal_pretax_deferred_tax` neighbourhood, ~line 251)
- Test: `tests/test_hsa_terminal_cliff_regression.py` (create)

**Interfaces:**
- Consumes: `hsa_terminal_tax` from Task 2.
- Produces: `estimate_terminal_hsa_deferred_tax(c, terminal) -> Dict[str, float]` with keys `terminal_hsa_nw`, `hsa_deferred_tax`, matching the shape `estimate_terminal_pretax_deferred_tax` already returns.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_hsa_terminal_cliff_regression.py
"""Pins the cliff's effect on after-tax terminal net worth WITHOUT involving the
optimizer. H1 and H3 ship in one release, so this is what keeps the two effects
attributable if a number later looks wrong."""
import unittest

from src.after_tax import estimate_terminal_hsa_deferred_tax

BASE = {"roth_heir_filing_status": "Single", "brk_inf": 0.0,
        "plan_start": 2026, "plan_end": 2056}
TERMINAL = {"hsa_nw": 400_000.0}


class HsaTerminalCliffTests(unittest.TestCase):
    def test_spouse_beneficiary_leaves_terminal_value_untouched(self):
        out = estimate_terminal_hsa_deferred_tax(dict(BASE, hsa_beneficiary_type="spouse"), TERMINAL)
        self.assertEqual(out["hsa_deferred_tax"], 0.0)
        self.assertEqual(out["terminal_hsa_nw"], 400_000.0)

    def test_non_spouse_beneficiary_takes_a_material_haircut(self):
        out = estimate_terminal_hsa_deferred_tax(dict(BASE, hsa_beneficiary_type="non_spouse"), TERMINAL)
        self.assertGreater(out["hsa_deferred_tax"], 80_000.0,
                           "a $400k lump to a Single heir must cost well over 20%")
        self.assertEqual(out["terminal_hsa_nw"], 400_000.0)

    def test_missing_hsa_in_terminal_is_not_an_error(self):
        out = estimate_terminal_hsa_deferred_tax(dict(BASE, hsa_beneficiary_type="non_spouse"), {})
        self.assertEqual(out["hsa_deferred_tax"], 0.0)
```

- [ ] **Step 2: Run and confirm it fails**

Run: `RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS=1 python -m pytest tests/test_hsa_terminal_cliff_regression.py -q`
Expected: FAIL — `ImportError: cannot import name 'estimate_terminal_hsa_deferred_tax'`.

- [ ] **Step 3: Implement**

```python
def estimate_terminal_hsa_deferred_tax(c: Mapping[str, Any],
                                       terminal: Mapping[str, Any]) -> Dict[str, float]:
    """Deferred tax embedded in a terminal HSA balance.

    Mirrors estimate_terminal_pretax_deferred_tax's shape so callers can treat
    the two the same way. Until this existed, hsa_nw flowed into after-tax
    terminal net worth at 100 cents on the dollar -- which made an HSA a
    strictly dominant asset and any drawdown optimizer's answer "never
    withdraw."
    """
    hsa_nw = max(0.0, _f(terminal.get("hsa_nw"), 0.0))
    return {
        "terminal_hsa_nw": hsa_nw,
        "hsa_deferred_tax": hsa_terminal_tax(c, hsa_nw),
    }
```

- [ ] **Step 4: Subtract it wherever pre-tax deferred tax is already subtracted**

Find every caller of `estimate_terminal_pretax_deferred_tax`:

```bash
grep -rn "estimate_terminal_pretax_deferred_tax" src/ | grep -v after_tax.py
```

At each site, subtract `estimate_terminal_hsa_deferred_tax(c, terminal)["hsa_deferred_tax"]` from after-tax terminal net worth alongside the existing pre-tax and capital-gains haircuts. Do not invent a new aggregation path — follow whatever the site already does.

- [ ] **Step 5: Run and confirm it passes**

Run: `RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS=1 python -m pytest tests/test_hsa_terminal_cliff_regression.py -q`
Expected: PASS, 3 tests.

- [ ] **Step 6: Observe the golden master move, and record why**

Run: `RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS=1 python -m pytest tests/test_frozen_sample_plan_golden_master_regression.py -q`

Expected on the frozen fixture: **PASS, unmoved**, because that fixture's beneficiary defaults to `spouse` and a spouse cliff is zero. If it fails, the fixture's beneficiary is not `spouse` — confirm which before re-pinning anything. Do **not** regenerate pins here; Task 16 owns the single regeneration.

- [ ] **Step 7: Commit**

```bash
git add src/after_tax.py tests/test_hsa_terminal_cliff_regression.py
git commit -m "H1.2: subtract the HSA terminal cliff from after-tax terminal net worth"
```

---

### Task 4: Feed the cliff to the Roth optimizer's objective

**Model · effort: sonnet · medium.** Mechanical wiring into an existing objective, but which scoring site to touch needs judgement.

**Files:**
- Modify: `src/planning_engines.py` (Roth optimizer scoring)
- Test: `tests/test_hsa_terminal_cliff_regression.py` (extend)

**Interfaces:**
- Consumes: `estimate_terminal_hsa_deferred_tax` from Task 3.

- [ ] **Step 1: Add the failing test**

```python
    def test_roth_objective_sees_the_hsa_cliff(self):
        """Both optimizers must score against ONE estate. If the Roth objective
        values a terminal HSA at 100c while the HSA optimizer values it at the
        cliff, the joint scoring in Task 9 is inconsistent by construction."""
        from src.planning_engines import _score_terminal_after_tax  # name per the local scorer
        spouse = _score_terminal_after_tax(dict(BASE, hsa_beneficiary_type="spouse"), TERMINAL)
        heir = _score_terminal_after_tax(dict(BASE, hsa_beneficiary_type="non_spouse"), TERMINAL)
        self.assertLess(heir, spouse)
```

Replace `_score_terminal_after_tax` with the actual scorer name found in step 2.

- [ ] **Step 2: Find the real scorer**

```bash
grep -rn "estimate_terminal_pretax_deferred_tax\|after_tax_terminal" src/planning_engines.py | head
```

Use the name that appears. Update the test to match before running it.

- [ ] **Step 3: Run and confirm it fails**

Expected: FAIL — spouse and non-spouse score identically, because the objective cannot see the cliff.

- [ ] **Step 4: Subtract the HSA cliff in that scorer, then confirm it passes**

- [ ] **Step 5: Fast tier, then commit**

```bash
RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS=1 python -m pytest tests/ -m "not slow" -q > /tmp/h1.txt 2>&1
grep -E "^(FAILED|ERROR)" /tmp/h1.txt; tail -3 /tmp/h1.txt
git add -u && git commit -m "H1.3: Roth objective scores the HSA cliff, so both optimizers see one estate"
```

---

## Phase H2 — Decouple withdrawals from current-year medical spend

### Task 5: Draw against the expense bank, not `wellness_cost`

**Model · effort: opus · medium.** The withdrawal cascade is load-bearing and every existing mode must keep its behavior.

**Files:**
- Modify: `src/planning_engines.py:908` (`withdraw_hsa_window`)
- Test: `tests/test_hsa_withdrawal_decoupling_regression.py` (create)

**Interfaces:**
- Produces: `hsa_available_to_draw(c, bal, cumulative_drawn) -> float`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_hsa_withdrawal_decoupling_regression.py
"""spend_as_needed used to cap the HSA draw at that year's wellness cost. With a
substantiated expense bank, the cap is the bank, not the calendar."""
import unittest
from src.planning_engines import withdraw_hsa_window

C = {"hsa_ids": ["Member_1_HSA"], "hsa_withdrawal_mode": "spend_as_needed",
     "hsa_expense_bank": None}


class HsaDecouplingTests(unittest.TestCase):
    def test_unlimited_bank_allows_a_draw_beyond_this_years_medical_cost(self):
        bal = {"Member_1_HSA": 100_000.0}
        out = withdraw_hsa_window(dict(C), bal, 2030, wellness_cost=5_000.0, requested=40_000.0)
        self.assertAlmostEqual(out["amount"], 40_000.0, places=6)

    def test_a_finite_bank_caps_the_draw(self):
        bal = {"Member_1_HSA": 100_000.0}
        out = withdraw_hsa_window(dict(C, hsa_expense_bank=12_000.0), bal, 2030,
                                  wellness_cost=5_000.0, requested=40_000.0)
        self.assertAlmostEqual(out["amount"], 12_000.0, places=6)

    def test_no_requested_amount_preserves_the_old_wellness_behavior(self):
        """Backward compatibility: existing plans pass no `requested` and must be
        bit-identical to today."""
        bal = {"Member_1_HSA": 100_000.0}
        out = withdraw_hsa_window(dict(C), bal, 2030, wellness_cost=5_000.0)
        self.assertAlmostEqual(out["amount"], 5_000.0, places=6)
```

- [ ] **Step 2: Run and confirm it fails**

Expected: FAIL — `withdraw_hsa_window() got an unexpected keyword argument 'requested'`.

- [ ] **Step 3: Add the optional `requested` parameter and bank cap**

Change the signature to `withdraw_hsa_window(c, bal, year, wellness_cost=0.0, requested=None, cumulative_drawn=0.0)`. In the `spend_as_needed` branch, the target becomes `wellness_cost if requested is None else requested`, then clamp by `hsa_available_to_draw`. Leave `annual_pct` and `smooth_window` untouched.

```python
def hsa_available_to_draw(c: Mapping, bal: BalanceMap, cumulative_drawn: float = 0.0) -> float:
    """Dollars the HSA can pay out tax-free right now.

    Bounded by the account balances and by the substantiated expense bank. A
    bank of None means unlimited, which is the default: most households have
    far more unreimbursed receipts than they realize, and the constraint only
    binds once someone actually enters a figure.
    """
    ids = list(c.get("hsa_ids", []) or [])
    balance = sum(max(0.0, float(bal.get(aid, 0.0) or 0.0)) for aid in ids)
    bank = c.get("hsa_expense_bank")
    if bank is None:
        return balance
    return max(0.0, min(balance, float(bank) - max(0.0, float(cumulative_drawn))))
```

- [ ] **Step 4: Run and confirm it passes**

- [ ] **Step 5: Full suite — this touches the cascade**

```bash
RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS=1 python -m pytest tests/ -n auto -q > /tmp/h2.txt 2>&1
grep -E "^(FAILED|ERROR)" /tmp/h2.txt
```

Expected: no FAILED/ERROR. A `PermissionError: WinError 5` on a `retirement_system_test_workspace_*` temp path is the documented Windows file-lock flake — rerun that one file serially to confirm before treating it as real.

- [ ] **Step 6: Commit**

```bash
git add -u && git commit -m "H2.1: HSA draws are bounded by the expense bank, not the current year's medical cost"
```

---

### Task 6: Non-qualified withdrawal branch

**Model · effort: sonnet · medium.** Small, specified, but the pre-65 penalty is a real tax rule.

**Files:**
- Modify: `src/planning_engines.py`
- Test: `tests/test_hsa_withdrawal_decoupling_regression.py` (extend)

- [ ] **Step 1: Add the failing test**

```python
    def test_draw_beyond_the_bank_is_blocked_by_default(self):
        bal = {"Member_1_HSA": 100_000.0}
        out = withdraw_hsa_window(dict(C, hsa_expense_bank=10_000.0), bal, 2030, requested=50_000.0)
        self.assertAlmostEqual(out["amount"], 10_000.0, places=6)
        self.assertAlmostEqual(out.get("taxable_amount", 0.0), 0.0, places=6)
        self.assertAlmostEqual(out.get("penalty", 0.0), 0.0, places=6)

    def test_allow_taxable_adds_income_and_a_pre65_penalty(self):
        bal = {"Member_1_HSA": 100_000.0}
        c = dict(C, hsa_expense_bank=10_000.0, hsa_nonqualified_treatment="allow_taxable",
                 hsa_owner_age=60)
        out = withdraw_hsa_window(c, bal, 2030, requested=50_000.0)
        self.assertAlmostEqual(out["amount"], 50_000.0, places=6)
        self.assertAlmostEqual(out["taxable_amount"], 40_000.0, places=6)
        self.assertAlmostEqual(out["penalty"], 8_000.0, places=6)  # 20% of the non-qualified part

    def test_after_65_there_is_income_but_no_penalty(self):
        bal = {"Member_1_HSA": 100_000.0}
        c = dict(C, hsa_expense_bank=10_000.0, hsa_nonqualified_treatment="allow_taxable",
                 hsa_owner_age=70)
        out = withdraw_hsa_window(c, bal, 2030, requested=50_000.0)
        self.assertAlmostEqual(out["taxable_amount"], 40_000.0, places=6)
        self.assertAlmostEqual(out["penalty"], 0.0, places=6)
```

- [ ] **Step 2: Run, confirm failure, implement, confirm pass**

Return `taxable_amount` and `penalty` keys (0.0 in the qualified case so callers never branch on presence). Route `taxable_amount` into ordinary income and `penalty` into the tax total at the `deterministic_engine.py:1851` call site.

- [ ] **Step 3: Fast tier, then commit**

```bash
git add -u && git commit -m "H2.2: non-qualified HSA withdrawals as income, with the pre-65 penalty"
```

---

## Phase H3 — Constrained phasing optimizer

### Task 7: Resolve the deadline year

**Model · effort: opus · medium.** Small surface, but it is the plan's risk dial.

**Files:**
- Create: `src/hsa_schedule.py`
- Test: `tests/test_hsa_optimizer_regression.py` (create)

**Interfaces:**
- Produces: `resolve_consume_by_year(c, rows) -> int`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_hsa_optimizer_regression.py
import unittest
from src.hsa_schedule import resolve_consume_by_year


class ConsumeByTests(unittest.TestCase):
    def test_explicit_year_is_honored(self):
        self.assertEqual(resolve_consume_by_year({"hsa_consume_by": "2044"}, []), 2044)

    def test_percentile_form_resolves_within_the_plan_horizon(self):
        c = {"hsa_consume_by": "second_death_p90", "plan_start": 2026, "plan_end": 2056}
        yr = resolve_consume_by_year(c, [])
        self.assertGreaterEqual(yr, 2026)
        self.assertLessEqual(yr, 2056)

    def test_a_higher_percentile_never_resolves_earlier(self):
        c = {"plan_start": 2026, "plan_end": 2056}
        p50 = resolve_consume_by_year(dict(c, hsa_consume_by="second_death_p50"), [])
        p90 = resolve_consume_by_year(dict(c, hsa_consume_by="second_death_p90"), [])
        self.assertGreaterEqual(p90, p50)

    def test_unparseable_value_falls_back_to_the_conservative_default(self):
        c = {"hsa_consume_by": "nonsense", "plan_start": 2026, "plan_end": 2056}
        self.assertEqual(resolve_consume_by_year(c, []),
                         resolve_consume_by_year(dict(c, hsa_consume_by="second_death_p90"), []))
```

- [ ] **Step 2: Run, confirm failure, implement, confirm pass**

Parse `second_death_pNN` against the engine's existing mortality machinery; fall back to `plan_end` when no distribution is available. **Never** silently fall back to an earlier year than the default — an early fallback is the expensive failure mode.

- [ ] **Step 3: Commit**

```bash
git add src/hsa_schedule.py tests/test_hsa_optimizer_regression.py
git commit -m "H3.1: resolve the HSA consume-by deadline, defaulting to p90"
```

---

### Task 8: Per-year scoring

**Model · effort: opus · high.** The scoring terms are the feature. Getting a sign or a filing status wrong is silent and produces a plausible schedule.

**Files:**
- Modify: `src/hsa_schedule.py`, `reference_data/schema.csv`
- Test: `tests/test_hsa_optimizer_regression.py` (extend)

**Interfaces:**
- Produces: `score_year(c, row, amount) -> float` — present-valued benefit in dollars of drawing `amount` in that row's year.

- [ ] **Step 1: Add failing tests, one per scoring term**

```python
class ScoringTests(unittest.TestCase):
    def test_a_higher_marginal_rate_year_scores_higher(self):
        from src.hsa_schedule import score_year
        lo = {"year": 2030, "effective_marginal_rate": 0.12, "irmaa_tier": 0}
        hi = {"year": 2030, "effective_marginal_rate": 0.32, "irmaa_tier": 0}
        self.assertGreater(score_year({}, hi, 10_000.0), score_year({}, lo, 10_000.0))

    def test_a_year_that_avoids_an_irmaa_crossing_scores_higher(self):
        from src.hsa_schedule import score_year
        flat = {"year": 2030, "effective_marginal_rate": 0.22, "irmaa_tier": 1,
                "irmaa_headroom": 50_000.0}
        cliff = {"year": 2030, "effective_marginal_rate": 0.22, "irmaa_tier": 1,
                 "irmaa_headroom": 500.0}
        self.assertGreater(score_year({}, cliff, 10_000.0), score_year({}, flat, 10_000.0))

    def test_survivor_years_score_higher_than_joint_years_at_equal_income(self):
        """Section 1.3 of the spec: the survivor files Single at compressed
        brackets, so the displaced dollar is dearer."""
        from src.hsa_schedule import score_year
        joint = {"year": 2040, "filing": "MFJ", "effective_marginal_rate": 0.22, "irmaa_tier": 0}
        single = {"year": 2040, "filing": "Single", "effective_marginal_rate": 0.32, "irmaa_tier": 0}
        self.assertGreater(score_year({}, single, 10_000.0), score_year({}, joint, 10_000.0))
```

- [ ] **Step 2: Run, confirm all three fail, implement, confirm pass**

Implement displacement, cliff, carry-cost and residual terms. Discount with `roth_tax_discount_rate` via the existing helper — do **not** introduce a second discount rate.

- [ ] **Step 3: Add the `optimize` mode and objective rows to schema.csv**

```csv
HSA Policy,Withdrawals,hsa_withdrawal_mode,choice,FALSE,spend_as_needed,,,spend_as_needed | annual_pct | smooth_window | optimize; optimize phases the drawdown to consume the balance by hsa_consume_by at the lowest present-valued tax cost.
HSA Policy,Withdrawals,hsa_irmaa_guardrail_mode,choice,FALSE,AVOID_NEXT_TIER,,,IGNORE | WARN_ONLY | AVOID_NEXT_TIER; Medicare threshold guardrail for optimizer-chosen HSA draws.
HSA Policy,Withdrawals,hsa_min_ending_balance,currency,FALSE,0,0,,Floor the optimizer must leave in the HSA in every year before the deadline.
```

Note there is **no** `hsa_objective_mode` and **no** `hsa_tax_discount_rate` row. That is deliberate: the objective is shared with Roth so joint scoring in Task 9 is well-defined.

- [ ] **Step 4: Resync manifest, run fast tier, commit**

```bash
python tools/check_plan_data_sync.py --write
git add -u && git commit -m "H3.2: per-year HSA scoring and the optimize mode"
```

---

### Task 9: Joint scoring with Roth conversions, and the surplus waterfall

**Model · effort: opus · high.** The most likely correctness bug in the feature. Scored separately, bracket headroom is double-counted and the waterfall's second priority cannot work at all.

**Files:**
- Modify: `src/hsa_schedule.py`, `src/planning_engines.py`
- Test: `tests/test_hsa_optimizer_regression.py` (extend)

**Interfaces:**
- Produces: `allocate_surplus(c, row, surplus) -> Dict[str, float]` with keys `to_spending`, `to_conversion_tax`, `to_taxable`.

- [ ] **Step 1: Write the failing tests**

```python
class SurplusWaterfallTests(unittest.TestCase):
    def test_spending_need_is_funded_before_anything_else(self):
        from src.hsa_schedule import allocate_surplus
        out = allocate_surplus({}, {"spending_need": 30_000.0, "conversion_tax_capacity": 20_000.0},
                               50_000.0)
        self.assertAlmostEqual(out["to_spending"], 30_000.0, places=6)
        self.assertAlmostEqual(out["to_conversion_tax"], 20_000.0, places=6)
        self.assertAlmostEqual(out["to_taxable"], 0.0, places=6)

    def test_leftover_after_conversion_tax_spills_to_taxable(self):
        from src.hsa_schedule import allocate_surplus
        out = allocate_surplus({}, {"spending_need": 10_000.0, "conversion_tax_capacity": 5_000.0},
                               50_000.0)
        self.assertAlmostEqual(out["to_taxable"], 35_000.0, places=6)

    def test_surplus_never_increases_the_conversion_itself(self):
        """The guardrail. Surplus changes how conversion tax is FUNDED, never how
        much conversion is worth doing. Without this pin, 'free' tax money
        quietly inflates the recommendation."""
        from src.planning_engines import choose_conversion_amount
        base = choose_conversion_amount({"hsa_surplus_available": 0.0})
        with_surplus = choose_conversion_amount({"hsa_surplus_available": 100_000.0})
        self.assertAlmostEqual(with_surplus, base, places=6)


class JointScoringTests(unittest.TestCase):
    def test_headroom_is_not_double_counted(self):
        """An HSA draw lowers AGI and frees headroom; a conversion consumes it.
        Scored separately, both claim the same dollars."""
        from src.hsa_schedule import joint_headroom_used
        used = joint_headroom_used({}, {"bracket_room": 40_000.0},
                                   hsa_draw=25_000.0, conversion=40_000.0)
        self.assertLessEqual(used, 40_000.0 + 25_000.0)
        self.assertGreater(used, 40_000.0)
```

- [ ] **Step 2: Run, confirm failure, implement, confirm pass**

Replace `choose_conversion_amount` with the real conversion-sizing function name found via `grep -rn "def .*conversion" src/planning_engines.py | head`.

- [ ] **Step 3: Full suite, then commit**

```bash
RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS=1 python -m pytest tests/ -n auto -q > /tmp/h3.txt 2>&1
grep -E "^(FAILED|ERROR)" /tmp/h3.txt
git add -u && git commit -m "H3.3: joint HSA/Roth scoring and the surplus waterfall"
```

---

### Task 10: Schedule search, feasibility states, and the two rejection tests

**Model · effort: opus · high.** Task 10's second test is the only thing in the plan that catches a mis-weighted residual term.

**Files:**
- Modify: `src/hsa_schedule.py`
- Test: `tests/test_hsa_optimizer_regression.py` (extend)

**Interfaces:**
- Produces: `build_schedule(c, rows) -> Dict[str, Any]` with keys `by_year: Dict[int, float]`, `feasibility: str` (`'feasible' | 'feasible_with_surplus' | 'infeasible'`), `residual: float`.

- [ ] **Step 1: Write the failing tests**

```python
class ScheduleSearchTests(unittest.TestCase):
    def test_a_feasible_plan_consumes_the_balance_by_the_deadline(self):
        from src.hsa_schedule import build_schedule
        out = build_schedule(FEASIBLE_C, FEASIBLE_ROWS)
        self.assertEqual(out["feasibility"], "feasible")
        self.assertAlmostEqual(out["residual"], 0.0, places=2)

    def test_an_oversized_balance_reports_infeasible_and_never_moves_the_deadline(self):
        from src.hsa_schedule import build_schedule, resolve_consume_by_year
        out = build_schedule(OVERSIZED_C, FEASIBLE_ROWS)
        self.assertEqual(out["feasibility"], "infeasible")
        self.assertGreater(out["residual"], 0.0)
        self.assertLessEqual(max(out["by_year"]), resolve_consume_by_year(OVERSIZED_C, FEASIBLE_ROWS))

    def test_optimizer_beats_smooth_window_by_weighting_survivor_years(self):
        """(a) Names the wrong implementation it must reject: a level drawdown.
        Beating it on total score is not enough -- it must beat it BECAUSE more
        dollars land in survivor years."""
        from src.hsa_schedule import build_schedule, schedule_score, level_schedule
        opt = build_schedule(SURVIVOR_C, SURVIVOR_ROWS)
        lvl = level_schedule(SURVIVOR_C, SURVIVOR_ROWS)
        self.assertGreater(schedule_score(SURVIVOR_C, SURVIVOR_ROWS, opt["by_year"]),
                           schedule_score(SURVIVOR_C, SURVIVOR_ROWS, lvl))
        survivor_years = [r["year"] for r in SURVIVOR_ROWS if r["filing"] == "Single"]
        opt_share = sum(opt["by_year"].get(y, 0.0) for y in survivor_years) / sum(opt["by_year"].values())
        lvl_share = sum(lvl.get(y, 0.0) for y in survivor_years) / sum(lvl.values())
        self.assertGreater(opt_share, lvl_share)

    def test_optimizer_does_not_back_load_into_the_final_years(self):
        """(b) The failure mode that appears if the residual term is missing or
        mis-weighted. Such a schedule satisfies every constraint and feasibility
        check while maximizing exposure to an early death. Nothing else catches it."""
        from src.hsa_schedule import build_schedule, resolve_consume_by_year
        out = build_schedule(SURVIVOR_C, SURVIVOR_ROWS)
        deadline = resolve_consume_by_year(SURVIVOR_C, SURVIVOR_ROWS)
        years = sorted(out["by_year"])
        last_three = [y for y in years if y > deadline - 3]
        share = sum(out["by_year"][y] for y in last_three) / sum(out["by_year"].values())
        self.assertLess(share, 0.50,
                        "more than half the balance in the final three years means the "
                        "residual term is not pricing early-death risk")
```

Define `FEASIBLE_C` / `OVERSIZED_C` / `SURVIVOR_C` / `FEASIBLE_ROWS` / `SURVIVOR_ROWS` as module-level fixtures at the top of the file. `SURVIVOR_ROWS` must contain a filing-status change partway through (`MFJ` then `Single`).

- [ ] **Step 2: Run and confirm each fails for the right reason**

Run each test individually. A test that errors on a missing fixture is not a valid red — fix the fixture and re-run until the failure is the assertion.

- [ ] **Step 3: Implement, confirm pass**

- [ ] **Step 4: Full suite, then commit**

```bash
git add -u && git commit -m "H3.4: constrained schedule search, feasibility states, survivor-weighting and anti-back-loading guards"
```

---

## Phase H4 — Override surface

### Task 11: `client_hsa_schedule.csv` flat table

**Model · effort: sonnet · medium.** Follows an established pattern; the registration points need care.

**Files:**
- Modify: `src/plan_data_registry.py`, `src/server/app_core.py`
- Test: `tests/test_hsa_schedule_override_contract.py` (create)

**Interfaces:**
- Produces: a flat CSV with header `year,optimizer_amount,override_amount,locked,note`, stored in `client_files` and mirrored to `input/`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_hsa_schedule_override_contract.py
import unittest
from src.plan_data_registry import flat_plan_data_files


class HsaScheduleRegistrationTests(unittest.TestCase):
    def test_schedule_file_is_registered_as_a_flat_table(self):
        self.assertIn("client_hsa_schedule.csv", flat_plan_data_files())
```

Replace `flat_plan_data_files` with the real accessor found via `grep -n "client_liabilities.csv" src/plan_data_registry.py`.

- [ ] **Step 2: Run, confirm failure, register it exactly where `client_liabilities.csv` is registered, confirm pass**

- [ ] **Step 3: Resync the manifest, run fast tier, commit**

```bash
python tools/check_plan_data_sync.py --write
git add -u && git commit -m "H4.1: register client_hsa_schedule.csv as a flat plan-data table"
```

---

### Task 12: Precedence resolver

**Model · effort: opus · medium.** Precedence bugs are silent and destroy user trust the first time an override vanishes.

**Files:**
- Modify: `src/hsa_schedule.py`
- Test: `tests/test_hsa_schedule_override_contract.py` (extend)

**Interfaces:**
- Produces: `resolve_year_amount(row) -> Tuple[float, str]` — the amount and its source (`'override' | 'locked' | 'optimizer' | 'mode'`).

- [ ] **Step 1: Write the failing tests**

```python
class PrecedenceTests(unittest.TestCase):
    def test_override_wins_over_everything(self):
        from src.hsa_schedule import resolve_year_amount
        amt, src = resolve_year_amount({"optimizer_amount": 10_000.0, "override_amount": 25_000.0,
                                        "locked": True})
        self.assertAlmostEqual(amt, 25_000.0, places=6)
        self.assertEqual(src, "override")

    def test_locked_without_override_pins_the_optimizer_value(self):
        from src.hsa_schedule import resolve_year_amount
        amt, src = resolve_year_amount({"optimizer_amount": 10_000.0, "override_amount": None,
                                        "locked": True})
        self.assertAlmostEqual(amt, 10_000.0, places=6)
        self.assertEqual(src, "locked")

    def test_optimizer_value_is_used_when_nothing_else_applies(self):
        from src.hsa_schedule import resolve_year_amount
        amt, src = resolve_year_amount({"optimizer_amount": 10_000.0, "override_amount": None,
                                        "locked": False})
        self.assertEqual(src, "optimizer")

    def test_zero_is_a_real_override_not_an_absent_one(self):
        """The classic falsy bug: 0.0 must not be treated as 'no override'."""
        from src.hsa_schedule import resolve_year_amount
        amt, src = resolve_year_amount({"optimizer_amount": 10_000.0, "override_amount": 0.0,
                                        "locked": False})
        self.assertAlmostEqual(amt, 0.0, places=6)
        self.assertEqual(src, "override")
```

- [ ] **Step 2: Run, confirm failure, implement as ONE pure function, confirm pass**

Do not scatter this logic across call sites. Test the fourth case especially — `if row["override_amount"]:` is wrong and `if row["override_amount"] is not None:` is right.

- [ ] **Step 3: Commit**

```bash
git add -u && git commit -m "H4.2: single pure precedence resolver for HSA schedule years"
```

---

### Task 13: Round-trip contract

**Model · effort: opus · high.** This is the user-facing contract. If a re-run eats an override, the feature is worse than not having it.

**Files:**
- Modify: `src/hsa_schedule.py`
- Test: `tests/test_hsa_schedule_override_contract.py` (extend)

- [ ] **Step 1: Write the failing tests**

```python
class RoundTripTests(unittest.TestCase):
    def test_rerunning_the_optimizer_never_touches_override_values(self):
        from src.hsa_schedule import rerun_optimizer
        rows = [{"year": 2030, "optimizer_amount": 10_000.0, "override_amount": 25_000.0,
                 "locked": False}]
        out = rerun_optimizer(FEASIBLE_C, FEASIBLE_ROWS, rows)
        self.assertAlmostEqual(out[0]["override_amount"], 25_000.0, places=6)

    def test_rerunning_does_refresh_the_optimizer_column(self):
        from src.hsa_schedule import rerun_optimizer
        rows = [{"year": 2030, "optimizer_amount": 1.0, "override_amount": None, "locked": False}]
        out = rerun_optimizer(FEASIBLE_C, FEASIBLE_ROWS, rows)
        self.assertNotAlmostEqual(out[0]["optimizer_amount"], 1.0, places=6)

    def test_locked_years_are_planned_around_not_through(self):
        from src.hsa_schedule import rerun_optimizer
        rows = [{"year": 2030, "optimizer_amount": 10_000.0, "override_amount": 40_000.0,
                 "locked": True}]
        out = rerun_optimizer(FEASIBLE_C, FEASIBLE_ROWS, rows)
        self.assertAlmostEqual(out[0]["override_amount"], 40_000.0, places=6)

    def test_clearing_an_override_returns_the_year_to_optimizer_control(self):
        from src.hsa_schedule import resolve_year_amount
        _, src = resolve_year_amount({"optimizer_amount": 10_000.0, "override_amount": None,
                                      "locked": False})
        self.assertEqual(src, "optimizer")

    def test_overrides_that_break_the_deadline_report_infeasible(self):
        """Honor the user's numbers, surface the consequence. Never silently
        redistribute into locked or overridden years."""
        from src.hsa_schedule import rerun_optimizer, schedule_feasibility
        rows = [{"year": y, "optimizer_amount": 0.0, "override_amount": 0.0, "locked": True}
                for y in range(2030, 2045)]
        out = rerun_optimizer(OVERSIZED_C, FEASIBLE_ROWS, rows)
        self.assertEqual(schedule_feasibility(OVERSIZED_C, out), "infeasible")
```

- [ ] **Step 2: Run, confirm failure, implement, confirm pass**

- [ ] **Step 3: Full suite, then commit**

```bash
git add -u && git commit -m "H4.3: HSA override round-trip contract - re-runs cannot eat user intent"
```

---

### Task 14: Per-year override UI

**Model · effort: sonnet · medium.** Follows established dashboard-module patterns.

**Files:**
- Modify: the YTD/HSA-adjacent decomp module under `frontend/js/`
- Test: `tests/test_hsa_schedule_override_contract.py` (extend, via `tests._decomp_dashboard.dashboard_js_text()`)

- [ ] **Step 1: Add the failing assertion**

```python
class HsaScheduleUiTests(unittest.TestCase):
    def test_schedule_table_shows_optimizer_and_override_side_by_side(self):
        from tests._decomp_dashboard import dashboard_js_text
        js = dashboard_js_text()
        self.assertIn("function renderHsaSchedule", js)
        self.assertIn("hsa-optimizer-amount", js)
        self.assertIn("hsa-override-amount", js)
        self.assertIn("hsa-schedule-feasibility", js)
```

- [ ] **Step 2: Run, confirm failure, implement, confirm pass**

Read plan-data through `dashboard_js_text()`, never `dashboard.js` directly — a direct read fails the guard added in `4b6c818`. After editing any extracted module, regenerate the window bridge in the **load-bearing order**:

```bash
node tools/js_codemod/census.mjs && node tools/js_codemod/convert_dashboard.mjs
```

- [ ] **Step 3: Verify in a real browser, not just in source text**

```bash
RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS=1 npx playwright test tests/e2e/nav-integrity.spec.js --reporter=line
```

Expected: 1 passed. Python tests only assert on source text; only this proves the bridge reaches the new functions at runtime.

- [ ] **Step 4: Commit**

```bash
git add -u && git commit -m "H4.4: per-year HSA schedule UI with optimizer/override side by side"
```

---

## Phase H5 — Reporting and disclosure

### Task 15: Sheet output and the disclosure guard

**Model · effort: opus · medium.** Client-facing advice; the limits must ship with the number.

**Files:**
- Modify: the HSA-owning sheet builder under `src/reporting/`
- Test: `tests/test_workbook_pdf_build_snapshot.py` (extend)

- [ ] **Step 1: Write the failing disclosure test**

```python
    def test_hsa_schedule_discloses_its_modeling_limits(self):
        import openpyxl
        from src.reporting.workbook_format_config import stable_name_for_sheet_title
        wb = openpyxl.load_workbook(self.workbook_path, data_only=True, read_only=True)
        sheets = [n for n in wb.sheetnames
                  if stable_name_for_sheet_title(n) == "<stable name of the HSA sheet>"]
        if not sheets:
            self.skipTest("HSA module off in this build")
        text = "\n".join(str(c) for row in wb[sheets[0]].iter_rows(values_only=True)
                         for c in row if c is not None)
        self.assertIn("optimized on the deterministic path", text)
        self.assertIn("shares the Roth conversion objective", text)
```

Resolve the sheet through `stable_name_for_sheet_title`, never a hardcoded `3A.`-style prefix — section letters are recomputed per build and shift when optional modules toggle.

- [ ] **Step 2: Run, confirm failure, add the schedule table and disclosure rows, confirm pass**

Disclosure must state: optimized on the deterministic path only; HSA modeled at bucket level in the vectorized MC so a schedule moves the success rate only through balances; the deadline rests on a longevity percentile and is a planning choice, shown with the residual exposure if the household outlives it; and the objective is shared with Roth, so changing either retunes both.

- [ ] **Step 3: Commit**

```bash
git add -u && git commit -m "H5.1: HSA drawdown schedule on the workbook, with its modeling limits"
```

---

### Task 16: Golden-master regeneration and changelog

**Model · effort: haiku · low.** Bookkeeping with a verifiable output — the regen block prints the constants.

**Files:**
- Modify: `tests/test_frozen_sample_plan_golden_master_regression.py`, `documentation/GOLDEN_MASTER_CHANGELOG.md`

- [ ] **Step 1: Regenerate**

```bash
RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS=1 python -m tests.test_frozen_sample_plan_golden_master_regression
```

Use `-m`; running it as a path puts `tests/` on `sys.path` instead of the repo root and dies with `ModuleNotFoundError: No module named 'src'`.

- [ ] **Step 2: Confirm the move is attributable before re-pinning**

The frozen fixture defaults to a `spouse` beneficiary, so the cliff is zero and **the pins should not move at all** unless the optimizer changed a conversion. If they moved, name which task did it — Task 3/4 (cliff in the objective) or Tasks 8–10 (schedule changes AGI). Do not re-pin a number you cannot attribute.

- [ ] **Step 3: Write the changelog entry**

Cover both effects separately even though they ship together: the HSA terminal cliff now reducing after-tax terminal net worth, and the optimizer changing the drawdown. State the blast radius: plans with a spouse beneficiary and no `optimize` mode are unmoved.

- [ ] **Step 4: Full suite in both interpreters, then commit**

```bash
RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS=1 python -m pytest tests/ -n auto -q > /tmp/final.txt 2>&1
grep -E "^(FAILED|ERROR)" /tmp/final.txt; tail -3 /tmp/final.txt
git status --short input/
git add -u && git commit -m "H5.3: regenerate the golden master for the HSA cliff and optimizer"
```

---

## Self-Review

**Spec coverage.** §2.1 B1/B3/B4/B5 → Tasks 1, 7, 8. §2.3 M1 → Task 1 (`hsa_state_conformity` input; consumption by the tax engine is **deliberately deferred** — see Open Items). §2.4 W1/W2/W3 → Tasks 1, 5, 6. §3.1 objective → Tasks 4, 8. §3.2 waterfall → Task 9. §3.3 feasibility → Task 10. §3.4 override contract → Tasks 11–14. §3.5 decoupling → Task 5. §3.6 limits → Task 15.

**Type consistency.** `build_schedule` returns `by_year` / `feasibility` / `residual` in Tasks 10 and 13. `resolve_year_amount` returns `(float, str)` in Tasks 12 and 13. `allocate_surplus` keys `to_spending` / `to_conversion_tax` / `to_taxable` used only in Task 9. `hsa_terminal_tax` returns **dollars**, not a rate, in Tasks 2 and 3.

**Named unknowns.** Three symbols are resolved by `grep` during execution rather than guessed: the Roth terminal scorer (Task 4), the conversion-sizing function (Task 9), and the flat-file registry accessor (Task 11). Each step says how to find it.

## Open Items

- **M1 consumption.** Task 1 adds `hsa_state_conformity` as an input, but no task makes the tax engine *use* it. Deliberate: it only matters for CA/NJ residents and needs its own state-tax work. If the household has or may acquire such residency, this needs a task before H5.
- **B3 verified.** `account_registry` already carries `owner_idx` and `owner_name` (`src/core.py:56`), so per-HSA ownership needs no new input. The first-death rollover logic can rely on it.
- **`'optimize'` is not reachable from real plan data — found during Task 15, 2026-08-19.** `src/data_io.py:1264-1266` coerces any `hsa_withdrawal_mode` outside `spend_as_needed`/`annual_pct`/`smooth_window` back to `spend_as_needed`; the UI (`app_core.py:1224`) and schema row (`:830`) offer the same three. **The entire H0-H5 optimizer built across Tasks 1-15 currently has no way to be turned on by a real household.** Deliberately left out of scope for Task 15 (a reporting task) and every task before it — widening the `data_io` allowlist is not a safe one-line change: `planning_engines.py`'s `withdraw_hsa_window` has no `'optimize'` case either, so an admitted value would silently fall through to the `smooth_window` branch there today, giving **wrong, silent engine semantics**, not just an inert value. Needs its own task: admit `'optimize'` in `data_io.py` and the UI schema, add the corresponding branch in `planning_engines.py` that actually calls `rerun_optimizer`/`build_schedule` and applies the resulting schedule to the withdrawal cascade, and assess golden-master impact before merging. Until that task lands, this whole feature is dark in production — reachable only via direct Python calls in tests.
