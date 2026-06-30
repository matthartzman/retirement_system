from __future__ import annotations

"""Local meta-optimizer coordinator for v10.

This module separates optimizer orchestration from individual optimizers.  It is
single-machine/local-only and deterministic by default.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping
import hashlib
import json


@dataclass(frozen=True)
class OptimizerResult:
    name: str
    score: float
    result: dict[str, Any]
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class MetaOptimizerResult:
    fingerprint: str
    results: tuple[OptimizerResult, ...]
    selected: OptimizerResult | None = None


def config_fingerprint(config: Mapping[str, Any]) -> str:
    payload = json.dumps(config, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def run_meta_optimizer(config: Mapping[str, Any], optimizers: Mapping[str, Callable[[Mapping[str, Any]], dict[str, Any]]]) -> MetaOptimizerResult:
    results = []
    for name, func in optimizers.items():
        raw = func(config)
        score = float(raw.get("score", raw.get("total_objective_score", 0.0)) or 0.0)
        results.append(OptimizerResult(name=name, score=score, result=dict(raw), notes=tuple(raw.get("notes", ()) or ())))
    ordered = tuple(sorted(results, key=lambda r: r.score, reverse=True))
    return MetaOptimizerResult(fingerprint=config_fingerprint(config), results=ordered, selected=ordered[0] if ordered else None)
