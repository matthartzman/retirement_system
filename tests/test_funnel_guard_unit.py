"""Funnel whitelist: the gateway may be published on 8443/10000 only, never a worker or the reporter's local port."""
from __future__ import annotations

import json
import subprocess
from types import SimpleNamespace

import pytest

from src import funnel_guard as fg

pytestmark = pytest.mark.unit

NODE = "hartzmanpc72024.tail1234.ts.net"


def _status(web: dict, funnel: bool = True) -> dict:
    tcp = {str(k.rsplit(":", 1)[1]): {"HTTPS": True} for k in web}
    return {"TCP": tcp,
            "Web": {k: {"Handlers": {"/": {"Proxy": v}}} for k, v in web.items()},
            "AllowFunnel": {k: funnel for k in web}}


def _run_returning(doc):
    return lambda *a, **k: SimpleNamespace(stdout=json.dumps(doc), returncode=0)


def test_the_expected_layout_passes():
    doc = _status({f"{NODE}:443": "http://127.0.0.1:5058", f"{NODE}:8443": "http://127.0.0.1:5065"})
    report = fg.check_funnel(gateway_funnel_port=5065, gateway_local_port=5064, worker_ports=[41000],
                             run=_run_returning(doc))
    assert report.ok and {e.external_port for e in report.exposures} == {443, 8443}


def test_nothing_published_is_fine():
    assert fg.check_funnel(gateway_funnel_port=5065, run=_run_returning({})).ok


@pytest.mark.parametrize("ext,target,needle", [
    (8443, "http://127.0.0.1:41000", "worker"),
    (10000, "http://127.0.0.1:41007", "worker"),
    (443, "http://127.0.0.1:41000", "worker"),
    (443, "http://127.0.0.1:5057", "local port"),
    (8443, "http://127.0.0.1:5057", "local port"),
    (8443, "http://127.0.0.1:5058", "only the gateway"),
    (443, "http://127.0.0.1:5065", "belongs to the trends reporter"),
    (8443, "http://127.0.0.1:5064", "local listener"),
    (8443, "http://127.0.0.1:9999", "only the gateway"),
    (8080, "http://127.0.0.1:5065", "not one of the expected ports"),
])
def test_misconfigurations_are_refused_with_a_reason(ext, target, needle):
    doc = _status({f"{NODE}:{ext}": target})
    report = fg.check_funnel(gateway_funnel_port=5065, gateway_local_port=5064, worker_ports=[41000, 41007],
                             run=_run_returning(doc))
    assert not report.ok and any(needle in p for p in report.problems), report.problems


def test_nested_handlers_and_non_proxy_publications_are_seen():
    doc = {"Web": {f"{NODE}:8443": {"Handlers": {"/": {"Proxy": "http://127.0.0.1:5065"},
                                                  "/app": {"Handlers": {"/x": {"Proxy": "http://127.0.0.1:41000"}}},
                                                  "/files": {"Path": "C:/Users"}}}},
           "AllowFunnel": {f"{NODE}:8443": True}}
    problems = fg.evaluate(fg.parse_serve_status(doc), gateway_funnel_port=5065, worker_ports=[41000])
    assert len(problems) == 2 and any("worker" in p for p in problems) and any("C:/Users" in p for p in problems)


def test_serve_without_funnel_is_still_checked_and_described_as_serve():
    doc = _status({f"{NODE}:8443": "http://127.0.0.1:41000"}, funnel=False)
    problems = fg.evaluate(fg.parse_serve_status(doc), gateway_funnel_port=5065, worker_ports=[41000])
    assert problems and "Serve" in problems[0]


def test_tcp_forward_is_checked():
    doc = {"TCP": {"10000": {"TCPForward": "127.0.0.1:41000"}}, "AllowFunnel": {f"{NODE}:10000": True}}
    problems = fg.evaluate(fg.parse_serve_status(doc), gateway_funnel_port=5065, worker_ports=[41000])
    assert problems and "worker" in problems[0]


def test_missing_or_unreadable_tailscale_is_reported_not_passed():
    def missing(*a, **k):
        raise FileNotFoundError

    assert fg.check_funnel(gateway_funnel_port=5065, run=missing).unreadable
    assert fg.check_funnel(gateway_funnel_port=5065,
                           run=lambda *a, **k: SimpleNamespace(stdout="not json")).unreadable
    assert not fg.check_funnel(gateway_funnel_port=5065, run=missing).ok

    def hung(*a, **k):
        raise subprocess.TimeoutExpired("tailscale", 15)

    assert fg.check_funnel(gateway_funnel_port=5065, run=hung).unreadable


def test_commands_refuse_443_reporter_ports_and_reset():
    assert fg.funnel_command(8443, 5065) == ["tailscale", "funnel", "--bg", "--https=8443", "http://127.0.0.1:5065"]
    assert fg.funnel_command(10000, 5065)[3] == "--https=10000"
    for ext, port in ((443, 5065), (8443, 5057), (8443, 5058), (8443, 80), (5058, 5065)):
        with pytest.raises(ValueError):
            fg.funnel_command(ext, port)
    assert fg.funnel_off_command(8443) == ["tailscale", "funnel", "--https=8443", "off"]
    with pytest.raises(ValueError, match="reset"):
        fg.funnel_off_command(443)


def test_the_reporter_check_is_unchanged():
    from financial_trends_reporter.listeners import check_funnel_target

    out = SimpleNamespace(stdout=json.dumps({"Web": {"h:443": {"Handlers": {"/": {"Proxy": "http://127.0.0.1:5057"}}}}}))
    assert "5057" in check_funnel_target(run=lambda *a, **k: out)
