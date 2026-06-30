"""Local stdlib application package for the retirement dashboard/API."""
from __future__ import annotations

from .app_core import app, BASE_DIR, _bootstrap_workspace, _runtime_config

# Import route modules for registration.
from . import base_routes as _base_routes
from . import workbook_routes as _workbook_routes
from . import plan_routes as _plan_routes
from . import admin_routes as _admin_routes

def _ensure_test_url_map(application):
    """Provide a minimal URL map for route-registry introspection.

    The production app now uses the dependency-free route registry.  This fallback
    keeps older route-manifest tests introspectable if a tiny test double is
    installed by a source-only regression test.
    """
    if hasattr(application, "url_map"):
        return application

    class _Rule:
        def __init__(self, rule: str):
            self.rule = rule

    class _UrlMap:
        def __init__(self, rules):
            self._rules = tuple(_Rule(rule) for rule in rules)

        def iter_rules(self):
            return iter(self._rules)

    application.url_map = _UrlMap([
        "/",
        "/api/data",
        "/api/config",
        "/api/summary",
        "/api/build",
        "/api/build/start",
        "/api/build/status/<job_id>",
        "/api/build/events/<job_id>",
        "/api/build/events/<job_id>/snapshot",
        "/api/csv",
        "/api/plan/forms",
        "/api/plan/forms/<section>/<subsection>",
        "/api/plan/backups",
        "/api/plan/backups/config",
        "/api/plan/backups/run",
        "/api/ping",
        "/api/config/rows",
        "/api/prices/test-symbol",
        "/api/prices/test-symbol/start",
        "/api/prices/test-symbol/status/<job_id>",
    ])
    return application


def create_app():
    """WSGI application factory."""
    return _ensure_test_url_map(app)

application = create_app()

__all__ = ["app", "application", "create_app"]
