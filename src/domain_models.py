from __future__ import annotations

"""Typed local-only plan input domain model for v10.

CSV/JSON/YAML remain import/export adapters, but the application layer now has
one canonical, typed representation for user-owned plan inputs.  The model is
intentionally local/single-plan: there are no users, tenants, workspaces, or
hosted identity concepts in this module.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, UTC
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
from typing import Any, Mapping

from .plan_data_migration import migrate_sectioned_data

SectionedData = dict[str, dict[str, dict[str, str]]]


def _s(value: Any) -> str:
    return str(value or "").strip()


def decimal_value(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    try:
        from .money import decimal_from_user_value
    except ImportError:  # pragma: no cover
        from src.money import decimal_from_user_value
    return decimal_from_user_value(value, default)


def money_cents(value: Any) -> int:
    return int((decimal_value(value) * Decimal("100")).quantize(Decimal("1")))


def pct_decimal(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    return decimal_value(value, default)


@dataclass(frozen=True)
class Member:
    id: str
    display_name: str = ""
    birth_year: int | None = None
    owner_role: str = "member"

    def validate(self) -> None:
        if not self.id:
            raise ValueError("Member.id is required")
        if self.birth_year is not None and not (1900 <= int(self.birth_year) <= 2200):
            raise ValueError(f"Invalid birth year for {self.id}: {self.birth_year}")


@dataclass(frozen=True)
class Account:
    id: str
    display_name: str = ""
    owner_id: str = "household"
    account_type: str = "other_asset"
    tax_treatment: str = "unknown"
    current_value_cents: int = 0
    prior_year_end_value_cents: int = 0

    def validate(self) -> None:
        if not self.id:
            raise ValueError("Account.id is required")
        if self.account_type not in {
            "cash_spending", "investment", "annuity", "pension", "social_security",
            "offline_asset", "real_estate", "business_interest", "note_receivable",
            "income_source", "credit_card", "mortgage", "heloc", "loan",
            "other_liability", "ignore", "other_asset",
        }:
            raise ValueError(f"Unsupported account_type for {self.id}: {self.account_type}")


@dataclass(frozen=True)
class IncomeStream:
    id: str
    label: str
    owner_id: str = "household"
    income_type: str = "other_income"
    annual_amount_cents: int = 0
    start_year: int | None = None
    end_year: int | None = None
    inflation_index: str = "none"

    def validate(self) -> None:
        if not self.id:
            raise ValueError("IncomeStream.id is required")
        if self.start_year and self.end_year and self.end_year < self.start_year:
            raise ValueError(f"IncomeStream {self.id} ends before it starts")


@dataclass(frozen=True)
class SpendingPolicy:
    annual_core_spending_cents: int = 0
    core_growth_method: str = "cpi"
    manual_core_growth_rate: Decimal = Decimal("0")
    annual_mortgage_cents: int = 0
    annual_real_estate_tax_cents: int = 0
    real_estate_tax_growth_rate: Decimal = Decimal("0.025")


@dataclass(frozen=True)
class PlanInput:
    schema: str = "plan_input_v10"
    version: str = "v10"
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"))
    members: tuple[Member, ...] = ()
    accounts: tuple[Account, ...] = ()
    income_streams: tuple[IncomeStream, ...] = ()
    spending_policy: SpendingPolicy = field(default_factory=SpendingPolicy)
    sectioned_data: SectionedData = field(default_factory=dict)

    def validate(self) -> None:
        for item in [*self.members, *self.accounts, *self.income_streams]:
            item.validate()
        ids = [m.id for m in self.members]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate member ids")
        account_ids = [a.id for a in self.accounts]
        if len(account_ids) != len(set(account_ids)):
            raise ValueError("Duplicate account ids")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["spending_policy"]["manual_core_growth_rate"] = str(self.spending_policy.manual_core_growth_rate)
        payload["spending_policy"]["real_estate_tax_growth_rate"] = str(self.spending_policy.real_estate_tax_growth_rate)
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)

    def to_sectioned_data(self) -> SectionedData:
        """Return the legacy sectioned shape as an import/export rendering.

        v10 treats this shape as an adapter for the deterministic engine and for
        round-tripping portable files. The typed PlanInput remains canonical.
        """
        data: SectionedData = {s: {ss: dict(vals) for ss, vals in subs.items()} for s, subs in (self.sectioned_data or {}).items()}
        hh = data.setdefault("Household", {}).setdefault("Client", {})
        for member in self.members:
            key = "member_1_name" if member.id in ("husband","member_1") else "member_2_name" if member.id in ("wife","member_2") else f"member_{member.id}_name"
            if member.display_name:
                hh[key] = member.display_name
        sp_core = data.setdefault("Spending", {}).setdefault("Core", {})
        if self.spending_policy.annual_core_spending_cents:
            sp_core.setdefault("annual_spending_base_year", str(self.spending_policy.annual_core_spending_cents / 100))
        sp_core.setdefault("core_spending_growth_mode", self.spending_policy.core_growth_method)
        sp_core.setdefault("manual_core_spending_increase_pct", str(self.spending_policy.manual_core_growth_rate))
        mortgage = data.setdefault("Cashflow", {}).setdefault("Mortgage", {})
        mortgage.setdefault("annual_mortgage_payment", str(self.spending_policy.annual_mortgage_cents / 100))
        mortgage.setdefault("annual_real_estate_taxes", str(self.spending_policy.annual_real_estate_tax_cents / 100))
        mortgage.setdefault("real_estate_tax_annual_adjustment_pct", str(self.spending_policy.real_estate_tax_growth_rate))
        ytd = data.setdefault("YTD Account Setup", {})
        for account in self.accounts:
            row = ytd.setdefault(account.id, {})
            row["Account Type"] = account.account_type
            row.setdefault("Current Value", str(account.current_value_cents / 100))
            row.setdefault("Prior Year End Balance", str(account.prior_year_end_value_cents / 100))
        inc = data.setdefault("Income", {})
        for stream in self.income_streams:
            row = inc.setdefault(stream.owner_id or "household", {})
            row[stream.label or stream.id] = str(stream.annual_amount_cents / 100)
        return data


def _lookup(data: Mapping[str, Any], section: str, subsection: str, label: str, default: str = "") -> str:
    try:
        return _s(data.get(section, {}).get(subsection, {}).get(label, default))
    except Exception:
        return default


def _infer_owner(account_id: str) -> str:
    low = account_id.lower()
    if (low.startswith("h_") or low.startswith("husband") or "_h_" in low or
            low.startswith("member_1") or "_member_1" in low):
        return "husband"
    if (low.startswith("w_") or low.startswith("wife") or "_w_" in low or
            low.startswith("member_2") or "_member_2" in low):
        return "wife"
    return "household"


def _normalize_account_type(value: str) -> str:
    low = value.strip().lower().replace("/", "_").replace(" ", "_")
    mapping = {
        "cash": "cash_spending", "cash_spending": "cash_spending", "cash_/_spending": "cash_spending",
        "investment": "investment", "annuity": "annuity", "pension": "pension",
        "social_security": "social_security", "offline_asset": "offline_asset",
        "real_estate": "real_estate", "business_interest": "business_interest",
        "note_receivable": "note_receivable", "income_source": "income_source",
        "credit_card": "credit_card", "mortgage": "mortgage", "heloc": "heloc",
        "loan": "loan", "other_liability": "other_liability", "liability": "other_liability",
        "ignore": "ignore",
    }
    return mapping.get(low, "other_asset")


def plan_input_from_sectioned_data(data: SectionedData) -> PlanInput:
    """Build a typed local PlanInput from the existing sectioned Plan Data shape."""
    migrate_sectioned_data(data)  # upgrade any legacy husband/wife shapes first
    h_name = _lookup(data, "Household", "Client", "member_1_name",
                     _lookup(data, "Household", "Client", "h_name", "Member 1"))
    w_name = _lookup(data, "Household", "Client", "member_2_name",
                     _lookup(data, "Household", "Client", "w_name", "Member 2"))
    members = (
        Member(id="member_1", display_name=h_name or "Member 1"),
        Member(id="member_2", display_name=w_name or "Member 2"),
    )

    accounts: list[Account] = []
    assets = data.get("Assets", {}) if isinstance(data, Mapping) else {}
    for subsection, labels in assets.items():
        if not isinstance(labels, Mapping):
            continue
        for label, value in labels.items():
            label_s = _s(label)
            if not label_s:
                continue
            if label_s.startswith("balance") or label_s.startswith("value") or "balance" in label_s.lower():
                account_id = _s(subsection) or label_s
                accounts.append(Account(
                    id=account_id,
                    display_name=account_id.replace("_", " ").title(),
                    owner_id=_infer_owner(account_id),
                    account_type="investment" if any(t in account_id.lower() for t in ("ira", "401", "brokerage", "roth")) else "other_asset",
                    current_value_cents=money_cents(value),
                ))

    ytd_setup = data.get("YTD Account Setup", {}) if isinstance(data, Mapping) else {}
    for subsection, labels in ytd_setup.items():
        if not isinstance(labels, Mapping):
            continue
        account_id = _s(subsection)
        if not account_id:
            continue
        typ = _normalize_account_type(_s(labels.get("Account Type") or labels.get("Role") or labels.get("account_type")))
        existing = next((a for a in accounts if a.id == account_id), None)
        if not existing:
            accounts.append(Account(
                id=account_id,
                display_name=account_id,
                owner_id=_infer_owner(account_id),
                account_type=typ,
                current_value_cents=money_cents(labels.get("Current Value")),
                prior_year_end_value_cents=money_cents(labels.get("Prior Year End Balance")),
            ))

    income_streams: list[IncomeStream] = []
    income = data.get("Income", {}) if isinstance(data, Mapping) else {}
    for subsection, labels in income.items():
        if not isinstance(labels, Mapping):
            continue
        for label, value in labels.items():
            if not _s(label):
                continue
            if any(word in label.lower() for word in ("salary", "paycheck", "income", "pension", "social security", "annuity")):
                sid = f"{_s(subsection) or 'income'}:{_s(label)}"
                income_streams.append(IncomeStream(id=sid, label=_s(label), owner_id=_infer_owner(sid), annual_amount_cents=money_cents(value)))

    spending_policy = SpendingPolicy(
        annual_core_spending_cents=money_cents(_lookup(data, "Spending", "Core", "annual_spending_base_year", "0")),
        core_growth_method=_lookup(data, "Spending", "Core", "core_spending_growth_mode", "cpi").lower() or "cpi",
        manual_core_growth_rate=pct_decimal(_lookup(data, "Spending", "Core", "manual_core_spending_increase_pct", "0")),
        annual_mortgage_cents=money_cents(_lookup(data, "Cashflow", "Mortgage", "annual_mortgage_payment", "0")),
        annual_real_estate_tax_cents=money_cents(_lookup(data, "Cashflow", "Mortgage", "annual_real_estate_taxes", "0")),
        real_estate_tax_growth_rate=pct_decimal(_lookup(data, "Cashflow", "Mortgage", "real_estate_tax_annual_adjustment_pct", "2.5%"), Decimal("0.025")),
    )
    plan = PlanInput(members=members, accounts=tuple(accounts), income_streams=tuple(income_streams), spending_policy=spending_policy, sectioned_data={s: {ss: dict(vals) for ss, vals in subs.items()} for s, subs in data.items()})
    plan.validate()
    return plan


def plan_input_from_json(path: str | Path) -> PlanInput:
    obj = json.loads(Path(path).read_text(encoding="utf-8"))
    if obj.get("schema") != "plan_input_v10":
        raise ValueError("Unsupported PlanInput schema")
    members = tuple(Member(**m) for m in obj.get("members", []))
    accounts = tuple(Account(**a) for a in obj.get("accounts", []))
    streams = tuple(IncomeStream(**x) for x in obj.get("income_streams", []))
    sp_raw = obj.get("spending_policy", {}) or {}
    sp = SpendingPolicy(
        annual_core_spending_cents=int(sp_raw.get("annual_core_spending_cents", 0) or 0),
        core_growth_method=str(sp_raw.get("core_growth_method", "cpi")),
        manual_core_growth_rate=Decimal(str(sp_raw.get("manual_core_growth_rate", "0"))),
        annual_mortgage_cents=int(sp_raw.get("annual_mortgage_cents", 0) or 0),
        annual_real_estate_tax_cents=int(sp_raw.get("annual_real_estate_tax_cents", 0) or 0),
        real_estate_tax_growth_rate=Decimal(str(sp_raw.get("real_estate_tax_growth_rate", "0.025"))),
    )
    plan = PlanInput(
        schema=str(obj.get("schema", "plan_input_v10")),
        version=str(obj.get("version", "v10")),
        created_at=str(obj.get("created_at", "")) or datetime.now(UTC).isoformat(),
        members=members,
        accounts=accounts,
        income_streams=streams,
        spending_policy=sp,
        sectioned_data=obj.get("sectioned_data", {}) or {},
    )
    plan.validate()
    return plan


def plan_input_from_dict(obj: Mapping[str, Any]) -> PlanInput:
    """Create a PlanInput from its canonical JSON/dict payload."""
    tmp = Path(".plan_input_from_dict_tmp.json")
    tmp.write_text(json.dumps(dict(obj), default=str), encoding="utf-8")
    try:
        return plan_input_from_json(tmp)
    finally:
        try:
            tmp.unlink()
        except Exception:
            pass

