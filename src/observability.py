from __future__ import annotations

"""Structured local performance observability.

The local application keeps observability in-process and file-free by default:
callers can collect spans from run configs/result payloads or subscribe to build
queue events.  Every event is a JSON-serializable dictionary with stable keys.
"""

from contextlib import contextmanager
from dataclasses import dataclass, asdict, field
from datetime import datetime, UTC
import time
import uuid
from typing import Any, Iterator, Mapping


@dataclass(frozen=True)
class PerformanceEvent:
    event_id: str
    name: str
    component: str
    event_type: str
    started_at: str
    ended_at: str | None = None
    duration_ms: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _utc() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _sink_from_config(config: Any) -> list[dict[str, Any]] | None:
    if isinstance(config, dict):
        return config.setdefault("performance_events", [])
    return None


def emit_performance_event(config: Any, name: str, component: str, event_type: str = "event", **metadata: Any) -> dict[str, Any]:
    event = PerformanceEvent(
        event_id=uuid.uuid4().hex,
        name=name,
        component=component,
        event_type=event_type,
        started_at=_utc(),
        metadata=dict(metadata),
    ).to_dict()
    sink = _sink_from_config(config)
    if sink is not None:
        sink.append(event)
    return event


@contextmanager
def observe(name: str, component: str, config: Any = None, **metadata: Any) -> Iterator[dict[str, Any]]:
    event_id = uuid.uuid4().hex
    started_iso = _utc()
    started = time.perf_counter()
    event = {
        "event_id": event_id,
        "name": name,
        "component": component,
        "event_type": "span",
        "started_at": started_iso,
        "metadata": dict(metadata),
    }
    sink = _sink_from_config(config)
    if sink is not None:
        sink.append({**event, "phase": "started"})
    try:
        yield event
    finally:
        ended = _utc()
        duration_ms = round((time.perf_counter() - started) * 1000.0, 3)
        completed = {**event, "phase": "completed", "ended_at": ended, "duration_ms": duration_ms}
        if sink is not None:
            sink.append(completed)


def summarize_performance_events(events: list[Mapping[str, Any]]) -> dict[str, Any]:
    spans = [e for e in events or [] if e.get("event_type") == "span" and e.get("phase") == "completed"]
    total_ms = sum(float(e.get("duration_ms") or 0.0) for e in spans)
    by_component: dict[str, float] = {}
    for e in spans:
        comp = str(e.get("component") or "unknown")
        by_component[comp] = by_component.get(comp, 0.0) + float(e.get("duration_ms") or 0.0)
    return {
        "schema": "performance_observability_v1",
        "span_count": len(spans),
        "event_count": len(events or []),
        "total_duration_ms": round(total_ms, 3),
        "duration_ms_by_component": {k: round(v, 3) for k, v in sorted(by_component.items())},
    }
