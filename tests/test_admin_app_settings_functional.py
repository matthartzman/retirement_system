"""Admin app install-wide settings, system status and tax-law routes, driven through the WSGI facade."""
from __future__ import annotations

import json

import pytest

from admin_app.main import create_app
from admin_app.settings import SettingsService
from src import system_config
from src.identity import IdentityStore

HEADERS = {"Host": "127.0.0.1:5056"}


class Rig:
    def __init__(self, tmp_path):
        self.store = IdentityStore(tmp_path / "identity.db", scrypt_n=2**4)
        self.settings = SettingsService(tmp_path / "workspace")
        self.client = create_app(self.store, settings=self.settings).test_client()

    def get(self, path):
        r = self.client.get(path, headers=HEADERS)
        return r.status_code, json.loads(r.get_data(as_text=True))

    def post(self, path, body):
        r = self.client.post(path, json=body, headers=HEADERS)
        return r.status_code, json.loads(r.get_data(as_text=True))

    def row(self, label):
        return next(r for r in self.get("/api/settings")[1]["rows"] if r[2] == label)

    def actions(self):
        return [(a["action"], a["details"]) for a in self.store.read_audit()]


@pytest.fixture
def rig(tmp_path):
    return Rig(tmp_path)


def test_settings_rows_come_back_with_a_header_and_no_engine_rows(rig):
    status, out = rig.get("/api/settings")
    assert status == 200 and out["rows"][0][:3] == ["section", "subsection", "label"]
    assert {r[0] for r in out["rows"][1:]}.isdisjoint({"Rebalancing", "Asset Class Assumptions", "Plan Settings"})


def test_saving_a_setting_is_visible_to_the_planner_reader_and_audited(rig):
    assert rig.row("max_build_seconds")[3] == "1800"
    rows = [list(rig.row("max_build_seconds"))]
    rows[0][3] = "777"
    status, out = rig.post("/api/settings", {"rows": rows})
    assert status == 200 and out["changed"] == 1
    # the planner reads the same app.db through src.system_config, with no Admin app object
    assert system_config.system_setting(system_config.load_system_config(rig.settings.app_db), "Runtime", "max_build_seconds") == "777"
    assert ("settings.save", "1 setting(s) changed") in rig.actions()


def test_saving_raw_csv_text_works(rig):
    csv_text = "System Configuration,Runtime,max_build_seconds,900,seconds,\n"
    status, out = rig.post("/api/settings", {"csv_content": csv_text})
    assert status == 200 and rig.row("max_build_seconds")[3] == "900"


@pytest.mark.parametrize("section", ["Rebalancing", "Asset Class Assumptions", "Asset Correlations", "Annuity Calibration", "Plan Settings"])
def test_engine_rows_are_refused_with_400_and_nothing_is_saved(rig, section):
    before = rig.get("/api/settings")[1]["rows"]
    status, out = rig.post("/api/settings", {"rows": [[section, "x", "y", "1", "", ""]]})
    assert status == 400 and section in out["engine_sections"]
    assert rig.get("/api/settings")[1]["rows"] == before and rig.actions() == []


def test_secret_rows_go_to_the_secret_store_and_are_never_returned_or_audited(rig, monkeypatch):
    stored = {}
    import src.secrets_store as secrets_store

    monkeypatch.setattr(secrets_store, "set_secret", lambda name, value: stored.__setitem__(name, value))
    row = list(rig.row("fmp_api_key"))
    row[3] = "sk-test-123456"
    status, out = rig.post("/api/settings", {"rows": [row]})
    assert status == 200 and out["secrets_stored"] == ["fmp_api_key"]
    assert stored == {"fmp_api_key": "sk-test-123456"}
    assert rig.row("fmp_api_key")[3] == ""
    assert "sk-test" not in json.dumps(out) and "sk-test" not in json.dumps(rig.actions())


def test_system_status_reports_each_app_and_the_planner_address(rig, monkeypatch):
    import admin_app.settings as settings_module

    monkeypatch.setattr(settings_module, "ping", lambda port, timeout=0.6: port == 5050)
    status, out = rig.get("/api/system/status")
    assert status == 200 and out["port"] == 5050 and out["apps"] == {"planner": True, "insights_local": False, "insights_remote": False}


def test_planner_shutdown_when_the_planner_is_not_running_is_a_502_with_a_reason(rig, monkeypatch):
    import admin_app.settings as settings_module

    monkeypatch.setattr(settings_module, "ping", lambda port, timeout=0.6: False)
    status, out = rig.post("/api/system/planner-shutdown", {})
    assert status == 502 and "not answering" in out["error"]
    assert ("system.planner-shutdown", "failed") in rig.actions()


def test_tax_law_dashboard_and_cache_clear_answer(rig):
    status, out = rig.get("/api/tax-law-dashboard")
    assert status == 200 and isinstance(out["rows"], list)
    status, out = rig.post("/api/system/clear-webview-cache", {})
    assert status == 200 and out["success"] is True


def test_unknown_pricing_test_job_is_404(rig):
    assert rig.get("/api/settings/pricing-test/status/nope")[0] == 404
    assert rig.post("/api/settings/pricing-test/start", {"symbol": ""})[0] == 400


def test_system_routes_do_not_exist_without_a_settings_service(tmp_path):
    bare = create_app(IdentityStore(tmp_path / "i.db", scrypt_n=2**4)).test_client()
    assert bare.get("/api/settings", headers=HEADERS).status_code == 404
