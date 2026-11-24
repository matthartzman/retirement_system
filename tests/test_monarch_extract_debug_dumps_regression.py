"""F-11: Monarch failure dumps are off by default, redacted when on, and deleted after 7 days."""
from __future__ import annotations

import asyncio
import importlib.util
import os
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "Monarch Extractor" / "monarch_debug_dumps.py"
SCRIPT = ROOT / "Monarch Extractor" / "monarch_extract.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


dumps = _load(HELPER, "monarch_debug_dumps_under_test")


def test_off_unless_asked():
    assert dumps.dumps_enabled(False, {}) is False
    assert dumps.dumps_enabled(True, {}) is True
    assert dumps.dumps_enabled(False, {"MONARCH_DEBUG_DUMPS": "1"}) is True
    assert dumps.dumps_enabled(False, {"MONARCH_DEBUG_DUMPS": "0"}) is False


def test_redaction_removes_amounts_and_account_numbers():
    html = ('<div class="acct">Checking ••••1234 <span>$12,345.67</span> <b>-$89.10</b> ($5,000)</div>'  # acct-scan: ok (synthetic)
            '<input value="987654.32" data-amount="1500000"> acct 123456789012 total 1,234,567 ok')  # acct-scan: ok (synthetic)
    out = dumps.redact_html(html)
    for secret in ("12,345.67", "1234", "89.10", "5,000", "987654", "1500000", "123456789012", "1,234,567"):
        assert secret not in out, secret
    assert out.count("Checking") == 1 and out.count('<div class="acct">') == 1  # the page structure survives


def test_purge_removes_only_old_dumps(tmp_path):
    now = time.time()
    old_html, old_png, fresh, other = (tmp_path / "monarch-debug-1.html", tmp_path / "monarch-debug-1.png",
                                       tmp_path / "monarch-debug-2.html", tmp_path / "balances.csv")
    for p in (old_html, old_png, fresh, other):
        p.write_text("x")
    for p in (old_html, old_png, other):
        os.utime(p, (now - 8 * 86400, now - 8 * 86400))
    removed = dumps.purge_old_dumps(tmp_path, now=now)
    assert {p.name for p in removed} == {"monarch-debug-1.html", "monarch-debug-1.png"}
    assert fresh.exists() and other.exists()  # newer dumps and unrelated files are never touched
    assert dumps.purge_old_dumps(tmp_path / "missing") == []


class _Page:
    async def content(self):
        return "<p>$9,999.99</p>"

    async def screenshot(self, **kw):
        Path(kw["path"]).write_bytes(b"PNG")


def _failing_run(mod, tmp_path, monkeypatch, *, dumps_on, shot):
    monkeypatch.setattr(mod, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(mod, "DEBUG_DUMPS", dumps_on)
    monkeypatch.setattr(mod, "DEBUG_SCREENSHOT", shot)

    class _Ctx:
        pages = [_Page()]

        async def close(self):
            pass

    class _Chromium:
        async def launch_persistent_context(self, **kw):
            return _Ctx()

    class _PW:
        chromium = _Chromium()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    async def boom(*a, **k):
        raise RuntimeError("page changed")

    _Page.set_default_timeout = lambda self, t: None
    _Page.set_default_navigation_timeout = lambda self, t: None
    monkeypatch.setattr(mod, "async_playwright", lambda: _PW())
    monkeypatch.setattr(mod, "goto_transactions", boom)
    with pytest.raises(RuntimeError):
        asyncio.run(mod.download_monarch_csv(False, "Last 30 days"))
    return sorted(p.name for p in tmp_path.iterdir())


def test_a_failure_writes_nothing_by_default(tmp_path, monkeypatch):
    mod = _load(SCRIPT, "monarch_extract_dumps_off")
    assert _failing_run(mod, tmp_path, monkeypatch, dumps_on=False, shot=False) == []


def test_flag_writes_redacted_html_only_and_the_screenshot_needs_its_own_flag(tmp_path, monkeypatch):
    mod = _load(SCRIPT, "monarch_extract_dumps_on")
    files = _failing_run(mod, tmp_path, monkeypatch, dumps_on=True, shot=False)
    assert len(files) == 1 and files[0].endswith(".html")
    assert (tmp_path / files[0]).read_text().count("9,999.99") == 0
    for f in tmp_path.iterdir():
        f.unlink()
    both = _failing_run(mod, tmp_path, monkeypatch, dumps_on=True, shot=True)
    assert [f.rsplit(".", 1)[1] for f in both] == ["html", "png"]
