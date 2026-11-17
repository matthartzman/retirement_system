from __future__ import annotations
"""Secret store over the operating system credential store (WP8.2 / P6.2).

Secrets (API keys) live in the OS credential store through ``keyring`` (Windows Credential
Manager is the primary target; macOS Keychain and Secret Service also work). The service name is
``SERVICE_NAME`` and the credential's username is the secret name. ``keyring`` cannot enumerate,
so the *names* (never values) are indexed in ``app.db`` settings under ``NAMES_KEY`` for
``list_secrets``.

When no usable credential service exists every operation that needs one raises
``SecretStoreUnavailable`` with a clear message. There is deliberately NO plain-text fallback:
nothing here ever writes a secret to a file. Pricing-path readers treat the error as "no key"
and surface the warning; set paths surface the error to the user.

``migrate_legacy_secrets_file`` moves keys out of the old ``local_state/secrets.local.json``
and only offers to delete that file after every key has been read back from the credential store.
"""
import json
import os
from pathlib import Path
from typing import Any

from .platform_runtime import workspace_root

SERVICE_NAME = "RetirementSystem"
# Set by the gateway's per-account launcher only (src/gateway/launchers.py); see _remote_mode_guard.
DEDICATED_ACCOUNT_ENV = "RETIREMENT_SYSTEM_DEDICATED_ACCOUNT"
_REMOTE_BACKENDS = frozenset({"keyring.backends.Windows.WinVaultKeyring"})
NAMES_KEY = "secrets.names"
MACHINE_KEY = "secrets.machine"  # remote mode: {name: base64 of a machine-scope DPAPI blob}, in the worker's own app.db
LEGACY_FILE_NAME = "secrets.local.json"


class SecretStoreUnavailable(RuntimeError):
    """No usable OS credential store (no keyring backend, or the backend failed)."""


_UNAVAILABLE_HELP = (
    "API keys are kept in the operating system credential store (Windows Credential Manager, "
    "macOS Keychain, or a Secret Service such as GNOME Keyring), and none is available here. "
    "Keys are never saved to a plain file. Set the key with an environment variable "
    "(e.g. RETIREMENT_SYSTEM_FMP_API_KEY) or enable a credential service."
)


def legacy_secrets_path() -> Path:
    """The old plain-text secrets file (``<workspace>/local_state/secrets.local.json``)."""
    return workspace_root() / "local_state" / LEGACY_FILE_NAME


secrets_path = legacy_secrets_path  # backwards-compatible name; the file is legacy-only now


def _machine_store_active() -> bool:
    """A dedicated server worker keeps its secrets in its own ``app.db`` under machine-scope DPAPI, not in Windows
    Credential Manager: user-scope keys do not reliably survive the account's password rotation
    (``src/dpapi_machine.py``). The same guard as before decides who may use it: only a worker the per-account
    launcher marked as running as its own account. A same-account worker still gets the refusal from
    ``_remote_mode_guard`` through the keyring path."""
    from . import remote_mode
    return remote_mode.enabled() and (os.environ.get(DEDICATED_ACCOUNT_ENV) or "").strip() == "1"


def _entropy(name: str) -> bytes:
    return f"{SERVICE_NAME}|{name}".encode("utf-8")


def _machine_blobs() -> dict[str, str]:
    from .app_state import open_app_store
    store = open_app_store()
    try:
        raw: Any = store.get_setting(MACHINE_KEY, {})
    finally:
        store.close()
    return {str(k): str(v) for k, v in raw.items()} if isinstance(raw, dict) else {}


def _machine_write(blobs: dict[str, str]) -> None:
    from .app_state import open_app_store
    store = open_app_store()
    try:
        store.set_setting(MACHINE_KEY, dict(sorted(blobs.items())))
    finally:
        store.close()


def _machine_op(op: str, fn):
    from . import dpapi_machine
    try:
        return fn(dpapi_machine)
    except dpapi_machine.DpapiUnavailable as exc:
        raise SecretStoreUnavailable(f"The server's secret store failed to {op} ({exc}).") from exc


def _keyring():
    """The active keyring module/backend pair, or raise ``SecretStoreUnavailable``."""
    try:
        import keyring
        from keyring.backends import fail
    except Exception as exc:  # ImportError or a broken backend import
        raise SecretStoreUnavailable(f"The keyring package could not be loaded ({exc}). {_UNAVAILABLE_HELP}") from exc
    try:
        backend = keyring.get_keyring()
    except Exception as exc:
        raise SecretStoreUnavailable(f"No credential store backend could be selected ({exc}). {_UNAVAILABLE_HELP}") from exc
    if isinstance(backend, fail.Keyring):
        raise SecretStoreUnavailable(f"No usable credential store backend was found. {_UNAVAILABLE_HELP}")
    _remote_mode_guard(backend)
    return keyring, backend


def _remote_mode_guard(backend) -> None:
    """In remote mode the store is used only when it is provably this user's own (multi-user Phase 4).

    A worker started by the gateway's per-account launcher runs as its own Windows account with its profile
    loaded, so the Windows Credential Manager is private to that user; the launcher marks such a worker with
    ``DEDICATED_ACCOUNT_ENV``. A same-account worker (development, CI) would share the gateway account's
    store with every other user, and any other backend (a ``keyrings.alt`` file, an override) could live in a
    shared place, so both are refused. No-op outside remote mode.
    """
    from . import remote_mode
    if not remote_mode.enabled():
        return
    if (os.environ.get(DEDICATED_ACCOUNT_ENV) or "").strip() != "1":
        raise SecretStoreUnavailable("Stored keys are not available: this server worker does not run as its own "
                                     "Windows account, so its credential store would be shared.")
    kind = f"{type(backend).__module__}.{type(backend).__name__}"
    if kind not in _REMOTE_BACKENDS:
        raise SecretStoreUnavailable("Stored keys are not available: only the Windows Credential Manager of this "
                                     "user's own account is used on the server.")


def _call(op: str, fn, *args):
    keyring, _ = _keyring()
    from keyring.errors import KeyringError, NoKeyringError, PasswordDeleteError
    try:
        return fn(keyring)(*args)
    except PasswordDeleteError:
        raise
    except NoKeyringError as exc:
        raise SecretStoreUnavailable(f"No usable credential store backend was found. {_UNAVAILABLE_HELP}") from exc
    except KeyringError as exc:
        raise SecretStoreUnavailable(f"The credential store failed to {op} ({exc}).") from exc


def _read_names() -> list[str]:
    from .app_state import open_app_store
    store = open_app_store()
    try:
        raw: Any = store.get_setting(NAMES_KEY, [])
    finally:
        store.close()
    return sorted({str(n) for n in raw}) if isinstance(raw, list) else []


def _write_names(names) -> None:
    from .app_state import open_app_store
    store = open_app_store()
    try:
        store.set_setting(NAMES_KEY, sorted({str(n) for n in names}))
    finally:
        store.close()


def encryption_status(*args, **kwargs) -> dict:
    """Whether a real OS credential store is active. Never raises."""
    if _machine_store_active():
        try:
            _machine_op("start", lambda d: d.unprotect(d.protect(b"probe", _entropy("probe")), _entropy("probe")))
        except SecretStoreUnavailable as exc:
            return {"mode": "machine-dpapi", "encrypted": False, "store_active": False, "error": str(exc)}
        return {"mode": "machine-dpapi", "encrypted": True, "store_active": True, "backend": "DPAPI (machine scope)"}
    try:
        _, backend = _keyring()
    except SecretStoreUnavailable as exc:
        return {"mode": "os-credential-store", "encrypted": False, "store_active": False, "error": str(exc)}
    return {"mode": "os-credential-store", "encrypted": True, "store_active": True,
            "backend": type(backend).__name__}


def require_secure_master_key(*args, **kwargs) -> bool:
    return True


def set_secret(name: str, value: str, workspace_id: str = 'local', db_path=None) -> None:
    name = str(name)
    if _machine_store_active():
        import base64
        blob = _machine_op("save the secret", lambda d: d.protect(str(value).encode("utf-8"), _entropy(name)))
        _machine_write({**_machine_blobs(), name: base64.b64encode(blob).decode("ascii")})
        _write_names(set(_read_names()) | {name})
        return
    _call("save the secret", lambda k: k.set_password, SERVICE_NAME, name, str(value))
    _write_names(set(_read_names()) | {name})


def get_secret(name: str, workspace_id: str = 'local', db_path=None) -> str:
    if _machine_store_active():
        import base64
        text = _machine_blobs().get(str(name))
        if not text:
            return ''
        return _machine_op("read the secret", lambda d: d.unprotect(base64.b64decode(text), _entropy(str(name)))
                           ).decode("utf-8")
    return str(_call("read the secret", lambda k: k.get_password, SERVICE_NAME, str(name)) or '')


def delete_secret(name: str, workspace_id: str = 'local', db_path=None) -> None:
    name = str(name)
    if _machine_store_active():
        blobs = _machine_blobs()
        blobs.pop(name, None)
        _machine_write(blobs)
        _write_names(set(_read_names()) - {name})
        return
    from keyring.errors import PasswordDeleteError
    try:
        _call("delete the secret", lambda k: k.delete_password, SERVICE_NAME, name)
    except PasswordDeleteError:
        pass  # never stored: deleting is a harmless no-op
    _write_names(set(_read_names()) - {name})


def list_secrets(workspace_id: str = 'local', db_path=None) -> list[str]:
    return _read_names()


def migrate_legacy_secrets_file(path: str | Path | None = None, *, delete_file: bool = False) -> dict:
    """Move keys from the legacy plain-text JSON file into the credential store.

    Every key is written, then read back and compared. The plain file is removed only when
    ``delete_file`` is true AND every key verified; otherwise it is left untouched (the WP10
    converter asks the user before passing ``delete_file=True``). Raises ``SecretStoreUnavailable``
    when there is no credential store. Values are never returned or logged.
    """
    p = Path(path) if path is not None else legacy_secrets_path()
    result: dict[str, Any] = {"path": str(p), "found": p.is_file(), "migrated": [], "failed": [],
                              "verified": False, "deleted": False}
    if not result["found"]:
        result["verified"] = True
        return result
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("not a JSON object")
    except Exception as exc:
        result["error"] = f"legacy secrets file is unreadable ({exc}); left in place"
        return result
    if not _machine_store_active():
        _keyring()  # fail early and loudly before touching anything
    for name, value in data.items():
        name, value = str(name), str(value)
        try:
            set_secret(name, value)
            ok = get_secret(name) == value
        except SecretStoreUnavailable:
            raise
        except Exception:
            ok = False
        (result["migrated"] if ok else result["failed"]).append(name)
    result["verified"] = not result["failed"]
    if delete_file and result["verified"]:
        p.unlink()
        result["deleted"] = True
    return result
