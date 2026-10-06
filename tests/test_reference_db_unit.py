"""WP3.1: reference.db build tool, process-wide accessor and golden codec."""
from __future__ import annotations

import dataclasses
import shutil
import sqlite3
import threading
from collections import namedtuple

import pytest

from src.stores import RefData, RefDataError, StoreError, ValidationError
from src.stores import ref_access as refmod
from src.stores.ref_data import build
from src.stores.ref_getters.tax_update_dashboard import tax_update_dashboard
from tests.reference_golden import dumps
from tools import build_reference_db as tool


@pytest.fixture
def ref_reset(monkeypatch):
    monkeypatch.delenv(refmod.REFERENCE_DB_ENV, raising=False)
    refmod.set_reference_for_tests(None)
    yield
    refmod.set_reference_for_tests(None)


@pytest.fixture
def built(tmp_path):
    out = tmp_path / "reference.db"
    return out, tool.build_reference_db(out)


# ------------------------------------------------------------------ build tool
def test_two_builds_are_byte_identical(tmp_path, built):
    out, digest = built
    again = tmp_path / "again" / "reference.db"
    assert tool.build_reference_db(again) == digest
    assert out.read_bytes() == again.read_bytes()
    with RefData.open(out) as r:
        assert r.content_hash == digest
        assert r.data_version == f"{tool.REFERENCE_RELEASE}+{digest[:12]}"
        assert r.meta()["schema"] == "1"


def test_build_leaves_no_temp_files_and_rollback_journal_mode(built):
    out, _ = built
    assert sorted(p.name for p in out.parent.iterdir()) == ["reference.db"]
    con = sqlite3.connect(out)
    try:
        assert con.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    finally:
        con.close()


def test_check_detects_stale_and_missing(tmp_path, built):
    out, _ = built
    assert tool.check(out) == []
    assert tool.main(["--check", "--out", str(out)]) == 0
    stale = tmp_path / "stale.db"
    build(stale, {"tax_update_status": (["seq"], [(1,)])}, data_version="old")
    assert tool.check(stale) and tool.main(["--check", "--out", str(stale)]) == 1
    assert tool.check(tmp_path / "missing.db") == [f"{tmp_path / 'missing.db'} does not exist"]


def test_every_source_must_be_owned_and_present(tmp_path):
    src = tmp_path / "src"
    shutil.copytree(tool.SOURCE_DIR, src)
    (src / "stray.csv").write_text("a\n1\n", encoding="utf-8")
    with pytest.raises(tool.ReferenceBuildError, match="not owned"):
        tool.collect_tables(src)
    (src / "stray.csv").unlink()
    (src / "tax_update_dashboard.csv").unlink()
    with pytest.raises(tool.ReferenceBuildError, match="not found"):
        tool.collect_tables(src)


def test_build_sorts_rows_and_refuses_ambiguous_cells(tmp_path):
    p = tmp_path / "a.db"
    build(p, {"t": (["k", "v"], [(2, "b"), (None, "z"), (1, 1.0), (1, 1)])}, data_version="x")
    with RefData.open(p) as r:
        rows = [tuple(x.values()) for x in r.table("t")]
    assert rows == [(None, "z"), (1, 1.0), (1, 1), (2, "b")]
    assert [type(v) for v in rows[1]] == [int, float]  # stored exactly, no affinity coercion
    for bad in ([(True, "x")], [(1,)]):
        with pytest.raises(ValidationError):
            build(tmp_path / f"bad{len(bad[0])}.db", {"t": (["k", "v"], bad)}, data_version="x")


# -------------------------------------------------------------------- accessor
def test_accessor_resolution_order_and_caching(tmp_path, built, ref_reset, monkeypatch):
    out, digest = built
    assert refmod.reference_path() == refmod.shipped_reference_path()
    assert refmod.shipped_reference_path().parts[-3:] == ("src", "reference", "reference.db")
    other = tmp_path / "env" / "reference.db"
    tool.build_reference_db(other)
    monkeypatch.setenv(refmod.REFERENCE_DB_ENV, str(other))
    assert refmod.reference_path() == other
    refmod.set_reference_for_tests(out)
    assert refmod.reference_path() == out
    first = refmod.reference()
    assert first is refmod.reference() and first.path == str(out) and first.content_hash == digest
    refmod.set_reference_for_tests(None)
    assert refmod.reference().path == str(other)
    with pytest.raises(StoreError, match="closed"):
        first.query("SELECT 1")  # the replaced handle was closed


def test_accessor_verifies_hash_and_refuses_missing(tmp_path, built, ref_reset):
    out, _ = built
    tampered = tmp_path / "tampered.db"
    shutil.copy(out, tampered)
    con = sqlite3.connect(tampered)
    con.execute("UPDATE tax_update_status SET status='X' WHERE seq=0")
    con.commit()
    con.close()
    refmod.set_reference_for_tests(tampered)
    with pytest.raises(RefDataError, match="hash"):
        refmod.reference()
    refmod.set_reference_for_tests(tmp_path / "nope.db")
    with pytest.raises(RefDataError):
        refmod.reference()


def test_shared_handle_works_across_threads(built, ref_reset):
    refmod.set_reference_for_tests(built[0])
    expected = tax_update_dashboard()
    results, errors = [], []

    def work():
        try:
            results.append(tax_update_dashboard())
        except Exception as exc:  # pragma: no cover - reported below
            errors.append(exc)

    threads = [threading.Thread(target=work) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors and results == [expected] * 8


def test_getter_returns_fresh_objects(built, ref_reset):
    refmod.set_reference_for_tests(built[0])
    a = tax_update_dashboard()
    a[0]["status"] = "MUTATED"
    assert tax_update_dashboard()[0]["status"] != "MUTATED"
    assert all(type(r["blocking"]) is bool for r in a)


# ----------------------------------------------------------------------- codec
@dataclasses.dataclass(frozen=True)
class _DC:
    a: int
    b: tuple


_NT = namedtuple("_NT", "x y")


def test_codec_keeps_every_type_distinction():
    assert dumps(1) != dumps(1.0) and dumps(True) != dumps(1)
    assert dumps((1, 2)) != dumps([1, 2])
    assert dumps({2025: 1}) != dumps({"2025": 1})
    assert dumps({"a": 1, "b": 2}) != dumps({"b": 2, "a": 1})  # key order matters
    assert dumps({"$tuple": [1]}) != dumps((1,))
    assert dumps({("BASELINE", "us"): (0.1, 0.2)}) == dumps({("BASELINE", "us"): (0.1, 0.2)})
    assert dumps(_DC(1, (2,))) != dumps(_NT(1, (2,)))
    assert dumps({3, 1, 2}) == dumps({1, 2, 3})
    assert dumps(float("nan")) == "NaN\n"
    with pytest.raises(TypeError):
        dumps(object())
