# HSA Expense Bank: Accumulation, and the Deduction Double-Dip — Spec

Next increment after PR #67 (HSA schedule search wired into builds).
**Spec/research only — no code in this document.**

The prior spec
(`2026-08-26-hsa-schedule-search-contingent-liability-spec.md`) named
"model per-year qualified-expense capacity" as Option B, the real successor
increment. **Researching it found that framing wrong**, and found a
different, more serious issue underneath. Both are recorded here.

## Correction: a cumulative bank is the CORRECT model, not a gap

The prior spec treated `hsa_expense_bank` being "a single lifetime scalar"
rather than a per-year figure as the defect. That is backwards.

Under the actual tax treatment, a qualified medical expense incurred at any
time after the HSA was established — and not previously reimbursed or
deducted — can justify a tax-free withdrawal at **any later date**. There is
no deadline. That is the basis of the well-known "shoebox" strategy: pay
medical costs out of pocket, keep the receipts, let the HSA compound, and
reimburse yourself years later.

So the constraint genuinely is **cumulative, not per-year**, and
`hsa_available_to_draw`'s existing shape is right. A per-year cap would
model the *wrong* rule — it would forbid the legitimate strategy the account
is most valuable for. The schema description agrees: *"Cumulative
substantiated unreimbursed qualified medical expenses available to justify
tax-free withdrawals."*

Option B as previously written should not be built.

> Tax-rule caveat: the specifics above (no reimbursement deadline;
> post-establishment expenses only; no double benefit) are the basis for
> this whole spec and should be confirmed against current guidance by the
> planner before implementation, not taken from this document. The
> *engine-behavior* findings below are verified directly against the code
> and stand independently.

## What is actually wrong

### Gap 1: the bank never accumulates from the plan's own medical spending

`c['hsa_expense_bank']` is parsed once from a single user-entered figure
(`data_io.py:2309-2310`) and never changes:

```python
_bank = _v(data, 'HSA Policy', 'Withdrawals', 'hsa_expense_bank', '')
c['hsa_expense_bank'] = None if (... blank ...) else _n(_bank, 0.0)
```

Blank — the schema default, and what the frozen fixture leaves it at —
means **unlimited**. Meanwhile the projection computes exactly the figure
that should feed this bank, every year, for tax purposes
(`deterministic_engine.py:1876`):

```python
medical_expense_yr = wellness_premium_yr + wellness_detail_budget_yr + wellness_shock_yr + ltc_prem_yr
```

and then discards it as far as the HSA is concerned. A household's *future*
projected medical spending — which is the bulk of the justification for
their HSA draws — contributes nothing to their modeled tax-free capacity.
The user is asked to type in a number representing historical receipts, and
that static number is the entire model.

### Gap 2 (the serious one): the same dollar can be deducted AND reimbursed

Verified by inspection: `medical_expense_yr` flows into the itemized medical
deduction above the 7.5%-of-AGI floor —

```python
medical_ded = max(0.0, medical_expense_yr - 0.075 * max(0.0, agi))
item_ded = salt + char + mort_interest_yr + medical_ded
```

— and **nothing anywhere reduces `medical_expense_yr` by HSA dollars
already reimbursed against it.** Confirmed: no reference to `hsa_wd` (or any
HSA draw) appears near the deduction computation.

Combined with Gap 1's unlimited default, the model therefore permits the
same medical dollar to deliver **two** benefits simultaneously: a tax-free
HSA withdrawal *and* a Schedule A deduction. Taking both for one expense is
not permitted, so this overstates the tax efficiency of every plan that
itemizes medical costs while drawing an HSA.

**PR #66 made this more reachable, not less.** That change
(`fund_contingent_liability_from_hsa`) routes `ltc_prem_yr +
wellness_shock_yr` to the HSA preferentially — and those are two of the four
components of `medical_expense_yr`. Before it, HSA dollars covered medical
costs only incidentally; now they cover exactly the dollars most likely to
clear the 7.5% floor and generate a deduction. The defect predates that PR,
but its frequency went up because of it. That is worth stating plainly
rather than discovering later.

**PR #67 compounds it further in `optimize` mode.** The newly-wired schedule
search maximizes `score_year`, whose displacement term prices the marginal
rate on the dollar the draw displaces. With the double benefit unpriced, the
search is optimizing against a model that overstates HSA value in exactly
the high-medical years it is drawn toward.

## Options

**Option A — Close the double-dip only** (recommended first). Reduce
`medical_expense_yr` by the HSA dollars reimbursed against it before
computing `medical_ded`. Self-contained, needs no new config, and fixes a
correctness defect rather than adding a feature. Sequencing note: the HSA
draw is decided in the withdrawal cascade, which runs *after* the deduction
is computed in the current row order — so this needs either a second pass
over the deduction or a reordering, and that ordering question is the main
implementation risk. **Will move golden-master pins** for any household with
both an HSA draw and medical costs above the floor — including, very
likely, the frozen fixture. That is a genuine engine correction and the pin
move is the correct outcome, regenerated via
`tools/regen_golden_master.py regen --reason <file>` per the runbook.

**Option B — Accumulate the bank from projected medical spending.** Seed the
bank from the user's entered figure (historical receipts) and grow it each
year by that year's qualified medical spend net of what the HSA already
reimbursed. Makes the bank a live constraint instead of an inert one, and is
the honest version of "model the capacity." Depends on Option A: without the
reimbursement tracking A introduces, there is no way to know what to net
out. Larger, and it changes behavior for every household that leaves the
field blank today (i.e. most), since "unlimited" becomes a real number.

**Option C — Per-year capacity.** The prior spec's Option B. **Do not
build** — models the wrong rule, per the correction above.

## Recommendation

**Option A first, on its own**, then re-evaluate B.

Rationale: A is a correctness fix with a bounded diff and a clear right
answer; B is a behavior change with a wide blast radius that is only
meaningful once A exists. Shipping them together would put a pin move that
is unambiguously a bug fix in the same commit as one that is a modeling
choice, and the changelog convention here is to keep an attributable pin
move traceable to a single cause.

Steps:

1. Establish where in the row's computation order the HSA draw becomes
   known relative to `medical_ded`, and decide between a second deduction
   pass and a reordering. This is the real design question and should be
   settled before code — the tax fixed-point in this engine already
   iterates, and adding a second interacting loop is where a subtle bug
   would live.
2. Net HSA-reimbursed dollars out of `medical_expense_yr` for deduction
   purposes only, leaving the cash-flow figure untouched (it is still a real
   cost, it is just not separately deductible).
3. Regenerate pins via the tool, with a changelog entry naming the double
   benefit as the cause.
4. Regression file `tests/test_hsa_medical_deduction_double_dip_regression.py`:
   (a) a household with an HSA draw covering medical costs gets a smaller
   `medical_expense_deduction` than one paying the same costs from taxable;
   (b) a household with no HSA draw is bit-identical to today; (c) HSA
   dollars beyond that year's qualified spend do not reduce the deduction
   below zero; (d) `total_spend`/cash flow is unchanged — this is a
   deduction correction, not a spending one.
5. Verify per the standing discipline, including an `-m slow` pass.

## Open questions

1. **Row ordering** (step 1) — genuinely open, and the main risk. Worth
   reading how the existing tax fixed-point settles before choosing.
2. **Does the deduction floor change the answer?** Only spending above
   7.5% of AGI is deductible, so netting HSA dollars out may move a
   household below the floor entirely, making the deduction vanish rather
   than shrink. That is correct behavior, but it makes the pin move larger
   than a naive reading suggests and is worth stating in the changelog.
3. **Should Option A be gated?** Everything shipped in this refactor so far
   has been either inert on the frozen fixture or gated. This one is
   neither: it is a straightforward correction with no "off" position that
   is defensible once known. Recommend shipping ungated, but flagging it
   for the planner review, since it makes every affected plan look
   *worse* — and a change in that direction deserves the same scrutiny the
   2026-08-18 entry gave a change that made plans look better.
