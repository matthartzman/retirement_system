"""Spending tracker — groups YTD transactions into budgetable categories.

Sits on top of the transaction data imported by the YTD tracking module.
Adds a category-to-group mapping layer, budget allocation by group
(as % of core spending), annualized forecasting, and variance metrics.

Tracking types:
  core           — counts toward core spending budget
  model_managed  — tracked separately by the projection model
  income         — income, not spending
  transfer       — excluded entirely
  business       — business expenses, tracked separately from personal
"""
from __future__ import annotations

import csv
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any

_TRACKING_CORE = "core"
_TRACKING_MODEL_TYPES = {"housing", "wellness", "travel", "large_disc"}
_TRACKING_INCOME = "income"
_TRACKING_TRANSFER = "transfer"
_TRACKING_BUSINESS = "business"

_CORE_GROUPS = frozenset({
    "Gifts & Donations", "Auto & Transport", "Housing",
    "Bills & Utilities", "Food & Dining", "Lifestyle",
    "Shopping", "Children", "Education", "Wellness",
    "Financial", "Other",
})


def _root(root: Path | None = None) -> Path:
    if root is not None:
        return Path(root)
    base = os.environ.get("RETIREMENT_SYSTEM_BASE_DIR")
    if base:
        return Path(base)
    return Path(__file__).resolve().parents[1]


def _parse_date(s: str) -> date:
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%Y/%m/%d", "%m-%d-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unparseable date: {s}")


def _safe_float(s: str) -> float:
    try:
        return float(s.replace(",", "").replace("$", "").strip())
    except (ValueError, TypeError, AttributeError):
        return 0.0


# ------------------------------------------------------------------
# Data loading
# ------------------------------------------------------------------

def load_category_map(root: Path | None = None) -> dict[str, dict]:
    """Load spending_category_map.csv → {category_lower: {category, group, supergroup, tracking}}."""
    path = _root(root) / "input" / "spending_category_map.csv"
    if not path.exists():
        return {}
    result: dict[str, dict] = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            cat = (row.get("category") or "").strip()
            if not cat:
                continue
            grp = (row.get("group") or "Other").strip()
            tracking = (row.get("tracking") or _TRACKING_CORE).strip().lower()
            if grp in {"Travel & Lifestyle", "Lifestyle"} and tracking == "travel":
                grp = "Travel"
            if grp == "Transportation":
                grp = "Auto & Transport"
            if grp == "Wellness" and tracking == _TRACKING_CORE:
                grp, tracking = "Medical", "wellness"
            if cat.lower() in {"entertainment & recreation", "entertainment/recreation", "entertainment and recreation"}:
                grp, tracking = "Travel", "travel"
            result[cat.lower()] = {
                "category": cat,
                "group": grp,
                "supergroup": (row.get("super_group") or "Expenses").strip(),
                "tracking": tracking,
            }
    return result


def load_transactions(root: Path | None = None, year: int | None = None) -> list[dict]:
    """Load ytd_transactions.csv, optionally filtered to a calendar year."""
    path = _root(root) / "input" / "ytd_transactions.csv"
    if not path.exists():
        return []
    rows: list[dict] = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            try:
                dt = _parse_date((row.get("Date") or "").strip())
                if year is not None and dt.year != year:
                    continue
                amount = _safe_float(row.get("Amount", "0"))
            except (ValueError, TypeError):
                continue
            rows.append({
                "date": dt,
                "merchant": (row.get("Merchant") or "").strip(),
                "category": (row.get("Category") or "").strip(),
                "account": (row.get("Account") or "").strip(),
                "amount": amount,
                "owner": (row.get("Owner") or "").strip(),
            })
    return rows


def load_budget(root: Path | None = None) -> dict[str, dict]:
    """Load spending_budget.csv → {group: {budget_pct, budget_override, notes}}."""
    path = _root(root) / "input" / "spending_budget.csv"
    if not path.exists():
        return {}
    result: dict[str, dict] = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            group = (row.get("group") or "").strip()
            if not group:
                continue
            result[group] = {
                "budget_pct": _safe_float(row.get("budget_pct", "")),
                "budget_override": _safe_float(row.get("budget_override", "")),
                "notes": (row.get("notes") or "").strip(),
            }
    return result


def save_budget(root: Path | None, budget: dict[str, dict]) -> None:
    """Write spending_budget.csv."""
    path = _root(root) / "input" / "spending_budget.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["group", "budget_pct", "budget_override", "notes"])
        for group in sorted(budget):
            b = budget[group]
            w.writerow([
                group,
                f"{b.get('budget_pct', 0):.1f}" if b.get("budget_pct") else "",
                f"{b.get('budget_override', 0):.0f}" if b.get("budget_override") else "",
                b.get("notes", ""),
            ])


def save_category_map(root: Path | None, rows: list[dict]) -> None:
    """Write spending_category_map.csv from a list of row dicts."""
    path = _root(root) / "input" / "spending_category_map.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["super_group", "group", "category", "tracking"])
        for row in rows:
            w.writerow([
                row.get("super_group", "Expenses"),
                row.get("group", "Other"),
                row.get("category", ""),
                row.get("tracking", "core"),
            ])


# ------------------------------------------------------------------
# Computation
# ------------------------------------------------------------------

def group_actuals(root: Path | None = None, year: int | None = None) -> dict:
    """Aggregate outflow transactions by group using the category map.

    Returns core-only totals for budgeting, plus model_managed and
    business breakouts for reference.
    """
    r = _root(root)
    if year is None:
        year = date.today().year

    cat_map = load_category_map(r)
    txns = load_transactions(r, year)

    today = date.today()
    jan1 = date(year, 1, 1)
    days_elapsed = max(1, (min(today, date(year, 12, 31)) - jan1).days + 1)
    annual_factor = 365.0 / days_elapsed

    groups: dict[str, dict[str, Any]] = {}
    model_managed: dict[str, dict[str, float]] = {}
    business_total = 0.0
    unmapped: set[str] = set()

    def _accum(g: dict, cat: str, merchant: str, spend: float) -> None:
        g["actual"] += spend
        cd = g["categories"].setdefault(cat, {"total": 0.0, "merchants": {}})
        cd["total"] += spend
        md = cd["merchants"].setdefault(merchant or "(no merchant)", {"total": 0.0, "count": 0})
        md["total"] += spend
        md["count"] += 1

    for txn in txns:
        amount = txn["amount"]
        if amount >= 0:
            continue
        spend = abs(amount)
        cat = txn["category"]
        merchant = txn.get("merchant", "") or ""
        cat_lower = cat.lower()
        mapping = cat_map.get(cat_lower)

        if mapping is None:
            unmapped.add(cat)
            mapping = {"group": "Other", "supergroup": "Expenses",
                       "tracking": _TRACKING_CORE, "category": cat}

        tracking = mapping["tracking"]
        if tracking in (_TRACKING_TRANSFER, _TRACKING_INCOME):
            continue
        if tracking in _TRACKING_MODEL_TYPES:
            t = tracking
            if t not in model_managed:
                model_managed[t] = {}
            cat = mapping.get("category", "")
            model_managed[t][cat] = model_managed[t].get(cat, 0) + spend
            continue
        if tracking == _TRACKING_BUSINESS:
            business_total += spend
            g = groups.setdefault("Business", {"actual": 0.0, "categories": {}, "is_business": True})
            _accum(g, cat, merchant, spend)
            continue

        group_name = mapping["group"]
        g = groups.setdefault(group_name, {"actual": 0.0, "categories": {}, "is_business": False})
        _accum(g, cat, merchant, spend)

    total_core = sum(g["actual"] for g in groups.values() if not g.get("is_business"))

    def _serialize_cats(cat_dict: dict) -> list[dict]:
        result = []
        for c, cd in sorted(cat_dict.items(), key=lambda x: -x[1]["total"]):
            merchants = [{"merchant": m, "actual": round(md["total"], 2), "count": md["count"]}
                         for m, md in sorted(cd["merchants"].items(), key=lambda x: -x[1]["total"])]
            result.append({"category": c, "actual": round(cd["total"], 2), "merchants": merchants})
        return result

    result_groups = []
    for gn in sorted(groups):
        g = groups[gn]
        result_groups.append({
            "group": gn,
            "actual": round(g["actual"], 2),
            "annualized": round(g["actual"] * annual_factor, 2),
            "is_business": g.get("is_business", False),
            "categories": _serialize_cats(g["categories"]),
        })

    return {
        "groups": result_groups,
        "total_core_actual": round(total_core, 2),
        "total_core_annualized": round(total_core * annual_factor, 2),
        "business_actual": round(business_total, 2),
        "business_annualized": round(business_total * annual_factor, 2),
        "days_elapsed": days_elapsed,
        "annualization_factor": round(annual_factor, 4),
        "unmapped_categories": sorted(unmapped),
        "model_managed": {k: {cat: round(v, 2) for cat, v in cats.items()} for k, cats in model_managed.items()},
    }


def budget_by_group(root: Path | None = None, core_spending: float = 0) -> dict:
    """Compute budget amounts from percentages x model core spending."""
    r = _root(root)
    budget = load_budget(r)
    groups: dict[str, dict] = {}
    total = 0.0
    for group_name, b in budget.items():
        if b.get("budget_override"):
            amount = b["budget_override"]
        elif b.get("budget_pct") and core_spending > 0:
            amount = round(core_spending * b["budget_pct"] / 100, 2)
        else:
            amount = 0.0
        groups[group_name] = {
            "budget_pct": b.get("budget_pct", 0),
            "budget_amount": amount,
            "budget_override": b.get("budget_override", 0),
        }
        total += amount

    return {
        "groups": groups,
        "total_budget": round(total, 2),
        "model_core_spending": core_spending,
    }


def monthly_series(root: Path | None = None, year: int | None = None,
                   total_budget: float = 0) -> list[dict]:
    """Monthly actual vs budget for the trajectory table."""
    r = _root(root)
    if year is None:
        year = date.today().year

    cat_map = load_category_map(r)
    txns = load_transactions(r, year)

    monthly_spend = [0.0] * 12
    for txn in txns:
        if txn["amount"] >= 0:
            continue
        cat_lower = txn["category"].lower()
        mapping = cat_map.get(cat_lower, {"tracking": _TRACKING_CORE})
        if mapping["tracking"] not in (_TRACKING_CORE,):
            continue
        month_idx = txn["date"].month - 1
        monthly_spend[month_idx] += abs(txn["amount"])

    monthly_budget = total_budget / 12 if total_budget > 0 else 0
    labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    cum_actual = 0.0
    cum_budget = 0.0
    series: list[dict] = []
    today = date.today()
    for i in range(12):
        if date(year, i + 1, 1) > today and i > 0:
            break
        cum_actual += monthly_spend[i]
        cum_budget += monthly_budget
        series.append({
            "month": i + 1,
            "label": labels[i],
            "actual": round(monthly_spend[i], 2),
            "cumulative_actual": round(cum_actual, 2),
            "budget": round(monthly_budget, 2),
            "cumulative_budget": round(cum_budget, 2),
        })
    return series


def spending_dashboard(root: Path | None = None, year: int | None = None,
                       core_spending: float = 0) -> dict:
    """Full dashboard payload for the UI endpoint."""
    r = _root(root)
    if year is None:
        year = date.today().year

    actuals = group_actuals(r, year)
    bdata = budget_by_group(r, core_spending)
    model_spend = core_spending or bdata["model_core_spending"]

    all_groups: set[str] = set()
    for g in actuals["groups"]:
        if not g.get("is_business"):
            all_groups.add(g["group"])
    for gn in bdata["groups"]:
        all_groups.add(gn)

    cat_map = load_category_map(r)

    def _group_tt(cats):
        for c in cats or []:
            m = cat_map.get(str(c.get("category", "")).strip().lower())
            if m:
                return _LEGACY_TRACKING_MAP.get(m.get("tracking", "core"), "Core Expenses")
        return "Core Expenses"

    merged: list[dict] = []
    for gn in sorted(all_groups):
        adata = next((g for g in actuals["groups"]
                      if g["group"] == gn and not g.get("is_business")), None)
        actual = adata["actual"] if adata else 0
        annualized = adata["annualized"] if adata else 0
        cats = adata["categories"] if adata else []

        bg = bdata["groups"].get(gn, {})
        budget_amt = bg.get("budget_amount", 0)
        budget_pct = bg.get("budget_pct", 0)

        variance = annualized - budget_amt if budget_amt else 0
        vpct = (variance / budget_amt * 100) if budget_amt else 0

        status = "over_budget" if vpct > 15 else "watch" if vpct > 5 else "on_track"

        merged.append({
            "group": gn,
            "tracking_type": _group_tt(cats),
            "actual": round(actual, 2),
            "annualized": round(annualized, 2),
            "budget_pct": budget_pct,
            "budget_amount": round(budget_amt, 2),
            "variance": round(variance, 2),
            "variance_pct": round(vpct, 1),
            "status": status,
            "categories": cats,
        })
    merged.sort(key=lambda g: -g["variance"])

    # Business group (separate)
    biz = next((g for g in actuals["groups"] if g.get("is_business")), None)
    business = {
        "actual": biz["actual"] if biz else 0,
        "annualized": biz["annualized"] if biz else 0,
        "categories": biz["categories"] if biz else [],
    } if biz else None

    mseries = monthly_series(r, year, bdata["total_budget"] or model_spend)

    forecast_total = actuals["total_core_annualized"]
    model_variance = (forecast_total - model_spend) if model_spend else 0
    model_vpct = (model_variance / model_spend * 100) if model_spend else 0

    return {
        "success": True,
        "enabled": len(actuals["groups"]) > 0,
        "year": year,
        "days_elapsed": actuals["days_elapsed"],
        "annualization_factor": actuals["annualization_factor"],
        "model_core_spending": round(model_spend, 2),
        "actuals_total": actuals["total_core_actual"],
        "annualized_total": round(forecast_total, 2),
        "budget_total": bdata["total_budget"],
        "forecast_total": round(forecast_total, 2),
        "variance_from_model": round(model_variance, 2),
        "variance_pct": round(model_vpct, 1),
        "groups": merged,
        "business": business,
        "monthly_series": mseries,
        "model_managed": actuals.get("model_managed", {}),
        "unmapped_categories": actuals.get("unmapped_categories", []),
        # Full Tracking Type -> Group -> Category hierarchy (taxonomy-based, with
        # per-level annualized actual + budget) for the expandable bars view.
        "taxonomy_summary": spending_summary_taxonomy(r, year),
    }


def seed_budget_from_actuals(root: Path | None = None, year: int | None = None,
                             core_spending: float = 0) -> dict[str, dict]:
    """Initialize spending_budget.csv from transaction history proportions."""
    r = _root(root)
    actuals = group_actuals(r, year)
    total = actuals["total_core_annualized"]
    if total <= 0:
        return {}
    budget: dict[str, dict] = {}
    for g in actuals["groups"]:
        if g.get("is_business"):
            continue
        pct = round(g["annualized"] / total * 100, 1)
        budget[g["group"]] = {
            "budget_pct": pct,
            "budget_override": 0.0,
            "notes": f"Seeded from {actuals['days_elapsed']}d actuals",
        }
    save_budget(r, budget)
    return budget


# ==================================================================
# Taxonomy  —  3-tier (Tracking Type → Group → Category)
# ==================================================================

#: Canonical display order for the 7 tracking types.
TRACKING_TYPE_ORDER = [
    "Income", "Core Expenses", "Wellness", "Housing",
    "Travel", "Large Discretionary", "Business",
]

#: Map legacy flat-tracking strings to canonical tracking-type names.
_LEGACY_TRACKING_MAP = {
    "core": "Core Expenses",
    "housing": "Housing",
    "wellness": "Wellness",
    "travel": "Travel",
    "large_disc": "Large Discretionary",
    "business": "Business",
    "model_managed": "Housing",
}


def load_taxonomy(root=None):
    """Load client_spending_taxonomy.csv -> nested dict keyed by tracking type."""
    path = _root(root) / "input" / "client_spending_taxonomy.csv"
    result = {}
    if not path.exists():
        return result
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in __import__("csv").DictReader(f):
            tt   = (row.get("section")    or "").strip()
            grp  = (row.get("subsection") or "").strip()
            cid  = (row.get("label")      or "").strip()
            clbl = (row.get("value")      or "").strip()
            note = (row.get("notes")      or "").strip()
            if not (tt and grp and cid):
                continue
            if tt not in result:
                result[tt] = {"label": tt, "groups": {}}
            if grp not in result[tt]["groups"]:
                result[tt]["groups"][grp] = {"label": grp, "categories": []}
            result[tt]["groups"][grp]["categories"].append(
                {"id": cid, "label": clbl, "notes": note}
            )
    return result


def taxonomy_flat(root=None):
    """Flat index: category_id -> {id, label, group, tracking_type}."""
    tree = load_taxonomy(root)
    flat = {}
    for tt, tdata in tree.items():
        for grp, gdata in tdata["groups"].items():
            for cat in gdata["categories"]:
                flat[cat["id"]] = {
                    "id": cat["id"], "label": cat["label"],
                    "group": grp, "tracking_type": tt,
                }
    return flat


def save_taxonomy_category(root, tracking_type, group, cat_id, label, notes=""):
    """Append a new category row."""
    path = _root(root) / "input" / "client_spending_taxonomy.csv"
    write_header = not path.exists()
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = __import__("csv").writer(f)
        if write_header:
            w.writerow(["section", "subsection", "label", "value", "notes"])
        w.writerow([tracking_type, group, cat_id, label, notes])


def update_taxonomy_category(root, cat_id, label, notes):
    """Update label/notes for an existing category id. Returns True if found."""
    import csv as _csv
    path = _root(root) / "input" / "client_spending_taxonomy.csv"
    if not path.exists():
        return False
    rows_out, found = [], False
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = _csv.reader(f)
        header = next(reader, None)
        for row in reader:
            if len(row) >= 3 and row[2].strip() == cat_id:
                found = True
                row = list(row) + [""] * max(0, 5 - len(row))
                row[3], row[4] = label, notes
            rows_out.append(row)
    if found and header:
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = _csv.writer(f)
            w.writerow(header)
            w.writerows(rows_out)
    return found


def delete_taxonomy_category(root, cat_id):
    """Remove a category row by id. Returns True if deleted."""
    import csv as _csv
    path = _root(root) / "input" / "client_spending_taxonomy.csv"
    if not path.exists():
        return False
    rows_out, found = [], False
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = _csv.reader(f)
        header = next(reader, None)
        for row in reader:
            if len(row) >= 3 and row[2].strip() == cat_id:
                found = True
            else:
                rows_out.append(row)
    if found and header:
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = _csv.writer(f)
            w.writerow(header)
            w.writerows(rows_out)
    return found


# ------------------------------------------------------------------
# Mapping rules  (keyword -> category_id)
# ------------------------------------------------------------------

def load_mapping_rules(root=None):
    """Load client_spending_rules.csv -> list of rule dicts sorted by priority desc."""
    import csv as _csv
    path = _root(root) / "input" / "client_spending_rules.csv"
    if not path.exists():
        return []
    rules = []
    with open(path, newline="", encoding="utf-8-sig", errors="replace") as f:
        for row in _csv.DictReader(line.replace('\x00', '') for line in f):
            kw  = (row.get("keyword")     or "").strip()
            cid = (row.get("category_id") or "").strip()
            if not (kw and cid):
                continue
            rules.append({
                "keyword":     kw,
                "category_id": cid,
                "match_field": (row.get("match_field") or "category").strip(),
                "exact":       (row.get("exact") or "").strip().lower() in ("1","true","yes"),
                "priority":    int(row.get("priority") or 50),
            })
    rules.sort(key=lambda r: (-r["priority"], r["keyword"]))
    return rules


def save_mapping_rules(root, rules):
    """Write client_spending_rules.csv."""
    import csv as _csv
    path = _root(root) / "input" / "client_spending_rules.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = _csv.writer(f)
        w.writerow(["keyword", "category_id", "match_field", "exact", "priority"])
        for rule in rules:
            w.writerow([
                rule.get("keyword",""), rule.get("category_id",""),
                rule.get("match_field","category"),
                "1" if rule.get("exact") else "0",
                str(rule.get("priority",50)),
            ])


def apply_mapping_rules(txns, rules, flat=None):
    """Annotate transactions with mapped_category_id using keyword rules."""
    for txn in txns:
        existing = txn.get("mapped_category_id","")
        if existing and existing.startswith("confirmed:"):
            continue
        merchant = (txn.get("merchant") or "").lower()
        category = (txn.get("category") or "").lower()
        matched = None
        for rule in rules:
            kw     = rule["keyword"].lower()
            field  = rule.get("match_field","category")
            target = merchant if field == "merchant" else category
            if rule.get("exact"):
                if target == kw:
                    matched = rule["category_id"]; break
            else:
                if kw in target:
                    matched = rule["category_id"]; break
        if matched:
            txn["mapped_category_id"] = "auto:" + matched
        elif not existing:
            txn["mapped_category_id"] = ""
    return txns


# ------------------------------------------------------------------
# Extended transaction loader
# ------------------------------------------------------------------

def load_transactions_extended(root=None, year=None):
    """Load ytd_transactions.csv including taxonomy columns if present."""
    import csv as _csv
    path = _root(root) / "input" / "ytd_transactions.csv"
    if not path.exists():
        return []
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in _csv.DictReader(f):
            try:
                dt     = _parse_date((row.get("Date") or "").strip())
                if year is not None and dt.year != year:
                    continue
                amount = _safe_float(row.get("Amount","0"))
            except (ValueError, TypeError):
                continue
            rows.append({
                "date":               dt,
                "merchant":           (row.get("Merchant")        or "").strip(),
                "category":           (row.get("Category")        or "").strip(),
                "account":            (row.get("Account")         or "").strip(),
                "amount":             amount,
                "owner":              (row.get("Owner")           or "").strip(),
                "mapped_category_id": (row.get("MappedCategoryId") or "").strip(),
                "confirmed":          (row.get("Confirmed") or "").strip().lower() in ("1","true","yes"),
                "notes":              (row.get("Notes") or "").strip(),
            })
    return rows


# ------------------------------------------------------------------
# Budget by category_id
# ------------------------------------------------------------------

def load_budget_by_category(root=None):
    """Load client_spending_budget.csv -> {category_id: {annual_budget, notes}}."""
    import csv as _csv
    path = _root(root) / "input" / "client_spending_budget.csv"
    if not path.exists():
        return {}
    result = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in _csv.DictReader(f):
            cid = (row.get("category_id") or "").strip()
            if not cid:
                continue
            result[cid] = {
                "annual_budget": _safe_float(row.get("annual_budget","")),
                "notes":         (row.get("notes") or "").strip(),
            }
    return result


def save_budget_by_category(root, budget):
    """Write client_spending_budget.csv indexed by category_id."""
    import csv as _csv
    path = _root(root) / "input" / "client_spending_budget.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = _csv.writer(f)
        w.writerow(["category_id","annual_budget","notes"])
        for cid in sorted(budget):
            b = budget[cid]
            w.writerow([
                cid,
                "%d" % int(b.get("annual_budget",0)) if b.get("annual_budget") else "",
                b.get("notes",""),
            ])


# ------------------------------------------------------------------
# Taxonomy-aware spending summary
# ------------------------------------------------------------------


def _legacy_source_page_for_tracking_type(tracking_type: str | None) -> str:
    tt = (tracking_type or '').strip()
    if tt == 'Housing':
        return 'Housing'
    if tt == 'Wellness':
        return 'Wellness'
    if tt == 'Travel':
        return 'Travel'
    if tt == 'Large Discretionary':
        return 'Large Discretionary'
    return 'Spending Categories'


def _legacy_nonzero_amount(value) -> bool:
    try:
        return abs(float(value or 0)) > 0.004
    except Exception:
        return False

def _legacy_spending_summary_taxonomy(root=None, year=None):
    """Aggregate transactions by Tracking Type -> Group -> Category via taxonomy."""
    from datetime import date as _date
    r = _root(root)
    if year is None:
        year = _date.today().year

    flat      = taxonomy_flat(r)
    rules     = load_mapping_rules(r)
    txns      = load_transactions_extended(r, year)
    apply_mapping_rules(txns, rules, flat)
    cat_map   = load_category_map(r)
    budget_cat = load_budget_by_category(r)

    today      = _date.today()
    jan1       = _date(year, 1, 1)
    days_elapsed  = max(1, (min(today, _date(year, 12, 31)) - jan1).days + 1)
    annual_factor = 365.0 / days_elapsed

    tree     = {}  # {tt -> {grp -> {cid -> {actual, count}}}}
    unmapped = set()

    def _accum(tt, grp, cid, amount):
        tree.setdefault(tt,{}).setdefault(grp,{}).setdefault(cid,{"actual":0.0,"count":0})
        tree[tt][grp][cid]["actual"] += amount
        tree[tt][grp][cid]["count"]  += 1

    for txn in txns:
        amount = txn["amount"]
        if amount >= 0:
            continue
        spend   = abs(amount)
        raw_cat = txn["category"]
        raw_id  = (txn.get("mapped_category_id") or "").replace("auto:","").replace("confirmed:","")

        if raw_id and raw_id in flat:
            info = flat[raw_id]
            tt   = info["tracking_type"]
            if tt.lower() in ("income","transfer"):
                continue
            _accum(tt, info["group"], raw_id, spend)
            continue

        legacy = cat_map.get(raw_cat.lower())
        if legacy:
            tl = (legacy.get("tracking") or "core").lower()
            if tl in ("transfer","income"):
                continue
            tt  = _LEGACY_TRACKING_MAP.get(tl, "Core Expenses")
            grp = legacy.get("group") or "Other"
            _accum(tt, grp, raw_cat, spend)
        else:
            unmapped.add(raw_cat)
            _accum("Core Expenses", "Other", raw_cat, spend)

    output_types  = []
    grand_actual  = 0.0
    grand_budget  = 0.0

    for tt in TRACKING_TYPE_ORDER:
        if tt not in tree:
            output_types.append({
                "tracking_type": tt, "actual": 0.0,
                "annualized": 0.0, "budget": 0.0, "groups": [],
            })
            continue
        type_actual = type_budget = 0.0
        out_groups  = []
        for grp in sorted(tree[tt]):
            ga = gb = 0.0
            out_cats = []
            for cid, cdata in sorted(tree[tt][grp].items()):
                ca  = cdata["actual"]
                ann = ca * annual_factor
                bud = budget_cat.get(cid,{}).get("annual_budget",0.0)
                lbl = flat.get(cid,{}).get("label") or cid
                ga += ca; gb += bud
                out_cats.append({
                    "id": cid, "label": lbl,
                    "actual":    round(ca,2),
                    "annualized":round(ann,2),
                    "budget":    round(bud,2),
                    "count":     cdata["count"],
                })
            # A group-level summary budget (key "grp::<tt>::<group>") overrides the
            # sum of category budgets when the UI is in group-Summary mode.
            grp_override = (budget_cat.get(f"grp::{tt}::{grp}", {}) or {}).get("annual_budget", 0.0) or 0.0
            group_budget = grp_override if grp_override > 0 else gb
            out_groups.append({
                "group":      grp,
                "actual":     round(ga,2),
                "annualized": round(ga*annual_factor,2),
                "budget":     round(group_budget,2),
                "categories": out_cats,
            })
            type_actual += ga; type_budget += group_budget
        output_types.append({
            "tracking_type": tt,
            "actual":     round(type_actual,2),
            "annualized": round(type_actual*annual_factor,2),
            "budget":     round(type_budget,2),
            "groups":     out_groups,
        })
        if tt != "Income":
            grand_actual += type_actual
            grand_budget += type_budget

    return {
        "success":           True,
        "year":              year,
        "days_elapsed":      days_elapsed,
        "annualization_factor": round(annual_factor,4),
        "tracking_types":    output_types,
        "grand_actual":      round(grand_actual,2),
        "grand_annualized":  round(grand_actual*annual_factor,2),
        "grand_budget":      round(grand_budget,2),
        "unmapped_categories": sorted(unmapped),
    }


# ==================================================================
# Unified spending taxonomy / alias / budget model (2026-06-24 spec)
# ==================================================================
# The functions below keep the old public function names as compatibility shims while moving
# storage toward:
#   - client_spending_taxonomy.csv: tracking_type, group, category_id, label, origin, status, notes
#   - client_spending_aliases.csv: match_value, match_field, exact, priority, category_id, source
#   - client_spending_budget.csv: kind, key, label, annual_budget, start_year, end_year, one_time_year, notes

import re as _unified_re

_TAXONOMY_HEADER = ["tracking_type", "group", "category_id", "label", "origin", "status", "notes"]
_ALIAS_HEADER = ["match_value", "match_field", "exact", "priority", "category_id", "source"]
_BUDGET_HEADER = ["kind", "key", "label", "annual_budget", "start_year", "end_year", "one_time_year", "notes", "line_section", "line_mode"]
_EXCLUDED_TRACKING_TYPES_FOR_SPEND_BASE = {"Income", "Transfer", "Business", "Housing", "Wellness"}
_TRANSFER_NAMES = {"Transfer", "Transfers"}


def slugify_category(value: str, max_len: int = 64) -> str:
    """Stable lowercase category-id slug used by migration/promote flows."""
    raw = str(value or "").strip().lower()
    slug = _unified_re.sub(r"[^a-z0-9]+", "_", raw).strip("_")
    return (slug[:max_len].strip("_") or "uncategorized")


def _csv_bool(value: Any, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(str(value or "").replace(",", "").strip()))
    except Exception:
        return default


def _read_csv_dicts(path: Path) -> tuple[list[str], list[dict]]:
    if not path.exists():
        return [], []
    with open(path, newline="", encoding="utf-8-sig", errors="replace") as f:
        reader = csv.DictReader(line.replace("\x00", "") for line in f)
        header = list(reader.fieldnames or [])
        return header, [dict(row) for row in reader]


def _write_csv_dicts(path: Path, header: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in header})


def _normalize_tracking_type(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "Core Expenses"
    lower = raw.lower()
    if lower in _LEGACY_TRACKING_MAP:
        return _LEGACY_TRACKING_MAP[lower]
    if lower in {"large discretionary expenses", "large discretionary"}:
        return "Large Discretionary"
    if lower in {"business expenses", "business"}:
        return "Business"
    if lower in {"transfer", "transfers"}:
        return "Transfer"
    for tt in TRACKING_TYPE_ORDER + ["Transfer"]:
        if lower == tt.lower():
            return tt
    return raw


def _normalize_spending_group_assignment(tracking_type: str, group: str, category_id: str, label: str) -> tuple[str, str]:
    """Apply current category architecture to legacy/stale taxonomy rows."""
    tt = _normalize_tracking_type(tracking_type)
    grp = (group or "Other").strip()
    cid = (category_id or "").strip().lower()
    lab = (label or "").strip().lower()

    # Cross-cutting group consolidation requested in the spending architecture follow-ups.
    if grp in {"Food / Dining", "Food & Dining"}:
        grp = "Food & Dining"
    if grp in {"Gifts & Donations", "Gifts / Charity", "Gifts Charity"}:
        grp = "Gifts Charity"
    if grp in {"Travel & Lifestyle", "Lifestyle", "Travel Detail"} and tt == "Travel":
        grp = "Travel"
    if grp == "Transportation":
        grp = "Auto & Transport"

    if cid in {"entertainment_recreation", "entertainment_and_recreation"} or lab in {"entertainment & recreation", "entertainment/recreation", "entertainment and recreation"}:
        return "Travel", "Travel"

    if tt == "Housing":
        housing_groups = {
            "mortgage": "Mortgage",
            "rent": "Mortgage",
            "real_estate_taxes": "Real Estate Taxes",
            "ho_insurance": "Other",
            "homeowners_insurance": "Other",
            "garbage": "Utilities",
            "gas_electric": "Utilities",
            "internet_cable": "Utilities",
            "phone": "Utilities",
            "sewer": "Utilities",
            "water": "Utilities",
            "dry_cleaners": "Utilities",
            "pest_control": "Utilities",
            "home_improvement": "Home Improvement",
            "other_improvement": "Home Improvement",
            "home_maintenance": "Maintenance",
            "furniture_home_decor_kitchenware": "Other",
            "house_cleaning": "Other",
            "lawn_service_garden_flowers": "Other",
            "sprinkler_maintenance": "Other",
        }
        if cid in housing_groups:
            return "Housing", housing_groups[cid]
        if grp == "Bills & Utilities":
            return "Housing", "Utilities"
        if grp == "Housing":
            return "Housing", "Other"

    # Business is shown as one tracking type with the requested business categories underneath it.
    if tt == "Business":
        return "Business", "Business"

    premium_ids = {"pre65_wellness_premium", "wellness_premium", "medicare_part_b", "medicare_part_d", "medigap_premium", "aca_marketplace_premium", "cobra_premium", "employer_health_premium"}
    if tt == "Wellness" and cid in premium_ids:
        return "Wellness", "Healthcare Premium"
    if tt == "Wellness" and cid in {"annual_oop_max", "annual_oop_estimate_today"}:
        return "Wellness", "Medical Cap Reference"

    health_tokens = ("dentist", "dental", "vision", "medical", "health", "pharmacy", "drug", "rx", "otc", "dermatologist", "doctor", "hospital", "therapy", "medicare", "premium")
    if tt == "Core Expenses" and (grp == "Wellness" or any(tok in cid or tok in lab for tok in health_tokens)):
        if "dental" in cid or "dentist" in cid or "dental" in lab or "dentist" in lab:
            return "Wellness", "Dental"
        if "vision" in cid or "vision" in lab or "eye" in cid or "eye" in lab:
            return "Wellness", "Vision"
        if any(tok in cid or tok in lab for tok in ("drug", "rx", "pharmacy", "otc")):
            return "Wellness", "Drugs - Rx/OTC"
        if any(tok in cid or tok in lab for tok in ("premium", "medicare")):
            return "Wellness", "Healthcare Premium"
        return "Wellness", "Medical"
    return tt, grp


def _taxonomy_rows(root=None, include_deleted: bool = True) -> list[dict]:
    """Return normalized taxonomy rows from either old or new schema."""
    path = _root(root) / "input" / "client_spending_taxonomy.csv"
    header, rows = _read_csv_dicts(path)
    out: list[dict] = []
    new_schema = {"tracking_type", "group", "category_id", "label"}.issubset(set(header))
    for row in rows:
        if new_schema:
            tt = _normalize_tracking_type(row.get("tracking_type"))
            grp = (row.get("group") or "Other").strip()
            cid = (row.get("category_id") or "").strip()
            label = (row.get("label") or cid).strip()
            origin = (row.get("origin") or "template").strip().lower() or "template"
            status = (row.get("status") or "active").strip().lower() or "active"
            notes = (row.get("notes") or "").strip()
        else:
            tt = _normalize_tracking_type(row.get("section"))
            grp = (row.get("subsection") or "Other").strip()
            cid = (row.get("label") or "").strip()
            label = (row.get("value") or cid).strip()
            origin = "template"
            status = "active"
            notes = (row.get("notes") or "").strip()
        if not (tt and grp and cid):
            continue
        if status not in {"active", "deleted"}:
            status = "active"
        if origin not in {"template", "transaction", "custom"}:
            origin = "custom"
        tt, grp = _normalize_spending_group_assignment(tt, grp, cid, label)
        normalized = {
            "tracking_type": tt,
            "group": grp,
            "category_id": cid,
            "label": label,
            "origin": origin,
            "status": status,
            "notes": notes,
        }
        if include_deleted or status != "deleted":
            out.append(normalized)
    return out


def _write_taxonomy_rows(root, rows: list[dict]) -> None:
    normalized: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        cid = (row.get("category_id") or row.get("id") or "").strip()
        if not cid or cid in seen:
            continue
        seen.add(cid)
        label = (row.get("label") or cid).strip()
        tt, grp = _normalize_spending_group_assignment(row.get("tracking_type"), row.get("group"), cid, label)
        normalized.append({
            "tracking_type": tt,
            "group": grp,
            "category_id": cid,
            "label": label,
            "origin": (row.get("origin") or "custom").strip().lower() or "custom",
            "status": (row.get("status") or "active").strip().lower() or "active",
            "notes": (row.get("notes") or "").strip(),
        })
    order = {tt: i for i, tt in enumerate(TRACKING_TYPE_ORDER + ["Transfer"])}
    normalized.sort(key=lambda r: (order.get(r["tracking_type"], 999), r["group"].lower(), r["label"].lower(), r["category_id"]))
    _write_csv_dicts(_root(root) / "input" / "client_spending_taxonomy.csv", _TAXONOMY_HEADER, normalized)


def load_taxonomy(root=None, include_deleted: bool = False):
    """Load canonical taxonomy as Tracking Type -> Group -> active categories.

    Back-compat: accepts the legacy section/subsection/label/value header.
    """
    result: dict[str, dict] = {}
    for row in _taxonomy_rows(root, include_deleted=include_deleted):
        if not include_deleted and row.get("status") == "deleted":
            continue
        tt = row["tracking_type"]
        grp = row["group"]
        result.setdefault(tt, {"label": tt, "groups": {}})
        result[tt]["groups"].setdefault(grp, {"label": grp, "categories": []})
        result[tt]["groups"][grp]["categories"].append({
            "id": row["category_id"],
            "label": row["label"],
            "notes": row.get("notes", ""),
            "origin": row.get("origin", "custom"),
            "status": row.get("status", "active"),
        })
    for tdata in result.values():
        for gdata in tdata["groups"].values():
            gdata["categories"].sort(key=lambda c: (c.get("label") or c.get("id") or "").lower())
    return result


def taxonomy_flat(root=None, include_deleted: bool = False):
    """Flat index: category_id -> {id, label, group, tracking_type, origin, status}."""
    flat: dict[str, dict] = {}
    for row in _taxonomy_rows(root, include_deleted=include_deleted):
        if not include_deleted and row.get("status") == "deleted":
            continue
        flat[row["category_id"]] = {
            "id": row["category_id"],
            "label": row["label"],
            "group": row["group"],
            "tracking_type": row["tracking_type"],
            "origin": row.get("origin", "custom"),
            "status": row.get("status", "active"),
            "notes": row.get("notes", ""),
        }
    return flat


def _unique_category_id(root, wanted: str) -> str:
    flat = taxonomy_flat(root, include_deleted=True)
    base = slugify_category(wanted)
    cid = base
    n = 2
    while cid in flat:
        cid = f"{base}_{n}"
        n += 1
    return cid


def save_taxonomy_category(root, tracking_type, group, cat_id, label, notes="", origin="custom", status="active"):
    rows = _taxonomy_rows(root, include_deleted=True)
    if any(r["category_id"] == cat_id for r in rows):
        raise ValueError(f"Category id '{cat_id}' already exists")
    rows.append({
        "tracking_type": _normalize_tracking_type(tracking_type),
        "group": (group or "Other").strip(),
        "category_id": (cat_id or "").strip(),
        "label": (label or cat_id or "").strip(),
        "origin": origin or "custom",
        "status": status or "active",
        "notes": notes or "",
    })
    _write_taxonomy_rows(root, rows)


def update_taxonomy_category(root, cat_id, label=None, notes=None, tracking_type=None, group=None):
    rows = _taxonomy_rows(root, include_deleted=True)
    found = False
    for row in rows:
        if row["category_id"] == cat_id:
            found = True
            if label is not None and str(label).strip():
                row["label"] = str(label).strip()
            if notes is not None:
                row["notes"] = str(notes or "").strip()
            if tracking_type is not None and str(tracking_type).strip():
                row["tracking_type"] = _normalize_tracking_type(tracking_type)
            if group is not None and str(group).strip():
                row["group"] = str(group).strip()
            break
    if found:
        _write_taxonomy_rows(root, rows)
    return found


def delete_taxonomy_category(root, cat_id):
    """Soft-delete a category row. Deleted template categories are restorable."""
    rows = _taxonomy_rows(root, include_deleted=True)
    found = False
    for row in rows:
        if row["category_id"] == cat_id:
            row["status"] = "deleted"
            found = True
            break
    if found:
        _write_taxonomy_rows(root, rows)
    return found


def delete_taxonomy_group(root, tracking_type: str, group: str) -> bool:
    """Delete an empty taxonomy group. Groups are implicit, so active categories block deletion."""
    tt = _normalize_tracking_type(tracking_type)
    grp = (group or "").strip()
    if not grp:
        return False
    rows = _taxonomy_rows(root, include_deleted=True)
    normalized = []
    active_count = 0
    removable_count = 0
    for row in rows:
        row_tt, row_grp = _normalize_spending_group_assignment(row.get("tracking_type"), row.get("group"), row.get("category_id"), row.get("label"))
        same_group = row_tt == tt and row_grp == grp
        if same_group and row.get("status") != "deleted":
            active_count += 1
        if same_group and row.get("status") == "deleted":
            removable_count += 1
            continue
        normalized.append(row)
    if active_count:
        raise ValueError("Group must have no active categories before it can be deleted")
    if removable_count:
        _write_taxonomy_rows(root, normalized)
    return True


def restore_taxonomy_category(root, cat_id):
    rows = _taxonomy_rows(root, include_deleted=True)
    found = False
    for row in rows:
        if row["category_id"] == cat_id:
            row["status"] = "active"
            found = True
            break
    if found:
        _write_taxonomy_rows(root, rows)
        budget = load_unified_budget(root)
        if not any(b.get("kind") == "category" and b.get("key") == cat_id for b in budget):
            budget.append({"kind": "category", "key": cat_id, "label": taxonomy_flat(root, True).get(cat_id, {}).get("label", cat_id), "annual_budget": 0, "start_year": "", "end_year": "", "one_time_year": "", "notes": "Restored at $0"})
            save_unified_budget(root, budget)
    return found


def restore_template_categories(root):
    """Restore every soft-deleted template category and ensure it has a $0 budget row."""
    rows = _taxonomy_rows(root, include_deleted=True)
    restored = []
    for row in rows:
        if row.get("origin") == "template" and row.get("status") == "deleted":
            row["status"] = "active"
            restored.append(row["category_id"])
    if restored:
        _write_taxonomy_rows(root, rows)
        budget = load_unified_budget(root)
        existing = {b.get("key") for b in budget if b.get("kind") == "category"}
        flat_all = taxonomy_flat(root, include_deleted=True)
        for cid in restored:
            if cid not in existing:
                budget.append({"kind": "category", "key": cid, "label": flat_all.get(cid, {}).get("label", cid), "annual_budget": 0, "start_year": "", "end_year": "", "one_time_year": "", "notes": "Restored template category at $0"})
        save_unified_budget(root, budget)
    return restored


def restore_template_group(root, tracking_type: str, group: str):
    """Restore soft-deleted template categories for one Tracking Type/Group at $0."""
    tt = _normalize_tracking_type(tracking_type)
    grp = str(group or "").strip()
    rows = _taxonomy_rows(root, include_deleted=True)
    restored = []
    for row in rows:
        if (row.get("origin") == "template" and row.get("status") == "deleted"
                and row.get("tracking_type") == tt and row.get("group") == grp):
            row["status"] = "active"
            restored.append(row["category_id"])
    if restored:
        _write_taxonomy_rows(root, rows)
        budget = load_unified_budget(root)
        existing = {b.get("key") for b in budget if b.get("kind") == "category"}
        flat_all = taxonomy_flat(root, include_deleted=True)
        for cid in restored:
            if cid not in existing:
                budget.append({"kind": "category", "key": cid, "label": flat_all.get(cid, {}).get("label", cid), "annual_budget": 0, "start_year": "", "end_year": "", "one_time_year": "", "notes": "Loaded template category at $0"})
        save_unified_budget(root, budget)
    return restored


def hide_unused_template_categories(root):
    """Soft-delete unused template rows so a new budget starts from transaction/custom categories.

    Template rows stay active when they already have aliases, category/group/line budget
    dollars, or detail lines. They can later be loaded by group.
    """
    rows = _taxonomy_rows(root, include_deleted=True)
    aliases = load_aliases(root)
    alias_ids = {a.get("category_id") for a in aliases if a.get("category_id")}
    budget_rows = load_unified_budget(root)
    budget_ids = {b.get("key") for b in budget_rows if b.get("kind") in {"category", "line"} and (_safe_float(str(b.get("annual_budget", 0))) != 0 or b.get("kind") == "line")}
    changed = []
    for row in rows:
        cid = row.get("category_id")
        if row.get("origin") == "template" and row.get("status") == "active" and cid not in alias_ids and cid not in budget_ids:
            row["status"] = "deleted"
            changed.append(cid)
    if changed:
        _write_taxonomy_rows(root, rows)
    return changed


def load_aliases(root=None):
    """Load unified aliases. Falls back to legacy mapping rules if migration has not run."""
    r = _root(root)
    path = r / "input" / "client_spending_aliases.csv"
    header, rows = _read_csv_dicts(path)
    aliases: list[dict] = []
    if rows and {"match_value", "category_id"}.issubset(set(header)):
        for row in rows:
            mv = (row.get("match_value") or "").strip()
            cid = (row.get("category_id") or "").strip()
            if not (mv and cid):
                continue
            aliases.append({
                "match_value": mv,
                "match_field": (row.get("match_field") or "category").strip().lower() or "category",
                "exact": _csv_bool(row.get("exact"), True),
                "priority": _safe_int(row.get("priority"), 50),
                "category_id": cid,
                "source": (row.get("source") or "user").strip().lower() or "user",
            })
    else:
        for rule in load_mapping_rules(root):
            aliases.append({
                "match_value": rule.get("keyword", ""),
                "match_field": rule.get("match_field", "category"),
                "exact": bool(rule.get("exact")),
                "priority": _safe_int(rule.get("priority"), 50),
                "category_id": rule.get("category_id", ""),
                "source": "seed",
            })
    aliases = [a for a in aliases if a.get("match_value") and a.get("category_id")]
    aliases.sort(key=lambda a: (-_safe_int(a.get("priority"), 50), str(a.get("match_value", "")).lower(), str(a.get("category_id", ""))))
    return aliases


def save_aliases(root, aliases: list[dict]) -> None:
    rows = []
    seen = set()
    for a in aliases or []:
        mv = str(a.get("match_value") or a.get("keyword") or "").strip()
        cid = str(a.get("category_id") or "").strip()
        if not (mv and cid):
            continue
        row = {
            "match_value": mv,
            "match_field": (a.get("match_field") or "category").strip().lower() or "category",
            "exact": "1" if _csv_bool(a.get("exact"), True) else "0",
            "priority": str(_safe_int(a.get("priority"), 50)),
            "category_id": cid,
            "source": (a.get("source") or "user").strip().lower() or "user",
        }
        key = (row["match_value"].lower(), row["match_field"], row["exact"], row["category_id"])
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)
    rows.sort(key=lambda r: (-_safe_int(r["priority"], 50), r["match_value"].lower(), r["category_id"]))
    _write_csv_dicts(_root(root) / "input" / "client_spending_aliases.csv", _ALIAS_HEADER, rows)


def add_alias(root, match_value, category_id, match_field="category", exact=True, priority=90, source="user"):
    flat = taxonomy_flat(root)
    if category_id not in flat:
        raise ValueError(f"Unknown category_id '{category_id}'")
    aliases = load_aliases(root)
    aliases = [a for a in aliases if not (str(a.get("match_value", "")).lower() == str(match_value).strip().lower() and str(a.get("match_field", "category")).lower() == str(match_field).lower())]
    aliases.append({"match_value": match_value, "match_field": match_field, "exact": exact, "priority": priority, "category_id": category_id, "source": source})
    save_aliases(root, aliases)


def _resolve_alias(txn: dict, aliases: list[dict], flat: dict) -> str:
    confirmed = (txn.get("mapped_category_id") or "").strip()
    if confirmed.startswith("confirmed:"):
        cid = confirmed.replace("confirmed:", "", 1)
        if cid in flat:
            return cid
    merchant = (txn.get("merchant") or "").lower()
    category = (txn.get("category") or "").lower()
    for alias in aliases:
        cid = alias.get("category_id") or ""
        if cid not in flat:
            continue
        field = (alias.get("match_field") or "category").lower()
        target = merchant if field == "merchant" else category
        needle = str(alias.get("match_value") or "").lower()
        if not needle:
            continue
        if alias.get("exact"):
            if target == needle:
                return cid
        elif needle in target:
            return cid
    return ""


def apply_mapping_rules(txns, rules=None, flat=None):
    """Compatibility wrapper: annotate transactions using unified aliases."""
    aliases = rules if rules is not None else []
    # Accept both legacy rule shape and unified alias shape.
    normalized = []
    for rule in aliases or []:
        normalized.append({
            "match_value": rule.get("match_value") or rule.get("keyword") or "",
            "match_field": rule.get("match_field") or "category",
            "exact": bool(rule.get("exact")),
            "priority": _safe_int(rule.get("priority"), 50),
            "category_id": rule.get("category_id") or "",
            "source": rule.get("source") or "seed",
        })
    normalized.sort(key=lambda a: (-_safe_int(a.get("priority"), 50), str(a.get("match_value", "")).lower()))
    flat = flat or {}
    for txn in txns:
        existing = txn.get("mapped_category_id", "")
        if existing and str(existing).startswith("confirmed:"):
            continue
        cid = _resolve_alias(txn, normalized, flat) if normalized else ""
        txn["mapped_category_id"] = ("auto:" + cid) if cid else (existing or "")
    return txns


def load_mapping_rules(root=None):
    """Compatibility: expose aliases with legacy keyword keys."""
    return [{
        "keyword": a.get("match_value", ""),
        "match_value": a.get("match_value", ""),
        "category_id": a.get("category_id", ""),
        "match_field": a.get("match_field", "category"),
        "exact": bool(a.get("exact")),
        "priority": _safe_int(a.get("priority"), 50),
        "source": a.get("source", "user"),
    } for a in load_aliases(root)]


def save_mapping_rules(root, rules):
    """Compatibility: save rules into client_spending_aliases.csv."""
    save_aliases(root, [{
        "match_value": r.get("match_value") or r.get("keyword") or "",
        "category_id": r.get("category_id") or "",
        "match_field": r.get("match_field") or "category",
        "exact": r.get("exact", True),
        "priority": r.get("priority", 50),
        "source": r.get("source") or "user",
    } for r in rules or []])


def _legacy_budget_to_unified(root=None) -> list[dict]:
    path = _root(root) / "input" / "client_spending_budget.csv"
    header, rows = _read_csv_dicts(path)
    out: list[dict] = []
    if not rows:
        return out
    if {"kind", "key"}.issubset(set(header)):
        for row in rows:
            kind = (row.get("kind") or "category").strip().lower()
            key = (row.get("key") or "").strip()
            if not (kind and key):
                continue
            out.append({
                "kind": kind,
                "key": key,
                "label": (row.get("label") or "").strip(),
                "annual_budget": _safe_float(row.get("annual_budget", "")),
                "start_year": (row.get("start_year") or "").strip(),
                "end_year": (row.get("end_year") or "").strip(),
                "one_time_year": (row.get("one_time_year") or "").strip(),
                "notes": (row.get("notes") or "").strip(),
                "line_section": (row.get("line_section") or "").strip(),
                "line_mode": (row.get("line_mode") or "").strip(),
            })
    else:
        for row in rows:
            cid = (row.get("category_id") or "").strip()
            if not cid:
                continue
            if cid.startswith("grp::"):
                parts = cid.split("::", 2)
                key = f"{parts[1]}::{parts[2]}" if len(parts) == 3 else cid.replace("grp::", "", 1)
                kind = "group"
            else:
                key = cid
                kind = "category"
            out.append({"kind": kind, "key": key, "label": "", "annual_budget": _safe_float(row.get("annual_budget", "")), "start_year": "", "end_year": "", "one_time_year": "", "notes": (row.get("notes") or "").strip()})
    # Fold legacy detail lines if they are still present and not already unified.
    if not {"kind", "key"}.issubset(set(header)):
        line_path = _root(root) / "input" / "client_spending_budget_lines.csv"
        _, line_rows = _read_csv_dicts(line_path)
        for line in line_rows:
            cid = (line.get("category_id") or "").strip()
            if not cid:
                continue
            out.append({
                "kind": "line",
                "key": cid,
                "label": (line.get("label") or line.get("line_id") or cid).strip(),
                "annual_budget": _safe_float(line.get("amount_per_year", "")),
                "start_year": (line.get("start_year") or "").strip(),
                "end_year": (line.get("end_year") or "").strip(),
                "one_time_year": (line.get("one_time_year") or "").strip(),
                "notes": (line.get("notes") or "").strip(),
                "line_section": (line.get("section") or "").strip(),
                "line_mode": (line.get("mode") or "").strip(),
            })
    return out


def _budget_recovery_seed_path(root=None) -> Path:
    return _root(root) / "input" / "client_spending_budget.recovery_seed.csv"


def _budget_row_total(rows: list[dict], kinds: set[str] | None = None) -> float:
    if kinds is None:
        kinds = {"category", "group", "line"}
    total = 0.0
    for row in rows or []:
        if (row.get("kind") or "category").strip().lower() in kinds:
            total += abs(_safe_float(str(row.get("annual_budget", ""))))
    return total


def _merge_budget_seed(current: list[dict], seed: list[dict], *, only_when_zero: bool = True) -> tuple[list[dict], int]:
    """Merge nonzero seed rows into a possibly zeroed budget file.

    This is intentionally conservative: existing nonzero rows win, seed values
    fill only missing/zero category/group rows, and line rows are added only when
    the current line key has no nonzero current line. It is used to recover from
    UI/autosave regressions that replaced the budget object with zeros.
    """
    merged = [dict(r) for r in (current or [])]
    idx: dict[tuple[str, str], dict] = {}
    for row in merged:
        kind = (row.get("kind") or "category").strip().lower()
        key = (row.get("key") or row.get("category_id") or "").strip()
        if key:
            idx[(kind, key)] = row

    changed = 0
    for row in seed or []:
        kind = (row.get("kind") or "category").strip().lower()
        key = (row.get("key") or row.get("category_id") or "").strip()
        seed_amt = _safe_float(str(row.get("annual_budget", "")))
        if not key or kind not in {"category", "group", "line"} or seed_amt == 0:
            continue
        cur = idx.get((kind, key))
        cur_amt = _safe_float(str((cur or {}).get("annual_budget", "")))
        if cur is None:
            merged.append(dict(row))
            idx[(kind, key)] = merged[-1]
            changed += 1
        elif (not only_when_zero) or cur_amt == 0:
            cur.update(dict(row))
            changed += 1
    return merged, changed


def recover_spending_budget_from_seed(root=None, *, persist: bool = True, force: bool = False) -> dict:
    """Recover nonzero spending budget rows from a packaged recovery seed.

    Returns a small status dict for UI/API callers. Force=False only fills
    missing/zero rows; it never overwrites a current nonzero budget.
    """
    r = _root(root)
    seed_path = _budget_recovery_seed_path(r)
    if not seed_path.exists():
        return {"success": False, "recovered": 0, "error": "No recovery seed file is available."}
    current = _legacy_budget_to_unified(r)
    seed_header, seed_rows_raw = _read_csv_dicts(seed_path)
    seed: list[dict] = []
    if {"kind", "key"}.issubset(set(seed_header)):
        for row in seed_rows_raw:
            kind = (row.get("kind") or "category").strip().lower()
            key = (row.get("key") or "").strip()
            if kind and key:
                seed.append({
                    "kind": kind,
                    "key": key,
                    "label": (row.get("label") or "").strip(),
                    "annual_budget": _safe_float(str(row.get("annual_budget", ""))),
                    "start_year": (row.get("start_year") or "").strip(),
                    "end_year": (row.get("end_year") or "").strip(),
                    "one_time_year": (row.get("one_time_year") or "").strip(),
                    "notes": (row.get("notes") or "").strip(),
                })
    if not seed or _budget_row_total(seed) == 0:
        return {"success": False, "recovered": 0, "error": "Recovery seed has no nonzero budget values."}
    merged, changed = _merge_budget_seed(current, seed, only_when_zero=not force)
    if changed and persist:
        try:
            budget_path = r / "input" / "client_spending_budget.csv"
            if budget_path.exists():
                backup_path = budget_path.with_suffix(budget_path.suffix + ".pre_recovery_backup")
                if not backup_path.exists():
                    backup_path.write_text(budget_path.read_text(encoding="utf-8-sig", errors="replace"), encoding="utf-8")
        except Exception:
            pass
        save_unified_budget(r, merged)
    return {
        "success": True,
        "recovered": changed,
        "current_total_before": round(_budget_row_total(current), 2),
        "seed_total": round(_budget_row_total(seed), 2),
        "current_total_after": round(_budget_row_total(merged), 2),
    }


def load_unified_budget(root=None) -> list[dict]:
    rows = _legacy_budget_to_unified(root)
    # Automatic safety net: if the editable category/group budget has been
    # zeroed but a packaged seed exists, restore the prior nonzero values. This
    # protects local data after an autosave regression without overwriting any
    # current nonzero user edits.
    if _budget_row_total(rows, {"category", "group"}) == 0 and _budget_recovery_seed_path(root).exists():
        status = recover_spending_budget_from_seed(root, persist=True, force=False)
        if status.get("success") and status.get("recovered"):
            rows = _legacy_budget_to_unified(root)
    return rows


def save_unified_budget(root, rows: list[dict]) -> None:
    out = []
    for row in rows or []:
        kind = (row.get("kind") or "category").strip().lower()
        key = (row.get("key") or row.get("category_id") or "").strip()
        if not (kind and key):
            continue
        if kind not in {"category", "group", "line"}:
            continue
        out.append({
            "kind": kind,
            "key": key,
            "label": (row.get("label") or "").strip(),
            "annual_budget": "%d" % int(round(_safe_float(str(row.get("annual_budget", ""))))) if _safe_float(str(row.get("annual_budget", ""))) else "",
            "start_year": (str(row.get("start_year") or "").strip()),
            "end_year": (str(row.get("end_year") or "").strip()),
            "one_time_year": (str(row.get("one_time_year") or "").strip()),
            "notes": (row.get("notes") or "").strip(),
            "line_section": (str(row.get("line_section") or "").strip()) if kind == "line" else "",
            "line_mode": (str(row.get("line_mode") or "").strip()) if kind == "line" else "",
        })
    _write_csv_dicts(_root(root) / "input" / "client_spending_budget.csv", _BUDGET_HEADER, out)


def load_budget_by_category(root=None):
    """Compatibility wrapper over unified budget rows.

    Category rows are keyed by category_id. Group rows use legacy key
    grp::<tracking_type>::<group> so existing UI code can continue to read them.
    Line rows are intentionally not included here; load_unified_budget owns them.
    """
    result: dict[str, dict] = {}
    for row in load_unified_budget(root):
        kind = row.get("kind")
        if kind == "category":
            key = row.get("key")
        elif kind == "group":
            key = "grp::" + row.get("key", "")
        else:
            continue
        result[key] = {"annual_budget": _safe_float(str(row.get("annual_budget", ""))), "notes": row.get("notes", "")}
    return result


def save_budget_by_category(root, budget):
    flat = taxonomy_flat(root, include_deleted=True)
    existing_rows = load_unified_budget(root)
    existing_lines = [r for r in existing_rows if r.get("kind") == "line"]
    rows: list[dict] = []
    for key, b in (budget or {}).items():
        if not key:
            continue
        if isinstance(b, dict) and b.get("_delete"):
            # Explicit delete marker from the UI. Absence/zero caused by a stale
            # client save is not treated as deletion.
            continue
        if str(key).startswith("grp::"):
            kind = "group"
            out_key = str(key).replace("grp::", "", 1)
            label = out_key.split("::", 1)[-1]
        else:
            kind = "category"
            out_key = str(key)
            label = flat.get(out_key, {}).get("label", out_key)
        rows.append({"kind": kind, "key": out_key, "label": label, "annual_budget": _safe_float(str((b or {}).get("annual_budget", ""))), "start_year": "", "end_year": "", "one_time_year": "", "notes": (b or {}).get("notes", "")})
    rows.extend(existing_lines)

    # Guard against the regression where the browser submitted an all-zero
    # budget cache and overwrote a nonzero budget file. Legitimate targeted zero
    # edits still save because this only trips when the whole category/group
    # payload is zero while existing data is materially nonzero.
    incoming_total = _budget_row_total(rows, {"category", "group"})
    existing_total = _budget_row_total(existing_rows, {"category", "group"})
    if incoming_total == 0 and existing_total > 0 and len(rows) >= 3:
        rows = existing_rows
    save_unified_budget(root, rows)


def _budget_indexes(root=None):
    categories: dict[str, dict] = {}
    groups: dict[str, dict] = {}
    lines_by_category: dict[str, list[dict]] = {}
    for row in load_unified_budget(root):
        if row.get("kind") == "category":
            categories[row.get("key", "")] = row
        elif row.get("kind") == "group":
            groups[row.get("key", "")] = row
        elif row.get("kind") == "line":
            lines_by_category.setdefault(row.get("key", ""), []).append(row)
    return categories, groups, lines_by_category


def _line_amount_for_year(line: dict, year: int | None) -> float:
    amt = _safe_float(str(line.get("annual_budget", "")))
    if amt == 0:
        return 0.0
    one = _safe_int(line.get("one_time_year"), 0)
    if one:
        return amt if (year is None or year == one) else 0.0
    start = _safe_int(line.get("start_year"), 0)
    end = _safe_int(line.get("end_year"), 0)
    if year is None:
        return amt
    if start and year < start:
        return 0.0
    if end and year > end:
        return 0.0
    return amt


def _category_budget_for_year(cid: str, year: int | None, cat_budgets: dict, line_budgets: dict) -> float:
    lines = line_budgets.get(cid) or []
    if lines:
        return sum(_line_amount_for_year(line, year) for line in lines)
    return _safe_float(str((cat_budgets.get(cid) or {}).get("annual_budget", 0)))




def _is_medical_cap_reference(category_id: str, info: dict | None = None) -> bool:
    """True when a row is a healthcare cap/reference, not an expense budget."""
    cid = str(category_id or "").strip().lower()
    label = str((info or {}).get("label") or "").strip().lower()
    group = str((info or {}).get("group") or "").strip().lower()
    return cid in {"annual_oop_max", "annual_oop_estimate_today"} or "oop cap" in label or "out-of-pocket max" in label or group == "medical cap reference"

def _is_tax_actual(info: dict, category_id: str = "", raw_category: str = "") -> bool:
    """True for tax actuals that should stay out of Spending Analysis."""
    tt = str((info or {}).get("tracking_type") or "")
    text = " ".join([
        str(category_id or ""),
        str(raw_category or ""),
        str((info or {}).get("label") or ""),
        str((info or {}).get("group") or ""),
    ]).lower()
    if "taxi" in text:
        return False
    if tt in _TRANSFER_NAMES and "tax" in text:
        return True
    return any(tok in text for tok in ["income_tax", "income taxes", "property tax escrow", "estimated tax"])


def _actuals_by_taxonomy(root, year: int):
    flat = taxonomy_flat(root)
    aliases = load_aliases(root)
    txns = load_transactions_extended(root, year)
    today = date.today()
    jan1 = date(year, 1, 1)
    days_elapsed = max(1, (min(today, date(year, 12, 31)) - jan1).days + 1)
    annual_factor = 365.0 / days_elapsed
    actuals: dict[str, dict] = {}
    alias_hits: dict[str, set[str]] = {}
    unmatched: dict[str, dict] = {}
    for txn in txns:
        amount = txn.get("amount", 0)
        if amount == 0:
            continue
        cid = _resolve_alias(txn, aliases, flat)
        raw_cat = txn.get("category") or ""
        if cid and cid in flat:
            info = flat[cid]
            tt = info.get("tracking_type")
            # Spending Analysis is comprehensive for Income and expenses, but
            # still ignores transfers and tax payments. Income is positive;
            # expenses are shown as positive outflows.
            if tt in _TRANSFER_NAMES or _is_tax_actual(info, cid, raw_cat):
                continue
            if tt == "Income":
                display_amount = amount if amount > 0 else -abs(amount)
            else:
                if amount > 0:
                    # Refunds/credits against an expense category reduce outflow.
                    display_amount = -abs(amount)
                else:
                    display_amount = abs(amount)
            actuals.setdefault(cid, {"actual": 0.0, "count": 0})
            actuals[cid]["actual"] += display_amount
            actuals[cid]["count"] += 1
            if raw_cat:
                alias_hits.setdefault(cid, set()).add(raw_cat)
        else:
            if raw_cat and amount < 0:
                entry = unmatched.setdefault(raw_cat, {"category": raw_cat, "actual": 0.0, "count": 0})
                entry["actual"] += abs(amount)
                entry["count"] += 1
    return actuals, alias_hits, list(unmatched.values()), days_elapsed, annual_factor



def _source_page_for_tracking_type(tracking_type: str | None) -> str:
    tt = (tracking_type or '').strip()
    if tt == 'Housing':
        return 'Housing'
    if tt == 'Wellness':
        return 'Wellness'
    if tt == 'Travel':
        return 'Travel'
    if tt == 'Large Discretionary':
        return 'Large Discretionary'
    return 'Spending Categories'


def _nonzero_amount(value) -> bool:
    try:
        return abs(float(value or 0)) > 0.004
    except Exception:
        return False

def spending_summary_taxonomy(root=None, year=None):
    """Unified model: Tracking Type -> Group -> Category with actuals, budget, aliases and deleted tray."""
    r = _root(root)
    if year is None:
        year = date.today().year
    flat = taxonomy_flat(r)
    all_flat = taxonomy_flat(r, include_deleted=True)
    aliases = load_aliases(r)
    aliases_by_category: dict[str, set[str]] = {}
    for alias in aliases:
        cid = alias.get("category_id")
        match_value = alias.get("match_value")
        if cid and match_value:
            aliases_by_category.setdefault(cid, set()).add(match_value)
    cat_budgets, group_budgets, line_budgets = _budget_indexes(r)
    actuals, alias_hits, unmatched, days_elapsed, annual_factor = _actuals_by_taxonomy(r, year)

    by_tt_group: dict[str, dict[str, list[dict]]] = {}
    for cid, info in flat.items():
        tt = info["tracking_type"]
        if tt in _TRANSFER_NAMES:
            continue
        by_tt_group.setdefault(tt, {}).setdefault(info["group"], []).append(info)

    template_available_by_group: dict[str, int] = {}
    for cid, info in all_flat.items():
        if info.get("origin") == "template" and info.get("status") == "deleted":
            gkey = f"{info.get('tracking_type')}::{info.get('group')}"
            template_available_by_group[gkey] = template_available_by_group.get(gkey, 0) + 1

    # Include aliased categories that are not active taxonomy rows as unmatched rather than duplicating them.
    for u in unmatched:
        u["actual"] = round(u.get("actual", 0.0), 2)
        u["annualized"] = round(u.get("actual", 0.0) * annual_factor, 2)

    output_types = []
    grand_actual = grand_budget = 0.0
    core_budget_base = 0.0
    order = TRACKING_TYPE_ORDER + [tt for tt in sorted(by_tt_group) if tt not in TRACKING_TYPE_ORDER]
    for tt in order:
        groups = by_tt_group.get(tt, {})
        type_actual = type_budget = 0.0
        out_groups = []
        for grp in sorted(groups):
            gkey = f"{tt}::{grp}"
            group_row = group_budgets.get(gkey)
            group_mode = "group" if group_row is not None else "category"
            ga = 0.0
            category_sum = 0.0
            out_cats = []
            for info in sorted(groups[grp], key=lambda x: (x.get("label", x["id"]).lower(), x["id"])):
                cid = info["id"]
                ca = float((actuals.get(cid) or {}).get("actual", 0.0))
                is_cap_reference = _is_medical_cap_reference(cid, info)
                cb = 0.0 if (group_mode == "group" or is_cap_reference) else _category_budget_for_year(cid, year, cat_budgets, line_budgets)
                has_line_budget = bool(line_budgets.get(cid) or []) and not is_cap_reference
                projection_seed = 0.0 if is_cap_reference else cb
                if is_cap_reference:
                    ca = 0.0
                # Do not hide any row that has transaction activity, an annual budget,
                # detail/line budget rows, or a projection seed.  Ordinary zero-value
                # template rows remain hidden until explicitly loaded/used.
                if not (_nonzero_amount(ca) or _nonzero_amount(cb) or has_line_budget or _nonzero_amount(projection_seed)):
                    continue
                ann = ca * annual_factor
                category_sum += cb
                ga += ca
                aliases_for_cat = sorted(alias_hits.get(cid, set()) | aliases_by_category.get(cid, set()))
                can_delete = (round(ca, 2) == 0 and round(cb, 2) == 0 and not (line_budgets.get(cid) or []))
                out_cats.append({
                    "id": cid,
                    "label": info.get("label", cid),
                    "actual": round(ca, 2),  # compatibility alias for ytd_actual
                    "ytd_actual": round(ca, 2),
                    "annualized": round(ann, 2),  # compatibility alias for annualized_actual
                    "annualized_actual": round(ann, 2),
                    "budget": round(cb, 2),  # compatibility alias for annual_budget
                    "annual_budget": round(cb, 2),
                    "projection_seed": round(projection_seed, 2),
                    "source_page": _source_page_for_tracking_type(tt),
                    "is_read_only_reference": tt in {"Wellness", "Housing", "Travel"} or is_cap_reference,
                    "is_cap_reference": is_cap_reference,
                    "budget_disabled": group_mode == "group" or is_cap_reference,
                    "line_count": len(line_budgets.get(cid) or []),
                    "count": int((actuals.get(cid) or {}).get("count", 0)),
                    "origin": info.get("origin", "custom"),
                    "status": info.get("status", "active"),
                    "notes": info.get("notes", ""),
                    "aliases": aliases_for_cat,
                    "can_delete": can_delete,
                    "delete_disabled_reason": "value must be zero before deleting" if not can_delete else "",
                })
            group_budget = _safe_float(str(group_row.get("annual_budget", 0))) if group_mode == "group" else category_sum
            group_projection_seed = group_budget
            if not out_cats and not (_nonzero_amount(ga) or _nonzero_amount(group_budget) or _nonzero_amount(group_projection_seed)):
                continue
            out_groups.append({
                "group": grp,
                "actual": round(ga, 2),  # compatibility alias for ytd_actual
                "ytd_actual": round(ga, 2),
                "annualized": round(ga * annual_factor, 2),  # compatibility alias for annualized_actual
                "annualized_actual": round(ga * annual_factor, 2),
                "budget": round(group_budget, 2),  # compatibility alias for annual_budget
                "annual_budget": round(group_budget, 2),
                "projection_seed": round(group_projection_seed, 2),
                "source_page": _source_page_for_tracking_type(tt),
                "is_read_only_reference": tt in {"Wellness", "Housing", "Travel"},
                "budget_mode": group_mode,
                "template_available_count": template_available_by_group.get(gkey, 0),
                "can_delete_group": False,
                "categories": out_cats,
            })
            type_actual += ga
            type_budget += group_budget
        if out_groups:
            output_types.append({
                "tracking_type": tt,
                "actual": round(type_actual, 2),  # compatibility alias for ytd_actual
                "ytd_actual": round(type_actual, 2),
                "annualized": round(type_actual * annual_factor, 2),  # compatibility alias for annualized_actual
                "annualized_actual": round(type_actual * annual_factor, 2),
                "budget": round(type_budget, 2),  # compatibility alias for annual_budget
                "annual_budget": round(type_budget, 2),
                "projection_seed": round(type_budget, 2),
                "source_page": _source_page_for_tracking_type(tt),
                "is_read_only_reference": tt in {"Wellness", "Housing", "Travel"},
                "groups": out_groups,
                "read_only_budget": tt in {"Wellness", "Housing"},
            })
        if tt != "Income" and tt not in _TRANSFER_NAMES:
            grand_actual += type_actual
            grand_budget += type_budget
        if tt not in _EXCLUDED_TRACKING_TYPES_FOR_SPEND_BASE:
            # The implementation decision excludes time-bounded Large-Disc/Travel line rows from spend_base;
            # those rows feed extras through the resolver instead.
            for grp_out in out_groups:
                if tt in {"Travel", "Large Discretionary"}:
                    gkey = f"{tt}::{grp_out['group']}"
                    if group_budgets.get(gkey):
                        core_budget_base += grp_out.get("budget", 0.0)
                    else:
                        for cat in grp_out.get("categories", []):
                            if not line_budgets.get(cat.get("id")):
                                core_budget_base += cat.get("budget", 0.0)
                else:
                    core_budget_base += grp_out.get("budget", 0.0)

    deleted_tray = []
    for cid, info in all_flat.items():
        if info.get("status") == "deleted":
            deleted_tray.append({"id": cid, "label": info.get("label", cid), "tracking_type": info.get("tracking_type"), "group": info.get("group"), "origin": info.get("origin", "custom"), "notes": info.get("notes", "")})

    return {
        "success": True,
        "year": year,
        "days_elapsed": days_elapsed,
        "annualization_factor": round(annual_factor, 4),
        "tracking_types": output_types,
        "grand_actual": round(grand_actual, 2),  # compatibility alias for expense_ytd_actual
        "grand_ytd_actual": round(grand_actual, 2),
        "grand_annualized": round(grand_actual * annual_factor, 2),
        "grand_annualized_actual": round(grand_actual * annual_factor, 2),
        "grand_budget": round(grand_budget, 2),
        "grand_annual_budget": round(grand_budget, 2),
        "grand_projection_seed": round(grand_budget, 2),
        "budget_derived_core_spend_base": round(core_budget_base, 2),
        "income_actual": round(sum(t.get("actual", 0.0) for t in output_types if t.get("tracking_type") == "Income"), 2),
        "income_annualized": round(sum(t.get("annualized", 0.0) for t in output_types if t.get("tracking_type") == "Income"), 2),
        "expense_actual": round(sum(t.get("actual", 0.0) for t in output_types if t.get("tracking_type") != "Income"), 2),
        "expense_annualized": round(sum(t.get("annualized", 0.0) for t in output_types if t.get("tracking_type") != "Income"), 2),
        "unmatched_categories": sorted(unmatched, key=lambda x: -x.get("actual", 0.0)),
        "deleted_tray": sorted(deleted_tray, key=lambda x: (x.get("tracking_type") or "", x.get("group") or "", x.get("label") or "")),
        "aliases": aliases,
    }


def spending_model(root=None, year=None):
    """API-ready merged model payload."""
    summary = spending_summary_taxonomy(root, year)
    return {
        "success": True,
        "model_version": "unified_spending_taxonomy_budget_cashflow_v1",
        "year": summary.get("year"),
        "tracking_types": summary.get("tracking_types", []),
        "deleted_tray": summary.get("deleted_tray", []),
        "unmatched_transaction_categories": summary.get("unmatched_categories", []),
        "aliases": summary.get("aliases", []),
        "totals": {
            "actual": summary.get("grand_actual", 0.0),
            "ytd_actual": summary.get("grand_ytd_actual", summary.get("grand_actual", 0.0)),
            "annualized": summary.get("grand_annualized", 0.0),
            "annualized_actual": summary.get("grand_annualized_actual", summary.get("grand_annualized", 0.0)),
            "budget": summary.get("grand_budget", 0.0),
            "annual_budget": summary.get("grand_annual_budget", summary.get("grand_budget", 0.0)),
            "projection_seed": summary.get("grand_projection_seed", summary.get("grand_budget", 0.0)),
            "budget_derived_core_spend_base": summary.get("budget_derived_core_spend_base", 0.0),
            "income_actual": summary.get("income_actual", 0.0),
            "income_annualized": summary.get("income_annualized", 0.0),
            "expense_actual": summary.get("expense_actual", 0.0),
            "expense_annualized": summary.get("expense_annualized", 0.0),
        },
        "decisions": {
            "spend_base_includes": "Projection spend base excludes Income, Transfer, Business, Housing, Wellness, and time-bounded Large-Disc/Travel line rows; Monthly Trajectory separately includes all non-tax spending actuals.",
            "business": "included_in_model_not_spend_base",
            "income": "out_of_spending_model_for_now",
            "group_mode": "group_budget_disables_category_and_line_detail",
        },
    }


def monthly_series(root: Path | None = None, year: int | None = None, total_budget: float = 0) -> list[dict]:
    """Monthly all-spending actual vs budget, excluding taxes and transfers.

    This table is a cash-flow trajectory, not the core-spend-base resolver.
    Therefore it includes Housing, Wellness/healthcare, Travel, Large
    Discretionary, and Business outflows when they appear in transactions.
    Income, transfers, and tax payments stay excluded.
    """
    r = _root(root)
    if year is None:
        year = date.today().year
    flat = taxonomy_flat(r)
    aliases = load_aliases(r)
    txns = load_transactions_extended(r, year)
    monthly_spend = [0.0] * 12
    for txn in txns:
        amount = float(txn.get("amount", 0) or 0)
        if amount >= 0:
            continue
        raw_cat = txn.get("category") or ""
        cid = _resolve_alias(txn, aliases, flat)
        info = flat.get(cid, {}) if cid else {}
        tt = info.get("tracking_type")
        if tt == "Income" or tt in _TRANSFER_NAMES or _is_tax_actual(info, cid or "", raw_cat) or _is_medical_cap_reference(cid or "", info):
            continue
        monthly_spend[txn["date"].month - 1] += abs(amount)
    monthly_budget = total_budget / 12 if total_budget > 0 else 0
    labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    series = []
    cum_actual = cum_budget = 0.0
    today = date.today()
    for i in range(12):
        if date(year, i + 1, 1) > today and i > 0:
            break
        cum_actual += monthly_spend[i]
        cum_budget += monthly_budget
        series.append({"month": i + 1, "label": labels[i], "actual": round(monthly_spend[i], 2), "cumulative_actual": round(cum_actual, 2), "budget": round(monthly_budget, 2), "cumulative_budget": round(cum_budget, 2)})
    return series


def spending_dashboard(root: Path | None = None, year: int | None = None, core_spending: float = 0) -> dict:
    """Dashboard payload backed by the unified taxonomy summary."""
    r = _root(root)
    if year is None:
        year = date.today().year
    summary = spending_summary_taxonomy(r, year)
    groups = []
    business = None
    for tt in summary.get("tracking_types", []):
        if tt.get("tracking_type") == "Business":
            business = {"actual": tt.get("actual", 0), "annualized": tt.get("annualized", 0), "categories": [c for g in tt.get("groups", []) for c in g.get("categories", [])]}
        if tt.get("tracking_type") in _TRANSFER_NAMES:
            continue
        for g in tt.get("groups", []):
            budget_amt = g.get("budget", 0.0)
            variance = g.get("annualized", 0.0) - budget_amt if budget_amt else 0.0
            vpct = (variance / budget_amt * 100) if budget_amt else 0.0
            groups.append({
                "group": g.get("group"),
                "tracking_type": tt.get("tracking_type"),
                "actual": g.get("ytd_actual", g.get("actual", 0.0)),
                "ytd_actual": g.get("ytd_actual", g.get("actual", 0.0)),
                "annualized": g.get("annualized_actual", g.get("annualized", 0.0)),
                "annualized_actual": g.get("annualized_actual", g.get("annualized", 0.0)),
                "budget_pct": 0,
                "budget_amount": budget_amt,
                "annual_budget": g.get("annual_budget", budget_amt),
                "projection_seed": g.get("projection_seed", budget_amt),
                "source_page": g.get("source_page") or _source_page_for_tracking_type(tt.get("tracking_type")),
                "variance": round(variance, 2),
                "variance_pct": round(vpct, 1),
                "status": "over_budget" if vpct > 15 else "watch" if vpct > 5 else "on_track",
                "categories": g.get("categories", []),
            })
    groups.sort(key=lambda g: -g.get("variance", 0.0))
    model_spend = summary.get("budget_derived_core_spend_base") or core_spending
    return {
        "success": True,
        "enabled": bool(groups),
        "year": year,
        "days_elapsed": summary.get("days_elapsed", 0),
        "annualization_factor": summary.get("annualization_factor", 0),
        "model_core_spending": round(model_spend, 2),
        "actuals_total": summary.get("expense_actual", summary.get("grand_actual", 0.0)),
        "annualized_total": summary.get("expense_annualized", summary.get("grand_annualized", 0.0)),
        "income_total": summary.get("income_actual", 0.0),
        "income_annualized_total": summary.get("income_annualized", 0.0),
        "budget_total": summary.get("grand_budget", 0.0),
        "annual_budget_total": summary.get("grand_annual_budget", summary.get("grand_budget", 0.0)),
        "projection_seed_total": summary.get("grand_projection_seed", summary.get("grand_budget", 0.0)),
        "forecast_total": summary.get("expense_annualized", summary.get("grand_annualized", 0.0)),
        "variance_from_model": round(summary.get("grand_annualized", 0.0) - model_spend, 2) if model_spend else 0,
        "variance_pct": round((summary.get("grand_annualized", 0.0) - model_spend) / model_spend * 100, 1) if model_spend else 0,
        "groups": groups,
        "business": business,
        "monthly_series": monthly_series(r, year, summary.get("grand_annual_budget", summary.get("grand_budget", model_spend))),
        "model_managed": {},
        "unmapped_categories": [u.get("category") for u in summary.get("unmatched_categories", [])],
        "taxonomy_summary": summary,
    }

# Corrected alias loader placed last so it overrides the initial unified definition
# and can seed from previous-format files without recursive adapter calls.
def load_aliases(root=None):
    """Load unified aliases. Falls back directly to previous-format CSV files before migration."""
    r = _root(root)
    path = r / "input" / "client_spending_aliases.csv"
    header, rows = _read_csv_dicts(path)
    aliases: list[dict] = []
    if rows and {"match_value", "category_id"}.issubset(set(header)):
        source_rows = rows
        for row in source_rows:
            mv = (row.get("match_value") or "").strip()
            cid = (row.get("category_id") or "").strip()
            if not (mv and cid):
                continue
            aliases.append({
                "match_value": mv,
                "match_field": (row.get("match_field") or "category").strip().lower() or "category",
                "exact": _csv_bool(row.get("exact"), True),
                "priority": _safe_int(row.get("priority"), 50),
                "category_id": cid,
                "source": (row.get("source") or "user").strip().lower() or "user",
            })
    else:
        # Previous-format rules: keyword/category_id/match_field/exact/priority
        _, rule_rows = _read_csv_dicts(r / "input" / "client_spending_rules.csv")
        for row in rule_rows:
            mv = (row.get("keyword") or "").strip()
            cid = (row.get("category_id") or "").strip()
            if not (mv and cid):
                continue
            aliases.append({"match_value": mv, "match_field": (row.get("match_field") or "category").strip() or "category", "exact": _csv_bool(row.get("exact"), True), "priority": _safe_int(row.get("priority"), 50), "category_id": cid, "source": "seed"})
        # Previous-format category maps supply exact bank-category aliases when the label can be matched to taxonomy.
        flat = taxonomy_flat(r, include_deleted=True)
        label_to_id = {str(v.get("label", "")).strip().lower(): cid for cid, v in flat.items()}
        label_to_id.update({cid.lower(): cid for cid in flat})
        _, map_rows = _read_csv_dicts(r / "input" / "spending_category_map.csv")
        for row in map_rows:
            raw = (row.get("category") or "").strip()
            if not raw:
                continue
            cid = label_to_id.get(raw.lower()) or label_to_id.get(slugify_category(raw).lower())
            if cid:
                aliases.append({"match_value": raw, "match_field": "category", "exact": True, "priority": 40, "category_id": cid, "source": "seed"})
    aliases = [a for a in aliases if a.get("match_value") and a.get("category_id")]
    dedup = {}
    for a in aliases:
        key = (str(a.get("match_value", "")).lower(), str(a.get("match_field", "category")).lower(), bool(a.get("exact")))
        old = dedup.get(key)
        if old is None or _safe_int(a.get("priority"), 50) > _safe_int(old.get("priority"), 50):
            dedup[key] = a
    aliases = list(dedup.values())
    aliases.sort(key=lambda a: (-_safe_int(a.get("priority"), 50), str(a.get("match_value", "")).lower(), str(a.get("category_id", ""))))
    return aliases


def load_mapping_rules(root=None):
    """Compatibility: expose unified aliases with legacy keyword keys."""
    return [{
        "keyword": a.get("match_value", ""),
        "match_value": a.get("match_value", ""),
        "category_id": a.get("category_id", ""),
        "match_field": a.get("match_field", "category"),
        "exact": bool(a.get("exact")),
        "priority": _safe_int(a.get("priority"), 50),
        "source": a.get("source", "user"),
    } for a in load_aliases(root)]

# Compatibility category-map facade over aliases.  The UI still has a compact
# bank-category table; saving it now writes aliases instead of creating a second
# source of truth for group/tracking.
def load_category_map(root: Path | None = None) -> dict[str, dict]:
    r = _root(root)
    flat = taxonomy_flat(r, include_deleted=False)
    rows: dict[str, dict] = {}
    legacy_tracking = {v: k for k, v in _LEGACY_TRACKING_MAP.items()}
    for alias in load_aliases(r):
        if alias.get("match_field") != "category" or not alias.get("exact"):
            continue
        cid = alias.get("category_id")
        info = flat.get(cid or "")
        if not info:
            continue
        tt = info.get("tracking_type", "Core Expenses")
        tracking = legacy_tracking.get(tt, tt.lower().replace(" ", "_"))
        cat = alias.get("match_value") or ""
        rows[cat.lower()] = {"category": cat, "group": info.get("group", "Other"), "supergroup": "Expenses", "tracking": tracking, "category_id": cid}
    return rows


def save_category_map(root: Path | None, rows: list[dict]) -> None:
    r = _root(root)
    flat = taxonomy_flat(r, include_deleted=False)
    label_index = {str(info.get("label", "")).lower(): cid for cid, info in flat.items()}
    label_index.update({cid.lower(): cid for cid in flat})
    aliases = load_aliases(r)
    # Drop existing exact category aliases for rows being replaced; keep merchant/power rules.
    replacing = {str(row.get("category", "")).strip().lower() for row in rows or [] if str(row.get("category", "")).strip()}
    aliases = [a for a in aliases if not (a.get("match_field") == "category" and a.get("exact") and str(a.get("match_value", "")).lower() in replacing)]
    for row in rows or []:
        raw = str(row.get("category") or "").strip()
        if not raw:
            continue
        group = str(row.get("group") or "Other").strip()
        tracking = _normalize_tracking_type(row.get("tracking") or "core")
        cid = label_index.get(raw.lower()) or label_index.get(slugify_category(raw).lower())
        if not cid:
            cid = _unique_category_id(r, raw)
            save_taxonomy_category(r, tracking, group, cid, raw, "Promoted from category-map UI", origin="transaction")
            flat = taxonomy_flat(r, include_deleted=False)
            label_index = {str(info.get("label", "")).lower(): k for k, info in flat.items()}
            label_index.update({k.lower(): k for k in flat})
        aliases.append({"match_value": raw, "match_field": "category", "exact": True, "priority": 50, "category_id": cid, "source": "user"})
    save_aliases(r, aliases)
