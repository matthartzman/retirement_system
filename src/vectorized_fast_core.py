from __future__ import annotations

"""Shared vectorized numerical core for optimizer and Monte Carlo.

The optimizer uses this module for covariance/moment math.  Monte Carlo uses the
same covariance/moment path through ``planning_engines._portfolio_asset_class_inputs``
and then applies batched return, inflation, tax, and withdrawal recursions.
"""

from typing import Mapping, Sequence, Any
import numpy as np


def correlation_lookup(correlations: Mapping[tuple[str, str], float], a: str, b: str) -> float:
    if a == b:
        return 1.0
    return float(correlations.get((a, b), correlations.get((b, a), 0.0)))


def covariance_matrix(classes: Sequence[str], asset_classes: Mapping[str, Mapping[str, Any]], correlations: Mapping[tuple[str, str], float]) -> np.ndarray:
    n = len(classes)
    vol = np.array([float(asset_classes[c]['vol']) for c in classes], dtype=float)
    corr = np.eye(n, dtype=float)
    for i, ci in enumerate(classes):
        for j, cj in enumerate(classes):
            corr[i, j] = correlation_lookup(correlations, ci, cj)
    return np.outer(vol, vol) * corr


def portfolio_moments(classes: Sequence[str], weights: Sequence[float], asset_classes: Mapping[str, Mapping[str, Any]], correlations: Mapping[tuple[str, str], float]) -> dict[str, Any]:
    if not classes:
        return {"classes": [], "weights": [], "expected_return": 0.0, "volatility": 0.0, "covariance": np.zeros((0, 0))}
    w = np.array(weights, dtype=float)
    total = float(w.sum())
    if total <= 0:
        w = np.ones(len(classes), dtype=float) / max(1, len(classes))
    else:
        w = w / total
    mu_vec = np.array([float(asset_classes[c]['ret']) for c in classes], dtype=float)
    cov = covariance_matrix(classes, asset_classes, correlations)
    expected = float(w @ mu_vec)
    volatility = float(np.sqrt(max(0.0, w @ cov @ w)))
    return {
        "classes": list(classes),
        "weights": [float(x) for x in w],
        "expected_return": expected,
        "volatility": volatility,
        "covariance": cov,
    }
