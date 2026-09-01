"""Local stdlib application package for the retirement dashboard/API."""
from __future__ import annotations

from .app_core import app, BASE_DIR, _bootstrap_workspace, _runtime_config

# Import route modules for registration.
from . import base_routes as _base_routes
from . import workbook_routes as _workbook_routes
from . import plan_routes as _plan_routes
from . import admin_routes as _admin_routes

def create_app():
    """WSGI application factory."""
    return app

application = create_app()

__all__ = ["app", "application", "create_app"]
