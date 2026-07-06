"""Unit tests for src/secrets_store.py.

Covers every function in the module: `_load`, `_save`, `encryption_status`,
`require_secure_master_key`, `set_secret`, `get_secret`, `delete_secret`,
and `list_secrets`.

Important behavioral note (documented, not "fixed"): `set_secret`,
`get_secret`, `delete_secret`, and `list_secrets` all accept a `db_path`
keyword argument, but none of them actually use it -- internally they call
`_load()` / `_save(data)` with NO arguments, so those calls always fall
back to `_load`/`_save`'s own default parameter (`DEFAULT_SECRETS`),
completely ignoring whatever `db_path` the caller supplied. `db_path` is
effectively a no-op placeholder today (likely there for a future/SaaS
signature match). Tests below cover this explicitly.

To keep tests from ever touching the real `local_state/secrets.local.json`
file, an autouse fixture redirects `_load`/`_save`'s default `path`
parameter (via their `__defaults__`) to a file under `tmp_path`, and also
patches `DEFAULT_SECRETS` for good measure. Since default-argument values
are read from the function object at call time, rebinding `__defaults__`
is sufficient to redirect every call that relies on the default.
"""

from __future__ import annotations

import json

import pytest

import src.secrets_store as secrets_store

# Captured at import time, before any per-test monkeypatching occurs, so we
# can assert on the module's real production path resolution without ever
# touching the live (test-patched) attribute or reloading the module.
_ORIGINAL_DEFAULT_SECRETS = secrets_store.DEFAULT_SECRETS


@pytest.fixture(autouse=True)
def _redirect_default_secrets_path(tmp_path, monkeypatch):
    """Redirect the module's default secrets file into tmp_path.

    This must patch the *default arguments* of `_load`/`_save` (not just
    the `DEFAULT_SECRETS` module attribute) because Python binds default
    parameter values once, at function-definition time. Simply reassigning
    `secrets_store.DEFAULT_SECRETS` after import would have no effect on
    calls like `_load()` that rely on the pre-bound default.
    """
    fake_path = tmp_path / "secrets.local.json"
    monkeypatch.setattr(secrets_store._load, "__defaults__", (fake_path,))
    monkeypatch.setattr(secrets_store._save, "__defaults__", (fake_path,))
    monkeypatch.setattr(secrets_store, "DEFAULT_SECRETS", fake_path)
    return fake_path


# ---------------------------------------------------------------------------
# DEFAULT_SECRETS path resolution (sanity check only, no I/O)
# ---------------------------------------------------------------------------

def test_default_secrets_points_under_local_state():
    # Uses the path captured at import time (before any per-test patching)
    # so this reflects the real production wiring, not the tmp_path redirect
    # that the autouse fixture applies for the rest of this test file.
    assert _ORIGINAL_DEFAULT_SECRETS.parent.name == "local_state"
    assert _ORIGINAL_DEFAULT_SECRETS.name == "secrets.local.json"


# ---------------------------------------------------------------------------
# _load
# ---------------------------------------------------------------------------

def test_load_missing_file_returns_empty_dict(tmp_path):
    missing = tmp_path / "does_not_exist.json"
    assert secrets_store._load(missing) == {}


def test_load_missing_file_uses_default_path(_redirect_default_secrets_path):
    # No explicit path -- the (patched) default file doesn't exist yet.
    assert not _redirect_default_secrets_path.exists()
    assert secrets_store._load() == {}


def test_load_valid_json_returns_dict(tmp_path):
    p = tmp_path / "secrets.json"
    p.write_text(json.dumps({"a": "1", "b": "2"}), encoding="utf-8")
    assert secrets_store._load(p) == {"a": "1", "b": "2"}


def test_load_corrupt_json_returns_empty_dict_not_raise(tmp_path):
    p = tmp_path / "corrupt.json"
    p.write_text("{not valid json::", encoding="utf-8")
    assert secrets_store._load(p) == {}


def test_load_accepts_string_path(tmp_path):
    p = tmp_path / "secrets.json"
    p.write_text(json.dumps({"x": "y"}), encoding="utf-8")
    assert secrets_store._load(str(p)) == {"x": "y"}


# ---------------------------------------------------------------------------
# _save
# ---------------------------------------------------------------------------

def test_save_writes_readable_json(tmp_path):
    p = tmp_path / "out.json"
    secrets_store._save({"k": "v"}, p)
    assert json.loads(p.read_text(encoding="utf-8")) == {"k": "v"}


def test_save_creates_parent_directories(tmp_path):
    p = tmp_path / "nested" / "dir" / "secrets.json"
    assert not p.parent.exists()
    secrets_store._save({"k": "v"}, p)
    assert p.exists()


def test_save_then_load_round_trip(tmp_path):
    p = tmp_path / "secrets.json"
    secrets_store._save({"alpha": "1", "beta": "2"}, p)
    assert secrets_store._load(p) == {"alpha": "1", "beta": "2"}


def test_save_overwrites_existing_file(tmp_path):
    p = tmp_path / "secrets.json"
    secrets_store._save({"old": "1"}, p)
    secrets_store._save({"new": "2"}, p)
    assert secrets_store._load(p) == {"new": "2"}


def test_save_uses_default_path_when_omitted(_redirect_default_secrets_path):
    secrets_store._save({"k": "v"})
    assert _redirect_default_secrets_path.exists()
    assert secrets_store._load() == {"k": "v"}


# ---------------------------------------------------------------------------
# encryption_status
# ---------------------------------------------------------------------------

def test_encryption_status_returns_local_only_stub():
    # Not real encryption -- this is a stub for a SaaS-mode signature that
    # is unused in the local-only deployment (per module docstring).
    assert secrets_store.encryption_status() == {
        "mode": "local-only",
        "encrypted": False,
        "configured": True,
    }


def test_encryption_status_ignores_any_arguments():
    # Signature is *args, **kwargs -- extra arguments are accepted but
    # have no effect on the returned value.
    assert secrets_store.encryption_status("workspace-1", db_path="/whatever") == {
        "mode": "local-only",
        "encrypted": False,
        "configured": True,
    }


# ---------------------------------------------------------------------------
# require_secure_master_key
# ---------------------------------------------------------------------------

def test_require_secure_master_key_always_true():
    assert secrets_store.require_secure_master_key() is True


def test_require_secure_master_key_ignores_any_arguments():
    assert secrets_store.require_secure_master_key("anything", flag=False) is True


# ---------------------------------------------------------------------------
# set_secret / get_secret / delete_secret / list_secrets
# ---------------------------------------------------------------------------

def test_set_then_get_round_trip():
    secrets_store.set_secret("api_key", "sk-12345")
    assert secrets_store.get_secret("api_key") == "sk-12345"


def test_set_secret_coerces_name_and_value_to_str():
    secrets_store.set_secret(123, 456)
    assert secrets_store.get_secret("123") == "456"


def test_get_secret_never_set_returns_empty_string():
    assert secrets_store.get_secret("never_set_this_name") == ""


def test_get_secret_on_first_call_with_no_file_does_not_crash(_redirect_default_secrets_path):
    assert not _redirect_default_secrets_path.exists()
    assert secrets_store.get_secret("anything") == ""


def test_delete_secret_removes_value():
    secrets_store.set_secret("temp_key", "temp_value")
    assert secrets_store.get_secret("temp_key") == "temp_value"
    secrets_store.delete_secret("temp_key")
    assert secrets_store.get_secret("temp_key") == ""


def test_delete_secret_missing_name_does_not_raise():
    # Deleting a name that was never set should be a harmless no-op.
    secrets_store.delete_secret("was_never_there")
    assert secrets_store.get_secret("was_never_there") == ""


def test_delete_secret_on_first_call_with_no_file_does_not_crash(_redirect_default_secrets_path):
    assert not _redirect_default_secrets_path.exists()
    secrets_store.delete_secret("anything")  # should not raise


def test_list_secrets_reflects_current_state():
    assert secrets_store.list_secrets() == []
    secrets_store.set_secret("zeta", "1")
    secrets_store.set_secret("alpha", "2")
    assert secrets_store.list_secrets() == ["alpha", "zeta"]


def test_list_secrets_after_delete():
    secrets_store.set_secret("a", "1")
    secrets_store.set_secret("b", "2")
    secrets_store.delete_secret("a")
    assert secrets_store.list_secrets() == ["b"]


def test_list_secrets_on_first_call_with_no_file_returns_empty_list(_redirect_default_secrets_path):
    assert not _redirect_default_secrets_path.exists()
    assert secrets_store.list_secrets() == []


def test_multiple_secrets_independent_round_trip():
    secrets_store.set_secret("one", "1")
    secrets_store.set_secret("two", "2")
    secrets_store.set_secret("three", "3")
    assert secrets_store.get_secret("one") == "1"
    assert secrets_store.get_secret("two") == "2"
    assert secrets_store.get_secret("three") == "3"
    assert secrets_store.list_secrets() == ["one", "three", "two"]


# ---------------------------------------------------------------------------
# db_path / workspace_id are accepted but currently have no effect (no-op)
# ---------------------------------------------------------------------------

def test_set_secret_db_path_argument_is_ignored(tmp_path, _redirect_default_secrets_path):
    """Surprising but real behavior: `db_path` is accepted in the public
    functions' signatures but never passed through to `_load`/`_save`
    internally, so it has NO effect on where data is written. The value
    always lands in whatever `_load`/`_save` currently default to.
    """
    other_file = tmp_path / "somewhere_else.json"
    secrets_store.set_secret("k", "v", db_path=other_file)

    # Nothing was written to the path we asked for...
    assert not other_file.exists()

    # ...instead it went to the (patched) default secrets path.
    assert _redirect_default_secrets_path.exists()
    assert secrets_store.get_secret("k", db_path=other_file) == "v"


def test_get_secret_workspace_id_argument_is_ignored():
    """`workspace_id` is likewise accepted but unused: secrets set under
    one "workspace" are visible when queried under a different one,
    because there is no per-workspace partitioning implemented.
    """
    secrets_store.set_secret("shared_key", "shared_value", workspace_id="workspace-a")
    assert secrets_store.get_secret("shared_key", workspace_id="workspace-b") == "shared_value"


def test_list_secrets_db_path_argument_is_ignored(tmp_path):
    other_file = tmp_path / "another.json"
    secrets_store.set_secret("k", "v")
    assert secrets_store.list_secrets(db_path=other_file) == ["k"]
    assert not other_file.exists()
