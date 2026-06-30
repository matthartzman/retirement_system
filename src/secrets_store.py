from __future__ import annotations
"""Local-only secret store compatibility for v10."""
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
    return {"mode": "local-only", "encrypted": False, "configured": True}

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
