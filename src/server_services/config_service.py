from __future__ import annotations

"""Feature-owned Plan Configuration service helpers.

Route modules adapt permissions, request bodies, and HTTP response objects.  This
service owns request-independent Plan Data row payloads, allocation preview, and
bulk row-save semantics so route modules remain thin under the
Flask-free runtime.
"""

import csv
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ..roth_ui_build_guard import normalize_roth_csv_value
from .. import allocation_policy as allocation_policy_mod
from ..schema_registry import validate_rows as _schema_validate_rows_full

JsonDict = dict[str, Any]
AuditFn = Callable[[str, dict[str, Any] | None], None]

OPTIONAL_FUNCTIONS_CSV = "client_optional_functions.csv"


def backfill_optional_function_rows(rows: list[JsonDict], effective: dict[str, bool]) -> list[JsonDict]:
    """Append a row for every switchable catalog module the plan's
    client_optional_functions.csv lacks, valued at its current effective
    state, so Plan Features can show and edit it (the missing-row bug).

    ``rows`` are the plan's existing Optional Functions rows (untouched --
    this never edits or reorders one that's already there); ``effective`` is
    a ``{module_key: enabled}`` map (e.g. from ``module_status()``), read
    with ``.get(key, True)`` so a module this map has no opinion on defaults
    to on rather than silently switching itself off the moment a backfill
    runs. Only ``GATE_MODULE_TOGGLE`` modules with no ``gated_by`` parent are
    candidates -- a plan flag has no CSV row by design (§5.3/W9), and a
    bundled module's state is decided by its parent's toggle, not its own row.
    """
    from ..module_catalog import CATALOG, GATE_MODULE_TOGGLE
    have = {r.get("label") for r in rows}
    out = list(rows)
    for key, m in CATALOG.items():
        if m.optional and m.gate_kind == GATE_MODULE_TOGGLE and not m.gated_by and key not in have:
            out.append({"section": "Optional Functions", "subsection": "", "label": key,
                        "value": "TRUE" if effective.get(key, True) else "FALSE",
                        "units": "boolean", "notes": m.name})
    return out


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
    write_plan_data_file: Callable[[str, str], Path]
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
        self._backfill_optional_function_rows_to_disk()
        payload = self.context.csv_rows_payload()
        _data, meta = self.context.load_active_config()
        return {
            "success": True,
            "version": self.context.version,
            "active_backend": meta.get("backend", "CSV"),
            "csv_path": str(self.context.csv_path),
            "module_status": self._module_status(_data),
            "module_gates": self._module_gates(),
            "module_taxonomy": self._module_taxonomy(),
            **payload,
        }, 200

    @staticmethod
    def _module_gates() -> JsonDict:
        """§7.4 + §5.3: {step_gates, section_gates, flag_gates} the frontend uses to hide a nav
        step or an input-CSV section while its owning optional module is
        off — the single source of truth replacing dashboard.js's
        hand-maintained ``stepGatedByOptionalModule``/``ROW_MODULE_GATES``.
        Static (module_catalog has zero heavy deps), so unlike
        ``_module_status`` this needs no sectioned-data input or fallback.

        ``section_gates`` carries both ``key`` (the toggle) and ``label``
        (the module's display name + " optional workbook module", matching
        the wording dashboard.js's old ``ROW_MODULE_GATES`` hardcoded) so the
        frontend needs no separate module-name lookup for its reason/
        activation text.
        """
        from ..module_catalog import (CATALOG, flag_gate_map, section_gate_map,
                                       step_gate_map)
        section_gates = {
            section: {"key": key, "label": f"{CATALOG[key].name} optional workbook module"}
            for section, key in section_gate_map().items()
        }
        return {
            "step_gates": step_gate_map(),
            "section_gates": section_gates,
            # #330 §5.3 (W6): the plan-flag half of the same question. Served
            # beside ``step_gates`` rather than merged into it because the two
            # are evaluated by different predicates on the frontend -- a
            # toggle key vs a (section, subsection, label) plan row -- and a
            # merged map would only make the caller re-derive which it held.
            "flag_gates": flag_gate_map(),
        }

    @staticmethod
    def _module_taxonomy() -> JsonDict:
        """#330 phase 2: the two classification axes, per module, for the UI.

        `domain` is what the Plan Features page groups by (the user is asking
        "is this about my life"); `kind` is what its filter chips filter by
        (the ticket's Optimizers/Stress-tests view, on demand). Both are
        served from `CATALOG` so the switch nav can never become a third
        hand-maintained taxonomy beside the catalog and the workbook.

        It also carries #330 §3.4's soft-dependency relation in both
        directions and the `engine_participation` flag, so the switch UI can
        warn about what an off-toggle removes elsewhere without shipping a
        second copy of the relation.

        Static and dependency-free for the same reason `_module_gates` is:
        `module_catalog` imports nothing heavier than the stdlib, so this adds
        no cost to a payload the dashboard fetches on every save.
        """
        from ..module_catalog import (
            ANSWER_TYPES, CATALOG, DOMAINS, KIND_ANSWER_TYPE, KIND_QUESTION,
            soft_dependents,
        )
        return {
            "domains": list(DOMAINS),
            "kind_questions": dict(KIND_QUESTION),
            # #332 §1.2: the user-facing vocabulary for `kind` (what SHAPE of
            # answer a module gives), served alongside `kind` so the frontend
            # never has to hand-maintain its own kind->label map.
            "answer_types": list(ANSWER_TYPES),
            "modules": {
                key: {
                    "name": m.name,
                    "kind": m.kind,
                    "answer_type": KIND_ANSWER_TYPE[m.kind],
                    "domain": m.domain,
                    "demand": m.demand,
                    "optional": m.optional,
                    # #330 §3.3 (W8b): the parent whose toggle switches this
                    # module, or None. Served because the switch page's whole
                    # promise is that a module's state is explainable -- a
                    # bundled module has no row of its own, so without this the
                    # UI could only report "on" with no way to say what decided
                    # it.
                    "gated_by": m.gated_by,
                    "description": m.description,
                    # #330 §3.4. Both directions are served, because the UI
                    # needs both and inverting a map in JS would make the
                    # frontend a second place the relationship is expressed.
                    #   degrades_without -- what this module needs to be
                    #     complete ("shows less because X is off");
                    #   degraded_by -- what turning THIS module off costs
                    #     elsewhere, which is the warning on its own switch.
                    "degrades_without": [
                        {"key": dep, "loses": loses} for dep, loses in m.degrades_without
                    ],
                    "degraded_by": [
                        {"key": dep, "name": CATALOG[dep].name, "loses": loses}
                        for dep, loses in soft_dependents(key)
                    ],
                    "engine_participation": m.engine_participation,
                    # #330 §5.3 (W9): Plan Features lists a plan flag too, but
                    # as a link to the page that owns its data rather than a
                    # toggle -- it has no client_optional_functions.csv row
                    # for the loop that builds every other row on this page to
                    # find. Served per-module (not only via flag_gate_map(),
                    # which is dashboard_step-keyed and so covers only HELOC)
                    # so Hybrid LTC/DAF/QCD -- none of which own a
                    # dashboard_step -- are still discoverable here.
                    "gate_kind": m.gate_kind,
                    "gate_ref": list(m.gate_ref) if m.gate_ref else None,
                    "gate_enable_label": m.gate_enable_label,
                }
                for key, m in CATALOG.items()
            },
        }

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
            return {}
        # #234: this only reads module on/off toggles from cfg -- it never
        # needs real holding values, so the live price-provider network calls
        # parse_client() makes for every held symbol (measured: ~12s of the
        # ~13s /api/config/rows was taking, fetched on every save/navigation)
        # are wasted work here. skip_live_pricing is threaded through as an
        # explicit parameter (not an env-var flip) because this server is a
        # ThreadingHTTPServer -- a global env mutation could race a concurrent
        # real build/report request that needs genuinely live prices.
        try:
            cfg = prepare_config_from_sectioned_data(sectioned_data, "", optimize_roth=False, skip_live_pricing=True)
            return module_status(cfg)
        except Exception:
            return {}

    def _backfill_optional_function_rows_to_disk(self) -> None:
        """#330 bug fix: client_optional_functions.csv can predate a catalog
        module (an older plan folder, or one saved before the module
        existed), leaving that module with no toggle row -- Plan Features
        then has no CSV row to render a switch for, so the module is
        invisible on the one page meant to be its complete list.

        Reads the file, computes what ``backfill_optional_function_rows`` is
        missing, and -- only if something is missing -- writes it back
        through ``write_plan_data_file``, the same plan-data save path
        ``update_config_rows_payload`` already uses (see its own comment on
        why: it keeps a SQLite-backed backend in sync with disk). Writing
        before ``csv_rows_payload()`` runs (called right after this, in
        ``config_rows_payload``) is what gives each backfilled row a real,
        persisted ``row_index`` -- the ordinary ``editValue(row_index)``
        toggle click needs nothing else to work on it.

        Best-effort: a missing/unreadable file just means nothing gets
        backfilled this call, not a broken payload.

        Deliberately does NOT call ``load_active_config``/``module_status``
        to decide a missing row's value. Two reasons (final review on A3):
        (1) which rows are even missing is a pure catalog-vs-existing-labels
        comparison, so doing a full config prepare unconditionally on every
        ``/api/config/rows`` GET -- before even checking whether anything is
        missing -- was wasted work, done twice over (``config_rows_payload``
        calls ``_module_status`` again right after this for the real
        payload). (2) ``module_status()[k]["enabled"]`` folds in the
        build-time ``RETIREMENT_SYSTEM_FORCE_*`` env-var override tier
        (#330 Q7), which was deliberately never made a writable path -- a
        missing row already defaults to enabled per ``module_enabled``'s own
        "absent keys default to enabled" rule, so using ``module_status()``
        here could only ever differ from that default by silently baking a
        FORCE_DISABLE override into the plan's permanent store on a mere
        GET. So a missing row is always written ``"TRUE"``, matching the
        ordinary missing-row default, regardless of any env override.
        """
        path = self.context.plan_data_path(OPTIONAL_FUNCTIONS_CSV)
        try:
            if not path.exists():
                return
            with path.open(newline="", encoding="utf-8-sig") as f:
                raw_rows = [list(r) for r in csv.reader(f)]
        except Exception:
            return
        if not raw_rows:
            return

        existing: list[JsonDict] = []
        for raw in raw_rows[1:]:  # skip header
            section = str(raw[0] if raw else "").strip()
            if not section or section.startswith("#"):
                continue  # comment/blank rows carry no label to key on
            padded = list(raw) + [""] * max(0, 6 - len(raw))
            existing.append({
                "section": padded[0], "subsection": padded[1], "label": padded[2],
                "value": padded[3], "units": padded[4], "notes": padded[5],
            })

        # effective={} -- backfill_optional_function_rows() reads it with
        # .get(key, True), so an empty map always falls through to the
        # standard "TRUE" missing-row default described above, with no
        # config load at all.
        out = backfill_optional_function_rows(existing, effective={})
        have = {r.get("label") for r in existing}
        new_rows = [r for r in out if r.get("label") not in have]
        if not new_rows:
            return

        all_rows = list(raw_rows)
        for r in new_rows:
            all_rows.append([r.get("section", ""), r.get("subsection", ""), r.get("label", ""),
                              r.get("value", ""), r.get("units", ""), r.get("notes", "")])
        buf = io.StringIO(newline="")
        csv.writer(buf, lineterminator="\n").writerows(all_rows)
        self.context.write_plan_data_file(OPTIONAL_FUNCTIONS_CSV, buf.getvalue())

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
            from ..report_compute import prepare_config_from_sectioned_data
            from ..optimization import compute_optimal_allocation
            from .. import allocation_policy as _ap
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

    def daf_recommendation_payload(self, body: dict[str, Any]) -> tuple[JsonDict, int]:
        """#270: recommend a DAF contribution amount for the current plan,
        maximizing within the IRS AGI ceiling (60% cash / 30% appreciated).
        Read-only -- never writes the plan; the UI applies the number itself."""
        from ..daf_optimizer import recommend_daf_contribution
        from ..report_compute import prepare_config_from_sectioned_data
        try:
            data = self.context.load_active_config()[0]
            cfg = prepare_config_from_sectioned_data(data, "", optimize_roth=False)
            year = body.get("year")
            appreciated = bool(body.get("appreciated", cfg.get("daf_contribution_is_appreciated", False)))
            out = recommend_daf_contribution(cfg, rows=None, year=int(year) if year else None, appreciated=appreciated)
            out["success"] = True
            return out, 200
        except Exception as exc:
            self._audit("daf_recommendation_failed", {"error": str(exc)})
            return {"success": False, "error": str(exc)}, 500

    def qlac_recommendation_payload(self, body: dict[str, Any]) -> tuple[JsonDict, int]:
        """#295: recommend a QLAC premium for one household member, maximizing
        within min(the statutory aggregate dollar cap, that person's available
        pre-tax balance). Read-only -- never writes the plan; the UI applies
        the number itself."""
        from ..qlac_optimizer import recommend_qlac_premium
        from ..report_compute import prepare_config_from_sectioned_data
        try:
            data = self.context.load_active_config()[0]
            cfg = prepare_config_from_sectioned_data(data, "", optimize_roth=False)
            year = body.get("year")
            owner_idx = int(body.get("owner_idx", 0) or 0)
            out = recommend_qlac_premium(cfg, owner_idx, year=int(year) if year else None)
            out["success"] = True
            return out, 200
        except Exception as exc:
            self._audit("qlac_recommendation_failed", {"error": str(exc)})
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

        # Route through write_plan_data_file (not the raw write_client_rows) so the
        # SQLite client_files row stays in sync with disk -- callers that read this
        # file DB-first (e.g. demo-mode restore, _read_plan_data_file) would
        # otherwise keep serving the pre-edit value after a grid save (#240).
        for source_file, rows in file_rows.items():
            buf = io.StringIO(newline="")
            # write_plan_data_file's disk write goes through Path.write_text(),
            # which translates "\n" to os.linesep -- an embedded "\r\n" from the
            # csv module's default dialect would double up into "\r\r\n" on
            # Windows, so force "\n" line endings (matches _csv_write_rows).
            csv.writer(buf, lineterminator="\n").writerows(rows)
            self.context.write_plan_data_file(source_file, buf.getvalue())

        self._audit("config_rows_saved", {"updated": updated, "skipped": len(skipped), "files": sorted(file_rows)})
        sync_result = None
        if body.get("sync"):
            sync_result = self.context.sync_config_backends()
            self._audit("config_backends_synced", sync_result)
        return {"success": True, "updated": updated, "skipped": skipped, "sync": sync_result}, 200
