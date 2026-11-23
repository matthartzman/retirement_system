"""F-11 / F-12: a startup warning (log, console box and a visible banner on the served page) when the data folder or
token file is open to other accounts or sits under OneDrive. It never blocks start-up."""
from __future__ import annotations

import pytest

from src.http_runtime import data_exposure_check as dec


def test_onedrive_by_environment_and_by_name(tmp_path):
    assert dec.onedrive_problem(tmp_path / "x", {}) is None
    assert dec.onedrive_problem(tmp_path / "x" / "y", {"OneDrive": str(tmp_path / "x")})
    assert dec.onedrive_problem("C:/Users/me/OneDrive - Contoso/data", {})
    assert dec.onedrive_problem("C:/Users/me/OneDriveBackup/data", {})
    assert dec.onedrive_problem("C:/RetirementPlanning/data", {"OneDrive": "C:/Users/me/OneDrive"}) is None


def test_posix_modes(tmp_path):
    f = tmp_path / "token"
    f.write_text("t")
    kw = {"platform": "linux"}  # the mode bits are injected, so this runs the same on every OS
    assert dec.permission_problems(f, mode_of=lambda p: 0o600, **kw) == []
    assert "accessible to group or other" in dec.permission_problems(f, mode_of=lambda p: 0o644, **kw)[0]
    assert dec.permission_problems(tmp_path / "missing", mode_of=lambda p: 0o777, **kw) == []


def _ace(sid, mask=0x1200A9, allow=True, inherit_only=False):
    from src.gateway import acl

    return acl.Ace(sid, allow, mask, inherit_only)


def test_windows_dacl_with_fakes(tmp_path):
    from src.gateway import acl

    f = tmp_path / "t"
    f.write_text("x")
    me = "S-1-5-21-1-2-3-1001"
    good = acl.Dacl(True, (_ace(me), _ace("S-1-5-18"), _ace("S-1-5-32-544")), me)
    bad = acl.Dacl(True, (_ace(me), _ace("S-1-5-32-545")), me)  # Users can read
    nulld = acl.Dacl(False, None, me)
    kw = {"platform": "win32", "current_sid": lambda: me}
    assert dec.permission_problems(f, read_dacl=lambda p: good, **kw) == []
    assert "S-1-5-32-545" in dec.permission_problems(f, read_dacl=lambda p: bad, **kw)[0]
    assert "no access list" in dec.permission_problems(f, read_dacl=lambda p: nulld, **kw)[0]

    def boom(_p):
        raise OSError(5, "denied")
    assert "could not be checked" in dec.permission_problems(f, read_dacl=boom, **kw)[0]  # never raises


def test_banner_is_escaped_and_lands_after_body():
    page = "<html><body class='x'><h1>App</h1></body></html>"
    out = dec.inject_banner(page, ["data: <script>alert(1)</script> is exposed"])
    assert out.index("data-exposure-banner") > out.index("<body class='x'>") and "<script>alert" not in out
    assert "&lt;script&gt;" in out
    assert dec.inject_banner(page, []) == page


def test_announce_logs_and_prints(capsys, caplog):
    import logging

    with caplog.at_level(logging.WARNING, logger="retirement.data_exposure"):
        dec.announce("Admin app", ["x is exposed"])
    assert "x is exposed" in caplog.text and "WARNING (Admin app)" in capsys.readouterr().err
    dec.announce("Admin app", [])
    assert capsys.readouterr().err == ""


def test_admin_app_and_insights_serve_the_banner_only_when_there_is_something_to_say(tmp_path):
    from admin_app.main import create_app as admin_app
    from financial_trends_reporter.main import create_app as fi_app
    from src.identity.store import open_identity_store

    store = open_identity_store(tmp_path / "identity.db")
    app = admin_app(store)
    app.data_exposure_warnings = ["identity database folder: it is on OneDrive"]
    html = app.test_client().get("/", headers={"Host": "127.0.0.1:5056"}).get_data(as_text=True)
    assert "data-exposure-banner" in html and "on OneDrive" in html
    app.data_exposure_warnings = []
    assert "data-exposure-banner" not in app.test_client().get("/", headers={"Host": "127.0.0.1:5056"}).get_data(as_text=True)
    ws = tmp_path / "ws"
    (ws / "financial_trends_reporter").mkdir(parents=True)
    fi = fi_app(ws)
    fi.data_exposure_warnings = ["Financial Insights data folder: readable by others"]
    assert "readable by others" in fi.test_client().get("/").get_data(as_text=True)
