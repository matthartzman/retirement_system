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


def _run(svc, *, dry_run):
    """Start a conversion and wait. The run lock is process-wide, so a conversion thread left over
    from another test makes this one return ``busy``; retry that (only) a few times."""
    for _ in range(50):
        body, code = svc.start({}, dry_run=dry_run)
        assert code == 202
        _wait(svc)
        res = svc.status()["last_result"]
        if res.get("blocked_reason") != "busy":
            return res
        time.sleep(0.2)
    return res


def test_options_are_whitelisted():
    opts = ConversionService._options({"accept_differences": True, "tier_mapping": "keep", "plan_file": "/x", "delete_legacy_secrets": "yes"})
    assert opts == {"accept_differences": True, "tier_mapping": "keep"}


def test_status_check_run_on_a_legacy_workspace(tmp_path):
    ws = pf.make_plan(tmp_path)
    svc = ConversionService(lambda: tmp_path)
    st = svc.status()
    assert st["needed"] and st["found"]["files"] and "last_result" in st
    dry = _run(svc, dry_run=True)
    assert dry["status"] == "dry_run" and not dry["blocked_reason"], dry
    res = _run(svc, dry_run=False)
    assert res["status"] == "done" and res["verified"], res
    assert (ws.input_dir / "client_data.csv").is_file()  # originals stay
    assert not svc.status()["needed"]
