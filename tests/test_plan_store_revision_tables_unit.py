"""M1: restoring a revision puts back every plan table (flat datasets and rental), not only plan_rows."""
from __future__ import annotations

from src.stores import PlanStore
from src.stores.datasets import _DATASETS

ROW = {"Date": "2026-01-02", "Merchant": "x"}


def _fill(store):
    store.insert_row("income", label="pay", value="1")
    for i, (table, cols) in enumerate(_DATASETS.items()):
        row = {c: f"{table}{i}" for c in cols}
        row["zz_extra"] = "keep"
        _repo(store, table).replace_all([row, {c: "b" for c in cols}])
    store.rental.replace_all([{"name": "A", "monthly_rent": 1500.0, "improvements": [{"year": 2020, "amount": 5.0}], "overrides": [{"year": 2027, "gross_rent": 9.0}]}])


def _repo(store, table):
    from src.stores.datasets import FlatDatasetRepository
    return FlatDatasetRepository(store, table)


def _state(store):
    return ({t: _repo(store, t).rows() for t in _DATASETS}, store.rental.properties())


def test_restore_revision_round_trips_every_table(tmp_path):
    store = PlanStore.open(tmp_path / "p.rpx")
    _fill(store)
    before = _state(store)
    rev = store.snapshot_revision("manual", "all")
    for t in _DATASETS:
        _repo(store, t).replace_all([])
    store.rental.replace_all([])
    store.restore_revision(rev)
    assert _state(store) == before
    assert before[1] and all(before[0][t] for t in _DATASETS)


def test_old_revision_without_tables_leaves_tables_alone(tmp_path):
    store = PlanStore.open(tmp_path / "p.rpx")
    _fill(store)
    rev = store.snapshot_revision("manual", "x", tables=False)
    before = _state(store)
    store.restore_revision(rev)
    assert _state(store) == before


def test_recovery_revisions_labelled_grouped_and_unpruned(tmp_path):
    store = PlanStore.open(tmp_path / "p.rpx")
    store.insert_row("income", label="pay", value="1")
    store.snapshot_revision("budget-recovery-seed", "seed")
    store.snapshot_revision("pre-recovery", "pre")
    store.set_revision_retention(1)
    for i in range(3):
        store.snapshot_revision("manual", str(i))
    revs = store.list_revisions()
    rec = store.list_revisions(group="recovery")
    assert {r["source"] for r in rec} == {"budget-recovery-seed", "pre-recovery"}
    assert {r["group"] for r in rec} == {"recovery"} and rec[0]["label"]
    assert [r["group"] for r in revs].count("history") == 1
