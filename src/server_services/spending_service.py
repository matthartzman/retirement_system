from __future__ import annotations

"""Feature-owned spending service helpers.

The HTTP route layer owns authentication, request extraction, and JSON
serialization.  This module owns request-independent spending dashboard,
taxonomy, budget, alias, and mapping behavior so the spending model can evolve
without adding more business logic to route files.
"""

import csv
import io
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

try:
    from .. import spending_tracker as st
except Exception:  # pragma: no cover - direct execution fallback
    from src import spending_tracker as st

AuditFn = Callable[[str, dict[str, Any] | None], None]
ReadPlanDataFn = Callable[[str], str | None]
WritePlanDataFn = Callable[[str, str], Path]


@dataclass(frozen=True)
class SpendingServiceContext:
    base_dir: Path
    read_plan_data_file: ReadPlanDataFn | None = None
    write_plan_data_file: WritePlanDataFn | None = None
    audit: AuditFn | None = None


class SpendingService:
    """Framework-neutral owner for spending API behavior."""

    def __init__(self, context: SpendingServiceContext):
        self.context = context
        self.base_dir = Path(context.base_dir)

    def _audit(self, event: str, details: dict[str, Any] | None = None) -> None:
        if self.context.audit:
            self.context.audit(event, details or {})

    def _read_plan_data_file(self, file_name: str) -> str | None:
        if self.context.read_plan_data_file:
            return self.context.read_plan_data_file(file_name)
        path = self.base_dir / "input" / file_name
        if path.exists():
            return path.read_text(encoding="utf-8-sig")
        return None

    def _write_plan_data_file(self, file_name: str, content: str) -> Path:
        if self.context.write_plan_data_file:
            return self.context.write_plan_data_file(file_name, content)
        path = self.base_dir / "input" / file_name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def core_spending_from_plan(self) -> float:
        content = self._read_plan_data_file("client_spending.csv")
        if not content:
            return 0.0
        reader = csv.DictReader(io.StringIO(content))
        for row in reader:
            if (
                str(row.get("section", "")).strip() == "Cashflow"
                and str(row.get("subsection", "")).strip().lower() == "spending"
                and str(row.get("label", "")).strip() == "annual_spending_base_year"
            ):
                raw = str(row.get("value", "") or "").replace(",", "").replace("$", "").strip()
                try:
                    return float(raw)
                except ValueError:
                    return 0.0
        return 0.0

    def dashboard_payload(self) -> tuple[dict[str, Any], int]:
        return st.spending_dashboard(root=self.base_dir, core_spending=self.core_spending_from_plan()), 200

    def seed_budget_payload(self) -> tuple[dict[str, Any], int]:
        budget = st.seed_budget_from_actuals(root=self.base_dir, core_spending=self.core_spending_from_plan())
        self._audit("spending_budget_seeded", {"groups": len(budget)})
        return {"success": True, "budget": {k: v for k, v in budget.items()}}, 200

    def load_actuals_payload(self) -> tuple[dict[str, Any], int]:
        """Merge unmapped transaction categories into taxonomy, then return annualized actuals."""
        summary = st.spending_summary_taxonomy(self.base_dir)
        flat = st.taxonomy_flat(self.base_dir)
        rules = st.load_mapping_rules(self.base_dir)
        existing_kw = {str(r.get("keyword", "")).lower() for r in rules}
        merged: list[dict[str, str]] = []
        for tt in summary.get("tracking_types", []) or []:
            ttname = tt.get("tracking_type") or "Core Expenses"
            if str(ttname).lower() in ("income", "transfer"):
                continue
            for g in tt.get("groups", []) or []:
                grp = g.get("group") or "Other"
                for c in g.get("categories", []) or []:
                    cid = str(c.get("id") or "").strip()
                    if not cid or cid in flat:
                        continue
                    raw = str(c.get("label") or cid)
                    slug = re.sub(r"[^a-z0-9]+", "_", cid.lower()).strip("_")[:64] or "uncategorized"
                    base, n = slug, 2
                    while slug in flat:
                        slug = f"{base}_{n}"
                        n += 1
                    st.save_taxonomy_category(self.base_dir, ttname, grp, slug, raw, "Auto-added from transactions")
                    flat = st.taxonomy_flat(self.base_dir)
                    merged.append({"category": cid, "id": slug})
                    if cid.lower() not in existing_kw:
                        rules.append({"keyword": cid, "category_id": slug, "match_field": "category", "exact": True, "priority": 60})
                        existing_kw.add(cid.lower())
        if merged:
            st.save_mapping_rules(self.base_dir, rules)
        summary2 = st.spending_summary_taxonomy(self.base_dir)
        actuals: dict[str, Any] = {}
        for tt in summary2.get("tracking_types", []):
            for g in tt.get("groups", []) or []:
                for c in g.get("categories", []) or []:
                    actuals[c["id"]] = c.get("annualized", 0.0)
        self._audit("spending_budget_load_actuals", {"merged": len(merged), "categories": len(actuals)})
        return {"success": True, "actuals": actuals, "merged": merged, "merged_count": len(merged)}, 200

    def taxonomy_payload(self) -> tuple[dict[str, Any], int]:
        tree = st.load_taxonomy(self.base_dir)
        flat = st.taxonomy_flat(self.base_dir)
        ordered = []
        for tt in st.TRACKING_TYPE_ORDER:
            if tt not in tree:
                continue
            tdata = tree[tt]
            groups_out = []
            for grp, gdata in tdata["groups"].items():
                groups_out.append({"group": grp, "categories": gdata["categories"]})
            ordered.append({"tracking_type": tt, "groups": groups_out})
        return {"success": True, "taxonomy": ordered, "flat": flat}, 200

    def taxonomy_category_add_payload(self, body: dict[str, Any]) -> tuple[dict[str, Any], int]:
        tt = (body.get("tracking_type") or "").strip()
        group = (body.get("group") or "").strip()
        cat_id = (body.get("id") or "").strip()
        label = (body.get("label") or "").strip()
        notes = (body.get("notes") or "").strip()
        if not (tt and group and cat_id and label):
            return {"success": False, "error": "tracking_type, group, id, and label are required"}, 400
        if not re.match(r"^[a-z0-9_]{1,64}$", cat_id):
            return {"success": False, "error": "id must be lowercase letters, numbers, underscores only"}, 400
        if cat_id in st.taxonomy_flat(self.base_dir):
            return {"success": False, "error": f"Category id '{cat_id}' already exists"}, 409
        st.save_taxonomy_category(self.base_dir, tt, group, cat_id, label, notes)
        self._audit("taxonomy_category_added", {"id": cat_id, "tracking_type": tt, "group": group})
        return {"success": True, "id": cat_id}, 200

    def taxonomy_category_update_payload(self, cat_id: str, body: dict[str, Any]) -> tuple[dict[str, Any], int]:
        label = (body.get("label") or "").strip()
        notes = (body.get("notes") or "").strip()
        if not label:
            return {"success": False, "error": "label is required"}, 400
        found = st.update_taxonomy_category(self.base_dir, cat_id, label, notes)
        if not found:
            return {"success": False, "error": f"Category '{cat_id}' not found"}, 404
        self._audit("taxonomy_category_updated", {"id": cat_id})
        return {"success": True}, 200

    def taxonomy_category_delete_payload(self, cat_id: str) -> tuple[dict[str, Any], int]:
        found = st.delete_taxonomy_category(self.base_dir, cat_id)
        if not found:
            return {"success": False, "error": f"Category '{cat_id}' not found"}, 404
        self._audit("taxonomy_category_deleted", {"id": cat_id})
        return {"success": True}, 200

    def taxonomy_group_delete_payload(self, body: dict[str, Any]) -> tuple[dict[str, Any], int]:
        tracking_type = (body.get("tracking_type") or "").strip()
        group = (body.get("group") or "").strip()
        if not (tracking_type and group):
            return {"success": False, "error": "tracking_type and group are required"}, 400
        try:
            ok = st.delete_taxonomy_group(self.base_dir, tracking_type, group)
        except ValueError as exc:
            return {"success": False, "error": str(exc)}, 409
        if not ok:
            return {"success": False, "error": "Group not found"}, 404
        self._audit("taxonomy_group_deleted", {"tracking_type": tracking_type, "group": group})
        return {"success": True}, 200

    def rules_payload(self) -> tuple[dict[str, Any], int]:
        return {"success": True, "rules": st.load_mapping_rules(self.base_dir)}, 200

    def save_rules_payload(self, body: dict[str, Any]) -> tuple[dict[str, Any], int]:
        rules = body.get("rules", [])
        st.save_mapping_rules(self.base_dir, rules)
        self._audit("spending_rules_saved", {"count": len(rules)})
        return {"success": True}, 200

    def budget_taxonomy_payload(self) -> tuple[dict[str, Any], int]:
        return {"success": True, "budget": st.load_budget_by_category(self.base_dir)}, 200

    def save_budget_taxonomy_payload(self, body: dict[str, Any]) -> tuple[dict[str, Any], int]:
        budget = body.get("budget", {})
        st.save_budget_by_category(self.base_dir, budget)
        self._audit("spending_budget_taxonomy_saved", {"categories": len(budget)})
        return {"success": True}, 200

    def recover_budget_payload(self) -> tuple[dict[str, Any], int]:
        out = st.recover_spending_budget_from_seed(self.base_dir, persist=True, force=False)
        self._audit("spending_budget_recovered", {"recovered": out.get("recovered", 0)})
        return out, 200

    def summary_payload(self, year: int | None = None) -> tuple[dict[str, Any], int]:
        return st.spending_summary_taxonomy(self.base_dir, year), 200

    def model_payload(self, year: int | None = None) -> tuple[dict[str, Any], int]:
        return st.spending_model(self.base_dir, year), 200

    _BUDGET_LINE_SECTION_DEFAULT = "category_budget"
    _BUDGET_LINE_MODE_DEFAULT = "detail"

    def _seed_charitable_giving_line(self) -> dict[str, Any] | None:
        """Bootstrap a starting Charitable Giving line for brand-new plans.

        Only used when no line rows exist yet in the unified budget; once a
        real charitable_donations line is saved, this seed is not consulted.
        """
        content = self._read_plan_data_file("client_spending.csv") or ""
        giving = ""
        try:
            for row in csv.DictReader(io.StringIO(content)):
                if str(row.get("label") or "").strip() == "annual_charitable_giving_high":
                    giving = str(row.get("value") or "").strip()
                    break
        except Exception:
            giving = ""
        if not giving:
            return None
        return {
            "section": "gifts_charity",
            "line_id": "charitable_giving_seed",
            "label": "Charitable Giving",
            "category_id": "charitable_donations",
            "start_year": "",
            "end_year": "",
            "one_time_year": "",
            "amount_per_year": giving,
            "mode": "summary",
            "notes": "Seeded from annual charitable giving",
        }

    def _budget_lines_from_unified(self) -> list[dict[str, Any]]:
        """Read persisted line-kind rows from the unified budget store.

        client_spending_budget.csv (kind=line rows) is the single source of
        truth for both reporting (spending_tracker._category_budget_for_year)
        and this editable "detail lines" UI. line_id is regenerated on every
        read; it only needs to be unique within one loaded session so the UI
        can target the right row for edits/deletes before the next save.
        """
        rows = st.load_unified_budget(self.base_dir)
        seen_counts: dict[str, int] = {}
        lines: list[dict[str, Any]] = []
        for row in rows:
            if row.get("kind") != "line":
                continue
            cid = str(row.get("key") or "").strip()
            if not cid:
                continue
            n = seen_counts.get(cid, 0)
            seen_counts[cid] = n + 1
            amount = row.get("annual_budget", 0)
            lines.append({
                "section": row.get("line_section") or self._BUDGET_LINE_SECTION_DEFAULT,
                "line_id": f"{cid}_{n}",
                "label": row.get("label") or "",
                "category_id": cid,
                "start_year": row.get("start_year") or "",
                "end_year": row.get("end_year") or "",
                "one_time_year": row.get("one_time_year") or "",
                "amount_per_year": (("%g" % amount) if amount else ""),
                "mode": row.get("line_mode") or self._BUDGET_LINE_MODE_DEFAULT,
                "notes": row.get("notes") or "",
            })
        if not lines:
            seed = self._seed_charitable_giving_line()
            if seed:
                lines.append(seed)
        return lines

    def budget_lines_payload(self) -> tuple[dict[str, Any], int]:
        return {"success": True, "lines": self._budget_lines_from_unified()}, 200

    def budget_lines_defaults_payload(self) -> tuple[dict[str, Any], int]:
        seed = self._seed_charitable_giving_line()
        return {"success": True, "lines": [seed] if seed else []}, 200

    def save_budget_lines_payload(self, body: dict[str, Any]) -> tuple[dict[str, Any], int]:
        lines = body.get("lines")
        if not isinstance(lines, list):
            return {"success": False, "error": "lines must be a list"}, 400
        existing = st.load_unified_budget(self.base_dir)
        non_line_rows = [r for r in existing if r.get("kind") != "line"]
        new_line_rows: list[dict[str, Any]] = []
        for line in lines:
            if not isinstance(line, dict):
                continue
            cid = str(line.get("category_id") or "").strip()
            if not cid:
                continue
            new_line_rows.append({
                "kind": "line",
                "key": cid,
                "label": str(line.get("label") or "").strip(),
                "annual_budget": line.get("amount_per_year"),
                "start_year": line.get("start_year") or "",
                "end_year": line.get("end_year") or "",
                "one_time_year": line.get("one_time_year") or "",
                "notes": line.get("notes") or "",
                "line_section": line.get("section") or "",
                "line_mode": line.get("mode") or "",
            })
        st.save_unified_budget(self.base_dir, non_line_rows + new_line_rows)
        self._audit("spending_budget_lines_saved", {"count": len(new_line_rows)})
        return {"success": True, "count": len(new_line_rows)}, 200

    def category_create_payload(self, body: dict[str, Any]) -> tuple[dict[str, Any], int]:
        label = (body.get("label") or body.get("category") or body.get("match_value") or "").strip()
        tracking_type = (body.get("tracking_type") or "Core Expenses").strip()
        group = (body.get("group") or "Other").strip()
        cat_id = (body.get("id") or body.get("category_id") or "").strip()
        if not label:
            return {"success": False, "error": "label is required"}, 400
        if not cat_id:
            cat_id = st._unique_category_id(self.base_dir, label)
        if not re.match(r"^[a-z0-9_]{1,64}$", cat_id):
            return {"success": False, "error": "category id must be lowercase letters, numbers, underscores only"}, 400
        if cat_id in st.taxonomy_flat(self.base_dir, include_deleted=True):
            return {"success": False, "error": f"Category id '{cat_id}' already exists"}, 409
        st.save_taxonomy_category(
            self.base_dir,
            tracking_type,
            group,
            cat_id,
            label,
            body.get("notes", ""),
            origin=body.get("origin") or "custom",
            status="active",
        )
        match_value = (body.get("match_value") or "").strip()
        if match_value:
            st.add_alias(
                self.base_dir,
                match_value,
                cat_id,
                match_field=body.get("match_field") or "category",
                exact=body.get("exact", True),
                priority=body.get("priority", 90),
                source=body.get("source") or "user",
            )
        self._audit("spending_category_created", {"id": cat_id, "tracking_type": tracking_type, "group": group})
        return {"success": True, "id": cat_id}, 200

    def category_update_payload(self, cat_id: str, body: dict[str, Any]) -> tuple[dict[str, Any], int]:
        found = st.update_taxonomy_category(
            self.base_dir,
            cat_id,
            label=body.get("label"),
            notes=body.get("notes"),
            tracking_type=body.get("tracking_type"),
            group=body.get("group"),
        )
        if not found:
            return {"success": False, "error": f"Category '{cat_id}' not found"}, 404
        self._audit("spending_category_updated", {"id": cat_id})
        return {"success": True}, 200

    def category_delete_payload(self, cat_id: str) -> tuple[dict[str, Any], int]:
        found = st.delete_taxonomy_category(self.base_dir, cat_id)
        if not found:
            return {"success": False, "error": f"Category '{cat_id}' not found"}, 404
        self._audit("spending_category_soft_deleted", {"id": cat_id})
        return {"success": True}, 200

    def category_restore_payload(self, cat_id: str) -> tuple[dict[str, Any], int]:
        found = st.restore_taxonomy_category(self.base_dir, cat_id)
        if not found:
            return {"success": False, "error": f"Category '{cat_id}' not found"}, 404
        self._audit("spending_category_restored", {"id": cat_id})
        return {"success": True}, 200

    def restore_template_payload(self, body: dict[str, Any]) -> tuple[dict[str, Any], int]:
        tracking_type = (body.get("tracking_type") or "").strip()
        group = (body.get("group") or "").strip()
        if tracking_type and group and hasattr(st, "restore_template_group"):
            restored = st.restore_template_group(self.base_dir, tracking_type, group)
            self._audit("spending_template_group_restored", {"tracking_type": tracking_type, "group": group, "count": len(restored)})
        else:
            restored = st.restore_template_categories(self.base_dir)
            self._audit("spending_template_categories_restored", {"count": len(restored)})
        return {"success": True, "restored": restored, "count": len(restored)}, 200

    def hide_unused_templates_payload(self) -> tuple[dict[str, Any], int]:
        hidden = st.hide_unused_template_categories(self.base_dir) if hasattr(st, "hide_unused_template_categories") else []
        self._audit("spending_unused_template_categories_hidden", {"count": len(hidden)})
        return {"success": True, "hidden": hidden, "count": len(hidden)}, 200

    def alias_add_payload(self, body: dict[str, Any]) -> tuple[dict[str, Any], int]:
        match_value = (body.get("match_value") or body.get("keyword") or "").strip()
        category_id = (body.get("category_id") or "").strip()
        if not (match_value and category_id):
            return {"success": False, "error": "match_value and category_id are required"}, 400
        try:
            st.add_alias(
                self.base_dir,
                match_value,
                category_id,
                match_field=body.get("match_field") or "category",
                exact=body.get("exact", True),
                priority=body.get("priority", 90),
                source=body.get("source") or "user",
            )
        except ValueError as exc:
            return {"success": False, "error": str(exc)}, 400
        self._audit("spending_alias_added", {"match_value": match_value, "category_id": category_id})
        return {"success": True}, 200

    def aliases_payload(self) -> tuple[dict[str, Any], int]:
        return {"success": True, "aliases": st.load_aliases(self.base_dir)}, 200

    def save_aliases_payload(self, body: dict[str, Any]) -> tuple[dict[str, Any], int]:
        aliases = body.get("aliases") or body.get("rules") or []
        st.save_aliases(self.base_dir, aliases)
        self._audit("spending_aliases_saved", {"count": len(aliases)})
        return {"success": True}, 200

    def unified_budget_payload(self) -> tuple[dict[str, Any], int]:
        return {"success": True, "budget": st.load_unified_budget(self.base_dir)}, 200

    def save_unified_budget_payload(self, body: dict[str, Any]) -> tuple[dict[str, Any], int]:
        rows = body.get("budget") or body.get("rows") or []
        if isinstance(rows, dict):
            st.save_budget_by_category(self.base_dir, rows)
        else:
            st.save_unified_budget(self.base_dir, rows)
        self._audit("spending_budget_unified_saved", {"rows": len(rows) if hasattr(rows, "__len__") else 0})
        return {"success": True}, 200
