"""X-4 / X-5: the Funnel guard fails closed on a failed command, reads the Services section, denies every
no-sign-in local port, and parses targets as URLs."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from src import funnel_guard as fg

NODE = "pc.tail1234.ts.net"


def _run(stdout="", returncode=0):
    return lambda *a, **k: SimpleNamespace(stdout=stdout, returncode=returncode)


def test_non_zero_exit_with_empty_output_is_unverified_not_ok():
    report = fg.check_funnel(gateway_funnel_port=5065, run=_run("", 1))
    assert report.unreadable and not report.ok


def test_non_zero_exit_with_valid_json_is_still_unverified():
    assert fg.check_funnel(gateway_funnel_port=5065, run=_run("{}", 2)).unreadable


def test_empty_output_on_success_is_unverified():
    assert fg.check_funnel(gateway_funnel_port=5065, run=_run("", 0)).unreadable


def test_empty_document_on_success_is_fine():
    assert fg.check_funnel(gateway_funnel_port=5065, run=_run("{}", 0)).ok


@pytest.mark.parametrize("port", [5050, 5056, 5057])
@pytest.mark.parametrize("ext", [443, 8443, 10000])
def test_every_no_sign_in_local_port_is_denied_on_every_external_port(port, ext):
    doc = {"Web": {f"{NODE}:{ext}": {"Handlers": {"/": {"Proxy": f"http://127.0.0.1:{port}"}}}}}
    problems = fg.evaluate(fg.parse_serve_status(doc), gateway_funnel_port=5065)
    assert problems, (port, ext)


def test_services_section_is_parsed_and_checked():
    doc = {"Services": {"svc:planner": {"Web": {"svc:planner:443": {"Handlers": {"/": {"Proxy": "http://127.0.0.1:5056"}}}}}}}
    exposures = fg.parse_serve_status(doc)
    assert [(e.external_port, e.target_port) for e in exposures] == [(443, 5056)]
    assert fg.evaluate(exposures, gateway_funnel_port=5065)


@pytest.mark.parametrize("target,port", [
    ("http://127.0.0.1:5065", 5065),
    ("https+insecure://localhost:5065/x", 5065),
    ("http://[::1]:5065", 5065),
    ("127.0.0.1:5065", 5065),
    ("5065", 5065),
    ("http://127.0.0.1:5065@evil.example:80", None),  # userinfo trick: the host is evil.example
    ("http://evil.example:5065", None),
    ("http://192.168.1.5:5065", None),
    ("http://127.0.0.1", None),
    ("http://127.0.0.1:99999", None),
])
def test_targets_are_parsed_as_urls(target, port):
    assert fg._target_port(target) == port
