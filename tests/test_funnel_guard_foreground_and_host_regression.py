"""The Funnel whitelist must also see foreground serve sessions and refuse a target that is not this machine."""
from __future__ import annotations

from src import funnel_guard as fg


def _doc(proxy: str, key: str = "node.ts.net:8443") -> dict:
    return {"TCP": {key.rsplit(":", 1)[1]: {"HTTPS": True}},
            "Web": {key: {"Handlers": {"/": {"Proxy": proxy}}}}, "AllowFunnel": {key: True}}


def test_a_foreground_session_is_parsed_like_a_background_one():
    data = {"Foreground": {"session-1": _doc("http://127.0.0.1:5057", "node.ts.net:443")}}
    problems = fg.evaluate(fg.parse_serve_status(data), gateway_funnel_port=5065)
    assert problems and "5057" in problems[0]


def test_a_target_on_another_machine_is_reported():
    data = _doc("http://10.1.2.3:5065")
    problems = fg.evaluate(fg.parse_serve_status(data), gateway_funnel_port=5065)
    assert problems and "10.1.2.3" in problems[0]


def test_the_expected_loopback_target_is_still_accepted():
    for host in ("127.0.0.1", "localhost", "[::1]"):
        data = _doc(f"http://{host}:5065")
        assert fg.evaluate(fg.parse_serve_status(data), gateway_funnel_port=5065) == []
