"""Conversion step T8: map an existing plan to a tier (feature-tiers design section 6, T-P8).

Rule (decision 6): the plan gets the smallest tier containing the features it *uses*, and every
other switch is set to that tier's preset. Safeguard (section 6.1): an engine-participating
feature that holds entered data is never switched off; it stays on and the plan reads
"<tier> (customized)".

What counts as "used" (the design leaves it open; decided here):

* a feature that is on (its stored switch, or ``default_on``) **and** holds entered data
  (rows in its declared data sections, ``plan_tier_service.entered_rows``; the YTD feature counts
  its YTD tables; Business Succession its section);
* a plan flag that is on (default off, so the user turned it on: HELOC, hybrid LTC, DAF, QCD).

An old plan stored every module toggle (the CSV template listed them all, default on), so a
stored "on" alone is not use: counting it would put nearly every plan at Expert and defeat the
point of tiers.

Numbers must not move by accident (10.3 verifies), so on top of the design's safeguard:

* an engine-participating feature whose data cannot be counted (no declared data location) is
  treated as holding data: if on, it stays on;
* an engine-participating feature or a plan flag (HELOC, hybrid LTC, DAF, QCD: each flag gates
  engine behaviour, though the catalog does not mark it ``engine_participation``) that is off is
  never switched on by the preset (turning it on could change the projection); it stays off
  (customized).

``map_tier(features)`` is pure (inputs are :class:`FeatureState` values); ``run(store)`` reads
the states from the plan, applies the result through ``module_catalog`` (``PLAN_TIER_ROW`` and
``set_feature``) and stamps ``plan_meta['legacy_conversion.t8']``. A plan that already stores a
tier (the user picked one) is left as it is.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ... import module_catalog as mc

STEP_ID = "T8"
MARKER_KEY = "legacy_conversion.t8"

# Data probes for engine-participating features without declared data sections.
_SECTION_PROBES: dict[str, tuple[str, ...]] = {"business_succession": ("Business Succession",)}
_DATASET_PROBES: dict[str, tuple[str, ...]] = {"spending_tracker_ytd": ("ytd_transactions", "ytd_account_setup")}


@dataclass(frozen=True)
class FeatureState:
    on: bool                 # stored switch (or default_on)
    tier: str                # catalog tier
    engine: bool             # participates in the projection
    entered_rows: int | None  # rows of entered data; None = cannot be counted
    plan_flag: bool = False  # a plan flag (default off)

    @property
    def in_use(self) -> bool:
        return self.on and (self.plan_flag or bool(self.entered_rows))


@dataclass
class TierMapping:
    tier: str
    switches: dict[str, bool]                       # final stored switch per feature
    turn_on: list[str] = field(default_factory=list)
    turn_off: list[str] = field(default_factory=list)
    kept_on: dict[str, str] = field(default_factory=dict)   # key -> reason
    kept_off: dict[str, str] = field(default_factory=dict)  # key -> reason
    in_use: list[str] = field(default_factory=list)

    @property
    def customized(self) -> bool:
        return bool(self.kept_on or self.kept_off)

    def as_dict(self) -> dict[str, Any]:
        return {"tier": self.tier, "customized": self.customized, "in_use": list(self.in_use),
                "turn_on": list(self.turn_on), "turn_off": list(self.turn_off),
                "kept_on": dict(self.kept_on), "kept_off": dict(self.kept_off)}


def smallest_tier(in_use: Mapping[str, str]) -> str:
    """The smallest tier whose rank covers every used feature's tier (``{key: tier}``)."""
    rank = max((mc.TIER_RANK[t] for t in in_use.values()), default=0)
    return mc.TIERS[rank]


def map_tier(features: Mapping[str, FeatureState]) -> TierMapping:
    """Pure: the tier and final switches for features in catalog order."""
    used = {k: s.tier for k, s in features.items() if s.in_use}
    tier = smallest_tier(used)
    rank = mc.TIER_RANK[tier]
    out = TierMapping(tier, {}, in_use=list(used))
    for key, s in features.items():
        want = mc.TIER_RANK[s.tier] <= rank
        final = want
        if s.on and not want and s.engine:
            if s.entered_rows is None:
                out.kept_on[key] = "engine feature, entered data cannot be counted"
                final = True
            elif s.entered_rows > 0:
                out.kept_on[key] = f"engine feature with {s.entered_rows} entered rows"
                final = True
        if not s.on and want and (s.engine or s.plan_flag):
            kind = "plan flag" if s.plan_flag else "engine feature"
            out.kept_off[key] = f"{kind} is off; turning it on would change the projection"
            final = False
        out.switches[key] = final
        if final and not s.on:
            out.turn_on.append(key)
        elif s.on and not final:
            out.turn_off.append(key)
    return out


def _entered(store: Any, key: str) -> int | None:
    from ...server_services.plan_tier_service import entered_rows, entered_value  # noqa: PLC0415

    if key in _SECTION_PROBES:
        return sum(1 for s in _SECTION_PROBES[key] for r in store.rows(s) if entered_value(r["value"]))
    if key in _DATASET_PROBES:
        return sum(store.dataset(n).count() for n in _DATASET_PROBES[key])
    return entered_rows(store, key)


def feature_states(store: Any) -> dict[str, FeatureState]:
    """The plan's switchable features as :class:`FeatureState`, catalog order."""
    out: dict[str, FeatureState] = {}
    for key in mc.switchable_keys():
        m = mc.CATALOG[key]
        out[key] = FeatureState(on=mc.stored_switch(store, key), tier=m.tier, engine=bool(m.engine_participation),
                                entered_rows=_entered(store, key), plan_flag=m.gate_kind == mc.GATE_PLAN_FLAG)
    return out


@dataclass
class T8Report:
    step: str
    skipped: bool
    reason: str = ""
    mapping: TierMapping | None = None

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"step": self.step, "skipped": self.skipped}
        if self.reason:
            out["reason"] = self.reason
        if self.mapping:
            out["mapping"] = self.mapping.as_dict()
        return out


def run(store: Any) -> T8Report:
    if store.get_meta(MARKER_KEY) is not None:
        return T8Report(STEP_ID, skipped=True)
    if mc.plan_profile(store)["tier_stored"]:
        with store.transaction():
            store.set_meta(MARKER_KEY, "tier already chosen")
        return T8Report(STEP_ID, skipped=True, reason="tier already chosen")
    mapping = map_tier(feature_states(store))
    with store.transaction():
        store.set_value(*mc.PLAN_TIER_ROW, mapping.tier, units=mc.PLAN_TIER_UNITS)
        for key in mapping.turn_on:
            mc.set_feature(store, key, True)
        for key in mapping.turn_off:
            mc.set_feature(store, key, False)
        store.set_meta(MARKER_KEY, f"tier={mapping.tier} customized={int(mapping.customized)}")
    return T8Report(STEP_ID, skipped=False, mapping=mapping)
