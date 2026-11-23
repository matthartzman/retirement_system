"""F-06: the guest listener records the address Funnel appended (right-most X-Forwarded-For), never a client-written one."""
from __future__ import annotations

from src.access_core import forwarded_client_ip
from tests.test_trends_access_gate_functional import PW, Rig


def test_helper_takes_the_right_most_entry_and_falls_back():
    assert forwarded_client_ip({"X-Forwarded-For": "6.6.6.6, 198.51.100.7"}) == "198.51.100.7"
    assert forwarded_client_ip({"X-Forwarded-For": " 198.51.100.7 "}) == "198.51.100.7"
    assert forwarded_client_ip({"X-Forwarded-For": ""}, "x") == "x"
    assert forwarded_client_ip({}) == ""


def test_spoofed_leading_entry_is_not_recorded_for_sign_in(tmp_path):
    rig = Rig(tmp_path)
    rig.add()
    rig.call(rig.remote, "POST", "/api/signin", {"username": "ann", "password": PW},
             headers={"X-Forwarded-For": "10.0.0.99, 203.0.113.9"})
    sources = {e["source"] for e in rig.store.read_events() if e["event"] == "signed in"}
    assert sources == {"203.0.113.9"}
    sessions = rig.store.conn.execute("SELECT source FROM app_sessions").fetchall() if hasattr(rig.store, "conn") else []
    assert all("10.0.0.99" not in str(r) for r in sessions)
