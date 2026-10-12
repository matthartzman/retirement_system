from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .. import active_plan


def safe_next_path(raw: object) -> str:
    """Return a same-origin, root-relative navigation target."""
    text = str(raw or "/").strip() or "/"
    parsed = urlparse(text)
    if parsed.scheme or parsed.netloc or not text.startswith("/") or text.startswith("//") or "\r" in text or "\n" in text:
        return "/"
    return text


def package_instance_payload(base_dir: Path, version: str | None = None) -> dict[str, str]:
    """Identify the exact package root serving this local desktop UI."""
    try:
        root = str(base_dir.resolve())
    except Exception:
        root = str(base_dir)
    version_text = str(version or "")
    try:
        package_instance_id = hashlib.sha256(f"{version_text}|{root}".encode("utf-8")).hexdigest()[:16]
    except Exception:
        package_instance_id = ""
    return {"package_root": root, "package_instance_id": package_instance_id}


def ping_payload(*, version: str, app_mode: str, base_dir: Path) -> dict[str, Any]:
    payload = {"success": True, "running": True, "version": version, "app_mode": app_mode}
    payload.update(package_instance_payload(base_dir, version))
    return payload


def auth_session_payload(*, ok: bool, identity: Any, cfg: Any, csrf_token: str) -> dict[str, Any]:
    return {
        "success": True,
        "authenticated": bool(ok),
        "app_mode": getattr(cfg, "app_mode", "LOCAL"),
        "https_required": bool(getattr(cfg, "force_https", False)),
        "public_base_url": getattr(cfg, "public_base_url", ""),
        "user": identity.__dict__ if identity else None,
        "csrf_token": csrf_token if ok else "",
    }


def login_payload(csrf_token: str) -> dict[str, Any]:
    return {"success": True, "next": "/", "user": {"user_id": "local", "role": "advisor"}, "csrf_token": csrf_token}


def logout_payload() -> dict[str, bool]:
    return {"success": True, "logged_out": True}


PREFS_SETTING = "preferences"


def _legacy_prefs(base_dir: Path) -> dict[str, Any]:
    """``data/prefs.json`` of an older install, read once when app.db holds no preferences yet."""
    try:
        payload = json.loads((base_dir / "data" / "prefs.json").read_text("utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _stored_prefs(store: Any, base_dir: Path) -> dict[str, Any]:
    stored = store.get_setting(PREFS_SETTING)
    return stored if isinstance(stored, dict) else _legacy_prefs(base_dir)


def read_prefs(base_dir: Path) -> dict[str, Any]:
    try:
        from ..app_state import app_store_path_for, open_app_store

        path = app_store_path_for(base_dir)
        if not path.exists():
            return {"success": True, "prefs": _legacy_prefs(base_dir)}
        with open_app_store(path, readonly=True) as store:
            return {"success": True, "prefs": _stored_prefs(store, base_dir)}
    except Exception:
        return {"success": True, "prefs": {}}


def save_prefs(base_dir: Path, updates: Any) -> tuple[dict[str, Any], int]:
    if not isinstance(updates, dict):
        return {"success": False, "error": "JSON object required"}, 400
    try:
        from ..app_state import app_store_path_for, open_app_store

        with open_app_store(app_store_path_for(base_dir)) as store, store.transaction():
            store.set_setting(PREFS_SETTING, {**_stored_prefs(store, base_dir), **updates})
        return {"success": True}, 200
    except Exception as exc:
        return {"success": False, "error": str(exc)}, 500


def runtime_payload(*, version: str, cfg: Any, user: Any, output_dir: Path) -> dict[str, Any]:
    return {
        "version": version,
        "app_mode": getattr(cfg, "app_mode", "LOCAL"),
        "user": {
            "user_id": getattr(user, "user_id", ""),
            "email": getattr(user, "email", ""),
            "role": getattr(user, "role", ""),
            "permissions": sorted(getattr(user, "permissions", []) or []),
        },
        "require_api_token": getattr(cfg, "require_api_token", False),
        "audit_log_enabled": getattr(cfg, "audit_log_enabled", False),
        "allow_csv_write": getattr(cfg, "allow_csv_write", False),
        "allow_downloads": getattr(cfg, "allow_downloads", False),
        "max_build_seconds": getattr(cfg, "max_build_seconds", 0),
        "output_dir": str(output_dir),
    }


def status_payload(*, version: str, cfg: Any, base_dir: Path, output_dir: Path, encryption: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {
        "version": version,
        "app_mode": getattr(cfg, "app_mode", "LOCAL"),
        "base_dir": str(base_dir.resolve()),
        "input_dir": str((base_dir / "input").resolve()),
        "input_dir_exists": (base_dir / "input").exists(),
        "output_dir": str(output_dir),
        "plan_summary_exists": bool((active_plan.read_build_results() or {}).get("summary")),
        "features": {
            "json_yaml_config": True,
            "sqlite_backend": False,
            # Finding SEC-5 (system review 2026-09-07, Wave 6 item W6-1): this
            # flatly contradicted the "encryption" key a few lines below in
            # this same payload (secrets_store.encryption_status()'s
            # "encrypted": False) -- the store is plaintext JSON, not
            # encrypted at rest.
            "encrypted_api_keys": bool((encryption or {}).get("encrypted", False)),
            "user_permissions": False,
            "build_queue": False,
            "web_dashboard": True,
            "nightly_price_refresh": True,
            "historical_price_snapshots": True,
            "portfolio_drift_analysis": True,
            "local_outputs": True,
            "sqlite_client_files": True,
        },
        "encryption": encryption or {},
    }
    payload.update(package_instance_payload(base_dir, version))
    return payload
