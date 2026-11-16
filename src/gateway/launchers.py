"""How a user's worker process is started: the same-account launcher (CI, development) and the
per-account launcher (one Windows account per user, the production setting).

Both start the worker suspended, put it in its own kill-on-close Job Object with a memory cap, and
only then resume it, so no child (the build, its process pool) can ever start outside the job. Both
pass no handles to the worker: it writes its own console log and port file inside its workspace.
"""
from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

from . import winapi

LOG = logging.getLogger("retirement.gateway.launchers")

# The OS essentials a worker gets from the identity it runs as. Everything else is set explicitly by
# the supervisor (token, workspace temp folder, pool cap, provider key); nothing else is inherited.
OS_ENV_KEYS = (
    "SYSTEMROOT", "WINDIR", "SYSTEMDRIVE", "COMSPEC", "PATH", "PATHEXT", "NUMBER_OF_PROCESSORS",
    "PROCESSOR_ARCHITECTURE", "PROCESSOR_IDENTIFIER", "PROCESSOR_LEVEL", "PROCESSOR_REVISION", "OS",
    "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "USERNAME", "USERDOMAIN", "LOCALAPPDATA", "APPDATA",
    "PROGRAMDATA", "PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMW6432", "COMMONPROGRAMFILES",
    "COMMONPROGRAMFILES(X86)", "COMMONPROGRAMW6432", "ALLUSERSPROFILE", "COMPUTERNAME",
)


def os_env(source: dict[str, str]) -> dict[str, str]:
    wanted = set(OS_ENV_KEYS)
    return {k: v for k, v in source.items() if k.upper() in wanted}


@dataclass(frozen=True)
class LaunchSpec:
    user_id: int
    argv: list[str]
    cwd: Path
    env: dict[str, str]  # pinned values, laid over the identity's OS essentials
    memory_limit_bytes: int | None = None
    active_process_limit: int | None = None


@dataclass
class WorkerProcess:
    """A started worker. ``kill()`` closes its job, which ends the whole process tree."""

    pid: int
    job: winapi.Job | None
    method: str
    _poll: Callable[[], int | None]
    _cleanup: list[Callable[[], None]] = field(default_factory=list)
    _done: bool = False

    def poll(self) -> int | None:
        return self._poll()

    def kill(self) -> None:
        if self._done:
            return
        self._done = True
        if self.job is not None:
            self.job.close()
        for fn in self._cleanup:
            try:
                fn()
            except Exception:  # pragma: no cover - best effort release of handles and the profile
                LOG.warning("worker cleanup step failed for pid %s", self.pid, exc_info=True)


class WorkerLauncher(Protocol):
    name: str

    def launch(self, spec: LaunchSpec) -> WorkerProcess: ...


def _new_job(spec: LaunchSpec) -> winapi.Job | None:
    if not winapi.IS_WINDOWS:
        return None
    return winapi.Job(memory_limit_bytes=spec.memory_limit_bytes, active_process_limit=spec.active_process_limit)


class SameAccountLauncher:
    """Starts the worker as the gateway's own account. Isolation between users then rests on the
    per-worker token and the gateway alone; used by CI and development."""

    name = "same-account"

    def __init__(self, base_env: dict[str, str] | None = None) -> None:
        self._base = os_env(dict(os.environ if base_env is None else base_env))

    def launch(self, spec: LaunchSpec) -> WorkerProcess:
        env = {**self._base, **spec.env}
        flags = 0
        if winapi.IS_WINDOWS:
            flags = winapi.CREATE_SUSPENDED | winapi.CREATE_NO_WINDOW | winapi.CREATE_NEW_PROCESS_GROUP
        proc = subprocess.Popen(spec.argv, cwd=str(spec.cwd), env=env, creationflags=flags, close_fds=True,
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        job = None
        try:
            job = _new_job(spec)
            if job is not None:
                handle = int(proc._handle)  # type: ignore[attr-defined]  # Popen's process handle on Windows
                job.assign(handle)
                winapi.resume_process(handle)
        except Exception:
            proc.kill()
            if job is not None:
                job.close()
            raise
        return WorkerProcess(proc.pid, job, self.name, proc.poll, [lambda: _reap(proc)])


def _reap(proc: subprocess.Popen) -> None:
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:  # pragma: no cover - the job close already killed it
        proc.kill()


class AccountCredentials(Protocol):
    def credentials(self, user_id: int) -> tuple[str, str]: ...


class PerAccountLauncher:
    """Starts the worker as the user's own Windows account: batch logon (type 4; type 2 conflicts with
    the deny-interactive right), profile loaded (so Credential Manager is that account's), the
    account's own environment block, then ``CreateProcessAsUserW`` suspended into the job."""

    name = "per-account"

    def __init__(self, accounts: AccountCredentials) -> None:
        if not winapi.IS_WINDOWS:
            raise OSError("the per-account launcher needs Windows")
        self._accounts = accounts

    def launch(self, spec: LaunchSpec) -> WorkerProcess:
        username, password = self._accounts.credentials(spec.user_id)
        token = winapi.logon(username, password, winapi.LOGON32_LOGON_BATCH)
        del password
        cleanup: list[Callable[[], None]] = []
        profile = None
        started = None
        job = None
        try:
            profile = winapi.load_profile(token, username)
            env = {**os_env(winapi.environment_block(token)), **spec.env}
            started = winapi.create_process_as(token, subprocess.list2cmdline(spec.argv), cwd=str(spec.cwd), env=env)
            job = _new_job(spec)
            assert job is not None
            job.assign(started.process_handle)
            winapi.resume_thread(started.thread_handle)
        except Exception:
            if started is not None:
                winapi.terminate_process(started.process_handle)
                winapi.close_handle(started.process_handle)
                winapi.close_handle(started.thread_handle)
            if job is not None:
                job.close()
            if profile is not None:
                profile.unload()
            winapi.close_handle(token)
            raise
        winapi.close_handle(started.thread_handle)
        ph = started.process_handle

        def _release() -> None:
            profile.unload()
            winapi.close_handle(token)
            winapi.close_handle(ph)

        cleanup.append(_release)
        LOG.info("worker for user %s started as its own account (%s)", spec.user_id, started.method)
        return WorkerProcess(started.pid, job, f"{self.name}:{started.method}", lambda: winapi.process_exit_code(ph),
                             cleanup)
