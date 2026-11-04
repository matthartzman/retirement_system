"""Transfer pairing across plan investment accounts (cash tracking Phase 3): pure, nothing is stored.

Takes the ledger rows of ALL plan investment accounts together (``cash_ledger.build_ledger``) and fills ``pair_status``
on each transfer row (design section 4.3, owner decisions in section 8):

- ``internal``: paired with exactly one opposite row of another plan account (``pair_id`` and ``partner_account`` set).
- ``external_withdrawal``: a cash outflow with no partner in a plan account; it stands alone (decision 3).
- ``external_inflow`` / ``external_in_kind``: cash, or shares, that arrived with no partner in a plan account (a rollover, a bank
  deposit, an ACAT from another broker): the sender is outside the plan, so there is nothing to pair.
- ``reversal``: an undescribed cash outflow and the same amount back into the SAME account within ``REVERSAL_DAYS`` (one candidate each way).
- ``reregistration``: shares that came in, went out and came in again in one account; the out cancels the earliest arrival.
- ``unmatched``: anything else (an ambiguous match, an inflow with a same-amount outflow within ``NEAR_DAYS``, an
  unclassified row, shares leaving with no partner).
  Visible, never guessed.

Contributions pair only when another plan account sent the money, and otherwise stay ``"unpaired"``. Rows that are not
transfers (income, trades, fees, journals, ``excess_return``) keep ``"unpaired"``.
A reference id (E*Trade ``REFID``) pairs first; otherwise the same amount (or, for an in-kind row, the same symbol and
shares) within ``WINDOW_DAYS`` pairs only when exactly one candidate exists on each side. In-kind rows are paired for
visibility only: they stay zero-cash and ``counts=False`` (the transaction log owns the lots). The shared function is
also what the transaction log's importer uses (integration plan decision 1.3).
"""
from __future__ import annotations

from datetime import date
from typing import Any, Mapping, Sequence

REVERSAL_DAYS = 60                   # a distribution put back within 60 days (HSA/IRA rule of thumb)
NEAR_DAYS = 30                       # an inflow with a same-amount outflow this close stays unmatched
WINDOW_DAYS = 3                      # the income check's tolerance
_OUT_CLASSES = frozenset({"transfer_out", "distribution"})
_IN_CLASSES = frozenset({"transfer_in", "contribution"})   # a contribution pairs only when another plan account sent it


def _day(row: Mapping[str, Any]) -> date:
    return date.fromisoformat(str(row["date"])[:10])


def _is_out(r: Mapping[str, Any]) -> bool:
    return r["class"] in _OUT_CLASSES


def _is_in(r: Mapping[str, Any]) -> bool:
    return r["class"] in _IN_CLASSES


def _same_thing(out: Mapping[str, Any], inn: Mapping[str, Any]) -> bool:
    """Same cash amount, or for in-kind rows the same symbol and share count; cash and in-kind never mix."""
    if out["in_kind"] != inn["in_kind"]:
        return False
    if out["in_kind"]:
        qo, qi = out.get("quantity"), inn.get("quantity")
        return bool(out["symbol"]) and out["symbol"] == inn["symbol"] and qo is not None and qi is not None \
            and abs(abs(qo) - abs(qi)) < 1e-6
    return abs(abs(out["amount"]) - abs(inn["amount"])) < 0.005 and out["amount"] != 0


def _link(out: dict[str, Any], inn: dict[str, Any], n: int) -> None:
    pid = f"pair-{n}"
    for r, other in ((out, inn), (inn, out)):
        r["pair_status"], r["pair_id"], r["partner_account"] = "internal", pid, other["account"]


def pair_transfers(ledgers: Mapping[str, Sequence[Mapping[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    """Copies of every ledger's rows with ``account``, ``pair_status``, ``pair_id`` and ``partner_account`` filled."""
    out: dict[str, list[dict[str, Any]]] = {}
    for account in sorted(ledgers):          # fixed order: the result never depends on how the caller built the mapping
        out[account] = [{**r, "account": account, "pair_id": None, "partner_account": None} for r in ledgers[account]]
    flat = [r for rows in out.values() for r in rows]
    outs = [r for r in flat if _is_out(r)]
    ins = [r for r in flat if _is_in(r)]
    n = 0

    # 1. reference id first: one outflow and one inflow of different accounts sharing it
    by_ref: dict[str, list[dict[str, Any]]] = {}
    for r in outs + ins:
        if r["ref_id"]:
            by_ref.setdefault(r["ref_id"], []).append(r)
    for rows in by_ref.values():
        o = [r for r in rows if _is_out(r)]
        i = [r for r in rows if _is_in(r)]
        if len(o) == 1 and len(i) == 1 and o[0]["account"] != i[0]["account"]:
            n += 1
            _link(o[0], i[0], n)

    # 2. amount (or in-kind symbol and shares) within the window, only when exactly one candidate exists on each side
    def candidates(r: dict[str, Any], pool: list[dict[str, Any]], match) -> list[dict[str, Any]]:
        return [p for p in pool if p["pair_status"] != "internal" and p["account"] != r["account"] and match(r, p)
                and abs((_day(r) - _day(p)).days) <= WINDOW_DAYS
                and not (r["ref_id"] and p["ref_id"] and r["ref_id"] != p["ref_id"])]   # two different references: two transfers

    free_out = [r for r in outs if r["pair_status"] != "internal"]
    free_in = [r for r in ins if r["pair_status"] != "internal"]
    ambiguous: set[int] = set()
    chosen: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for o in free_out:
        cand = candidates(o, free_in, lambda a, b: _same_thing(a, b))
        if len(cand) == 1 and len(candidates(cand[0], free_out, lambda a, b: _same_thing(b, a))) == 1:
            chosen.append((o, cand[0]))
        elif cand:
            ambiguous.add(id(o))       # a partner may exist but is not unique: left unmatched, not called a withdrawal
    for o, i in chosen:
        n += 1
        _link(o, i, n)

    # 2b. one account, undescribed cash out then the same amount back within REVERSAL_DAYS: a reversal (a returned distribution)
    for o in [r for r in outs if r["pair_status"] != "internal" and r["needs_review"] and not r["in_kind"]]:
        back = [i for i in ins if i["pair_status"] != "internal" and i["account"] == o["account"] and i["needs_review"]
                and _same_thing(o, i) and 0 <= (_day(i) - _day(o)).days <= REVERSAL_DAYS]
        outs_for = [p for p in outs if p["pair_status"] != "internal" and p["account"] == o["account"] and p["needs_review"]
                    and back and _same_thing(p, back[0]) and 0 <= (_day(back[0]) - _day(p)).days <= REVERSAL_DAYS]
        if len(back) == 1 and len(outs_for) == 1:
            n += 1
            pid = f"pair-{n}"
            for r in (o, back[0]):
                r["pair_status"], r["pair_id"], r["partner_account"] = "reversal", pid, o["account"]

    # 2c. one account, shares in, out, in again (a re-registration): the out cancels the earliest same-size arrival
    for o in [r for r in outs if r["pair_status"] != "internal" and r["in_kind"]]:
        back = sorted((i for i in ins if i["pair_status"] != "internal" and i["account"] == o["account"] and i["in_kind"]
                       and _same_thing(o, i) and 0 <= (_day(o) - _day(i)).days <= WINDOW_DAYS), key=_day)
        if back:
            n += 1
            pid = f"pair-{n}"
            for r in (o, back[0]):
                r["pair_status"], r["pair_id"], r["partner_account"] = "reregistration", pid, o["account"]

    # 3. what is left: a cash outflow stands alone as an external withdrawal, a clean inflow or arriving shares as an external
    #    inflow (the sender is outside the plan); everything else (ambiguous, unclassified, shares leaving) stays visible as unmatched
    for i in ins:        # a same-amount outflow within NEAR_DAYS (any account, paired or not) makes an inflow a question, not a fact
        if i["pair_status"] not in ("internal", "reversal", "reregistration") and any(
                _same_thing(p, i) and abs((_day(i) - _day(p)).days) <= NEAR_DAYS
                and not (i["ref_id"] and p["ref_id"] and i["ref_id"] != p["ref_id"]) for p in outs if p["pair_status"] not in ("reversal", "reregistration")):
            ambiguous.add(id(i))
    for r in outs + ins:
        if r["pair_status"] in ("internal", "reversal", "reregistration") or r["class"] == "contribution":
            continue                       # a contribution with no partner is simply a contribution (from outside the plan)
        if _is_out(r):
            alone = not r["in_kind"] and not r["needs_review"] and id(r) not in ambiguous
            r["pair_status"] = "external_withdrawal" if alone else "unmatched"
        else:
            clean = not r["needs_review"] and id(r) not in ambiguous
            r["pair_status"] = ("external_in_kind" if r["in_kind"] else "external_inflow") if clean else "unmatched"
    return out
