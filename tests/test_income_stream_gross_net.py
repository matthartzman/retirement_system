"""Gross vs net income streams (FUNCTIONAL_SPEC §6).

initial_guaranteed_income_payment is the gross monthly payment the engine taxes;
net_monthly_payment is an optional reference-only deposit after withholding.
"""
import copy
import tempfile
import unittest
from pathlib import Path


def _backfilled_demo(tmp):
    from src import plan_data_backfill
    from src.server.app_core import PLAN_DATA_BACKFILL_ENTRIES
    from tests.plan_fixture import make_plan

    ws = make_plan(Path(tmp), "demo")
    store = ws.store()
    with store, store.transaction():
        for r in store.all_rows():
            if r["section"] == "Income Streams" and r["label"] == "net_monthly_payment":
                store.delete_row(r["row_id"])
        before = store.sectioned_data()
        plan_data_backfill.apply_backfill(store, PLAN_DATA_BACKFILL_ENTRIES, ws.input_dir)
        after = store.sectioned_data()
        pension_labels = [r["label"] for r in store.rows("Income Streams") if r["subsection"] == "Member 2 Pension"]
    return before, after, pension_labels


class NetMonthlyPaymentBackfillTests(unittest.TestCase):
    def test_every_stream_gets_a_blank_net_row(self):
        from src.server.app_core import INCOME_STREAM_GROSS_NET_SUBSECTIONS

        with tempfile.TemporaryDirectory() as tmp:
            before, after, _ = _backfilled_demo(tmp)
        self.assertNotIn("net_monthly_payment", before["Income Streams"]["Member 2 Pension"])
        for sub in INCOME_STREAM_GROSS_NET_SUBSECTIONS:
            self.assertEqual(after["Income Streams"][sub]["net_monthly_payment"], "", sub)

    def test_net_row_sits_right_after_the_gross_payment(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, labels = _backfilled_demo(tmp)
        i = labels.index("initial_guaranteed_income_payment")
        self.assertEqual(labels[i + 1], "net_monthly_payment")

    def test_backfill_changes_no_projection_input(self):
        from src.data_io import parse_client

        with tempfile.TemporaryDirectory() as tmp:
            before, after, _ = _backfilled_demo(tmp)
        c_before, c_after = parse_client(before, ""), parse_client(after, "")
        for k in ("wife_pension", "wife_single", "wife_joint", "h_single", "h_joint"):
            self.assertEqual(c_before[k]["init_pmt"], c_after[k]["init_pmt"])
            self.assertEqual(c_after[k]["monthly_withholding"], 0.0)


class GrossNetParseTests(unittest.TestCase):
    def _pension(self, gross, net):
        from src.data_io import parse_client

        with tempfile.TemporaryDirectory() as tmp:
            _, data, _ = _backfilled_demo(tmp)
        data = copy.deepcopy(data)
        data["Income Streams"]["Member 2 Pension"]["initial_guaranteed_income_payment"] = gross
        data["Income Streams"]["Member 2 Pension"]["net_monthly_payment"] = net
        return parse_client(data, "")["wife_pension"]

    def test_withholding_is_gross_minus_net(self):
        p = self._pension("$397.73", "$282.58")
        self.assertAlmostEqual(p["init_pmt"], 397.73)
        self.assertAlmostEqual(p["net_monthly_payment"], 282.58)
        self.assertAlmostEqual(p["monthly_withholding"], 115.15)

    def test_blank_net_means_no_withholding(self):
        p = self._pension("$397.73", "")
        self.assertAlmostEqual(p["net_monthly_payment"], 397.73)
        self.assertEqual(p["monthly_withholding"], 0.0)


if __name__ == "__main__":
    unittest.main()
