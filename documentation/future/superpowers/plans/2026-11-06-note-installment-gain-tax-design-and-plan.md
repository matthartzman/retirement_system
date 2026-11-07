# Note Receivable installment-sale gain tax — design and plan

Status: approved

Date: 2026-11-06. Decisions confirmed by the user in chat the same day (section 1).

## 1. Intent and decisions

The RedMane Note was received for stock the household sold. Each principal payment is partly a return of
basis and partly capital gain, reported each year on Form 8949 under the installment method. The plan today
treats all principal as tax-free, so it under-taxes 2026–2033 by roughly $51.8K of gain a year.

What the user asked for, in priority order:

1. **Taxes correct.** Each year's gain on the note is taxed the way the CPA reports it: a short-term part
   (Part I, ordinary rates) and a long-term part (Part II, capital-gain rates).
2. **Net worth and cash flow close.** No change is needed to either.

Decisions:

- **Inputs mirror Form 8949.** The user enters, per note, the short-term and long-term proceeds and basis from
  one year's 8949 (the CPA's figures), not percentages. Their 2025 return shows:

  | 8949 part | Proceeds | Basis | Gain |
  |---|---|---|---|
  | I (short-term) | $10,671 | $0 | $10,671 |
  | II (long-term) | $48,611 | $7,500 | $41,111 |
  | Total | $59,282 | $7,500 | $51,782 |

  The two proceeds add up to the note's annual principal payment ($59,281.62).
- **Net worth stays at remaining principal.** For a note whose interest is charged on the outstanding balance,
  remaining principal equals the present value of all remaining principal and interest discounted at the note's
  own rate, so interest is already reflected. The user chose this over an NPV at the 5% annuity rate (~$549K at
  plan start) and over the undiscounted total (~$636K). No discount-rate input is added.
- **Pre-tax valuation**, consistent with annuities, pension and pre-tax IRAs: net worth does not subtract the
  tax still owed on the remaining gain.

## 2. Goals, non-goals, anti-goals

**Goals**

- Tax each year's installment gain: short-term as ordinary income, long-term at LTCG rates, with NIIT, state
  tax, AGI, IRMAA MAGI and Social Security provisional income following the existing capital-gain paths.
- Show the gain and its tax on the projection tax sheet so the user can tie it to the return.
- Read the interest schedule for every year the note pays, not just plan_start..plan_start+7.

**Non-goals**

- Changing net worth, the note balance, or the principal/interest cash received.
- The Current Snapshot (`financial_trends_reporter`) note handling.
- Installment obligations at death (IRD, no step-up): the note keeps paying the survivor as today.
- Fixing the annuity current-year double count noted in chat (annuity PV includes the year's payment while
  balances are year-end). Separate follow-up.
- Electing out of the installment method, depreciation recapture, or §453A interest on large installment
  obligations.

**Anti-goals** (would be a failure even if it runs)

- A plan with the new fields blank changes any number. Blank must mean "no gain modeled", today's behaviour,
  so goldens and other plans do not move.
- Gain taxed twice (for example, also added to `note_int_yr` or the realized-gain ledger).
- The 2033 gain computed as a fixed dollar amount: it must follow the 2033 principal ($59,327.50).

## 3. What exists today (verified 2026-11-06)

- `src/parsing/note_receivable.py::parse_note_receivable` builds `c['note_items']`: `face_value`,
  `first_payment_year`, `last_payment_year`, `annual_principal`, `final_principal`, `interest_by_year`. Interest
  is read only for `range(plan_start, plan_start + 8)` (line 70).
- `src/projection_stages/deterministic_engine.py:942-955` sums `note_princ_yr` and `note_int_yr` per year and
  reduces each note's balance. Principal is never taxed. Interest is taxed as ordinary investment income
  (`note_int_yr` feeds NII, state investment income, ACA, AGI).
- Net worth adds `note_bal` (remaining principal), `portfolio_growth_and_net_worth.py:187`.
- New-note rows come from `strategy_asset_service.add_note_receivable_payload` (line 1053): `name`,
  `face_value`, `first_payment`, `last_payment`, `annual_principal_base_period`, `final_principal_2033`. No
  interest rows are seeded. The UI is `frontend/js/dashboard_decomp_assets_other.js::renderNoteReceivableTable`,
  which renders every row of the note's subsection with `fieldHtml`, plus the interest matrix.
- Note Receivable rows have no entries in `reference_src/schema.csv` / `field_tiers.csv`.
- **Prior art on this branch** (commit 7343e0d0, `src/projection_stages/other_asset_sale_tax.py`): Other Asset
  sales split gain into `ltcg_gain` (added to `home_sale_ltcg_gain`, so the investment-tax cascade taxes it as
  LTCG with NIIT/state/AGI/IRMAA/SS) and `ordinary_gain` (taxed by `stacked_gain_tax` as a fixed amount on top of
  ordinary taxable income, re-taxed after Priority 4b at the converged taxable income). Row fields, the
  cash-flow breakdown `tax.other_asset_sale` line and two tax-sheet columns follow from it.

## 4. Design

### 4.1 Inputs (per note)

Four new rows in each `Note N` subsection, all `USD`, all optional:

| Label | UI text | Help |
|---|---|---|
| `st_proceeds` | Short-term proceeds per payment (8949 Part I) | From one year's Form 8949, Part I, column (d) for this note. |
| `st_basis` | Short-term basis per payment (8949 Part I) | Part I, column (e). |
| `lt_proceeds` | Long-term proceeds per payment (8949 Part II) | Part II, column (d). |
| `lt_basis` | Long-term basis per payment (8949 Part II) | Part II, column (e). |

`add_note_receivable_payload` writes them as `$0` for new notes. Existing notes get them through the plan-data
backfill used for the Other Asset rows in commit 8b2ad975 (`BackfillEntry.from_plan`), blank / `$0`.

### 4.2 Ratios and yearly gain (parser + engine)

The parser adds to each note item:

```
total = st_proceeds + lt_proceeds
if total <= 0: no gain modeled (st_share = lt_share = 0)
st_share = st_proceeds / total             # 0.180 for RedMane
lt_share = lt_proceeds / total             # 0.820
st_gain_ratio = max(0, st_proceeds - st_basis) / st_proceeds   (0 if st_proceeds == 0)   # 1.000
lt_gain_ratio = max(0, lt_proceeds - lt_basis) / lt_proceeds   (0 if lt_proceeds == 0)   # 0.8457
```

Each year the note pays principal `P` (the same `_nprinc_yr` the engine already uses):

```
st_gain = P * st_share * st_gain_ratio      # 2026: 10,671.  2033: 10,679
lt_gain = P * lt_share * lt_gain_ratio      # 2026: 41,111.  2033: 41,143
```

The ratios do not depend on the year the 8949 came from: under the installment method the gross-profit ratio
is fixed for the life of the note.

### 4.3 Tax

- `lt_gain` is added to `home_sale_ltcg_gain` beside the Other Asset `ltcg_gain`, so it rides the same LTCG
  line (rates, NIIT, state, AGI, IRMAA MAGI, SS provisional income).
- `st_gain` is taxed like the Other Asset `ordinary_gain`: a fixed stacked amount via
  `other_asset_sale_tax.stacked_gain_tax` (federal ordinary, state, NIIT), added to `total_tax`, IRMAA MAGI and
  reported AGI, and re-taxed after Priority 4b at the converged taxable income. When both an Other Asset sale
  and a note gain occur in one year, the stacked amounts must be taxed in one call (ordinary gains summed) so
  neither is taxed as if the other were absent.
- New row fields: `note_gain_st`, `note_gain_lt`, `note_gain_stacked_tax`.
- Cash-flow breakdown: `tax.note_installment_gain` = `note_gain_stacked_tax`, taken out of `tax.other` as the
  Other Asset line is.
- Projection tax sheet (`sheets_projection_tax.build_sheet7`): when any row has a note gain, two columns: "Note
  Installment Gain (ST + LT)" and "Note Short-Term Gain Tax". Long-term tax stays inside Total Tax via the LTCG
  line, as for Other Assets.

### 4.4 Interest years

`parse_note_receivable` reads every row present in `"{sub} Interest"` whose label is a year, instead of
`range(plan_start, plan_start + 8)`. `note_interest` (the aggregate) sums over the union of those years. The
interest matrix in the UI already renders whatever rows exist.

### 4.5 Settled after the builder check (designer's calls, for the user to check)

- **ACA MAGI.** Both gains count toward ACA subsidy MAGI, since that MAGI is AGI-based and taxes must be right.
  If the Other Asset paths (`home_sale_ltcg_gain`, the stacked ordinary path) do not already reach the ACA
  MAGI used in `spending_and_rmd.py` (~line 579), the note gains are added there explicitly. Matthew is 64 in
  2026, so 2026 is the year this can matter.
- **Interest years outside the plan.** Interest rows for years before `plan_start` are ignored; years after it
  are read through the note's last payment year. Consumers of `note_interest` are grepped during the build and
  any 8-year assumption removed.
- **Verification data.** A new test fixture carries the RedMane figures (section 1) and pins 2026 gains of
  10,671 ST / 41,111 LT and 2033 gains of 10,679 ST / 41,143 LT.
- **The user's live plan** (user's decision, 2026-11-06): the build enters the 2025 Form 8949 figures into the
  RedMane note (`Note 1`) of the active plan through the store layer: `st_proceeds` $10,671, `st_basis` $0,
  `lt_proceeds` $48,611, `lt_basis` $7,500. The demo and frozen sample plans are not touched.

## 5. Left to the builder

- Whether the note gains are merged into an `OtherAssetSaleGains` value or carried as a sibling, provided the
  stacked tax is computed once per year over the summed ordinary gains (4.3).
- How the stacked tax is split between the Other Asset and note row fields when both occur (pro rata by gain is
  fine).
- Field order in the note's UI: the four rows after `final_principal_2033`.
- Whether to seed interest rows for new notes. Not required.

## 6. Data to check with the CPA (not code)

The interest schedule runs at about 7.7% of the outstanding balance for 2027–2031, then about 3.75% for 2032
and 2033. Worth confirming. `total_cash_flow` ($613,395) is display-only and does not match the schedule's
total ($635,913).

## 7. Implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Tax each year's Note Receivable installment gain (short-term at ordinary rates, long-term at LTCG
rates) from four 8949 inputs per note, and enter the RedMane figures into the live plan.

**Architecture:** A small fields module owns the four plan rows (add payload + backfill, as
`src/other_asset_tax.py` does). The parser turns them into per-note ratios. A pure projection-stage function
gives each year's gain from that year's principal; the engine feeds the long-term part into the existing LTCG
line and the short-term part into the Other Asset stacked-ordinary path, so one stacked tax is computed per year.

**Tech stack:** Python 3, pytest, the plan store (`src/stores/plan_store.py`), vanilla JS UI (no UI code change
expected: note rows render generically).

**Spec:** sections 1–5 above.

### Global constraints

- Blank or `$0` inputs change no number anywhere (anti-goal). Goldens must not move.
- Gain uses the year's actual principal (`_nprinc_yr`), so 2033 follows $59,327.50.
- Test files: `tests/test_<scope>_<type>.py`, no tracking ids. Regexes as raw strings. Edit/Write tools, not
  scripts, for source edits.
- New files under `src/` → `python tools/generate_system_diagram.py` and commit the diagram in the same commit.
- Run `python tools/fast_gates.py` before any push. pytest always `-v -rfE` into a scratchpad log.
- Never print or store full account numbers.

### Review focus

1. **A year with both an Other Asset sale and a note gain:** one stacked tax over the summed ordinary gains;
   `other_asset_sale_*` fields hold only the asset's share, `note_gain_*` only the note's. (Task 2 test.)
2. **Only one 8949 part filled** (e.g. all long-term, `st_proceeds` 0): no divide-by-zero, ST gain 0. (Task 1.)
3. **Basis above proceeds** in a part: that part's gain is 0, not negative. (Task 1.)
4. **Note paid off or principal 0 in a year:** no gain, no tax that year. (Task 2.)
5. **Interest rows before plan start or after year 8:** pre-plan years ignored, later years read. (Task 1.)

---

### Task 1: Note gain fields, backfill and parser

**Files:**
- Create: `src/note_installment_tax.py`
- Modify: `src/server_services/strategy_asset_service.py:1053-1066` (add payload), `src/server/app_core.py:674`
  (backfill list), `src/parsing/note_receivable.py`
- Test: `tests/test_note_installment_fields_unit.py`

**Interfaces — produces:**
- `note_installment_tax.FIELDS = ("st_proceeds", "st_basis", "lt_proceeds", "lt_basis")`
- `note_installment_tax.added_field_rows(subsection: str) -> list[list[str]]` — four
  `["Note Receivable", sub, label, "$0", "USD", help]` rows, help text from section 4.1.
- `note_installment_tax.backfill_rows(store) -> list[list[str]]` — the rows for every `Note N` subsection.
- `note_installment_tax.gain_ratios(st_proceeds, st_basis, lt_proceeds, lt_basis) -> tuple[float, float]` —
  `(st_gain_per_principal, lt_gain_per_principal)`, i.e. `st_share * st_gain_ratio` and `lt_share * lt_gain_ratio`
  from section 4.2.
- Each `c['note_items'][i]` gains `st_gain_per_principal` and `lt_gain_per_principal` (floats, 0.0 when blank).
- `interest_by_year` holds every year row from `plan_start` on (no 8-year cap); `note_interest` sums the union.

- [ ] **Step 1: Write failing tests**

```python
def test_redmane_ratios():
    st, lt = nit.gain_ratios(10_671, 0, 48_611, 7_500)
    assert st * 59_281.62 == pytest.approx(10_671, abs=1)
    assert lt * 59_281.62 == pytest.approx(41_111, abs=1)
    assert st * 59_327.50 == pytest.approx(10_679, abs=1)
    assert lt * 59_327.50 == pytest.approx(41_143, abs=1)

def test_blank_and_one_sided_and_loss():
    assert nit.gain_ratios(0, 0, 0, 0) == (0.0, 0.0)
    assert nit.gain_ratios(0, 0, 50_000, 10_000) == (0.0, pytest.approx(0.8))
    assert nit.gain_ratios(10_000, 12_000, 0, 0) == (0.0, 0.0)

def test_parser_reads_fields_and_all_interest_years():
    # sectioned data with Note 1 fields + "Note 1 Interest" rows for plan_start-1 .. plan_start+9
    out = parse_note_receivable(data, 2026)
    item = out["note_items"][0]
    assert item["st_gain_per_principal"] == pytest.approx(10_671 / 59_282, rel=1e-3)
    assert 2025 not in item["interest_by_year"] and 2035 in item["interest_by_year"]

def test_add_payload_and_backfill_write_four_rows():
    # add_note_receivable_payload writes the four labels; backfill_rows on a store with Note 1 and Note 2
    # returns 8 rows
```

- [ ] **Step 2:** `pytest tests/test_note_installment_fields_unit.py -v -rfE > <scratchpad>/pytest_t1.txt 2>&1`
  → FAIL (module missing).
- [ ] **Step 3:** Implement the module, call `added_field_rows` from the add payload, add
  `_BF.BackfillEntry(note_installment_tax.backfill_rows, from_plan=True)` after the Other Asset entry, and read
  the fields + all interest year labels in the parser. Grep `note_interest` consumers
  (`data_io.py:1054`, `planning_engines.py:1148`) and confirm none assumes 8 years.
- [ ] **Step 4:** Re-run → PASS. Also run `pytest tests -k "note or backfill or strategy_asset" -v -rfE` into a log.
- [ ] **Step 5:** Regenerate the diagram, commit: "Note Receivable: 8949 gain inputs per note".

### Task 2: Engine gain tax, ACA MAGI and reports

**Files:**
- Create: `src/projection_stages/note_installment_gain.py`
- Modify: `src/projection_stages/deterministic_engine.py` (~942-955 per-year note loop; ~1298-1332 Other Asset
  gain block; ~1586-1606 re-tax and reported AGI), `src/projection_stages/other_asset_sale_tax.py`,
  `src/projection_stages/roth_conversion_and_agi_tax.py:627` (ACA MAGI), `src/projection_stages/cashflow_breakdown.py`,
  `src/reporting/sheets_projection_tax.py`
- Test: `tests/test_note_installment_gain_tax_unit.py` (engine runs via `tests.synthetic_plans`, as
  `tests/test_other_asset_sale_tax_unit.py::_run` does)

**Interfaces:**
- Consumes: Task 1's `st_gain_per_principal`, `lt_gain_per_principal` on each note item.
- Produces: `note_installment_gain.year_gains(principal_by_note: list[tuple[dict, float]]) -> NoteGains` where
  `NoteGains(st: float, lt: float)`; row fields `note_gain_st`, `note_gain_lt`, `note_gain_stacked_tax`;
  `cashflow_breakdown['tax']['note_installment_gain']`; tax-sheet columns "Note Installment Gain (ST + LT)",
  "Note Short-Term Gain Tax".

- [ ] **Step 1: Write failing tests**

```python
def test_year_gains_sums_notes():                      # pure
def test_engine_taxes_note_gain(runs):                 # RedMane-like note on baseline_balanced_couple
    row = taxed[2027]
    assert row["note_gain_st"] == pytest.approx(10_671, abs=1)
    assert row["note_gain_lt"] == pytest.approx(41_111, abs=1)
    extra = row["total_tax"] - untaxed[2027]["total_tax"]
    assert 0.10 * 10_671 + 0.15 * 41_111 - 1 <= extra <= (0.37+0.038+0.0495) * 10_671 + (0.20+0.038+0.0495) * 41_111 + 1
    assert row["agi"] >= untaxed[2027]["agi"] + 51_782 - 1
    assert row["cashflow_breakdown"]["tax"]["note_installment_gain"] == pytest.approx(row["note_gain_stacked_tax"])
    assert sum(row["cashflow_breakdown"]["tax"].values()) == pytest.approx(row["total_tax"], abs=0.01)
def test_final_year_uses_final_principal(runs):        # 2033: 10,679 / 41,143
def test_no_gain_after_payoff_and_blank_inputs_change_nothing(runs):
def test_same_year_asset_sale_and_note_gain_split(runs):
    # other_asset_sale_ordinary_gain excludes the note; note_gain_st excludes the asset;
    # stacked tax total == one stacked_gain_tax call on the summed ordinary gain
def test_note_gain_in_aca_magi(runs):
    # the row's ACA MAGI (grep the key set near roth_conversion_and_agi_tax.py:627) rises by st + lt
```

- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** In the per-year note loop, collect `(item, _nprinc_yr)` and call `year_gains`. Add `lt` to
  `home_sale_ltcg_gain` next to `_oa_gains.ltcg_gain`. Make the stacked path run when either the asset sale or
  the note has an ordinary gain (today it is gated on `_oa_gains.items`), on the summed ordinary gain, and split
  the result pro rata into `other_asset_sale_stacked_tax` and `note_gain_stacked_tax`. Add both gains to ACA MAGI
  if the test shows they are missing. Cash-flow line and tax-sheet columns mirror the Other Asset ones.
- [ ] **Step 4:** Re-run → PASS; then `pytest tests/test_other_asset_sale_tax_unit.py -v -rfE` (must still pass
  unchanged).
- [ ] **Step 5:** Diagram regen, commit: "Tax the installment gain on Note Receivable principal".

### Task 3: Gates, goldens and the fast suite

- [ ] `python tools/regen_golden_master.py measure` → expect zero delta (no fixture plan has the new fields).
- [ ] `pytest tests/test_phase_golden_equality_regression.py -v -rfE` into a log → PASS. Any delta is a bug
  (anti-goal), not something to record.
- [ ] `python tools/fast_gates.py` → PASS.
- [ ] `pytest -m "not slow" -v -rfE > <scratchpad>/pytest_fast.txt 2>&1` in the background → PASS.
- [ ] `npm test` → PASS (no frontend change expected; confirms nothing broke).

### Task 4: Enter the RedMane figures and confirm in the live plan

- [ ] Start the app once (or call the backfill directly) so Note 1 has the four rows; confirm with
  `peek_plan_data()['Note Receivable']['Note 1']`.
- [ ] Write the values through the store: `with edit_active_plan() as e: e.store.set_value("Note Receivable",
  "Note 1", "st_proceeds", "$10,671")`, likewise `st_basis` `$0`, `lt_proceeds` `$48,611`, `lt_basis` `$7,500`.
- [ ] Re-run the projection script (as `scratchpad/joint_pv.py` does) and print 2026–2033 `note_gain_st`,
  `note_gain_lt`, `note_gain_stacked_tax` and the change in `total_tax`. Expect 10,671 / 41,111 in 2026 and
  10,679 / 41,143 in 2033.
- [ ] Open the Other Assets & Debts page in the browser pane and screenshot the note with its four fields.

### Usage estimates

Check `/usage` after each task against these. They are relative, not token counts.

| Task | Model / effort | Usage vs a 5-hour Pro session | What drives context |
|---|---|---|---|
| 1 Fields + parser | Sonnet / medium | Light | Small files; `strategy_asset_service.py` and `app_core.py` by grep and offset only. |
| 2 Engine tax | Opus / high | **Moderate–heavy** | `deterministic_engine.py` is large: read only the three cited regions. Synthetic engine runs in tests take time. |
| 3 Gates + suite | Sonnet / low | Moderate | Fast suite and golden test run time; read logs with `tail`, not whole. |
| 4 Live data | Sonnet / low | Light | One store edit, one projection run, one screenshot. |

**Flagged as expensive:**

- **Task 2's stacked-tax refactor.** It touches the Other Asset path just shipped; keep the change to the gate and
  the split, and let `test_other_asset_sale_tax_unit.py` prove nothing else moved. Do not read
  `deterministic_engine.py` linearly.
- **Golden drift loops.** Expect zero drift. If `measure` shows any, stop and find why; never regen.
- **The fast suite.** Run once per task at most, in the background, into a log.

**Parallelism:** none worth it. Task 2 needs Task 1's parser fields; Tasks 3 and 4 need Task 2.
