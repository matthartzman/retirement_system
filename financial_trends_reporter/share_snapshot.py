"""The shared-view snapshot (Phase 9, ``multi-user-shared-view-design.md`` 5.3 and 5.4): worker mode only.

``POST /api/share-snapshot`` renders the granted tabs of the worker's own active plan into one record for the
gateway's publisher. It runs FI's own ``GET`` handlers in process (the same code and caches as the routes, so it adds
no new reader of the plan), inside the read-only plan scope the worker wrapper holds for the whole request.

A record holds only the routes of the granted tabs (C18). Transactions, account settings, run status, whoami and every
``POST`` are never rendered. In the percent view each body goes through ``percent_view.percent_body``, the very
transform the desktop remote listener applies, with the same basis, and the whole record must then pass
``percent_view.find_money_leaks`` (C19). A route that does not answer 200 is marked ``{"available": false}``; its body
is never copied (C21). The worker refuses unless the active plan is the share's plan (C22).

Only the gateway may call this route: it requires :data:`PUBLISH_HEADER`, which the gateway's proxy strips from every
browser request (``src/gateway/upstream.py``, the ``x-gateway-`` prefix), and the proxy also refuses the path (C23).
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

from src.http_runtime.wsgi_facade import HeaderMap, LocalRequest, Response, request

from . import percent_view

SCHEMA = "shared_view/1"
PUBLISH_HEADER = "X-Gateway-Share-Publish"
SNAPSHOT_RULE = "/api/share-snapshot"
VIEW_NAMES = ("live", "trends", "projections")
# The fixed Time scope presets (index.html's scope picker without Custom) and charts.js's scopeRange rules.
SCOPES = ("week", "month", "3m", "6m", "ytd", "1y", "all")
ALL_TIME_START = date(2025, 2, 1)  # charts.js ALL_TIME_START
TOP_LEVEL_KEYS = frozenset({"schema", "share_id", "scope_rev", "generated_at", "plan", "money_view", "basis_date",
                            "scopes", "views"})
TRENDS_ROUTES = ("/api/history", "/api/balances", "/api/flows", "/api/liquid-change")
_SHARE_ID = re.compile(r"^[0-9a-f]{32}$")


def _add_months(d: date, n: int) -> date:
    """Calendar-month arithmetic with month-end clamping, as charts.js addMonthsStr."""
    total = d.year * 12 + (d.month - 1) + n
    y, m = divmod(total, 12)
    m += 1
    nxt = date(y + (m == 12), 1 if m == 12 else m + 1, 1)
    return date(y, m, min(d.day, (nxt - timedelta(days=1)).day))


def scope_ranges(anchor: date) -> dict[str, dict[str, str]]:
    """Each preset's ``from``/``to``, anchored on the latest data date (charts.js scopeRange)."""
    starts = {"week": anchor - timedelta(days=7), "month": _add_months(anchor, -1), "3m": _add_months(anchor, -3),
              "6m": _add_months(anchor, -6), "ytd": date(anchor.year, 1, 1), "1y": _add_months(anchor, -12),
              "all": ALL_TIME_START}
    return {sc: {"from": starts[sc].isoformat(), "to": anchor.isoformat()} for sc in SCOPES}


def route_plan(views: list[str], scopes: dict[str, dict[str, str]], today: date) -> dict[str, list[tuple[str, str]]]:
    """``{tab: [(record key, request target)]}`` for the granted tabs only. Keys carry the preset, not the dates."""
    out: dict[str, list[tuple[str, str]]] = {}
    for view in views:
        items: list[tuple[str, str]] = []
        if view == "trends":
            items += [(r, r) for r in TRENDS_ROUTES]
            items += [(f"/api/spending?scope={sc}", f"/api/spending?from={r['from']}&to={r['to']}")
                      for sc, r in scopes.items()]
        elif view == "live":
            items += [(f"/api/live-snapshot?scope={sc}", f"/api/live-snapshot?from={r['from']}")
                      for sc, r in scopes.items()]
            items += [(f"/api/realized?tax_year={y}", f"/api/realized?tax_year={y}&group=symbol")
                      for y in (today.year, today.year - 1)]
        elif view == "projections":
            items.append(("/api/projections", "/api/projections"))
        out[view] = items
    return out


def _route_of(key: str) -> str:
    return key.split("?", 1)[0]


def _anchor(history: list[dict], today: date) -> date:
    for entry in reversed(history or []):
        raw = str((entry or {}).get("as_of_date") or "")[:10]
        try:
            return min(date.fromisoformat(raw), today)
        except ValueError:
            continue
    return today


def _json(payload: dict, status: int = 200) -> Response:
    return Response(json.dumps(payload), status=status, content_type="application/json")


def _parse(body: Any) -> dict | None:
    if not isinstance(body, dict):
        return None
    sid, rev, mv, views, plan = (body.get(k) for k in ("share_id", "scope_rev", "money_view", "views",
                                                       "expected_plan_id"))
    if not isinstance(sid, str) or not _SHARE_ID.match(sid):
        return None
    if isinstance(rev, bool) or not isinstance(rev, int) or rev < 1:
        return None
    if mv not in ("percent", "dollars") or not isinstance(plan, str) or not plan.strip():
        return None
    if not isinstance(views, list) or not views or any(v not in VIEW_NAMES for v in views) or len(set(views)) != len(views):
        return None
    return {"share_id": sid, "scope_rev": rev, "money_view": mv, "views": [v for v in VIEW_NAMES if v in views],
            "plan_id": plan.strip()}


def register(app, *, basis: Callable[[], float | None], history: Callable[[], list[dict]],  # noqa: ANN001
             today: Callable[[], date]) -> None:
    """Add the snapshot route to a worker-mode FI app."""

    def _render(target: str) -> tuple[int, Any]:
        req = LocalRequest("GET", target, HeaderMap({"Host": "127.0.0.1"}), b"", environ={"listener": "worker"})
        resp = app.dispatch_request(req)
        if resp.status_code != 200 or not str(resp.mimetype or "").endswith("json"):
            return resp.status_code, None
        try:
            return 200, json.loads(resp.get_data(as_text=True))
        except ValueError:
            return 500, None

    @app.route(SNAPSHOT_RULE, methods=["POST"])
    def share_snapshot():
        if str(request.headers.get(PUBLISH_HEADER, "") or "") != "1":
            return _json({"success": False, "error": "Not found"}, 404)
        ask = _parse(request.get_json(silent=True))
        if ask is None:
            return _json({"success": False, "error": "bad_request"}, 400)
        from src import plan_registry  # noqa: PLC0415

        record = plan_registry.active_record()
        if str(record.get("plan_id") or "") != ask["plan_id"]:
            try:
                plan_registry.get_plan(ask["plan_id"])
            except Exception:  # noqa: BLE001 - deleted, or never registered: the gateway revokes the share
                return _json({"success": False, "error": "plan_missing"}, 410)
            return _json({"success": False, "error": "plan_not_active"}, 409)
        k = None
        if ask["money_view"] == "percent":
            k = basis()
            if k is None:
                return _json({"success": False, "error": "no_basis"}, 409)
        now_day = today()
        scopes = scope_ranges(_anchor(history(), now_day))
        views: dict[str, dict[str, Any]] = {}
        for view, items in route_plan(ask["views"], scopes, now_day).items():
            panel: dict[str, Any] = {}
            for key, target in items:
                status, payload = _render(target)
                if status != 200:
                    panel[key] = {"available": False}  # never the error body: FI errors carry exception text
                    continue
                panel[key] = percent_view.percent_body(_route_of(key), payload, k) if k is not None else payload
            views[view] = panel
        if k is not None and percent_view.find_money_leaks(views):
            return _json({"success": False, "error": "money_leak"}, 422)
        out = {"schema": SCHEMA, "share_id": ask["share_id"], "scope_rev": ask["scope_rev"],
               "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
               "plan": {"id": ask["plan_id"], "name": str(record.get("name") or "")},
               "money_view": ask["money_view"], "basis_date": now_day.isoformat() if k is not None else "",
               "scopes": scopes, "views": views}
        return Response(json.dumps(out, ensure_ascii=False), status=200, content_type="application/json")
