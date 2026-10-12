"""WP10.4: first-launch conversion service and routes (status, check, run), privacy-safe."""
from __future__ import annotations

import time

from src.server_services.conversion_service import ConversionService
from tests import plan_fixture as pf


def _wait(svc):
    for _ in range(300):
        if not svc.status()["running"]:
            return
        time.sleep(0.1)
    raise AssertionError("conversion did not finish")


def test_options_are_whitelisted():
    opts = ConversionService._options({"accept_differences": True, "tier_mapping": "keep", "plan_file": "/x", "delete_legacy_secrets": "yes"})
    assert opts == {"accept_differences": True, "tier_mapping": "keep"}


def test_status_check_run_on_a_legacy_workspace(tmp_path):
    ws = pf.make_plan(tmp_path)
    svc = ConversionService(lambda: tmp_path)
    st = svc.status()
    assert st["needed"] and st["found"]["files"] and "last_result" in st
    body, code = svc.start({}, dry_run=True)
    assert code == 202
    _wait(svc)
    dry = svc.status()["last_result"]
    assert dry["status"] == "dry_run" and not dry["blocked_reason"]
    body, code = svc.start({}, dry_run=False)
    assert code == 202
    _wait(svc)
    res = svc.status()["last_result"]
    assert res["status"] == "done" and res["verified"]
    assert (ws.input_dir / "client_data.csv").is_file()  # originals stay
    assert not svc.status()["needed"]
