"""Transfer pairing (cash tracking Phase 3): exactly-one-candidate rule, reference id first, external withdrawals,
in-kind pairing, return of excess, journals."""
from __future__ import annotations

from src.cash_ledger import build_ledger
from src.cash_pairing import pair_transfers

A, B, C = "etrade:1111", "fidelity:2222", "vanguard:3333"


def _b(**kw):
    base = {"import_id": 1, "row_key": "x", "run_date": "2026-03-01", "kind": "other", "sweep": False, "action": "Transfer",
            "symbol": "", "description": "", "quantity": None, "amount": 0.0, "cash_balance": None}
    return {**base, **kw}


def _ledger(account, rows):
    rows = [{**r, "row_key": f"{account}-{i}"} for i, r in enumerate(rows)]
    return build_ledger(account, rows, [{"import_id": 1, "account": account, "date_from": "2026-01-01",
                                         "date_to": "2026-12-31", "status": "applied"}], [])


def _pair(**accounts):
    return pair_transfers({k.replace("_", ":"): _ledger(k.replace("_", ":"), v) for k, v in accounts.items()})


def test_one_outflow_and_one_inflow_within_three_days_pair_internal():
    out = _pair(etrade_1111=[_b(run_date="2026-03-01", amount=-1000.0, description="TRANSFER OUT")],
                fidelity_2222=[_b(run_date="2026-03-04", amount=1000.0, description="TRANSFER IN")])
    o, i = out[A][0], out[B][0]
    assert o["pair_status"] == i["pair_status"] == "internal"
    assert o["pair_id"] == i["pair_id"] and o["pair_id"]
    assert o["partner_account"] == B and i["partner_account"] == A
    assert o["account"] == A


def test_four_days_apart_does_not_pair():
    out = _pair(etrade_1111=[_b(run_date="2026-03-01", amount=-1000.0)],
                fidelity_2222=[_b(run_date="2026-03-05", amount=1000.0)])
    assert out[A][0]["pair_status"] == "external_withdrawal" and out[B][0]["pair_status"] == "unmatched"


def test_two_same_amount_candidates_stay_unmatched():
    out = _pair(etrade_1111=[_b(run_date="2026-03-01", amount=-1000.0)],
                fidelity_2222=[_b(run_date="2026-03-01", amount=1000.0)],
                vanguard_3333=[_b(run_date="2026-03-01", amount=1000.0)])
    assert out[A][0]["pair_status"] == "unmatched"
    assert out[B][0]["pair_status"] == "unmatched" and out[C][0]["pair_status"] == "unmatched"
    assert not any(r.get("pair_id") for rows in out.values() for r in rows)


def test_two_outflows_for_one_inflow_stay_unmatched():
    out = _pair(etrade_1111=[_b(run_date="2026-03-01", amount=-1000.0)],
                vanguard_3333=[_b(run_date="2026-03-02", amount=-1000.0)],
                fidelity_2222=[_b(run_date="2026-03-02", amount=1000.0)])
    assert out[B][0]["pair_status"] == "unmatched"
    assert out[A][0]["pair_status"] == "unmatched" and out[C][0]["pair_status"] == "unmatched"


def test_same_account_never_pairs_with_itself():
    out = _pair(etrade_1111=[_b(run_date="2026-03-01", amount=-1000.0), _b(run_date="2026-03-01", amount=1000.0)])
    assert [r["pair_status"] for r in out[A]] == ["external_withdrawal", "unmatched"]


def test_reference_id_pairs_first_even_when_amount_candidates_are_ambiguous():
    out = _pair(etrade_1111=[_b(run_date="2026-03-01", amount=-1000.0, description="TRANSFER TO XXXXX2222  REFID:555")],
                fidelity_2222=[_b(run_date="2026-03-01", amount=1000.0, description="OTHER"),
                               _b(run_date="2026-03-02", amount=1000.0, description="TRANSFER FROM XXXXX1111  REFID:555")])
    assert out[A][0]["partner_account"] == B and out[A][0]["pair_status"] == "internal"
    paired = [r for r in out[B] if r["pair_status"] == "internal"]
    assert len(paired) == 1 and paired[0]["ref_id"] == "555"
    assert [r["pair_status"] for r in out[B] if r["ref_id"] == ""] == ["unmatched"]


def test_reference_id_pairs_beyond_three_days():
    out = _pair(etrade_1111=[_b(run_date="2026-03-01", amount=-1000.0, description="X  REFID:9")],
                fidelity_2222=[_b(run_date="2026-03-20", amount=1000.0, description="Y  REFID:9")])
    assert out[A][0]["pair_status"] == out[B][0]["pair_status"] == "internal"


def test_different_reference_ids_do_not_pair_on_amount():
    out = _pair(etrade_1111=[_b(run_date="2026-03-01", amount=-1000.0, description="ACH WITHDRAWL  REFID:1;")],
                fidelity_2222=[_b(run_date="2026-03-01", amount=1000.0, description="ACH DEPOSIT  REFID:2;")])
    assert out[A][0]["pair_status"] == "external_withdrawal" and out[B][0]["pair_status"] == "unmatched"


def test_external_withdrawal_stands_alone_without_a_partner():
    out = _pair(vanguard_3333=[_b(run_date="2026-04-07", action="Withdrawal", description="Withdrawal via Electronic Bank", amount=-500.0)])
    r = out[C][0]
    assert r["class"] == "distribution" and r["pair_status"] == "external_withdrawal" and not r.get("pair_id")
    assert r["partner_account"] is None


def test_distribution_with_a_partner_in_another_plan_account_is_internal():
    out = _pair(fidelity_2222=[_b(run_date="2025-07-03", action="Distribution", description="DISTRIBUTION", amount=-2500.0)],
                etrade_1111=[_b(run_date="2025-07-03", action="Online Transfer", description="TRANSFER FROM XXXXX2222", amount=2500.0)])
    assert out[B][0]["pair_status"] == out[A][0]["pair_status"] == "internal"


def test_unmatched_inflow_and_unclassified_row_are_visible_never_guessed():
    out = _pair(etrade_1111=[_b(run_date="2026-03-01", amount=300.0, description="ACH DEPOSIT"),
                             _b(action="Mystery", description="???", amount=-70.0)])
    assert out[A][0]["pair_status"] == "unmatched"
    assert out[A][1]["pair_status"] == "unmatched" and out[A][1]["needs_review"] is True


def test_unclassified_rows_pair_by_sign_and_keep_the_review_flag():
    out = _pair(etrade_1111=[_b(action="Mystery", description="???", amount=-70.0)],
                fidelity_2222=[_b(action="Mystery", description="???", amount=70.0)])
    assert out[A][0]["pair_status"] == out[B][0]["pair_status"] == "internal"
    assert out[A][0]["needs_review"] and out[B][0]["needs_review"]


def test_in_kind_rows_pair_for_visibility_and_stay_zero_cash_uncounted():
    out = _pair(etrade_1111=[_b(run_date="2026-03-01", symbol="TOTL", quantity=-10.0, amount=None, description="TFR TO ACCT")],
                fidelity_2222=[_b(run_date="2026-03-02", symbol="TOTL", quantity=10.0, amount=None, description="TFR FROM ACCT")])
    for acct in (A, B):
        r = out[acct][0]
        assert r["pair_status"] == "internal" and r["amount"] == 0.0 and r["counts"] is False and r["in_kind"] is True


def test_in_kind_and_cash_rows_never_pair_with_each_other():
    out = _pair(etrade_1111=[_b(symbol="TOTL", quantity=-10.0, amount=None)],
                fidelity_2222=[_b(amount=10.0, description="TRANSFER")])
    assert out[A][0]["pair_status"] == "unmatched" and out[B][0]["pair_status"] == "unmatched"


def test_in_kind_different_quantity_or_symbol_stays_unmatched():
    out = _pair(etrade_1111=[_b(symbol="TOTL", quantity=-10.0, amount=None)],
                fidelity_2222=[_b(symbol="TOTL", quantity=9.0, amount=None), _b(symbol="EXMK", quantity=10.0, amount=None)])
    assert out[A][0]["pair_status"] == "unmatched"
    assert {r["pair_status"] for r in out[B]} == {"unmatched"}


def test_return_of_excess_contribution_is_not_a_transfer_and_not_external():
    out = _pair(fidelity_2222=[_b(action="RETURN EXCESS CONTR HSA", amount=-100.0)],
                etrade_1111=[_b(amount=100.0, description="ACH DEPOSIT")])
    assert out[B][0]["class"] == "excess_return" and out[B][0]["pair_status"] == "unpaired"
    assert out[A][0]["pair_status"] == "unmatched"


def test_journals_are_never_paired():
    out = _pair(etrade_1111=[_b(description="TRNSFR CASH TO MARGIN", amount=-300.0)],
                fidelity_2222=[_b(description="TRNSFR MARGIN TO CASH", amount=300.0)])
    assert out[A][0]["class"] == "adjustment" and out[A][0]["pair_status"] == "unpaired"
    assert out[B][0]["pair_status"] == "unpaired" and not out[B][0].get("pair_id")


def test_rollover_without_a_partner_is_unmatched_not_internal_and_keeps_its_marker():
    out = _pair(vanguard_3333=[_b(action="Rollover (incoming)", symbol="CASH", amount=5000.0)])
    r = out[C][0]
    assert r["pair_status"] == "unmatched" and r["rollover"] is True


def test_non_transfer_rows_stay_unpaired_and_inputs_are_not_mutated():
    ledger = _ledger(A, [_b(action="Contribution", amount=500.0, description="EMPLOYER"), _b(amount=-5.0)])
    before = [dict(r) for r in ledger]
    out = pair_transfers({A: ledger})
    assert out[A][0]["pair_status"] == "unpaired"
    assert ledger == before


def test_result_does_not_depend_on_account_order():
    a = _ledger(A, [_b(run_date="2026-03-01", amount=-1000.0)])
    b = _ledger(B, [_b(run_date="2026-03-02", amount=1000.0)])
    r1, r2 = pair_transfers({A: a, B: b}), pair_transfers({B: b, A: a})
    assert [(r["pair_status"], r["partner_account"]) for r in r1[A]] == [(r["pair_status"], r["partner_account"]) for r in r2[A]]


def test_contribution_pairs_with_a_matching_outflow_of_another_plan_account():
    out = _pair(fidelity_2222=[_b(run_date="2026-03-01", amount=-500.0, description="TRANSFER TO IRA")],
                etrade_1111=[_b(run_date="2026-03-02", action="Contribution", description="IRA CONTRIBUTION", amount=500.0)])
    assert out[A][0]["class"] == "contribution" and out[A][0]["counts"] is True
    assert out[A][0]["pair_status"] == out[B][0]["pair_status"] == "internal"
    assert out[A][0]["partner_account"] == B


def test_contribution_without_a_partner_stays_unpaired_not_unmatched():
    out = _pair(etrade_1111=[_b(action="Contribution", description="EMPLOYER", amount=500.0)],
                fidelity_2222=[_b(run_date="2026-03-01", amount=-40.0)])
    assert out[A][0]["pair_status"] == "unpaired" and out[B][0]["pair_status"] == "external_withdrawal"


def test_two_same_amount_contributions_for_one_outflow_stay_unmatched():
    out = _pair(fidelity_2222=[_b(run_date="2026-03-01", amount=-500.0)],
                etrade_1111=[_b(action="Contribution", amount=500.0)],
                vanguard_3333=[_b(action="Contribution", amount=500.0)])
    assert out[B][0]["pair_status"] == "unmatched"
    assert out[A][0]["pair_status"] == out[C][0]["pair_status"] == "unpaired"
