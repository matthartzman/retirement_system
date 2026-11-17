from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_local_user_has_admin_permissions():
    from src.permissions import UserContext

    user = UserContext()
    assert user.can("manage_clients")
    assert user.can("manage_users")
    assert user.can("view_dashboard")


def test_admin_route_still_serves_admin_shell_and_uses_local_admin_permission():
    routes = (ROOT / "src/server/admin_routes.py").read_text(encoding="utf-8")
    perms = (ROOT / "src/permissions.py").read_text(encoding="utf-8")

    assert '@app.route("/admin")' in routes
    assert '"manage_clients"' in perms
    assert '"manage_users"' in perms


def test_admin_routes_hand_off_to_the_admin_app(monkeypatch):
    """/admin and /system-configuration redirect to the Admin app when it runs, else explain how to start it."""
    from src.server import admin_routes, create_app

    client = create_app().test_client()
    for path in ("/admin", "/system-configuration"):
        monkeypatch.setattr(admin_routes, "_admin_app_running", lambda: True)
        running = client.get(path, headers={"X-User-Role": "admin"})
        assert running.status_code == 302 and running.headers["Location"] == admin_routes.ADMIN_APP_URL
        monkeypatch.setattr(admin_routes, "_admin_app_running", lambda: False)
        stopped = client.get(path, headers={"X-User-Role": "admin"})
        assert stopped.status_code == 200
        assert admin_routes.ADMIN_APP_URL in stopped.get_data(as_text=True)


def test_html_permission_denials_do_not_render_blank_json_window():
    core = (ROOT / "src/server/app_core.py").read_text(encoding="utf-8")

    assert "def _permission_denied_html" in core
    assert "Admin permission required" in core
    assert "not str(request.path or \"\").startswith(\"/api/\")" in core
    assert 'return jsonify({"success": False, "error": str(exc)}), 403' in core
