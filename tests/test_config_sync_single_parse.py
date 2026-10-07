"""The plan-data sync must read the sectioned CSV set once per save.

System review 2026-08-04, architect finding `csv-roundtrip-on-every-save`: the sync ran
on every plan-data CSV write and used to parse the ten-file CSV set twice. Since WP4.2
``_sync_config_backends()`` reads the set once (``csv_exchange.read_plan_csv_set``),
carries it into the active plan file and writes the JSON/YAML mirrors from the plan's
sectioned view. The architect's risk note asked for a byte-comparison gate on the
derived files, since tools and folder export read input/client_data.json|yaml -- that is
test_derived_files_are_byte_identical below.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import src.active_plan as active_plan
import src.config_backend as cb
from src.data_io import load_csv
from tests import plan_fixture as pf


def _hashes(written: dict[str, str]) -> dict[str, str]:
    return {
        Path(p).name: hashlib.sha256(Path(p).read_bytes()).hexdigest()
        for p in written.values()
    }


def test_derived_files_are_byte_identical(tmp_path):
    """The mirrors written from the plan file's view equal those written from the CSV
    loader's view: a formatting or ordering difference would be a behaviour change."""
    ws = pf.make_plan(tmp_path / "ws")
    old_dir = tmp_path / "from_csv"
    new_dir = tmp_path / "from_plan_file"
    from_csv = cb.export_client_json_yaml(load_csv(ws.input_dir / "client_data.csv"), old_dir)
    from_plan = cb.export_client_json_yaml(ws.store_data(), new_dir)
    assert _hashes(from_csv) == _hashes(from_plan)


def test_sync_reads_the_csv_set_only_once(monkeypatch, tmp_path):
    """Guards the actual saving: one read of the CSV set per sync."""
    import src.server.app_core as app_core

    # a workspace of its own: the shared session workspace is edited by other xdist workers
    ws = pf.make_plan(tmp_path / "ws")
    monkeypatch.setenv("RETIREMENT_SYSTEM_WORKSPACE_ROOT", str(ws.root))
    monkeypatch.delenv(active_plan.PLAN_DB_ENV, raising=False)
    monkeypatch.delenv("RETIREMENT_SYSTEM_CONFIG_FILE", raising=False)
    monkeypatch.setattr(app_core, "CSV_PATH", ws.input_dir / "client_data.csv")

    calls = {"n": 0}
    real = active_plan.read_plan_csv_set

    def counting(*args, **kwargs):
        calls["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(active_plan, "read_plan_csv_set", counting)
    result = app_core._sync_config_backends()
    assert result["success"] is True, result
    assert calls["n"] == 1
    # an unchanged CSV set writes nothing to the plan file
    assert result["plan_rows"] == {"updated": 0, "inserted": 0, "deleted": 0, "rewritten": 0}
