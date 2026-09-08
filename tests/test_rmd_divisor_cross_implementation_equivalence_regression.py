"""Do core.rmd_divisor, planning_engines.rmd_divisor, and tax_kernel.rmd_divisor agree?

System review 2026-09-07, finding N5 / Wave 5 item W5-2.

**History.** `src.core.rmd_divisor` and `src.planning_engines.rmd_divisor`
were independently implemented copies of the same statutory Uniform
Lifetime / IRS Table II lookup. This test proved they genuinely disagreed
for a **fractional age** (e.g. an age computed as a fraction of a year from
a birth month, rather than a whole number): `core.rmd_divisor` indexed
`RMD_DIVISORS` with the raw, un-truncated age -- a miss for any non-integer
key -- and fell through to the post-table conservative extrapolation
formula using that same fractional age uncorrected, which for an age
comfortably inside the table's real [72, 115] range produces a wildly wrong
divisor (see `test_fractional_age_previously_diverged_now_agrees` below).
`planning_engines.rmd_divisor` truncated to `int` first and was correct.

**Fix (Wave 5 item W5-2).** `src/tax_kernel.py` is now the single canonical
implementation (`tax_kernel.rmd_divisor`); both `core.rmd_divisor` and
`planning_engines.rmd_divisor` are now thin delegating call sites, so they
are expected to agree exactly. This file is kept as the regression guard
against the fix regressing.
"""
from __future__ import annotations

import itertools
import unittest

from src.core import rmd_divisor as core_rmd_divisor
from src.planning_engines import rmd_divisor as pe_rmd_divisor
from src.tax_kernel import rmd_divisor as tk_rmd_divisor

AGES = [0, 40, 71, 72, 73, 80, 90, 100, 114, 115, 116, 120, 130]
SPOUSE_AGES = [None, 20, 55, 60, 65, 70, 80]
SOLE_BENEFICIARY_FLAGS = [False, True]


class RmdDivisorCrossImplementationEquivalenceTests(unittest.TestCase):
    def test_all_three_implementations_agree_across_the_grid(self):
        mismatches = []
        for age, spouse_age, sole in itertools.product(AGES, SPOUSE_AGES, SOLE_BENEFICIARY_FLAGS):
            core_val = core_rmd_divisor(age, spouse_age=spouse_age, sole_beneficiary_spouse=sole)
            pe_val = pe_rmd_divisor(age, spouse_age=spouse_age, sole_beneficiary_spouse=sole)
            tk_val = tk_rmd_divisor(age, spouse_age=spouse_age, sole_beneficiary_spouse=sole)
            if not (core_val == pe_val == tk_val):
                mismatches.append((age, spouse_age, sole, core_val, pe_val, tk_val))
        self.assertEqual(
            mismatches, [],
            f"rmd_divisor implementations disagree at {len(mismatches)} grid point(s): {mismatches[:5]}",
        )

    def test_fractional_age_previously_diverged_now_agrees(self):
        # Age 80.5's real table entry is age 80's divisor. core.rmd_divisor
        # used to miss this table lookup for a fractional key and fall
        # through to the >115 extrapolation formula, producing a divisor
        # far from age 80's real value. All three must now agree and match
        # the plain int(80) lookup.
        expected = core_rmd_divisor(80)
        for fn in (core_rmd_divisor, pe_rmd_divisor, tk_rmd_divisor):
            with self.subTest(fn=fn.__module__ + "." + fn.__qualname__):
                self.assertEqual(fn(80.5), expected)
                self.assertGreater(expected, 10.0)  # sanity: age-80 divisor is nowhere near the >115 tail

    def test_joint_life_relief_path_agrees(self):
        # 25-year gap, sole beneficiary spouse -> Joint Life table applies
        # for all three implementations identically.
        for fn in (core_rmd_divisor, pe_rmd_divisor, tk_rmd_divisor):
            with self.subTest(fn=fn.__module__ + "." + fn.__qualname__):
                val = fn(80, spouse_age=55, sole_beneficiary_spouse=True)
                uniform = fn(80, spouse_age=55, sole_beneficiary_spouse=False)
                self.assertGreater(val, uniform)  # Joint Life relief always widens the divisor here

    def test_pe_table_override_still_works(self):
        # planning_engines.rmd_divisor's `table` override parameter (used by
        # build_workbook) must survive the consolidation.
        override = {80: 999.0}
        self.assertEqual(pe_rmd_divisor(80, table=override), 999.0)
        self.assertEqual(tk_rmd_divisor(80, table=override), 999.0)


if __name__ == "__main__":
    unittest.main()
