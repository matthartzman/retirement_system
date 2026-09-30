from __future__ import annotations

"""Resolver for plan-level tax assumptions ("Auto" model value vs. override).

Each lever has a model value (a documented default, or derived from the plan)
and an optional plan override. Only overrides are stored in the plan: a blank
or absent field means Auto. ``resolve_tax_assumptions`` is the single place
that turns the raw plan fields into the effective values the engine reads, so
the CSV and JSON build paths cannot drift apart.

The model value is never a silent engine fallback: a lever whose model value
cannot be derived raises ``TaxAssumptionError`` so the build fails loudly,
matching ``residence_state`` handling.
"""

import re
from dataclasses import dataclass
from typing import Any, Callable, Mapping

# A rate override further than this from the model value gets a warning (never
# a block); the plan is advisor-edited, so unusual values are allowed.
RATE_WARN_DISTANCE = 0.02


class TaxAssumptionError(ValueError):
    """A tax lever has no usable model value."""


@dataclass(frozen=True)
class TaxLever:
    key: str
    label: str
    engine_key: str
    minimum: float
    maximum: float
    model_value: Callable[[Mapping[str, Any]], tuple[float, str]]
    help: str = ""


@dataclass(frozen=True)
class ResolvedLever:
    key: str
    label: str
    value: float
    source: str  # "override" | "model"
    model_value: float
    basis: str
    matches_model: bool
    warning: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key, "label": self.label, "value": self.value,
            "source": self.source, "model_value": self.model_value,
            "basis": self.basis, "matches_model": self.matches_model,
            "warning": self.warning,
        }


def _bracket_inflator_model(_ctx: Mapping[str, Any]) -> tuple[float, str]:
    return 0.02, "Model default: 2.00%/yr bracket indexation"


def _ss_fraction_model(_ctx: Mapping[str, Any]) -> tuple[float, str]:
    return 0.85, "Statutory maximum taxable share of Social Security (IRC section 86)"


def _state_rate_model(ctx: Mapping[str, Any]) -> tuple[float, str]:
    state = str(ctx.get("state", "") or "")
    rules = (ctx.get("state_rules") or {}).get(state)
    if not rules:
        raise TaxAssumptionError(
            f"No state tax rules for residence state {state!r}; cannot derive a model state rate.")
    rate = float(rules.get("rate", 0.0) or 0.0)
    kind = str(rules.get("type", "flat") or "flat")
    note = "flat rate" if kind != "graduated" else "headline rate; bracketed schedule applies in Auto"
    return rate, f"reference_data/state_tax.csv for {state} ({note})"


LEVERS: tuple[TaxLever, ...] = (
    TaxLever("fed_tax_bracket_inflator", "Bracket inflator", "brk_inf", 0.0, 0.05,
             _bracket_inflator_model, "Annual indexation of federal brackets and deductions."),
    TaxLever("social_security_taxable_fraction", "Social Security taxable fraction", "ss_taxable",
             0.0, 1.0, _ss_fraction_model, "Share of Social Security benefits included in AGI."),
    TaxLever("state_income_tax_rate", "State income-tax rate", "state_rate_override",
             0.0, 0.15, _state_rate_model,
             "Blank = use the state's own rules. A value taxes state income at this flat rate."),
)

LEVER_BY_KEY = {lv.key: lv for lv in LEVERS}


_NUMERIC_TEXT = re.compile(r"^\s*[-+]?(\d+(\.\d*)?|\.\d+)\s*%?\s*$")


def _is_numeric_text(raw: Any) -> bool:
    return isinstance(raw, (int, float)) or bool(_NUMERIC_TEXT.match(str(raw)))


def _is_blank(raw: Any) -> bool:
    return raw is None or str(raw).strip() == ""


def resolve_tax_assumptions(raw: Mapping[str, Any], parse: Callable[[Any, Any], Any],
                            *, state: str = "",
                            state_rules: Mapping[str, Mapping[str, Any]] | None = None,
                            ) -> dict[str, ResolvedLever]:
    """Resolve every lever. ``raw`` maps lever key -> stored field text/number
    (missing or blank = Auto). ``parse(raw, default)`` is the caller's number
    parser (returns ``default`` when ``raw`` is unparseable)."""
    ctx = {"state": state, "state_rules": state_rules or {}}
    out: dict[str, ResolvedLever] = {}
    for lever in LEVERS:
        model, basis = lever.model_value(ctx)
        text = raw.get(lever.key)
        if _is_blank(text):
            out[lever.key] = ResolvedLever(lever.key, lever.label, model, "model", model, basis, True)
            continue
        value = parse(text, None) if _is_numeric_text(text) else None
        if value is None:
            out[lever.key] = ResolvedLever(
                lever.key, lever.label, model, "model", model, basis, True,
                warning=f"Override {text!r} is not a number; using the model value.")
            continue
        value = float(value)
        if not (lever.minimum <= value <= lever.maximum):
            out[lever.key] = ResolvedLever(
                lever.key, lever.label, model, "model", model, basis, True,
                warning=(f"Override {value:g} is outside {lever.minimum:g} to {lever.maximum:g}; "
                         "using the model value."))
            continue
        warning = ""
        if abs(value - model) > RATE_WARN_DISTANCE:
            warning = (f"Override {value:.2%} differs from the model value {model:.2%} "
                       f"by more than {RATE_WARN_DISTANCE:.0%}.")
        out[lever.key] = ResolvedLever(
            lever.key, lever.label, value, "override", model, basis,
            abs(value - model) < 1e-12, warning)
    return out


def apply_to_config(c: dict, resolved: Mapping[str, ResolvedLever]) -> None:
    """Write effective values into the engine config and publish the report
    payload ``c['tax_assumptions_effective']``."""
    for key, res in resolved.items():
        engine_key = LEVER_BY_KEY[key].engine_key
        if engine_key == "state_rate_override":
            # Auto keeps the state's own (possibly bracketed) schedule.
            c[engine_key] = res.value if res.source == "override" else None
        else:
            c[engine_key] = res.value
    c["tax_assumptions_effective"] = {k: r.as_dict() for k, r in resolved.items()}


def law_reference_table(year: int | None = None) -> dict[str, Any]:
    """Read-only tier-2 view: the dated tax-law values the engine uses for
    ``year`` (default: the tax reference year). Law is data, not an
    assumption, so it is shown but never overridden here."""
    from . import taxes as _td
    from .tax_law import load_tax_law_dataset

    year = int(year or _td.TAX_REFERENCE_YEAR)
    ds = load_tax_law_dataset()
    tables = ds.as_engine_tables(year)
    return {
        "year": year,
        "dataset_version": ds.version,
        "source": ds.generated_from,
        "standard_deduction": tables.get("standard_deduction", {}),
        "niit_threshold": tables.get("niit_threshold", {}),
        "ltcg_brackets": tables.get("ltcg_brackets", {}),
        "salt_cap": tables.get("salt_cap"),
        "ordinary_brackets": {
            status: [{"lower": lo, "upper": None if hi == float("inf") else hi, "rate": rate}
                     for lo, hi, rate in rows]
            for status, rows in (tables.get("ordinary_brackets") or {}).items()
        },
    }
