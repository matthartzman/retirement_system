#!/usr/bin/env python3
"""Migrate legacy spending taxonomy/map/rules/budget files to the unified model.

Idempotent: if the taxonomy and budget files already use the new schemas, the
script exits without rewriting unless --dry-run is used for inspection.
"""
from __future__ import annotations

import argparse
import csv
import shutil
from collections import defaultdict
from datetime import datetime
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "input"

TAXONOMY_HEADER = ["tracking_type", "group", "category_id", "label", "origin", "status", "notes"]
ALIAS_HEADER = ["match_value", "match_field", "exact", "priority", "category_id", "source"]
BUDGET_HEADER = ["kind", "key", "label", "annual_budget", "start_year", "end_year", "one_time_year", "notes"]
TRACKING_MAP = {
    "core": "Core Expenses",
    "housing": "Housing",
    "wellness": "Wellness",
    "travel": "Travel",
    "large_disc": "Large Discretionary",
    "business": "Business",
    "income": "Income",
    "transfer": "Transfer",
    "model_managed": "Housing",
}


def slugify(value: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_") or "uncategorized"


def n(value) -> float:
    try:
        return float(str(value or "").replace("$", "").replace(",", "").strip() or 0)
    except Exception:
        return 0.0


def read_csv(path: Path):
    if not path.exists():
        return [], []
    with path.open(newline="", encoding="utf-8-sig", errors="replace") as f:
        reader = csv.DictReader(line.replace("\x00", "") for line in f)
        return list(reader.fieldnames or []), [dict(r) for r in reader]


def write_csv(path: Path, header: list[str], rows: list[dict]):
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in header})


def backup_inputs() -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bdir = INPUT / f"spending_model_migration_backup_{ts}"
    bdir.mkdir(parents=True, exist_ok=False)
    for pat in ("client_spending_*.csv", "spending_*.csv"):
        for src in INPUT.glob(pat):
            if src.is_file():
                shutil.copy2(src, bdir / src.name)
    return bdir


def already_migrated() -> bool:
    h_tax, _ = read_csv(INPUT / "client_spending_taxonomy.csv")
    h_bud, _ = read_csv(INPUT / "client_spending_budget.csv")
    return {"tracking_type", "group", "category_id", "origin", "status"}.issubset(set(h_tax)) and {"kind", "key"}.issubset(set(h_bud))


def normalize_tracking(raw: str) -> str:
    v = str(raw or "").strip()
    return TRACKING_MAP.get(v.lower(), v or "Core Expenses")


def build_taxonomy():
    header, rows = read_csv(INPUT / "client_spending_taxonomy.csv")
    is_new = {"tracking_type", "group", "category_id", "label"}.issubset(set(header))
    prelim = []
    for r in rows:
        if is_new:
            tt, grp, cid, label = normalize_tracking(r.get("tracking_type")), r.get("group", "Other"), r.get("category_id", ""), r.get("label", "")
            origin = (r.get("origin") or "template").strip().lower() or "template"
            status = (r.get("status") or "active").strip().lower() or "active"
            notes = r.get("notes", "")
        else:
            tt, grp, cid, label = normalize_tracking(r.get("section")), r.get("subsection", "Other"), r.get("label", ""), r.get("value", "")
            origin = "transaction" if "auto-added from transactions" in str(r.get("notes", "")).lower() else "template"
            status = "active"
            notes = r.get("notes", "")
        cid = str(cid or "").strip()
        if not cid:
            continue
        prelim.append({"tracking_type": tt, "group": str(grp or "Other").strip(), "category_id": cid, "label": str(label or cid).strip(), "origin": origin, "status": status, "notes": str(notes or "").strip()})

    by_id = {r["category_id"]: r for r in prelim}
    by_label_slug = defaultdict(list)
    for r in prelim:
        by_label_slug[slugify(r["label"])].append(r["category_id"])

    remap: dict[str, str] = {}
    final = []
    for r in prelim:
        cid = r["category_id"]
        # Collapse visible transaction collisions such as groceries_2 to the canonical template id.
        base = None
        import re
        m = re.match(r"^(.+)_\d+$", cid)
        if m:
            candidate = m.group(1)
            if candidate in by_id:
                base = candidate
            else:
                same_label_ids = [x for x in by_label_slug.get(slugify(r["label"]), []) if x != cid]
                template_same = [x for x in same_label_ids if by_id.get(x, {}).get("origin") == "template"]
                if template_same:
                    base = template_same[0]
        if base:
            remap[cid] = base
            continue
        final.append(r)
    # Remove accidental duplicate IDs after collapsing.
    dedup = {}
    for r in final:
        dedup.setdefault(r["category_id"], r)
    final = list(dedup.values())
    return final, remap


def match_category_id(label: str, taxonomy: list[dict], remap: dict[str, str]) -> str:
    value = str(label or "").strip()
    if not value:
        return ""
    ids = {r["category_id"]: r for r in taxonomy}
    if value in remap:
        return remap[value]
    if value in ids:
        return value
    value_slug = slugify(value)
    if value_slug in ids:
        return value_slug
    for r in taxonomy:
        if slugify(r["label"]) == value_slug:
            return r["category_id"]
    return ""


def unique_id(wanted: str, taxonomy: list[dict]) -> str:
    existing = {r["category_id"] for r in taxonomy}
    base = slugify(wanted)[:64].strip("_") or "uncategorized"
    cid = base
    i = 2
    while cid in existing:
        cid = f"{base}_{i}"
        i += 1
    return cid


def build_aliases(taxonomy: list[dict], remap: dict[str, str]):
    aliases = []
    # Rules become aliases directly.
    _, rules = read_csv(INPUT / "client_spending_rules.csv")
    for r in rules:
        mv = str(r.get("keyword") or "").strip()
        cid = match_category_id(r.get("category_id", ""), taxonomy, remap) or match_category_id(mv, taxonomy, remap)
        if mv and cid:
            aliases.append({"match_value": mv, "match_field": r.get("match_field") or "category", "exact": "1" if str(r.get("exact", "1")).lower() in ("1", "true", "yes") else "0", "priority": r.get("priority") or "60", "category_id": cid, "source": "seed"})
    # Legacy bank category map: exact raw category aliases; promote if no canonical category exists.
    _, cat_map = read_csv(INPUT / "spending_category_map.csv")
    for r in cat_map:
        raw = str(r.get("category") or "").strip()
        if not raw:
            continue
        cid = match_category_id(raw, taxonomy, remap)
        if not cid:
            cid = unique_id(raw, taxonomy)
            taxonomy.append({
                "tracking_type": normalize_tracking(r.get("tracking")),
                "group": str(r.get("group") or "Other").strip(),
                "category_id": cid,
                "label": raw,
                "origin": "transaction",
                "status": "active",
                "notes": "Promoted from legacy spending_category_map.csv during unified spending migration",
            })
        aliases.append({"match_value": raw, "match_field": "category", "exact": "1", "priority": "50", "category_id": cid, "source": "seed"})
    dedup = {}
    for a in aliases:
        key = (a["match_value"].lower(), a["match_field"].lower(), a["exact"], a["category_id"])
        dedup[key] = a
    return sorted(dedup.values(), key=lambda x: (-int(float(x["priority"] or 0)), x["match_value"].lower(), x["category_id"]))


def apply_template_default_status(taxonomy: list[dict], aliases: list[dict], budget: list[dict]) -> int:
    """Start from transaction/custom categories; template rows load on demand by group.

    Template categories that already have aliases or budget/detail rows stay active.
    Everything else is soft-deleted so it can be restored by group at $0.
    """
    alias_ids = {a.get("category_id") for a in aliases if a.get("category_id")}
    budget_ids = {b.get("key") for b in budget if b.get("kind") in {"category", "line"} and (n(b.get("annual_budget")) != 0 or b.get("kind") == "line")}
    changed = 0
    for row in taxonomy:
        cid = row.get("category_id")
        if row.get("origin") == "template" and cid not in alias_ids and cid not in budget_ids:
            if row.get("status") != "deleted":
                changed += 1
            row["status"] = "deleted"
    return changed


def build_budget(taxonomy: list[dict], remap: dict[str, str]):
    flat = {r["category_id"]: r for r in taxonomy}
    category_totals = defaultdict(float)
    notes = {}
    h, rows = read_csv(INPUT / "client_spending_budget.csv")
    if {"kind", "key"}.issubset(set(h)):
        return rows
    for r in rows:
        cid = match_category_id(r.get("category_id", ""), taxonomy, remap)
        if not cid:
            continue
        category_totals[cid] += n(r.get("annual_budget"))
        notes.setdefault(cid, r.get("notes", ""))
    out = []
    for cid in sorted(category_totals):
        out.append({"kind": "category", "key": cid, "label": flat.get(cid, {}).get("label", cid), "annual_budget": "%d" % round(category_totals[cid]) if category_totals[cid] else "", "start_year": "", "end_year": "", "one_time_year": "", "notes": notes.get(cid, "")})
    _, lines = read_csv(INPUT / "client_spending_budget_lines.csv")
    for line in lines:
        cid = match_category_id(line.get("category_id", ""), taxonomy, remap)
        if not cid:
            continue
        out.append({
            "kind": "line",
            "key": cid,
            "label": line.get("label") or line.get("line_id") or cid,
            "annual_budget": "%d" % round(n(line.get("amount_per_year"))) if n(line.get("amount_per_year")) else "",
            "start_year": line.get("start_year", ""),
            "end_year": line.get("end_year", ""),
            "one_time_year": line.get("one_time_year", ""),
            "notes": line.get("notes", ""),
        })
    return out


def main(argv=None) -> int:
    global ROOT, INPUT
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Print migration plan without writing files")
    parser.add_argument("--root", type=Path, default=ROOT, help="Project root")
    args = parser.parse_args(argv)
    ROOT = args.root.resolve()
    INPUT = ROOT / "input"

    if already_migrated():
        print("Unified spending model already detected; no migration needed.")
        return 0

    taxonomy, remap = build_taxonomy()
    aliases = build_aliases(taxonomy, remap)
    budget = build_budget(taxonomy, remap)
    hidden_templates = apply_template_default_status(taxonomy, aliases, budget)
    taxonomy.sort(key=lambda r: (r["tracking_type"], r["group"], r["label"], r["category_id"]))

    before_budget = 0.0
    _, old_budget_rows = read_csv(INPUT / "client_spending_budget.csv")
    for r in old_budget_rows:
        before_budget += n(r.get("annual_budget"))
    after_budget = sum(n(r.get("annual_budget")) for r in budget if r.get("kind") == "category")

    print("Category ID remaps:")
    for old, new in sorted(remap.items()):
        print(f"  {old} -> {new}")
    print(f"Taxonomy rows: {len(taxonomy)}")
    print(f"Alias rows: {len(aliases)}")
    print(f"Budget category dollars before/after: {before_budget:,.0f} / {after_budget:,.0f}")
    print(f"Unified budget rows: {len(budget)}")
    print(f"Template categories hidden by default: {hidden_templates}")
    remaining_suffix_2 = [r["category_id"] for r in taxonomy if r["category_id"].endswith("_2")]
    if remaining_suffix_2:
        print("WARNING: _2 category ids remain:", ", ".join(remaining_suffix_2))

    if args.dry_run:
        return 0

    bdir = backup_inputs()
    write_csv(INPUT / "client_spending_taxonomy.csv", TAXONOMY_HEADER, taxonomy)
    write_csv(INPUT / "client_spending_aliases.csv", ALIAS_HEADER, aliases)
    write_csv(INPUT / "client_spending_budget.csv", BUDGET_HEADER, budget)

    # Regenerate manifest when the project helper is available.
    helper = ROOT / "tools" / "check_plan_data_sync.py"
    if helper.exists():
        import subprocess
        subprocess.run([sys.executable, str(helper), "--write"], cwd=str(ROOT), check=False)
    print(f"Backed up legacy spending files to {bdir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
