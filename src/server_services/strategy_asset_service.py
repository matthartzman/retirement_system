from __future__ import annotations

"""Feature-owned strategy, asset, insurance, and estate service helpers.

The route layer owns authentication, CSV-write policy checks, request parsing,
and JSON serialization.  This module owns request-independent manipulation of
plan-data CSV sections used by strategy and other-assets workflow pages.
"""

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

AuditFn = Callable[[str, dict[str, Any] | None], None]
PathFn = Callable[[str], Path]
ClientSectionPathFn = Callable[[str, str], Path]
RowsFn = Callable[[Path], list[list[str]]]
WriteRowsFn = Callable[[Path, list[list[str]]], None]
EnsureHeaderFn = Callable[[list[list[str]]], list[list[str]]]
SyncFn = Callable[[], dict[str, Any]]

WITHDRAWAL_ORDER_TYPES: dict[str, list[str]] = {
    "RMD": ["mandatory"],
    "HSA": ["spend_as_needed", "annual_pct", "smooth_window"],
    "IRA_elective": ["gross_up_tax", "net_amount", "skip_until_needed"],
    "Trust": ["with_buffer", "spend_first", "preserve"],
    "Roth": ["tax_free", "last_resort", "preserve_for_legacy"],
    "Home_equity_tap": ["heloc_or_downsize", "heloc", "downsize", "never"],
}

HOUSING_SEED_ROWS: list[list[str]] = [
    ["Cashflow","Mortgage","monthly_payment","","money","Current monthly mortgage payment; stops after last_payment_year"],
    ["Cashflow","Mortgage","balance_as_of_plan_start","","money","Current outstanding mortgage balance"],
    ["Cashflow","Mortgage","interest_rate","","pct","Mortgage interest rate"],
    ["Cashflow","Mortgage","last_payment_date","","date","Final scheduled mortgage payment date"],
    ["Cashflow","Mortgage","last_payment_year","","int","Final scheduled mortgage payment year; model stops mortgage after this year"],
    ["Housing","current_home","homeowners_insurance_annual","","money","Annual homeowners insurance premium"],
    ["Housing","current_home","utilities_annual","","money","Annual utilities (electric, gas, water, internet)"],
    ["Housing","current_home","home_maintenance_annual","","money","Annual home maintenance and repairs"],
    ["Housing","current_home","city_type","suburban","choice","Area type: urban|suburban|rural"],
    ["Housing","current_home","population_size","20000","int","Approximate population of the area"],
    ["Housing","current_home","hoa_annual","","money","Annual HOA fees (if applicable)"],
    ["Housing","next_step_1","type","purchase","choice","purchase|rent"],
    ["Housing","next_step_1","start_year","","int","Year this housing step begins"],
    ["Housing","next_step_1","end_year","","int","Year this housing step ends (0 = indefinite)"],
    ["Housing","next_step_1","state","","text","US state (e.g. IL)"],
    ["Housing","next_step_1","city_type","suburban","choice","Area type: urban|suburban|rural"],
    ["Housing","next_step_1","population_size","20000","int","Approximate population of the area (e.g. 20000)"],
    ["Housing","next_step_1","purchase_price","","money","Purchase price (purchase only)"],
    ["Housing","next_step_1","down_payment","20%","pct","Down payment percentage (purchase only, default 20%)"],
    ["Housing","next_step_1","mortgage_rate_pct","","pct","Mortgage interest rate % (purchase only)"],
    ["Housing","next_step_1","monthly_rent","","money","Monthly rent (rent only)"],
    ["Housing","next_step_1","insurance_annual","","money","Annual insurance (homeowners or renters)"],
    ["Housing","next_step_1","utilities_annual","","money","Annual utilities"],
    ["Housing","next_step_1","maintenance_annual","","money","Annual home maintenance (purchase only)"],
    ["Housing","next_step_1","re_tax_pct","","pct","Real-estate tax as % of value (purchase only)"],
    ["Housing","next_step_1","hoa_pct","","pct","HOA fee as % of value, optional (purchase only)"],
    ["Housing","next_step_2","type","purchase","choice","purchase|rent"],
    ["Housing","next_step_2","start_year","","int","Year this housing step begins"],
    ["Housing","next_step_2","end_year","","int","Year this housing step ends (0 = indefinite)"],
    ["Housing","next_step_2","state","","text","US state (e.g. IL)"],
    ["Housing","next_step_2","city_type","suburban","choice","Area type: urban|suburban|rural"],
    ["Housing","next_step_2","population_size","20000","int","Approximate population of the area (e.g. 20000)"],
    ["Housing","next_step_2","purchase_price","","money","Purchase price (purchase only)"],
    ["Housing","next_step_2","down_payment","20%","pct","Down payment percentage (purchase only, default 20%)"],
    ["Housing","next_step_2","mortgage_rate_pct","","pct","Mortgage interest rate % (purchase only)"],
    ["Housing","next_step_2","monthly_rent","","money","Monthly rent (rent only)"],
    ["Housing","next_step_2","insurance_annual","","money","Annual insurance (homeowners or renters)"],
    ["Housing","next_step_2","utilities_annual","","money","Annual utilities"],
    ["Housing","next_step_2","maintenance_annual","","money","Annual home maintenance (purchase only)"],
    ["Housing","next_step_2","re_tax_pct","","pct","Real-estate tax as % of value (purchase only)"],
    ["Housing","next_step_2","hoa_pct","","pct","HOA fee as % of value, optional (purchase only)"],
]

HEALTHCARE_OOP_SEED_ROWS: list[list[str]] = [
    ["Wellness","Out-of-Pocket","medical_annual","","money","Annual medical out-of-pocket (deductibles, copays, uncovered services)"],
    ["Wellness","Out-of-Pocket","dental_annual","","money","Annual dental out-of-pocket"],
    ["Wellness","Out-of-Pocket","vision_annual","","money","Annual vision out-of-pocket"],
    ["Wellness","Out-of-Pocket","pharmacy_annual","","money","Annual pharmacy/drugs out-of-pocket"],
]

STATE_ESTIMATES = {
    "TX": dict(purchase_price=360000, monthly_rent=1700, insurance_annual=2800, utilities_annual=2800, maintenance_annual=3600, re_tax_pct=0.0181, hoa_pct=0.003),
    "IL": dict(purchase_price=310000, monthly_rent=1600, insurance_annual=1600, utilities_annual=2800, maintenance_annual=3100, re_tax_pct=0.0205, hoa_pct=0.001),
    "FL": dict(purchase_price=420000, monthly_rent=2000, insurance_annual=3500, utilities_annual=2800, maintenance_annual=4200, re_tax_pct=0.0083, hoa_pct=0.003),
    "AZ": dict(purchase_price=385000, monthly_rent=1750, insurance_annual=1600, utilities_annual=2600, maintenance_annual=3850, re_tax_pct=0.0062, hoa_pct=0.002),
}


def housing_state_estimate_payload(data: dict[str, Any]) -> tuple[dict[str, Any], int]:
    state = str((data or {}).get("state", "")).strip().upper()
    housing_type = str((data or {}).get("type", (data or {}).get("housing_type", "purchase")) or "purchase").strip().lower()
    is_rent = housing_type == "rent"
    city_type = str((data or {}).get("city_type", "suburban")).strip().lower()
    try:
        population_size = int((data or {}).get("population_size", 20000) or 20000)
    except (ValueError, TypeError):
        population_size = 20000

    estimate = dict(STATE_ESTIMATES.get(state) or dict(purchase_price=350000, monthly_rent=1600, insurance_annual=1600, utilities_annual=2800, maintenance_annual=3500, re_tax_pct=0.0100, hoa_pct=0.001))
    city_multipliers = {"urban": 1.30, "city": 1.30, "suburban": 1.00, "exurban": 0.85, "rural": 0.75}
    city_mult = city_multipliers.get(city_type, 1.00)
    if population_size > 500_000:
        pop_mult = 1.20
    elif population_size > 200_000:
        pop_mult = 1.12
    elif population_size > 100_000:
        pop_mult = 1.06
    elif population_size > 50_000:
        pop_mult = 1.02
    elif population_size > 20_000:
        pop_mult = 1.00
    elif population_size > 10_000:
        pop_mult = 0.92
    else:
        pop_mult = 0.85

    combined = city_mult * pop_mult
    estimate["purchase_price"] = round(float(estimate["purchase_price"]) * combined / 1000) * 1000
    estimate["monthly_rent"] = round(float(estimate["monthly_rent"]) * combined / 10) * 10
    estimate["maintenance_annual"] = round(float(estimate["purchase_price"]) * 0.01 / 100) * 100
    if is_rent:
        estimate["insurance_annual"] = round(max(180.0, min(450.0, float(estimate.get("insurance_annual", 0) or 0) * 0.15)) / 10) * 10
        estimate["utilities_annual"] = round(float(estimate.get("utilities_annual", 0) or 0) * 0.75 / 100) * 100
        estimate["maintenance_annual"] = 0
    estimate.update({
        "mortgage_rate_pct": estimate.get("mortgage_rate_pct", 0.0685),
        "type": "rent" if is_rent else "purchase",
        "city_type": city_type or "suburban",
        "population_size": population_size,
        "state": state,
        "note": f"Estimated costs for a 3BR/2BA home with at least a 40x40 ft backyard in a {city_type or 'suburban'} area (~{population_size:,} population) in {state}. All values are editable.",
    })
    return {"success": True, "schema": "housing_state_estimate_v1", "estimate": estimate}, 200


@dataclass(frozen=True)
class StrategyAssetServiceContext:
    base_dir: Path
    plan_data_path: PathFn
    client_section_path: ClientSectionPathFn
    reference_file_path: PathFn
    csv_read_rows: RowsFn
    csv_write_rows: WriteRowsFn
    ensure_header: EnsureHeaderFn
    write_client_rows: WriteRowsFn
    read_client_section_rows: Callable[[str, str], list[list[str]]]
    large_discretionary_expenses_from_plan_data: Callable[[], list[dict[str, Any]]]
    normalize_large_discretionary_type: Callable[[str], str]
    replace_large_discretionary_expenses: Callable[[list[dict[str, Any]]], None]
    pre_tax_account_options_from_holdings: Callable[[], list[str]]
    forced_roth_conversions_from_csv_rows: Callable[[list[list[str]]], list[dict[str, Any]]]
    replace_forced_roth_conversions: Callable[[list[dict[str, Any]]], None]
    liquidity_buffers_from_csv_rows: Callable[[list[list[str]]], list[dict[str, Any]]]
    replace_liquidity_buffers: Callable[[list[dict[str, Any]]], None]
    ensure_user_ui_plan_data_rows: Callable[[], None]
    sync_config_backends: SyncFn
    audit: AuditFn | None = None
    travel_extra_types: list[str] | None = None


class StrategyAssetService:
    """Framework-neutral owner for strategy/assets/estate plan-data mutations."""

    def __init__(self, context: StrategyAssetServiceContext):
        self.context = context
        self.base_dir = Path(context.base_dir)

    def _audit(self, event: str, details: dict[str, Any] | None = None) -> None:
        if self.context.audit:
            self.context.audit(event, details or {})

    def _row_key(self, row: list[str]) -> tuple[str, str, str]:
        cols = list(row) + [""] * 3
        return (str(cols[0]).strip(), str(cols[1]).strip(), str(cols[2]).strip())

    def _seed_rows(self, *, file_name: str, seed_rows: list[list[str]], audit_event: str) -> tuple[dict[str, Any], int]:
        path = self.context.plan_data_path(file_name)
        rows = self.context.csv_read_rows(path)
        existing: set[tuple[str, str, str]] = set()
        for r in rows[1:] if rows else []:
            if r and not str(r[0] if r else "").startswith("#"):
                existing.add((r[0] if len(r) > 0 else "", r[1] if len(r) > 1 else "", r[2] if len(r) > 2 else ""))
        added = 0
        for seed_row in seed_rows:
            key = (seed_row[0], seed_row[1], seed_row[2])
            if key not in existing:
                rows.append(seed_row)
                existing.add(key)
                added += 1
        if added > 0:
            self.context.csv_write_rows(path, rows)
            self._audit(audit_event, {"added": added})
        return {"success": True, "seeded": added, "already_present": len(seed_rows) - added}, 200

    def withdrawal_order_payload(self, body: dict[str, Any]) -> tuple[dict[str, Any], int]:
        items = body.get("rows") or []
        if not isinstance(items, list) or not items:
            return {"success": False, "error": "rows must be a non-empty list"}, 400
        cleaned: list[dict[str, Any]] = []
        seen_priorities: set[int] = set()
        for raw in items:
            if not isinstance(raw, dict):
                continue
            try:
                pri = int(raw.get("priority"))
            except Exception:
                continue
            typ = str(raw.get("type") or "").strip()
            if typ not in WITHDRAWAL_ORDER_TYPES:
                return {"success": False, "error": f"Invalid withdrawal type: {typ}"}, 400
            opts = WITHDRAWAL_ORDER_TYPES[typ]
            opt = str(raw.get("option") or opts[0]).strip()
            if opt not in opts:
                opt = opts[0]
            if pri in seen_priorities:
                continue
            seen_priorities.add(pri)
            cleaned.append({"priority": pri, "type": typ, "option": opt})
        if not cleaned:
            return {"success": False, "error": "No valid withdrawal rows supplied"}, 400
        cleaned = sorted(cleaned, key=lambda x: x["priority"])
        for i, item in enumerate(cleaned, start=1):
            item["priority"] = i
        path = self.context.plan_data_path("client_policy.csv")
        file_rows = self.context.csv_read_rows(path)
        priority_indices: list[int] = []
        for idx, row in enumerate(file_rows):
            cols = list(row) + [""] * 6
            if str(cols[0]).strip() == "Withdrawal Policy" and re.match(r"^Priority\s+\d+$", str(cols[1]).strip(), re.I):
                priority_indices.append(idx)
        if not priority_indices:
            insert_at = len(file_rows)
            for idx, row in enumerate(file_rows):
                if row and str(row[0]).strip() == "Withdrawal Policy":
                    insert_at = idx
                    break
            priority_indices = list(range(insert_at, insert_at + len(cleaned)))
            file_rows[insert_at:insert_at] = [["", "", "", "", "", ""] for _ in cleaned]
        while len(priority_indices) < len(cleaned):
            insert_at = priority_indices[-1] + 1 if priority_indices else len(file_rows)
            file_rows.insert(insert_at, ["", "", "", "", "", ""])
            priority_indices.append(insert_at)
        for item, idx in zip(cleaned, priority_indices):
            while len(file_rows[idx]) < 6:
                file_rows[idx].append("")
            file_rows[idx][0] = "Withdrawal Policy"
            file_rows[idx][1] = f"Priority {item['priority']}"
            file_rows[idx][2] = item["type"]
            file_rows[idx][3] = item["option"]
            file_rows[idx][4] = "choice"
            file_rows[idx][5] = "Withdrawal cascade row edited from the User UI compressed withdrawal-order table."
        self.context.write_client_rows(path, file_rows)
        self._audit("withdrawal_order_saved", {"updated": len(cleaned)})
        return {"success": True, "updated": len(cleaned), "sync": self.context.sync_config_backends()}, 200

    def large_discretionary_payload(self) -> tuple[dict[str, Any], int]:
        return {"success": True, "types": self.context.travel_extra_types or [], "events": self.context.large_discretionary_expenses_from_plan_data()}, 200

    def save_large_discretionary_payload(self, body: dict[str, Any]) -> tuple[dict[str, Any], int]:
        events = body.get("events") or []
        if not isinstance(events, list):
            return {"success": False, "error": "events must be a list"}, 400
        clean: list[dict[str, str]] = []
        for ev in events:
            if not isinstance(ev, dict):
                continue
            typ = self.context.normalize_large_discretionary_type(ev.get("type") or "Other")
            amount = str(ev.get("amount") or "").strip()
            year = str(ev.get("year") or "").strip()
            start_year = str(ev.get("start_year") or "").strip()
            end_year = str(ev.get("end_year") or "").strip()
            comment = str(ev.get("comment") or "").strip()
            if not any([typ, amount, year, start_year, end_year, comment]):
                continue
            clean.append({"type": typ, "amount": amount, "year": year, "start_year": start_year, "end_year": end_year, "comment": comment})
        self.context.replace_large_discretionary_expenses(clean)
        self._audit("large_discretionary_expenses_saved", {"count": len(clean)})
        sync_result = None
        if body.get("sync"):
            sync_result = self.context.sync_config_backends()
            self._audit("config_backends_synced", sync_result)
        return {"success": True, "count": len(clean), "sync": sync_result}, 200

    def forced_roth_conversions_payload(self) -> tuple[dict[str, Any], int]:
        rows = self.context.read_client_section_rows("Forced Actions", "client_policy.csv")
        return {"success": True, "accounts": self.context.pre_tax_account_options_from_holdings(), "conversions": self.context.forced_roth_conversions_from_csv_rows(rows)}, 200

    def save_forced_roth_conversions_payload(self, body: dict[str, Any]) -> tuple[dict[str, Any], int]:
        conversions = body.get("conversions") or []
        if not isinstance(conversions, list):
            return {"success": False, "error": "conversions must be a list"}, 400
        valid_accounts = set(self.context.pre_tax_account_options_from_holdings())
        clean: list[dict[str, str]] = []
        for conv in conversions:
            if not isinstance(conv, dict):
                continue
            acct = str(conv.get("source_account") or "").strip()
            year = str(conv.get("year") or "").strip()
            amount = str(conv.get("amount") or "").strip()
            if not any([acct, year, amount]):
                continue
            if valid_accounts and acct not in valid_accounts:
                return {"success": False, "error": f"{acct} is not a recognized pre-tax account"}, 400
            if year and not re.match(r"^(19|20)\d{2}$", year):
                return {"success": False, "error": f"Forced conversion year must be YYYY: {year}"}, 400
            clean.append({"source_account": acct, "year": year, "amount": amount})
        self.context.replace_forced_roth_conversions(clean)
        self._audit("forced_roth_conversions_saved", {"count": len(clean)})
        sync_result = None
        if body.get("sync"):
            sync_result = self.context.sync_config_backends()
            self._audit("config_backends_synced", sync_result)
        return {"success": True, "count": len(clean), "sync": sync_result}, 200

    def liquidity_buffers_payload(self) -> tuple[dict[str, Any], int]:
        rows = self.context.read_client_section_rows("Liquidity Buffer", "client_assets.csv")
        return {"success": True, "buffers": self.context.liquidity_buffers_from_csv_rows(rows)}, 200

    def save_liquidity_buffers_payload(self, body: dict[str, Any]) -> tuple[dict[str, Any], int]:
        buffers = body.get("buffers") or []
        if not isinstance(buffers, list):
            return {"success": False, "error": "buffers must be a list"}, 400
        clean: list[dict[str, str]] = []
        for b in buffers:
            if not isinstance(b, dict):
                continue
            start = str(b.get("start_year") or "").strip()
            end = str(b.get("end_year") or "").strip()
            yrs = str(b.get("years_of_expenses") or "0").strip() or "0"
            reserve_account = str(b.get("reserve_account") or b.get("preserve_account") or "Taxable/Trust").strip() or "Taxable/Trust"
            if not any([start, end, yrs, reserve_account]):
                continue
            clean.append({"start_year": start, "end_year": end, "years_of_expenses": yrs, "reserve_account": reserve_account})
        self.context.replace_liquidity_buffers(clean)
        self._audit("liquidity_buffers_saved", {"count": len(clean)})
        sync_result = None
        if body.get("sync"):
            sync_result = self.context.sync_config_backends()
            self._audit("config_backends_synced", sync_result)
        return {"success": True, "count": len(clean), "sync": sync_result}, 200

    def add_other_asset_payload(self, body: dict[str, Any]) -> tuple[dict[str, Any], int]:
        typ = str(body.get("asset_type") or "Auto").strip() or "Auto"
        path = self.context.client_section_path("Other Assets", "client_assets.csv")
        rows = self.context.ensure_header(self.context.csv_read_rows(path))
        nums: list[int] = []
        for r in rows[1:]:
            if len(r) >= 2 and str(r[0]).strip() == "Other Assets":
                m = re.match(r"Other Asset\s+(\d+)$", str(r[1]).strip(), re.I)
                if m:
                    nums.append(int(m.group(1)))
        n = max(nums) + 1 if nums else 1
        sub = f"Other Asset {n}"
        additions = [
            ["Other Assets", sub, "type", typ, "choice", "Auto | Boat | Start-up Equity | Art | Collectible | Other; choose the broad asset type."],
            ["Other Assets", sub, "name", typ, "text", "User-described asset name."],
            ["Other Assets", sub, "value", "$0", "dollars", "Estimated value as of the as-of date."],
            ["Other Assets", sub, "as_of_date", "", "date", "Date the value estimate was prepared."],
            ["Other Assets", sub, "annual_appreciation_pct", "0.00%", "percent", "Annual appreciation (+) or depreciation (-)."],
            ["Other Assets", sub, "basis", "", "dollars", "Purchase price or tax basis for appreciating assets."],
            ["Other Assets", sub, "sell_date", "", "date", "Optional planned sale date."],
        ]
        insert_at = len(rows)
        for i, r in enumerate(rows[1:], start=1):
            if len(r) >= 1 and str(r[0]).strip() in {"Liquidity Buffer", "HSA Policy", "Education Funding", "Note Receivable", "DAF", "Hybrid LTC", "Equity Compensation"}:
                insert_at = i
                break
        rows[insert_at:insert_at] = additions
        self.context.csv_write_rows(path, rows)
        self._audit("other_asset_item_added", {"section": sub, "asset_type": typ})
        return {"success": True, "section": sub, "message": f"Added {typ} other asset."}, 200

    def delete_other_asset_payload(self, body: dict[str, Any]) -> tuple[dict[str, Any], int]:
        sub = str(body.get("subsection") or "").strip()
        if not re.match(r"^Other Asset\s+\d+$", sub, re.I):
            return {"success": False, "error": "subsection must be an Other Asset N section"}, 400
        path = self.context.client_section_path("Other Assets", "client_assets.csv")
        rows = self.context.ensure_header(self.context.csv_read_rows(path))
        kept = [rows[0]]
        removed = 0
        for r in rows[1:]:
            cols = list(r) + [""] * 6
            if str(cols[0]).strip() == "Other Assets" and str(cols[1]).strip() == sub:
                removed += 1
                continue
            kept.append(r)
        if removed == 0:
            return {"success": False, "error": f"No other asset section named {sub!r} was found."}, 404
        self.context.csv_write_rows(path, kept)
        self._audit("other_asset_item_deleted", {"section": sub, "rows_removed": removed})
        return {"success": True, "section": sub, "rows_removed": removed, "message": f"Deleted {sub}."}, 200

    def add_education_529_payload(self) -> tuple[dict[str, Any], int]:
        path = self.context.client_section_path("Education Funding", "client_assets.csv")
        rows = self.context.ensure_header(self.context.csv_read_rows(path))
        existing = [str(r[1]).strip() for r in rows[1:] if len(r) >= 2 and str(r[0]).strip() == "Education Funding"]
        nums: list[int] = []
        for sub_existing in existing:
            m = re.search(r"(\d+)", sub_existing)
            if m:
                try:
                    nums.append(int(m.group(1)))
                except Exception:
                    pass
        n = (max(nums) + 1) if nums else 1
        sub = f"529 Plan {n}"
        additions = [
            ["Education Funding", sub, "beneficiary", "", "text", "Beneficiary name for this 529 plan."],
            ["Education Funding", sub, "current_balance", "$0", "dollars", "Current 529 plan balance."],
            ["Education Funding", sub, "annual_contribution", "$0", "dollars", "Annual 529 contribution."],
            ["Education Funding", sub, "contribution_start_year", "", "year", "First contribution year."],
            ["Education Funding", sub, "contribution_end_year", "", "year", "Last contribution year."],
            ["Education Funding", sub, "expected_use_year", "", "year", "Expected first use/distribution year."],
        ]
        insert_at = len(rows)
        for i, r in enumerate(rows[1:], start=1):
            if len(r) >= 1 and str(r[0]).strip() in {"Equity Compensation", "Note Receivable", "Hybrid LTC"}:
                insert_at = i
                break
        rows[insert_at:insert_at] = additions
        self.context.csv_write_rows(path, rows)
        self._audit("education_529_section_added", {"section": sub})
        return {"success": True, "section": sub, "message": f"Added {sub}."}, 200

    def estate_state_options_payload(self) -> tuple[dict[str, Any], int]:
        path = self.base_dir / "reference_data" / "state_tax.csv"
        states: list[dict[str, str]] = []
        if path.exists():
            with path.open(newline="", encoding="utf-8-sig") as f:
                for r in csv.DictReader(f):
                    states.append({"state": str(r.get("state") or "").strip(), "estate": str(r.get("estate") or "").strip(), "estate_exempt": str(r.get("estate_exempt") or "").strip(), "source": str(r.get("source") or "").strip()})
        return {"success": True, "states": [s for s in states if s.get("state")]}, 200

    def add_estate_state_payload(self, body: dict[str, Any]) -> tuple[dict[str, Any], int]:
        state = str(body.get("state") or "").strip()
        if not state:
            return {"success": False, "error": "state is required"}, 400
        ref: dict[str, Any] = {}
        path_ref = self.base_dir / "reference_data" / "state_tax.csv"
        if path_ref.exists():
            with path_ref.open(newline="", encoding="utf-8-sig") as f:
                for r in csv.DictReader(f):
                    if str(r.get("state") or "").strip().lower() == state.lower():
                        ref = r
                        state = str(r.get("state") or state).strip()
                        break
        path = self.context.client_section_path("Estate Planning", "client_insurance_estate.csv")
        rows = self.context.ensure_header(self.context.csv_read_rows(path))
        seen = {self._row_key(r) for r in rows[1:]}
        exempt = str(ref.get("estate_exempt") or "0").strip() or "0"
        estate = str(ref.get("estate") or "FALSE").strip() or "FALSE"
        source = str(ref.get("source") or "State estate-tax reference row; verify annually.").strip()
        additions = [
            ["Estate Planning", state, "state_estate_exemption", exempt if exempt.startswith("$") else ("$" + exempt if exempt not in {"0", ""} else "0"), "USD", f"State estate-tax exemption from state_tax.csv; source: {source}"],
            ["Estate Planning", state, "state_estate_tax_applies", estate, "boolean", "Whether state estate tax is currently flagged in reference_data/state_tax.csv."],
            ["Estate Planning", state, "state_estate_rate_note", "verify annually", "text", "State estate-tax rate/structure note; update during annual tax review."],
        ]
        additions = [a for a in additions if self._row_key(a) not in seen]
        if not additions:
            return {"success": True, "state": state, "message": f"{state} already exists in Estate Information."}, 200
        insert_at = len(rows)
        for i, r in enumerate(rows[1:], start=1):
            if len(r) >= 2 and str(r[0]).strip() == "Estate Planning" and str(r[1]).strip() in {"Gifting", "Trust Structure", "Step-Up", "QTIP Trust", "Credit Shelter Trust"}:
                insert_at = i
                break
        rows[insert_at:insert_at] = additions
        self.context.csv_write_rows(path, rows)
        self._audit("estate_state_added", {"state": state})
        return {"success": True, "state": state, "message": f"Added {state} estate rows."}, 200

    def add_trust_account_payload(self, body: dict[str, Any]) -> tuple[dict[str, Any], int]:
        name = str(body.get("account_name") or "").strip()
        typ = str(body.get("trust_type") or "Revocable").strip() or "Revocable"
        if not name:
            return {"success": False, "error": "account_name is required"}, 400
        path = self.context.client_section_path("Estate Planning", "client_insurance_estate.csv")
        rows = self.context.ensure_header(self.context.csv_read_rows(path))
        nums: list[int] = []
        for r in rows[1:]:
            if len(r) >= 2 and str(r[0]).strip() == "Estate Planning" and str(r[1]).strip().startswith("Trust Account"):
                m = re.search(r"(\d+)", str(r[1]))
                if m:
                    nums.append(int(m.group(1)))
        n = max(nums) + 1 if nums else 1
        sub = f"Trust Account {n}"
        additions = [
            ["Estate Planning", sub, "account_name", name, "text", "Trust account name shown in Estate Information."],
            ["Estate Planning", sub, "trust_type", typ, "choice", "Revocable | Irrevocable | Credit Shelter | QTIP | Special Needs | Other; trust classification for estate-planning display."],
            ["Estate Planning", sub, "notes", "", "text", "Optional trust notes."],
        ]
        insert_at = len(rows)
        for i, r in enumerate(rows[1:], start=1):
            if len(r) >= 2 and str(r[0]).strip() == "Estate Planning" and str(r[1]).strip() in {"QTIP Trust", "Credit Shelter Trust", "Gifting"}:
                insert_at = i
                break
        rows[insert_at:insert_at] = additions
        self.context.csv_write_rows(path, rows)
        self._audit("trust_account_added", {"section": sub, "account_name": name, "trust_type": typ})
        return {"success": True, "section": sub, "message": f"Added {name} trust account."}, 200

    def add_insurance_policy_payload(self, body: dict[str, Any]) -> tuple[dict[str, Any], int]:
        typ = str(body.get("policy_type") or "Life").strip() or "Life"
        norm_typ = re.sub(r"[^A-Za-z0-9]+", "_", typ).strip("_") or "Policy"
        path = self.context.client_section_path("Insurance In Force", "client_insurance_estate.csv")
        rows = self.context.ensure_header(self.context.csv_read_rows(path))
        nums: list[int] = []
        for r in rows[1:]:
            if len(r) >= 2 and str(r[0]).strip() == "Insurance In Force" and str(r[1]).strip().lower().startswith(norm_typ.lower()):
                m = re.search(r"(\d+)$", str(r[1]).strip())
                if m:
                    nums.append(int(m.group(1)))
        n = max(nums) + 1 if nums else 1
        sub = f"{norm_typ}_{n}"
        common = [
            ["Insurance In Force", sub, "policy_type", typ, "choice", "Life | Disability | Long-Term Care | Umbrella | Other; policy type shown in the section heading."],
            ["Insurance In Force", sub, "owner", "", "text", "Policy owner."],
            ["Insurance In Force", sub, "insured", "", "text", "Insured person or covered property."],
            ["Insurance In Force", sub, "annual_premium", "$0", "USD", "Annual premium amount; premium-end year fields use YYYY."],
            ["Insurance In Force", sub, "premium_end_year", "", "year", "Last premium year in YYYY format."],
            ["Insurance In Force", sub, "notes", "", "text", "Optional policy notes."],
        ]
        if typ.lower().startswith("life"):
            common[3:3] = [["Insurance In Force", sub, "beneficiary", "", "text", "Primary beneficiary."], ["Insurance In Force", sub, "face_amount", "$0", "USD", "Death benefit / face amount."], ["Insurance In Force", sub, "term_end_year", "", "year", "Term end year in YYYY format."]]
        elif "disability" in typ.lower():
            common[3:3] = [["Insurance In Force", sub, "monthly_benefit", "$0", "USD/mo", "Monthly disability benefit."], ["Insurance In Force", sub, "elimination_days", "", "days", "Elimination period in days."], ["Insurance In Force", sub, "benefit_period_years", "", "years", "Benefit period in years."]]
        else:
            common[3:3] = [["Insurance In Force", sub, "coverage_limit", "$0", "USD", "Coverage limit."], ["Insurance In Force", sub, "deductible", "$0", "USD", "Deductible amount."]]
        rows.extend(common)
        self.context.csv_write_rows(path, rows)
        self._audit("insurance_policy_added", {"section": sub, "policy_type": typ})
        return {"success": True, "section": sub, "message": f"Added {typ} policy {n}."}, 200

    def delete_insurance_policy_payload(self, body: dict[str, Any]) -> tuple[dict[str, Any], int]:
        sub = str(body.get("subsection") or "").strip()
        if not sub:
            return {"success": False, "error": "subsection is required"}, 400
        path = self.context.client_section_path("Insurance In Force", "client_insurance_estate.csv")
        rows = self.context.ensure_header(self.context.csv_read_rows(path))
        kept = [rows[0]]
        removed = 0
        for r in rows[1:]:
            cols = list(r) + [""] * 6
            if str(cols[0]).strip() == "Insurance In Force" and str(cols[1]).strip() == sub:
                removed += 1
                continue
            kept.append(r)
        if removed == 0:
            return {"success": False, "error": f"No insurance policy section named {sub!r} was found."}, 404
        self.context.csv_write_rows(path, kept)
        self._audit("insurance_policy_deleted", {"section": sub, "rows_removed": removed})
        return {"success": True, "section": sub, "rows_removed": removed, "message": f"Deleted insurance policy {sub}."}, 200

    def import_reference_csv_payload(self, *, file_name: str, body: dict[str, Any], audit_event: str) -> tuple[dict[str, Any], int]:
        content = body.get("csv_content", "")
        if not content:
            return {"success": False, "error": "No csv_content in request"}, 400
        path = self.context.reference_file_path(file_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        self._audit(audit_event, {"bytes": len(content), "path": str(path)})
        return {"success": True, "path": str(path), "bytes": len(content)}, 200

    def seed_housing_payload(self) -> tuple[dict[str, Any], int]:
        return self._seed_rows(file_name="client_spending.csv", seed_rows=HOUSING_SEED_ROWS, audit_event="housing_rows_seeded")

    def seed_healthcare_oop_payload(self) -> tuple[dict[str, Any], int]:
        return self._seed_rows(file_name="client_spending.csv", seed_rows=HEALTHCARE_OOP_SEED_ROWS, audit_event="healthcare_oop_rows_seeded")

    def config_sync_payload(self) -> tuple[dict[str, Any], int]:
        try:
            self.context.ensure_user_ui_plan_data_rows()
        except Exception as exc:
            self._audit("config_sync_ui_row_warning", {"error": str(exc)})
        result = self.context.sync_config_backends()
        self._audit("config_backends_synced", result)
        return result, 200 if result.get("success") else 500
