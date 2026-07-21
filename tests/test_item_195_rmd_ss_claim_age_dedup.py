"""Wave 3.5b item 195 (system review Addendum A): delete the redundant
household-level "RMD Start Age" / "SS Claim Age" echo, keep the per-member
fields as the sole authoritative, reachable, settable copies.

Field-authority analysis done before this change (per the review's own §10.1
revision, which blocked 195 until this was named explicitly):
  - Authoritative: per-member `member_1_rmd_start_age`/`member_2_rmd_start_age`
    (Model Constants/Retirement) and `Social Security/Member 1|2/claim_age`.
    Both are reachable on real guided steps (economic_tax_assumptions and
    income_retirement respectively), both round-trip to the same schema key
    as before this change.
  - Redundant echo (removed): `Model Constants/Retirement/ss_claim_age` and
    `rmd_start_age` — a household-wide value that only ever functioned as a
    fallback default when a per-member field was blank, and whose own value
    never differed from what the fallback already computed (statutory RMD
    age from date of birth; 70 for SS claim age).
"""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _schema_keys() -> set:
    text = (ROOT / "reference_data" / "schema.csv").read_text(encoding="utf-8")
    keys = set()
    for line in text.splitlines()[1:]:
        parts = line.split(",")
        if len(parts) < 3:
            continue
        keys.add((parts[0].strip(), parts[1].strip(), parts[2].strip()))
    return keys


class Item195RmdSsClaimAgeDedupTests(unittest.TestCase):
    def test_household_generic_fields_are_gone_from_schema(self):
        keys = _schema_keys()
        self.assertNotIn(("Model Constants", "Retirement", "ss_claim_age"), keys)
        self.assertNotIn(("Model Constants", "Retirement", "rmd_start_age"), keys)

    def test_household_generic_fields_are_gone_from_live_and_frozen_csv(self):
        for rel in ("input/client_policy.csv", "tests/fixtures/sample_plan_frozen/client_policy.csv"):
            text = (ROOT / rel).read_text(encoding="utf-8")
            self.assertNotIn("Model Constants,Retirement,ss_claim_age,", text, rel)
            self.assertNotIn("Model Constants,Retirement,rmd_start_age,", text, rel)

    def test_per_member_fields_remain_authoritative_and_schema_current(self):
        keys = _schema_keys()
        # Authoritative, reachable, settable per-member fields — current label
        # names (member_1_/member_2_, "Member 1"/"Member 2"), not the retired
        # husband_/wife_ / "Husband"/"Wife" naming plan_data_migration.py
        # already migrates away from at rest.
        self.assertIn(("Model Constants", "Retirement", "member_1_rmd_start_age"), keys)
        self.assertIn(("Model Constants", "Retirement", "member_2_rmd_start_age"), keys)
        self.assertIn(("Social Security", "Member 1", "claim_age"), keys)
        self.assertIn(("Social Security", "Member 2", "claim_age"), keys)
        # The stale husband_/wife_ naming schema.csv previously carried for
        # these same fields (matching nothing in any live CSV) is gone too.
        self.assertNotIn(("Model Constants", "Retirement", "husband_rmd_start_age"), keys)
        self.assertNotIn(("Model Constants", "Retirement", "wife_rmd_start_age"), keys)
        self.assertNotIn(("Social Security", "Husband", "claim_age"), keys)
        self.assertNotIn(("Social Security", "Wife", "claim_age"), keys)

    def test_per_member_rmd_and_claim_age_are_reachable_on_guided_steps(self):
        js = (ROOT / "frontend" / "js" / "dashboard.js").read_text(encoding="utf-8")
        # economic_tax_assumptions claims every Model Constants/Retirement row
        # except spending_freeze_year — member_1_/2_rmd_start_age land there.
        idx = js.index('case "economic_tax_assumptions":')
        block = js[idx: idx + 500]
        self.assertIn('"retirement", "capital_gains"', block)
        # income_retirement claims the whole Social Security section, where
        # per-member claim_age lives, via a dedicated compact table.
        self.assertIn('case "income_retirement":', js)
        self.assertIn('sec === "Social Security"', js)
        self.assertIn("function ssPersonRows(person)", js)
        self.assertIn('"claim_age"', js)

    def test_engine_derives_rmd_start_age_purely_from_statutory_default(self):
        from src.data_io import load_csv, parse_client
        c = parse_client(load_csv(ROOT / "input" / "client_data.csv"), "")
        from src.core import statutory_rmd_start_age
        self.assertEqual(c["rmd_start_age"], statutory_rmd_start_age(c["h_dob_yr"]))
        self.assertEqual(c["ss_claim_age"], 70)
        # Per-member overrides are unaffected — the live plan's claim_age=69
        # override for both members still round-trips exactly as before.
        self.assertEqual(c["h_ss_claim_age"], 69)
        self.assertEqual(c["w_ss_claim_age"], 69)


if __name__ == "__main__":
    unittest.main()
