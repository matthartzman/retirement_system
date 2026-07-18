from __future__ import annotations
"""Build execution strategy: subprocess (desktop) vs in-process (mobile).

The workbook build historically ran only as a subprocess:
``subprocess.run([sys.executable, "tools/build_workbook.py"])``. Android hosts
cannot spawn a second interpreter, so the build must be able to run in-process
on a worker thread. This module provides the in-process runner and the
capability-driven selection helper. The subprocess path stays inline at its two
call sites (sync ``/api/build`` and the async progress job) and remains the
default, so desktop behavior is byte-identical.

The in-process runner returns a :class:`BuildOutcome` that mirrors the attribute
surface of ``subprocess.CompletedProcess`` (``returncode``/``stdout``/
``stderr``) so the downstream summary/QC handling is identical regardless of how
the build ran. On timeout it raises ``subprocess.TimeoutExpired``, matching the
subprocess contract the call sites already catch.
"""

import contextlib
import io
import os
import subprocess
import threading
from dataclasses import dataclass
from typing import Callable, Optional

try:
    from .. import platform_runtime
    from ..build_entry import run_build as _run_build
except ImportError:  # direct execution fallback
    from src import platform_runtime
    from src.build_entry import run_build as _run_build


@dataclass(frozen=True)
class BuildOutcome:
    """Result of an in-process build, shaped like ``subprocess.CompletedProcess``."""

    returncode: int
    stdout: str
    stderr: str


def should_run_in_process() -> bool:
    """True when builds should run in-process instead of via subprocess.

    Driven by :func:`platform_runtime.build_mode`, which defaults to subprocess
    on any host that can spawn a process (desktop/server) and switches to
    in-process on mobile.
    """
    return platform_runtime.build_mode() == "inprocess"


class _LineCapture(io.TextIOBase):
    """Text sink that accumulates output and streams complete lines to a callback.

    Used to give the in-process build the same line-oriented progress surface the
    subprocess path gets from ``proc.stdout.readline()``.
    """

    def __init__(self, on_line: Optional[Callable[[str], None]] = None):
        super().__init__()
        self._on_line = on_line
        self._chunks: list[str] = []
        self._pending = ""
        self._lock = threading.Lock()

    def write(self, text: str) -> int:  # type: ignore[override]
        if not text:
            return 0
        with self._lock:
            self._chunks.append(text)
            self._pending += text
            while "\n" in self._pending:
                line, self._pending = self._pending.split("\n", 1)
                if self._on_line is not None:
                    try:
                        self._on_line(line + "\n")
                    except Exception:
                        pass
        return len(text)

    def flush(self) -> None:  # noqa: D401 - stream contract
        return None

    def getvalue(self) -> str:
        with self._lock:
            return "".join(self._chunks)


def run_inprocess_build(
    *,
    env: Optional[dict] = None,
    on_line: Optional[Callable[[str], None]] = None,
    timeout: Optional[float] = None,
) -> BuildOutcome:
    """Run a full workbook build in-process, capturing stdout/stderr.

    ``env`` fully replaces ``os.environ`` for the duration of the build (and is
    restored afterward), matching what a subprocess would have seen. ``on_line``
    receives each complete stdout line as it is produced, for progress updates.

    Raises ``subprocess.TimeoutExpired`` if the build does not finish within
    ``timeout`` seconds. A Python thread cannot be force-killed, so on timeout the
    build thread is abandoned as a daemon; the mobile shell is expected to treat a
    timed-out build as fatal and restart, exactly as it would a killed process.
    """
    capture = _LineCapture(on_line)
    result: dict[str, int] = {}

    def _target() -> None:
        try:
            with contextlib.redirect_stdout(capture), contextlib.redirect_stderr(capture):
                outcome = _run_build()
            result["returncode"] = int(outcome.returncode)
        except SystemExit as exc:  # a bare SystemExit from deep in the pipeline
            try:
                result["returncode"] = int(exc.code) if exc.code is not None else 0
            except (TypeError, ValueError):
                result["returncode"] = 1
        except BaseException as exc:  # surface the failure like a non-zero exit
            capture.write(f"\nBuild error: {exc.__class__.__name__}: {exc}\n")
            result["returncode"] = 1

    original_env = dict(os.environ)
    thread = threading.Thread(target=_target, name="inprocess-build", daemon=True)
    try:
        if env is not None:
            os.environ.clear()
            os.environ.update(env)
        thread.start()
        thread.join(timeout)
    finally:
        os.environ.clear()
        os.environ.update(original_env)

    if thread.is_alive():
        raise subprocess.TimeoutExpired("in-process build", timeout or 0)

    return BuildOutcome(returncode=result.get("returncode", 1), stdout=capture.getvalue(), stderr="")
