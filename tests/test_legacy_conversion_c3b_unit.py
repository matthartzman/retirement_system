"""Conversion step C3b: the legacy custom reference files -> plan override tables."""
from __future__ import annotations

import pytest

from src import optimization as opt
from src import plan_overrides as po
from src.csv_exchange import parse_csv_dicts
from src.legacy_conversion.steps import c3b_plan_overrides as c3b
from src.stores import PlanStore

CLASS = next(iter(opt._BASE_ASSET_CLASSES))
OTHER = list(opt._BASE_ASSET_CLASSES)[1]
CMA_CSV = (f"horizon_years,preset,asset_class,expected_return,volatility,stock_index_correlation,notes\n"
           f"30,BASELINE,{CLASS},7.5%,15%,1.0,expert view\n"
           f",,{OTHER},4%,6%,,\n")
CORR_CSV = f"horizon_years,preset,asset_class_a,asset_class_b,correlation,notes\n,,{CLASS},{OTHER},0.3,x\n"


def test_parse_csv_dicts_strips_cells_and_skips_empty_rows():
    text = "﻿a, b\n 1 , 2\n,\n3,\n"
    assert parse_csv_dicts(text) == [{"a": "1", "b": "2"}, {"a": "3", "b": ""}]
    assert parse_csv_dicts("") == []


def test_convert_is_pure_drops_extra_columns_and_validates():
    rows = c3b.convert(po.CMA, parse_csv_dicts(CMA_CSV))
    assert rows[0] == {"horizon_years": "30", "preset": "BASELINE", "asset_class": CLASS,
                       "expected_return": "7.5%", "volatility": "15%", "stock_index_correlation": "1.0"}
    assert rows[1] == {"asset_class": OTHER, "expected_return": "4%", "volatility": "6%"}
    with pytest.raises(po.OverrideRowsError):
        c3b.convert(po.CMA, [{"asset_class": "Nope", "expected_return": "5%"}])


def test_run_writes_the_tables_and_the_marker_once():
    with PlanStore.open() as store:
        report = c3b.run(store, {po.CMA: CMA_CSV, po.CORRELATIONS: CORR_CSV, po.REAL_LOSS: "ignored"})
        assert report.as_dict() == {"step": "C3b", "skipped": False, "rows_written": {po.CMA: 2, po.CORRELATIONS: 1}}
        view = store.sectioned_data()
        assert po.override_rows(view, po.CMA)[1]["asset_class"] == OTHER
        assert po.override_rows(view, po.CORRELATIONS) == [{"asset_class_a": CLASS, "asset_class_b": OTHER, "correlation": "0.3"}]
        assert store.get_meta(c3b.MARKER_KEY) == "rows=capital_market:2,correlations:1"
        # a second run is a no-op
        assert c3b.run(store, {po.CMA: ""}).skipped is True and len(po.override_rows(store.sectioned_data(), po.CMA)) == 2


def test_run_with_no_files_only_stamps_the_marker():
    with PlanStore.open() as store:
        report = c3b.run(store, {})
        assert report.rows_written == {} and store.all_rows() == [] and store.get_meta(c3b.MARKER_KEY) == "rows="


def test_an_invalid_file_writes_nothing_and_no_marker():
    with PlanStore.open() as store:
        with pytest.raises(po.OverrideRowsError):
            c3b.run(store, {po.CMA: CMA_CSV, po.CORRELATIONS: "asset_class_a,asset_class_b,correlation\nNope,Nope,2\n"})
        assert store.all_rows() == [] and store.get_meta(c3b.MARKER_KEY) is None
