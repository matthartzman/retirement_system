from __future__ import annotations
"""real_loss_curves.py — probability of a real (inflation-adjusted) loss by
holding period, per asset class.

Shipped defaults are digitized from the Discipline Funds "Probability of a
Real Loss by Holding Period" reference chart: four curves (Cash/T-bills,
short-intermediate real bonds, a 60/40 blend, and 100% equities), each
sampled at holding years 0,3,5,7,9,11,13,15,17,19,21. Like
the capital market assumptions, this is an editable planning
assumption, not a market forecast: cash's real-loss probability rises with
holding period (inflation erosion), while equities' falls (mean reversion
dominates over long horizons). The shipped curves live in the read-only
reference.db (source reference_src/real_loss_probability.csv); plan-side override
rows can replace individual curves, and this module's constants are the fallback.
"""

from pathlib import Path
from collections import OrderedDict

try:
    from . import allocation_policy as _ap
except ImportError:  # pragma: no cover - allows direct script-style imports
    import allocation_policy as _ap

CASH_CURVE = 'Cash'
BONDS_CURVE = 'Bonds_Short_Intermediate'
BLEND_CURVE = 'Blend_60_40'
EQUITY_CURVE = 'Equities_100'

# Fallback curves for any curve the shipped reference table lacks.
# {curve_name: [(holding_years, real_loss_prob), ...]} sorted ascending.
_BASE_CURVES = {
    CASH_CURVE: [
        (0, 0.08), (3, 0.14), (5, 0.20), (7, 0.26), (9, 0.31), (11, 0.36),
        (13, 0.40), (15, 0.44), (17, 0.47), (19, 0.50), (21, 0.52),
    ],
    BONDS_CURVE: [
        (0, 0.22), (3, 0.20), (5, 0.19), (7, 0.18), (9, 0.17), (11, 0.16),
        (13, 0.16), (15, 0.15), (17, 0.15), (19, 0.14), (21, 0.14),
    ],
    BLEND_CURVE: [
        (0, 0.28), (3, 0.20), (5, 0.14), (7, 0.09), (9, 0.06), (11, 0.03),
        (13, 0.02), (15, 0.01), (17, 0.01), (19, 0.00), (21, 0.00),
    ],
    EQUITY_CURVE: [
        (0, 0.38), (3, 0.30), (5, 0.24), (7, 0.19), (9, 0.14), (11, 0.10),
        (13, 0.07), (15, 0.05), (17, 0.03), (19, 0.02), (21, 0.01),
    ],
}

# Maps each optimizer asset class to the curve that best represents its
# real-loss profile. Growth/equity-like classes (including liquid real
# estate) use the equity curve; core duration/credit classes use the bond
# curve; Cash uses its own curve. Commodities and Managed Futures are
# diversifying/alternative sleeves whose real-loss profile is closer to a
# blended portfolio than to pure equities or pure bonds, so they use the
# blend curve rather than being force-fit into equity or bond.
ASSET_CLASS_CURVE_MAP = OrderedDict([
    ('US Large Cap', EQUITY_CURVE),
    ('US Mid Cap', EQUITY_CURVE),
    ('US Small Cap', EQUITY_CURVE),
    ('International', EQUITY_CURVE),
    ('Emerging Markets', EQUITY_CURVE),
    ('REITs', EQUITY_CURVE),
    ('Commodities', BLEND_CURVE),
    ('Managed Futures', BLEND_CURVE),
    ('Private Credit', BONDS_CURVE),
    ('Bonds', BONDS_CURVE),
    ('Short-Term Bonds', BONDS_CURVE),
    ('TIPS', BONDS_CURVE),
    ('Municipal Bonds', BONDS_CURVE),
    ('Cash', CASH_CURVE),
])

_BASE_CURVE_NAMES = set(_BASE_CURVES.keys())


def _parse_pct(value, default=None):
    try:
        if value is None:
            return default
        text = str(value).strip()
        if not text:
            return default
        is_pct = text.endswith('%')
        text = text.replace('%', '').replace(',', '').strip()
        out = float(text)
        return out / 100.0 if is_pct else out
    except Exception:
        return default


def _curve_points(rows):
    """Build {curve_name: [(years, prob), ...]} sorted ascending from rows.

    Row columns: curve_name,holding_years,real_loss_prob,notes.
    """
    out = {}
    for row in rows:
        name = (row.get('curve_name') or '').strip()
        years = _parse_pct(row.get('holding_years'), None)
        prob = _parse_pct(row.get('real_loss_prob'), None)
        if not name or years is None or prob is None:
            continue
        out.setdefault(name, []).append((float(years), max(0.0, min(1.0, prob))))
    for name in out:
        out[name].sort(key=lambda t: t[0])
    return out


def load_real_loss_curves(c=None):
    """Return {curve_name: [(holding_years, real_loss_prob), ...]}.

    The shipped reference table (reference.db) is authoritative; the hardcoded
    _BASE_CURVES table is a last-resort fallback for curves it lacks. Optional
    plan-side override rows (c['real_loss_curve_rows'], same columns as the shipped
    rows) replace individual curves.
    """
    from .stores.ref_getters.mortality_real_loss import real_loss_rows
    curves = {name: list(pts) for name, pts in _BASE_CURVES.items()}
    for name, pts in _curve_points(real_loss_rows()).items():
        curves[name] = pts

    custom_rows = (c or {}).get('real_loss_curve_rows') if c else None
    if custom_rows:
        for name, pts in _curve_points(custom_rows).items():
            curves[name] = pts
    return curves


def _interpolate(points, years):
    """Piecewise-linear interpolation over sorted (years, prob) points.

    Clamped at both ends: the chart has no data before year 0 or after its
    last sampled year (21), and these curves are not forecasts, so
    extrapolating past the sampled range would overstate precision.
    """
    if not points:
        return 0.0
    years = max(0.0, float(years))
    if years <= points[0][0]:
        return points[0][1]
    if years >= points[-1][0]:
        return points[-1][1]
    for (y0, p0), (y1, p1) in zip(points, points[1:]):
        if y0 <= years <= y1:
            if y1 == y0:
                return p0
            frac = (years - y0) / (y1 - y0)
            return p0 + frac * (p1 - p0)
    return points[-1][1]


def curve_for_asset_class(asset_class):
    cls = _ap.canonical_asset_class(asset_class)
    return ASSET_CLASS_CURVE_MAP.get(cls, BLEND_CURVE)


def real_loss_prob(asset_class, holding_years, c=None, curves=None):
    """Probability of a real loss for ``asset_class`` held ``holding_years``.

    ``curves`` lets callers reuse one load_real_loss_curves() result across
    many lookups (e.g. inside an optimizer objective) instead of re-reading
    the table every call.
    """
    curves = curves if curves is not None else load_real_loss_curves(c)
    curve_name = curve_for_asset_class(asset_class)
    points = curves.get(curve_name) or _BASE_CURVES.get(curve_name) or []
    return _interpolate(points, holding_years)
