Status: draft

# Illinois estate tax method (W4-01 / FIN-004) - design, blocked on attorney sign-off

**Not implemented.** The method below is the review's understanding only (confidence low,
`requires_external_domain_verification`). An estate attorney or the Illinois Attorney General's
estate tax calculator must confirm it before any engine change. Until then
`src/core.py` `illinois_estate_tax` and `state_death_tax_credit` stay as they are.

## Current behaviour

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

## Calculator-matched test points

Run the Illinois AG calculator (or have counsel run it) at these taxable estates and record the
result next to each before implementing. The expected values are deliberately blank: they must
come from the calculator, not from this note.

| Taxable estate | Calculator result | Engine today | Review expectation |
|---|---|---|---|
| $4,050,000 | _pending_ | _measure_ | phase-in region, a few thousand dollars |
| $4,500,000 | _pending_ | _measure_ | phase-in region |
| $5,000,000 | _pending_ | _measure_ | near the table / limit crossover |
| $10,000,000 | _pending_ | _measure_ | table binds; differs from today by the $60k adjustment |

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
