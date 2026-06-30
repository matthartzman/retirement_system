from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


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


def read_prefs(base_dir: Path) -> dict[str, Any]:
    prefs_file = base_dir / "data" / "prefs.json"
    try:
        if prefs_file.exists():
            payload = json.loads(prefs_file.read_text("utf-8"))
            if isinstance(payload, dict):
                return {"success": True, "prefs": payload}
    except Exception:
        pass
    return {"success": True, "prefs": {}}


def save_prefs(base_dir: Path, updates: Any) -> tuple[dict[str, Any], int]:
    if not isinstance(updates, dict):
        return {"success": False, "error": "JSON object required"}, 400
    prefs_file = base_dir / "data" / "prefs.json"
    try:
        prefs_file.parent.mkdir(parents=True, exist_ok=True)
        existing: dict[str, Any] = {}
        if prefs_file.exists():
            try:
                loaded = json.loads(prefs_file.read_text("utf-8"))
                if isinstance(loaded, dict):
                    existing = loaded
            except Exception:
                existing = {}
        existing.update(updates)
        prefs_file.write_text(json.dumps(existing, indent=2), "utf-8")
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
        "plan_summary_exists": (output_dir / "plan_summary.json").exists(),
        "features": {
            "json_yaml_config": True,
            "sqlite_backend": False,
            "encrypted_api_keys": True,
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
