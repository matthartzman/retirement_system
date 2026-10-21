"""UX-002 follow-up: a real server-side build cancel (the Wave 2 overlay only hid the window)."""
from __future__ import annotations

import subprocess
import sys
import time

from src.server_services.build_job_service import BuildJobRegistry, run_build_progress_job


def test_request_cancel_outcomes():
    reg = BuildJobRegistry()
    assert reg.request_cancel("nope") == "not_found"
    reg.create("j", created_at=time.time())
    reg.update("j", status="done")
    assert reg.request_cancel("j") == "finished"
    reg.create("k", created_at=time.time())
    assert reg.request_cancel("k") == "cancelling"
    assert reg.is_cancel_requested("k")


def test_cancel_stops_a_running_build_process(tmp_path):
    script = tmp_path / "slow_build.py"
    script.write_text("import time\nprint('start', flush=True)\ntime.sleep(60)\n", encoding="utf-8")
    reg = BuildJobRegistry()
    reg.create("job", created_at=time.time())

    import threading
    t = threading.Thread(target=run_build_progress_job, kwargs=dict(
        registry=reg, job_id="job", workspace_id="w", client_id="c", env={}, output_dir=tmp_path,
        build_script=script, base_dir=tmp_path, previous_build_ts=0.0, build_start_ts=0.0,
        timeout_seconds=120, redact_logs=False, admin_changes_between=lambda *a: [],
        write_last_build_metadata=lambda *a: None, redact_text=lambda s: s,
        interpret_build_result=lambda **k: (_ for _ in ()).throw(AssertionError("must not interpret a cancelled build"))))
    t.start()
    deadline = time.time() + 20
    while time.time() < deadline and "start" not in (reg.snapshot("job").get("stdout_tail") or ""):
        time.sleep(0.05)
    started = time.time()
    assert reg.request_cancel("job") == "cancelling"
    t.join(15)
    assert not t.is_alive()
    assert time.time() - started < 15
    job = reg.snapshot("job")
    assert job["status"] == "cancelled"
    assert job["result"]["cancelled"] is True
