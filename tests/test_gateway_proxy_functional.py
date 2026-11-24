"""The reverse proxy against a recording fake worker over real HTTP: the header contract, limits,
timeouts, the blocked routes, the port-owner check and the build queue interception."""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from src.gateway.build_queue import BuildQueue
from src.gateway.proxy import ProxyConfig, WorkerProxy
from src.gateway.supervisor import Endpoint
from src.gateway.upstream import Identity
from src.http_runtime.wsgi_facade import HeaderMap, LocalRequest

pytestmark = pytest.mark.integration
TOKEN = "worker-token-for-proxy-tests"


class FakeWorker:
    """Records every request; answers by path."""

    def __init__(self) -> None:
        self.requests: list[dict] = []
        self.jobs: dict[str, str] = {}
        self.sleep = 0.0
        self.big = 0
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):  # noqa: D401
                return

            def _go(self):
                n = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(n) if n else b""
                outer.requests.append({"method": self.command, "path": self.path, "headers": dict(self.headers.items()),
                                       "raw_headers": self.headers.items(), "body": body})
                if self.headers.get("X-API-Token") != TOKEN:
                    return self._send(401, {"error": "token"})
                if outer.sleep:
                    time.sleep(outer.sleep)
                if self.path == "/big":
                    return self._send(200, b"x" * outer.big, ctype="application/octet-stream")
                if self.path == "/redirect":
                    return self._send(302, b"", extra={"Location": f"http://127.0.0.1:{outer.port}/somewhere"})
                if self.path == "/api/build/start":
                    jid = f"job{len(outer.jobs) + 1}"
                    outer.jobs[jid] = "running"
                    return self._send(200, {"success": True, "job_id": jid})
                if self.path.startswith("/api/build/progress/"):
                    jid = self.path.rsplit("/", 1)[1]
                    if jid not in outer.jobs:
                        return self._send(404, {"success": False})
                    return self._send(200, {"success": True, "job": {"job_id": jid, "status": outer.jobs[jid]}})
                return self._send(200, {"ok": True, "path": self.path},
                                  extra={"Set-Cookie": "worker=1", "Access-Control-Allow-Origin": "*",
                                         "X-Frame-Options": "DENY"})

            def _send(self, status, payload, ctype="application/json", extra=None):
                data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                for k, v in (extra or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(data)

            do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = _go

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class FakeSupervisor:
    def __init__(self, workers: dict[int, FakeWorker]) -> None:
        self.workers = workers
        self.owner_ok = True
        self.dead: list[tuple[int, str]] = []
        self.touched: list[int] = []
        self._slots: dict = {}
        self.unavailable = False

    def endpoint(self, uid):
        if self.unavailable:
            from src.gateway.supervisor import WorkerUnavailable
            raise WorkerUnavailable("Your planner is taking too long to start.")
        return Endpoint(uid, self.workers[uid].port, 4242, TOKEN)

    def current_endpoint(self, uid):
        return self.endpoint(uid) if uid in self.workers else None

    def touch(self, uid):
        self.touched.append(uid)

    def port_owner_ok(self, ep):
        return self.owner_ok

    def mark_dead(self, uid, ep, reason):
        self.dead.append((uid, reason))

    def build_busy(self, uid):
        return False


@pytest.fixture
def rig():
    workers = {1: FakeWorker(), 2: FakeWorker()}
    sup = FakeSupervisor(workers)
    queue = BuildQueue(1)
    proxy = WorkerProxy(sup, queue, ProxyConfig(max_request_bytes=1000, max_response_bytes=5000, read_timeout=1.0))
    yield proxy, sup, workers, queue
    for w in workers.values():
        w.close()


ALICE, BOB = Identity(1, "alice", "Alice", "user"), Identity(2, "bob", "Bob", "user")


def _req(method, target, headers=None, body=b""):
    return LocalRequest(method, target, HeaderMap(headers or {}), body)


def test_client_credentials_and_proxy_headers_are_replaced_and_host_origin_rewritten(rig):
    proxy, _sup, workers, _q = rig
    hostile = {"Host": "node.example.ts.net:8443", "Origin": "https://node.example.ts.net:8443",
               "Authorization": "Bearer client", "X-API-Token": "client", "Cookie": "__Host-rp_session=abc",
               "X-CSRF-Token": "csrf", "X-Forwarded-For": "1.2.3.4", "X-Forwarded-Host": "evil", "Forwarded": "for=x",
               "X-Real-IP": "1.2.3.4", "Tailscale-User-Login": "x", "X-Gateway-User": "2", "Referer": "https://evil/",
               "Connection": "keep-alive, X-Secret", "X-Secret": "hop", "Content-Type": "application/json",
               "Content-Length": "999", "Transfer-Encoding": "chunked", "Accept": "application/json"}
    resp = proxy.forward(_req("POST", "/api/config/rows?x=1", hostile, b'{"a":1}'), ALICE)
    assert resp.status_code == 200
    got = workers[1].requests[-1]
    names = {k.lower(): v for k, v in got["headers"].items()}
    assert names["host"] == f"127.0.0.1:{workers[1].port}"
    assert names["origin"] == f"http://127.0.0.1:{workers[1].port}"
    assert names["x-api-token"] == TOKEN and names["content-length"] == "7"
    for gone in ("authorization", "cookie", "x-csrf-token", "x-forwarded-for", "x-forwarded-host", "forwarded",
                 "x-real-ip", "tailscale-user-login", "x-gateway-user", "referer", "x-secret", "transfer-encoding"):
        assert gone not in names, gone
    assert [k.lower() for k, _ in got["raw_headers"]].count("content-length") == 1
    assert [k.lower() for k, _ in got["raw_headers"]].count("x-api-token") == 1
    assert got["path"] == "/api/config/rows?x=1" and got["body"] == b'{"a":1}'
    assert names["accept"] == "application/json"
    assert workers[2].requests == []  # never the other user's worker


def test_no_origin_is_invented_when_the_client_sent_none(rig):
    proxy, _sup, workers, _q = rig
    proxy.forward(_req("GET", "/api/plan/rows"), BOB)
    names = {k.lower() for k in workers[2].requests[-1]["headers"]}
    assert "origin" not in names


def test_worker_response_cookies_and_cors_are_dropped_and_loopback_redirects_rewritten(rig):
    proxy, _sup, _w, _q = rig
    resp = proxy.forward(_req("GET", "/api/ping"), ALICE)
    keys = {k.lower() for k in resp.headers}
    assert "set-cookie" not in keys and "access-control-allow-origin" not in keys
    assert resp.headers.get("X-Frame-Options") == "DENY"
    resp = proxy.forward(_req("GET", "/redirect"), ALICE)
    assert resp.status_code == 302 and resp.headers["Location"] == "/somewhere"


def test_blocked_routes_and_bad_paths_never_reach_the_worker(rig):
    proxy, _sup, workers, _q = rig
    assert proxy.forward(_req("GET", "/api/build/events/abc"), ALICE).status_code == 403
    assert proxy.forward(_req("POST", "/api/build", {}, b"{}"), ALICE).status_code == 403
    assert proxy.forward(_req("GET", "/api/../x"), ALICE).status_code == 400
    assert proxy.forward(_req("GET", "/a\\b"), ALICE).status_code == 400
    assert workers[1].requests == []


def test_size_limits_and_timeouts(rig):
    proxy, _sup, workers, _q = rig
    assert proxy.forward(_req("POST", "/api/x", {}, b"y" * 1001), ALICE).status_code == 413
    workers[1].big = 6000
    assert proxy.forward(_req("GET", "/big"), ALICE).status_code == 502
    workers[1].big = 100
    assert proxy.forward(_req("GET", "/big"), ALICE).get_data() == b"x" * 100
    workers[1].sleep = 1.5
    assert proxy.forward(_req("GET", "/slow"), ALICE).status_code == 504


def test_a_port_owned_by_another_process_is_never_used(rig):
    proxy, sup, workers, _q = rig
    sup.owner_ok = False
    resp = proxy.forward(_req("GET", "/api/ping"), ALICE)
    assert resp.status_code == 503 and sup.dead and workers[1].requests == []


def test_a_worker_that_cannot_start_gives_503(rig):
    proxy, sup, _w, _q = rig
    sup.unavailable = True
    resp = proxy.forward(_req("GET", "/api/ping"), ALICE)
    assert resp.status_code == 503 and "too long" in resp.get_json()["error"]
    page = proxy.forward(_req("GET", "/"), ALICE)
    assert page.status_code == 503 and page.content_type.startswith("text/html")


def test_builds_queue_behind_the_global_limit_and_dispatch_when_a_slot_frees(rig):
    proxy, _sup, workers, queue = rig
    start = {"Content-Type": "application/json"}
    first = proxy.forward(_req("POST", "/api/build/start", start, b"{}"), ALICE).get_json()
    assert first["job_id"] == "job1" and not first.get("queued")
    again = proxy.forward(_req("POST", "/api/build/start", start, b"{}"), ALICE)
    assert again.status_code == 409  # one build per user
    second = proxy.forward(_req("POST", "/api/build/start", start, b"{}"), BOB).get_json()
    assert second["queued"] is True and second["job_id"].startswith("queued-") and second["position"] == 1
    assert [r["path"] for r in workers[2].requests] == []
    poll = proxy.forward(_req("GET", f"/api/build/progress/{second['job_id']}"), BOB).get_json()
    assert poll["job"]["status"] == "queued"
    # Alice cannot see or cancel Bob's queued build.
    assert proxy.forward(_req("GET", f"/api/build/progress/{second['job_id']}"), ALICE).status_code == 404
    proxy.tick()
    assert workers[2].requests == []  # Alice's build still holds the only slot
    workers[1].jobs["job1"] = "done"
    done = proxy.forward(_req("GET", "/api/build/progress/job1"), ALICE).get_json()
    assert done["job"]["status"] == "done"
    proxy.tick()
    assert [r["path"] for r in workers[2].requests] == ["/api/build/start"]
    poll = proxy.forward(_req("GET", f"/api/build/progress/{second['job_id']}"), BOB).get_json()
    assert poll["job"]["job_id"] == "job1" and poll["job"]["status"] == "running"  # Bob's worker's own id
    assert workers[2].requests[-1]["path"] == "/api/build/progress/job1"


def test_the_monitor_releases_a_slot_when_nobody_polls(rig):
    proxy, _sup, workers, queue = rig
    proxy.forward(_req("POST", "/api/build/start", {"Content-Type": "application/json"}, b"{}"), ALICE)
    assert queue.has_build(1)
    workers[1].jobs["job1"] = "failed"
    proxy.tick()
    assert not queue.has_build(1)


def test_cancelling_a_queued_build(rig):
    proxy, _sup, _w, _q = rig
    proxy.forward(_req("POST", "/api/build/start", {"Content-Type": "application/json"}, b"{}"), ALICE)
    qid = proxy.forward(_req("POST", "/api/build/start", {"Content-Type": "application/json"}, b"{}"), BOB).get_json()["job_id"]
    assert proxy.forward(_req("POST", f"/api/build/cancel/{qid}", {}, b"{}"), BOB).get_json()["outcome"] == "cancelling"
    assert proxy.forward(_req("GET", f"/api/build/progress/{qid}"), BOB).get_json()["job"]["status"] == "cancelled"


def test_a_refused_connection_to_a_live_worker_is_retried_not_treated_as_dead(rig):
    """A full listen backlog looks like a refusal; the worker process still owns its port, so back off and retry."""
    proxy, sup, workers, _q = rig
    port = workers[1].port
    workers[1].server.shutdown()
    workers[1].server.server_close()  # nothing listens now: connections are refused

    def revive() -> None:
        time.sleep(0.15)
        workers[1].server = ThreadingHTTPServer(("127.0.0.1", port), workers[1].server.RequestHandlerClass)
        threading.Thread(target=workers[1].server.serve_forever, daemon=True).start()

    threading.Thread(target=revive, daemon=True).start()
    resp = proxy.forward(_req("GET", "/api/ping"), ALICE)
    assert resp.status_code == 200 and sup.dead == []


def test_a_refused_connection_when_the_port_is_lost_still_marks_the_worker_dead(rig):
    proxy, sup, workers, _q = rig
    workers[1].server.shutdown()
    workers[1].server.server_close()
    sup.owner_ok = False
    assert proxy.forward(_req("GET", "/api/ping"), ALICE).status_code == 503
    assert sup.dead


def test_one_users_parallel_requests_are_bounded_and_all_answered(rig):
    proxy, _sup, workers, _q = rig
    proxy.config = ProxyConfig(max_upstream_per_user=4, read_timeout=5.0)
    workers[1].sleep = 0.05
    live = {"now": 0, "max": 0}
    lock = threading.Lock()
    orig = workers[1].server.RequestHandlerClass

    class Counting(orig):
        def _go(self):
            with lock:
                live["now"] += 1
                live["max"] = max(live["max"], live["now"])
            try:
                super()._go()
            finally:
                with lock:
                    live["now"] -= 1
        do_GET = _go

    workers[1].server.RequestHandlerClass = Counting
    out: list[int] = []
    threads = [threading.Thread(target=lambda: out.append(proxy.forward(_req("GET", "/x"), ALICE).status_code))
               for _ in range(30)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert out == [200] * 30 and live["max"] <= 4


# ---- X-7: the synchronous Monte Carlo run takes a slot from the global build limit ----
def test_plan_runs_share_the_global_limit_wait_their_turn_and_then_get_429(rig):
    proxy, _sup, workers, queue = rig  # the queue allows ONE build or plan run at a time
    proxy.config = ProxyConfig(max_request_bytes=1000, max_response_bytes=5000, read_timeout=5.0,
                               plan_wait_seconds=0.4, plan_poll_seconds=0.02)
    workers[1].sleep = 0.25
    results: dict[str, object] = {}

    def run(name, ident):
        results[name] = proxy.forward(_req("POST", "/api/plan", {"Content-Type": "application/json"}, b'{"x":1}'), ident)

    t1 = threading.Thread(target=run, args=("alice", ALICE))
    t1.start()
    time.sleep(0.08)  # Alice's run is in the worker and holds the only slot
    assert queue.has_build(1)
    t2 = threading.Thread(target=run, args=("bob", BOB))
    t2.start()
    t1.join(5)
    t2.join(5)
    assert results["alice"].status_code == 200
    assert results["bob"].status_code == 200  # Bob waited for the slot, then ran
    assert [r["path"] for r in workers[2].requests] == ["/api/plan"]
    assert not queue.has_build(1) and not queue.has_build(2)  # the slot is released afterwards


def test_a_plan_run_that_cannot_get_a_slot_is_refused_with_retry_after_and_never_reaches_the_worker(rig):
    proxy, _sup, workers, queue = rig
    proxy.config = ProxyConfig(max_request_bytes=1000, read_timeout=1.0, plan_wait_seconds=0.15, plan_poll_seconds=0.02)
    assert queue.try_acquire(1)  # a build holds the only slot
    resp = proxy.forward(_req("POST", "/api/plan", {"Content-Type": "application/json"}, b"{}"), BOB)
    assert resp.status_code == 429 and resp.headers.get("Retry-After") == "5"
    assert "busy" in resp.get_json()["error"]
    assert workers[2].requests == []
    assert queue.has_build(1)  # the build's slot was not touched


def test_a_plan_run_never_releases_a_build_that_started_meanwhile(rig):
    proxy, _sup, workers, queue = rig
    workers[1].sleep = 0.2
    done = {}
    t = threading.Thread(target=lambda: done.setdefault("r", proxy.forward(
        _req("POST", "/api/plan", {"Content-Type": "application/json"}, b"{}"), ALICE)))
    t.start()
    time.sleep(0.05)
    queue.worker_gone(1)           # slot reservation has job_id None, so this leaves it
    queue.finished(1)              # simulate the reservation being cleared elsewhere...
    assert queue.try_acquire(1)    # ...and a new reservation made by a build start
    queue.started(1, "jobX")       # now a real build owns the slot
    t.join(5)
    assert done["r"].status_code == 200
    assert queue.has_build(1), "the plan run released a slot that belongs to a build"
