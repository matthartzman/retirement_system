from __future__ import annotations

"""Plan tier and feature switches (WP5.1, design 2026-10-04 §2-§4, P4).

The route layer owns permissions and request parsing; this service owns the plan profile
payload, the tier presets the Plan Features picker shows, and the two writes: picking a tier
(``POST /api/plan/tier``, with a ``preview`` dry run) and overriding one switch
(``POST /api/plan/feature``). Both write through the context's ``edit_plan``
(``app_core._edit_active_plan``: one transaction on the plan file's rows), the same edit
context the strategy endpoints use. The rules themselves live in ``module_catalog``
(``tier_preset``, ``plan_profile``, ``apply_tier``, ``set_feature``).
"""

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Callable

from .. import module_catalog as mc

JsonDict = dict[str, Any]
AuditFn = Callable[[str, dict[str, Any] | None], None]


def entered_value(value: Any) -> bool:
    """A plan value that counts as entered data: non-blank and not a bare off switch.
    The rule the Plan Features page's ``enteredRowCount`` applies."""
    v = str(value if value is not None else "").strip()
    return bool(v) and v.upper() not in ("NO", "FALSE", "0")


def entered_rows(store: Any, key: str) -> int | None:
    """Rows of entered data behind feature ``key``, or None when the catalog declares no data
    location for it (only modules that gate input sections, ``csv_sections``, have one; a
    module owning a whole page is counted by the page from its own rows)."""
    sections = mc.CATALOG[key].csv_sections
    if not sections:
        return None
    return sum(1 for s in sections for r in store.rows(s) if entered_value(r["value"]))


def tier_presets_payload() -> JsonDict:
    """The picker's data: each tier's label, one-line description and preset keys (catalog
    order), smallest tier first. Static: the presets are a function of the catalog."""
    order = mc.switchable_keys()
    return {
        "default": mc.DEFAULT_PLAN_TIER,
        "switchable": order,
        "tiers": [
            {
                "key": tier,
                "label": mc.TIER_LABELS[tier],
                "description": mc.TIER_DESCRIPTIONS[tier],
                "features": [k for k in order if k in mc.tier_preset(tier)],
            }
            for tier in mc.TIERS
        ],
    }


def _feature_ref(key: str) -> JsonDict:
    return {"key": key, "name": mc.CATALOG[key].name}


def tier_change_details(store: Any, tier: str) -> JsonDict:
    """What picking ``tier`` changes, for the confirm dialog: the features turning on, the
    ones turning off with their entered-row counts and engine participation, and the
    engine-participating ones the projection will then ignore."""
    changes = mc.tier_changes(store, tier)
    turn_off = []
    for key in changes["turn_off"]:
        item = _feature_ref(key)
        item["entered_rows"] = entered_rows(store, key)
        item["engine_participation"] = mc.CATALOG[key].engine_participation
        turn_off.append(item)
    return {
        "tier": tier,
        "label": mc.TIER_LABELS[tier],
        "turn_on": [_feature_ref(k) for k in changes["turn_on"]],
        "turn_off": turn_off,
        "engine_ignored": [_feature_ref(i["key"]) for i in turn_off if i["engine_participation"]],
        "unchanged": not changes["turn_on"] and not changes["turn_off"],
    }


@dataclass(frozen=True)
class PlanTierServiceContext:
    edit_plan: Callable[[], AbstractContextManager[Any]]
    read_plan: Callable[[], AbstractContextManager[Any]]
    audit: AuditFn | None = None


class PlanTierService:
    """Framework-neutral owner for the plan tier and feature-switch writes."""

    def __init__(self, context: PlanTierServiceContext):
        self.context = context

    def _audit(self, event: str, details: dict[str, Any] | None = None) -> None:
        if self.context.audit:
            self.context.audit(event, details or {})

    def profile(self) -> JsonDict:
        """``module_catalog.plan_profile`` of the active plan."""
        with self.context.read_plan() as store:
            return mc.plan_profile(store)

    def apply_tier_payload(self, body: dict[str, Any]) -> tuple[JsonDict, int]:
        """``{tier, preview}``: with ``preview: true`` answer what picking the tier would
        change and write nothing; otherwise write the tier row and the switches in one edit."""
        tier = str(body.get("tier") or "").strip().lower()
        if tier not in mc.TIERS:
            return {"success": False, "error": f"tier must be one of: {', '.join(mc.TIERS)}"}, 400
        preview = body.get("preview", False)
        if not isinstance(preview, bool):
            return {"success": False, "error": "preview must be true or false"}, 400
        if preview:
            with self.context.read_plan() as store:
                details = tier_change_details(store, tier)
                current = mc.plan_profile(store)
            return {"success": True, "preview": True, "current": current, **details}, 200
        try:
            with self.context.edit_plan() as edit:
                details = tier_change_details(edit.store, tier)
                mc.apply_tier(edit.store, tier)
                profile = mc.plan_profile(edit.store)
            revision = edit.revision
        except Exception as exc:
            self._audit("plan_tier_failed", {"tier": tier, "error": str(exc)})
            return {"success": False, "error": f"Plan Data could not be saved: {exc}"}, 500
        self._audit("plan_tier_applied", {
            "tier": tier,
            "turned_on": [i["key"] for i in details["turn_on"]],
            "turned_off": [i["key"] for i in details["turn_off"]],
            "revision": revision,
        })
        return {"success": True, "preview": False, "profile": profile, "revision": revision, **details}, 200

    def set_feature_payload(self, body: dict[str, Any]) -> tuple[JsonDict, int]:
        """``{key, on}``: override one switch (``module_catalog.set_feature``) in one edit. For
        a switch with no row yet (a rowless page switch, a plan flag the plan never stored)."""
        key = str(body.get("key") or "").strip()
        on = body.get("on")
        if not isinstance(on, bool):
            return {"success": False, "error": "on must be true or false"}, 400
        try:
            mc.feature_row_key(key)
        except KeyError:
            return {"success": False, "error": f"unknown feature: {key!r}"}, 400
        except ValueError as exc:
            return {"success": False, "error": str(exc)}, 400
        try:
            with self.context.edit_plan() as edit:
                mc.set_feature(edit.store, key, on)
                profile = mc.plan_profile(edit.store)
            revision = edit.revision
        except Exception as exc:
            self._audit("plan_feature_failed", {"key": key, "error": str(exc)})
            return {"success": False, "error": f"Plan Data could not be saved: {exc}"}, 500
        self._audit("plan_feature_set", {"key": key, "on": on, "revision": revision})
        return {"success": True, "key": key, "on": on, "profile": profile, "revision": revision}, 200
