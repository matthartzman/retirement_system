from __future__ import annotations
"""User-facing allocation policy defaults, optimizer eligibility, and ETF examples."""

from collections import OrderedDict

ALLOCATION_MODE_USER = "user_target"
ALLOCATION_MODE_OPTIMIZER = "optimizer_recommendation"
ALLOCATION_MODE_MAX_SHARPE = "max_sharpe"
ALLOCATION_MODE_TANGENCY = "tangency"
ALLOCATION_MODE_CHOICES = (
    ALLOCATION_MODE_USER,
    ALLOCATION_MODE_OPTIMIZER,
    ALLOCATION_MODE_MAX_SHARPE,
    ALLOCATION_MODE_TANGENCY,
)
ALLOCATION_MODE_LABELS = {
    ALLOCATION_MODE_USER: "Use user-specified allocation",
    ALLOCATION_MODE_OPTIMIZER: "Use allocation optimizer recommendation",
    ALLOCATION_MODE_MAX_SHARPE: "Use max-Sharpe allocation (risk-budgeted)",
    ALLOCATION_MODE_TANGENCY: "Use max-Sharpe allocation (pure tangency, no risk budget)",
}
OPTIMIZER_RECOMMENDATION_COMMENT = (
    "Optimizer recommendation is based on risk tolerance or auto risk score, age, withdrawal rate, "
    "years to retirement, human-capital stability, guaranteed-income alternate-crediting mappings, home-equity/REIT "
    "coverage switches, concentration flags, enabled asset classes, capital-market assumptions, "
    "pairwise correlations, glide path, and inflation-sensitive spending. Consider it as a "
    "second-opinion allocation because it can account for household-specific risk capacity and "
    "diversification relationships that a static target mix cannot see."
)
MAX_SHARPE_RECOMMENDATION_COMMENT = (
    "Risk-budgeted max-Sharpe keeps the same equity-vs-bonds/cash risk level as the optimizer "
    "recommendation (same risk tolerance/auto risk score, glide path, and guaranteed-income/home-equity "
    "coverage), but chooses the equity sleeve's sub-class weights to maximize the sleeve's own Sharpe "
    "ratio (expected return in excess of the risk-free rate, per unit of volatility) instead of a fixed "
    "risk-aversion utility. The sleeve's candidate classes are the same ones the optimizer recommendation "
    "already considers eligible on the Asset-Class Allocation Policy page: a class set to Exclude there "
    "never enters the sleeve, and a class set to Consider alternate first and mapped to a covered "
    "non-liquid source (guaranteed income, home equity, ...) is left out once that source's value meets "
    "the target -- e.g. large annuities/home equity replacing the bond/real-estate sleeves there "
    "automatically keeps this optimization scoped to the classes it doesn't already decide. It does not "
    "itself re-optimize the equity/bond/cash split or the fixed-income sub-class ladder."
)
TANGENCY_RECOMMENDATION_COMMENT = (
    "Pure tangency solves for the single long-only portfolio, across the enabled/uncovered asset "
    "classes, with the highest Sharpe ratio -- with no risk-tolerance ceiling or glide path applied. It "
    "still respects each class's Include/Exclude/Consider-alternate-first choice on the Asset-Class "
    "Allocation Policy page: a class set to Exclude is never a candidate, and a class set to Consider "
    "alternate first and mapped to a covered non-liquid source (guaranteed income, home equity, ...) is "
    "left out once that source's value meets the target -- so if this household's annuities/home equity "
    "already fill the fixed-income/real-estate role there, tangency is automatically scoped to the "
    "liquid classes it doesn't already decide, driven by that page rather than a fixed list. This is a "
    "textbook mean-variance tangency portfolio, not a risk-appropriate recommendation: because it freely "
    "trades off risk for Sharpe within its candidate classes, it can concentrate heavily in one class. "
    "Treat it as an analytical reference point and review it against your risk capacity before using it "
    "to drive the plan."
)

SELECTION_INCLUDE = "include"
SELECTION_EXCLUDE = "exclude"
SELECTION_ALTERNATE_FIRST = "consider_alternate_first"
SELECTION_ACTION_CHOICES = (SELECTION_INCLUDE, SELECTION_EXCLUDE, SELECTION_ALTERNATE_FIRST)
SELECTION_ACTION_LABELS = {
    SELECTION_INCLUDE: "Include",
    SELECTION_EXCLUDE: "Exclude",
    SELECTION_ALTERNATE_FIRST: "Consider alternate first",
}

def normalize_selection_action(value: str | None) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "yes": SELECTION_INCLUDE,
        "true": SELECTION_INCLUDE,
        "enabled": SELECTION_INCLUDE,
        "enable": SELECTION_INCLUDE,
        "include": SELECTION_INCLUDE,
        "included": SELECTION_INCLUDE,
        "no": SELECTION_EXCLUDE,
        "false": SELECTION_EXCLUDE,
        "disabled": SELECTION_EXCLUDE,
        "disable": SELECTION_EXCLUDE,
        "exclude": SELECTION_EXCLUDE,
        "excluded": SELECTION_EXCLUDE,
        "alternate": SELECTION_ALTERNATE_FIRST,
        "alternative": SELECTION_ALTERNATE_FIRST,
        "consider_alternate": SELECTION_ALTERNATE_FIRST,
        "consider_alternative": SELECTION_ALTERNATE_FIRST,
        "consider_alternate_first": SELECTION_ALTERNATE_FIRST,
        "consider_alternative_first": SELECTION_ALTERNATE_FIRST,
        "alternate_first": SELECTION_ALTERNATE_FIRST,
        "alternative_first": SELECTION_ALTERNATE_FIRST,
    }
    return aliases.get(text, SELECTION_INCLUDE)

def selection_action_label(value: str | None) -> str:
    return SELECTION_ACTION_LABELS.get(normalize_selection_action(value), SELECTION_ACTION_LABELS[SELECTION_INCLUDE])

ASSET_CLASS_ALIASES = {
    "US Equity": "US Large Cap",
    "US Large Cap Equity": "US Large Cap",
    "US Large": "US Large Cap",
    "Large Cap": "US Large Cap",
    "US Small/Value": "US Small Cap",
    "US Small Value": "US Small Cap",
    "US Small-Cap": "US Small Cap",
    "Small Cap": "US Small Cap",
    "US Mid-Cap": "US Mid Cap",
    "Mid Cap": "US Mid Cap",
    "International Developed": "International",
    "Developed International": "International",
    "EM": "Emerging Markets",
    "Emerging Market": "Emerging Markets",
    "Muni Bonds": "Municipal Bonds",
    "Munis": "Municipal Bonds",
    "Short Term Bonds": "Short-Term Bonds",
    "Short-term Bonds": "Short-Term Bonds",
    "Cash / Money Market": "Cash",
}


def canonical_asset_class(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        return text
    return ASSET_CLASS_ALIASES.get(text, text)


def normalize_allocation_mode(value: str | None) -> str:
    text = str(value or "").strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "optimizer": ALLOCATION_MODE_OPTIMIZER,
        "optimized": ALLOCATION_MODE_OPTIMIZER,
        "optimizer_recommendation": ALLOCATION_MODE_OPTIMIZER,
        "use_optimizer": ALLOCATION_MODE_OPTIMIZER,
        "model": ALLOCATION_MODE_OPTIMIZER,
        "auto": ALLOCATION_MODE_OPTIMIZER,
        "user": ALLOCATION_MODE_USER,
        "manual": ALLOCATION_MODE_USER,
        "user_target": ALLOCATION_MODE_USER,
        "user_specified": ALLOCATION_MODE_USER,
        "target_pct": ALLOCATION_MODE_USER,
        "static": ALLOCATION_MODE_USER,
        "max_sharpe": ALLOCATION_MODE_MAX_SHARPE,
        "sharpe": ALLOCATION_MODE_MAX_SHARPE,
        "sharpe_optimal": ALLOCATION_MODE_MAX_SHARPE,
        "max_sharpe_ratio": ALLOCATION_MODE_MAX_SHARPE,
        "risk_budgeted_max_sharpe": ALLOCATION_MODE_MAX_SHARPE,
        "sharpe_max": ALLOCATION_MODE_MAX_SHARPE,
        "tangency": ALLOCATION_MODE_TANGENCY,
        "tangency_portfolio": ALLOCATION_MODE_TANGENCY,
        "pure_tangency": ALLOCATION_MODE_TANGENCY,
        "unconstrained_sharpe": ALLOCATION_MODE_TANGENCY,
        "max_sharpe_unconstrained": ALLOCATION_MODE_TANGENCY,
    }
    return aliases.get(text, ALLOCATION_MODE_USER)


def allocation_mode_label(value: str | None) -> str:
    return ALLOCATION_MODE_LABELS.get(normalize_allocation_mode(value), ALLOCATION_MODE_LABELS[ALLOCATION_MODE_USER])

# Default user-specified allocation. Users can override any row, but the UI
# requires these rows to total 100%. This default intentionally separates the
# U.S. equity sleeve into large/mid/small cap and includes Cash as its own class.
DEFAULT_ALLOCATION_TARGETS = OrderedDict([
    ("US Large Cap", 0.40),
    ("US Mid Cap", 0.05),
    ("US Small Cap", 0.05),
    ("International", 0.20),
    ("Emerging Markets", 0.05),
    ("Commodities", 0.00),
    ("Bonds", 0.15),
    ("Short-Term Bonds", 0.05),
    ("TIPS", 0.00),
    ("Municipal Bonds", 0.00),
    ("Managed Futures", 0.00),
    ("Private Credit", 0.00),
    ("REITs", 0.00),
    ("Cash", 0.05),
])

# Separate optimizer consideration defaults. These are loaded from the new
# asset_class_optimizer_controls.csv when present. Cash remains included because
# it has existing capital-market assumptions and correlations and is part of the
# user-specified allocation workflow.
DEFAULT_OPTIMIZER_ENABLED = OrderedDict((cls, True) for cls in DEFAULT_ALLOCATION_TARGETS)
DEFAULT_SELECTION_ACTIONS = OrderedDict((cls, SELECTION_INCLUDE) for cls in DEFAULT_ALLOCATION_TARGETS)

ASSET_CLASS_CATEGORIES = {
    "US Large Cap": "Equity",
    "US Mid Cap": "Equity",
    "US Small Cap": "Equity",
    "International": "Equity",
    "Emerging Markets": "Equity",
    "Bonds": "Fixed income",
    "Short-Term Bonds": "Fixed income",
    "TIPS": "Fixed income",
    "Municipal Bonds": "Fixed income",
    "Private Credit": "Fixed income",
    "Cash": "Fixed income",
    "Commodities": "Other",
    "Managed Futures": "Other",
    "REITs": "Other",
}

EXISTING_ASSET_SOURCE_ALIASES = {
    "social security": "Social Security",
    "ss": "Social Security",
    "pension": "Pension",
    "pensions": "Pension",
    "annuity": "Annuities",
    "annuities": "Annuities",
    "note": "Note Receivable",
    "note receivable": "Note Receivable",
    "guaranteed income": "Guaranteed income + note receivable",
    "guaranteed income + note": "Guaranteed income + note receivable",
    "guaranteed income + note receivable": "Guaranteed income + note receivable",
    "home": "Home Equity",
    "home equity": "Home Equity",
    "residence": "Home Equity",
    "cash": "Cash / checking",
    "checking": "Cash / checking",
    "cash / checking": "Cash / checking",
    "cash checking": "Cash / checking",
}

def normalize_existing_asset_source(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    key = text.lower().replace("&", "+").replace("_", " ").replace("-", " ")
    key = " ".join(key.split())
    return EXISTING_ASSET_SOURCE_ALIASES.get(key, text)

DEFAULT_ALTERNATE_ASSET_CLASS = OrderedDict((cls, "") for cls in DEFAULT_ALLOCATION_TARGETS)
DEFAULT_SELECTION_ACTIONS["Bonds"] = SELECTION_ALTERNATE_FIRST
DEFAULT_ALTERNATE_ASSET_CLASS["Bonds"] = "Guaranteed income + note receivable"
DEFAULT_SELECTION_ACTIONS["REITs"] = SELECTION_ALTERNATE_FIRST
DEFAULT_ALTERNATE_ASSET_CLASS["REITs"] = "Home Equity"

ETF_CANDIDATES = {
    "US Large Cap": ["VOO", "IVV", "SCHX"],
    "US Mid Cap": ["VO", "IJH", "SCHM"],
    "US Small Cap": ["VB", "IJR", "SCHA"],
    "International": ["VEA", "IEFA", "SCHF"],
    "Emerging Markets": ["VWO", "IEMG", "EEM"],
    "Commodities": ["PDBC", "DJP", "GSG"],
    "Bonds": ["BND", "AGG", "SCHZ"],
    "Short-Term Bonds": ["SGOV", "SHY", "USFR"],
    "TIPS": ["TIP", "SCHP", "VTIP"],
    "Municipal Bonds": ["MUB", "VTEB", "TFI"],
    "Managed Futures": ["DBMF", "KMLM", "CTA"],
    "Private Credit": ["BKLN", "SRLN", "JAAA"],
    "REITs": ["VNQ", "SCHH", "IYR"],
    "Cash": ["CASH", "SGOV", "BIL"],
}

ASSET_CLASS_NOTES = {
    "US Large Cap": "Default 40%; broad U.S. large-cap stock exposure. Examples: VOO, IVV, SCHX.",
    "US Mid Cap": "Default 5%; U.S. mid-cap equity exposure. Examples: VO, IJH, SCHM.",
    "US Small Cap": "Default 5%; U.S. small-cap equity exposure. Examples: VB, IJR, SCHA.",
    "International": "Default 20%; developed non-U.S. stock exposure. Examples: VEA, IEFA, SCHF.",
    "Emerging Markets": "Default 5%; emerging-market stock exposure. Examples: VWO, IEMG, EEM.",
    "Commodities": "Default 0%; optional real-asset/inflation-shock sleeve. Examples: PDBC, DJP, GSG.",
    "Bonds": "Default 15%; core investment-grade bond exposure. Examples: BND, AGG, SCHZ.",
    "Short-Term Bonds": "Default 5%; short-duration reserve/bond sleeve. Examples: SGOV, SHY, USFR.",
    "TIPS": "Default 0%; optional inflation-linked bonds. Examples: TIP, SCHP, VTIP.",
    "Municipal Bonds": "Default 0%; optional tax-exempt bond sleeve. Examples: MUB, VTEB, TFI.",
    "Managed Futures": "Default 0%; optional trend-following diversifier. Examples: DBMF, KMLM, CTA.",
    "Private Credit": "Default 0%; optional senior-loan/CLO-style credit sleeve. Examples: BKLN, SRLN, JAAA.",
    "REITs": "Default 0%; optional liquid real-estate exposure. Examples: VNQ, SCHH, IYR.",
    "Cash": "Default 5%; liquidity and money-market reserve. Examples: CASH, SGOV, BIL.",
}

FIXED_INCOME_CLASSES = {"Bonds", "Short-Term Bonds", "TIPS", "Municipal Bonds"}
REAL_ESTATE_CLASSES = {"REITs"}
GROWTH_CLASSES = {
    "US Large Cap", "US Mid Cap", "US Small Cap", "International", "Emerging Markets",
    "Commodities", "Managed Futures", "Private Credit", "REITs",
}


def _coerce_float(value, default=0.0):
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


def normalize_targets(targets: dict[str, float] | None) -> OrderedDict[str, float]:
    """Return targets in canonical order, normalized to sum to 1 when possible."""
    raw = targets or DEFAULT_ALLOCATION_TARGETS
    canonical_raw: dict[str, float] = {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            cls = canonical_asset_class(k)
            canonical_raw[cls] = canonical_raw.get(cls, 0.0) + _coerce_float(v, 0.0)
    ordered = OrderedDict()
    for cls, default in DEFAULT_ALLOCATION_TARGETS.items():
        ordered[cls] = max(0.0, canonical_raw.get(cls, default))
    total = sum(ordered.values())
    if total > 0:
        for cls in list(ordered):
            ordered[cls] = ordered[cls] / total
    return ordered


def target_total(targets: dict[str, float] | None) -> float:
    if not targets:
        return sum(DEFAULT_ALLOCATION_TARGETS.values())
    canonical_raw: dict[str, float] = {}
    for k, v in targets.items():
        cls = canonical_asset_class(k)
        canonical_raw[cls] = canonical_raw.get(cls, 0.0) + _coerce_float(v, 0.0)
    return sum(canonical_raw.get(cls, 0.0) for cls in DEFAULT_ALLOCATION_TARGETS)


def default_note(asset_class: str) -> str:
    cls = canonical_asset_class(asset_class)
    return ASSET_CLASS_NOTES.get(cls, f"Default target from recommended allocation mix for {cls}.")
