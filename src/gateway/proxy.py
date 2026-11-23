"""The reverse proxy: the real ``Upstream`` that sends an authenticated request to that user's worker.

Buffered (the worker's responses are fully buffered and nothing uses keep-alive, chunking or
WebSockets), with ``upstream_headers`` as the header contract: client credentials and proxy headers
stripped, the worker token injected, Host and Origin rewritten to the worker's exact loopback address,
one ``Content-Length``. It enforces size limits and timeouts, refuses the event-stream build route,
checks that the worker's port still belongs to the worker process, and routes build starts through the
gateway-wide ``BuildQueue``. See ``documentation/future/multi-user-server-supervisor-design.md``.
"""
from __future__ import annotations

import http.client
import json
import logging
import re
import socket
import threading
import time
from dataclasses import dataclass
from typing import Callable
from urllib.parse import unquote

from src.http_runtime import security_headers
from src.http_runtime.wsgi_facade import HeaderMap, LocalRequest, Response

from .build_queue import FINAL_STATUSES, AlreadyQueued, BuildQueue
from .supervisor import Endpoint, Supervisor, WorkerUnavailable, call_worker
from .upstream import HOP_BY_HOP, Identity, upstream_headers

LOG = logging.getLogger("retirement.gateway.proxy")
_PROGRESS = re.compile(r"^/api/build/progress/([A-Za-z0-9_-]{1,64})$")
_CANCEL = re.compile(r"^/api/build/cancel/([A-Za-z0-9_-]{1,64})$")
_SAFE_PATH = re.compile(r"^/[A-Za-z0-9._~!$&'()*+,;=:@%/-]*$")
DROPPED_RESPONSE_HEADERS = HOP_BY_HOP | frozenset({"set-cookie", "content-length", "server", "date"})
DROPPED_RESPONSE_PREFIXES = ("access-control-",)
QUEUED_PHASE = "Waiting for a free build slot"
# Financial Insight's share-snapshot route renders a record for the gateway's publisher only (Phase 9, C23); the
# publisher calls the worker directly with call_worker, never through here.
SNAPSHOT_PATHS = frozenset({"/insights/api/share-snapshot"})


def _is_snapshot_path(path: str) -> bool:
    """Any spelling of the snapshot route: percent-decoded (twice), any case, any trailing slash. The worker also
    requires a gateway-only header that ``upstream_headers`` strips from every browser request."""
    p = unquote(unquote(path)).lower()
    return p.rstrip("/") in SNAPSHOT_PATHS or "share-snapshot" in p


@dataclass(frozen=True)
class ProxyConfig:
    max_request_bytes: int = 64 * 1024 * 1024
    max_response_bytes: int = 256 * 1024 * 1024
    connect_timeout: float = 5.0
    read_timeout: float = 120.0
    build_poll_seconds: float = 5.0
    max_upstream_per_user: int = 16  # parallel requests one user's worker is handed; the rest wait their turn
    upstream_wait_seconds: float = 60.0  # how long a request may wait for a turn before a 503
    refused_backoff: tuple[float, ...] = (0.05, 0.1, 0.2, 0.4, 0.8)  # retries of a refused connection to a live worker


def _json(payload: dict, status: int = 200) -> Response:
    return Response(json.dumps(payload), status=status, content_type="application/json")


def _error(req: LocalRequest, message: str, status: int) -> Response:
    if req.path.startswith(("/api/", "/insights/api/")):
        return _json({"success": False, "error": message}, status)
    html = ("<!doctype html><meta charset=utf-8><title>Retirement Planner</title>"
            f"<p>{message}</p><p><a href=\"/\">Try again</a> &middot; <a href=\"/gateway/account\">Your account</a></p>")
    return Response(html, status=status, content_type="text/html; charset=utf-8")


class WorkerProxy:
    def __init__(self, supervisor: Supervisor, build_queue: BuildQueue, config: ProxyConfig | None = None, *,
                 audit: Callable[[str, int, str], None] | None = None) -> None:
        self.supervisor = supervisor
        self.queue = build_queue
        self.config = config or ProxyConfig()
        self._audit = audit  # (event, user id, details): ids only
        # Called after a successful forwarded response (Phase 9: the plan-delete hook revokes that plan's shares).
        self.after_forward: Callable[[LocalRequest, Identity, Response], None] | None = None
        self._gates: dict[int, threading.BoundedSemaphore] = {}
        self._gates_lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ---- the Upstream protocol ----
    def forward(self, req: LocalRequest, identity: Identity) -> Response:
        if getattr(identity, "kind", None) != "member":
            # Second layer behind the gate (Phase 9, C2): only an exact member ever reaches a worker.
            if self._audit is not None:
                try:
                    self._audit("viewer_forward_refused", int(identity.user_id), "")
                except Exception:  # noqa: BLE001 - the refusal stands whatever the audit does
                    LOG.exception("could not audit a refused forward")
            return _error(req, "This page is not available.", 503)
        uid = int(identity.user_id)
        path, method = req.path, req.method
        if not _SAFE_PATH.match(path) or "/../" in path + "/" or "//" in path:
            return _error(req, "That address is not valid.", 400)
        if _is_snapshot_path(path):
            return _error(req, "That address is not valid.", 404)
        if path.startswith("/api/build/events/"):
            return _error(req, "Live build events are not available here; the page checks progress instead.", 403)
        if path == "/api/build" and method == "POST":
            return _error(req, "Start builds with /api/build/start.", 403)
        if len(req.body or b"") > self.config.max_request_bytes:
            return _error(req, "That upload is too large.", 413)
        if path == "/api/build/start" and method == "POST":
            return self._build_start(req, uid)
        m = _PROGRESS.match(path)
        if m and method == "GET":
            return self._build_progress(req, uid, m.group(1))
        m = _CANCEL.match(path)
        if m and method == "POST":
            return self._build_cancel(req, uid, m.group(1))
        resp = self._send(req, uid, path)
        hook = self.after_forward
        if hook is not None and resp.status_code == 200:
            try:
                hook(req, identity, resp)
            except Exception:  # noqa: BLE001 - never turns a served response into an error
                LOG.exception("after-forward hook failed for user %s", uid)
        return resp

    # ---- plain forwarding ----
    def _gate(self, uid: int) -> threading.BoundedSemaphore:
        with self._gates_lock:
            gate = self._gates.get(uid)
            if gate is None:
                gate = self._gates[uid] = threading.BoundedSemaphore(max(1, self.config.max_upstream_per_user))
            return gate

    def _send(self, req: LocalRequest, uid: int, path: str, *, retry: bool = True) -> Response:
        # A page load can issue 100+ requests at once; hand the worker a bounded number and queue the rest
        # briefly instead of overrunning its listener (which would look like a dead worker).
        gate = self._gate(uid)
        if not gate.acquire(timeout=self.config.upstream_wait_seconds):
            return _error(req, "Your planner is busy. Please try again shortly.", 503)
        try:
            return self._send_gated(req, uid, path, retry=retry)
        finally:
            gate.release()

    def _send_gated(self, req: LocalRequest, uid: int, path: str, *, retry: bool = True) -> Response:
        try:
            ep = self.supervisor.endpoint(uid)
        except WorkerUnavailable as exc:
            return _error(req, str(exc), 503)
        except Exception:
            LOG.exception("could not start the worker for user %s", uid)
            return _error(req, "Your planner could not be started. Please try again shortly.", 503)
        if not req.environ.get("gateway_background_poll"):  # a background poll must not keep the worker alive
            self.supervisor.touch(uid)
        if not self.supervisor.port_owner_ok(ep):
            self.supervisor.mark_dead(uid, ep, "its port is no longer held by the worker process")
            return _error(req, "Your planner restarted. Please try again.", 503)
        body = req.body or b""
        target = path + (f"?{req.query_string}" if req.query_string else "")
        headers = upstream_headers(req.headers, worker_port=ep.port, worker_token=ep.token, body_length=len(body))
        attempt = 0
        while True:
            conn = http.client.HTTPConnection("127.0.0.1", ep.port, timeout=self.config.connect_timeout)
            try:
                conn.connect()
                conn.sock.settimeout(self.config.read_timeout)
                conn.request(req.method, target, body=body, headers=headers)
                resp = conn.getresponse()
                data = resp.read(self.config.max_response_bytes + 1)
                status, raw_headers = resp.status, resp.getheaders()
                break
            except (ConnectionRefusedError, ConnectionResetError, http.client.RemoteDisconnected) as exc:
                # A refusal while the worker process still owns its port is a full backlog, not a dead worker:
                # back off and try again. Only a worker that has lost its port is stopped.
                if (attempt < len(self.config.refused_backoff) and self.supervisor.port_owner_ok(ep)
                        and (req.method in ("GET", "HEAD") or isinstance(exc, ConnectionRefusedError))):
                    time.sleep(self.config.refused_backoff[attempt])
                    attempt += 1
                    continue
                self.supervisor.mark_dead(uid, ep, f"connection failed ({type(exc).__name__})")
                if retry and req.method in ("GET", "HEAD"):
                    return self._send_gated(req, uid, path, retry=False)
                return _error(req, "Your planner restarted while handling that request. Please try again.", 502)
            except (socket.timeout, TimeoutError):
                return _error(req, "Your planner took too long to answer.", 504)
            except OSError:
                LOG.warning("proxy error for user %s", uid, exc_info=True)
                return _error(req, "Your planner could not be reached.", 502)
            finally:
                conn.close()
        if len(data) > self.config.max_response_bytes:
            return _error(req, "That response is too large to send.", 502)
        return self._response(status, raw_headers, data, ep)

    @staticmethod
    def _response(status: int, raw_headers: list[tuple[str, str]], data: bytes, ep: Endpoint) -> Response:
        connection_named = {p.strip().lower() for k, v in raw_headers if k.lower() == "connection"
                            for p in v.split(",") if p.strip()}
        out = HeaderMap()
        loopback = f"http://127.0.0.1:{ep.port}"
        for key, value in raw_headers:
            k = key.lower()
            if k in DROPPED_RESPONSE_HEADERS or k in connection_named or k.startswith(DROPPED_RESPONSE_PREFIXES):
                continue
            if k == "location" and value.startswith(loopback):
                value = value[len(loopback):] or "/"
            out[key] = value
        # SEC-07: whatever the worker (or Financial Insights) set wins; anything it left out gets the narrowest policy
        # the planner pages work with.
        security_headers.apply(out, security_headers.PLANNER_CSP)
        resp = Response(data, status=status, headers=dict(out))
        return resp

    # ---- builds ----
    def _build_start(self, req: LocalRequest, uid: int) -> Response:
        if self.queue.has_build(uid):
            return _json({"success": False, "build_in_progress": True,
                          "error": "A build is already running or waiting for your plan."}, 409)
        if self.queue.try_acquire(uid):
            resp = self._send(req, uid, req.path, retry=False)
            job_id = _job_id(resp)
            if resp.status_code == 200 and job_id:
                self.queue.started(uid, job_id)
            else:
                self.queue.abandon(uid)
            return resp
        ctype = str(req.headers.get("Content-Type", "") or "application/json")
        try:
            qid, position = self.queue.enqueue_unique(uid, req.body or b"", ctype)
        except AlreadyQueued:  # a parallel start from the same user got there first
            return _json({"success": False, "build_in_progress": True,
                          "error": "A build is already running or waiting for your plan."}, 409)
        self._wake.set()
        ahead = position - 1 + len(self.queue.running())
        return _json({"success": True, "queued": True, "job_id": qid, "position": position, "progress": 0,
                      "phase": QUEUED_PHASE, "detail": f"{ahead} build(s) ahead of yours."})

    def _build_progress(self, req: LocalRequest, uid: int, job_id: str) -> Response:
        kind, value = self.queue.resolve(uid, job_id)
        if kind == "unknown":
            return _json({"success": False, "error": "build job not found"}, 404)
        if kind == "queued":
            return _json({"success": True, "job": {"job_id": job_id, "status": "queued", "queued": True, "progress": 0,
                                                    "phase": QUEUED_PHASE, "position": value,
                                                    "detail": f"Position {value} in the build queue."}})
        if kind in ("failed", "cancelled"):
            error = (value or {}).get("error") if isinstance(value, dict) else "The build was cancelled."
            status = "failed" if kind == "failed" else "cancelled"
            return _json({"success": True, "job": {"job_id": job_id, "status": status, "progress": 100,
                                                    "phase": "Build failed" if kind == "failed" else "Build cancelled",
                                                    "detail": error, "result": {"success": False, "error": error}}})
        real_id = str(value)
        resp = self._send(req, uid, f"/api/build/progress/{real_id}")
        payload = _payload(resp)
        job = payload.get("job") if isinstance(payload, dict) else None
        if resp.status_code == 404 or (isinstance(job, dict) and job.get("status") in FINAL_STATUSES):
            if self.queue.finished(uid, real_id):
                self._wake.set()
                self._maybe_release(uid)
        return resp

    def _build_cancel(self, req: LocalRequest, uid: int, job_id: str) -> Response:
        kind, value = self.queue.resolve(uid, job_id)
        if kind == "unknown":
            return _json({"success": False, "error": "build job not found"}, 404)
        if kind == "queued":
            self.queue.cancel_queued(uid, job_id)
            return _json({"success": True, "job_id": job_id, "outcome": "cancelling"})
        if kind in ("failed", "cancelled"):
            return _json({"success": True, "job_id": job_id, "outcome": "finished"})
        return self._send(req, uid, f"/api/build/cancel/{value}", retry=False)

    def _maybe_release(self, uid: int) -> None:
        """A build ended: a worker kept up only for that build may stop now."""
        slot = self.supervisor._slots.get(uid)  # noqa: SLF001 - same package
        if slot is not None and slot.stop_when_idle_of_builds and not self.supervisor.build_busy(uid):
            self.supervisor.stop(uid, "signed out; build finished")

    def _dispatch_waiting(self) -> None:
        while True:
            waiting = self.queue.next_dispatch()
            if waiting is None:
                return
            headers = HeaderMap({"Content-Type": waiting.content_type})
            req = LocalRequest("POST", "/api/build/start", headers, waiting.body)
            resp = self._send(req, waiting.user_id, "/api/build/start", retry=False)
            job_id = _job_id(resp)
            if resp.status_code == 200 and job_id:
                self.queue.started(waiting.user_id, job_id, queued_id=waiting.queued_id)
                LOG.info("queued build for user %s started", waiting.user_id)
            else:
                payload = _payload(resp)
                error = payload.get("error") if isinstance(payload, dict) else None
                self.queue.abandon(waiting.user_id, waiting.queued_id,
                                   {"error": str(error or "The build could not be started.")})

    def _poll_running(self) -> None:
        for uid, job_id, _started in self.queue.running():
            if job_id is None:
                continue
            ep = self.supervisor.current_endpoint(uid)
            if ep is None:
                self.queue.worker_gone(uid)
                continue
            try:
                status, body = call_worker(ep, "GET", f"/api/build/progress/{job_id}", timeout=15)
                job = json.loads(body).get("job") if status == 200 else None
            except (OSError, ValueError):
                continue
            if status == 404 or (isinstance(job, dict) and job.get("status") in FINAL_STATUSES):
                if self.queue.finished(uid, job_id):
                    self._maybe_release(uid)

    def tick(self) -> None:
        """One pass of the build monitor: release finished or expired builds, then start waiting ones."""
        self._poll_running()
        self.queue.expire()
        self._dispatch_waiting()

    def start(self) -> None:
        if self._thread is not None:
            return

        def loop() -> None:
            while not self._stop.is_set():
                self._wake.wait(self.config.build_poll_seconds)
                self._wake.clear()
                if self._stop.is_set():
                    return
                try:
                    self.tick()
                except Exception:  # pragma: no cover - the monitor must keep running
                    LOG.exception("build monitor pass failed")

        self._thread = threading.Thread(target=loop, name="build-queue", daemon=True)
        self._thread.start()

    def shutdown(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=10)


def _payload(resp: Response) -> object:
    try:
        return json.loads(resp.get_data(as_text=True))
    except ValueError:
        return None


def _job_id(resp: Response) -> str | None:
    payload = _payload(resp)
    job_id = payload.get("job_id") if isinstance(payload, dict) else None
    return str(job_id) if job_id else None
