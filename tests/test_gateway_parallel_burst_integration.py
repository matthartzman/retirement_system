"""A browser over Tailscale Funnel (HTTP/2) fires ~128 static requests at once; every one must be answered.

Before the fix the worker listened with the stdlib default backlog of 5, so a burst got connections
refused, the proxy took each refusal for a dead worker, killed a healthy worker and returned 502 for
the rest. This runs the real gateway and the real same-account worker (see
``test_multi_user_isolation_integration.py``) and fires the burst through the gateway as a signed-in user.
"""
from __future__ import annotations

import re
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from test_multi_user_isolation_integration import Client, launch_gateway

pytestmark = [pytest.mark.integration, pytest.mark.e2e]

BURST = 110  # under the gateway's own 128-connection cap, so only the worker side is exercised


@pytest.fixture(scope="module")
def gateway(tmp_path_factory):
    yield from launch_gateway(tmp_path_factory.mktemp("burst"), {"alice": "user"})


def test_a_burst_of_parallel_static_requests_is_all_answered(gateway):
    c = Client(gateway["ready"]["local_port"])
    c.sign_in("alice", gateway["users"]["alice"][1])
    # Wake the worker and read the script list the way a browser does: from the page itself.
    status, _h, page = c.request("GET", "/frontend/index.html")
    assert status == 200
    files = sorted(set(re.findall(r'src="(?:/?frontend/)?(js/[A-Za-z0-9_./-]+\.js)', page.decode("utf-8", "replace"))))[:BURST]
    assert len(files) >= 80
    gate = threading.Barrier(len(files))

    def fetch(name: str) -> tuple[str, int]:
        gate.wait(timeout=30)
        return name, c.request("GET", f"/frontend/{name}")[0]

    with ThreadPoolExecutor(max_workers=len(files)) as pool:
        results = list(pool.map(fetch, files))
    bad = [(n, s) for n, s in results if s != 200]
    assert not bad, f"{len(bad)} of {len(files)} failed: {bad[:5]}"
    log = gateway["log"].read_text(encoding="utf-8", errors="replace")
    killed = [line for line in log.splitlines() if "marked dead" in line]
    assert not killed, f"a healthy worker was killed by the burst: {killed[:2]}"
