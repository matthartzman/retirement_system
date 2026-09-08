from __future__ import annotations
"""Local-only secret store compatibility for v11."""
from pathlib import Path
import json

DEFAULT_SECRETS = Path(__file__).resolve().parent.parent / "local_state" / "secrets.local.json"

def _load(path: str | Path = DEFAULT_SECRETS) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except Exception:
        return {}

def _save(data: dict, path: str | Path = DEFAULT_SECRETS) -> None:
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(data, indent=2, sort_keys=True), encoding='utf-8')

def encryption_status(*args, **kwargs) -> dict:
    # Finding SEC-5 (system review 2026-09-07, Wave 6 item W6-1): this used to
    # return a "configured": True key alongside "encrypted": False -- a
    # self-contradicting pair a human skimming the JSON reads as "encryption
    # is configured". It never meant that; it meant "this local-only stub is
    # active" (always true -- a compatibility shim for a SaaS-mode signature
    # unused in this deployment, per the module docstring). Worse than just
    # confusing: tools/manage_secret.py builds
    # `{"configured": bool(val), **encryption_status()}` -- the spread's
    # "configured" key silently overwrote the caller's real "was a secret
    # actually set" flag with this stub's unconditional True. Renamed to
    # "store_active" so it can no longer collide with (or be mistaken for)
    # any caller's own "configured" meaning.
    return {"mode": "local-only", "encrypted": False, "store_active": True}

def require_secure_master_key(*args, **kwargs) -> bool:
    return True

def set_secret(name: str, value: str, workspace_id: str = 'local', db_path=None) -> None:
    data = _load(); data[str(name)] = str(value); _save(data)

def get_secret(name: str, workspace_id: str = 'local', db_path=None) -> str:
    return str(_load().get(str(name), ''))

def delete_secret(name: str, workspace_id: str = 'local', db_path=None) -> None:
    data = _load(); data.pop(str(name), None); _save(data)

def list_secrets(workspace_id: str = 'local', db_path=None) -> list[str]:
    return sorted(_load().keys())
