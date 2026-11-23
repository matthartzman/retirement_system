"""A per-boot random credential for the two owner-only loopback apps (Admin app 5056, Financial Insights owner listener 5057).

"The peer is loopback" proves nothing on a host where worker accounts (``rpw_N``) are untrusted local users who can
open a socket to 127.0.0.1 as well as the owner can (security review 2026-11-23, finding X-1). Each app therefore
generates ``secrets.token_urlsafe(32)`` at startup and writes it to a file only the current user can read
(``<workspace>/local_state/<name>_local_token``). A request is accepted when it carries either

* the HttpOnly, SameSite=Strict session cookie that the browser handoff below sets, or
* the token itself in an ``X-Local-Token`` header (local scripts and tests).

The browser handoff: the launcher reads the token file and POSTs it (header, never a URL or command line) to
``/_local/nonce``; the app returns a single-use nonce that lives 60 seconds. The launcher opens
``/_local/open?n=<nonce>``; the app swaps the nonce for a fresh random session id in a cookie and redirects to ``/``.
The token never appears in a URL, a log or an argv. Comparisons use ``hmac.compare_digest``.

The cookie is named per app because browsers share cookies across ports on one host.
Residual: malware running as the same Windows user can read the token file, and on Windows the file is protected by
an explicit ``icacls`` grant to the current user (inheritance removed) plus the folder's own ACL.
"""
from __future__ import annotations

import hmac
import json
import os
import secrets
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

from .wsgi_facade import Response, request

TOKEN_HEADER = "X-Local-Token"
OPEN_PATH = "/_local/open"
NONCE_PATH = "/_local/nonce"
NONCE_TTL_SECONDS = 60.0
SESSION_TTL_SECONDS = 7 * 24 * 3600.0
MAX_NONCES = 16
MAX_SESSIONS = 32

_UNAUTHENTICATED_HTML = (
    "<!doctype html><meta charset=\"utf-8\"><title>Open from the launcher</title>"
    "<body style=\"font:16px system-ui;max-width:38em;margin:3em auto;padding:0 1em\">"
    "<h2>Open this app from its launcher</h2>"
    "<p>This page needs a sign-in that only the launcher can give your browser. Use the desktop shortcut, or run "
    "<code>python {module} --print-open-url</code> and open the address it prints (it works once, for a minute).</p></body>"
)


def token_file_path(root: Path | str, name: str) -> Path:
    return Path(root) / "local_state" / f"{name}_local_token"


def _windows_user_grant() -> str:
    """``*S-1-5-...:F`` for the current user (a SID, so no name lookup), else the account name."""
    try:
        out = subprocess.run(["whoami", "/user", "/fo", "csv", "/nh"], capture_output=True, text=True, timeout=10, check=True).stdout
        sid = out.strip().rsplit(",", 1)[-1].strip().strip('"')
        if sid.startswith("S-1-"):
            return f"*{sid}:F"
    except (OSError, subprocess.SubprocessError):
        pass
    domain, user = os.environ.get("USERDOMAIN", ""), os.environ.get("USERNAME", "")
    return f"{domain}\\{user}:F" if domain else f"{user}:F"


def restrict_to_current_user(path: Path) -> None:
    """Owner-only: ``chmod 600`` on POSIX; on Windows an explicit ACL, inheritance removed, current user only."""
    if sys.platform == "win32":
        proc = subprocess.run(["icacls", str(path), "/inheritance:r", "/grant:r", _windows_user_grant()],
                              capture_output=True, text=True, timeout=30)
        if proc.returncode != 0:
            print(f"warning: could not restrict {path} to the current user: {(proc.stdout + proc.stderr).strip()[-200:]}",
                  file=sys.stderr)
        return
    os.chmod(path, 0o600)


def write_private_file(path: Path, text: str) -> None:
    """Write ``text`` so that no moment exists when another account could read it: create restricted, then replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        restrict_to_current_user(tmp)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


class LocalTokenGate:
    def __init__(self, name: str, token_path: Path | None = None, clock: Callable[[], float] = time.time,
                 token: str | None = None, module: str = "") -> None:
        self.name = name
        self.cookie_name = f"{name}_local_session"
        self.token = token or secrets.token_urlsafe(32)
        self.token_path = token_path
        self.module = module or name
        self._clock = clock
        self._lock = threading.Lock()
        self._nonces: dict[str, float] = {}
        self._sessions: dict[str, float] = {}

    @classmethod
    def start(cls, name: str, root: Path | str, **kwargs) -> "LocalTokenGate":
        """A gate with a fresh token, already written to ``<root>/local_state/<name>_local_token``."""
        gate = cls(name, token_file_path(root, name), **kwargs)
        gate.write_token_file()
        return gate

    def write_token_file(self) -> None:
        if self.token_path is not None:
            write_private_file(self.token_path, self.token + "\n")

    # ---- credentials ----
    def _same(self, presented: str, expected: str) -> bool:
        return bool(presented) and hmac.compare_digest(presented.encode("utf-8", "replace"), expected.encode("utf-8"))

    def _take(self, table: dict[str, float], presented: str, *, consume: bool) -> bool:
        """True when ``presented`` is a live entry of ``table``; expired entries are dropped; compared in constant time."""
        now = self._clock()
        with self._lock:
            for key in [k for k, until in table.items() if until <= now]:
                del table[key]
            hit = next((k for k in table if self._same(presented, k)), None)
            if hit is not None and consume:
                del table[hit]
            return hit is not None

    def _put(self, table: dict[str, float], ttl: float, cap: int) -> str:
        value = secrets.token_urlsafe(32)
        with self._lock:
            while len(table) >= cap:
                del table[min(table, key=table.get)]
            table[value] = self._clock() + ttl
        return value

    def mint_nonce(self) -> str:
        return self._put(self._nonces, NONCE_TTL_SECONDS, MAX_NONCES)

    def redeem_nonce(self, nonce: str) -> str | None:
        """Single use: a session id for a live nonce, else None."""
        if not self._take(self._nonces, nonce, consume=True):
            return None
        return self._put(self._sessions, SESSION_TTL_SECONDS, MAX_SESSIONS)

    def open_url(self, base_url: str) -> str:
        return f"{base_url.rstrip('/')}{OPEN_PATH}?n={self.mint_nonce()}"

    def authenticated(self) -> bool:
        if self._same(str(request.headers.get(TOKEN_HEADER, "") or ""), self.token):
            return True
        return self._take(self._sessions, str(request.cookies.get(self.cookie_name, "") or ""), consume=False)

    # ---- the gate ----
    def refusal(self) -> Response:
        if request.path.startswith("/api/") or request.method not in ("GET", "HEAD"):
            return Response(json.dumps({"success": False, "error": "local sign-in required: open this app from its launcher"}),
                            status=401, content_type="application/json")
        return Response(_UNAUTHENTICATED_HTML.format(module=self.module), status=401, content_type="text/html; charset=utf-8")

    def check(self) -> Response | None:
        """A ``before_request`` hook: None lets the request through. Run it after the Host/Origin/proxy checks."""
        if request.method == "GET" and request.path == OPEN_PATH:
            return None  # the nonce is this request's credential; the route validates it
        return None if self.authenticated() else self.refusal()

    def register(self, app, is_local: Callable[[], bool] = lambda: True) -> None:
        @app.route(NONCE_PATH, methods=["POST"])
        def _local_nonce():  # reached only with the header token (check() let it through)
            if not is_local() or not self._same(str(request.headers.get(TOKEN_HEADER, "") or ""), self.token):
                return Response(json.dumps({"success": False, "error": "token required"}), status=401, content_type="application/json")
            return Response(json.dumps({"success": True, "nonce": self.mint_nonce(), "expires_in": NONCE_TTL_SECONDS}),
                            content_type="application/json", headers={"Cache-Control": "no-store"})

        @app.route(OPEN_PATH, methods=["GET"])
        def _local_open():
            session = self.redeem_nonce(str(request.args.get("n") or "")) if is_local() else None
            if session is None:
                return self.refusal()
            resp = Response(b"", status=302, headers={"Location": "/", "Cache-Control": "no-store"})
            resp.set_cookie(self.cookie_name, session, httponly=True, samesite="Strict", path="/")
            return resp


# ---- launcher side: read the token file, ask a running app for a single-use handoff URL ----
def read_token(root: Path | str, name: str) -> str | None:
    try:
        return token_file_path(root, name).read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def request_open_url(base_url: str, root: Path | str, name: str, timeout: float = 3.0) -> str | None:
    """The one-time browser URL for a running app, or None (no token file, app not answering, token refused)."""
    token = read_token(root, name)
    if token is None:
        return None
    req = urllib.request.Request(f"{base_url.rstrip('/')}{NONCE_PATH}", data=b"{}", method="POST",
                                 headers={TOKEN_HEADER: token, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - fixed loopback URL
            nonce = json.loads(resp.read().decode("utf-8")).get("nonce")
    except (urllib.error.URLError, OSError, ValueError):
        return None
    return f"{base_url.rstrip('/')}{OPEN_PATH}?n={nonce}" if isinstance(nonce, str) and nonce else None


def open_running_app(base_url: str, root: Path | str, name: str, *, print_only: bool, opener: Callable[[str], object],
                     out=print) -> int:
    """Hand a running app to the browser (or print the one-time URL). 0 on success, 1 when it cannot be authenticated."""
    url = request_open_url(base_url, root, name)
    if url is None:
        print(f"Could not sign in to the running app at {base_url}: no readable token file for it under "
              f"{token_file_path(root, name)}, or it was started by another account. Stop it and start it from here.",
              file=sys.stderr)
        return 1
    if print_only:
        out(url)
    else:
        opener(url)
    return 0
