"""Concurrency regression tests for plan-CSV writes.

Background: the dashboard is served by ``ThreadingHTTPServer`` (one thread per
request), and several asset-add endpoints rewrite the same
``input/client_assets.csv``.  Two defects lived in that path:

1. Every writer derived its temp file as ``<name>.tmp`` -- a *fixed* name -- so
   concurrent writers opened the same temp path.  On Windows the second open
   made the first writer's ``replace()`` fail with ``WinError 32``; on POSIX the
   interleaved writes silently published a corrupt file.
2. The endpoints read, modified, and wrote without holding a lock across the
   cycle, so the second writer based its rows on the pre-edit snapshot and
   dropped the first writer's addition.

Fixing only (1) turns a visible 500 into silent data loss, so these tests assert
both that the requests succeed *and* that every addition survives.
"""

from __future__ import annotations

import csv
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def _run_concurrently(fns):
    """Run callables in parallel, released together to maximise overlap."""
    start = threading.Barrier(len(fns))

    def wrapped(fn):
        def run():
            start.wait(timeout=10)
            return fn()

        return run

    with ThreadPoolExecutor(max_workers=len(fns)) as pool:
        futures = [pool.submit(wrapped(fn)) for fn in fns]
        return [f.result(timeout=30) for f in futures]


def test_atomic_write_survives_concurrent_writers_to_one_path(tmp_path):
    from src.plan_file_io import atomic_write

    target = tmp_path / "client_assets.csv"
    writer_count = 8
    # Each writer emits a distinct, self-consistent 200-row payload. If two
    # writers ever shared a temp file, the published file would mix them.
    payloads = {
        i: [[f"writer-{i}", str(row)] for row in range(200)] for i in range(writer_count)
    }

    def write(i):
        def run():
            with atomic_write(target) as handle:
                csv.writer(handle, lineterminator="\n").writerows(payloads[i])

        return run

    _run_concurrently([write(i) for i in range(writer_count)])

    with target.open(newline="", encoding="utf-8-sig") as f:
        written = list(csv.reader(f))
    owners = {row[0] for row in written if row}
    assert len(owners) == 1, f"published file interleaved writers: {sorted(owners)}"
    assert written == payloads[int(owners.pop().split("-")[1])]
    assert list(tmp_path.glob("*.tmp")) == [], "temp files leaked into the plan directory"


def test_atomic_write_leaves_original_intact_when_writer_raises(tmp_path):
    from src.plan_file_io import atomic_write

    target = tmp_path / "client_assets.csv"
    target.write_text("section,subsection\noriginal,row\n", encoding="utf-8")

    class Boom(RuntimeError):
        pass

    try:
        with atomic_write(target) as handle:
            handle.write("partial")
            raise Boom
    except Boom:
        pass

    assert target.read_text(encoding="utf-8") == "section,subsection\noriginal,row\n"
    assert list(tmp_path.glob("*.tmp")) == [], "failed write leaked a temp file"


def test_plan_file_lock_is_reentrant_within_one_thread(tmp_path):
    """Endpoints hold the lock across read-modify-write, then the write helper
    re-acquires it for the same path. A non-reentrant lock would deadlock."""
    from src.plan_file_io import plan_file_lock

    target = tmp_path / "client_assets.csv"
    with plan_file_lock(target):
        with plan_file_lock(target):
            pass


def test_plan_file_lock_serialises_threads_on_the_same_path(tmp_path):
    from src.plan_file_io import plan_file_lock

    target = tmp_path / "client_assets.csv"
    overlaps = []
    active = 0
    guard = threading.Lock()

    def critical():
        nonlocal active
        with plan_file_lock(target):
            with guard:
                active += 1
                overlaps.append(active)
            # Long enough that unserialised threads would visibly overlap.
            threading.Event().wait(0.02)
            with guard:
                active -= 1

    _run_concurrently([critical for _ in range(6)])
    assert max(overlaps) == 1, f"threads entered the critical section together: {overlaps}"


def test_plan_file_lock_does_not_serialise_unrelated_paths(tmp_path):
    """A single global lock would work but would needlessly serialise every
    plan file; the lock must be per-path."""
    from src.plan_file_io import plan_file_lock

    held = threading.Event()
    released = threading.Event()

    def hold_first():
        with plan_file_lock(tmp_path / "client_assets.csv"):
            held.set()
            assert released.wait(timeout=5), "second path blocked on the first path's lock"

    def take_second():
        assert held.wait(timeout=5)
        with plan_file_lock(tmp_path / "client_liabilities.csv"):
            released.set()

    _run_concurrently([hold_first, take_second])


def test_shared_write_helpers_delegate_to_plan_file_io():
    """The same fixed-temp-name bug was copy-pasted across seven helpers; they
    must all route through the shared implementation so it cannot drift back."""
    root = Path(__file__).resolve().parents[1]
    offenders = []
    for rel in [
        "src/server/app_core.py",
        "src/server_services/admin_service.py",
        "src/ytd_tracking.py",
        "src/plan_data_backfill.py",
    ]:
        text = (root / rel).read_text(encoding="utf-8")
        if 'with_name(path.name + ".tmp")' in text:
            offenders.append(f"{rel} still derives a fixed temp name")
        if "atomic_write" not in text:
            offenders.append(f"{rel} does not use the shared atomic_write helper")
    assert offenders == []
