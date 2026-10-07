"""WP4.1 key invariant for the WP4.2 read path: a fixture's plan file reads back exactly as
``load_csv`` reads its CSV set.

``make_plan`` builds ``plan.rpx`` with the ``csv_exchange`` importer; ``PlanStore.sectioned_data``
must return the same ``{section: {subsection: {label: value}}}`` as ``data_io.load_csv`` over
the copied CSVs -- same keys, same values, same key order -- and ``parse_client`` must produce
the same engine config from either. When WP4.2 swaps the read path, this is what proves the
swap moves no number.
"""
from __future__ import annotations

import json

import pytest

from src.data_io import parse_client
from tests import plan_fixture as pf


@pytest.mark.parametrize("fixture", sorted(pf.FIXTURES))
def test_plan_file_view_is_identical_to_load_csv(tmp_path, fixture):
    ws = pf.make_plan(tmp_path, fixture)
    legacy, view = ws.data(), ws.store_data()
    assert view == legacy
    # identical including key order at every level (json.dumps keeps insertion order)
    assert json.dumps(view) == json.dumps(legacy)
    with ws.store(readonly=True) as store:
        rows = store.all_rows()
    # every load_csv value is backed by a stored row; extra stored rows are only the
    # earlier copies of a repeated key (the legacy anchor's Scenarios duplicates)
    n_values = sum(len(labels) for subs in legacy.values() for labels in subs.values())
    keys = [(r["section"], r["subsection"], r["label"]) for r in rows]
    assert len(set(keys)) == n_values
    assert len(rows) - n_values == len(keys) - len(set(keys)) == 2


@pytest.mark.parametrize("fixture", sorted(pf.FIXTURES))
def test_parse_client_is_identical_from_either_source(tmp_path, fixture):
    ws = pf.make_plan(tmp_path, fixture)
    from_csv = parse_client(ws.data(), "", skip_live_pricing=True)
    from_store = parse_client(ws.store_data(), "", skip_live_pricing=True)
    assert from_store.keys() == from_csv.keys()
    diff = [k for k in from_csv if pf.plain(from_store[k]) != pf.plain(from_csv[k])]
    assert diff == []


def test_withheld_part_file_is_absent_from_the_plan_file(tmp_path):
    ws = pf.make_plan(tmp_path, withhold=("client_business.csv",))
    view = ws.store_data()
    assert "Business Succession" not in view
    assert view == ws.data()
