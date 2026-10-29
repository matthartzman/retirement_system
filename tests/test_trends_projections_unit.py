"""Recent Projections backend: locating the active plan's projection_tables.json through its latest
build snapshot, caching it by mtime, and keeping dollars away from a percent-only viewer."""
from __future__ import annotations

import json
import os

from financial_trends_reporter import percent_view, projections
from src.active_plan import ensure_plan_file, plan_state, write_build_results

DOC = {
    "schema": "projection_tables/1", "build_id": "b1", "built_at": "2026-10-03T21:56:40Z", "owners": ["A", "B"],
    "tables": {
        "net_worth": {"columns": [{"key": "TOTAL NW", "label": "TOTAL NW", "banner": "TOTAL", "subtotal": True}],
                      "rows": [{"year": 2026, "ages": [64, 65], "values": {"TOTAL NW": 5687742.91}},
                               {"year": 2027, "ages": [65, 66], "values": {"TOTAL NW": 5582247.97}}]},
        "cash_flow": {"columns": [{"key": "Σ_Inc", "label": "Σ Income", "banner": "INCOME", "subtotal": True}],
                      "rows": [{"year": 2026, "ages": [64, 65], "values": {"Σ_Inc": 408768.63}},
                               {"year": 2027, "ages": [65, 66], "values": {"Σ_Inc": 95957.62}}]},
    },
}


def _workspace(tmp_path, doc=DOC, *, snapshot=True, state=None):
    root = tmp_path / "ws"
    out = root / "output" / "plans" / "p1"
    out.mkdir(parents=True)
    plan = root / "plan.rpx"
    ensure_plan_file(plan)
    if snapshot:
        write_build_results("b1", path=plan, plan_state=plan_state(plan) if state is None else state, snapshot={"artifacts": [
            {"file": "retirement_plan.xlsx", "path": str(out / "retirement_plan.xlsx")}]})
    if doc is not None:
        (out / "projection_tables.json").write_text(json.dumps(doc), encoding="utf-8")
    return root, out


def test_missing_when_no_build_results(tmp_path):
    root, _ = _workspace(tmp_path, snapshot=False)
    assert projections.locate(root) is None
    assert projections.load(root) == {"missing": True}


def test_missing_when_file_absent(tmp_path):
    root, _ = _workspace(tmp_path, doc=None)
    assert projections.load(root) == {"missing": True}


def test_missing_when_schema_unknown(tmp_path):
    root, _ = _workspace(tmp_path, doc={**DOC, "schema": "projection_tables/99"})
    assert projections.load(root) == {"missing": True}


def test_locates_via_snapshot_artifact(tmp_path):
    root, out = _workspace(tmp_path)
    assert projections.locate(root) == out / "projection_tables.json"
    data = projections.load(root)
    assert data["tables"]["net_worth"]["rows"][0]["values"]["TOTAL NW"] == 5687742.91
    assert data["plan_first_year"] == 2026 and data["plan_last_year"] == 2027
    assert data["plan_changed"] is False


def test_missing_when_file_is_from_another_build(tmp_path):
    # A build whose JSON write failed leaves no file (the builder clears it); one left over anyway
    # from an earlier build must not pose as this build's numbers.
    root, _ = _workspace(tmp_path, doc={**DOC, "build_id": "b0"})
    assert projections.load(root) == {"missing": True}


def test_plan_changed_when_plan_state_differs(tmp_path):
    # The build writes its results into the plan file after the workbook, so the plan file's mtime
    # can't say "changed since the build"; the recorded plan_state can.
    root, _ = _workspace(tmp_path, state="state-at-build-time")
    assert projections.load(root)["plan_changed"] is True


def test_file_replaced_mid_load_reads_as_missing(tmp_path, monkeypatch):
    # A rebuild can swap the file out between locate() finding it and _read() stat-ing it.
    root, out = _workspace(tmp_path)
    monkeypatch.setattr(projections, "locate", lambda *_a, **_k: out / "gone.json")
    assert projections.load(root) == {"missing": True}


def test_plan_input_check_is_cached_until_the_plan_file_changes(tmp_path, monkeypatch):
    root, _ = _workspace(tmp_path)
    calls = []
    real = projections.plan_state
    monkeypatch.setattr(projections, "plan_state", lambda p: calls.append(p) or real(p))
    projections._plan_state_cache.clear()
    assert projections.load(root)["plan_changed"] is False
    assert projections.load(root)["plan_changed"] is False
    assert len(calls) == 1
    plan = root / "plan.rpx"
    st = plan.stat()
    os.utime(plan, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))
    projections.load(root)
    assert len(calls) == 2


def test_cache_reloads_on_mtime_change(tmp_path):
    root, out = _workspace(tmp_path)
    assert projections.load(root)["owners"] == ["A", "B"]
    path = out / "projection_tables.json"
    path.write_text(json.dumps({**DOC, "owners": ["C", "D"]}), encoding="utf-8")
    st = path.stat()
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))
    assert projections.load(root)["owners"] == ["C", "D"]


def test_percent_viewer_gets_no_dollars(tmp_path):
    root, _ = _workspace(tmp_path)
    data = projections.load(root)
    scaled = percent_view.scale_payload(data, 5_000_000)
    assert percent_view.find_money_leaks(scaled) == []
    row = scaled["tables"]["net_worth"]["rows"][0]
    assert row["year"] == 2026 and row["ages"] == [64, 65]
    assert scaled["plan_changed"] is False
    assert scaled["plan_first_year"] == 2026 and scaled["plan_last_year"] == 2027
    assert abs(row["values"]["TOTAL NW"] - 5687742.91 / 5_000_000) < 1e-12


def test_route_serves_projections(tmp_path):
    from financial_trends_reporter.main import create_app

    root, _ = _workspace(tmp_path)
    app = create_app(root, log_path=tmp_path / "log.jsonl")
    client = app.test_client()
    body = client.get("/api/projections").get_json()
    assert body["build_id"] == "b1"
    for js, marker in (("/projections.js", "mountProjections"), ("/projection_groups.js", "buildTree")):
        resp = client.get(js)
        assert resp.status_code == 200 and marker in resp.get_data(as_text=True)
        assert resp.headers["Content-Type"].startswith("text/javascript")


def test_view_buttons_read_now_then_trends_then_forecast():
    # How are we doing right now, what are the trends, what does it mean forecasting out.
    import re
    from pathlib import Path

    html = (Path(__file__).resolve().parents[1] / "financial_trends_reporter" / "frontend" / "index.html").read_text(encoding="utf-8")
    assert re.findall(r'data-view="(\w+)"', html) == ["live", "trends", "projections"]

