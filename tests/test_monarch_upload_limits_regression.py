"""Monarch upload: blank lines count toward the row cap, bad CSV is a 400-style refusal, redirects are not followed."""
from __future__ import annotations

import base64
import tracemalloc
import urllib.error
import urllib.request

import pytest

from src import monarch_connector as mc
from src import monarch_upload as up


def _body(kind: str, text: str) -> dict:
    return {"kind": kind, "filename": "x.csv", "content_base64": base64.b64encode(text.encode()).decode(), "dry_run": True}


def test_blank_lines_are_capped_and_do_not_balloon_memory(monkeypatch):
    monkeypatch.setattr(up, "MAX_ROWS", 1000)
    text = "Date,Account,Amount,Id\n" + "\n" * 50_000
    tracemalloc.start()
    try:
        with pytest.raises(up.UploadError, match="more than"):
            up.normalize_transactions_text(text)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert peak < 20_000_000, peak


def test_an_oversized_field_is_an_upload_refusal_not_a_server_error():
    text = "Date,Account,Amount,Id\n2026-01-01," + "A" * 200_000 + ",1.00,x1\n"
    with pytest.raises(up.UploadError):
        up.normalize_transactions_text(text)


def test_the_connector_transport_never_follows_a_redirect():
    handler = next(h for h in mc._urllib_opener().handlers if isinstance(h, urllib.request.HTTPRedirectHandler))
    req = urllib.request.Request(mc.ENDPOINT_PREFIX + "mcp", headers={"Authorization": "Bearer x"})
    with pytest.raises(urllib.error.HTTPError):
        handler.redirect_request(req, None, 302, "Found", {}, "http://127.0.0.1:9999/admin")
