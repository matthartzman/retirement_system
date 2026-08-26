"""Resolve the unified spending budget into projection-engine inputs.

The unified spending model is the source of truth for the spending side of
cash flow.  This adapter converts category/group/line budget rows into the
legacy engine keys so the deterministic projection can remain stable while the
UI and data model are consolidated.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

try:  # package import
    from . import spending_tracker as st
except ImportError:  # direct script/test import
    import spending_tracker as st  # type: ignore

EXCLUDED_FROM_SPEND_BASE = {"Income", "Transfer", "Transfers", "Business", "Housing", "Wellness"}
TIME_BOUNDED_LINE_TRACKING_TYPES = {"Travel", "Large Discretionary"}

# ======================================================================
# Spending-tier taxonomy (optimization-refactor Phase 0)
#
# A classification layer above the existing tracking_type/group/category
# structure. Every taxonomy category resolves to exactly one of the four
# tiers below so downstream reporting (and, eventually, a cut-priority
# policy) can treat a reduction in essential care differently from a
# reduction in discretionary travel. This registry only classifies; it
# never changes spend_base, recurring_extras, lump, or any other existing
# dollar total.
# ======================================================================

SPENDING_TIER_ESSENTIAL = "essential"
SPENDING_TIER_IMPORTANT = "important"
SPENDING_TIER_DISCRETIONARY = "discretionary"
SPENDING_TIER_CONTINGENT = "contingent_liability"

#: SPENDING_TIERS keys the four tiers to the taxonomy dimensions that
#: default into them (tracking type, (tracking_type, group) pair, or a
#: specific category_id), plus id substrings used to catch a shock-driven
#: category before a household has explicitly taxonomized it. A household
#: override in client_spending_tier_overrides.csv always wins; see
#: resolve_spending_tier for the full precedence order.
SPENDING_TIERS: dict[str, dict[str, Any]] = {
    SPENDING_TIER_ESSENTIAL: {
        "label": "Essential",
        "description": (
            "Core spending, housing, insurance, baseline transportation, "
            "core health care, and required taxes."
        ),
        "cut_priority": 3,
        "default_tracking_types": {"Wellness", "Housing"},
        "default_groups": {
            ("Core Expenses", "Auto & Transport"),
            ("Core Expenses", "Financial"),
            ("Wellness", "Wellness Budget Detail"),
        },
        "default_category_ids": {"groceries", "ho_insurance"},
    },
    SPENDING_TIER_IMPORTANT: {
        "label": "Important",
        "description": (
            "Meaningful quality-of-life spending: dining, hobbies, everyday "
            "services, gifts, and family support."
        ),
        "cut_priority": 1,
        "default_tracking_types": {"Core Expenses"},
        "default_groups": set(),
        "default_category_ids": {
            "coffee_shops", "fast_food", "restaurants_bars", "fitness",
            "health_club", "exercise_health_equipment", "vitamins_supplements",
            "house_cleaning", "lawn_service_garden_flowers",
            "sprinkler_maintenance", "furniture_home_decor_kitchenware",
        },
    },
    SPENDING_TIER_DISCRETIONARY: {
        "label": "Discretionary",
        "description": (
            "Travel, large gifts, home projects, and other big-ticket "
            "quality-of-life spending -- the first tier to be cut."
        ),
        "cut_priority": 0,
        "default_tracking_types": {"Travel", "Large Discretionary"},
        "default_groups": {
            ("Core Expenses", "Shopping"),
            ("Housing", "Home Improvement"),
        },
        "default_category_ids": set(),
    },
    SPENDING_TIER_CONTINGENT: {
        "label": "Contingent Liability",
        "description": (
            "Long-term care, major medical needs, home modifications, and "
            "other irregular, shock-driven costs modeled as state-dependent "
            "funding requirements rather than ordinary discretionary spending."
        ),
        "cut_priority": 2,
        "default_tracking_types": set(),
        "default_groups": set(),
        "default_category_ids": set(),
        "id_hints": (
            "long_term_care", "ltc", "medical_emergency",
            "home_modification", "accessibility_mod", "in_home_care",
        ),
    },
}

#: Cut order for a future spending-priority policy (Phase 2): discretionary
#: first, then important, then contingent-liability funding rules, with
#: essential protected last. Inert in Phase 0 -- exposed now so later
#: phases have a single source of truth for cut ordering.
SPENDING_TIER_CUT_ORDER = tuple(
    sorted(SPENDING_TIERS, key=lambda t: SPENDING_TIERS[t]["cut_priority"])
)

#: Tracking types that are never household lifestyle spending and are
#: therefore left untiered (Income/Transfer are cash-flow sources, not
#: spending; Business is tracked for reference only and is already excluded
#: from spend_base -- see EXCLUDED_FROM_SPEND_BASE above).
_TIER_UNCLASSIFIED_TRACKING_TYPES = {"Income", "Transfer", "Transfers", "Business"}

_TIER_OVERRIDE_HEADER = ["category_id", "tier", "notes"]


def _tier_override_path(root: str | Path | None) -> Path:
    r = Path(root) if root is not None else st._root(None)  # type: ignore[attr-defined]
    return r / "input" / "client_spending_tier_overrides.csv"


def load_spending_tier_overrides(root: str | Path | None = None) -> dict[str, str]:
    """Household-specific category_id -> tier overrides.

    Stored under input/ alongside the rest of the unified spending
    configuration (taxonomy, budget, aliases) so it travels through the
    same CSV backup/sync/import path used for other user settings.
    """
    _, rows = st._read_csv_dicts(_tier_override_path(root))  # type: ignore[attr-defined]
    overrides: dict[str, str] = {}
    for row in rows:
        cid = (row.get("category_id") or "").strip()
        tier = (row.get("tier") or "").strip().lower()
        if cid and tier in SPENDING_TIERS:
            overrides[cid] = tier
    return overrides


def save_spending_tier_override(root: str | Path | None, category_id: str, tier: str, notes: str = "") -> None:
    """Persist one household tier override; passing a falsy tier clears it."""
    path = _tier_override_path(root)
    _, rows = st._read_csv_dicts(path)  # type: ignore[attr-defined]
    rows = [r for r in rows if (r.get("category_id") or "").strip() != category_id]
    if tier:
        rows.append({"category_id": category_id, "tier": tier.strip().lower(), "notes": notes})
    st._write_csv_dicts(path, _TIER_OVERRIDE_HEADER, rows)  # type: ignore[attr-defined]


def resolve_spending_tier(category_id: str, tracking_type: str, group: str,
                           overrides: dict[str, str] | None = None) -> str | None:
    """Classify one taxonomy category into a spending tier.

    Precedence: household override > category default > group default >
    tracking-type default > contingent-liability id hint > "important"
    fallback. Returns None for Income/Transfer/Business, which are not
    household lifestyle spending.
    """
    if tracking_type in _TIER_UNCLASSIFIED_TRACKING_TYPES:
        return None
    if overrides and category_id in overrides:
        return overrides[category_id]
    for tier, info in SPENDING_TIERS.items():
        if category_id and category_id in info.get("default_category_ids", ()):
            return tier
    key = (tracking_type, group)
    for tier, info in SPENDING_TIERS.items():
        if key in info.get("default_groups", ()):
            return tier
    if category_id:
        cid_lower = category_id.lower()
        for tier, info in SPENDING_TIERS.items():
            if any(hint in cid_lower for hint in info.get("id_hints", ())):
                return tier
    for tier, info in SPENDING_TIERS.items():
        if tracking_type in info.get("default_tracking_types", ()):
            return tier
    return SPENDING_TIER_IMPORTANT


def spending_tier_map(root: str | Path | None = None, flat: dict | None = None) -> dict[str, str]:
    """category_id -> tier for every active taxonomy category.

    Household overrides are applied. Categories whose tracking type is not
    household spending (Income/Transfer/Business) are omitted.
    """
    r = Path(root) if root is not None else st._root(None)  # type: ignore[attr-defined]
    flat = flat if flat is not None else st.taxonomy_flat(r, include_deleted=False)
    overrides = load_spending_tier_overrides(r)
    out: dict[str, str] = {}
    for cid, info in flat.items():
        tier = resolve_spending_tier(cid, info.get("tracking_type") or "", info.get("group") or "", overrides)
        if tier:
            out[cid] = tier
    return out


def _num(value: Any) -> float:
    try:
        return float(str(value or "").replace("$", "").replace(",", "").strip() or 0)
    except Exception:
        return 0.0


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(str(value or "").strip()))
    except Exception:
        return default


def _year_range(year_range: Iterable[int] | None, config: dict | None = None) -> list[int]:
    if year_range is not None:
        return [int(y) for y in year_range]
    if config:
        start = _int(config.get("plan_start"), 0)
        end = _int(config.get("plan_end"), 0)
        if start and end and end >= start:
            return list(range(start, end + 1))
    return []


def _line_years(row: dict, years: list[int]) -> list[int]:
    one = _int(row.get("one_time_year"), 0)
    if one:
        return [one] if not years or one in years else []
    if not years:
        start = _int(row.get("start_year"), 0)
        end = _int(row.get("end_year"), start)
        return list(range(start, end + 1)) if start and end >= start else []
    start = _int(row.get("start_year"), min(years)) or min(years)
    end = _int(row.get("end_year"), max(years)) or max(years)
    if end < start:
        end = start
    return [y for y in years if start <= y <= end]


def _is_home_improvement(info: dict, row: dict) -> bool:
    text = " ".join(str(x or "") for x in [
        info.get("tracking_type"), info.get("group"), info.get("label"), row.get("label"), row.get("notes")
    ]).lower()
    return "home improvement" in text or "home projects" in text or "home project" in text


def resolve_spending_inputs(root: str | Path | None = None, year_range: Iterable[int] | None = None,
                            config: dict | None = None) -> dict:
    """Return budget-derived spending drivers for the projection engine.

    Decisions implemented from the design-review answers:
    1. spend_base includes Core Expenses and recurring non-excluded tracking types;
       excludes Income, Transfer, Business, Housing, Wellness, Travel, and Large
       Discretionary at EVERY level (group, category, and line rows). Travel and
       Large Discretionary dollars only ever reach the projection as extras/lumps
       (the Travel/Other columns), never as core spending.
    2. Business remains in the model, but not in spend_base.
    3. Income is left out of this spending-side resolver, but nothing in the
       file format prevents future income-side use.
    4. Group budget mode disables category and line detail for that group.
    """
    r = Path(root) if root is not None else st._root(None)  # type: ignore[attr-defined]
    years = _year_range(year_range, config)
    flat = st.taxonomy_flat(r, include_deleted=False)
    cat_budgets, group_budgets, line_budgets = st._budget_indexes(r)  # type: ignore[attr-defined]

    spend_base = 0.0
    recurring_extras: list[dict] = []
    lump: dict[int, float] = defaultdict(float)
    lump_by_tt: dict[int, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    home_improvement_lump: dict[int, float] = defaultdict(float)
    by_year: dict[int, dict[str, dict[str, float]]] = {y: {} for y in years}
    by_category_year: dict[int, dict[str, float]] = {y: {} for y in years}
    business_reference = 0.0

    # Spending-tier classification (Phase 0). spend_base is a single
    # plan-wide scalar (not a by-year series), so its tier composition is
    # tracked the same way: one running total per tier, tagged at each of
    # the three sites below that add into spend_base.
    tier_overrides = load_spending_tier_overrides(r)
    spend_base_tier_totals: dict[str, float] = defaultdict(float)

    def _tag_spend_base_tier(cid: str, tt: str, grp: str, amount: float) -> None:
        tier = resolve_spending_tier(cid, tt, grp, tier_overrides)
        if tier:
            spend_base_tier_totals[tier] += amount

    # Group budgets win and suppress their category/line detail.
    group_mode_categories: set[str] = set()
    groups_by_key: dict[str, list[str]] = defaultdict(list)
    for cid, info in flat.items():
        groups_by_key[f"{info.get('tracking_type')}::{info.get('group')}"].append(cid)

    # Track group-level time-bounded budgets to convert to recurring_extras.
    # #231: carries the group row's own start/end year (e.g. a Travel budget
    # that stops after a given year) instead of always spanning the full plan.
    time_bounded_group_budgets: list[tuple[str, str, float, int, int]] = []

    for gkey, grow in group_budgets.items():
        # Honor the persisted group mode. A group row only acts as a summary
        # override (suppressing its category/line detail and projecting the single
        # group amount) when it is in summary mode. In detail mode the group row is
        # inert and the per-category/line detail drives the projection. Rows with no
        # explicit mode default to summary for backward compatibility with budgets
        # saved before the _mode field existed (a group row implied summary then).
        if str(grow.get("_mode") or "").strip().lower() == "detail":
            continue

        amount = _num(grow.get("annual_budget"))
        tt = gkey.split("::", 1)[0] if "::" in gkey else "Core Expenses"
        grp = gkey.split("::", 1)[1] if "::" in gkey else gkey

        if tt == "Business":
            business_reference += amount
        # Time-bounded group budgets (Travel, Large Discretionary) that are set in
        # group mode (summary) should project as recurring_extras, not disappear.
        # Record them for later conversion to recurring_extras.
        if tt in TIME_BOUNDED_LINE_TRACKING_TYPES and amount > 0:
            time_bounded_group_budgets.append((
                tt, grp, amount,
                _int(grow.get("start_year"), 0),
                _int(grow.get("end_year"), 0),
            ))
        elif tt not in EXCLUDED_FROM_SPEND_BASE and tt not in TIME_BOUNDED_LINE_TRACKING_TYPES:
            spend_base += amount
            _tag_spend_base_tier("", tt, grp, amount)

        for cid in groups_by_key.get(gkey, []):
            group_mode_categories.add(cid)
        for y in years:
            tt_map = by_year.setdefault(y, {}).setdefault(tt, {})
            tt_map[grp] = tt_map.get(grp, 0.0) + amount

    # Category budgets are recurring unless their group is in group mode.
    # When a category also has explicit line (detail) rows, those line rows are
    # the sole budget authority for that category — the same rule the UI applies
    # in spending_tracker._category_budget_for_year (lines win, category row is
    # ignored). This holds for EVERY tracking type, not just the domain-owned
    # time-bounded ones (Housing > Home Improvement, Travel, Large Discretionary):
    # a Core Expenses category such as charitable_donations that carries both a
    # $5,000 category row and a $5,000 detail line must count once, not twice.
    # Skipping only Housing/Travel/Large-Disc here previously double-counted such
    # Core-Expenses/Wellness categories into spend_base (item 141 reconciliation).
    categories_with_projection_lines = {cid for cid, rows in line_budgets.items() if rows}
    for cid, row in cat_budgets.items():
        if cid in group_mode_categories:
            continue
        info = flat.get(cid)
        if not info:
            continue
        tt = info.get("tracking_type") or "Core Expenses"
        if cid in categories_with_projection_lines:
            continue
        amount = _num(row.get("annual_budget"))
        grp = info.get("group") or "Other"
        if tt == "Business":
            business_reference += amount
        if tt in TIME_BOUNDED_LINE_TRACKING_TYPES:
            # Core spending must never absorb Travel/Large-Discretionary dollars.
            # A category-level budget with no detail lines still projects — as a
            # recurring extra spanning the plan window (the Travel/Other columns) —
            # instead of leaking into spend_base.
            if amount > 0:
                start = min(years) if years else _int((config or {}).get("plan_start"), 0)
                end = max(years) if years else _int((config or {}).get("plan_end"), start) or start
                recurring_extras.append({
                    "type": info.get("label") or cid,
                    "amount": amount,
                    "start_year": start,
                    "end_year": max(start, end),
                    "comment": row.get("notes", ""),
                    "is_home_improvement": _is_home_improvement(info, row),
                    "source": "unified_budget",
                    "category_id": cid,
                    "tracking_type": tt,
                })
        elif tt not in EXCLUDED_FROM_SPEND_BASE:
            spend_base += amount
            _tag_spend_base_tier(cid, tt, grp, amount)
        for y in years:
            tt_map = by_year.setdefault(y, {}).setdefault(tt, {})
            tt_map[grp] = tt_map.get(grp, 0.0) + amount
            by_category_year.setdefault(y, {})[cid] = by_category_year.setdefault(y, {}).get(cid, 0.0) + amount

    # Line rows feed extras.  Category-budget entries are ignored when their
    # group is in group mode (the group budget takes precedence).  Pure line
    # items — those with no matching category budget row — are never suppressed:
    # they are explicit, time-bounded projections that must always flow through.
    for cid, rows in line_budgets.items():
        if cid in group_mode_categories and cid in cat_budgets:
            continue
        info = flat.get(cid)
        if not info:
            # A line whose key is not an active taxonomy category — a summary
            # rollup row (travel_total / healthcare_total / housing_total, which
            # merely restate domain budgets already projected via their own
            # columns) or an orphaned line whose category was deleted — must not
            # be projected. Without this guard it falls through to the
            # "Large Discretionary" default below and invents phantom spend
            # (e.g. $57,600/yr of Large Discretionary from three summary rows).
            # Mirrors the category-budget loop above, which already skips
            # unmapped keys.
            continue
        tt = info.get("tracking_type") or "Large Discretionary"
        grp = info.get("group") or "Other"
        for row in rows:
            amount = _num(row.get("annual_budget"))
            if amount <= 0:
                continue
            one_year = _int(row.get("one_time_year"), 0)
            active_years = _line_years(row, years)
            is_home = _is_home_improvement(info, row)
            # Non-excluded non-Travel/Large-Discretionary line rows are recurring
            # budget detail and therefore remain in spend_base per Matt's decision.
            # Time-bounded Travel/Large-Disc lines become projection extras instead.
            if tt not in TIME_BOUNDED_LINE_TRACKING_TYPES and tt not in EXCLUDED_FROM_SPEND_BASE:
                spend_base += amount
                _tag_spend_base_tier(cid, tt, grp, amount)
                for y in active_years or years:
                    tt_map = by_year.setdefault(y, {}).setdefault(tt, {})
                    tt_map[grp] = tt_map.get(grp, 0.0) + amount
                    by_category_year.setdefault(y, {})[cid] = by_category_year.setdefault(y, {}).get(cid, 0.0) + amount
                continue
            if one_year:
                if is_home:
                    home_improvement_lump[one_year] += amount
                else:
                    lump[one_year] += amount
                    # Track the one-time lump by tracking type so the current-year
                    # YTD blend can exclude it from the discretionary run-rate floor
                    # (a lump already modeled here must not also be annualized).
                    lump_by_tt[one_year][tt] += amount
            else:
                if active_years:
                    start, end = min(active_years), max(active_years)
                else:
                    start = _int(row.get("start_year"), _int((config or {}).get("plan_start"), 0))
                    end = _int(row.get("end_year"), _int((config or {}).get("plan_end"), start)) or start
                recurring_extras.append({
                    "type": row.get("label") or info.get("label") or cid,
                    "amount": amount,
                    "start_year": start,
                    "end_year": max(start, end),
                    "comment": row.get("notes", ""),
                    "is_home_improvement": is_home,
                    "source": "unified_budget",
                    "category_id": cid,
                    "tracking_type": tt,
                })
            for y in active_years:
                tt_map = by_year.setdefault(y, {}).setdefault(tt, {})
                tt_map[grp] = tt_map.get(grp, 0.0) + amount
                by_category_year.setdefault(y, {})[cid] = by_category_year.setdefault(y, {}).get(cid, 0.0) + amount

    # Convert group-level time-bounded budgets to recurring_extras so they project.
    # These are Travel or Large Discretionary groups in summary mode that suppressed
    # all their category detail. Without this conversion, the budget amounts would be
    # lost and the projection would see zero spending (item 151 reconciliation).
    for tt, grp, amount, grow_start, grow_end in time_bounded_group_budgets:
        if amount > 0:
            plan_start = min(years) if years else _int((config or {}).get("plan_start"), 0)
            plan_end = max(years) if years else _int((config or {}).get("plan_end"), plan_start) or plan_start
            # #231: a group row's own start/end year (e.g. Travel budget ends
            # after a given year) narrows the plan-wide window; 0/blank means
            # "no bound on this side" and falls back to the full plan horizon.
            start = grow_start or plan_start
            end = grow_end or plan_end
            end = max(start, end)
            recurring_extras.append({
                "type": grp,
                "amount": amount,
                "start_year": start,
                "end_year": end,
                "comment": "",
                "is_home_improvement": False,
                "source": "unified_budget",
                "category_id": f"{tt.lower()}::{grp.lower()}",
                "tracking_type": tt,
            })
            for y in years:
                if y < start or y > end:
                    continue
                tt_map = by_year.setdefault(y, {}).setdefault(tt, {})
                tt_map[grp] = tt_map.get(grp, 0.0) + amount

    # spend_base's tier composition, as fractions of spend_base (spend_base
    # itself is a single plan-wide scalar, not by-year, so this is too).
    spend_base_tier_shares: dict[str, float] = {}
    _sb_tier_total = sum(spend_base_tier_totals.values())
    if _sb_tier_total > 0:
        spend_base_tier_shares = {t: v / _sb_tier_total for t, v in spend_base_tier_totals.items()}

    # Whole-household tier rollup (all categories, not just spend_base --
    # Housing, Wellness, Travel, etc. included) for reporting/QC visibility.
    # This does not feed the deterministic engine's spend_by_tier; it is a
    # broader informational cut across everything in by_category_year.
    tier_map = spending_tier_map(r, flat=flat)
    spending_tier_rollup_by_year: dict[int, dict[str, float]] = {}
    for y, cat_amounts in by_category_year.items():
        totals: dict[str, float] = {}
        for cid, amt in cat_amounts.items():
            tier = tier_map.get(cid)
            if tier and amt:
                totals[tier] = totals.get(tier, 0.0) + amt
        if totals:
            spending_tier_rollup_by_year[y] = {t: round(v, 2) for t, v in totals.items()}

    return {
        "spend_base": round(spend_base, 2),
        "recurring_extras": recurring_extras,
        "lump": dict(lump),
        "lump_by_tracking_type": {y: dict(m) for y, m in lump_by_tt.items()},
        "home_improvement_lump": dict(home_improvement_lump),
        "business_reference_budget": round(business_reference, 2),
        "spending_rollup_by_year": by_year,
        "spending_category_rollup_by_year": by_category_year,
        "spend_base_tier_shares": spend_base_tier_shares,
        "spending_tier_rollup_by_year": spending_tier_rollup_by_year,
        "budget_drives_projection": True,
    }


def apply_budget_to_engine_config(config: dict, root: str | Path | None = None) -> dict:
    """Mutate and return an engine config using budget-derived spend drivers.

    If no unified budget dollars exist, the config is left unchanged so tests and
    blank plans keep their previous fallback behavior.
    """
    resolved = resolve_spending_inputs(root=root, config=config)
    if (_num(resolved.get("spend_base")) <= 0
            and not resolved.get("recurring_extras")
            and not resolved.get("lump")
            and not resolved.get("home_improvement_lump")
            and not any((resolved.get("spending_rollup_by_year") or {}).values())
            and not any((resolved.get("spending_category_rollup_by_year") or {}).values())):
        return config
    config["spend_base"] = _num(resolved.get("spend_base"))
    config["recurring_extras"] = list(resolved.get("recurring_extras") or [])
    config["lump"] = dict(resolved.get("lump") or {})
    config["lump_by_tracking_type"] = dict(resolved.get("lump_by_tracking_type") or {})
    config["home_improvement_lump"] = dict(resolved.get("home_improvement_lump") or {})
    config["home_proj"] = 0.0
    config["home_proj_end"] = _int(config.get("plan_start"), 0) - 1
    config["vac"] = 0.0
    config["vac_end"] = _int(config.get("plan_start"), 0) - 1
    config["business_reference_budget"] = resolved.get("business_reference_budget", 0.0)
    config["spending_rollup_by_year"] = resolved.get("spending_rollup_by_year", {})
    config["spending_category_rollup_by_year"] = resolved.get("spending_category_rollup_by_year", {})
    config["spend_base_tier_shares"] = resolved.get("spend_base_tier_shares", {})
    config["spending_tier_rollup_by_year"] = resolved.get("spending_tier_rollup_by_year", {})
    config["budget_drives_projection"] = True
    return config
