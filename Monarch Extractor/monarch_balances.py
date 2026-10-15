#!/usr/bin/env python3
"""Monarch account-balance export.

Downloads Monarch's full balance history (one row per account per day) from the
Accounts page, normalizes it, and writes ``output/balances.csv`` for the
downstream importer. Separate from monarch_extract.py so a failure here never
affects the transaction job (and vice versa).

Every run downloads the full history (~800 KB), so no delta logic is needed:
the importer upserts by (date, account_key).

Playwright is imported lazily, so the normalizer is importable (and testable)
without the extractor venv.
"""

import argparse
import asyncio
import csv
import math
import os
import re
import sys
import unicodedata
from datetime import date, datetime
from pathlib import Path

ACCOUNTS_URL = "https://app.monarch.com/accounts"

BASE_DIR = Path(__file__).resolve().parent
PROFILE_DIR = BASE_DIR / "monarch-browser"
RAW_DIR = BASE_DIR / "raw"
OUTPUT_DIR = BASE_DIR / "output"
BALANCES_FILE = OUTPUT_DIR / "balances.csv"

PAGE_TIMEOUT_MS = 90_000
DOWNLOAD_TIMEOUT_MS = 120_000
DOWNLOAD_RETRIES = 3

EXPECTED_HEADER = ["Date", "Balance", "Account"]
OUTPUT_HEADER = ["date", "account_key", "account", "balance"]


def clean_account_name(value):
    """Display name: NFKC, trimmed, internal whitespace collapsed."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value or "")).strip()


def account_key(value):
    """Stable identity key. The export carries no account id, so the cleaned
    name (case-insensitive) is the key."""
    return clean_account_name(value).casefold()


def parse_date(text):
    """Accept ISO (2024-01-10) and US (1/10/2024) dates; return ISO."""
    text = (text or "").strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"unparseable date {text!r}")


def parse_amount(text):
    text = (text or "").strip().replace(",", "").replace("$", "")
    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]
    try:
        value = float(text)
    except ValueError:
        raise ValueError(f"unparseable balance {text!r}") from None
    if not math.isfinite(value):
        raise ValueError(f"non-finite balance {text!r}")
    return value


def normalize_balances_csv(path):
    """Read a raw Monarch balances CSV -> list of normalized rows, sorted.

    Raises ValueError on a wrong header, an empty file, or any bad date/amount
    (a partial or changed export must not be written as if it were good).
    Two rows for the same (date, account) with different balances are refused: the export has no account
    id, so same-named accounts would otherwise be merged and one balance silently dropped.
    """
    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader, None)
        if [h.strip() for h in (header or [])] != EXPECTED_HEADER:
            raise ValueError(f"unexpected balances header {header!r}; expected {EXPECTED_HEADER!r}")
        merged = {}
        for line_no, row in enumerate(reader, start=2):
            if not row or not any(cell.strip() for cell in row):
                continue
            if len(row) != 3:
                raise ValueError(f"line {line_no}: expected 3 columns, got {len(row)}")
            try:
                iso = parse_date(row[0])
                amount = parse_amount(row[1])
            except ValueError as exc:
                raise ValueError(f"line {line_no}: {exc}") from None
            name = clean_account_name(row[2])
            if not name:
                raise ValueError(f"line {line_no}: empty account name")
            key = (iso, account_key(name))
            if key in merged and merged[key]["balance"] != amount:
                raise ValueError(
                    f"line {line_no}: two accounts named {name!r} on {iso} with different balances; "
                    "rename one in Monarch so they can be told apart"
                )
            merged[key] = {
                "date": iso,
                "account_key": account_key(name),
                "account": name,
                "balance": amount,
            }
    if not merged:
        raise ValueError("balances CSV contained no rows")
    return sorted(merged.values(), key=lambda r: (r["date"], r["account_key"]))


def write_balances_csv(rows, path=BALANCES_FILE):
    """Atomically write the normalized rows (temp file + replace)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_HEADER)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(tmp, path)


async def download_balances_csv(headed):
    """Open Monarch's Accounts page and save the balance-history CSV."""
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError
    from playwright.async_api import async_playwright

    RAW_DIR.mkdir(exist_ok=True)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=not headed,
            accept_downloads=True,
            viewport={"width": 1440, "height": 1000},
        )
        page = browser.pages[0] if browser.pages else await browser.new_page()
        page.set_default_timeout(PAGE_TIMEOUT_MS)
        page.set_default_navigation_timeout(PAGE_TIMEOUT_MS)
        try:
            print("Opening Monarch accounts...")
            await page.goto(ACCOUNTS_URL, wait_until="domcontentloaded")
            if any(token in page.url.lower() for token in ("/login", "sign-in", "signin", "/auth")):
                raise RuntimeError("Monarch login required; run with --login to sign in.")

            last_error = None
            for attempt in range(1, DOWNLOAD_RETRIES + 1):
                try:
                    button = page.get_by_role("button", name="Download CSV", exact=True)
                    await button.first.wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)
                    print(f"Downloading balances CSV (attempt {attempt}/{DOWNLOAD_RETRIES})...")
                    out = RAW_DIR / f"balances-{datetime.now().strftime('%Y%m%d-%H%M%S')}-attempt{attempt}.csv"
                    async with page.expect_download(timeout=DOWNLOAD_TIMEOUT_MS) as info:
                        await button.first.click(timeout=PAGE_TIMEOUT_MS)
                    download = await info.value
                    failure = await download.failure()
                    if failure:
                        raise RuntimeError(f"Browser download failure: {failure}")
                    await download.save_as(str(out))
                    if not out.exists() or out.stat().st_size == 0:
                        raise RuntimeError("Downloaded balances CSV is missing or empty.")
                    print(f"Downloaded: {out}")
                    return out
                except (PlaywrightTimeoutError, RuntimeError) as exc:
                    last_error = exc
                    print(f"Download attempt {attempt} failed: {exc}")
                    if attempt < DOWNLOAD_RETRIES:
                        await page.wait_for_timeout(3_000)
            raise RuntimeError(f"Balances download failed after {DOWNLOAD_RETRIES} attempt(s): {last_error}")
        except Exception:
            try:
                OUTPUT_DIR.mkdir(exist_ok=True)
                stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                await page.screenshot(path=str(OUTPUT_DIR / f"balances-debug-{stamp}.png"), full_page=True)
            except Exception:
                pass
            raise
        finally:
            await browser.close()


async def main():
    parser = argparse.ArgumentParser(description="Export Monarch daily account balances to output/balances.csv.")
    parser.add_argument("--headed", action="store_true", help="Show the browser window.")
    parser.add_argument("--login", action="store_true", help="Show browser for Monarch login or 2FA.")
    parser.add_argument("--from-file", metavar="CSV", help="Normalize an already-downloaded balances CSV instead of downloading.")
    args = parser.parse_args()

    raw_path = Path(args.from_file) if args.from_file else await download_balances_csv(args.headed or args.login)
    rows = normalize_balances_csv(raw_path)
    write_balances_csv(rows)
    accounts = len({r["account_key"] for r in rows})
    print(f"Wrote {len(rows)} rows, {accounts} accounts, {rows[0]['date']} -> {rows[-1]['date']}: {BALANCES_FILE}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(1)
    except Exception as exc:
        print(f"Monarch balances export failed: {exc}", file=sys.stderr)
        sys.exit(1)
