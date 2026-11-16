"""Run the gateway: ``python -m src.gateway --db <gateway.db> --funnel-port 5065 --public-origin https://<node>.ts.net:8443``.

Two listeners, both bound to 127.0.0.1 and tagged by port (the trust boundary behind Funnel):
the **Funnel** listener, which Tailscale Funnel publishes (external 8443; 443 belongs to the trends
reporter), and an optional **local** listener for use on this machine. Port 0 picks a free port;
the chosen ports are printed as ``RETIREMENT_GATEWAY_READY {json}``.
"""
from __future__ import annotations

import argparse
import json
import logging
import socket
import sys
import threading
from urllib.parse import urlsplit

from src.access_core import is_loopback_host, tailscale_serves_port
from src.http_runtime.server import LocalHTTPServer

from .app import GatewayConfig, GatewayListener, create_gateway_app
from .store import GatewayStore

READY_PREFIX = "RETIREMENT_GATEWAY_READY"


class _GatewayHTTPServer(LocalHTTPServer):
    """No address reuse: on Windows SO_REUSEADDR lets a second process bind the same port."""

    allow_reuse_address = False

    def server_bind(self) -> None:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def _origin(value: str) -> str:
    parts = urlsplit(value.strip())
    if parts.scheme != "https" or not parts.hostname or parts.path not in ("", "/") or parts.query or parts.fragment:
        raise ValueError(f"--public-origin must be an https origin such as https://node.example.ts.net:8443, not {value!r}")
    return f"https://{parts.netloc}"


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m src.gateway", description="Multi-user planner gateway.")
    p.add_argument("--db", required=True, help="path to gateway.db (created when missing)")
    p.add_argument("--host", default="127.0.0.1", help="bind address; only loopback is accepted")
    p.add_argument("--funnel-port", type=int, default=None, help="loopback port Tailscale Funnel points at")
    p.add_argument("--local-port", type=int, default=None, help="optional loopback port for use on this machine")
    p.add_argument("--public-origin", action="append", default=[], help="https origin users reach through Funnel")
    p.add_argument("--no-tailscale-check", action="store_true", help="skip the 'tailscale serve status' check (tests)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    err = sys.stderr
    if args.host != "127.0.0.1" and not is_loopback_host(args.host):
        print("The gateway binds loopback only (127.0.0.1); Tailscale Funnel reaches it there.", file=err)
        return 2
    if args.funnel_port is None and args.local_port is None:
        print("Give --funnel-port, --local-port or both.", file=err)
        return 2
    try:
        origins = tuple(_origin(o) for o in args.public_origin)
    except ValueError as exc:
        print(str(exc), file=err)
        return 2
    if args.funnel_port is not None and not origins:
        print("The Funnel listener needs --public-origin (the https address users open).", file=err)
        return 2
    if args.local_port and not args.no_tailscale_check and tailscale_serves_port(args.local_port):
        print(f"Tailscale is configured to serve port {args.local_port}, the gateway's local listener. Point Funnel at "
              "the --funnel-port only ('tailscale funnel reset', then 'tailscale funnel --https=8443 "
              "http://127.0.0.1:<funnel-port>').", file=err)
        return 2

    logging.basicConfig(level=logging.INFO, stream=err)
    store = GatewayStore(args.db)
    app = create_gateway_app(store, config=GatewayConfig(public_origins=origins))
    servers: dict[str, _GatewayHTTPServer] = {}
    for kind, port in (("funnel", args.funnel_port), ("local", args.local_port)):
        if port is None:
            continue
        srv = _GatewayHTTPServer(("127.0.0.1", int(port)), None)
        srv.retirement_app = GatewayListener(app, kind, srv.server_address[1])
        servers[kind] = srv
    ready = {"host": "127.0.0.1", "funnel_port": servers["funnel"].server_address[1] if "funnel" in servers else None,
             "local_port": servers["local"].server_address[1] if "local" in servers else None,
             "schema_version": store.schema_version()}
    threads = [threading.Thread(target=s.serve_forever, daemon=True) for s in servers.values()]
    for t in threads:
        t.start()
    print(f"{READY_PREFIX} {json.dumps(ready)}", flush=True)
    try:
        for t in threads:
            t.join()
    except KeyboardInterrupt:  # pragma: no cover
        pass
    finally:
        for s in servers.values():
            s.shutdown()
            s.server_close()
    return 0
