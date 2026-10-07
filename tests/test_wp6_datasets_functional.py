"""WP6.1/6.2: holdings, liabilities, HSA schedule and targets live in plan.db tables; conversion
step C4a fills them from the legacy files; the product readers see the active plan's tables."""
import csv
import io

import pytest

from tests.plan_fixture import fixture_dir, make_plan
from src.csv_exchange import FLAT_DATASET_FILES, dataset_csv_text
from src.legacy_conversion.steps import c4a_datasets
from src.stores import PlanStore


def _csv_rows(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def test_c4a_converts_the_fixture_files_and_is_idempotent(tmp_path):
    with PlanStore.open(tmp_path / "p.rpx") as store:
        report = c4a_datasets.run(fixture_dir("sample_frozen"), store)
        assert not report.skipped
        for name, file in FLAT_DATASET_FILES.items():
            src = fixture_dir("sample_frozen") / file
            expected = len(_csv_rows(src)) if src.is_file() else 0
            assert getattr(store, name).count() == expected == report.rows_written.get(name, 0)
        assert store.get_meta(c4a_datasets.MARKER_KEY)
        assert c4a_datasets.run(fixture_dir("sample_frozen"), store).skipped


def test_converted_holdings_equal_the_file_cell_for_cell(tmp_path):
    with PlanStore.open(tmp_path / "p.rpx") as store:
        c4a_datasets.run(fixture_dir("sample_frozen"), store)
        got = list(csv.DictReader(io.StringIO(dataset_csv_text(store.holdings))))
    want = _csv_rows(fixture_dir("sample_frozen") / "client_holdings.csv")
    assert [{k: r[k] for k in w} for r, w in zip(got, want)] == want and len(got) == len(want)


@pytest.mark.parametrize("fixture", ["sample_frozen", "demo"])
def test_make_plan_loads_the_datasets_into_the_plan_file(tmp_path, fixture):
    ws = make_plan(tmp_path, fixture)
    with ws.store(readonly=True) as store:
        assert store.holdings.count() == len(_csv_rows(ws.input_dir / "client_holdings.csv"))


def test_readers_follow_the_active_plan_not_the_workspace_files(tmp_path, monkeypatch):
    from src.active_plan import PLAN_DB_ENV
    from src.plan_datasets import active_dataset_text

    ws = make_plan(tmp_path, "sample_frozen")
    monkeypatch.setenv(PLAN_DB_ENV, str(ws.plan_db))
    assert active_dataset_text("holdings").splitlines()[0].startswith("account,symbol")
    with ws.store() as store:
        store.holdings.replace_all([])
    assert active_dataset_text("holdings") is None  # an empty table reads as "no file"
