"""Limitation and preflight notices N1-N7 (WI-010a, WI-010).

Each notice tells the user about a known limitation of the model. A notice
changes no calculation: it is only shown, in preflight, on the Tax Assumptions
page, in the workbook and in the advisor report, for plans where its display
condition holds.

The wording is the owner-approved text recorded in
``documentation/archive/reports/SYSTEM_REVIEW_2026-10-19_WAVE1_NOTICE_WORDING.md``
(a test compares the two). Each notice carries its removal triggers as data:
when every ``remove`` trigger is marked ``shipped`` the notice is retired and
is never returned, so flipping the flag is the whole removal step.

N7 is the per-family reference-data status list; its status strings come from
the dataset's own ``status`` vocabulary (never "verified" unless the rows say so).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Sequence

SEVERITY_WARNING = "warning"
SEVERITY_INFO = "info"

# Dataset status vocabulary for N7. The reference tables use "verified",
# "assumption", "legislated" and "historical"; "unreviewed" is used when a
# family has no dataset rows (or its review flag says review is required).
STATUS_VERIFIED = "verified"
STATUS_ASSUMPTION = "assumption"
STATUS_UNREVIEWED = "unreviewed"

EARLY_DISTRIBUTION_AGE = 59.5
DEFAULT_FRA = 67.0


@dataclass(frozen=True)
class RemovalTrigger:
    """What retires (or changes) a notice. ``effect`` is ``remove`` (retires the
    notice when shipped), ``update_wording`` or ``update_status`` (the notice
    stays; its text or data changes)."""
    work_item: str
    description: str
    effect: str = "remove"
    shipped: bool = False


@dataclass(frozen=True)
class Notice:
    id: str
    finding: str
    severity: str
    text: str
    shown_when: str
    triggers: tuple[RemovalTrigger, ...]

    @property
    def retired(self) -> bool:
        removers = [t for t in self.triggers if t.effect == "remove"]
        return bool(removers) and all(t.shipped for t in removers)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "finding": self.finding, "severity": self.severity,
            "text": self.text, "shown_when": self.shown_when,
            "removal_triggers": [
                {"work_item": t.work_item, "description": t.description,
                 "effect": t.effect, "shipped": t.shipped} for t in self.triggers],
        }


NOTICES: tuple[Notice, ...] = (
    Notice(
        "N1", "FIN-001", SEVERITY_WARNING,
        "Gains from selling taxable investments are not yet counted as income in the Medicare (IRMAA), "
        "net investment income tax, ACA subsidy and Social Security taxation calculations. Federal income "
        "tax on those gains is calculated. Results may be optimistic for plans that fund spending from "
        "appreciated taxable holdings.",
        "Plan sells taxable holdings at a gain",
        (RemovalTrigger("WI-024", "Phase 1 (IRMAA MAGI) ships: update the wording", "update_wording", shipped=True),
         RemovalTrigger("WI-024", "Phase 2 (NIIT, ACA MAGI, Social Security taxation) ships: remove", shipped=True)),
    ),
    Notice(
        "N2", "FIN-003", SEVERITY_INFO,
        "Qualified dividends are currently taxed at ordinary rates instead of the lower 0%, 15% and 20% "
        "rates. Estimated federal tax is overstated (conservative) for plans with taxable stock holdings.",
        "Plan has taxable equity holdings",
        (RemovalTrigger("WI-023", "Qualified-dividend stacking fix ships", shipped=True),),
    ),
    Notice(
        "N3", "FIN-004", SEVERITY_WARNING,
        "Withdrawals from IRAs and 401(k)s before age 59½ may carry a 10% additional tax unless an "
        "exception applies. This version does not calculate that tax, so plans that draw from pre-tax "
        "accounts before 59½ may look more sustainable than they are.",
        "Plan has pre-tax draws before age 59½",
        (RemovalTrigger("WI-002a", "Early-withdrawal tax is modeled (WI-002(a) decided and implemented)"),),
    ),
    Notice(
        "N4", "FIN-010", SEVERITY_INFO,
        "When the spouse who does not own a joint taxable account dies first, the survivor's step-up in "
        "cost basis is not modeled. Later capital gains tax may be overstated in that case.",
        "Plan has joint taxable accounts",
        (RemovalTrigger("WI-025", "Symmetric survivor step-up fix ships", shipped=True),),
    ),
    Notice(
        "N5", "FIN-007", SEVERITY_WARNING,
        "The Social Security earnings test is not modeled. If you claim before full retirement age while "
        "still earning wages, some benefits may be temporarily withheld, and this plan does not reflect that.",
        "Claim age is before full retirement age and wages continue",
        (RemovalTrigger("WI-040", "Earnings test is modeled (WI-002(b) decided; WI-040 implemented)", shipped=True),),
    ),
    Notice(
        "N6", "FIN-009", SEVERITY_WARNING,
        "The estate tax calculation uses a default exemption sized for a married couple using portability. "
        "For a one-person household the exemption is lower, so estimated federal estate tax may be understated.",
        "Household has one member and the federal exemption is above the per-person amount",
        (RemovalTrigger("WI-027", "Remove once saved plans no longer carry an explicit couple-sized exemption (a blank exemption is already derived from the household)"),),
    ),
    Notice(
        "N7", "FIN-005, FIN-006", SEVERITY_INFO,
        "Reference data status by family: verified, assumption or unreviewed.",
        "Always (data status)",
        (RemovalTrigger("WI-003", "A data family is updated and verified: its status changes", "update_status"),
         RemovalTrigger("WI-027", "AMT, state, estate, Part D and mortality values updated", "update_status")),
    ),
)

NOTICE_BY_ID = {n.id: n for n in NOTICES}


# ── Display conditions (pure functions of the parsed config and projection rows) ──

def _f(v: Any) -> float:
    try:
        return float(v or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _members(c: Mapping[str, Any]) -> int:
    members = c.get("members")
    if isinstance(members, (list, tuple)) and members:
        return len(members)
    return int(_f(c.get("household_size")))


def _owner_prefix(idx: Any) -> str:
    return "h" if int(_f(idx)) == 0 else "w"


def _sells_taxable_at_gain(c: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> bool:
    return any(_f(r.get("ltcg_gain")) > 0 for r in rows)


def _taxable_equity(c: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> bool:
    income = c.get("account_taxable_income_assumptions") or {}
    for acct in c.get("account_registry") or []:
        if acct.get("tax") != "taxable" or _f(acct.get("balance")) <= 0:
            continue
        if _f((income.get(acct.get("id")) or {}).get("qualified_yield")) > 0:
            return True
    return False


def _pretax_draw_before_59_5(c: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> bool:
    owners = {a["id"]: _owner_prefix(a.get("owner_idx")) for a in c.get("account_registry") or []
              if a.get("tax") == "pre_tax"}
    for r in rows:
        draws = r.get("_account_withdrawals") or {}
        for acct_id, prefix in owners.items():
            age = r.get(f"{prefix}_age")
            if age is None or not r.get(f"{prefix}_alive", True):
                continue
            if _f(age) < EARLY_DISTRIBUTION_AGE and _f(draws.get(acct_id)) > 0:
                return True
    return False


def _joint_taxable(c: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> bool:
    if _members(c) < 2:
        return False
    from .planning_engines import _account_titling
    for acct in c.get("account_registry") or []:
        if acct.get("tax") != "taxable" or _f(acct.get("balance")) <= 0:
            continue
        titling = str(_account_titling(c, acct["id"]).get("titling") or "").strip().upper()
        if titling in {"JTWROS", "TENANTS_IN_COMMON"}:
            return True
    return False


def _early_claim_with_wages(c: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> bool:
    for prefix in ("h", "w"):
        claim = c.get(f"{prefix}_ss_claim_age_precise") or c.get(f"{prefix}_ss_claim_age")
        if claim is None:
            continue
        fra = _f(c.get(f"{prefix}_fra_age")) or DEFAULT_FRA
        if _f(claim) >= fra:
            continue
        for r in rows:
            age = r.get(f"{prefix}_age")
            if age is None or not r.get(f"{prefix}_alive", True):
                continue
            if _f(claim) <= _f(age) < fra and _f(r.get("earned")) > 0:
                return True
    return False


def _one_member(c: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> bool:
    return _members(c) == 1


def _one_member_with_couple_exemption(c: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> bool:
    """N6 (WI-027): a one-person household whose federal exemption is above the per-person
    basic exclusion. A blank exemption is now derived from the household, so only an
    explicit couple-sized value triggers it."""
    from .tax_law import default_tax_law_dataset
    per_person = default_tax_law_dataset().latest_value("federal_estate_basic_exclusion").value
    return _members(c) == 1 and _f(c.get("fed_exempt")) > per_person


CONDITIONS: dict[str, Callable[[Mapping[str, Any], Sequence[Mapping[str, Any]]], bool]] = {
    "N1": _sells_taxable_at_gain,
    "N2": _taxable_equity,
    "N3": _pretax_draw_before_59_5,
    "N4": _joint_taxable,
    "N5": _early_claim_with_wages,
    "N6": _one_member_with_couple_exemption,
    "N7": lambda c, rows: True,
}


# ── N7: reference-data status per family ──

DATA_FAMILIES = ("Federal tables", "AMT", "State income tax", "State estate tax", "Mortality", "Part D")

_FEDERAL_VALUE_NAMES = {"standard_deduction", "standard_deduction_over65", "niit_threshold",
                        "ltcg_0pct_top", "ltcg_15pct_top", "ss_wage_base"}
_PART_D_NAMES = {"part_d_base_premium_monthly"}


def _roll_up(statuses: Iterable[str]) -> str:
    """A family reads verified only when every row in force is verified or legislated."""
    found = [s for s in statuses if s != "historical"]
    if not found:
        return STATUS_UNREVIEWED
    if all(s in ("verified", "legislated") for s in found):
        return STATUS_VERIFIED
    return STATUS_ASSUMPTION


def _rows_in_force(ds: Any, year: int, *, values: Callable[[str], bool], brackets: bool) -> list[str]:
    latest: dict[tuple, Any] = {}
    for v in ds.values:
        if values(v.name) and v.effective_year <= year and (v.expires_year is None or year <= v.expires_year):
            key = ("v", v.name, v.jurisdiction, v.filing_status)
            if key not in latest or v.effective_year >= latest[key].effective_year:
                latest[key] = v
    if brackets:
        for b in ds.brackets:
            if b.effective_year <= year and (b.expires_year is None or year <= b.expires_year):
                key = ("b", b.bracket_type, b.jurisdiction, b.filing_status, b.lower)
                if key not in latest or b.effective_year >= latest[key].effective_year:
                    latest[key] = b
    return [str(r.status) for r in latest.values()]


def data_family_statuses(year: int | None = None) -> list[dict[str, str]]:
    """Per-family status list for N7, taken from the reference dataset's status vocabulary."""
    from . import taxes as _taxes
    from .stores.ref_getters.tax_law import tax_law_dataset
    from .stores.ref_getters.tax_update_dashboard import tax_update_dashboard

    year = int(year or _taxes.TAX_REFERENCE_YEAR)
    ds = tax_law_dataset()
    federal = _roll_up(_rows_in_force(ds, year, values=lambda n: n in _FEDERAL_VALUE_NAMES, brackets=True))
    part_d = _roll_up(_rows_in_force(
        ds, year, values=lambda n: n in _PART_D_NAMES or (n.startswith("irmaa_tier") and "_part_d_" in n),
        brackets=False))
    # AMT rows are dated dataset rows since WI-027; their own status decides the family.
    amt_rows = _rows_in_force(ds, year, values=lambda n: "amt" in n.lower(), brackets=False)
    amt = _roll_up(amt_rows)
    # State tables carry no per-row status; the tax-update dashboard flags them for review.
    try:
        dash = {r["constant"]: r for r in tax_update_dashboard()}
    except Exception:
        dash = {}
    state_row = dash.get("state_tax")
    state = STATUS_UNREVIEWED
    if state_row is not None and str(state_row.get("status", "")).startswith("CURRENT") and not state_row.get("blocking"):
        # Within review policy is not "verified": the state rows carry no per-row verified status.
        state = STATUS_ASSUMPTION
    # The mortality table is SSA data interpolated/extrapolated by the project: an assumption.
    mortality = STATUS_ASSUMPTION
    source = {
        "Federal tables": f"tax_law dataset {ds.version}, rows in force for {year}",
        "AMT": f"tax_law dataset {ds.version}, AMT rows in force for {year}",
        "State income tax": "state_tax table; tax-update dashboard review flag",
        "State estate tax": "state_tax table; tax-update dashboard review flag",
        "Mortality": "SSA Actuarial Study No. 124 (interpolated/extrapolated)",
        "Part D": f"tax_law dataset {ds.version}, Part D rows in force for {year}",
    }
    status = {"Federal tables": federal, "AMT": amt, "State income tax": state,
              "State estate tax": state, "Mortality": mortality, "Part D": part_d}
    return [{"family": f, "status": status[f], "source": source[f]} for f in DATA_FAMILIES]


# ── Evaluation ──

def active_notices() -> list[Notice]:
    return [n for n in NOTICES if not n.retired]


def evaluate_notices(config: Mapping[str, Any], rows: Sequence[Mapping[str, Any]] = ()) -> list[dict[str, Any]]:
    """The notices whose display condition holds for this plan, as plain dicts."""
    out: list[dict[str, Any]] = []
    for n in active_notices():
        if CONDITIONS[n.id](config, rows):
            rec = n.as_dict()
            if n.id == "N7":
                rec["families"] = data_family_statuses()
            out.append(rec)
    return out


def display_lines(notices: Iterable[Mapping[str, Any]]) -> list[tuple[str, str, str]]:
    """(id, severity, text) lines for text surfaces (workbook, report); N7 expands per family."""
    lines: list[tuple[str, str, str]] = []
    for n in notices:
        # A stored notice is shown only while its registry entry is still active.
        reg = NOTICE_BY_ID.get(str(n.get("id")))
        if reg is None or reg.retired:
            continue
        lines.append((reg.id, reg.severity, reg.text))
        for fam in n.get("families") or []:
            lines.append((reg.id, reg.severity, f"{fam['family']}: {fam['status']} ({fam['source']})"))
    return lines


def shown_notices(stored: Iterable[Mapping[str, Any]] | None) -> list[dict[str, Any]]:
    """Filter stored (build-time) notices through the registry so a retired notice never shows."""
    out = []
    for n in stored or []:
        reg = NOTICE_BY_ID.get(str(n.get("id")))
        if reg is not None and not reg.retired:
            out.append({**reg.as_dict(), **({"families": n["families"]} if n.get("families") else {})})
    return out


def with_always_on(stored: Iterable[Mapping[str, Any]] | None) -> list[dict[str, Any]]:
    """Stored notices, plus N7 (always shown) when no build has stored it yet."""
    notices = shown_notices(stored)
    if not any(n["id"] == "N7" for n in notices) and not NOTICE_BY_ID["N7"].retired:
        n7 = NOTICE_BY_ID["N7"].as_dict()
        n7["families"] = data_family_statuses()
        notices.append(n7)
    return notices
