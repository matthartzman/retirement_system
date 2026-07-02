from __future__ import annotations

"""YTD spending, income, and growth tracking helpers.

YTD tracking still uses canonical CSV adapter files inside the workspace so the
projection/reporting code can stay simple, but the server mirrors those files
into the local SQLite client_files table. Normal UI saves therefore persist in
the local database first, while CSV remains a compatibility/import-export
working copy.

- ytd_transactions.csv
- ytd_account_setup.csv
- ytd_import_history.csv
"""

import csv
import hashlib
import io
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

TRANSACTION_COLUMNS = [
    "Date",
    "Merchant",
    "Category",
    "Account",
    "Original Statement",
    "Notes",
    "Amount",
    "Tags",
    "Owner",
]

ACCOUNT_SETUP_COLUMNS = [
    "Account",
    "Role",
    "Mapped Investment Account",
    "Prior Year End Date",
    "Prior Year End Balance",
    "Current Value",
    "Current Balance",
    "Notes",
]

IMPORT_HISTORY_COLUMNS = [
    "Loaded At",
    "Mode",
    "Rows Received",
    "Rows Added",
    "Rows Skipped",
    "Earliest Transaction Date",
    "Latest Transaction Date",
    "Notes",
]

ROLE_OPTIONS = [
    "Cash / spending",
    "Investment",
    "Annuity/Pension",
    "Annuity",
    "Pension",
    "Social Security",
    "Offline asset",
    "Real estate",
    "Business interest",
    "Note receivable",
    "Income source",
    "Credit card",
    "Mortgage",
    "HELOC",
    "Loan",
    "Other liability",
    "Ignore",
]

# Roles that contribute to YTD growth and net worth calculations.
# Growth = current value − prior year-end balance, summed across these roles only.
# Investment current value comes from mapped client_holdings.csv accounts.
# Annuity/Pension current value comes from the manually entered "Current Value" field.
GROWTH_ROLES = frozenset({"Investment", "Annuity/Pension", "Annuity", "Pension"})

DATE_FORMATS = ["%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%Y/%m/%d", "%m-%d-%Y"]

EARNED_INCOME_RE = re.compile(r"\b(payroll|paycheck|salary|salaries|wages|bonus|commission|employer|w-?2|direct deposit)\b", re.I)
INVESTMENT_INCOME_RE = re.compile(r"\b(dividend|dividends|interest|qualified dividend|ordinary dividend|cap(?:ital)? gain distribution|yield|1099[- ]?div|1099[- ]?int)\b", re.I)
TAX_RE = re.compile(r"\b(irs|treasury|federal tax(?:es)?|state tax(?:es)?|income tax(?:es)?|estimated tax(?:es)?|tax payment|withholding|fica|medicare tax(?:es)?|social security tax(?:es)?)\b", re.I)
TRANSFER_RE = re.compile(r"\b(transfer|xfer|credit card payment|cc payment|payment thank you|autopay|investment buy|investment sell|move money|internal transfer|401\s*\(?k\)?\s+match|401\s*\(?k\)?\s+contribution|hsa contribution|health savings account contribution)\b", re.I)
INVESTMENT_DEPOSIT_RE = re.compile(r"\b(deposit|contribution|transfer in|cash in|ach in|wire in|rollover|to brokerage|to investment)\b", re.I)
INVESTMENT_WITHDRAWAL_RE = re.compile(r"\b(withdrawal|distribution|transfer out|cash out|ach out|wire out|from brokerage|from investment|rmd)\b", re.I)

EXCLUDED_SPENDING_CATEGORIES = {
    "buy",
    "sell",
    "transfer",
    "credit card payment",
    "401k match",
    "401k contribution",
    "401(k) match",
    "401(k) contribution",
    "hsa contribution",
}

ALLOWED_INCOME_CATEGORY_KINDS = {
    "paychecks": "earned_income",
    "redmane annual note p&i": "note_receivable_income",
    "redmane annual note p and i": "note_receivable_income",
    "dividends and capital gains": "investment_income",
    "other income": "other_income",
    "interest": "investment_income",
}

ALLOWED_INCOME_CATEGORIES = [
    "Paychecks",
    "RedMane Annual Note P&I",
    "Dividends and Capital Gains",
    "other Income",
    "Interest",
]


def _input_dir(root: str | Path) -> Path:
    p = Path(root)
    p.mkdir(parents=True, exist_ok=True)
    return p


def transactions_path(root: str | Path) -> Path:
    return _input_dir(root) / "ytd_transactions.csv"


def account_setup_path(root: str | Path) -> Path:
    return _input_dir(root) / "ytd_account_setup.csv"


def import_history_path(root: str | Path) -> Path:
    return _input_dir(root) / "ytd_import_history.csv"


def _read_csv_dicts(path: Path, columns: list[str]) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return []
        rows = []
        for raw in reader:
            rows.append({col: str(raw.get(col, "") or "") for col in columns})
        return rows


def _write_csv_dicts(path: Path, columns: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns, lineterminator="\n", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({col: str(row.get(col, "") if row.get(col, "") is not None else "") for col in columns})
    tmp.replace(path)


def _current_year(today: date | None = None) -> int:
    return (today or date.today()).year


def _is_current_year_transaction(row: dict[str, Any], *, today: date | None = None) -> bool:
    d = parse_date(row.get("Date"))
    return bool(d and d.year == _current_year(today))


def read_transactions(root: str | Path, *, current_year_only: bool = True, today: date | None = None) -> list[dict[str, str]]:
    rows = _read_csv_dicts(transactions_path(root), TRANSACTION_COLUMNS)
    if current_year_only:
        rows = [r for r in rows if _is_current_year_transaction(r, today=today)]
    return rows


def write_transactions(root: str | Path, rows: list[dict[str, Any]], *, current_year_only: bool = True, today: date | None = None) -> None:
    cleaned = [normalize_transaction(r) for r in rows]
    if current_year_only:
        cleaned = [r for r in cleaned if _is_current_year_transaction(r, today=today)]
    _write_csv_dicts(transactions_path(root), TRANSACTION_COLUMNS, cleaned)


def read_account_setup(root: str | Path) -> list[dict[str, str]]:
    return _read_csv_dicts(account_setup_path(root), ACCOUNT_SETUP_COLUMNS)


def write_account_setup(root: str | Path, rows: list[dict[str, Any]]) -> None:
    cleaned = []
    seen = set()
    for raw in rows:
        row = normalize_account_setup(raw)
        acct = row["Account"].strip()
        if not acct:
            continue
        key = acct.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(row)
    _write_csv_dicts(account_setup_path(root), ACCOUNT_SETUP_COLUMNS, cleaned)


def read_import_history(root: str | Path) -> list[dict[str, str]]:
    return _read_csv_dicts(import_history_path(root), IMPORT_HISTORY_COLUMNS)


def append_import_history(root: str | Path, row: dict[str, Any]) -> None:
    rows = read_import_history(root)
    rows.append({col: str(row.get(col, "") if row.get(col, "") is not None else "") for col in IMPORT_HISTORY_COLUMNS})
    _write_csv_dicts(import_history_path(root), IMPORT_HISTORY_COLUMNS, rows)


def parse_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(text[:10]).date()
    except Exception:
        return None


def format_date(d: date | None) -> str:
    return d.isoformat() if d else ""


def parse_money(value: Any) -> float:
    text = str(value or "").strip()
    if not text:
        return 0.0
    neg = False
    if text.startswith("(") and text.endswith(")"):
        neg = True
        text = text[1:-1]
    text = text.replace("$", "").replace(",", "").strip()
    try:
        val = float(text)
    except Exception:
        val = 0.0
    return -abs(val) if neg else val


def parse_percent(value: Any, default: float = 0.0) -> float:
    text = str(value or "").strip()
    if not text:
        return default
    is_pct = text.endswith("%")
    text = text.replace("%", "").replace(",", "").strip()
    try:
        val = float(text)
    except Exception:
        return default
    return val / 100.0 if is_pct else val


def normalize_money(value: Any) -> str:
    val = parse_money(value)
    if abs(val) < 0.005:
        return "0"
    return f"{val:.2f}".rstrip("0").rstrip(".")


def normalize_transaction(raw: dict[str, Any]) -> dict[str, str]:
    row = {col: str(raw.get(col, "") if raw.get(col, "") is not None else "") for col in TRANSACTION_COLUMNS}
    d = parse_date(row["Date"])
    row["Date"] = format_date(d) if d else row["Date"].strip()
    row["Amount"] = normalize_money(row["Amount"])
    for col in TRANSACTION_COLUMNS:
        if col not in {"Date", "Amount"}:
            row[col] = str(row[col] or "").strip()
    return row


def normalize_account_setup(raw: dict[str, Any]) -> dict[str, str]:
    row = {col: str(raw.get(col, "") if raw.get(col, "") is not None else "") for col in ACCOUNT_SETUP_COLUMNS}
    role = row["Role"].strip() or "Cash / spending"
    role_low = role.lower().replace("_", " ").replace("-", " ")
    role_aliases = {
        "cash": "Cash / spending",
        "cash spending": "Cash / spending",
        "spending": "Cash / spending",
        "transaction": "Cash / spending",
        "investment account": "Investment",
        "investments": "Investment",
        "annuity/pension": "Annuity/Pension",
        "annuity pension": "Annuity/Pension",
        "annuity": "Annuity",
        "annuities": "Annuity",
        "pension": "Pension",
        "pensions": "Pension",
        "social security": "Social Security",
        "ss": "Social Security",
        "offline": "Offline asset",
        "offline asset": "Offline asset",
        "real estate": "Real estate",
        "property": "Real estate",
        "business": "Business interest",
        "business interest": "Business interest",
        "note": "Note receivable",
        "note receivable": "Note receivable",
        "credit card": "Credit card",
        "credit cards": "Credit card",
        "cc": "Credit card",
        "mortgage": "Mortgage",
        "heloc": "HELOC",
        "home equity line": "HELOC",
        "loan": "Loan",
        "loans": "Loan",
        "liability": "Other liability",
        "liabilities": "Other liability",
        "debt": "Other liability",
        "other liability": "Other liability",
        "income": "Income source",
        "income source": "Income source",
    }
    if "ignore" in role_low or "exclude" in role_low:
        role = "Ignore"
    elif "invest" in role_low or "brokerage" in role_low or "ira" in role_low or "401" in role_low:
        role = "Investment"
    else:
        role = role_aliases.get(role_low, role if role in ROLE_OPTIONS else "Cash / spending")
    row["Role"] = role
    d = parse_date(row["Prior Year End Date"])
    row["Prior Year End Date"] = format_date(d) if d else row["Prior Year End Date"].strip()
    row["Prior Year End Balance"] = normalize_money(row["Prior Year End Balance"])
    # Historical packages used both labels.  Keep both columns so older files
    # import cleanly, but make Current Value the canonical calculation field.
    current_raw = row.get("Current Value") or row.get("Current Balance")
    row["Current Value"] = normalize_money(current_raw)
    row["Current Balance"] = row["Current Value"]
    if row["Role"] == "Investment":
        # Investment current value is derived from mapped client_holdings.csv accounts,
        # not entered manually in account setup. Keep manual value only as a fallback
        # when no mapped holding account is available.
        pass
    for col in ["Account", "Mapped Investment Account", "Notes"]:
        row[col] = row[col].strip()
    return row


def csv_template() -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(TRANSACTION_COLUMNS)
    writer.writerow(["2026-01-15", "Sample Grocery", "Groceries", "Checking", "Bank CSV", "", "-125.43", "", "Household"])
    writer.writerow(["2026-01-31", "Sample Refund", "Groceries", "Checking", "Bank CSV", "", "25.00", "", "Household"])
    return out.getvalue()


def load_transactions_from_csv_text(text: str) -> tuple[list[dict[str, str]], list[str]]:
    f = io.StringIO(text or "")
    reader = csv.DictReader(f)
    if not reader.fieldnames:
        return [], ["CSV is empty or missing a header row."]
    actual = [str(x or "").strip() for x in reader.fieldnames]
    if actual != TRANSACTION_COLUMNS:
        return [], ["CSV header must exactly match: " + ", ".join(TRANSACTION_COLUMNS)]
    rows = []
    errors = []
    for i, raw in enumerate(reader, start=2):
        row = normalize_transaction(raw)
        if not row["Date"] and not row["Merchant"] and not row["Amount"]:
            continue
        d = parse_date(row["Date"])
        if not d:
            errors.append(f"Row {i}: Date is invalid or missing.")
        rows.append(row)
    return rows, errors


def transaction_hash(row: dict[str, Any]) -> str:
    norm = normalize_transaction(row)
    payload = "\u241f".join(str(norm.get(col, "")) for col in TRANSACTION_COLUMNS)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def import_transactions(root: str | Path, text: str, mode: str = "replace", *, today: date | None = None) -> dict[str, Any]:
    incoming_all, errors = load_transactions_from_csv_text(text)
    if errors:
        return {"success": False, "errors": errors[:50], "received": len(incoming_all)}
    current_year = _current_year(today)
    incoming = []
    skipped_not_current_year = 0
    for row in incoming_all:
        d = parse_date(row.get("Date"))
        if not d or d.year != current_year:
            skipped_not_current_year += 1
            continue
        incoming.append(row)
    mode = str(mode or "replace").strip().lower()
    existing = read_transactions(root, today=today)
    existing_hashes = {transaction_hash(r) for r in existing}
    latest_existing = max([parse_date(r.get("Date")) for r in existing if parse_date(r.get("Date"))] or [None])
    added = []
    skipped = skipped_not_current_year
    if mode in {"replace", "reload", "delete_all_and_reload"}:
        final = incoming
        added = incoming
    else:
        final = list(existing)
        for row in incoming:
            d = parse_date(row.get("Date"))
            if latest_existing and d and d <= latest_existing:
                skipped += 1
                continue
            h = transaction_hash(row)
            if h in existing_hashes:
                skipped += 1
                continue
            final.append(row)
            existing_hashes.add(h)
            added.append(row)
    final.sort(key=lambda r: (format_date(parse_date(r.get("Date"))) or "9999-12-31", r.get("Account", ""), r.get("Merchant", "")))
    write_transactions(root, final, today=today)
    ensure_account_setup_for_transactions(root, today=today)
    all_dates = [parse_date(r.get("Date")) for r in final if parse_date(r.get("Date"))]
    append_import_history(root, {
        "Loaded At": datetime.now().isoformat(timespec="seconds"),
        "Mode": mode,
        "Rows Received": len(incoming_all),
        "Rows Added": len(added),
        "Rows Skipped": skipped,
        "Earliest Transaction Date": format_date(min(all_dates) if all_dates else None),
        "Latest Transaction Date": format_date(max(all_dates) if all_dates else None),
        "Notes": f"Transactions imported from UI upload. Current-year filter: kept {len(incoming)} {current_year} rows; skipped {skipped_not_current_year} non-{current_year} rows.",
    })
    return {
        "success": True,
        "received": len(incoming_all),
        "added": len(added),
        "skipped": skipped,
        "skipped_not_current_year": skipped_not_current_year,
        "current_year": current_year,
        "total": len(final),
        "earliest": format_date(min(all_dates) if all_dates else None),
        "latest": format_date(max(all_dates) if all_dates else None),
    }


def ensure_account_setup_for_transactions(root: str | Path, *, today: date | None = None) -> list[dict[str, str]]:
    txns = read_transactions(root, today=today)
    setup = read_account_setup(root)
    by_acct = {r.get("Account", "").strip().lower(): r for r in setup if r.get("Account", "").strip()}
    changed = False
    prior_year = _current_year(today) - 1
    default_date = date(prior_year, 12, 31).isoformat()
    for acct in sorted({str(r.get("Account", "") or "").strip() for r in txns if str(r.get("Account", "") or "").strip()}):
        key = acct.lower()
        if key not in by_acct:
            by_acct[key] = normalize_account_setup({
                "Account": acct,
                "Role": "Cash / spending",
                "Mapped Investment Account": "",
                "Prior Year End Date": default_date,
                "Prior Year End Balance": "0",
                "Current Value": "0",
                "Notes": "Created from transaction upload.",
            })
            changed = True
    if changed or not account_setup_path(root).exists():
        write_account_setup(root, list(by_acct.values()))
    return read_account_setup(root)


def transaction_text(row: dict[str, Any]) -> str:
    return " ".join(str(row.get(k, "")) for k in ("Category", "Tags", "Merchant", "Notes", "Original Statement")).lower()


def _norm_label(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _income_category_key(value: Any) -> str:
    text = _norm_label(value)
    text = re.sub(r"\s*&\s*", " and ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if text == "redmane annual note p and i":
        return "redmane annual note p and i"
    return text


def income_kind_for_category(row: dict[str, Any]) -> str | None:
    """Return the YTD income bucket for explicit income categories only."""
    return ALLOWED_INCOME_CATEGORY_KINDS.get(_income_category_key(row.get("Category")))


def is_ignored_ytd_spending_flow(row: dict[str, Any]) -> bool:
    """Return True for bookkeeping/investment-flow rows that must not count as spending.

    The exact category check intentionally handles generic categories such as
    ``Buy`` and ``Sell`` without excluding normal merchants such as Best Buy.
    Phrase checks below catch common transfer/contribution text in statement
    descriptions even when the Category field is less specific.
    """
    category = _norm_label(row.get("Category"))
    if category in EXCLUDED_SPENDING_CATEGORIES:
        return True
    return bool(TRANSFER_RE.search(transaction_text(row)))


def classify_cash_transaction(row: dict[str, Any]) -> str:
    amount = parse_money(row.get("Amount"))
    text = transaction_text(row)
    if is_ignored_ytd_spending_flow(row):
        return "transfer"
    if TAX_RE.search(text):
        return "tax"
    income_kind = income_kind_for_category(row)
    if amount > 0 and income_kind:
        return income_kind
    if INVESTMENT_DEPOSIT_RE.search(text) or INVESTMENT_WITHDRAWAL_RE.search(text):
        return "transfer"
    if amount > 0:
        # Positive flows in cash/spending accounts are treated as merchant/category
        # refunds unless their Category is one of the explicit YTD income categories.
        return "spending_refund"
    if amount < 0:
        return "spending"
    return "neutral"


def classify_investment_transaction(row: dict[str, Any]) -> str:
    amount = parse_money(row.get("Amount"))
    text = transaction_text(row)
    if TAX_RE.search(text):
        return "tax"
    income_kind = income_kind_for_category(row)
    if amount > 0 and income_kind:
        return income_kind
    if INVESTMENT_WITHDRAWAL_RE.search(text):
        return "investment_withdrawal"
    if INVESTMENT_DEPOSIT_RE.search(text):
        return "investment_deposit"
    if is_ignored_ytd_spending_flow(row):
        return "transfer"
    # Unclassified positive/negative investment-account cash movements are not
    # YTD income. Keep them out of the income chart and cashflow diagnostics
    # unless the category/text explicitly identifies a deposit or withdrawal.
    if amount != 0:
        return "transfer"
    return "neutral"


def classify_transaction(row: dict[str, Any], *, role: str = "Cash / spending") -> str:
    if role == "Investment":
        return classify_investment_transaction(row)
    return classify_cash_transaction(row)


def annual_spending_forecast(root: str | Path) -> float | None:
    """Read the plan's current core-spending base as a benchmark if available."""
    for name in ["client_spending.csv", "client_income.csv", "client_data.csv"]:
        p = Path(root) / name
        if not p.exists():
            continue
        try:
            with p.open(newline="", encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    if str(row.get("section", "")).strip() == "Cashflow" and str(row.get("subsection", "")).strip().lower() == "spending" and str(row.get("label", "")).strip() == "annual_spending_base_year":
                        return parse_money(row.get("value"))
        except Exception:
            pass
    return None


def annual_earned_income_forecast(root: str | Path, current_year: int) -> float:
    """Return current-year earned-income forecast from plan inputs.

    Work Income supplies the annual amount, start year, and annual increase. The
    stop year is derived from Retirement Timing, so there is no separate earned-
    income end-year field to keep synchronized.
    """
    annual = parse_money(_cashflow_value(root, "Earned Income", "annual_earned_income"))
    if annual <= 0:
        return 0.0
    start = _parse_int(_cashflow_value(root, "Earned Income", "earned_income_start_year"))
    end = _last_earned_income_year_from_retirement_timing(root, current_year)
    growth = parse_percent(_cashflow_value(root, "Earned Income", "earned_income_annual_increase"), 0.0)
    if start and current_year < start:
        return 0.0
    if end and current_year > end:
        return 0.0
    years = max(0, current_year - (start or current_year))
    return annual * ((1.0 + growth) ** years)


def _real_estate_tax_category(row: dict[str, Any]) -> bool:
    cat = _norm_label(row.get("Category"))
    text = transaction_text(row)
    return cat in {"real estate taxes", "real estate tax", "property tax", "property taxes", "re taxes", "re tax"} or bool(re.search(r"\b(real estate tax|property tax|dupage co tax|county treasurer)\b", text, re.I))


def annual_real_estate_tax_from_transactions(root: str | Path, current_year: int) -> float:
    """Infer planned real-estate tax from the most recent prior-year transaction history.

    Some single-user plans leave the explicit annual_real_estate_taxes field at
    zero even though prior-year transactions contain property-tax payments.  For
    the YTD spending benchmark, use the latest complete prior-year net payments
    as a fallback so the spending chart does not show RE tax as zero.
    """
    by_year: dict[int, float] = {}
    for row in read_transactions(root, current_year_only=False):
        d = parse_date(row.get("Date"))
        if not d or d.year >= current_year:
            continue
        if not _real_estate_tax_category(row):
            continue
        amt = parse_money(row.get("Amount"))
        by_year[d.year] = by_year.get(d.year, 0.0) + (-amt)
    for yr in sorted(by_year, reverse=True):
        val = by_year.get(yr, 0.0)
        if val > 0:
            rate = real_estate_tax_adjustment_rate(root)
            years = max(0, current_year - yr)
            return val * ((1.0 + rate) ** years)
    return 0.0


def _account_current_value(row: dict[str, Any]) -> float:
    return parse_money(row.get("Current Value") or row.get("Current Balance"))


def _iter_cashflow_rows(root: str | Path):
    """Yield Cashflow rows from split plan data, preferring client_spending.csv."""
    for name in ["client_spending.csv", "client_income.csv", "client_data.csv"]:
        p = Path(root) / name
        if not p.exists():
            continue
        try:
            with p.open(newline="", encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    if str(row.get("section", "")).strip() == "Cashflow":
                        yield row
        except Exception:
            continue


def _cashflow_value(root: str | Path, subsection: str, label: str) -> str:
    target_sub = _norm_label(subsection)
    target_label = _norm_label(label)
    for row in _iter_cashflow_rows(root):
        if _norm_label(row.get("subsection")) == target_sub and _norm_label(row.get("label")) == target_label:
            return str(row.get("value", "") or "")
    return ""


def _parse_int(value: Any) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return int(float(text.replace(",", "")))
    except Exception:
        return None


def _plan_start_year(root: str | Path, default: int) -> int:
    for name in ["client_household.csv", "client_spending.csv", "client_data.csv"]:
        p = Path(root) / name
        if not p.exists():
            continue
        try:
            with p.open(newline="", encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    label = _norm_label(row.get("label"))
                    if label in {"plan_start", "plan_start_year", "start_year"}:
                        yr = _parse_int(row.get("value"))
                        if yr:
                            return yr
        except Exception:
            continue
    return default



def _last_earned_income_year_from_retirement_timing(root: str | Path, default: int) -> int:
    """Return the final year in which earned income should be forecast.

    Retirement timing is a date-effective boundary. If the retirement date is
    January 1, the retiree has no earned income in that calendar year. For
    later retirement dates, keep the existing annual YTD forecast behavior and
    include that calendar year.
    """
    for name in ["client_household.csv", "client_data.csv"]:
        p = Path(root) / name
        if not p.exists():
            continue
        try:
            with p.open(newline="", encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    if str(row.get("section", "")).strip() != "Household":
                        continue
                    if _norm_label(row.get("label")) not in {"husband_retirement_date", "retirement_date"}:
                        continue
                    raw = row.get("value")
                    d = parse_date(raw)
                    if d:
                        return d.year - 1 if (d.month == 1 and d.day == 1) else d.year
                    yr = _parse_int(raw)
                    if yr:
                        return yr
        except Exception:
            continue
    return default


def _retirement_timing_year(root: str | Path, default: int) -> int:
    """Compatibility helper returning the calendar year of retirement."""
    last = _last_earned_income_year_from_retirement_timing(root, default)
    return last

def real_estate_tax_adjustment_rate(root: str | Path) -> float:
    return parse_percent(_cashflow_value(root, "Mortgage", "real_estate_tax_annual_adjustment_pct"), 0.0)


def annual_mortgage_spending(root: str | Path, current_year: int) -> float:
    """Return this year's planned mortgage payments from client_spending.csv."""
    monthly = parse_money(_cashflow_value(root, "Mortgage", "monthly_payment"))
    if monthly <= 0:
        return 0.0
    last_year = _parse_int(_cashflow_value(root, "Mortgage", "last_payment_year"))
    last_payment_date = parse_date(_cashflow_value(root, "Mortgage", "last_payment_date"))
    if last_payment_date and not last_year:
        last_year = last_payment_date.year
    if last_year and current_year > last_year:
        return 0.0
    if last_year and current_year == last_year and last_payment_date:
        return monthly * max(0, min(12, last_payment_date.month))
    return monthly * 12


def annual_real_estate_tax_spending(root: str | Path, current_year: int) -> float:
    """Return this year's planned real-estate taxes from the Mortgage section.

    The field is intentionally in Cashflow / Mortgage so real-estate taxes are
    modeled with housing costs instead of embedded in core lifestyle spending.
    """
    for label in ("annual_real_estate_taxes", "real_estate_taxes", "property_tax"):
        val = parse_money(_cashflow_value(root, "Mortgage", label))
        if val > 0:
            rate = real_estate_tax_adjustment_rate(root)
            years = max(0, current_year - _plan_start_year(root, current_year))
            return val * ((1.0 + rate) ** years)
    return annual_real_estate_tax_from_transactions(root, current_year)


def annual_large_discretionary_spending(root: str | Path, current_year: int) -> float:
    """Return planned large discretionary expenses active in the current year."""
    grouped: dict[str, dict[str, str]] = {}
    for row in _iter_cashflow_rows(root):
        if _norm_label(row.get("subsection")) != "large discretionary expenses":
            continue
        label = str(row.get("label", "") or "").strip()
        match = re.match(r"extra_(\d+)_(type|amount|year|start_year|end_year|comment)$", label)
        if not match:
            continue
        grouped.setdefault(match.group(1), {})[match.group(2)] = str(row.get("value", "") or "")

    total = 0.0
    for item in grouped.values():
        amount = parse_money(item.get("amount"))
        if amount <= 0:
            continue
        one_time_year = _parse_int(item.get("year"))
        start_year = _parse_int(item.get("start_year"))
        end_year = _parse_int(item.get("end_year"))
        if one_time_year:
            if one_time_year == current_year:
                total += amount
            continue
        if start_year and current_year < start_year:
            continue
        if end_year and current_year > end_year:
            continue
        if start_year or end_year:
            total += amount
    return total


def planned_spending_components(root: str | Path, current_year: int) -> dict[str, float]:
    core = annual_spending_forecast(root) or 0.0
    mortgage_payment = annual_mortgage_spending(root, current_year)
    real_estate_tax_adjustment_pct = real_estate_tax_adjustment_rate(root)
    real_estate_taxes = annual_real_estate_tax_spending(root, current_year)
    mortgage_and_re_tax = mortgage_payment + real_estate_taxes
    large_discretionary = annual_large_discretionary_spending(root, current_year)
    total = core + mortgage_and_re_tax + large_discretionary
    return {
        "core_spending": core,
        "mortgage": mortgage_and_re_tax,
        "mortgage_payment": mortgage_payment,
        "real_estate_taxes": real_estate_taxes,
        "real_estate_tax_annual_adjustment_pct": real_estate_tax_adjustment_pct,
        "mortgage_and_re_tax": mortgage_and_re_tax,
        "large_discretionary": large_discretionary,
        "annual_total": total,
    }



def _local_price_snapshot(root: str | Path) -> dict[str, float]:
    """Return last known prices from local output sidecars without live calls."""
    root_p = Path(root)
    candidates = [root_p / "price_refresh_result.json", root_p.parent / "output" / "price_refresh_result.json", root_p / "pricing_diagnostics.json", root_p.parent / "output" / "pricing_diagnostics.json"]
    out: dict[str, float] = {}
    for p in candidates:
        if not p.exists():
            continue
        try:
            payload = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        prices = payload.get("prices") if isinstance(payload, dict) else {}
        if isinstance(prices, dict):
            for k, v in prices.items():
                price = parse_money(v)
                if price > 0:
                    out[str(k).strip().upper()] = price
    return out


def investment_holding_accounts(root: str | Path) -> list[str]:
    """Return investment account names available in client_holdings.csv for UI dropdowns."""
    p = Path(root) / "client_holdings.csv"
    accounts: set[str] = set()
    if p.exists():
        try:
            with p.open(newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    acct = str(row.get("account") or row.get("Account") or "").strip()
                    if acct:
                        accounts.add(acct)
        except Exception:
            pass
    return sorted(accounts, key=lambda x: x.lower())


_INCOME_STREAM_META = {"joint-and-survivor percentage", "present value horizon", "recovery age"}

def annuity_pension_accounts(root: str | Path) -> list[str]:
    """Return Income Stream subsection names (annuities/pensions) for the Mapped Account dropdown."""
    p = Path(root) / "client_income.csv"
    seen: set[str] = set()
    results: list[str] = []
    if p.exists():
        try:
            with p.open(newline="", encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    if str(row.get("section", "") or "").strip() != "Income Streams":
                        continue
                    sub = str(row.get("subsection", "") or "").strip()
                    if sub and sub.lower() not in _INCOME_STREAM_META and sub not in seen:
                        seen.add(sub)
                        results.append(sub)
        except Exception:
            pass
    return sorted(results, key=lambda x: x.lower())


def annuity_pension_account_values(root: str | Path) -> dict[str, float]:
    """Return base (account value) for each Income Stream from client_income.csv.

    The 'base' field is the starting account value used by the net worth model.
    Used to auto-populate Current Value when a YTD row is mapped to an income stream.
    """
    p = Path(root) / "client_income.csv"
    values: dict[str, float] = {}
    if not p.exists():
        return values
    try:
        with p.open(newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                if str(row.get("section", "") or "").strip() != "Income Streams":
                    continue
                sub = str(row.get("subsection", "") or "").strip()
                if not sub or sub.lower() in _INCOME_STREAM_META:
                    continue
                if str(row.get("label", "") or "").strip().lower() == "base":
                    val = parse_money(row.get("value", ""))
                    if val:
                        values[sub] = val
    except Exception:
        pass
    return values


def investment_holding_account_values(root: str | Path) -> dict[str, float]:
    """Return current investment values by holding account from client_holdings.csv.

    YTD growth uses the holdings table as the source of current values so the
    account-mapping UI only needs transaction-account mapping and prior-year
    starting balances. Prefer explicit market/current/value columns when present;
    otherwise approximate lot value from shares × purchase_price, with CASH lots
    treated as dollar balances when no price is supplied.
    """
    p = Path(root) / "client_holdings.csv"
    values: dict[str, float] = {}
    if not p.exists():
        return values
    local_prices = _local_price_snapshot(root)
    try:
        with p.open(newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                acct = str(row.get("account") or row.get("Account") or "").strip()
                if not acct:
                    continue
                explicit = None
                for col in ("market_value", "current_value", "value", "Current Value", "Market Value"):
                    if str(row.get(col, "") or "").strip():
                        explicit = parse_money(row.get(col))
                        break
                if explicit is not None:
                    lot_value = explicit
                else:
                    shares = parse_money(row.get("shares") or row.get("Shares"))
                    symbol = str(row.get("symbol") or row.get("Symbol") or "").strip().upper()
                    price = parse_money(row.get("current_price") or row.get("Current Price") or row.get("price") or row.get("Price"))
                    if price == 0 and symbol in {"CASH", "USD", "MMF", "MONEY MARKET"}:
                        price = 1.0
                    if price == 0 and symbol in local_prices:
                        price = local_prices[symbol]
                    if price == 0:
                        price = parse_money(row.get("purchase_price") or row.get("Purchase Price"))
                    lot_value = shares * price
                values[acct] = values.get(acct, 0.0) + lot_value
    except Exception:
        return values
    return values


def transaction_accounts(root: str | Path, *, today: date | None = None) -> list[str]:
    accounts = {str(r.get("Account", "") or "").strip() for r in read_transactions(root, today=today) if str(r.get("Account", "") or "").strip()}
    return sorted(accounts, key=lambda x: x.lower())


def _account_setup_map(root: str | Path) -> dict[str, dict[str, str]]:
    return {str(r.get("Account", "") or "").strip().lower(): r for r in read_account_setup(root)}


def ytd_summary(root: str | Path, *, today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    transactions = read_transactions(root, today=today)
    setup = ensure_account_setup_for_transactions(root, today=today) if transactions else read_account_setup(root)
    setup_map = _account_setup_map(root)
    parsed = []
    for idx, row in enumerate(transactions):
        d = parse_date(row.get("Date"))
        if d and d.year == today.year:
            parsed.append((idx, d, row))
    dates = [d for _, d, _ in parsed]
    current_year = today.year
    ytd_start = date(current_year, 1, 1)
    current_year_dates = [d for d in dates if d.year == current_year]
    ytd_end = max(current_year_dates) if current_year_dates else None
    ytd_rows = [(i, d, r) for i, d, r in parsed if d >= ytd_start and (not ytd_end or d <= ytd_end)]
    ytd_days = max(1, ((ytd_end or today) - ytd_start).days + 1)
    year_days = 366 if current_year % 4 == 0 and (current_year % 100 != 0 or current_year % 400 == 0) else 365

    spending = 0.0
    earned_income = 0.0
    investment_income = 0.0
    other_income = 0.0
    note_receivable_income = 0.0
    taxes = 0.0
    transfer = 0.0
    investment_deposits = 0.0
    investment_withdrawals = 0.0
    category_totals: dict[str, float] = {}
    income_category_totals: dict[str, float] = {}
    account_totals: dict[str, float] = {}
    transaction_type_totals: dict[str, float] = {}
    monthly = {m: {"spending": 0.0, "income": 0.0, "growth": None, "taxes": 0.0} for m in range(1, 13)}

    for _, d, row in ytd_rows:
        amount = parse_money(row.get("Amount"))
        account_key = str(row.get("Account", "") or "").strip().lower()
        setup_row = setup_map.get(account_key, {})
        role = str(setup_row.get("Role", "Cash / spending") or "Cash / spending")
        kind = classify_transaction(row, role=role)
        transaction_type_totals[kind] = transaction_type_totals.get(kind, 0.0) + amount

        if role == "Ignore":
            transfer += amount
            continue

        if role == "Investment":
            if kind == "investment_income":
                val = abs(amount)
                investment_income += val
                monthly[d.month]["income"] += val
                cat = str(row.get("Category", "") or "Uncategorized").strip() or "Uncategorized"
                income_category_totals[cat] = income_category_totals.get(cat, 0.0) + val
            elif kind == "investment_deposit":
                investment_deposits += abs(amount)
            elif kind == "investment_withdrawal":
                investment_withdrawals += abs(amount)
            elif kind == "note_receivable_income":
                val = abs(amount)
                note_receivable_income += val
                monthly[d.month]["income"] += val
                cat = str(row.get("Category", "") or "Uncategorized").strip() or "Uncategorized"
                income_category_totals[cat] = income_category_totals.get(cat, 0.0) + val
            elif kind == "tax":
                val = -amount
                taxes += val
                monthly[d.month]["taxes"] += val
            else:
                transfer += amount
            continue

        if kind == "transfer":
            transfer += amount
            continue
        if kind == "tax":
            val = -amount
            taxes += val
            monthly[d.month]["taxes"] += val
        elif kind == "earned_income":
            val = abs(amount)
            earned_income += val
            monthly[d.month]["income"] += val
            cat = str(row.get("Category", "") or "Uncategorized").strip() or "Uncategorized"
            income_category_totals[cat] = income_category_totals.get(cat, 0.0) + val
        elif kind == "investment_income":
            val = abs(amount)
            investment_income += val
            monthly[d.month]["income"] += val
            cat = str(row.get("Category", "") or "Uncategorized").strip() or "Uncategorized"
            income_category_totals[cat] = income_category_totals.get(cat, 0.0) + val
        elif kind == "note_receivable_income":
            val = abs(amount)
            note_receivable_income += val
            monthly[d.month]["income"] += val
            cat = str(row.get("Category", "") or "Uncategorized").strip() or "Uncategorized"
            income_category_totals[cat] = income_category_totals.get(cat, 0.0) + val
        elif kind == "other_income":
            val = abs(amount)
            other_income += val
            monthly[d.month]["income"] += val
            cat = str(row.get("Category", "") or "Uncategorized").strip() or "Uncategorized"
            income_category_totals[cat] = income_category_totals.get(cat, 0.0) + val
        elif kind == "spending":
            val = abs(amount)
            spending += val
            monthly[d.month]["spending"] += val
            cat = str(row.get("Category", "") or "Uncategorized").strip() or "Uncategorized"
            category_totals[cat] = category_totals.get(cat, 0.0) + val
        elif kind == "spending_refund":
            val = abs(amount)
            spending -= val
            monthly[d.month]["spending"] -= val
            cat = str(row.get("Category", "") or "Uncategorized").strip() or "Uncategorized"
            category_totals[cat] = category_totals.get(cat, 0.0) - val

        account = str(row.get("Account", "") or "Unassigned").strip() or "Unassigned"
        account_totals[account] = account_totals.get(account, 0.0) + amount

    total_income = earned_income + investment_income + note_receivable_income + other_income
    holding_values = investment_holding_account_values(root)
    annuity_values = annuity_pension_account_values(root)
    account_growth_rows = []
    prior_bal = 0.0
    current_bal = 0.0
    any_growth_account = False
    for r in setup:
        role = str(r.get("Role") or "").strip() or "Cash / spending"
        if role == "Ignore":
            continue
        # Growth is calculated only for Investment and Annuity/Pension account types.
        # Cash, credit cards, liabilities, and other roles are excluded — they do not
        # represent investment growth and would distort the YTD growth metric.
        if role not in GROWTH_ROLES:
            continue
        acct = str(r.get("Account") or "").strip()
        if not acct:
            continue
        prior = parse_money(r.get("Prior Year End Balance"))
        mapped = str(r.get("Mapped Investment Account") or "").strip() or acct
        # Investment accounts: current value from mapped client_holdings.csv accounts.
        # Annuity/Pension accounts: current value from mapped Income Stream base value,
        # falling back to the manually entered Current Value.
        if role == "Investment" and mapped in holding_values:
            current = holding_values[mapped]
            source = f"holdings:{mapped}"
        elif role in {"Annuity/Pension", "Annuity", "Pension"} and mapped in annuity_values:
            current = annuity_values[mapped]
            source = f"income_stream_base:{mapped}"
        else:
            current = _account_current_value(r)
            source = "account_setup_current_value"
        if abs(prior) < 0.005 and abs(current) < 0.005:
            continue
        prior_bal += prior
        current_bal += current
        any_growth_account = True
        account_growth_rows.append({
            "account": acct,
            "role": role,
            "mapped_investment_account": mapped if role in {"Investment", "Annuity/Pension", "Annuity", "Pension"} else "",
            "prior_year_end_balance": round(prior, 2),
            "current_value": round(current, 2),
            "growth": round(current - prior, 2),
            "source": source,
        })
    current_bal_value = current_bal if any_growth_account else None
    net_external_investment_cashflow = investment_deposits - investment_withdrawals
    # Current YTD growth is point-to-point across mapped account setup rows:
    # investment rows use current holdings value/prices; non-investment rows use
    # Current Value/Current Balance.  External cashflow is reported only for
    # diagnostics and is not deducted from growth.
    actual_growth = (current_bal - prior_bal) if any_growth_account else None
    growth_balance_series = []
    if any_growth_account:
        prior_dates = [parse_date(r.get("Prior Year End Date")) for r in setup if parse_date(r.get("Prior Year End Date"))]
        prior_date = max(prior_dates) if prior_dates else date(current_year - 1, 12, 31)
        growth_balance_series = [
            {
                "label": prior_date.strftime("%m/%d"),
                "date": prior_date.isoformat(),
                "balance": round(prior_bal, 2),
                "growth": 0.0,
            },
            {
                "label": "Today",
                "date": today.isoformat(),
                "balance": round(current_bal, 2),
                "growth": round(actual_growth, 2),
            },
        ]

    spending_annualized = spending / ytd_days * year_days if ytd_rows else None
    earned_income_annual_plan = annual_earned_income_forecast(root, current_year)
    earned_income_remaining = max(0.0, earned_income_annual_plan - earned_income)
    investment_income_annualized = investment_income / ytd_days * year_days if ytd_rows else None
    other_income_annualized = other_income / ytd_days * year_days if ytd_rows else None
    income_annualized = (
        earned_income + earned_income_remaining
        + (investment_income_annualized or 0.0)
        + note_receivable_income
        + (other_income_annualized or 0.0)
    ) if ytd_rows else None
    taxes_annualized = taxes / ytd_days * year_days if ytd_rows else None
    growth_annualized = actual_growth / ytd_days * year_days if actual_growth is not None else None
    benchmark_spending = annual_spending_forecast(root)
    spending_plan_components = planned_spending_components(root, current_year)
    annual_planned_spending = spending_plan_components["annual_total"]
    spending_expected_ytd = annual_planned_spending * (ytd_days / year_days) if ytd_rows and annual_planned_spending else None
    monthly_series = []
    cum_sp = cum_in = cum_tax = 0.0
    for m in range(1, 13):
        cum_sp += monthly[m]["spending"]
        cum_in += monthly[m]["income"]
        cum_tax += monthly[m]["taxes"]
        month_end_days = min(year_days, (date(current_year, min(m + 1, 12), 1) - ytd_start).days if m < 12 else year_days)
        progress = max(1, month_end_days) / year_days
        monthly_series.append({
            "month": m,
            "label": date(current_year, m, 1).strftime("%b"),
            "actual_spending": round(cum_sp, 2),
            "actual_income": round(cum_in, 2),
            "actual_taxes": round(cum_tax, 2),
            "forecast_spending": round(annual_planned_spending * progress, 2) if annual_planned_spending else None,
            "forecast_income": round((income_annualized or 0.0) * progress, 2) if income_annualized is not None else None,
            "forecast_taxes": round((taxes_annualized or 0.0) * progress, 2) if taxes_annualized is not None else None,
            "forecast_growth": round((growth_annualized or 0.0) * progress, 2) if growth_annualized is not None else None,
        })
    return {
        "enabled": len(transactions) > 0,
        "transaction_count": len(transactions),
        "earliest_transaction_date": format_date(min(dates) if dates else None),
        "latest_transaction_date": format_date(max(dates) if dates else None),
        "ytd_start": ytd_start.isoformat(),
        "ytd_end": format_date(ytd_end),
        "through_date": format_date(ytd_end),
        "current_year": current_year,
        "ytd_days": ytd_days,
        "year_days": year_days,
        "actual": {
            "spending": round(spending, 2),
            "income": round(total_income, 2),
            "earned_income": round(earned_income, 2),
            "investment_income": round(investment_income, 2),
            "note_receivable_income": round(note_receivable_income, 2),
            "other_income": round(other_income, 2),
            "taxes": round(taxes, 2),
            "growth": round(actual_growth, 2) if actual_growth is not None else None,
        },
        "forecast": {
            "spending": round(spending_expected_ytd, 2) if spending_expected_ytd is not None else None,
            "spending_annualized_actual": round(spending_annualized, 2) if spending_annualized is not None else None,
            "spending_annual_plan": round(annual_planned_spending, 2),
            "income": round(income_annualized, 2) if income_annualized is not None else None,
            "earned_income_annual_plan": round(earned_income_annual_plan, 2),
            "earned_income_remaining": round(earned_income_remaining, 2),
                        "investment_income_annualized": round(investment_income_annualized, 2) if investment_income_annualized is not None else None,
            "other_income_annualized": round(other_income_annualized, 2) if other_income_annualized is not None else None,
            "note_receivable_income_non_extrapolated": round(note_receivable_income, 2),
            "taxes": round(taxes_annualized, 2) if taxes_annualized is not None else None,
            "growth": round(growth_annualized, 2) if growth_annualized is not None else None,
            "spending_plan_benchmark": round(benchmark_spending, 2) if benchmark_spending is not None else None,
            "spending_plan_components": {k: round(v, 2) for k, v in spending_plan_components.items()},
        },
        "investment_balance": {
            "prior_year_end_balance": round(prior_bal, 2),
            "current_balance": round(current_bal_value, 2) if current_bal_value is not None else None,
            "current_balance_source": "client_holdings.csv" if current_bal is not None else None,
            "external_deposits": round(investment_deposits, 2),
            "external_withdrawals": round(investment_withdrawals, 2),
            "net_ytd_investment_cashflow": round(net_external_investment_cashflow, 2),
            "investment_income_transactions": round(investment_income, 2),
            "actual_growth_available": current_bal_value is not None,
            "growth_method": "mapped_accounts_current_value_minus_prior_year_end_balance",
            "account_growth_rows": account_growth_rows,
        },
        "cashflow_components": {
            "earned_income": round(earned_income, 2),
            "investment_income": round(investment_income, 2),
            "note_receivable_income": round(note_receivable_income, 2),
            "other_income": round(other_income, 2),
            "taxes": round(taxes, 2),
            "transfers": round(transfer, 2),
        },
        "transaction_type_totals": sorted([{"type": k, "amount": round(v, 2)} for k, v in transaction_type_totals.items()], key=lambda x: x["type"]),
        "allowed_income_categories": ALLOWED_INCOME_CATEGORIES,
        "category_totals": sorted([{"category": k, "amount": round(v, 2)} for k, v in category_totals.items() if round(v, 2) > 0], key=lambda x: -x["amount"]),
        "income_category_totals": sorted([{"category": k, "amount": round(v, 2)} for k, v in income_category_totals.items() if round(v, 2) > 0], key=lambda x: -x["amount"]),
        "account_totals": sorted([{"account": k, "amount": round(v, 2)} for k, v in account_totals.items()], key=lambda x: x["account"]),
        "growth_series": growth_balance_series,
        "series": monthly_series,
        "accounts": setup,
        "role_options": ROLE_OPTIONS,
        "transaction_accounts": transaction_accounts(root, today=today),
        "investment_holding_accounts": investment_holding_accounts(root),
        "annuity_pension_accounts": annuity_pension_accounts(root),
    }


def status_payload(root: str | Path) -> dict[str, Any]:
    return {
        "success": True,
        "transactions": [{"index": i, **r} for i, r in enumerate(read_transactions(root))],
        "account_setup": read_account_setup(root),
        "import_history": read_import_history(root),
        "summary": ytd_summary(root),
        "expected_transaction_columns": TRANSACTION_COLUMNS,
        "transaction_template_csv": csv_template(),
        "transaction_accounts": transaction_accounts(root),
        "investment_holding_accounts": investment_holding_accounts(root),
    }
