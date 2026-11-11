Status: implemented in commit 74b531e8 on claude/w4-01-illinois-estate-7b5d8d (not yet merged; method confirmed by estate attorney, tests hand-derived rather than AG-calculator matched)

# Illinois estate tax method (W4-01 / FIN-004) - design, attorney signed off, implemented

**Implemented (W4-01).** The estate attorney signed off on the method as written. The 2001(c) schedule
(`FEDERAL_ESTATE_RATE_SCHEDULE`) sits in `src/core.py` beside the 2011(b) and New York tables, which are
inline there too; it is permanent statute, not a dated reference row. Limitation notice N9 was removed.

## Behaviour before W4-01

`illinois_estate_tax(gross, exemption=4M)` returns 0 at or below $4M. Above it, it iterates
`T = state_death_tax_credit(gross - T)`: the old IRC 2011(b) credit table applied to the whole
estate, with no $60,000 adjustment and no cap at the federal tax. Callers:
`after_tax.estimate_terminal_estate_tax` and `engine_sections/roth_conversion._estate_tax_for_row`.
At a $4.1M taxable estate it converges to about $269k; the review expects about $40k.

## Proposed method (to be confirmed)

1. Adjusted taxable estate `ATE = taxable_estate - 60,000`.
2. Table credit `C(ATE)` from the 2011(b) schedule.
3. Federal-limit `F = tentative federal estate tax` on the estate using a $4,000,000 exclusion,
   with the IRC 2001(c) rate schedule (top 40% above $1M taxable amount, so 40% of the excess
   above $4M plus the 2001(c) tax on the first $4M is fully sheltered by the credit).
4. `IL tax = min(C(ATE), F)`.
5. The Illinois tax is itself deductible in computing the taxable estate (interrelated
   deduction), so solve `T = min(C(ATE(gross - T)), F(gross - T))` by fixed-point iteration
   as today.

Expected shape: a steep phase-in above $4M (about 40 cents per dollar before the interrelated
deduction), then the table binding above roughly $5M, where the only correction versus today is
the $60k adjustment (about $6.7k-$9.6k).

## Test points (hand-derived, NOT calculator-matched)

The estate attorney signed off on the method as written. No Illinois AG calculator output was
available, so the values pinned in `tests/test_illinois_estate_tax_unit.py` are closed-form solutions
of the method's interrelated equation. Replace them with calculator figures if counsel supplies them.
"Engine before" is the pre-W4-01 `illinois_estate_tax`.

| Taxable estate | Pinned value (hand-derived) | Engine before | Binding limit |
|---|---|---|---|
| $4,050,000 | $14,285.71 | $264,348 | federal limit: 0.4/1.4 x excess over $4M |
| $4,500,000 | $142,857.14 | $307,842 | federal limit |
| $5,000,000 | $285,714.29 | $358,202 | federal limit (table would give about $359k) |
| $10,000,000 | $926,923.08 | $934,653 | 2011(b) table on estate less $60k |

Note: the review's "about $40k at $4.1M" is the 40-cents-per-dollar figure before the interrelated
deduction; with the Illinois tax deducted the figure is $28,571.

## Implementation steps once confirmed

- Add `federal_tentative_tax(taxable, exclusion)` with the 2001(c) schedule next to the other
  estate helpers in `src/core.py`; keep the schedule in the reference-data store, not inline.
- Rewrite `illinois_estate_tax` per the method; keep the signature.
- Add a unit test with the four points above and a monotonic and continuity test (no cliff).
- Run `python tools/regen_golden_master.py measure`, hand-verify one delta, and only then
  re-pin with a recorded reason. Run `tests/test_phase_golden_equality_regression.py` locally.
- Update the Illinois text in the help registry that calls the behaviour a cliff.

## Exit

Attorney sign-off recorded here; tests match the calculator.
