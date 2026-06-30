from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE_DIR = ROOT / "src" / "server_services"


def _imports_for(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
    return imports


def test_feature_services_are_http_runtime_independent():
    offenders = []
    for path in SERVICE_DIR.glob("*.py"):
        if path.name == "__init__.py":
            continue
        text = path.read_text(encoding="utf-8")
        for imported in _imports_for(path):
            root = imported.split(".", 1)[0]
            if root in {"flask", "werkzeug"} or imported.startswith("src.http_runtime") or imported.startswith("..http_runtime"):
                offenders.append(f"{path.relative_to(ROOT)} imports {imported}")
        for forbidden in ["jsonify(", "request.", "@app.route", "send_file(", "send_from_directory("]:
            if forbidden in text:
                offenders.append(f"{path.relative_to(ROOT)} contains HTTP adapter token {forbidden}")
    assert offenders == []


def test_route_adapters_delegate_migrated_families_to_services():
    expected = {
        ROOT / "src" / "server" / "base_routes.py": ["base_service.ping_payload", "base_service.read_prefs", "base_service.runtime_payload"],
        ROOT / "src" / "server" / "admin_routes.py": ["admin_service.csv_file_payload", "admin_service.system_config_payload", "admin_service.diagnostics_payload"],
        ROOT / "src" / "server" / "workbook_routes.py": ["build_service.build_preflight_payload", "build_service.read_summary_payload", "plan_forms_service.get_forms_payload"],
    }
    missing = []
    for path, tokens in expected.items():
        text = path.read_text(encoding="utf-8")
        missing.extend(f"{path.relative_to(ROOT)} missing {token}" for token in tokens if token not in text)
    assert missing == []


def test_service_unit_payloads_are_plain_data(tmp_path):
    from src.server_services import admin_service, base_service, build_service

    prefs = base_service.read_prefs(tmp_path)
    assert prefs == {"success": True, "prefs": {}}
    payload, status = base_service.save_prefs(tmp_path, {"theme": "dark"})
    assert status == 200 and payload["success"] is True
    assert json.loads((tmp_path / "data" / "prefs.json").read_text())["theme"] == "dark"

    cfg = tmp_path / "system_config.csv"
    cfg.write_text("section,subsection,label,value\nA,B,C,D\n", encoding="utf-8")
    assert admin_service.system_config_payload(cfg)["rows"][1] == ["A", "B", "C", "D"]

    meta = build_service.file_meta(cfg)
    assert meta["exists"] is True and meta["bytes"] > 0


def test_stdlib_route_smoke_after_service_extraction():
    from src.server import create_app

    client = create_app().test_client()
    ping = client.get("/api/ping", headers={"X-User-Role": "admin"})
    assert ping.status_code == 200
    assert ping.get_json()["success"] is True

    prefs = client.get("/api/prefs", headers={"X-User-Role": "admin"})
    assert prefs.status_code == 200
    assert prefs.get_json()["success"] is True

    server = client.get("/api/admin/server", headers={"X-User-Role": "admin"})
    assert server.status_code == 200
    assert server.get_json()["app_mode"] == "LOCAL"
