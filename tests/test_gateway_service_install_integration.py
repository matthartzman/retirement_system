"""Real service install/start/stop/remove (elevated; skipped unless RETIREMENT_ELEVATED_TESTS=1)."""

from __future__ import annotations

import json
import secrets
import time
import urllib.request
from pathlib import Path

import pytest

from src.gateway import service

pytestmark = [pytest.mark.elevated, pytest.mark.integration]

ERROR_SERVICE_DOES_NOT_EXIST = 1060


def _gone(name: str) -> bool:
    try:
        service.query_status(name)
    except OSError as exc:
        return exc.errno == ERROR_SERVICE_DOES_NOT_EXIST
    return False


def test_service_install_start_serve_stop_remove(tmp_path: Path):
    name = f"RetirementGatewayTest{secrets.token_hex(3)}"
    ready = tmp_path / "ready.json"
    config = tmp_path / "gateway.json"
    config.write_text(
        json.dumps(
            {
                "argv": [
                    "--local-port", "0",
                    "--no-tailscale-check",
                    "--db", str(tmp_path / "gateway.db"),
                    "--ready-file", str(ready),
                ],
                "log_file": str(tmp_path / "service.log"),
            }
        ),
        encoding="utf-8",
    )
    try:
        service.install_service(name, "Retirement Gateway Test", config)
        assert service.query_status(name) == service.SERVICE_STOPPED
        service.start_service(name)
        deadline = time.time() + 60
        while time.time() < deadline and not (ready.exists() and ready.stat().st_size > 0):
            time.sleep(0.5)
        assert ready.exists(), "gateway never wrote its ready file"
        info = json.loads(ready.read_text(encoding="utf-8"))
        port = info.get("local_port") or info.get("port")
        assert port, f"no local port in ready file keys {sorted(info)}"
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/login", timeout=15) as resp:
            assert resp.status == 200
        assert service.stop_service(name) == service.SERVICE_STOPPED
        service.remove_service(name)
    finally:
        try:
            service.stop_service(name)
        except OSError:
            pass
        try:
            service.remove_service(name)
        except OSError:
            pass
        deadline = time.time() + 15
        while time.time() < deadline and not _gone(name):
            time.sleep(0.5)
        assert _gone(name)
