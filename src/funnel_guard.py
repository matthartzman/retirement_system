"""What Tailscale Funnel / Serve may point at, as a whitelist (shared by the planner gateway and the reporter).

``tailscale serve status --json`` lists, per ``host:external-port``, a handler tree whose ``Proxy`` values are the
local targets.  Rules (the port is the trust boundary, because Funnel delivers every request from 127.0.0.1):

* external 443 may target only the trends reporter's remote port (5058);
* external 8443 or 10000 (the planner) may target only the gateway's Funnel port;
* nothing may target the reporter's local port (5057), the gateway's local port, or any worker's port;
* any other target is reported as unexpected.

Pure parsing and decisions here; ``check_funnel`` is the one function that runs ``tailscale``.
"""
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from typing import Iterable

REPORTER_LOCAL_PORT = 5057
REPORTER_REMOTE_PORT = 5058
PLANNER_EXTERNAL_PORTS = (8443, 10000)
REPORTER_EXTERNAL_PORT = 443
_PORT_RE = re.compile(r"^(?:[a-z][a-z0-9+.-]*://)?(?:\[[^\]]+\]|[^:/\s]+)?:(\d{1,5})(?:/|$)", re.I)


@dataclass(frozen=True)
class Exposure:
    external_port: int
    target_port: int | None
    target: str
    funnel: bool


@dataclass
class FunnelReport:
    problems: list[str] = field(default_factory=list)
    exposures: list[Exposure] = field(default_factory=list)
    unreadable: bool = False

    @property
    def ok(self) -> bool:
        return not self.problems and not self.unreadable


def _target_port(text: str) -> int | None:
    m = _PORT_RE.match(text.strip())
    return int(m.group(1)) if m else None


def parse_serve_status(data: dict) -> list[Exposure]:
    """Every (external port, local target) in a ``tailscale serve status --json`` document."""
    funnel_keys = {k for k, v in (data.get("AllowFunnel") or {}).items() if v}
    found: list[Exposure] = []
    for key, web in (data.get("Web") or {}).items():
        try:
            ext = int(str(key).rsplit(":", 1)[1])
        except (IndexError, ValueError):
            continue
        stack = [web.get("Handlers") or {}]
        while stack:
            for handler in stack.pop().values():
                if not isinstance(handler, dict):
                    continue
                for name in ("Proxy", "Path"):
                    if handler.get(name):
                        target = str(handler[name])
                        found.append(Exposure(ext, _target_port(target) if name == "Proxy" else None, target,
                                              key in funnel_keys))
                if isinstance(handler.get("Handlers"), dict):
                    stack.append(handler["Handlers"])
    for port, tcp in (data.get("TCP") or {}).items():
        fwd = tcp.get("TCPForward") if isinstance(tcp, dict) else None
        if fwd:
            found.append(Exposure(int(port), _target_port(str(fwd)), str(fwd),
                                  any(k.endswith(":" + str(port)) for k in funnel_keys)))
    return found


def evaluate(exposures: Iterable[Exposure], *, gateway_funnel_port: int | None, gateway_local_port: int | None = None,
             worker_ports: Iterable[int] = (), reporter_local_port: int = REPORTER_LOCAL_PORT,
             reporter_remote_port: int = REPORTER_REMOTE_PORT) -> list[str]:
    """Problems, each a sentence an operator can act on; empty when every exposure is allowed."""
    workers = {int(p) for p in worker_ports}
    problems: list[str] = []
    for e in exposures:
        what = f"Tailscale {'Funnel' if e.funnel else 'Serve'} on external port {e.external_port}"
        if e.target_port is None:
            problems.append(f"{what} publishes {e.target!r}, which is not the gateway or the reporter.")
        elif e.target_port in workers:
            problems.append(f"{what} points at port {e.target_port}, a planner worker: workers have no sign-in. "
                            f"Remove it ('tailscale funnel --https={e.external_port} off').")
        elif e.target_port == reporter_local_port:
            problems.append(f"{what} points at port {e.target_port}, the trends reporter's local port, which has "
                            f"no sign-in. Point it at {reporter_remote_port} only.")
        elif gateway_local_port is not None and e.target_port == gateway_local_port:
            problems.append(f"{what} points at port {e.target_port}, the gateway's local listener. Point it at the "
                            f"Funnel port {gateway_funnel_port} only.")
        elif e.external_port == REPORTER_EXTERNAL_PORT:
            if e.target_port != reporter_remote_port:
                problems.append(f"{what} points at port {e.target_port}; 443 belongs to the trends reporter and may "
                                f"target only {reporter_remote_port}.")
        elif e.external_port in PLANNER_EXTERNAL_PORTS:
            if e.target_port != gateway_funnel_port:
                problems.append(f"{what} points at port {e.target_port}; the planner's external ports may target "
                                f"only the gateway's Funnel port ({gateway_funnel_port}).")
        else:
            problems.append(f"{what} is not one of the expected ports "
                            f"({REPORTER_EXTERNAL_PORT}, {', '.join(map(str, PLANNER_EXTERNAL_PORTS))}).")
    return problems


def read_serve_status(run=subprocess.run) -> dict | None:
    """The parsed ``tailscale serve status --json``, or None when tailscale is missing or the output unreadable."""
    try:
        out = run(["tailscale", "serve", "status", "--json"], capture_output=True, text=True, timeout=15)
        text = getattr(out, "stdout", "") or ""
        data = json.loads(text) if text.strip() else {}
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def check_funnel(*, gateway_funnel_port: int | None, gateway_local_port: int | None = None,
                 worker_ports: Iterable[int] = (), run=subprocess.run) -> FunnelReport:
    data = read_serve_status(run)
    if data is None:
        return FunnelReport(unreadable=True)
    exposures = parse_serve_status(data)
    return FunnelReport(evaluate(exposures, gateway_funnel_port=gateway_funnel_port,
                                 gateway_local_port=gateway_local_port, worker_ports=worker_ports), exposures)


def funnel_command(external_port: int, gateway_funnel_port: int) -> list[str]:
    """The exact command that publishes the gateway; refuses any external port but the planner's."""
    if int(external_port) not in PLANNER_EXTERNAL_PORTS:
        raise ValueError(f"the planner may use external port {PLANNER_EXTERNAL_PORTS[0]} or {PLANNER_EXTERNAL_PORTS[1]} "
                         f"only, never {external_port} (443 belongs to the trends reporter)")
    port = int(gateway_funnel_port)
    if not 1024 <= port <= 65535 or port in (REPORTER_LOCAL_PORT, REPORTER_REMOTE_PORT):
        raise ValueError(f"{port} is not a valid gateway Funnel port")
    return ["tailscale", "funnel", "--bg", f"--https={int(external_port)}", f"http://127.0.0.1:{port}"]


def funnel_off_command(external_port: int) -> list[str]:
    if int(external_port) not in PLANNER_EXTERNAL_PORTS:
        raise ValueError("only the planner's external ports can be turned off here; 'tailscale funnel reset' would "
                         "also remove the trends reporter")
    return ["tailscale", "funnel", f"--https={int(external_port)}", "off"]
