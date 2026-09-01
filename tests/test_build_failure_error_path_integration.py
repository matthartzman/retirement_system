"""Error-path tests: build-failure surfacing and malformed-input rejection
(item 2.13, finding Q5).

The suite has strong coverage of a SUCCESSFUL build (the ~90s subprocess
build tests) but nothing exercising what a user actually sees when the
build subprocess itself crashes, times out, or is asked to run with a
malformed request. This file drives the real
``server_services.build_job_service.run_build_progress_job`` -- the same
function ``workbook_routes.py``'s ``/api/build/start`` route runs in a
background thread -- against a tiny synthetic "build script" that fails
fast (milliseconds, not the ~90s real build), so the failure-surfacing code
path (subprocess launch, exit-code/stderr capture,
``extract_build_failure_message``, job registry update) is exercised for
real without paying the real build's cost or needing
``@pytest.mark.slow``.
"""
from __future__ import annotations

import time

from src.server import app
from src.server_services import build_service
from src.server_services.build_job_service import BuildJobRegistry, run_build_progress_job

HEADERS = {"X-User-Role": "admin"}


def _noop_admin_changes(workspace_id, after_ts, before_ts):
    return []


def _noop_write_last_build_metadata(workspace_id, payload):
    pass


def _identity_redact(text):
    return text


def _run_job(tmp_path, script_body, *, timeout_seconds=30):
    script = tmp_path / "fake_build.py"
    script.write_text(script_body, encoding="utf-8")
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    registry = BuildJobRegistry()
    job_id = "test-job"
    registry.create(job_id, created_at=time.time())
    run_build_progress_job(
        registry=registry,
        job_id=job_id,
        workspace_id="local",
        client_id="local",
        env={"RETIREMENT_SYSTEM_BUILD_ID": job_id},
        output_dir=output_dir,
        build_script=script,
        base_dir=tmp_path,
        previous_build_ts=0.0,
        build_start_ts=time.time(),
        timeout_seconds=timeout_seconds,
        redact_logs=False,
        admin_changes_between=_noop_admin_changes,
        write_last_build_metadata=_noop_write_last_build_metadata,
        redact_text=_identity_redact,
        interpret_build_result=build_service.interpret_build_result,
    )
    return registry.snapshot(job_id)


# ─────────────────────────────────────────────────────────────────────────────
# A genuinely crashed build subprocess
# ─────────────────────────────────────────────────────────────────────────────

def test_crashed_build_subprocess_surfaces_a_failed_job_status(tmp_path):
    job = _run_job(tmp_path, (
        "import sys\n"
        "print('Starting build...')\n"
        "sys.stderr.write('ValueError: household config is missing plan_start\\n')\n"
        "sys.exit(1)\n"
    ))
    assert job["status"] == "failed"
    assert job["progress"] == 100
    assert job["phase"] == "Build failed"
    assert job["result"]["success"] is False
    assert job["result"]["returncode"] == 1


def test_crashed_build_subprocess_error_message_names_the_real_exception(tmp_path):
    """The user-visible result.error must name the actual failure (extracted
    via extract_build_failure_message's traceback-line scan over the
    combined stdout+stderr stream -- run_build_progress_job merges the
    child's stderr into the same pipe it reads stdout from), not a generic
    'something went wrong' -- otherwise a real crash is indistinguishable
    from a hang or a silent no-op to whoever is looking at the Build tab.

    Note: job["detail"] (as opposed to job["result"]["error"]) is set from
    result_payload["stderr"] alone, which run_build_progress_job's own
    subprocess.Popen call routes into the SAME pipe as stdout
    (stderr=subprocess.STDOUT) -- so `stderr_text` from proc.communicate()
    is always empty on this code path, and job["detail"] always falls back
    to the generic "Build process returned an error." string, even though
    the specific message was captured and IS available in
    job["result"]["error"]. Whether that is worth changing (e.g. reading
    result.error for detail too) is a separate, smaller follow-up; this
    test locks in the current, factual behavior of both fields rather than
    silently document only the one that already works.
    """
    job = _run_job(tmp_path, (
        "import sys\n"
        "sys.stderr.write('Traceback (most recent call last):\\n')\n"
        "sys.stderr.write('  File \"build_workbook.py\", line 1, in <module>\\n')\n"
        "sys.stderr.write('ValueError: household config is missing plan_start\\n')\n"
        "sys.exit(1)\n"
    ))
    assert "ValueError: household config is missing plan_start" in job["result"]["error"]
    assert job["detail"] == "Build process returned an error."


def test_build_subprocess_success_without_summary_is_not_reported_as_success(tmp_path):
    """A subprocess that exits 0 but writes no plan_summary.json (e.g. it
    crashed before the summary-writing step but still exited cleanly, or
    wrote outputs to the wrong directory) must NOT be reported as a
    successful build -- see build_service.interpret_build_result's own
    `bool(summary)` requirement."""
    job = _run_job(tmp_path, "print('did nothing useful')\n")
    assert job["status"] == "failed"
    assert job["result"]["success"] is False
    assert "no current plan_summary.json" in job["result"]["error"]


def test_build_subprocess_timeout_surfaces_a_failed_job_not_a_hang(tmp_path):
    """A build that runs past timeout_seconds is killed and reported as
    "Build timed out", not left to hang or misreported as a generic
    failure.

    The script below prints a heartbeat line every 0.1s: run_build_progress_
    job's timeout check only runs BETWEEN calls to the blocking
    proc.stdout.readline(), so a genuinely silent child (no output at all
    for longer than timeout_seconds) would block inside that one readline()
    call and never get a chance to hit the timeout check until it exits on
    its own -- a real edge case this test deliberately avoids hitting, to
    test the intended/documented timeout behavior rather than that gap.
    Whether a silent-child build can ever actually run past timeout_seconds
    in production (the real build script always prints progress lines) is
    a separate question from what this test locks in.
    """
    job = _run_job(tmp_path, (
        "import time\n"
        "for _ in range(50):\n"
        "    print('heartbeat', flush=True)\n"
        "    time.sleep(0.1)\n"
    ), timeout_seconds=1)
    assert job["status"] == "failed"
    assert job["phase"] == "Build timed out"
    assert "timed out" in job["result"]["error"].lower()


def test_successful_build_writes_a_matching_summary_and_is_reported_as_success(tmp_path):
    """Control case: a script that exits 0 and writes a plan_summary.json
    naming this exact build ID is reported as a real success, not swept up
    by the same failure path the tests above exercise."""
    output_marker = str(tmp_path / "output" / "plan_summary.json").replace("\\", "\\\\")
    job = _run_job(tmp_path, (
        "import json, os\n"
        f"json.dump({{'qc_result': 'PASS', 'build_id': os.environ['RETIREMENT_SYSTEM_BUILD_ID']}}, open(r'{output_marker}', 'w'))\n"
        "print('QC: PASS')\n"
    ))
    assert job["status"] == "done"
    assert job["result"]["success"] is True


# ─────────────────────────────────────────────────────────────────────────────
# Malformed-input rejection at the route layer (no subprocess involved)
# ─────────────────────────────────────────────────────────────────────────────

def test_build_start_route_rejects_the_retired_direct_csv_payload_shape():
    resp = app.test_client().post(
        "/api/build/start",
        json={"csv_content": "Section,Subsection,Label,Value\n"},
        headers=HEADERS,
    )
    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["success"] is False
    assert "no longer accepted" in payload["error"]


def test_build_progress_route_returns_404_for_an_unknown_job_id():
    resp = app.test_client().get("/api/build/progress/not-a-real-job-id", headers=HEADERS)
    assert resp.status_code == 404
    payload = resp.get_json()
    assert payload["success"] is False


def test_build_events_snapshot_route_returns_404_for_an_unknown_job_id():
    resp = app.test_client().get("/api/build/events/not-a-real-job-id/snapshot", headers=HEADERS)
    assert resp.status_code == 404
    payload = resp.get_json()
    assert payload["success"] is False
