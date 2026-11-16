"""The gateway runs as its own process, bound to loopback, and answers 302/401 before sign-in."""
from __future__ import annotations

import http.client
import json
import os
import subprocess
import sys
from pathlib import Path


from src.gateway import server

ROOT = Path(__file__).resolve().parents[1]


def test_refuses_a_non_loopback_bind(tmp_path, capsys):
    code = server.main(["--db", str(tmp_path / "g.db"), "--funnel-port", "0", "--public-origin", "https://n.example:8443",
                        "--host", "0.0.0.0"])
    assert code == 2 and "loopback" in capsys.readouterr().err


def test_funnel_listener_needs_a_public_origin(tmp_path, capsys):
    code = server.main(["--db", str(tmp_path / "g.db"), "--funnel-port", "0"])
    assert code == 2 and "--public-origin" in capsys.readouterr().err


def test_public_origin_must_be_https(tmp_path, capsys):
    code = server.main(["--db", str(tmp_path / "g.db"), "--funnel-port", "0", "--public-origin", "http://n.example"])
    assert code == 2 and "https" in capsys.readouterr().err


def test_local_listener_refused_when_tailscale_serves_its_port(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(server, "tailscale_serves_port", lambda port: True)
    code = server.main(["--db", str(tmp_path / "g.db"), "--local-port", "5064"])
    assert code == 2 and "5064" in capsys.readouterr().err


def test_gateway_process_serves_login_and_gates_requests(tmp_path):
    env = dict(os.environ)
    proc = subprocess.Popen([sys.executable, "-m", "src.gateway", "--db", str(tmp_path / "gateway.db"), "--funnel-port", "0",
                             "--local-port", "0", "--public-origin", "https://node.example.ts.net:8443", "--no-tailscale-check"],
                            cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        line = proc.stdout.readline()
        assert line.startswith("RETIREMENT_GATEWAY_READY "), line + proc.stderr.read() if proc.poll() is not None else line
        ports = json.loads(line.split(" ", 1)[1])
        assert ports["funnel_port"] > 0 and ports["local_port"] > 0 and ports["host"] == "127.0.0.1"
        conn = http.client.HTTPConnection("127.0.0.1", ports["local_port"], timeout=10)
        conn.request("GET", "/")
        r = conn.getresponse()
        r.read()
        assert r.status == 302 and r.getheader("Location") == "/login?next=%2F"
        conn.request("GET", "/api/plan/rows")
        r = conn.getresponse()
        assert r.status == 401 and json.loads(r.read())["authenticated"] is False
        conn.request("GET", "/login")
        r = conn.getresponse()
        assert r.status == 200 and b"<form" in r.read()
        conn.close()
        conn = http.client.HTTPConnection("127.0.0.1", ports["funnel_port"], timeout=10)
        conn.request("GET", "/api/ping", headers={"X-Forwarded-For": "203.0.113.5", "Host": "node.example.ts.net:8443"})
        r = conn.getresponse()
        r.read()
        assert r.status == 401
        conn.close()
    finally:
        proc.terminate()
        proc.wait(timeout=10)
