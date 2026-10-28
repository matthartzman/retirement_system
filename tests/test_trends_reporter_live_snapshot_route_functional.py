"""GET /api/live-snapshot: wiring between the reporter server and live_snapshot (no network)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from financial_trends_reporter import live_snapshot, main as reporter_main
from financial_trends_reporter.main import create_app


def _workspace(tmp_path: Path) -> Path:
    base_dir = tmp_path / "workspace"
    (base_dir / "input").mkdir(parents=True)
    (base_dir / "local_state").mkdir(parents=True)
    return base_dir


@pytest.fixture
def calls(monkeypatch):
    seen = {"load": [], "build": []}

    def fake_load(base_dir, log_path, balances_db):
        seen["load"].append((Path(base_dir), Path(log_path), Path(balances_db)))
        return {"lots": []}

    def fake_build(*, inputs, data_dir, force=False, **_):
        seen["build"].append({"inputs": inputs, "data_dir": Path(data_dir), "force": force})
        return {"as_of": "2026-10-27T15:18:04Z", "liquid": {"current": 1.0}}

    monkeypatch.setattr(live_snapshot, "load_inputs", fake_load)
    monkeypatch.setattr(live_snapshot, "build", fake_build)
    return seen


def test_live_snapshot_returns_the_build(tmp_path, calls):
    base, log_path = _workspace(tmp_path), tmp_path / "data" / "log.jsonl"
    client = create_app(base, log_path=log_path).test_client()
    resp = client.get("/api/live-snapshot")
    assert resp.status_code == 200
    assert json.loads(resp.get_data(as_text=True))["liquid"]["current"] == 1.0
    assert calls["load"] == [(base, log_path, log_path.with_name("monarch_balances.sqlite3"))]
    assert calls["build"][0]["data_dir"] == log_path.parent
    assert calls["build"][0]["force"] is False


def test_refresh_flag_forces_a_refetch(tmp_path, calls):
    client = create_app(_workspace(tmp_path), log_path=tmp_path / "log.jsonl").test_client()
    client.get("/api/live-snapshot?refresh=1")
    assert calls["build"][0]["force"] is True


def test_build_failure_is_a_json_500(tmp_path, monkeypatch):
    monkeypatch.setattr(live_snapshot, "load_inputs", lambda *a: {"lots": []})

    def boom(**_):
        raise RuntimeError("provider exploded")

    monkeypatch.setattr(live_snapshot, "build", boom)
    resp = create_app(_workspace(tmp_path), log_path=tmp_path / "log.jsonl").test_client().get("/api/live-snapshot")
    assert resp.status_code == 500
    assert "provider exploded" in json.loads(resp.get_data(as_text=True))["error"]


def test_cross_origin_request_is_rejected(tmp_path, calls):
    client = create_app(_workspace(tmp_path), log_path=tmp_path / "log.jsonl").test_client()
    resp = client.get("/api/live-snapshot", headers={"Origin": "http://evil.example", "Host": "127.0.0.1:8770"})
    assert resp.status_code == 403
    assert calls["build"] == []


def test_successful_run_now_clears_the_inputs_cache(tmp_path, monkeypatch):
    cleared = []
    monkeypatch.setattr(live_snapshot, "clear_inputs_cache", lambda: cleared.append(True))
    monkeypatch.setattr(reporter_main, "run_trends_job", lambda *a, **k: {"success": True})
    client = create_app(_workspace(tmp_path), log_path=tmp_path / "log.jsonl").test_client()
    assert client.post("/api/run-now").status_code == 200
    assert cleared == [True]


def test_live_snapshot_js_is_served_as_a_module(tmp_path):
    resp = create_app(_workspace(tmp_path), log_path=tmp_path / "log.jsonl").test_client().get("/live_snapshot.js")
    assert resp.status_code == 200
    assert "javascript" in resp.headers.get("Content-Type", "").lower()
    assert "export function liveViewHtml" in resp.get_data(as_text=True)


# ---- load_inputs caching (live_snapshot) ----

def test_load_inputs_caches_for_ten_minutes_and_clears(monkeypatch):
    live_snapshot.clear_inputs_cache()
    loads, clock = [], [0.0]
    monkeypatch.setattr(live_snapshot, "_load_inputs_uncached", lambda *a: loads.append(a) or {"n": len(loads)})
    tick = lambda: clock[0]  # noqa: E731
    assert live_snapshot.load_inputs("b", "l", "d", clock=tick) == {"n": 1}
    clock[0] = 599
    assert live_snapshot.load_inputs("b", "l", "d", clock=tick) == {"n": 1}
    clock[0] = 600
    assert live_snapshot.load_inputs("b", "l", "d", clock=tick) == {"n": 2}
    live_snapshot.clear_inputs_cache()
    assert live_snapshot.load_inputs("b", "l", "d", clock=tick) == {"n": 3}
    live_snapshot.clear_inputs_cache()


def test_load_inputs_error_is_returned_and_not_cached(monkeypatch):
    live_snapshot.clear_inputs_cache()
    results = iter([OSError("locked"), {"ok": True}])

    def flaky(*a):
        r = next(results)
        if isinstance(r, Exception):
            raise r
        return r

    monkeypatch.setattr(live_snapshot, "_load_inputs_uncached", flaky)
    assert live_snapshot.load_inputs("b", "l", "d") == {"error": "OSError: locked"}
    assert live_snapshot.load_inputs("b", "l", "d") == {"ok": True}
    live_snapshot.clear_inputs_cache()


def test_every_module_index_html_loads_is_served(tmp_path):
    # index.html's module script fails as a whole if any import 404s, leaving every card empty
    # (spending_dock.js shipped without a route). Follow the imports through the served pages.
    import re
    pattern = re.compile(r"""(?:from |src=)["'](?:\./)?([^"']+\.js)["']""")
    client = create_app(_workspace(tmp_path), log_path=tmp_path / "log.jsonl").test_client()
    index = client.get("/")
    assert index.status_code == 200
    queue, served = list(pattern.findall(index.get_data(as_text=True))), set()
    while queue:
        rel = queue.pop().lstrip("/")
        if rel in served:
            continue
        resp = client.get("/" + rel)
        assert resp.status_code == 200, rel
        assert "javascript" in resp.headers.get("Content-Type", "").lower(), rel
        served.add(rel)
        queue.extend(pattern.findall(resp.get_data(as_text=True)))
    assert {"charts.js", "spending_dock.js", "live_snapshot.js"} <= served
