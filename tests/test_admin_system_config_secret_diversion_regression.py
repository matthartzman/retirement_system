"""WI-206 / ARC-006: provider API keys never reach the checked-in system_config.csv."""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

from src.server_services import admin_service

ROOT = Path(__file__).resolve().parents[1]
HEADER = ["section", "subsection", "label", "value", "units", "notes"]


@pytest.fixture()
def stored(monkeypatch):
    calls = {}
    monkeypatch.setattr("src.secrets_store.set_secret", lambda name, value, *a, **k: calls.__setitem__(name, value))
    return calls


def _rows(path):
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.reader(f))


def _cfg_rows(fmp="FMPKEY123", alpha="ALPHAKEY456"):
    return [HEADER,
            ["Market Pricing", "API", "fmp_api_key", fmp, "secret", ""],
            ["Market Pricing", "API", "alpha_vantage_api_key", alpha, "secret", ""],
            ["Market Pricing", "API", "timeout", "10", "sec", ""]]


def test_save_system_config_rows_diverts_keys(tmp_path, stored):
    p = tmp_path / "system_config.csv"
    payload, status, _b, after = admin_service.save_system_config({"rows": _cfg_rows()}, p)
    assert status == 200
    assert stored == {"fmp_api_key": "FMPKEY123", "alpha_vantage_api_key": "ALPHAKEY456"}
    assert payload["secrets_stored"] == ["fmp_api_key", "alpha_vantage_api_key"]
    text = p.read_text(encoding="utf-8")
    assert "FMPKEY123" not in text and "ALPHAKEY456" not in text
    assert [r[3] for r in _rows(p)[1:]] == ["", "", "10"]
    assert "FMPKEY123" not in str(after)


def test_save_system_config_csv_content_diverts_keys(tmp_path, stored):
    p = tmp_path / "system_config.csv"
    content = "\n".join(",".join(r) for r in _cfg_rows(alpha="")) + "\n"
    _payload, status, *_ = admin_service.save_system_config({"csv_content": content}, p)
    assert status == 200
    assert stored == {"fmp_api_key": "FMPKEY123"}
    assert "FMPKEY123" not in p.read_text(encoding="utf-8")


def test_generic_csv_endpoint_for_system_kind_also_diverts(tmp_path, stored):
    p = tmp_path / "system_config.csv"
    payload, status, *_ = admin_service.save_csv_file(
        "system", "system_config.csv", {"rows": _cfg_rows()}, base_dir=tmp_path, system_config_path=p)
    assert status == 200 and payload["secrets_stored"]
    assert "FMPKEY123" not in p.read_text(encoding="utf-8")


def test_blank_key_cells_do_not_touch_secret_store(tmp_path, stored):
    p = tmp_path / "system_config.csv"
    admin_service.save_system_config({"rows": _cfg_rows("", "")}, p)
    assert stored == {}


def test_secret_store_failure_does_not_write_key_to_csv(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise OSError("disk")
    monkeypatch.setattr("src.secrets_store.set_secret", boom)
    p = tmp_path / "system_config.csv"
    with pytest.raises(OSError):
        admin_service.save_system_config({"rows": _cfg_rows()}, p)
    assert not p.exists()


def test_shipped_system_config_key_cells_are_blank():
    rows = _rows(ROOT / "system_config.csv")
    for row in rows:
        if len(row) > 3 and row[2] in admin_service.SECRET_CONFIG_LABELS | {"openai_api_key"}:
            assert row[3] == "", row[2]
