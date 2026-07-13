"""Phase 1 DB-canonical migration seam: src.engine_config_loader.load_engine_config.

Verifies that source='db' (canonical local SQLite plan snapshot) and
source='import_file' (explicit CSV adapter import) produce an equivalent
engine config for the same sample plan, and that the default source='current'
still resolves without raising (i.e. the additive seam does not disturb the
existing build path).

Per repo convention, live market-price providers are disabled for
deterministic golden-master-adjacent comparisons.

Uses pytest's tmp_path fixture (not tempfile.TemporaryDirectory) because
SQLite WAL-mode journal files can still be memory-mapped by the OS
momentarily after the connection context manager exits, and Windows refuses
to delete a file with an open handle; tmp_path's deferred cleanup avoids
turning that harmless race into a spurious test failure.
"""
import csv
import os
from pathlib import Path

import pytest

os.environ.setdefault("RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS", "1")

from src.data_io import load_csv
from src.local_store import import_sectioned_plan, init_local_store
from src.engine_config_loader import load_engine_config

ROOT = Path(__file__).resolve().parents[1]

# A representative cross-section of scalar engine-config fields that should be
# identical regardless of whether the sectioned data was acquired from the
# canonical DB snapshot or from a freshly-imported CSV adapter file, since
# both funnel through the same prepare_config_from_sectioned_data pipeline.
_COMPARISON_KEYS = [
    "h_name", "w_name", "h_dob_yr", "w_dob_yr", "h_ret_yr", "w_ret_yr",
    "filing_status", "state", "inf", "ss_cola", "ret", "spend_base",
    "spend_inf", "mort_bal", "mort_rate", "mort_end", "home_val",
    "k401_mo", "k401_lim", "earned", "plan_start", "plan_end",
]


def _write_sectioned_csv(data: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["section", "subsection", "label", "value"])
        w.writeheader()
        for section, subs in data.items():
            for subsection, labels in subs.items():
                for label, value in labels.items():
                    w.writerow({"section": section, "subsection": subsection, "label": label, "value": value})


@pytest.fixture(scope="module")
def sample_data():
    data = load_csv(ROOT / "input" / "client_data.csv")
    assert data, "expected input/client_data.csv to parse into sectioned data"
    return data


def test_db_and_import_file_sources_produce_equivalent_config(sample_data, tmp_path):
    csv_path = tmp_path / "sample_plan.csv"
    db_path = tmp_path / "engine_config_loader_test.db"

    _write_sectioned_csv(sample_data, csv_path)
    init_local_store(db_path)
    import_sectioned_plan(sample_data, source="test_seed", db_path=db_path)

    cfg_from_db = load_engine_config(source="db", db_path=db_path, optimize_roth=False)
    cfg_from_file = load_engine_config(
        source="import_file", path=csv_path, backend="CSV", optimize_roth=False,
    )

    for key in _COMPARISON_KEYS:
        assert key in cfg_from_db, f"missing {key} in db-sourced config"
        assert key in cfg_from_file, f"missing {key} in import_file-sourced config"
        assert cfg_from_db[key] == cfg_from_file[key], (
            f"engine config field {key!r} differs between source='db' ({cfg_from_db[key]!r}) "
            f"and source='import_file' ({cfg_from_file[key]!r})"
        )


def test_unknown_source_raises():
    with pytest.raises(ValueError):
        load_engine_config(source="not_a_real_source")


def test_import_file_requires_path():
    with pytest.raises(ValueError):
        load_engine_config(source="import_file")


def test_default_source_preserves_current_build_behavior():
    # source='current' (the default) must resolve without raising and
    # must return the same shape of config as the existing build path
    # (config_backend.load_active_config + prepare_config_from_sectioned_data).
    cfg = load_engine_config(optimize_roth=False)
    assert "plan_start" in cfg
    assert "h_name" in cfg
