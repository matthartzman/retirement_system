"""Neighborhood Stability Score (NSS) for one ZCTA.

A pure weighted sum: every percentile was computed against the full national
distribution at build time (scripts/build_zip_metrics.py), so nothing here
needs distribution data.

Missing metrics are RENORMALIZED, never zero-filled. Zero-filling would
penalize a rural ZIP for a gap in the eviction dataset rather than for any
property of the place, which is precisely the distortion this model exists to
avoid.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .schema import (
    HIGHER_IS_BETTER,
    NSS_WEIGHTS,
    PCTL_COLUMN,
    ZipRecord,
    band_for,
)


@dataclass(frozen=True)
class NssResult:
    score: float
    band: str
    coverage_pct: float
    components: dict[str, float] = field(default_factory=dict)
    upi_adjusted: bool = False


def _component_score(metric: str, percentile: float) -> float:
    """PDF section 2.2: lower-is-better metrics use 100 * (1 - Percentile)."""
    if metric in HIGHER_IS_BETTER:
        return 100.0 * percentile
    return 100.0 * (1.0 - percentile)


def score_zip(rec: ZipRecord) -> NssResult:
    """Score one ZCTA 0-100, reporting per-metric components and coverage."""
    components: dict[str, float] = {}
    available_weight = 0.0
    weighted_total = 0.0
    for metric, weight in NSS_WEIGHTS.items():
        percentile = getattr(rec, PCTL_COLUMN[metric], None)
        if percentile is None:
            continue
        value = _component_score(metric, float(percentile))
        components[metric] = value
        weighted_total += value * weight
        available_weight += weight
    if available_weight <= 0.0:
        return NssResult(score=0.0, band=band_for(0.0), coverage_pct=0.0, components={})
    score = weighted_total / available_weight
    return NssResult(
        score=score,
        band=band_for(score),
        coverage_pct=available_weight,
        components=components,
    )
