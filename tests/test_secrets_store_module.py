"""Unit tests for src/secrets_store.py (WP8.2: OS credential store via keyring).

Every test runs against an in-memory fake keyring backend; the real credential store is never
touched. The names index lives in an ``app.db`` redirected into ``tmp_path``.
"""
from __future__ import annotations

import json

import keyring
import pytest
from keyring.backend import KeyringBackend
from keyring.backends import fail
from keyring.errors import PasswordDeleteError

import src.secrets_store as secrets_store
from src.app_state import APP_DB_ENV, open_app_store
from src.secrets_store import SecretStoreUnavailable


class MemoryKeyring(KeyringBackend):
    priority = 1

    def __init__(self):
        super().__init__()
        self.data: dict[tuple[str, str], str] = {}

    def set_password(self, service, username, password):
        self.data[(service, username)] = password

    def get_password(self, service, username):
        return self.data.get((service, username))

    def delete_password(self, service, username):
        if (service, username) not in self.data:
            raise PasswordDeleteError("not found")
        del self.data[(service, username)]


@pytest.fixture(autouse=True)
def fake(tmp_path, monkeypatch):
    monkeypatch.setenv(APP_DB_ENV, str(tmp_path / "app.db"))
    monkeypatch.setenv("RETIREMENT_SYSTEM_WORKSPACE_ROOT", str(tmp_path / "ws"))
    prev = keyring.get_keyring()
    backend = MemoryKeyring()
    keyring.set_keyring(backend)
    yield backend
    keyring.set_keyring(prev)


def _no_backend():
    keyring.set_keyring(fail.Keyring())


def test_set_get_round_trip_uses_service_and_name(fake):
    secrets_store.set_secret("api_key", "sk-1")
    assert secrets_store.get_secret("api_key") == "sk-1"
    assert fake.data == {(secrets_store.SERVICE_NAME, "api_key"): "sk-1"}


def test_values_coerced_to_str_and_missing_is_empty():
    secrets_store.set_secret(123, 456)
    assert secrets_store.get_secret("123") == "456"
    assert secrets_store.get_secret("never") == ""


def test_delete_and_missing_delete_are_quiet():
    secrets_store.set_secret("a", "1")
    secrets_store.delete_secret("a")
    assert secrets_store.get_secret("a") == ""
    secrets_store.delete_secret("a")
    assert secrets_store.list_secrets() == []


def test_names_index_lives_in_app_db_and_holds_no_values(tmp_path):
    secrets_store.set_secret("zeta", "v-zeta")
    secrets_store.set_secret("alpha", "v-alpha")
    assert secrets_store.list_secrets() == ["alpha", "zeta"]
    store = open_app_store()
    try:
        assert store.get_setting("secrets.names") == ["alpha", "zeta"]
    finally:
        store.close()
    assert b"v-zeta" not in (tmp_path / "app.db").read_bytes()
    secrets_store.delete_secret("alpha")
    assert secrets_store.list_secrets() == ["zeta"]


def test_no_plaintext_file_is_written(tmp_path):
    secrets_store.set_secret("k", "super-secret-value")
    assert not secrets_store.legacy_secrets_path().exists()
    for f in tmp_path.rglob("*"):
        if f.is_file():
            assert b"super-secret-value" not in f.read_bytes(), f


@pytest.mark.parametrize("call", [
    lambda: secrets_store.set_secret("k", "v"),
    lambda: secrets_store.get_secret("k"),
    lambda: secrets_store.delete_secret("k"),
])
def test_unavailable_backend_raises_clearly_and_writes_nothing(tmp_path, call):
    _no_backend()
    with pytest.raises(SecretStoreUnavailable, match="never saved to a plain file"):
        call()
    assert not secrets_store.legacy_secrets_path().exists()


def test_no_keyring_error_from_backend_is_unavailable(fake, monkeypatch):
    from keyring.errors import NoKeyringError

    def boom(*a):
        raise NoKeyringError("none")
    monkeypatch.setattr(fake, "get_password", boom)
    with pytest.raises(SecretStoreUnavailable):
        secrets_store.get_secret("k")


def test_failed_set_does_not_touch_the_index():
    _no_backend()
    with pytest.raises(SecretStoreUnavailable):
        secrets_store.set_secret("k", "v")
    keyring.set_keyring(MemoryKeyring())
    assert secrets_store.list_secrets() == []


def test_encryption_status_never_raises_and_has_no_configured_key():
    assert secrets_store.encryption_status("ws", db_path="x") == {
        "mode": "os-credential-store", "encrypted": True, "store_active": True, "backend": "MemoryKeyring"}
    _no_backend()
    st = secrets_store.encryption_status()
    assert st["encrypted"] is False and st["store_active"] is False and "plain file" in st["error"]
    assert "configured" not in st  # SEC-5: must not shadow a caller's own "configured" key


def test_require_secure_master_key_always_true():
    assert secrets_store.require_secure_master_key("anything", flag=False) is True


def test_db_path_and_workspace_id_are_accepted_but_unused(tmp_path):
    other = tmp_path / "elsewhere.db"
    secrets_store.set_secret("k", "v", workspace_id="a", db_path=other)
    assert secrets_store.get_secret("k", workspace_id="b") == "v"
    assert secrets_store.list_secrets(db_path=other) == ["k"]
    assert not other.exists()


def _write_legacy(data):
    p = secrets_store.legacy_secrets_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def test_legacy_migration_moves_verifies_and_keeps_file_by_default(fake):
    p = _write_legacy({"fmp_api_key": "F", "alpha_vantage_api_key": "A"})
    r = secrets_store.migrate_legacy_secrets_file()
    assert r["verified"] and not r["deleted"] and sorted(r["migrated"]) == ["alpha_vantage_api_key", "fmp_api_key"]
    assert p.exists()  # never auto-deleted
    assert secrets_store.get_secret("fmp_api_key") == "F"
    assert secrets_store.list_secrets() == ["alpha_vantage_api_key", "fmp_api_key"]
    assert "F" not in json.dumps({k: v for k, v in r.items()})


def test_legacy_migration_deletes_only_when_asked_and_verified(fake):
    p = _write_legacy({"k": "v"})
    r = secrets_store.migrate_legacy_secrets_file(delete_file=True)
    assert r["verified"] and r["deleted"] and not p.exists()


def test_legacy_migration_keeps_file_when_readback_fails(fake, monkeypatch):
    p = _write_legacy({"good": "1", "bad": "2"})
    orig = fake.get_password
    monkeypatch.setattr(fake, "get_password", lambda s, u: "WRONG" if u == "bad" else orig(s, u))
    r = secrets_store.migrate_legacy_secrets_file(delete_file=True)
    assert r["failed"] == ["bad"] and not r["verified"] and not r["deleted"] and p.exists()


def test_legacy_migration_without_backend_raises_and_keeps_file():
    p = _write_legacy({"k": "v"})
    _no_backend()
    with pytest.raises(SecretStoreUnavailable):
        secrets_store.migrate_legacy_secrets_file(delete_file=True)
    assert p.exists()


def test_legacy_migration_missing_or_corrupt_file(tmp_path):
    assert secrets_store.migrate_legacy_secrets_file()["found"] is False
    p = secrets_store.legacy_secrets_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{not json", encoding="utf-8")
    r = secrets_store.migrate_legacy_secrets_file(delete_file=True)
    assert not r["verified"] and not r["deleted"] and p.exists() and "unreadable" in r["error"]


def test_pricing_reader_treats_unavailable_as_no_key_with_warning(monkeypatch):
    from src.market_data import MarketDataProvider
    for n in ("RETIREMENT_SYSTEM_FMP_API_KEY", "FMP_API_KEY", "FINANCIAL_MODELING_PREP_API_KEY",
              "RETIREMENT_SYSTEM_ALPHA_VANTAGE_API_KEY", "ALPHA_VANTAGE_API_KEY"):
        monkeypatch.delenv(n, raising=False)
    _no_backend()
    md = MarketDataProvider()
    assert not md.fmp_api_key and "unavailable" in md.secret_store_warning
    assert "secret_store_warning" in md.api_key_sources()
    monkeypatch.setenv("FMP_API_KEY", "env-key")  # env override still works with no store
    md.fmp_api_key = ""
    md.refresh_api_keys()
    assert md.fmp_api_key == "env-key"
