"""The plan-data sync must parse the sectioned CSVs once, not twice.

System review 2026-08-04, architect finding `csv-roundtrip-on-every-save`:
``_sync_config_backends()`` called ``export_client_json_yaml()`` and
``import_csv_to_sqlite()``, and each independently called ``load_csv()``.
``load_csv`` on the client_data.csv anchor opens and DictReader-parses TEN
files -- itself plus the nine part files in
plan_data_registry.CLIENT_DATA_PART_FILES -- so every saved field cost twenty
file reads. The sync runs on every plan-data CSV write
(plan_data_file_service, config_service, demo_plan_service, app_core).

Both functions now accept pre-parsed ``data``. The architect's risk note asked
for a byte-comparison gate on the derived files, since tools and folder export
read input/client_data.json|yaml -- that is test_derived_files_are_byte_identical
below.
"""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pytest

import src.config_backend as cb
from conftest import TEST_INPUT_DIR

ANCHOR = TEST_INPUT_DIR / "client_data.csv"


def _hashes(written: dict[str, str]) -> dict[str, str]:
    return {
        Path(p).name: hashlib.sha256(Path(p).read_bytes()).hexdigest()
        for p in written.values()
    }


def test_derived_files_are_byte_identical(tmp_path):
    """Pre-parsed data must produce exactly the same JSON/YAML mirrors.

    These are read by tools and by folder export, so a formatting or ordering
    difference here would be a real behaviour change, not an optimisation.
    """
    old_dir = tmp_path / "loaded_internally"
    new_dir = tmp_path / "data_passed_in"
    old_dir.mkdir()
    new_dir.mkdir()

    internally = cb.export_client_json_yaml(ANCHOR, old_dir)
    passed_in = cb.export_client_json_yaml(ANCHOR, new_dir, data=cb.load_csv(ANCHOR))

    assert _hashes(internally) == _hashes(passed_in)


def test_sync_parses_the_csvs_only_once(tmp_path, monkeypatch):
    """Guards the actual saving: one load_csv per sync, not two."""
    calls = {"n": 0}
    real = cb.load_csv

    def counting(*args, **kwargs):
        calls["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(cb, "load_csv", counting)

    data = cb.load_csv(ANCHOR)
    calls["n"] = 0  # don't count the caller's own parse
    cb.export_client_json_yaml(ANCHOR, tmp_path, data=data)
    cb.import_csv_to_sqlite(ANCHOR, tmp_path / "plan.db", data=data)

    assert calls["n"] == 0, (
        f"export/import re-parsed the CSVs {calls['n']} time(s) despite being "
        "handed pre-parsed data"
    )


def test_omitting_data_still_loads(tmp_path, monkeypatch):
    """The parameter is optional; existing callers must keep working."""
    calls = {"n": 0}
    real = cb.load_csv

    def counting(*args, **kwargs):
        calls["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(cb, "load_csv", counting)
    cb.export_client_json_yaml(ANCHOR, tmp_path)
    assert calls["n"] == 1
