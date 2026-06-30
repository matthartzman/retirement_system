"""WSGI-compatible entry point.

The packaged application now uses the stdlib local HTTP runtime.  This module
provides ``src.server.wsgi:application`` for tool integrations that expect a
WSGI-style object; it does not require Flask/Werkzeug.
"""
from __future__ import annotations

from . import create_app

application = create_app()
app = application
