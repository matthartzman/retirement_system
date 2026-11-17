"""Multi-user Phase 4 in one worker process: the Monarch upload route, the disables, and per-user secrets.

In-process against the session app with remote mode switched on through the environment, like
``test_remote_mode_contract.py``. The two-process proof (one user's data and the shared key invisible to the
other) is in ``test_multi_user_isolation_integration.py``.
"""
from __future__ import annotations

import base64
from pathlib import Path

import keyring
import sys

import pytest
from keyring.backend import KeyringBackend

from src import market_data, monarch_autoimport_job, monarch_autoupdate, platform_runtime, remote_mode
from src import secrets_store
from src.gateway import launchers, server as gateway_server
from src.gateway.supervisor import FORBIDDEN_ENV, MAPPING_SEED_RELPATH, SupervisorConfig, check_mapping_csv
from src.server import app_core, create_app, monarch_routes
from src import monarch_upload

TOKEN = "test-worker-token-0123456789"
TX = "Date,Merchant,Category,Account,Amount,Id\n2026-10-01,Grocer,Groceries,Joint Checking (...4821),-5.00,tx-1\n"


@pytest.fixture(autouse=True)
def _live_workspace_constant(monkeypatch):
    from src.server import base_routes, plan_routes, workbook_routes

    live = platform_runtime.workspace_root()
    for module in (app_core, base_routes, plan_routes, workbook_routes):
        monkeypatch.setattr(module, "WORKSPACE_ROOT", live, raising=False)


@pytest.fixture
def remote(monkeypatch):
    monkeypatch.setenv(remote_mode.REMOTE_MODE_ENV, "1")
    monkeypatch.setenv(remote_mode.TOKEN_ENV, TOKEN)
    return create_app().test_client()


@pytest.fixture
def own_workspace(tmp_path, monkeypatch):
    """Point the upload route at a throwaway workspace so the session plan is never changed."""
    base = tmp_path / "ws"
    (base / "input").mkdir(parents=True)
    monkeypatch.setattr(monarch_routes, "_ytd_input_root", lambda: base / "input")
    return base


def _post(client, path, body):
    return client.post(path, json=body, headers={"X-API-Token": TOKEN})


def _body(text: str, **extra) -> dict:
    return {"kind": "transactions", "filename": "t.csv", "content_base64": base64.b64encode(text.encode()).decode(),
            **extra}


# ---------------------------------------------------------------- item 1: the upload route

def test_upload_route_is_on_the_allow_list_and_imports(remote, own_workspace):
    resp = _post(remote, "/api/monarch/upload", _body(TX))
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["success"] and body["added"] == 1 and body["kind"] == "transactions"
    assert str(own_workspace) not in resp.get_data(as_text=True)


def test_upload_route_refuses_bad_input_with_400(remote, own_workspace):
    resp = _post(remote, "/api/monarch/upload", {"kind": "transactions", "content_base64": "%%%"})
    assert resp.status_code == 400 and "base64" in resp.get_json()["error"]


def test_upload_route_needs_the_worker_token(remote, own_workspace):
    assert remote.post("/api/monarch/upload", json=_body(TX)).status_code == 401


def test_upload_route_audits_counts_not_names(remote, own_workspace, monkeypatch):
    seen = []
    monkeypatch.setattr(monarch_routes, "_audit", lambda event, details=None: seen.append((event, details)))
    _post(remote, "/api/monarch/upload", _body(TX))
    assert seen == [("monarch_uploaded", {"kind": "transactions", "rows": 1, "accounts": 1})]


# ---------------------------------------------------------------- item 5: disables

@pytest.mark.parametrize("method,path", [
    ("GET", "/api/plan/monarch-autoupdate"),
    ("POST", "/api/plan/monarch-autoupdate/config"),  # registers the machine-wide scheduled task
    ("POST", "/api/plan/monarch-autoupdate/run"),  # runs the extractor's mark-delivered launcher
    ("POST", "/api/secrets"),  # the secret-store UI
])
def test_monarch_scheduler_extractor_and_secret_routes_are_refused(remote, method, path, monkeypatch):
    called = []
    monkeypatch.setattr(monarch_autoupdate, "register_scheduled_task", lambda *a, **k: called.append(a))
    monkeypatch.setattr(secrets_store, "set_secret", lambda *a, **k: called.append(a))
    resp = remote.open(path, method=method, json={"name": "fmp_api_key", "value": "x", "enabled": True},
                       headers={"X-API-Token": TOKEN})
    assert resp.status_code == 403, (path, resp.status_code)
    assert called == []


def test_scheduled_task_registration_refuses_in_remote_mode_even_if_called(monkeypatch, tmp_path):
    monkeypatch.setenv(remote_mode.REMOTE_MODE_ENV, "1")
    ran = []
    monkeypatch.setattr(monarch_autoupdate, "_run_registration_script", lambda *a: ran.append(a) or {})
    out = monarch_autoupdate.register_scheduled_task(tmp_path, True)
    assert out["attempted"] is False and ran == []


def test_extractor_import_job_refuses_in_remote_mode_even_if_called(monkeypatch, tmp_path):
    monkeypatch.setenv(remote_mode.REMOTE_MODE_ENV, "1")
    monkeypatch.setattr(monarch_autoimport_job, "_mark_runs_delivered", lambda *a: pytest.fail("launcher ran"))
    out = monarch_autoimport_job.run(tmp_path, force=True)
    assert out["success"] is False and out["skip_reason"] == "remote_mode"


# ---------------------------------------------------------------- item 3: per-user secrets

class _MemoryKeyring(KeyringBackend):
    priority = 1

    def __init__(self):
        super().__init__()
        self.data = {}

    def set_password(self, service, username, password):
        self.data[(service, username)] = password

    def get_password(self, service, username):
        return self.data.get((service, username))

    def delete_password(self, service, username):
        self.data.pop((service, username), None)


def _winvault_like():
    cls = type("WinVaultKeyring", (_MemoryKeyring,), {"__module__": "keyring.backends.Windows"})
    return cls()


@pytest.fixture
def fake_keyring(tmp_path, monkeypatch):
    from src.app_state import APP_DB_ENV

    monkeypatch.setenv("RETIREMENT_SYSTEM_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv(APP_DB_ENV, str(tmp_path / "app.db"))
    prev = keyring.get_keyring()
    yield lambda backend: keyring.set_keyring(backend)
    keyring.set_keyring(prev)


def test_desktop_mode_is_unchanged(fake_keyring, monkeypatch):
    monkeypatch.delenv(remote_mode.REMOTE_MODE_ENV, raising=False)
    fake_keyring(_MemoryKeyring())
    secrets_store.set_secret("k", "v")
    assert secrets_store.get_secret("k") == "v"


def test_a_same_account_worker_never_uses_the_shared_credential_store(fake_keyring, monkeypatch):
    monkeypatch.setenv(remote_mode.REMOTE_MODE_ENV, "1")
    monkeypatch.delenv(secrets_store.DEDICATED_ACCOUNT_ENV, raising=False)
    backend = _winvault_like()
    fake_keyring(backend)
    with pytest.raises(secrets_store.SecretStoreUnavailable, match="own"):
        secrets_store.set_secret("k", "v")
    assert backend.data == {}
    assert secrets_store.encryption_status()["store_active"] is False


_windows_only = pytest.mark.skipif(sys.platform != "win32", reason="machine-scope DPAPI is Windows only")


@_windows_only
def test_a_dedicated_worker_keeps_secrets_under_machine_dpapi_not_credential_manager(fake_keyring, monkeypatch):
    """User-scope DPAPI (Credential Manager) did not reliably survive the account's password rotation in the elevated
    runs, so a dedicated worker uses machine-scope DPAPI in its own app.db and never touches keyring."""
    monkeypatch.setenv(remote_mode.REMOTE_MODE_ENV, "1")
    monkeypatch.setenv(secrets_store.DEDICATED_ACCOUNT_ENV, "1")
    vault = _winvault_like()
    fake_keyring(vault)
    secrets_store.set_secret("k", "s3cret-value")
    assert secrets_store.get_secret("k") == "s3cret-value"
    assert vault.data == {}, "a dedicated worker must not write to Windows Credential Manager"
    assert secrets_store.list_secrets() == ["k"]
    status = secrets_store.encryption_status()
    assert status["store_active"] is True and status["encrypted"] is True and status["mode"] == "machine-dpapi"
    secrets_store.delete_secret("k")
    assert secrets_store.get_secret("k") == "" and secrets_store.list_secrets() == []


@_windows_only
def test_machine_dpapi_secrets_are_never_stored_in_plain_text_and_are_bound_to_their_name(fake_keyring, monkeypatch):
    import base64
    from src import dpapi_machine

    monkeypatch.setenv(remote_mode.REMOTE_MODE_ENV, "1")
    monkeypatch.setenv(secrets_store.DEDICATED_ACCOUNT_ENV, "1")
    fake_keyring(_winvault_like())
    secrets_store.set_secret("alpha", "plain-text-marker-123")
    raw = secrets_store._machine_blobs()["alpha"]
    assert "plain-text-marker-123" not in raw
    blob = base64.b64decode(raw)
    assert b"plain-text-marker-123" not in blob
    with pytest.raises(dpapi_machine.DpapiUnavailable):  # another name's entropy cannot open this blob
        dpapi_machine.unprotect(blob, secrets_store._entropy("beta"))
    assert dpapi_machine.unprotect(blob, secrets_store._entropy("alpha")) == b"plain-text-marker-123"


def test_a_dedicated_worker_without_dpapi_gets_a_clear_refusal(fake_keyring, monkeypatch):
    from src import dpapi_machine

    monkeypatch.setenv(remote_mode.REMOTE_MODE_ENV, "1")
    monkeypatch.setenv(secrets_store.DEDICATED_ACCOUNT_ENV, "1")

    def boom(*args, **kwargs):
        raise dpapi_machine.DpapiUnavailable("CryptProtectData failed (Windows error 5)")

    monkeypatch.setattr(dpapi_machine, "protect", boom)
    with pytest.raises(secrets_store.SecretStoreUnavailable, match="failed to save"):
        secrets_store.set_secret("k", "v")
    assert secrets_store.encryption_status()["store_active"] is False


def test_price_lookup_treats_a_refused_store_as_no_key(fake_keyring, monkeypatch):
    monkeypatch.setenv(remote_mode.REMOTE_MODE_ENV, "1")
    monkeypatch.delenv(secrets_store.DEDICATED_ACCOUNT_ENV, raising=False)
    for name in ("RETIREMENT_SYSTEM_FMP_API_KEY", "FMP_API_KEY", "FINANCIAL_MODELING_PREP_API_KEY",
                 "RETIREMENT_SYSTEM_ALPHA_VANTAGE_API_KEY", "ALPHA_VANTAGE_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    fake_keyring(_winvault_like())
    svc = market_data.MarketDataProvider.__new__(market_data.MarketDataProvider)
    svc.fmp_api_key = svc.alpha_vantage_api_key = None
    svc.secret_store_warning = ""
    svc.refresh_api_keys()
    assert not svc.fmp_api_key and "own Windows account" in svc.secret_store_warning


def test_only_the_per_account_launcher_marks_a_dedicated_worker():
    assert launchers.DEDICATED_ACCOUNT_ENV == secrets_store.DEDICATED_ACCOUNT_ENV
    assert secrets_store.DEDICATED_ACCOUNT_ENV in FORBIDDEN_ENV
    with pytest.raises(ValueError, match="may not be passed"):
        SupervisorConfig(data_root=Path("unused"), extra_env={secrets_store.DEDICATED_ACCOUNT_ENV: "1"})


# ---------------------------------------------------------------- item 4: the shared provider key

def test_key_fingerprints_are_hidden_in_remote_mode(monkeypatch):
    monkeypatch.delenv(remote_mode.REMOTE_MODE_ENV, raising=False)
    assert market_data._secret_fingerprint("shared-key-value")
    monkeypatch.setenv(remote_mode.REMOTE_MODE_ENV, "1")
    assert market_data._secret_fingerprint("shared-key-value") is None


@pytest.mark.parametrize("name", sorted(gateway_server.PROVIDER_KEY_NAMES))
def test_provider_keys_are_refused_on_the_worker_env_command_line(name):
    import argparse

    with pytest.raises(argparse.ArgumentTypeError, match="--pass-env"):
        gateway_server._env_pair(f"{name}=secret")
    assert gateway_server._env_pair("RETIREMENT_SYSTEM_FROZEN_TODAY=2026-01-01")


def test_gateway_and_worker_agree_on_the_provider_key_names():
    assert gateway_server.PROVIDER_KEY_NAMES == remote_mode._PROVIDER_KEYS


# ---------------------------------------------------------------- item 2: the mapping seed copy

def test_mapping_csv_is_checked_and_copied_into_a_new_workspace(tmp_path):
    from src.gateway.launchers import SameAccountLauncher
    from src.gateway.supervisor import Supervisor

    good = tmp_path / "map.csv"
    good.write_text("Monarch,App Location,App Field,Status,Primary Source\nVenmo,,IGNORE,Active,App\n", encoding="utf-8")
    bad = tmp_path / "bad.csv"
    bad.write_text("Name,Value\n", encoding="utf-8")
    with pytest.raises(ValueError, match="App Field"):
        check_mapping_csv(bad)
    with pytest.raises(ValueError, match="not a file"):
        check_mapping_csv(tmp_path / "missing.csv")
    sup = Supervisor(SupervisorConfig(data_root=tmp_path / "data", monarch_mapping_csv=good), SameAccountLauncher())
    sup.user_created(7)
    copied = sup.workspace(7) / MAPPING_SEED_RELPATH
    assert copied.read_bytes() == good.read_bytes()
    assert MAPPING_SEED_RELPATH == monarch_upload.MAPPING_SEED_RELPATH
