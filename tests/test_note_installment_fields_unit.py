"""Note Receivable installment-sale inputs: the four Form 8949 rows per note, their backfill, the gain ratios
the parser derives from them, and the interest schedule read for every year the note pays.

Design: documentation/future/superpowers/plans/2026-11-06-note-installment-gain-tax-design-and-plan.md 4.1-4.4."""
from __future__ import annotations

import pytest

from src import note_installment_tax as nit
from src import plan_data_backfill as bf
from src.data_io import parse_note_receivable  # re-export; data_io must load before parsing.note_receivable

REDMANE_PRINCIPAL = 59_281.62
REDMANE_FINAL = 59_327.50


def test_redmane_ratios_reproduce_the_8949_gains():
    st, lt = nit.gain_ratios(10_671, 0, 48_611, 7_500)
    assert st * REDMANE_PRINCIPAL == pytest.approx(10_671, abs=1)
    assert lt * REDMANE_PRINCIPAL == pytest.approx(41_111, abs=1)
    assert st * REDMANE_FINAL == pytest.approx(10_679, abs=1)
    assert lt * REDMANE_FINAL == pytest.approx(41_143, abs=1)


def test_blank_one_sided_and_loss_inputs():
    assert nit.gain_ratios(0, 0, 0, 0) == (0.0, 0.0)
    st, lt = nit.gain_ratios(0, 0, 50_000, 10_000)
    assert st == 0.0 and lt == pytest.approx(0.8)
    assert nit.gain_ratios(10_000, 12_000, 0, 0) == (0.0, 0.0)  # basis above proceeds: no gain, never negative


def _note_data(**extra):
    fields = {"name": "RedMane Note", "face_value": "$474,252.96", "first_payment": "1/2/2026",
              "last_payment": "1/2/2033", "annual_principal_base_period": "$59,281.62",
              "final_principal_2033": "$59,327.50", **extra}
    interest = {str(y): "$1,000" for y in range(2025, 2036)}  # one year before plan start, three past year 8
    return {"Note Receivable": {"Note 1": fields, "Note 1 Interest": interest}}


def test_parser_reads_the_8949_fields_into_ratios():
    data = _note_data(st_proceeds="$10,671", st_basis="$0", lt_proceeds="$48,611", lt_basis="$7,500")
    item = parse_note_receivable(data, 2026)["note_items"][0]
    assert item["st_gain_per_principal"] == pytest.approx(10_671 / 59_282, rel=1e-3)
    assert item["lt_gain_per_principal"] == pytest.approx(41_111 / 59_282, rel=1e-3)


def test_parser_blank_fields_mean_no_gain():
    item = parse_note_receivable(_note_data(), 2026)["note_items"][0]
    assert (item["st_gain_per_principal"], item["lt_gain_per_principal"]) == (0.0, 0.0)


def test_parser_reads_every_interest_year_from_plan_start():
    out = parse_note_receivable(_note_data(), 2026)
    years = out["note_items"][0]["interest_by_year"]
    assert 2025 not in years
    assert 2026 in years and 2035 in years
    assert out["note_interest"][2035] == pytest.approx(1_000)


def test_added_field_rows_are_the_four_usd_rows():
    rows = nit.added_field_rows("Note 3")
    assert [r[2] for r in rows] == list(nit.FIELDS) == ["st_proceeds", "st_basis", "lt_proceeds", "lt_basis"]
    assert all(r[0] == "Note Receivable" and r[1] == "Note 3" and r[3] == "$0" and r[4] == "USD" for r in rows)


class _Store:
    def __init__(self, rows):
        self._rows = rows

    def rows(self, section):
        return [r for r in self._rows if r["section"] == section]

    def all_rows(self):
        return list(self._rows)


def _row(sub, label):
    return {"section": "Note Receivable", "subsection": sub, "label": label}


def test_backfill_adds_only_missing_rows_of_each_note():
    store = _Store([_row("Note 1", "name"), _row("Note 1 Interest", "2026"), _row("Note 2", "name"),
                    _row("Note 2", "st_proceeds")])
    entry = bf.BackfillEntry(nit.backfill_rows, from_plan=True)
    [(_entry, missing)] = bf.pending_rows(store, [entry], None)
    assert [(r[1], r[2]) for r in missing] == [
        ("Note 1", "st_proceeds"), ("Note 1", "st_basis"), ("Note 1", "lt_proceeds"), ("Note 1", "lt_basis"),
        ("Note 2", "st_basis"), ("Note 2", "lt_proceeds"), ("Note 2", "lt_basis")]


def test_backfill_entry_is_registered_for_the_active_plan():
    from src.server import app_core

    assert any(e.from_plan and e.rows is nit.backfill_rows for e in app_core.PLAN_DATA_BACKFILL_ENTRIES)


def test_add_note_writes_the_four_rows(tmp_path, monkeypatch):
    from src.server import plan_routes
    from tests.plan_fixture import make_plan

    plan = make_plan(tmp_path / "ws")
    monkeypatch.setenv("RETIREMENT_SYSTEM_WORKSPACE_ROOT", str(plan.root))
    monkeypatch.delenv("RETIREMENT_SYSTEM_PLAN_DB", raising=False)
    monkeypatch.delenv("RETIREMENT_SYSTEM_CONFIG_FILE", raising=False)
    payload, status = plan_routes._strategy_asset_feature_service().add_note_receivable_payload({"name": "X"})
    assert status == 200
    with plan.store(readonly=True) as store:
        labels = {r["label"] for r in store.rows("Note Receivable") if r["subsection"] == payload["section"]}
    assert set(nit.FIELDS) <= labels
