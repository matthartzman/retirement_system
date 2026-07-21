from __future__ import annotations

"""Feature-owned Plan Configuration service helpers.

Route modules adapt permissions, request bodies, and HTTP response objects.  This
service owns request-independent Plan Data row payloads, allocation preview, and
bulk row-save semantics so route modules remain thin under the
Flask-free runtime.
"""

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

try:
    from ..roth_ui_build_guard import normalize_roth_csv_value
    from .. import allocation_policy as allocation_policy_mod
    from ..schema_registry import validate_rows as _schema_validate_rows_full
except ImportError:  # pragma: no cover - direct execution fallback
    from src.roth_ui_build_guard import normalize_roth_csv_value
    from src import allocation_policy as allocation_policy_mod
    from src.schema_registry import validate_rows as _schema_validate_rows_full

JsonDict = dict[str, Any]
AuditFn = Callable[[str, dict[str, Any] | None], None]


@dataclass(frozen=True)
class ConfigServiceContext:
    version: str
    base_dir: Path
    csv_path: Path
    plan_data_csv_files: list[str]
    client_data_csv_file_set: set[str]
    plan_data_path: Callable[..., Path]
    client_csv_rows: Callable[[], list[dict[str, Any]]]
    csv_rows_payload: Callable[[], dict[str, Any]]
    read_schema_map: Callable[[], dict[Any, dict[str, Any]]]
    write_client_rows: Callable[[Path, list[list[str]]], None]
    load_active_config: Callable[[], tuple[dict[str, Any], dict[str, Any]]]
    runtime_config: Callable[[], Any]
    normalize_date_for_csv: Callable[[str], str]
    sync_config_backends: Callable[[], Any]
    audit: AuditFn | None = None


class ConfigService:
    """Framework-neutral owner for Plan Configuration routes."""

    def __init__(self, context: ConfigServiceContext):
        self.context = context

    def _audit(self, event: str, details: dict[str, Any] | None = None) -> None:
        if self.context.audit:
            self.context.audit(event, details or {})

    def config_backends_payload(self) -> tuple[JsonDict, int]:
        cfg = self.context.runtime_config()
        payload = self.context.csv_rows_payload()
        _data, meta = self.context.load_active_config()
        return {
            "success": True,
            "active_backend": meta.get("backend", "CSV"),
            "csv_path": str(self.context.csv_path),
            "json_path": str(self.context.csv_path.parent / "client_data.json"),
            "yaml_path": str(self.context.csv_path.parent / "client_data.yaml"),
            "sqlite_db": str(getattr(cfg, "sqlite_db", "")),
            "row_count": len(payload["rows"]),
            "schema_count": payload["schema_count"],
            "config_backend_setting": getattr(cfg, "config_backend", None),
        }, 200

    def config_rows_payload(self) -> tuple[JsonDict, int]:
        payload = self.context.csv_rows_payload()
        _data, meta = self.context.load_active_config()
        return {
            "success": True,
            "version": self.context.version,
            "active_backend": meta.get("backend", "CSV"),
            "csv_path": str(self.context.csv_path),
            "module_status": self._module_status(_data),
            **payload,
        }, 200

    @staticmethod
    def _module_status(sectioned_data: dict[str, Any]) -> JsonDict:
        """Best-effort optional-module gating status for the UI (see
        ``module_catalog.module_status``). module_catalog has zero heavy
        dependencies (A9), so unlike the reporting package this import is not
        lazy for cost reasons - it just still degrades to ``{}`` rather than
        failing the whole config payload if anything's amiss.
        """
        try:
            from ..module_catalog import module_status
            from ..report_compute import prepare_config_from_sectioned_data
        except ImportError:  # pragma: no cover - direct execution fallback
            try:
                from src.module_catalog import module_status
                from src.report_compute import prepare_config_from_sectioned_data
            except ImportError:
                return {}
        try:
            cfg = prepare_config_from_sectioned_data(sectioned_data, "", optimize_roth=False)
            return module_status(cfg)
        except Exception:
            return {}

    @staticmethod
    def _sectioned_data_from_ui_rows(ui_rows: list[Any]) -> dict[str, dict[str, dict[str, str]]]:
        data: dict[str, dict[str, dict[str, str]]] = {}
        for r in ui_rows:
            if not isinstance(r, dict):
                continue
            sec = str(r.get("section") or "").strip()
            sub = str(r.get("subsection") or "").strip()
            lbl = str(r.get("label") or "").strip()
            if not sec or sec.startswith("#") or not lbl:
                continue
            val = str(r.get("value") or "").strip()
            data.setdefault(sec, {}).setdefault(sub, {})[lbl] = val
        return data

    @staticmethod
    def _clean_targets(obj: dict[str, Any], key: str) -> dict[str, float]:
        out: dict[str, float] = {}
        for k, v in (obj.get(key) or {}).items():
            try:
                out[str(k)] = float(v or 0.0)
            except Exception:
                out[str(k)] = 0.0
        return out

    def allocation_preview_payload(self, body: dict[str, Any]) -> tuple[JsonDict, int]:
        ui_rows = body.get("rows") or []
        mode = allocation_policy_mod.normalize_allocation_mode(
            body.get("mode") or body.get("allocation_selection_mode") or "optimizer_recommendation"
        )
        try:
            if isinstance(ui_rows, list) and ui_rows:
                data = self._sectioned_data_from_ui_rows(ui_rows)
            else:
                data = self.context.load_active_config()[0]
            data.setdefault("Asset Allocation Policy", {}).setdefault("Global", {})["allocation_selection_mode"] = mode
            try:
                from ..report_compute import prepare_config_from_sectioned_data
                from ..optimization import compute_optimal_allocation
                from .. import allocation_policy as _ap
            except ImportError:  # pragma: no cover - direct execution fallback
                from src.report_compute import prepare_config_from_sectioned_data
                from src.optimization import compute_optimal_allocation
                from src import allocation_policy as _ap
            cfg = prepare_config_from_sectioned_data(data, "", optimize_roth=False)
            selected = compute_optimal_allocation(cfg, force_mode=mode)
            optimizer = compute_optimal_allocation(cfg, force_mode=_ap.ALLOCATION_MODE_OPTIMIZER)
            user = compute_optimal_allocation(cfg, force_mode=_ap.ALLOCATION_MODE_USER)
            coverage = selected.get("allocation_coverage") or {}
            return {
                "success": True,
                "mode": mode,
                "selected_policy_mode": (selected.get("diagnostics") or {}).get("allocation_policy_mode"),
                "optimizer_policy_mode": (optimizer.get("diagnostics") or {}).get("allocation_policy_mode"),
                "selected_total_targets": self._clean_targets(selected, "total_targets"),
                "selected_liquid_targets": self._clean_targets(selected, "liquid_targets"),
                "optimizer_total_targets": self._clean_targets(optimizer, "total_targets"),
                "optimizer_liquid_targets": self._clean_targets(optimizer, "liquid_targets"),
                "user_total_targets": self._clean_targets(user, "total_targets"),
                "user_liquid_targets": self._clean_targets(user, "liquid_targets"),
                "selected_diagnostics": selected.get("diagnostics") or {},
                "optimizer_diagnostics": optimizer.get("diagnostics") or {},
                "user_diagnostics": user.get("diagnostics") or {},
                "coverage_summary": {
                    "fixed_income_coverage_pv": coverage.get("fixed_income_coverage_pv", 0),
                    "fixed_income_included_sources": coverage.get("fixed_income_included_sources", []),
                    "fixed_income_excluded_sources": coverage.get("fixed_income_excluded_sources", []),
                    "ss_pv": coverage.get("ss_pv", 0),
                    "pension_pv": coverage.get("pension_pv", 0),
                    "annuity_pv": coverage.get("annuity_pv", 0),
                    "gross_home_equity": coverage.get("gross_home_equity", 0),
                    "home_equity_allocation_value": coverage.get("home_equity_allocation_value", 0),
                    "home_equity_reit_coverage_value": coverage.get("home_equity_reit_coverage_value", 0),
                    "home_equity_counts_toward_reit": coverage.get("home_equity_counts_toward_reit", False),
                    "home_equity_excluded": coverage.get("home_equity_excluded", False),
                    "funded_ratio": selected.get("funded_ratio", 0),
                },
            }, 200
        except Exception as exc:
            self._audit("allocation_preview_failed", {"error": str(exc)})
            return {"success": False, "error": str(exc)}, 500

    def _validate_all_workspace_plan_rows(self, file_rows: dict[str, list[list[str]]]) -> list[str]:
        combined: list[dict[str, str]] = []
        names = [n for n in self.context.plan_data_csv_files if n != "client_holdings.csv"]
        for name in names:
            rows = file_rows.get(name)
            if rows is None:
                p = self.context.plan_data_path(name)
                if not p.exists():
                    continue
                with p.open(newline="", encoding="utf-8-sig") as f:
                    rows = list(csv.reader(f))
            if not rows:
                continue
            header = list(rows[0])
            if not {"section", "subsection", "label", "value"}.issubset(set(header)):
                continue
            for raw in rows[1:]:
                padded = list(raw) + [""] * max(0, len(header) - len(raw))
                combined.append({header[i]: padded[i] if i < len(padded) else "" for i in range(len(header))})
        return _schema_validate_rows_full(combined)

    def update_config_rows_payload(self, body: dict[str, Any], *, allow_csv_write: bool) -> tuple[JsonDict, int]:
        if not allow_csv_write:
            return {"success": False, "error": "CSV writes are disabled"}, 403
        updates = body.get("updates") or []
        if not isinstance(updates, list):
            return {"success": False, "error": "updates must be a list"}, 400

        row_map = {int(e["row_index"]): e for e in self.context.client_csv_rows()}
        file_rows: dict[str, list[list[str]]] = {}
        updated = 0
        skipped: list[dict[str, Any]] = []

        def rows_for_file(name: str) -> list[list[str]]:
            if name not in file_rows:
                path = self.context.plan_data_path(name)
                with path.open(newline="", encoding="utf-8-sig") as f:
                    file_rows[name] = list(csv.reader(f))
            return file_rows[name]

        for u in updates:
            try:
                idx = int(u.get("row_index"))
            except Exception:
                skipped.append({"update": u, "reason": "invalid row_index"})
                continue
            entry = row_map.get(idx)
            if not entry:
                skipped.append({"row_index": idx, "reason": "out of range or stale row index"})
                continue
            source_file = str(entry["source_file"])
            source_idx = int(entry["source_row_index"])
            rows = rows_for_file(source_file)
            if source_idx <= 0 or source_idx >= len(rows):
                skipped.append({"row_index": idx, "reason": "out of range or header row"})
                continue
            row = rows[source_idx]
            while len(row) < 6:
                row.append("")
            section = str(row[0] or "").strip()
            label = str(row[2] or "").strip()
            if section.startswith("#") or not label:
                skipped.append({"row_index": idx, "reason": "comment/blank row is not editable"})
                continue
            value = str(u.get("value", ""))
            spec = self.context.read_schema_map().get((str(row[0]).strip(), str(row[1]).strip(), str(row[2]).strip()), {})
            if (spec.get("type") or "").lower() == "date" or str(row[4] if len(row) > 4 else "").strip().lower() == "date":
                value = self.context.normalize_date_for_csv(value)
            value = normalize_roth_csv_value(row[0], row[1], row[2], value)
            row[3] = value
            updated += 1

        validation_errors = self._validate_all_workspace_plan_rows(file_rows)
        if validation_errors:
            self._audit("config_rows_validation_failed", {"updated_attempted": updated, "error_count": len(validation_errors)})
            return {"success": False, "error": "Plan Data validation failed", "errors": validation_errors[:50]}, 422

        for source_file, rows in file_rows.items():
            self.context.write_client_rows(self.context.plan_data_path(source_file), rows)

        self._audit("config_rows_saved", {"updated": updated, "skipped": len(skipped), "files": sorted(file_rows)})
        sync_result = None
        if body.get("sync"):
            sync_result = self.context.sync_config_backends()
            self._audit("config_backends_synced", sync_result)
        return {"success": True, "updated": updated, "skipped": skipped, "sync": sync_result}, 200
