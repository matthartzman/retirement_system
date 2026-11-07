"""Other Asset tax treatment: type defaults, stored labels, holding period, parsed fields and the backfill
of purchase_date / tax_treatment into assets made before those fields existed."""
from datetime import date

import pytest

from src import other_asset_tax as oat
from src import plan_data_backfill as bf
from src.parsing.client_sections import parse_housing_and_other_assets


@pytest.mark.parametrize("typ, want", [
    ("Auto", "none"), ("Boat", "none"), ("Start-up Equity", "gains"), ("Other", "gains"),
    ("Art", "collectible_gains"), ("Collectible", "collectible_gains"),
])
def test_default_treatment_by_type(typ, want):
    assert oat.default_treatment(typ) == want


def test_stored_label_wins_and_blank_or_unknown_takes_the_default():
    assert oat.resolve_treatment("Auto", "Taxed on gains") == "gains"
    assert oat.resolve_treatment("Start-up Equity", "taxed on gains (collectible)") == "collectible_gains"
    assert oat.resolve_treatment("Art", "Not taxed") == "none"
    assert oat.resolve_treatment("Art", "") == "collectible_gains"
    assert oat.resolve_treatment("Auto", "nonsense") == "none"


def test_long_term_is_more_than_one_year():
    bought = date(2025, 3, 10)
    assert not oat.is_long_term(bought, date(2026, 3, 10))  # exactly one year: short-term
    assert oat.is_long_term(bought, date(2026, 3, 11))
    assert oat.is_long_term(None, date(2026, 1, 1))  # unknown purchase date counts as long-term
    assert oat.is_long_term(date(2024, 2, 29), date(2025, 3, 2))


def test_parse_date_accepts_iso_and_us():
    assert oat.parse_date("2024-05-01") == date(2024, 5, 1)
    assert oat.parse_date("5/1/2024") == date(2024, 5, 1)
    assert oat.parse_date("") is None and oat.parse_date("soon") is None


def _parse(items):
    data = {"Other Assets": {f"Other Asset {i}": v for i, v in enumerate(items, 1)}}
    c = {"plan_start": 2026}
    parse_housing_and_other_assets(data, c)
    return c["other_asset_items"]


def test_parser_carries_purchase_date_treatment_and_basis_flag():
    a, b, c = _parse([
        {"type": "Start-up Equity", "name": "hucu.ai", "value": "$50,000", "basis": "$25,000",
         "purchase_date": "2023-06-01", "sell_date": "2030-01-15"},
        {"type": "Art", "name": "Masterworks", "value": "$10,000"},
        {"type": "Auto", "name": "Car", "value": "$20,000", "tax_treatment": "Taxed on gains"},
    ])
    assert (a["tax_treatment"], a["purchase_date"], a["sell_date"], a["basis_entered"]) == ("gains", "2023-06-01", "2030-01-15", True)
    assert (b["tax_treatment"], b["purchase_date"], b["basis_entered"]) == ("collectible_gains", "", False)
    assert c["tax_treatment"] == "gains"  # an explicit choice beats the type default


class _Store:
    def __init__(self, rows):
        self._rows = rows

    def rows(self, section):
        return [r for r in self._rows if r["section"] == section]

    def all_rows(self):
        return list(self._rows)


def _row(sub, label):
    return {"section": "Other Assets", "subsection": sub, "label": label}


def test_backfill_adds_only_the_missing_rows_of_each_other_asset():
    store = _Store([_row("Other Asset 1", "type"), _row("Other Asset 2", "type"), _row("Other Asset 2", "purchase_date"),
                    _row("Summary", "note")])
    entry = bf.BackfillEntry(oat.backfill_rows, from_plan=True)
    [(got_entry, missing)] = bf.pending_rows(store, [entry], None)
    assert got_entry is entry
    assert [(r[1], r[2]) for r in missing] == [("Other Asset 1", "purchase_date"), ("Other Asset 1", "tax_treatment"),
                                              ("Other Asset 2", "tax_treatment")]
    assert all(r[3] == "" for r in missing)  # blank: the type's default, never a guessed value


def test_backfill_entry_is_registered_for_the_active_plan():
    from src.server import app_core

    assert any(e.from_plan and e.rows is oat.backfill_rows for e in app_core.PLAN_DATA_BACKFILL_ENTRIES)
