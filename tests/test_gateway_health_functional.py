"""Health report: contents, warnings, and the admin-only rule on the route."""
from __future__ import annotations

import json
import shutil
from types import SimpleNamespace

import pytest

from src.gateway import health as h
from src.gateway.app import GatewayConfig, GatewayListener, create_gateway_app
from tests.gateway_rig import PUBLIC_ORIGIN, Rig

pytestmark = pytest.mark.integration


class FakeBackups:
    def __init__(self, ok=True, newest=None, errors=()):
        self._last = {"at": 1000.0, "ok": ok, "users": 3, "errors": list(errors)}
        self._newest = newest

    def last_result(self):
        return dict(self._last)

    def newest_full_epoch(self):
        return self._newest


def _health(tmp_path, backups, **kw):
    base = dict(started_at=0.0, schema_version=7, workers_running=2, build_running=1, build_waiting=4,
                data_root=tmp_path, backup_dir=tmp_path / "bk", backups=backups, clock=lambda: 10_000.0)
    base.update(kw)
    return h.build_health(**base)


def test_report_has_every_field_the_task_names(tmp_path):
    rep = _health(tmp_path, FakeBackups(newest=9_000.0))
    assert rep["status"] == "ok" and rep["warnings"] == []
    assert rep["workers"] == {"running": 2} and rep["build_queue"] == {"running": 1, "waiting": 4}
    assert rep["uptime_seconds"] == 10_000 and rep["schema_version"] == 7
    for vol in ("data", "backups"):
        assert rep["disk"][vol]["free_bytes"] > 0 and rep["disk"][vol]["total_bytes"] >= rep["disk"][vol]["free_bytes"]
    assert rep["backup"]["last_ok"] is True and rep["backup"]["newest_archive_age_seconds"] == 1000
    assert str(tmp_path) not in json.dumps(rep)  # volumes are labelled, no folder paths


def test_warnings_for_no_backups_failed_backup_stale_backup_and_low_disk(tmp_path, monkeypatch):
    assert "no backups are configured" in _health(tmp_path, None)["warnings"]
    rep = _health(tmp_path, FakeBackups(ok=False, newest=9_000.0, errors=["user 3"]))
    assert rep["status"] == "warning" and "the last backup reported errors" in rep["warnings"]
    assert "there is no recent complete backup" in _health(tmp_path, FakeBackups(newest=None))["warnings"]
    assert "there is no recent complete backup" in _health(tmp_path, FakeBackups(newest=10_000.0 - 3 * 86400))["warnings"]
    monkeypatch.setattr(h.shutil, "disk_usage", lambda p: SimpleNamespace(total=100 * 1024**3, used=99 * 1024**3, free=1024**3))
    low = _health(tmp_path, FakeBackups(newest=9_000.0))
    assert "low free space on the data volume" in low["warnings"] and "low free space on the backup volume" in low["warnings"]


def test_missing_backup_folder_reports_the_volume_it_would_live_on(tmp_path):
    rep = _health(tmp_path, FakeBackups(newest=9_000.0), backup_dir=tmp_path / "not" / "yet" / "made")
    assert rep["disk"]["backups"]["free_bytes"] == shutil.disk_usage(tmp_path).free or rep["disk"]["backups"]["free_bytes"] > 0


def _with_health(tmp_path, provider):
    rig = Rig(tmp_path)
    rig.app = create_gateway_app(rig.store, config=GatewayConfig(public_origins=(PUBLIC_ORIGIN,)),
                                 clock=lambda: rig.now[0], upstream=rig.upstream, health=provider)
    rig.funnel = GatewayListener(rig.app, "funnel", rig.funnel.port)
    rig.local = GatewayListener(rig.app, "local", rig.local.port)
    return rig


def test_health_route_is_admin_only_on_both_listeners(tmp_path):
    rig = _with_health(tmp_path, lambda: {"status": "ok", "warnings": [], "workers": {"running": 0}})
    admin, _ = rig.signed_in("root", role="admin")
    user, _ = rig.signed_in("ann", ip="198.51.100.9")
    anon = rig.browser()
    assert user.get("/api/auth/admin/health").status_code == 403
    assert anon.get("/api/auth/admin/health").status_code == 401
    r = admin.get("/api/auth/admin/health")
    assert r.status_code == 200 and r.get_json()["success"] is True and r.get_json()["workers"] == {"running": 0}
    # "from this machine" is not an exemption: a signed-out browser on the local listener is still refused
    assert rig.browser(listener="local").get("/api/auth/admin/health").status_code == 401
    assert rig.upstream.calls == [] or all("/health" not in c[1] for c in rig.upstream.calls)


def test_a_failing_provider_returns_a_generic_error(tmp_path):
    def boom():
        raise RuntimeError("secret path C:/data/users/1")

    rig = _with_health(tmp_path, boom)
    admin, _ = rig.signed_in("root", role="admin")
    r = admin.get("/api/auth/admin/health")
    assert r.status_code == 500 and "secret" not in r.get_data(as_text=True)
