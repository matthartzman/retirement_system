"""Win32 calls the supervisor needs, through ``ctypes`` only (no ``pywin32``; Phase 0 decision).

Job Objects with kill-on-close and a memory cap, starting a process suspended and resuming it once it
is in its job, the owner of a listening TCP port, SIDs, DPAPI, and the batch logon plus
``CreateProcessAsUserW`` used by the per-account launcher. Everything here is a thin wrapper that raises
``OSError(winerror)`` on failure; policy lives in the callers. Importing this module on a non-Windows
system works, but the functions raise ``OSError``.
"""
from __future__ import annotations

import ctypes
import os
import socket
from ctypes import wintypes as w
from dataclasses import dataclass

IS_WINDOWS = os.name == "nt"

# Process creation flags.
CREATE_SUSPENDED = 0x00000004
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_UNICODE_ENVIRONMENT = 0x00000400
CREATE_NO_WINDOW = 0x08000000
LOGON_WITH_PROFILE = 0x00000001
# Job limits.
JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x00000008
JOB_OBJECT_LIMIT_JOB_MEMORY = 0x00000200
JOB_OBJECT_LIMIT_DIE_ON_UNHANDLED_EXCEPTION = 0x00000400
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
_JOB_BASIC_ACCOUNTING = 1
_JOB_EXTENDED_LIMIT = 9
# Logon.
LOGON32_LOGON_INTERACTIVE = 2
LOGON32_LOGON_BATCH = 4
LOGON32_PROVIDER_DEFAULT = 0
ERROR_PRIVILEGE_NOT_HELD = 1314
ERROR_LOGON_TYPE_NOT_GRANTED = 1385
_PROCESS_ALL_ACCESS = 0x1F0FFF
_PROCESS_QUERY_LIMITED = 0x1000
_TOKEN_QUERY = 0x0008
_TOKEN_USER = 1
_PI_NOUI = 1


def _dll(name: str):
    if not IS_WINDOWS:
        raise OSError(f"{name} is only available on Windows")
    return ctypes.WinDLL(name, use_last_error=True)


def _fail(what: str) -> OSError:
    code = ctypes.get_last_error()
    return OSError(code, f"{what} failed (Windows error {code})", None, code)


class _BASIC_LIMIT(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", w.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", w.DWORD),
                ("Affinity", ctypes.c_size_t), ("PriorityClass", w.DWORD), ("SchedulingClass", w.DWORD)]


class _IO_COUNTERS(ctypes.Structure):
    _fields_ = [(n, ctypes.c_uint64) for n in ("r", "w", "o", "rb", "wb", "ob")]


class _EXTENDED_LIMIT(ctypes.Structure):
    _fields_ = [("BasicLimitInformation", _BASIC_LIMIT), ("IoInfo", _IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]


class _BASIC_ACCOUNTING(ctypes.Structure):
    _fields_ = [("TotalUserTime", ctypes.c_int64), ("TotalKernelTime", ctypes.c_int64),
                ("ThisPeriodTotalUserTime", ctypes.c_int64), ("ThisPeriodTotalKernelTime", ctypes.c_int64),
                ("TotalPageFaultCount", w.DWORD), ("TotalProcesses", w.DWORD), ("ActiveProcesses", w.DWORD),
                ("TotalTerminatedProcesses", w.DWORD)]


def _kernel32():
    k = _dll("kernel32")
    k.CreateJobObjectW.restype = w.HANDLE
    k.CreateJobObjectW.argtypes = [ctypes.c_void_p, w.LPCWSTR]
    k.OpenProcess.restype = w.HANDLE
    k.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
    k.CloseHandle.argtypes = [w.HANDLE]
    k.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
    k.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
    k.QueryInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD, ctypes.c_void_p]
    k.IsProcessInJob.argtypes = [w.HANDLE, w.HANDLE, ctypes.POINTER(w.BOOL)]
    k.TerminateJobObject.argtypes = [w.HANDLE, w.UINT]
    k.ResumeThread.argtypes = [w.HANDLE]
    k.ResumeThread.restype = w.DWORD
    k.TerminateProcess.argtypes = [w.HANDLE, w.UINT]
    k.GetExitCodeProcess.argtypes = [w.HANDLE, ctypes.POINTER(w.DWORD)]
    k.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
    k.WaitForSingleObject.restype = w.DWORD
    k.GetCurrentProcess.restype = w.HANDLE
    k.LocalFree.argtypes = [ctypes.c_void_p]
    return k


# ---- Job Objects ---------------------------------------------------------------------------------

class Job:
    """A kill-on-close Job Object. Closing it (``close()``, or this process ending) kills every process in it."""

    def __init__(self, *, memory_limit_bytes: int | None = None, active_process_limit: int | None = None) -> None:
        k = _kernel32()
        handle = k.CreateJobObjectW(None, None)
        if not handle:
            raise _fail("CreateJobObjectW")
        info = _EXTENDED_LIMIT()
        flags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE | JOB_OBJECT_LIMIT_DIE_ON_UNHANDLED_EXCEPTION
        if memory_limit_bytes:
            flags |= JOB_OBJECT_LIMIT_JOB_MEMORY
            info.JobMemoryLimit = int(memory_limit_bytes)
        if active_process_limit:
            flags |= JOB_OBJECT_LIMIT_ACTIVE_PROCESS
            info.BasicLimitInformation.ActiveProcessLimit = int(active_process_limit)
        info.BasicLimitInformation.LimitFlags = flags
        if not k.SetInformationJobObject(handle, _JOB_EXTENDED_LIMIT, ctypes.byref(info), ctypes.sizeof(info)):
            err = _fail("SetInformationJobObject")
            k.CloseHandle(handle)
            raise err
        self._k, self.handle = k, handle
        self.memory_limit_bytes = memory_limit_bytes

    def assign(self, process_handle: int) -> None:
        if not self._k.AssignProcessToJobObject(self.handle, w.HANDLE(process_handle)):
            raise _fail("AssignProcessToJobObject")

    def contains(self, process_handle: int) -> bool:
        result = w.BOOL()
        if not self._k.IsProcessInJob(w.HANDLE(process_handle), self.handle, ctypes.byref(result)):
            raise _fail("IsProcessInJob")
        return bool(result.value)

    def active_processes(self) -> int:
        info = _BASIC_ACCOUNTING()
        if not self._k.QueryInformationJobObject(self.handle, _JOB_BASIC_ACCOUNTING, ctypes.byref(info),
                                                 ctypes.sizeof(info), None):
            raise _fail("QueryInformationJobObject")
        return int(info.ActiveProcesses)

    def peak_memory_bytes(self) -> int:
        info = _EXTENDED_LIMIT()
        if not self._k.QueryInformationJobObject(self.handle, _JOB_EXTENDED_LIMIT, ctypes.byref(info),
                                                 ctypes.sizeof(info), None):
            raise _fail("QueryInformationJobObject")
        return int(info.PeakJobMemoryUsed)

    @property
    def closed(self) -> bool:
        return self.handle is None

    def close(self) -> None:
        """Kill everything in the job and release it."""
        if self.handle is not None:
            self._k.TerminateJobObject(self.handle, 1)
            self._k.CloseHandle(self.handle)
            self.handle = None


def resume_process(process_handle: int) -> None:
    """Resume every thread of a process started with ``CREATE_SUSPENDED`` (``NtResumeProcess``)."""
    ntdll = _dll("ntdll")
    ntdll.NtResumeProcess.argtypes = [w.HANDLE]
    status = ntdll.NtResumeProcess(w.HANDLE(process_handle))
    if status != 0:
        raise OSError(f"NtResumeProcess failed (NTSTATUS {status & 0xFFFFFFFF:#x})")


def resume_thread(thread_handle: int) -> None:
    if _kernel32().ResumeThread(w.HANDLE(thread_handle)) == 0xFFFFFFFF:
        raise _fail("ResumeThread")


# ---- Listening ports -----------------------------------------------------------------------------

class _TCPROW_OWNER_PID(ctypes.Structure):
    _fields_ = [("dwState", w.DWORD), ("dwLocalAddr", w.DWORD), ("dwLocalPort", w.DWORD),
                ("dwRemoteAddr", w.DWORD), ("dwRemotePort", w.DWORD), ("dwOwningPid", w.DWORD)]


def tcp_listener_pids(port: int) -> set[int]:
    """PIDs that hold an IPv4 listening socket on ``port`` on 127.0.0.1 or any address."""
    iphlp = _dll("iphlpapi")
    iphlp.GetExtendedTcpTable.argtypes = [ctypes.c_void_p, ctypes.POINTER(w.DWORD), w.BOOL, w.ULONG, ctypes.c_int,
                                          w.ULONG]
    iphlp.GetExtendedTcpTable.restype = w.DWORD
    size = w.DWORD(0)
    for _ in range(5):
        buf = ctypes.create_string_buffer(max(int(size.value), 4))
        rc = iphlp.GetExtendedTcpTable(buf, ctypes.byref(size), False, socket.AF_INET, 3, 0)  # TCP_TABLE_OWNER_PID_LISTENER
        if rc == 0:
            break
        if rc != 122:  # ERROR_INSUFFICIENT_BUFFER
            raise OSError(rc, f"GetExtendedTcpTable failed (Windows error {rc})", None, rc)
    else:
        raise OSError("GetExtendedTcpTable kept growing")
    count = w.DWORD.from_buffer(buf).value
    rows = (_TCPROW_OWNER_PID * count).from_buffer(buf, ctypes.sizeof(w.DWORD))
    loopback, anyaddr = int.from_bytes(socket.inet_aton("127.0.0.1"), "little"), 0
    out: set[int] = set()
    for row in rows:
        if socket.ntohs(row.dwLocalPort & 0xFFFF) == int(port) and row.dwLocalAddr in (loopback, anyaddr):
            out.add(int(row.dwOwningPid))
    return out


# ---- SIDs and tokens -----------------------------------------------------------------------------

def _advapi():
    a = _dll("advapi32")
    a.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(w.LPWSTR)]
    a.ConvertStringSidToSidW.argtypes = [w.LPCWSTR, ctypes.POINTER(ctypes.c_void_p)]
    a.OpenProcessToken.argtypes = [w.HANDLE, w.DWORD, ctypes.POINTER(w.HANDLE)]
    a.GetTokenInformation.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD, ctypes.POINTER(w.DWORD)]
    a.LookupAccountNameW.argtypes = [w.LPCWSTR, w.LPCWSTR, ctypes.c_void_p, ctypes.POINTER(w.DWORD), w.LPWSTR,
                                     ctypes.POINTER(w.DWORD), ctypes.POINTER(ctypes.c_int)]
    a.LogonUserW.argtypes = [w.LPCWSTR, w.LPCWSTR, w.LPCWSTR, w.DWORD, w.DWORD, ctypes.POINTER(w.HANDLE)]
    a.CreateProcessAsUserW.argtypes = [w.HANDLE, w.LPCWSTR, w.LPWSTR, ctypes.c_void_p, ctypes.c_void_p, w.BOOL,
                                       w.DWORD, ctypes.c_void_p, w.LPCWSTR, ctypes.c_void_p, ctypes.c_void_p]
    a.CreateProcessWithTokenW.argtypes = [w.HANDLE, w.DWORD, w.LPCWSTR, w.LPWSTR, w.DWORD, ctypes.c_void_p,
                                          w.LPCWSTR, ctypes.c_void_p, ctypes.c_void_p]
    return a


def sid_to_string(psid) -> str:
    a, k = _advapi(), _kernel32()
    out = w.LPWSTR()
    if not a.ConvertSidToStringSidW(psid, ctypes.byref(out)):
        raise _fail("ConvertSidToStringSidW")
    try:
        return str(out.value)
    finally:
        k.LocalFree(out)


def token_user_sid(token: int) -> str:
    a = _advapi()
    size = w.DWORD(0)
    a.GetTokenInformation(w.HANDLE(token), _TOKEN_USER, None, 0, ctypes.byref(size))
    buf = ctypes.create_string_buffer(int(size.value) or 64)
    if not a.GetTokenInformation(w.HANDLE(token), _TOKEN_USER, buf, size, ctypes.byref(size)):
        raise _fail("GetTokenInformation")
    psid = ctypes.c_void_p.from_buffer(buf).value  # TOKEN_USER.User.Sid
    return sid_to_string(psid)


def process_user_sid(pid: int) -> str:
    """String SID of the account a process runs as."""
    k, a = _kernel32(), _advapi()
    ph = k.OpenProcess(_PROCESS_QUERY_LIMITED, False, int(pid))
    if not ph:
        raise _fail("OpenProcess")
    try:
        tok = w.HANDLE()
        if not a.OpenProcessToken(ph, _TOKEN_QUERY, ctypes.byref(tok)):
            raise _fail("OpenProcessToken")
        try:
            return token_user_sid(tok.value)
        finally:
            k.CloseHandle(tok)
    finally:
        k.CloseHandle(ph)


def current_user_sid() -> str:
    return process_user_sid(os.getpid())


def lookup_account_sid(name: str) -> str | None:
    """String SID of a local account, or None when it does not exist."""
    a = _advapi()
    sid_size, dom_size, use = w.DWORD(0), w.DWORD(0), ctypes.c_int()
    a.LookupAccountNameW(None, name, None, ctypes.byref(sid_size), None, ctypes.byref(dom_size), ctypes.byref(use))
    if ctypes.get_last_error() == 1332 or not sid_size.value:  # ERROR_NONE_MAPPED
        return None
    sid = ctypes.create_string_buffer(int(sid_size.value))
    dom = ctypes.create_unicode_buffer(int(dom_size.value) + 1)
    if not a.LookupAccountNameW(None, name, sid, ctypes.byref(sid_size), dom, ctypes.byref(dom_size), ctypes.byref(use)):
        if ctypes.get_last_error() == 1332:
            return None
        raise _fail("LookupAccountNameW")
    return sid_to_string(sid)


def is_admin() -> bool:
    if not IS_WINDOWS:
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


# ---- DPAPI ---------------------------------------------------------------------------------------

class _BLOB(ctypes.Structure):
    _fields_ = [("cbData", w.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _crypt(fn_name: str, data: bytes) -> bytes:
    crypt32, k = _dll("crypt32"), _kernel32()
    fn = getattr(crypt32, fn_name)
    fn.argtypes = [ctypes.POINTER(_BLOB), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, w.DWORD,
                   ctypes.POINTER(_BLOB)]
    src_buf = ctypes.create_string_buffer(data, len(data))
    src = _BLOB(len(data), ctypes.cast(src_buf, ctypes.POINTER(ctypes.c_char)))
    out = _BLOB()
    if not fn(ctypes.byref(src), None, None, None, None, _PI_NOUI, ctypes.byref(out)):
        raise _fail(fn_name)
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        k.LocalFree(out.pbData)


def dpapi_protect(data: bytes) -> bytes:
    """Encrypt for the current account only (DPAPI user scope)."""
    return _crypt("CryptProtectData", data)


def dpapi_unprotect(blob: bytes) -> bytes:
    return _crypt("CryptUnprotectData", blob)


# ---- Logon and process creation as another account ----------------------------------------------

class _STARTUPINFOW(ctypes.Structure):
    _fields_ = [("cb", w.DWORD), ("lpReserved", w.LPWSTR), ("lpDesktop", w.LPWSTR), ("lpTitle", w.LPWSTR),
                ("dwX", w.DWORD), ("dwY", w.DWORD), ("dwXSize", w.DWORD), ("dwYSize", w.DWORD),
                ("dwXCountChars", w.DWORD), ("dwYCountChars", w.DWORD), ("dwFillAttribute", w.DWORD),
                ("dwFlags", w.DWORD), ("wShowWindow", w.WORD), ("cbReserved2", w.WORD),
                ("lpReserved2", ctypes.c_void_p), ("hStdInput", w.HANDLE), ("hStdOutput", w.HANDLE),
                ("hStdError", w.HANDLE)]


class _PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [("hProcess", w.HANDLE), ("hThread", w.HANDLE), ("dwProcessId", w.DWORD), ("dwThreadId", w.DWORD)]


class _PROFILEINFOW(ctypes.Structure):
    _fields_ = [("dwSize", w.DWORD), ("dwFlags", w.DWORD), ("lpUserName", w.LPWSTR), ("lpProfilePath", w.LPWSTR),
                ("lpDefaultPath", w.LPWSTR), ("lpServerName", w.LPWSTR), ("lpPolicyPath", w.LPWSTR),
                ("hProfile", w.HANDLE)]


def logon(username: str, password: str, logon_type: int = LOGON32_LOGON_BATCH) -> int:
    """A primary token for a local account (``LogonUserW``). The caller closes it with ``close_handle``."""
    tok = w.HANDLE()
    if not _advapi().LogonUserW(username, ".", password, logon_type, LOGON32_PROVIDER_DEFAULT, ctypes.byref(tok)):
        raise _fail("LogonUserW")
    return int(tok.value)


def close_handle(handle: int | None) -> None:
    if handle:
        _kernel32().CloseHandle(w.HANDLE(handle))


def pid_in_job(job: "Job", pid: int) -> bool:
    """True when process ``pid`` is in ``job`` (False when it cannot be opened or does not exist)."""
    k = _kernel32()
    ph = k.OpenProcess(_PROCESS_QUERY_LIMITED, False, int(pid))
    if not ph:
        return False
    try:
        return job.contains(ph)
    except OSError:
        return False
    finally:
        k.CloseHandle(ph)


@dataclass
class LoadedProfile:
    token: int
    profile_handle: int

    def unload(self) -> None:
        if self.profile_handle:
            userenv = _dll("userenv")
            userenv.UnloadUserProfile.argtypes = [w.HANDLE, w.HANDLE]
            userenv.UnloadUserProfile(w.HANDLE(self.token), w.HANDLE(self.profile_handle))
            self.profile_handle = 0


def load_profile(token: int, username: str) -> LoadedProfile:
    userenv = _dll("userenv")
    userenv.LoadUserProfileW.argtypes = [w.HANDLE, ctypes.POINTER(_PROFILEINFOW)]
    info = _PROFILEINFOW()
    info.dwSize = ctypes.sizeof(info)
    info.dwFlags = _PI_NOUI
    info.lpUserName = username
    if not userenv.LoadUserProfileW(w.HANDLE(token), ctypes.byref(info)):
        raise _fail("LoadUserProfileW")
    return LoadedProfile(token, int(info.hProfile or 0))


def environment_block(token: int) -> dict[str, str]:
    """The account's own default environment (``CreateEnvironmentBlock``), as a dict."""
    userenv = _dll("userenv")
    userenv.CreateEnvironmentBlock.argtypes = [ctypes.POINTER(ctypes.c_void_p), w.HANDLE, w.BOOL]
    userenv.DestroyEnvironmentBlock.argtypes = [ctypes.c_void_p]
    block = ctypes.c_void_p()
    if not userenv.CreateEnvironmentBlock(ctypes.byref(block), w.HANDLE(token), False):
        raise _fail("CreateEnvironmentBlock")
    try:
        out: dict[str, str] = {}
        offset = 0
        while True:
            entry = ctypes.wstring_at(block.value + offset)
            if not entry:
                break
            offset += (len(entry) + 1) * ctypes.sizeof(ctypes.c_wchar)
            key, sep, value = entry.partition("=")
            if sep and key:  # skips the "=C:=C:\\" drive entries, whose key is empty
                out[key] = value
        return out
    finally:
        userenv.DestroyEnvironmentBlock(block)


def _env_block(env: dict[str, str]):
    text = "".join(f"{k}={v}\0" for k, v in sorted(env.items(), key=lambda kv: kv[0].upper())) + "\0"
    return ctypes.create_unicode_buffer(text, len(text))


@dataclass
class StartedProcess:
    pid: int
    process_handle: int
    thread_handle: int
    method: str  # "CreateProcessAsUserW" or "CreateProcessWithTokenW"


def create_process_as(token: int, command_line: str, *, cwd: str, env: dict[str, str]) -> StartedProcess:
    """Start ``command_line`` suspended under ``token`` with no window and no inherited handles.

    ``CreateProcessAsUserW`` needs ``SeAssignPrimaryTokenPrivilege`` (LocalSystem has it). Without it
    (an elevated administrator shell) this falls back to ``CreateProcessWithTokenW``, which needs
    ``SeImpersonatePrivilege`` and still runs under the given batch-logon token.
    """
    a = _advapi()
    si = _STARTUPINFOW()
    si.cb = ctypes.sizeof(si)
    pi = _PROCESS_INFORMATION()
    flags = CREATE_SUSPENDED | CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP | CREATE_UNICODE_ENVIRONMENT
    cmd = ctypes.create_unicode_buffer(command_line)
    block = _env_block(env)
    if a.CreateProcessAsUserW(w.HANDLE(token), None, cmd, None, None, False, flags, block, cwd, ctypes.byref(si),
                              ctypes.byref(pi)):
        method = "CreateProcessAsUserW"
    else:
        if ctypes.get_last_error() != ERROR_PRIVILEGE_NOT_HELD:
            raise _fail("CreateProcessAsUserW")
        cmd = ctypes.create_unicode_buffer(command_line)
        if not a.CreateProcessWithTokenW(w.HANDLE(token), 0, None, cmd, flags, block, cwd, ctypes.byref(si),
                                         ctypes.byref(pi)):
            raise _fail("CreateProcessWithTokenW")
        method = "CreateProcessWithTokenW"
    return StartedProcess(int(pi.dwProcessId), int(pi.hProcess), int(pi.hThread), method)


def process_exit_code(process_handle: int) -> int | None:
    """None while the process runs, else its exit code."""
    k = _kernel32()
    if k.WaitForSingleObject(w.HANDLE(process_handle), 0) == 0x102:  # WAIT_TIMEOUT
        return None
    code = w.DWORD()
    if not k.GetExitCodeProcess(w.HANDLE(process_handle), ctypes.byref(code)):
        raise _fail("GetExitCodeProcess")
    return int(code.value)


def terminate_process(process_handle: int, code: int = 1) -> None:
    _kernel32().TerminateProcess(w.HANDLE(process_handle), code)
