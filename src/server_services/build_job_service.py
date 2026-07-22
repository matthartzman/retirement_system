from __future__ import annotations

import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

try:
    from . import build_runner
except ImportError:  # direct execution fallback
    from src.server_services import build_runner

CURRENT_BUILD_OUTPUT_FILES = [
    "plan_summary.json",
    "retirement_plan.xlsx",
    "retirement_plan.pdf",
    "retirement_dashboard.html",
    "results_explorer_model.json",
    "build_snapshot.json",
    "forecast_package.json",
]


def clear_current_build_outputs(output_dir: Path, filenames: list[str] | tuple[str, ...] | None = None) -> None:
    """Remove current-build artifacts before launching a new build.

    This prevents stale KPI/output files from being mistaken for the build that is
    about to start.  Failure to clear is intentionally non-fatal because the
    later build-id and stale-summary checks are the authoritative protection.
    """
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        for name in list(filenames or CURRENT_BUILD_OUTPUT_FILES):
            p = output_dir / name
            if p.exists() and p.is_file():
                p.unlink()
    except Exception:
        pass


def summary_matches_build(summary: dict[str, Any], build_id: str) -> bool:
    if not build_id:
        return True
    return str((summary or {}).get("build_id") or "") == str(build_id)


def friendly_build_detail(low: str, fallback: str = "Working through the build steps...") -> str:
    """Return user-facing progress detail with no filenames or sheet numbers."""
    if "loading active configuration" in low:
        return "Reading the saved plan settings."
    if "using config backend" in low or "output directory:" in low:
        return "Preparing the build environment."
    if "live market pricing" in low or "etf prices" in low:
        return "Refreshing account values and market-price assumptions."
    if "parsing client data" in low:
        return "Reading household, income, spending, holdings, and policy inputs."
    if "selected roth strategy" in low or "plan horizon" in low:
        return "Normalizing planning assumptions before the projection starts."
    if "running projection" in low:
        return "Projecting year-by-year cash flow, taxes, withdrawals, and account balances."
    if "monte carlo exact scalar paths" in low:
        return "Testing retirement paths with the advanced exact Monte Carlo engine."
    if "monte carlo vectorized batch" in low:
        return "Testing retirement paths with the quick vectorized Monte Carlo engine."
    if "monte carlo sensitivity grid" in low:
        return "Checking how results change under different return and risk assumptions."
    if "validation fail" in low:
        return "Checking projection consistency before workbook output."
    if low == "building workbook...":
        return "Creating workbook pages."
    if "sheet " in low:
        return "Writing workbook pages."
    if "saving to" in low or "workbook saved" in low:
        return "Saving the finished workbook."
    if "xml patch" in low:
        return "Making the workbook compatible with Excel viewers."
    if "qc:" in low:
        return "Running quality checks on the finished workbook."
    if "building html dashboard" in low or "schema-driven ui" in low:
        return "Refreshing the dashboard output."
    if "building pdf report" in low:
        return "Creating the optional PDF report."
    if "building ml forecast" in low or "forecast package" in low:
        return "Creating the optional forecast package."
    if low == "done!" or low.startswith("done!"):
        return "Finalizing build results."
    return fallback


def build_progress_from_line(line: str, current: int) -> tuple[int, str, str]:
    """Map build stdout lines to user-facing progress."""
    text = (line or "").strip()
    low = text.lower()
    pct = current
    title = "Building workbook"
    detail = friendly_build_detail(low)
    if "loading active configuration" in low:
        pct, title = max(current, 5), "Loading settings"
    elif "using config backend" in low or "output directory:" in low:
        pct, title = max(current, 8), "Preparing build"
    elif "live market pricing" in low or "etf prices" in low:
        pct, title = max(current, 14), "Updating account values"
    elif "parsing client data" in low:
        pct, title = max(current, 20), "Reading Plan Data"
    elif "selected roth strategy" in low or "plan horizon" in low:
        pct, title = max(current, 26), "Preparing assumptions"
    elif "running projection" in low:
        pct, title = max(current, 32), "Running projection"
    elif "monte carlo exact scalar paths" in low:
        m = re.search(r"paths:\s*(\d+)\s*/\s*(\d+)", low)
        if m:
            done, total = int(m.group(1)), max(1, int(m.group(2)))
            pct = max(current, min(70, 34 + int(36 * done / total)))
        else:
            pct = max(current, 36)
        title = "Running Monte Carlo"
    elif "monte carlo vectorized batch" in low:
        if "main batch complete" in low:
            pct = max(current, 62)
        elif "sensitivity" in low:
            pct = max(current, 70)
        else:
            pct = max(current, 42)
        title = "Running Monte Carlo"
    elif "monte carlo sensitivity grid" in low:
        m = re.search(r"grid:\s*(\d+)\s*/\s*(\d+)", low)
        if m:
            done, total = int(m.group(1)), max(1, int(m.group(2)))
            pct = max(current, min(89, 70 + int(19 * done / total)))
        else:
            pct = max(current, 72)
        title = "Running risk sensitivity"
    elif "validation fail" in low:
        pct, title = max(current, 81), "Checking projection"
    elif low == "building workbook...":
        pct, title = max(current, 82), "Creating workbook"
    elif "sheet " in low:
        m = re.search(r"sheet\s+(\d+)", low)
        if m:
            sheet = min(25, max(1, int(m.group(1))))
            pct = max(current, min(89, 82 + int(sheet * 0.28)))
        else:
            pct = max(current, 84)
        title = "Writing workbook pages"
    elif "saving to" in low:
        pct, title = max(current, 90), "Saving workbook"
    elif "xml patch" in low:
        pct, title = max(current, 91), "Finalizing workbook"
    elif "workbook saved" in low:
        pct, title = max(current, 92), "Workbook saved"
    elif "qc:" in low:
        pct, title = max(current, 94), "Running quality checks"
    elif "building html dashboard" in low or "schema-driven ui" in low:
        pct, title = max(current, 96), "Refreshing dashboard"
    elif "building pdf report" in low:
        pct, title = max(current, 97), "Creating PDF report"
    elif "building ml forecast" in low or "forecast package" in low:
        pct, title = max(current, 98), "Creating forecast package"
    elif low == "done!" or low.startswith("done!"):
        pct, title = max(current, 99), "Finalizing build"
    return int(max(current, min(99, pct))), title, detail


class BuildJobRegistry:
    """Thread-safe local build job registry with optional desktop push callbacks."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._push_callback: Callable[[dict[str, Any]], None] | None = None

    def register_push_callback(self, callback: Callable[[dict[str, Any]], None] | None) -> None:
        self._push_callback = callback

    def create(self, job_id: str, *, created_at: float) -> dict[str, Any]:
        payload = {
            "job_id": job_id,
            "status": "starting",
            "progress": 0,
            "phase": "Preparing build",
            "detail": "Preparing workbook build process...",
            "created_at": created_at,
        }
        with self._lock:
            self._jobs[job_id] = dict(payload)
        return dict(payload)

    def snapshot(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            return dict(self._jobs.get(job_id) or {})

    def update(self, job_id: str, **kwargs: Any) -> None:
        push_data: dict[str, Any] | None = None
        with self._lock:
            job = self._jobs.setdefault(job_id, {})
            old_progress = int(job.get("progress") or 0)
            job.update(kwargs)
            job["updated_at"] = time.time()
            events = job.setdefault("events", [])
            if any(k in kwargs for k in ("status", "progress", "phase", "detail", "result")):
                events.append({
                    "job_id": job_id,
                    "sequence": len(events) + 1,
                    "event_type": "completed" if kwargs.get("status") == "done" else "failed" if kwargs.get("status") == "failed" else "progress",
                    "phase": str(job.get("phase") or "Build progress"),
                    "progress": int(job.get("progress") if job.get("progress") is not None else old_progress),
                    "detail": str(job.get("detail") or ""),
                    "timestamp": time.time(),
                })
                status = job.get("status")
                push_data = {
                    "job_id": job_id,
                    "status": status,
                    "progress": job.get("progress"),
                    "phase": job.get("phase"),
                    "detail": job.get("detail"),
                    "result": job.get("result") if status in ("done", "failed") else None,
                }

        if push_data is not None and self._push_callback is not None:
            try:
                self._push_callback(push_data)
            except Exception:
                pass

    def find_latest_for_wait(self, timeout_seconds: float = 0.0) -> dict[str, Any]:
        deadline = time.time() + max(0.0, timeout_seconds)
        while True:
            with self._lock:
                candidates = sorted(self._jobs.values(), key=lambda j: float(j.get("created_at") or 0), reverse=True)
                for candidate in candidates:
                    if candidate.get("status") in ("starting", "running", "done", "failed"):
                        return dict(candidate)
            if time.time() >= deadline:
                return {}
            time.sleep(0.1)

    def prune_older_than(self, seconds: float) -> None:
        cutoff = time.time() - max(0.0, seconds)
        with self._lock:
            for old_id, old_job in list(self._jobs.items()):
                if float(old_job.get("updated_at") or old_job.get("created_at") or 0) < cutoff:
                    self._jobs.pop(old_id, None)


def extract_build_failure_message(returncode: int, stdout: str = "", stderr: str = "") -> str:
    """Return a concise actionable build failure without masking it as missing summary."""
    text = "\n".join([str(stderr or ""), str(stdout or "")]).strip()
    if not text:
        return f"Build process exited with code {returncode}."
    for line in reversed(text.splitlines()):
        clean = line.strip()
        if not clean:
            continue
        if re.match(r"^[A-Za-z_][A-Za-z0-9_.]*(Error|Exception):", clean):
            if clean.startswith("PermissionError") and "retirement_plan.xlsx" in clean:
                return clean + " — close Excel (or any app with retirement_plan.xlsx open) and try again."
            return clean
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    tail = lines[-1] if lines else text
    return tail[-800:]


def build_error_message(returncode: int, summary: dict[str, Any], stale_summary: bool, stdout: str = "", stderr: str = "") -> str:
    if returncode != 0:
        detail = extract_build_failure_message(returncode, stdout, stderr)
        return f"Build failed before producing a current plan_summary.json: {detail}"
    if stale_summary:
        return "Build completed, but the KPI summary belonged to an older build. Re-run after confirming Plan Data is saved."
    if not summary:
        return "Build completed, but no current plan_summary.json was produced. This usually means the build wrote outputs somewhere unexpected or stopped before the summary-writing step."
    return ""


def run_build_progress_job(
    *,
    registry: BuildJobRegistry,
    job_id: str,
    workspace_id: str,
    client_id: str,
    env: dict[str, str],
    output_dir: Path,
    build_script: Path,
    base_dir: Path,
    previous_build_ts: float,
    build_start_ts: float,
    timeout_seconds: int,
    redact_logs: bool,
    admin_changes_between: Callable[[str, float, float], list[dict[str, Any]]],
    write_last_build_metadata: Callable[[str, dict[str, Any]], None],
    redact_text: Callable[[str], str],
    interpret_build_result: Callable[..., Any],
) -> None:
    stdout_lines: list[str] = []
    stderr_text = ""
    progress = 0
    start = time.time()
    registry.update(job_id, status="running", progress=progress, phase="Starting build", detail="Launching the workbook build.")
    try:
        if build_runner.should_run_in_process():
            # Mobile hosts cannot spawn a second interpreter; run the same build
            # logic in-process, streaming stdout lines to the progress registry
            # exactly as the subprocess readline loop does.
            progress_state = {"value": progress}

            def _on_line(line: str) -> None:
                stdout_lines.append(line)
                p, title, detail = build_progress_from_line(line, progress_state["value"])
                progress_state["value"] = p
                registry.update(job_id, status="running", progress=p, phase=title, detail=detail, stdout_tail="".join(stdout_lines)[-4000:])

            outcome = build_runner.run_inprocess_build(env=env, on_line=_on_line, timeout=timeout_seconds)
            returncode = outcome.returncode
            stderr_text = outcome.stderr
        else:
            build_env = dict(env)
            build_env["PYTHONUNBUFFERED"] = "1"
            build_cmd = [sys.executable, str(build_script)] if getattr(sys, "frozen", False) else [sys.executable, "-u", str(build_script)]
            proc = subprocess.Popen(
                build_cmd,
                cwd=str(base_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=build_env,
                bufsize=1,
            )
            assert proc.stdout is not None
            while True:
                if time.time() - start > timeout_seconds:
                    proc.kill()
                    raise subprocess.TimeoutExpired(str(build_script), timeout_seconds)
                line = proc.stdout.readline()
                if line:
                    stdout_lines.append(line)
                    progress, title, detail = build_progress_from_line(line, progress)
                    registry.update(job_id, status="running", progress=progress, phase=title, detail=detail, stdout_tail="".join(stdout_lines)[-4000:])
                elif proc.poll() is not None:
                    break
                else:
                    time.sleep(0.15)
            remaining_out, stderr_text = proc.communicate(timeout=2)
            if remaining_out:
                for line in remaining_out.splitlines(True):
                    stdout_lines.append(line)
                    progress, title, detail = build_progress_from_line(line, progress)
                    registry.update(job_id, status="running", progress=progress, phase=title, detail=detail, stdout_tail="".join(stdout_lines)[-4000:])
            returncode = proc.returncode
        elapsed = round(time.time() - start, 1)
        stdout = "".join(stdout_lines)
        build_id = str(env.get("RETIREMENT_SYSTEM_BUILD_ID", "") or "")
        outcome = interpret_build_result(
            returncode=returncode,
            stdout=stdout,
            output_dir=output_dir,
            build_id=build_id,
            stderr=stderr_text,
        )
        finished_ts = time.time()
        admin_changes = admin_changes_between(workspace_id, previous_build_ts, build_start_ts)
        result_payload = {
            "success": outcome.success,
            "returncode": returncode,
            "elapsed_seconds": elapsed,
            "qc_result": outcome.qc_result,
            "kpi": outcome.summary,
            "output_dir": str(output_dir),
            "admin_changes": admin_changes,
            "previous_build_ts": previous_build_ts,
            "build_started_at_ts": build_start_ts,
            "build_finished_at_ts": finished_ts,
            "stdout": redact_text(stdout[-3000:]) if redact_logs else stdout[-3000:],
            "stderr": redact_text((stderr_text or "")[-1000:]) if redact_logs else (stderr_text or "")[-1000:],
        }
        if outcome.error_message:
            result_payload["error"] = outcome.error_message
        if outcome.success:
            write_last_build_metadata(workspace_id, {"finished_at_ts": finished_ts, "client_id": client_id, "job_id": job_id, "elapsed_seconds": elapsed, "qc_result": result_payload["qc_result"]})
        registry.update(job_id, status="done" if outcome.success else "failed", progress=100, phase="Build complete" if outcome.success else "Build failed", detail=result_payload["qc_result"] if outcome.success else (result_payload["stderr"] or "Build process returned an error."), result=result_payload)
    except subprocess.TimeoutExpired:
        payload = {"success": False, "error": f"Build timed out after {timeout_seconds} seconds"}
        registry.update(job_id, status="failed", progress=100, phase="Build timed out", detail=payload["error"], result=payload)
    except Exception as exc:
        payload = {"success": False, "error": str(exc)}
        registry.update(job_id, status="failed", progress=100, phase="Build failed", detail=str(exc), result=payload)
