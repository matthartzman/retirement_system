"""Dependency-free local HTTP runtime for the retirement dashboard.

The public API intentionally mirrors the tiny subset of Flask that the
legacy route modules use while the service layer is incrementally extracted.
No third-party web framework is imported by this package.
"""
from __future__ import annotations

from .wsgi_facade import Flask, Response, g, jsonify, make_response, redirect, request, send_file, send_from_directory, url_for

__all__ = [
    "Flask",
    "Response",
    "g",
    "jsonify",
    "make_response",
    "redirect",
    "request",
    "send_file",
    "send_from_directory",
    "url_for",
]
