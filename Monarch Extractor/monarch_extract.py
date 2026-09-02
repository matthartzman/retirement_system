#!/usr/bin/env python3

import argparse
import asyncio
import csv
import hashlib
import json
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright


MONARCH_URL = "https://app.monarchmoney.com"
TRANSACTIONS_URL = f"{MONARCH_URL}/transactions"

BASE_DIR = Path(__file__).resolve().parent
PROFILE_DIR = BASE_DIR / "monarch-browser"
RAW_DIR = BASE_DIR / "raw"
OUTPUT_DIR = BASE_DIR / "output"

HISTORY_FILE = OUTPUT_DIR / "transactions.csv"
NEW_FILE = OUTPUT_DIR / "new_transactions.csv"
CHANGED_FILE = OUTPUT_DIR / "changed_transactions.csv"
DUPLICATES_FILE = OUTPUT_DIR / "duplicates_removed.csv"
STATE_DB = OUTPUT_DIR / "monarch_state.sqlite3"

PAGE_TIMEOUT_MS = 90_000
DOWNLOAD_TIMEOUT_MS = 120_000
DOWNLOAD_RETRIES = 3

MONARCH_ID_HEADER = "Id"
DEFAULT_PERIOD = "Last 30 days"

PERIOD_LABELS = {
    "7": "Last 7 days",
    "7 days": "Last 7 days",
    "last 7 days": "Last 7 days",
    "14": "Last 14 days",
    "14 days": "Last 14 days",
    "last 14 days": "Last 14 days",
    "30": "Last 30 days",
    "30 days": "Last 30 days",
    "last 30 days": "Last 30 days",
    "this month": "This month",
    "last month": "Last month",
    "this year": "This year",
    "last year": "Last year",
}

RAW_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def normalize_period(value):
    """Return the exact Monarch date-preset label; invalid input uses 30 days."""
    normalized = str(value or "").strip().casefold()

    if not normalized:
        return DEFAULT_PERIOD

    return PERIOD_LABELS.get(
        normalized,
        DEFAULT_PERIOD,
    )


def clean_key(value):
    """Convert a raw CSV header into a stable output-column name."""
    text = str(value).strip()

    return "".join(
        character
        if character.isalnum() or character == "_"
        else "_"
        for character in text
    ).strip("_").lower()


def clean_value(value):
    """Return a scalar string suitable for a CSV field."""
    if value is None:
        return ""

    return str(value).strip()


def monarch_transaction_id(row):
    """
    Return only Monarch's actual `Id` value.

    This intentionally does not derive an ID from merchant, date, account,
    category, or amount. Such a fallback could merge valid separate purchases.
    """
    for header, value in row.items():
        if str(header).strip().casefold() == MONARCH_ID_HEADER.casefold():
            return clean_value(value)

    return ""


def normalize_transaction(row, row_number):
    """
    Normalize a raw export row.

    Transactions missing Monarch Id receive a run-local key solely so they
    can remain in the history CSV. They are excluded from deduplication,
    change detection, and downstream events.
    """
    original = {
        str(key).strip(): clean_value(value)
        for key, value in row.items()
        if key is not None
    }

    source_columns = {}

    for key, value in original.items():
        column = clean_key(key)

        if column:
            source_columns[column] = value

    monarch_id = monarch_transaction_id(original)

    return {
        "id": monarch_id,
        "row_key": monarch_id or f"missing-monarch-id-row-{row_number}",
        "date": clean_value(original.get("Date", "")),
        "merchant": clean_value(
            original.get("Merchant")
            or original.get("Name")
            or ""
        ),
        "amount": clean_value(original.get("Amount", "")),
        "account": clean_value(original.get("Account", "")),
        "category": clean_value(original.get("Category", "")),
        "source_columns": source_columns,
    }


def transaction_fingerprint(transaction):
    """Hash all current fields to identify a changed version of the same Id."""
    canonical = {
        "id": transaction.get("id", ""),
        "date": transaction.get("date", ""),
        "merchant": transaction.get("merchant", ""),
        "amount": transaction.get("amount", ""),
        "account": transaction.get("account", ""),
        "category": transaction.get("category", ""),
        "source_columns": transaction.get("source_columns", {}),
    }

    payload = json.dumps(
        canonical,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )

    return hashlib.sha256(
        payload.encode("utf-8")
    ).hexdigest()


def read_csv(path):
    """Read a raw Monarch export with UTF-8 and Windows-1252 fallback."""
    last_error = None

    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            with open(
                path,
                "r",
                encoding=encoding,
                newline="",
            ) as file:
                reader = csv.DictReader(file)

                return [
                    normalize_transaction(row, row_number)
                    for row_number, row in enumerate(reader, start=2)
                ]
        except UnicodeDecodeError as exc:
            last_error = exc

    raise RuntimeError(
        f"Unable to read raw CSV {path}: {last_error}"
    )


def all_source_columns(transactions):
    """Collect all Monarch source columns found across supplied transactions."""
    columns = set()

    for transaction in transactions:
        columns.update(
            transaction.get("source_columns", {}).keys()
        )

    return sorted(columns)


def transaction_to_flat_row(transaction, source_fields):
    """Return a flat, consumer-safe CSV row without nested JSON fields."""
    row = {
        "id": transaction.get("id", ""),
        "date": transaction.get("date", ""),
        "merchant": transaction.get("merchant", ""),
        "amount": transaction.get("amount", ""),
        "account": transaction.get("account", ""),
        "category": transaction.get("category", ""),
    }

    source_columns = transaction.get("source_columns", {})

    for field in source_fields:
        row[field] = source_columns.get(field, "")

    return row


def flat_row_to_transaction(row):
    """Reconstruct an internal transaction from the user-facing history CSV."""
    standard_fields = {
        "id",
        "date",
        "merchant",
        "amount",
        "account",
        "category",
    }

    source_columns = {
        key: clean_value(value)
        for key, value in row.items()
        if key not in standard_fields
        and value is not None
    }

    tx_id = clean_value(row.get("id", ""))

    return {
        "id": tx_id,
        "row_key": tx_id,
        "date": clean_value(row.get("date", "")),
        "merchant": clean_value(row.get("merchant", "")),
        "amount": clean_value(row.get("amount", "")),
        "account": clean_value(row.get("account", "")),
        "category": clean_value(row.get("category", "")),
        "source_columns": source_columns,
    }


def load_history_csv():
    """Load the full transaction history keyed by genuine Monarch Id."""
    if not HISTORY_FILE.exists():
        return {}

    last_error = None

    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            with open(
                HISTORY_FILE,
                "r",
                encoding=encoding,
                newline="",
            ) as file:
                history = {}

                for row in csv.DictReader(file):
                    transaction = flat_row_to_transaction(row)

                    if transaction["id"]:
                        history[transaction["id"]] = transaction

                return history
        except UnicodeDecodeError as exc:
            last_error = exc

    raise RuntimeError(
        f"Unable to read history CSV {HISTORY_FILE}: {last_error}"
    )


def sort_transactions(transactions):
    """Sort transactions newest first."""
    return sorted(
        transactions,
        key=lambda transaction: (
            transaction.get("date") or "",
            transaction.get("merchant") or "",
            transaction.get("id") or "",
        ),
        reverse=True,
    )


def sort_events(events):
    """Sort event records newest first using their current transaction values."""
    return sorted(
        events,
        key=lambda event: (
            event["transaction"].get("date") or "",
            event["transaction"].get("merchant") or "",
            event["transaction"].get("id") or "",
            event["event_id"],
        ),
        reverse=True,
    )


def save_history_csv(history):
    """Write a flat current-history CSV, one row per retained transaction."""
    transactions = sort_transactions(list(history.values()))

    standard_fields = [
        "id",
        "date",
        "merchant",
        "amount",
        "account",
        "category",
    ]

    source_fields = [
        field
        for field in all_source_columns(transactions)
        if field not in standard_fields
    ]

    fieldnames = standard_fields + source_fields

    with open(
        HISTORY_FILE,
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
            extrasaction="ignore",
        )

        writer.writeheader()

        for transaction in transactions:
            writer.writerow(
                transaction_to_flat_row(
                    transaction,
                    source_fields,
                )
            )

    print(f"Saved {len(transactions)} historical transactions")
    print(f"History output: {HISTORY_FILE}")


def write_duplicates_csv(duplicates):
    """
    Write raw rows whose actual nonblank Monarch Id appeared earlier in the
    same raw export. Rows without an Id are retained and never called duplicates.
    """
    transactions = [
        item["transaction"]
        for item in duplicates
    ]

    fixed_fields = [
        "duplicate_of_id",
        "duplicate_reason",
        "id",
        "date",
        "merchant",
        "amount",
        "account",
        "category",
    ]

    source_fields = [
        field
        for field in all_source_columns(transactions)
        if field not in fixed_fields
    ]

    fieldnames = fixed_fields + source_fields

    with open(
        DUPLICATES_FILE,
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
            extrasaction="ignore",
        )

        writer.writeheader()

        for item in duplicates:
            transaction = item["transaction"]

            row = {
                "duplicate_of_id": item["duplicate_of_id"],
                "duplicate_reason": (
                    "Repeated Monarch Id in this raw export"
                ),
                **transaction_to_flat_row(
                    transaction,
                    source_fields,
                ),
            }

            writer.writerow(row)

    print(f"Saved {len(duplicates)} duplicate raw row(s)")
    print(f"Duplicates output: {DUPLICATES_FILE}")


def init_database():
    """
    Create internal persistent state and a delivery outbox.

    JSON is stored internally in SQLite to preserve full comparisons; no
    output CSV includes JSON columns.
    """
    connection = sqlite3.connect(STATE_DB)

    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS transactions (
                transaction_id TEXT PRIMARY KEY,
                fingerprint TEXT NOT NULL,
                transaction_json TEXT NOT NULL,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                last_changed_at TEXT NOT NULL
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                source_csv TEXT NOT NULL,
                period_label TEXT NOT NULL,
                status TEXT NOT NULL,
                transaction_count INTEGER NOT NULL DEFAULT 0,
                new_count INTEGER NOT NULL DEFAULT 0,
                changed_count INTEGER NOT NULL DEFAULT 0,
                delivered_at TEXT
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS outbox (
                event_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                transaction_id TEXT NOT NULL,
                fingerprint TEXT NOT NULL,
                change_type TEXT NOT NULL,
                previous_transaction_json TEXT,
                transaction_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                delivery_status TEXT NOT NULL DEFAULT 'pending',
                delivered_at TEXT,
                UNIQUE(transaction_id, fingerprint),
                FOREIGN KEY(run_id) REFERENCES runs(run_id)
            )
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_outbox_status_created
            ON outbox(delivery_status, created_at)
            """
        )

        connection.commit()

    finally:
        connection.close()


def compare_and_record(transactions, source_csv, period_label):
    """
    Compare genuine Monarch-Id transactions to persistent state.

    It creates an outbox event only once for a particular Monarch Id plus
    transaction fingerprint, even if a scheduled job repeats the same export.
    """
    run_id = str(uuid.uuid4())
    now = utc_now()

    connection = sqlite3.connect(STATE_DB)
    connection.row_factory = sqlite3.Row

    try:
        connection.execute("BEGIN IMMEDIATE")

        connection.execute(
            """
            INSERT INTO runs (
                run_id,
                created_at,
                source_csv,
                period_label,
                status,
                transaction_count
            )
            VALUES (?, ?, ?, ?, 'created', ?)
            """,
            (
                run_id,
                now,
                str(source_csv),
                period_label,
                len(transactions),
            ),
        )

        new_count = 0
        changed_count = 0

        for transaction in transactions:
            tx_id = transaction["id"]

            if not tx_id:
                continue

            fingerprint = transaction_fingerprint(transaction)

            current_json = json.dumps(
                transaction,
                ensure_ascii=False,
                sort_keys=True,
            )

            stored = connection.execute(
                """
                SELECT fingerprint, transaction_json
                FROM transactions
                WHERE transaction_id = ?
                """,
                (tx_id,),
            ).fetchone()

            if stored is None:
                change_type = "new"
                previous_json = None
                new_count += 1

                connection.execute(
                    """
                    INSERT INTO transactions (
                        transaction_id,
                        fingerprint,
                        transaction_json,
                        first_seen_at,
                        last_seen_at,
                        last_changed_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        tx_id,
                        fingerprint,
                        current_json,
                        now,
                        now,
                        now,
                    ),
                )

            elif stored["fingerprint"] != fingerprint:
                change_type = "changed"
                previous_json = stored["transaction_json"]
                changed_count += 1

                connection.execute(
                    """
                    UPDATE transactions
                    SET fingerprint = ?,
                        transaction_json = ?,
                        last_seen_at = ?,
                        last_changed_at = ?
                    WHERE transaction_id = ?
                    """,
                    (
                        fingerprint,
                        current_json,
                        now,
                        now,
                        tx_id,
                    ),
                )

            else:
                connection.execute(
                    """
                    UPDATE transactions
                    SET last_seen_at = ?
                    WHERE transaction_id = ?
                    """,
                    (now, tx_id),
                )
                continue

            event_id = hashlib.sha256(
                f"{tx_id}|{fingerprint}".encode("utf-8")
            ).hexdigest()

            connection.execute(
                """
                INSERT OR IGNORE INTO outbox (
                    event_id,
                    run_id,
                    transaction_id,
                    fingerprint,
                    change_type,
                    previous_transaction_json,
                    transaction_json,
                    created_at,
                    delivery_status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')
                """,
                (
                    event_id,
                    run_id,
                    tx_id,
                    fingerprint,
                    change_type,
                    previous_json,
                    current_json,
                    now,
                ),
            )

        connection.execute(
            """
            UPDATE runs
            SET status = 'ready',
                new_count = ?,
                changed_count = ?
            WHERE run_id = ?
            """,
            (
                new_count,
                changed_count,
                run_id,
            ),
        )

        connection.commit()

        return run_id, new_count, changed_count

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def get_all_pending_events():
    """
    Return every pending event from every unconsumed run.

    This is what prevents a later scheduled run from hiding the earlier
    unconsumed events in the consumer-facing output CSVs.
    """
    connection = sqlite3.connect(STATE_DB)
    connection.row_factory = sqlite3.Row

    try:
        rows = connection.execute(
            """
            SELECT
                event_id,
                run_id,
                change_type,
                previous_transaction_json,
                transaction_json,
                delivery_status
            FROM outbox
            WHERE delivery_status = 'pending'
            ORDER BY created_at, event_id
            """
        ).fetchall()

        events = []

        for row in rows:
            events.append(
                {
                    "event_id": row["event_id"],
                    "run_id": row["run_id"],
                    "change_type": row["change_type"],
                    "delivery_status": row["delivery_status"],
                    "previous_transaction": (
                        json.loads(row["previous_transaction_json"])
                        if row["previous_transaction_json"]
                        else None
                    ),
                    "transaction": json.loads(
                        row["transaction_json"]
                    ),
                }
            )

        return events

    finally:
        connection.close()


def write_new_transactions_csv(events):
    """
    Write every pending `new` event across all unconsumed runs.

    This file is regenerated each run, but old unconsumed events remain in it.
    """
    new_events = [
        event
        for event in events
        if event["change_type"] == "new"
    ]

    transactions = [
        event["transaction"]
        for event in new_events
    ]

    fixed_fields = [
        "run_id",
        "event_id",
        "delivery_status",
        "change_type",
        "id",
        "date",
        "merchant",
        "amount",
        "account",
        "category",
    ]

    source_fields = [
        field
        for field in all_source_columns(transactions)
        if field not in fixed_fields
    ]

    fieldnames = fixed_fields + source_fields

    with open(
        NEW_FILE,
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
            extrasaction="ignore",
        )

        writer.writeheader()

        for event in sort_events(new_events):
            row = {
                "run_id": event["run_id"],
                "event_id": event["event_id"],
                "delivery_status": event["delivery_status"],
                "change_type": "new",
                **transaction_to_flat_row(
                    event["transaction"],
                    source_fields,
                ),
            }

            writer.writerow(row)

    print(f"Saved {len(new_events)} pending new transaction(s)")
    print(f"New output: {NEW_FILE}")


def write_changed_transactions_csv(events):
    """
    Write every pending `changed` event across all unconsumed runs.

    Current values use ordinary columns; immediately prior values use
    `previous_` columns. No output column contains JSON.
    """
    changed_events = [
        event
        for event in events
        if event["change_type"] == "changed"
    ]

    current_transactions = [
        event["transaction"]
        for event in changed_events
    ]

    previous_transactions = [
        event["previous_transaction"]
        for event in changed_events
        if event["previous_transaction"] is not None
    ]

    base_fields = [
        "id",
        "date",
        "merchant",
        "amount",
        "account",
        "category",
    ]

    source_fields = [
        field
        for field in all_source_columns(
            current_transactions + previous_transactions
        )
        if field not in base_fields
    ]

    current_fields = base_fields + source_fields

    fieldnames = [
        "run_id",
        "event_id",
        "delivery_status",
        "change_type",
        *current_fields,
        *[
            f"previous_{field}"
            for field in current_fields
            if field != "id"
        ],
    ]

    with open(
        CHANGED_FILE,
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
            extrasaction="ignore",
        )

        writer.writeheader()

        for event in sort_events(changed_events):
            current = transaction_to_flat_row(
                event["transaction"],
                source_fields,
            )

            row = {
                "run_id": event["run_id"],
                "event_id": event["event_id"],
                "delivery_status": event["delivery_status"],
                "change_type": "changed",
                **current,
            }

            for field in current_fields:
                if field != "id":
                    row[f"previous_{field}"] = ""

            previous_transaction = event["previous_transaction"]

            if previous_transaction is not None:
                previous = transaction_to_flat_row(
                    previous_transaction,
                    source_fields,
                )

                for field in current_fields:
                    if field != "id":
                        row[f"previous_{field}"] = previous.get(
                            field,
                            "",
                        )

            writer.writerow(row)

    print(
        f"Saved {len(changed_events)} pending changed transaction(s)"
    )
    print(f"Changed output: {CHANGED_FILE}")


def mark_run_delivered(run_id):
    """
    Mark pending events in a run as delivered.

    Do this only once your consumer has successfully finished every applicable
    row for that RUN_ID in both new_transactions.csv and
    changed_transactions.csv.
    """
    now = utc_now()
    connection = sqlite3.connect(STATE_DB)

    try:
        connection.execute("BEGIN IMMEDIATE")

        pending_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM outbox
            WHERE run_id = ?
              AND delivery_status = 'pending'
            """,
            (run_id,),
        ).fetchone()[0]

        if pending_count == 0:
            raise RuntimeError(
                f"No pending events found for run ID: {run_id}"
            )

        connection.execute(
            """
            UPDATE outbox
            SET delivery_status = 'delivered',
                delivered_at = ?
            WHERE run_id = ?
              AND delivery_status = 'pending'
            """,
            (now, run_id),
        )

        connection.execute(
            """
            UPDATE runs
            SET status = 'delivered',
                delivered_at = ?
            WHERE run_id = ?
            """,
            (now, run_id),
        )

        connection.commit()

        print(
            f"Marked {pending_count} event(s) delivered "
            f"for run ID: {run_id}"
        )

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


async def wait_for_manual_login(page):
    """Pause for interactive Monarch login and any required 2FA."""
    print()
    print("Monarch login or 2FA is required.")
    print("Complete login and 2FA in the browser window.")
    print("When the Transactions page is available, press ENTER here.")

    await asyncio.to_thread(input)

    await page.goto(
        TRANSACTIONS_URL,
        wait_until="domcontentloaded",
        timeout=PAGE_TIMEOUT_MS,
    )


def login_required(page):
    """Identify likely URL patterns for Monarch authentication screens."""
    url = page.url.lower()

    return (
        "/login" in url
        or "sign-in" in url
        or "signin" in url
        or "/auth" in url
    )


async def goto_transactions(page, headed):
    """Open Transactions and handle an expired persistent browser session."""
    await page.goto(
        TRANSACTIONS_URL,
        wait_until="domcontentloaded",
        timeout=PAGE_TIMEOUT_MS,
    )

    if login_required(page):
        if not headed:
            raise RuntimeError(
                "Monarch session expired. Run with --headed, complete "
                "login/2FA, then try the scheduled job again."
            )

        await wait_for_manual_login(page)

    date_button = page.get_by_role(
        "button",
        name="Date",
        exact=True,
    )

    try:
        await date_button.wait_for(
            state="visible",
            timeout=PAGE_TIMEOUT_MS,
        )
    except PlaywrightTimeoutError as exc:
        if login_required(page) and headed:
            await wait_for_manual_login(page)

            await date_button.wait_for(
                state="visible",
                timeout=PAGE_TIMEOUT_MS,
            )
        else:
            raise RuntimeError(
                "Transactions page did not become ready within "
                f"{PAGE_TIMEOUT_MS // 1000} seconds."
            ) from exc

    return date_button


async def apply_period_filter(page, date_button, period_label):
    """Apply a supported date-preset label in Monarch's Date filter."""
    print("Transactions page loaded.")
    print("Opening Date filter...")

    await date_button.click(timeout=PAGE_TIMEOUT_MS)

    period_option = page.get_by_text(
        period_label,
        exact=True,
    )

    await period_option.wait_for(
        state="visible",
        timeout=PAGE_TIMEOUT_MS,
    )

    print(f"Selecting {period_label}...")
    await period_option.click(timeout=PAGE_TIMEOUT_MS)

    await page.wait_for_timeout(1_500)


async def download_csv_with_retries(page):
    """Download a verified nonempty CSV with retry handling."""
    last_error = None

    for attempt in range(1, DOWNLOAD_RETRIES + 1):
        try:
            download_csv = page.get_by_role(
                "button",
                name="Download CSV",
                exact=True,
            )

            await download_csv.wait_for(
                state="visible",
                timeout=PAGE_TIMEOUT_MS,
            )

            print(
                f"Downloading CSV "
                f"(attempt {attempt}/{DOWNLOAD_RETRIES})..."
            )

            timestamp = datetime.now().strftime(
                "%Y%m%d-%H%M%S"
            )

            output_path = RAW_DIR / (
                f"monarch-{timestamp}-attempt{attempt}.csv"
            )

            async with page.expect_download(
                timeout=DOWNLOAD_TIMEOUT_MS
            ) as download_info:
                await download_csv.click(timeout=PAGE_TIMEOUT_MS)

            download = await download_info.value
            failure = await download.failure()

            if failure:
                raise RuntimeError(
                    f"Browser download failure: {failure}"
                )

            await download.save_as(str(output_path))

            if not output_path.exists():
                raise RuntimeError(
                    "Browser reported a download but no CSV was saved."
                )

            if output_path.stat().st_size == 0:
                raise RuntimeError("Downloaded CSV is empty.")

            print(f"Downloaded: {output_path}")
            return output_path

        except (
            PlaywrightTimeoutError,
            RuntimeError,
        ) as exc:
            last_error = exc

            print(
                f"Download attempt {attempt} failed: {exc}"
            )

            if attempt < DOWNLOAD_RETRIES:
                await page.wait_for_timeout(3_000)

    raise RuntimeError(
        f"CSV download failed after {DOWNLOAD_RETRIES} attempt(s): "
        f"{last_error}"
    )


async def download_monarch_csv(headed, period_label):
    """Open Monarch, select the requested period, and save a raw CSV export."""
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=not headed,
            accept_downloads=True,
            viewport={
                "width": 1440,
                "height": 1000,
            },
        )

        page = (
            browser.pages[0]
            if browser.pages
            else await browser.new_page()
        )

        page.set_default_timeout(PAGE_TIMEOUT_MS)
        page.set_default_navigation_timeout(PAGE_TIMEOUT_MS)

        try:
            print("Opening Monarch...")

            date_button = await goto_transactions(
                page,
                headed=headed,
            )

            await apply_period_filter(
                page,
                date_button,
                period_label,
            )

            return await download_csv_with_retries(page)

        except Exception:
            timestamp = datetime.now().strftime(
                "%Y%m%d-%H%M%S"
            )

            debug_png = OUTPUT_DIR / (
                f"monarch-debug-{timestamp}.png"
            )
            debug_html = OUTPUT_DIR / (
                f"monarch-debug-{timestamp}.html"
            )

            try:
                await page.screenshot(
                    path=str(debug_png),
                    full_page=True,
                )

                debug_html.write_text(
                    await page.content(),
                    encoding="utf-8",
                )

                print(f"Debug screenshot: {debug_png}")
                print(f"Debug HTML: {debug_html}")
            except Exception:
                pass

            raise

        finally:
            await browser.close()


async def run_export(headed, period_label):
    """Export, deduplicate, queue changes, and regenerate pending CSV backlog."""
    raw_csv_path = await download_monarch_csv(
        headed=headed,
        period_label=period_label,
    )

    raw_transactions = read_csv(raw_csv_path)

    if not raw_transactions:
        raise RuntimeError(
            "Monarch CSV contained no transactions. "
            "No history or delivery state was changed."
        )

    unique_transactions = {}
    duplicates = []
    idless_transactions = []

    for transaction in raw_transactions:
        monarch_id = transaction["id"]

        if not monarch_id:
            idless_transactions.append(transaction)
            continue

        if monarch_id in unique_transactions:
            duplicates.append(
                {
                    "transaction": transaction,
                    "duplicate_of_id": monarch_id,
                }
            )
            continue

        unique_transactions[monarch_id] = transaction

    write_duplicates_csv(duplicates)

    history = load_history_csv()
    history_before = len(history)

    for transaction in unique_transactions.values():
        history[transaction["id"]] = transaction

    for transaction in idless_transactions:
        history[transaction["row_key"]] = transaction

    run_id, new_count, changed_count = compare_and_record(
        list(unique_transactions.values()),
        raw_csv_path,
        period_label,
    )

    save_history_csv(history)

    # Critical: regenerate consumer files from every pending event, not merely
    # this run. Therefore later scheduled runs do not conceal old unconsumed
    # transactions.
    all_pending_events = get_all_pending_events()
    write_new_transactions_csv(all_pending_events)
    write_changed_transactions_csv(all_pending_events)

    pending_new_count = sum(
        1
        for event in all_pending_events
        if event["change_type"] == "new"
    )

    pending_changed_count = sum(
        1
        for event in all_pending_events
        if event["change_type"] == "changed"
    )

    print()
    print(f"Period: {period_label}")
    print(f"Current run ID: {run_id}")
    print(f"Raw export rows: {len(raw_transactions)}")
    print(
        f"Unique Monarch-ID transactions retained: "
        f"{len(unique_transactions)}"
    )
    print(
        f"Repeated Monarch-ID rows removed: "
        f"{len(duplicates)}"
    )
    print(
        f"Rows without Monarch Id retained but not tracked: "
        f"{len(idless_transactions)}"
    )
    print(
        f"Historical transaction count: "
        f"{history_before} -> {len(history)}"
    )
    print(f"New events created in current run: {new_count}")
    print(f"Changed events created in current run: {changed_count}")
    print(f"All pending new events: {pending_new_count}")
    print(f"All pending changed events: {pending_changed_count}")

    if all_pending_events:
        print()
        print(
            "The output files include all still-pending events from every run:"
        )
        print(f"  {NEW_FILE}")
        print(f"  {CHANGED_FILE}")
        print()
        print(
            "After the consumer finishes a specific run, mark that run "
            "delivered using its run ID:"
        )
        print(
            f"python .\\monarch_extract.py "
            f"--mark-delivered {run_id}"
        )
    else:
        print()
        print("No pending new or changed transactions require processing.")


async def main():
    parser = argparse.ArgumentParser(
        description=(
            "Export Monarch transactions to flat CSV reports and retain "
            "all pending events until a downstream consumer acknowledges them."
        )
    )

    parser.add_argument(
        "--headed",
        action="store_true",
        help="Show the browser window.",
    )

    parser.add_argument(
        "--login",
        action="store_true",
        help="Show browser for Monarch login or 2FA.",
    )

    parser.add_argument(
        "--period",
        type=normalize_period,
        default=DEFAULT_PERIOD,
        metavar="PERIOD",
        help=(
            "Date filter. Default: '30 days'. Valid values: "
            "'7 days', '14 days', '30 days', 'This month', "
            "'Last month', 'This year', or 'Last year'. Invalid "
            "values default to '30 days'."
        ),
    )

    parser.add_argument(
        "--mark-delivered",
        metavar="RUN_ID",
        help=(
            "Mark pending events for one run as delivered after "
            "the downstream consumer succeeds."
        ),
    )

    args = parser.parse_args()

    init_database()

    if args.mark_delivered:
        mark_run_delivered(args.mark_delivered)
        return

    print()
    print("================================")
    print(" Monarch transaction export job")
    print("================================")
    print()

    await run_export(
        headed=args.headed or args.login,
        period_label=args.period,
    )

    print()
    print("Complete.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(1)
    except Exception as exc:
        print()
        print("ERROR:")
        print(str(exc))
        sys.exit(1)