"""WP12.9: rental properties through csv_exchange (template, validation, round trip, feature-off)."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.csv_exchange import (
    ImportRejected, export_plan_set_files, import_plan_set, parse, preview, rental_csv)
from src.stores import PlanStore

FIX = Path(__file__).parent / "fixtures" / "csv_exchange" / "rental"
TEMPLATE = {f: (FIX / f).read_text() for f in rental_csv.FILES}


@pytest.fixture
def store():
    s = PlanStore.open(":memory:")
    yield s
    s.close()


def _import(store, files, **kw):
    return import_plan_set(store, files, **kw)


def test_template_fixture_is_current():
    assert rental_csv.template_files() == TEMPLATE


def test_template_imports_clean_and_round_trips_byte_stable(store):
    res = _import(store, TEMPLATE)
    assert res["errors"] == 0 and res["committed"] == {"rental_properties": 1}
    p = store.rental.get("Maple Street duplex")
    assert p["monthly_rent"] == 2400 and p["active_participation"] is True
    assert p["improvements"][0]["description"] == "New roof" and p["overrides"][0]["year"] == 2025
    first = rental_csv.export_dataset(store)
    assert first == TEMPLATE
    other = PlanStore.open(":memory:")
    try:
        _import(other, first)
        assert rental_csv.export_dataset(other) == first
    finally:
        other.close()


def test_plan_set_export_carries_rental_only_when_present(store):
    assert not set(rental_csv.FILES) & set(export_plan_set_files(store))
    _import(store, TEMPLATE)
    out = export_plan_set_files(store)
    assert {f: out[f] for f in rental_csv.FILES} == TEMPLATE
    assert '"rental_properties"' in out["manifest.json"]


def test_unknown_columns_stripped_with_warning(store):
    files = dict(TEMPLATE)
    files[rental_csv.PROPERTIES_FILE] = files[rental_csv.PROPERTIES_FILE].replace("name,", "name,bogus,", 1).replace(
        "Maple Street duplex,", "Maple Street duplex,zzz,", 1)
    res = _import(store, files)
    assert res["errors"] == 0
    warns = res["datasets"]["rental_properties"]["warnings"]
    assert any("bogus" in w["message"] for w in warns)
    assert rental_csv.export_dataset(store) == TEMPLATE


def test_row_level_errors_block_and_write_nothing(store):
    bad = dict(TEMPLATE)
    bad[rental_csv.PROPERTIES_FILE] = bad[rental_csv.PROPERTIES_FILE].replace(",2400,", ",abc,", 1)
    bad[rental_csv.IMPROVEMENTS_FILE] += "Nowhere,2024,1,500,x\n"
    res = _import(store, bad, dry_run=True)
    errs = res["datasets"]["rental_properties"]["errors"]
    assert res["errors"] == 2 and not res["will_write"]
    assert any(e["row"] == 1 and "monthly_rent" in e["message"] for e in errs)
    assert any(e["row"] == 3 and "Nowhere" in e["message"] for e in errs)
    with pytest.raises(ImportRejected):
        _import(store, bad)
    assert store.rental.count() == 0


def test_missing_required_column_and_blank_name(store):
    parsed = parse({rental_csv.PROPERTIES_FILE: "kind\nstandalone\n"}, "rental_properties")
    assert any("missing required" in i.message for i in parsed.errors)
    parsed = parse({rental_csv.PROPERTIES_FILE: "name,monthly_rent\n ,100\n"}, "rental_properties")
    s = PlanStore.open(":memory:")
    try:
        assert any("blank" in e["message"] for e in preview(s, parsed)["errors"])
    finally:
        s.close()


def test_import_keeps_data_regardless_of_feature_and_replaces_set(store):
    _import(store, TEMPLATE)
    # a file set with only the properties file replaces the set and clears the children
    only = {rental_csv.PROPERTIES_FILE: TEMPLATE[rental_csv.PROPERTIES_FILE]}
    _import(store, only)
    p = store.rental.get("Maple Street duplex")
    assert p["improvements"] == [] and p["overrides"] == []


def test_preview_diff_counts(store):
    _import(store, TEMPLATE)
    res = _import(store, TEMPLATE, dry_run=True)
    d = res["datasets"]["rental_properties"]
    assert d["diff"]["unchanged"] == 3 and d["diff"]["added"] == 0 and d["rows_after"] == 3
