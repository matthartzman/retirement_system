"""WP2.3: RefData skeleton (read-only open, version, content hash, plain getters)."""
import sqlite3

import pytest

from src.stores import NotFoundError, RefData, RefDataError
from src.stores.ref_data import build

TABLES = {"tax": (["year", "key", "val"], [(2025, "std", 15000.0), (2025, "x", 1)]), "cma": (["a"], [("eq",)])}


def _make(tmp_path):
    p = tmp_path / "reference.db"
    return p, build(p, TABLES, data_version="2025.1")


def test_open_getters_and_hash(tmp_path):
    p, digest = _make(tmp_path)
    with RefData.open(p) as r:
        assert r.data_version == "2025.1" and r.content_hash == digest
        assert r.tables() == ["cma", "tax"]
        assert r.table("tax")[0] == {"year": 2025, "key": "std", "val": 15000.0}
        with pytest.raises(NotFoundError):
            r.table("nope")


def test_build_is_deterministic(tmp_path):
    assert _make(tmp_path)[1] == build(tmp_path / "b.db", TABLES, data_version="2025.1")


def test_missing_file_and_wrong_hash(tmp_path):
    with pytest.raises(RefDataError):
        RefData.open(tmp_path / "none.db")
    p, _ = _make(tmp_path)
    con = sqlite3.connect(p)
    con.execute("UPDATE tax SET val=1 WHERE key='std'")
    con.commit()
    con.close()
    with pytest.raises(RefDataError):
        RefData.open(p)
    RefData.open(p, verify=False).close()


def test_read_only_and_foreign_file(tmp_path):
    p, _ = _make(tmp_path)
    with RefData.open(p) as r:
        with pytest.raises(sqlite3.OperationalError):
            r._c().execute("DELETE FROM tax")
    q = tmp_path / "other.db"
    sqlite3.connect(q).execute("CREATE TABLE t(x)").connection.close()
    with pytest.raises(RefDataError):
        RefData.open(q)
