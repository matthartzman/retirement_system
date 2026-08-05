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
    # /admin and /system-configuration redirect to /frontend/admin.html (like
    # "/" -> "/frontend/index.html") so admin.html's relative css/admin.css,
    # js/admin.js, and js/pywebview_bridge.js references resolve against a
    # URL the /frontend/<path:filename> route actually serves, instead of
    # 404ing when admin.html is served directly at /admin or
    # /system-configuration.
    assert 'redirect(target, code=302)' in routes
    assert '"/frontend/admin.html"' in routes
    assert '"manage_clients"' in perms
    assert '"manage_users"' in perms


def test_html_permission_denials_do_not_render_blank_json_window():
    core = (ROOT / "src/server/app_core.py").read_text(encoding="utf-8")

    assert "def _permission_denied_html" in core
    assert "Admin permission required" in core
    assert "not str(request.path or \"\").startswith(\"/api/\")" in core
    assert 'return jsonify({"success": False, "error": str(exc)}), 403' in core
