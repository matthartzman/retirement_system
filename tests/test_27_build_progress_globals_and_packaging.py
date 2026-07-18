from pathlib import Path

from _decomp_dashboard import dashboard_js_text

ROOT = Path(__file__).resolve().parents[1]
WORKBOOK_ROUTES = ROOT / "src" / "server" / "workbook_routes.py"
BUILD_JOB_SERVICE = ROOT / "src" / "server_services" / "build_job_service.py"
PACKAGE_SCRIPT = ROOT / "tools" / "build_release_package.py"
CHECK_PACKAGE = ROOT / "tools" / "check_package_clean.py"


def test_build_progress_route_delegates_to_feature_service_registry():
    route_text = WORKBOOK_ROUTES.read_text(encoding="utf-8")
    service_text = BUILD_JOB_SERVICE.read_text(encoding="utf-8")
    for token in [
        "build_job_service",
        "_BUILD_JOBS = build_job_service.BuildJobRegistry()",
        "def _build_job_snapshot",
        "def _update_build_job",
        "def build_progress",
    ]:
        assert token in route_text
    for token in [
        "class BuildJobRegistry",
        "threading.RLock()",
        "self._jobs:",
        "def run_build_progress_job",
    ]:
        assert token in service_text
    assert "_BUILD_PROGRESS_LOCK" not in route_text
    assert "_BUILD_PROGRESS_JOBS" not in route_text


def test_release_package_script_permanently_excludes_input_folder_and_checks_globals():
    text = PACKAGE_SCRIPT.read_text(encoding="utf-8")
    assert '"input"' in text
    assert '".claude"' in text
    assert '"data"' in text
    assert '"local_state"' in text
    assert '"saved_plans"' in text
    assert "EXCLUDED_DIR_NAMES" in text
    assert "input/ Plan Data folder is excluded" in text
    assert "_run_prepackage_checks(stage)" in text
    assert "Missing build-job service definitions" in text
    assert "check_package_clean.py" in text


def test_package_clean_still_rejects_input_folder():
    text = CHECK_PACKAGE.read_text(encoding="utf-8")
    assert "Packaged release must not include input/ Plan Data" in text
    assert "Secure release package must not include desktop/webview profile data" in text
    assert "Secure release package must not include saved plan snapshots" in text
    assert "Secure release package must not include local SQLite/runtime state" in text


def test_server_build_progress_uses_unbuffered_subprocess_and_zero_pct_start():
    route_text = WORKBOOK_ROUTES.read_text(encoding="utf-8")
    service_text = BUILD_JOB_SERVICE.read_text(encoding="utf-8")
    combined = route_text + "\n" + service_text
    assert '[sys.executable, "-u", str(build_script)]' in service_text
    assert 'build_env["PYTHONUNBUFFERED"] = "1"' in service_text
    assert 'stderr=subprocess.STDOUT' in service_text
    assert 'progress = 0' in service_text
    assert '"progress": 0' in combined
    assert '"progress": 30' not in service_text
    assert '"progress": 2' not in service_text


def test_client_build_progress_starts_at_zero_and_polls_smoothly():
    text = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8") + "\n" + dashboard_js_text()
    assert 'let lastProgress = Math.max(0, Number(started.progress) || 0)' in text
    assert 'sleep(i < 40 ? 750 : 1500)' in text
    assert '${buildOverlayExpectedLabel' in text
    assert "Number(started.progress)||2" not in text
    assert "Math.max(30" not in text


def test_build_result_carries_build_id_and_rejects_stale_summary():
    route_text = WORKBOOK_ROUTES.read_text(encoding="utf-8")
    builder_text = (ROOT / "src" / "reporting" / "workbook_builder.py").read_text(encoding="utf-8")
    assert "RETIREMENT_SYSTEM_BUILD_ID" in route_text
    assert "_clear_current_build_outputs" in route_text
    assert "_summary_matches_build" in route_text
    assert "stale_summary" in route_text
    assert "plan_input_fingerprint" in builder_text
    assert "roth_heard" in builder_text


def test_vectorized_monte_carlo_emits_progress_lines():
    text = (ROOT / "src" / "planning_engines.py").read_text(encoding="utf-8")
    assert "Monte Carlo vectorized batch: sampling" in text
    assert "Monte Carlo vectorized batch: main batch complete" in text
    assert "Monte Carlo sensitivity grid:" in text
