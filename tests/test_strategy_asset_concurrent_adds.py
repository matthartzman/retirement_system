"""Regression test for the reported ``/api/note-receivable/add`` 500.

Repro from the bug report: ``addOtherAssetItem()``, ``addNoteReceivable()`` and
``addEducation529Section()`` fired in the same JS tick.  All three rewrite
``input/client_assets.csv``; the note-receivable request returned 500 with
``PermissionError: [WinError 32]`` from the temp-file replace.

Asserting only "all three return 200" is not enough -- serialising just the
write would satisfy that while two of the three additions were silently
clobbered, because each request reads the file, modifies its snapshot and
writes the whole thing back.  So these tests assert the additions survive.
"""

from __future__ import annotations

import csv
import threading
from concurrent.futures import ThreadPoolExecutor


def _service(tmp_path, read_delay=0.01):
    from src.plan_file_io import atomic_write
    from src.server_services.strategy_asset_service import (
        StrategyAssetService,
        StrategyAssetServiceContext,
    )

    header = ["section", "subsection", "label", "value", "units", "notes"]

    def read_rows(path):
        if not path.exists():
            return []
        with path.open(newline="", encoding="utf-8-sig") as f:
            rows = list(csv.reader(f))
        # Widen the read-modify-write window so an unserialised cycle loses an
        # edit reliably rather than occasionally.
        threading.Event().wait(read_delay)
        return rows

    def write_rows(path, rows):
        with atomic_write(path) as handle:
            csv.writer(handle, lineterminator="\n").writerows(rows)

    def ensure_header(rows):
        if not rows:
            return [list(header)]
        first = [str(x or "").strip().lower() for x in rows[0][:3]]
        if first[:3] != ["section", "subsection", "label"]:
            return [list(header), *rows]
        return rows

    ctx = StrategyAssetServiceContext(
        base_dir=tmp_path,
        plan_data_path=lambda name: tmp_path / name,
        client_section_path=lambda section, file_name: tmp_path / file_name,
        reference_file_path=lambda name: tmp_path / name,
        csv_read_rows=read_rows,
        csv_write_rows=write_rows,
        ensure_header=ensure_header,
        write_client_rows=write_rows,
        read_client_section_rows=lambda section, file_name: [],
        large_discretionary_expenses_from_plan_data=lambda: [],
        normalize_large_discretionary_type=lambda value: str(value),
        replace_large_discretionary_expenses=lambda events: None,
        pre_tax_account_options_from_holdings=lambda: [],
        forced_roth_conversions_from_csv_rows=lambda rows: [],
        replace_forced_roth_conversions=lambda conversions: None,
        liquidity_buffers_from_csv_rows=lambda rows: [],
        replace_liquidity_buffers=lambda buffers: None,
        ensure_user_ui_plan_data_rows=lambda: None,
        sync_config_backends=lambda: {"success": True},
        audit=lambda event, details=None: None,
    )
    return StrategyAssetService(ctx)


def _run_concurrently(fns):
    start = threading.Barrier(len(fns))

    def wrapped(fn):
        def run():
            start.wait(timeout=10)
            return fn()

        return run

    with ThreadPoolExecutor(max_workers=len(fns)) as pool:
        futures = [pool.submit(wrapped(fn)) for fn in fns]
        return [f.result(timeout=30) for f in futures]


def _sections(tmp_path):
    with (tmp_path / "client_assets.csv").open(newline="", encoding="utf-8-sig") as f:
        return [(r[0].strip(), r[1].strip()) for r in csv.reader(f) if len(r) >= 2]


def test_concurrent_asset_adds_all_succeed_and_all_survive(tmp_path):
    service = _service(tmp_path)

    results = _run_concurrently([
        lambda: service.add_other_asset_payload({"asset_type": "Auto"}),
        lambda: service.add_note_receivable_payload({"name": "Seller Note"}),
        lambda: service.add_education_529_payload(),
    ])

    statuses = [status for _payload, status in results]
    assert statuses == [200, 200, 200], f"an endpoint failed: {results}"

    sections = _sections(tmp_path)
    assert ("Other Assets", "Other Asset 1") in sections
    assert ("Note Receivable", "Note 1") in sections
    assert ("Education Funding", "529 Plan 1") in sections


def test_concurrent_note_adds_do_not_collide_on_one_subsection_id(tmp_path):
    """Two concurrent adds that both read the same snapshot would both compute
    ``Note 1`` and one would be clobbered."""
    service = _service(tmp_path)

    results = _run_concurrently([
        lambda: service.add_note_receivable_payload({"name": "First"}),
        lambda: service.add_note_receivable_payload({"name": "Second"}),
        lambda: service.add_note_receivable_payload({"name": "Third"}),
    ])
    assert [status for _payload, status in results] == [200, 200, 200]

    notes = [sub for section, sub in _sections(tmp_path) if section == "Note Receivable"]
    assert sorted(set(notes)) == ["Note 1", "Note 2", "Note 3"], f"got {sorted(set(notes))}"

    names = sorted(
        r[3]
        for r in csv.reader((tmp_path / "client_assets.csv").open(newline="", encoding="utf-8-sig"))
        if len(r) >= 4 and r[0].strip() == "Note Receivable" and r[2].strip() == "name"
    )
    assert names == ["First", "Second", "Third"], f"an add was lost: {names}"
