"""WP2.1: connection helpers and forward-only schema versioning."""
import pytest

from src.stores import SchemaVersionError, StoreError, connect, get_version, migrate, transaction

M = ["CREATE TABLE a(x INTEGER);", "CREATE TABLE b(y TEXT); INSERT INTO b VALUES('s;t');"]


def test_migrate_fresh_and_idempotent():
    con = connect()
    assert get_version(con) == 0
    assert migrate(con, M) == 2
    assert get_version(con) == 2
    assert con.execute("SELECT y FROM b").fetchone()[0] == "s;t"
    assert migrate(con, M) == 2


def test_migrate_applies_only_tail():
    con = connect()
    migrate(con, M[:1])
    con.execute("INSERT INTO a VALUES(1)")
    migrate(con, M)
    assert con.execute("SELECT count(*) FROM a").fetchone()[0] == 1


def test_newer_db_refused():
    con = connect()
    migrate(con, M)
    with pytest.raises(SchemaVersionError):
        migrate(con, M[:1])


def test_failed_step_rolls_back_and_keeps_version():
    con = connect()
    with pytest.raises(SchemaVersionError):
        migrate(con, [M[0], "CREATE TABLE c(z); INSERT INTO nope VALUES(1);"])
    assert get_version(con) == 1
    assert con.execute("SELECT name FROM sqlite_master WHERE name='c'").fetchone() is None


def test_transaction_commit_rollback_and_nesting():
    con = connect()
    migrate(con, M)
    with transaction(con):
        con.execute("INSERT INTO a VALUES(1)")
    with pytest.raises(RuntimeError):
        with transaction(con):
            con.execute("INSERT INTO a VALUES(2)")
            raise RuntimeError
    with transaction(con):
        con.execute("INSERT INTO a VALUES(3)")
        with pytest.raises(RuntimeError):
            with transaction(con):
                con.execute("INSERT INTO a VALUES(4)")
                raise RuntimeError
    assert [r[0] for r in con.execute("SELECT x FROM a ORDER BY x")] == [1, 3]


def test_file_connection_wal_and_readonly(tmp_path):
    p = tmp_path / "d.db"
    con = connect(p)
    assert con.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    migrate(con, M)
    ro = connect(p, readonly=True)
    assert ro.execute("SELECT count(*) FROM a").fetchone()[0] == 0
    with pytest.raises(Exception):
        ro.execute("INSERT INTO a VALUES(1)")
    with pytest.raises(StoreError):
        connect(tmp_path / "missing.db", readonly=True)
