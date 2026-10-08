"""WP2.2: PlanStore (plan.db) API, revisions, retention, paths, repository interfaces."""
import hashlib
import json
import re
import sqlite3
from pathlib import Path

import pytest

from src.stores import (
    DEFAULT_REVISION_RETENTION,
    PLAN_SCHEMA_VERSION,
    AppStore,
    DatasetRepository,
    HoldingsLotsRepository,
    IntegrityError,
    NotFoundError,
    PlanStore,
    SchemaVersionError,
    StoreError,
    ValidationError,
    plan_paths,
)
from src.stores import db, errors
from src.stores.plan_store import PLAN_APPLICATION_ID, hash_rows

ROOT = Path(__file__).resolve().parents[1]


def _ticker():
    n = iter(range(1, 10_000))
    return lambda: f"2026-01-01T00:00:{next(n):02d}+00:00"


@pytest.fixture
def store():
    s = PlanStore.open(":memory:", clock=_ticker())
    yield s
    s.close()


# ------------------------------------------------------------------------ schema / open
def test_fresh_memory_store_schema(store):
    con = store._con
    assert store.schema_version == PLAN_SCHEMA_VERSION == 8
    assert con.execute("PRAGMA application_id").fetchone()[0] == PLAN_APPLICATION_ID
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"plan_rows", "plan_revisions", "revision_rows", "plan_meta"} <= tables
    assert store.sections() == []
    assert store.list_revisions() == []
    assert store.revision_retention == DEFAULT_REVISION_RETENTION
    assert store.revision() == hashlib.sha256(b"plan_rows/v1").hexdigest()


def test_file_store_persists_and_reopens(tmp_path):
    p = tmp_path / "My Plan.rpx"
    with PlanStore.open(p) as s:
        rid = s.insert_row("Household", label="Name", value="Pat")
        h = s.revision()
    assert p.is_file()
    with PlanStore.open(p, create=False) as s:
        assert s.get_row(rid)["value"] == "Pat"
        assert s.revision() == h
    with PlanStore.open(p, readonly=True) as s:
        assert s.rows("Household")[0]["label"] == "Name"
        with pytest.raises(StoreError, match="read-only"):
            s.insert_row("Household")
        with pytest.raises(StoreError, match="read-only"):
            with s.transaction():
                pass


def test_open_refusals(tmp_path):
    with pytest.raises(NotFoundError):
        PlanStore.open(tmp_path / "missing.rpx", create=False)
    with pytest.raises(NotFoundError):
        PlanStore.open(tmp_path / "missing.rpx", readonly=True)
    assert not (tmp_path / "missing.rpx").exists()
    with pytest.raises(NotFoundError):
        PlanStore.open(":memory:", create=False)
    with pytest.raises(StoreError):
        PlanStore.open(":memory:", readonly=True)

    empty = tmp_path / "empty.rpx"
    db.connect(empty).close()  # valid, uninitialised sqlite file
    with pytest.raises(NotFoundError, match="initialised"):
        PlanStore.open(empty, create=False)

    foreign = tmp_path / "foreign.db"
    con = db.connect(foreign)
    con.execute("CREATE TABLE t(x)")
    con.close()
    with pytest.raises(StoreError, match="not a valid plan.db"):
        PlanStore.open(foreign)

    app = tmp_path / "app.db"
    AppStore.open(app).close()
    with pytest.raises(StoreError, match="not a valid plan.db"):
        PlanStore.open(app)


def test_newer_schema_refused_and_readonly_needs_current(tmp_path):
    p = tmp_path / "p.rpx"
    PlanStore.open(p).close()
    con = sqlite3.connect(p)
    con.execute("PRAGMA user_version=99")
    con.close()
    with pytest.raises(SchemaVersionError):
        PlanStore.open(p)
    with pytest.raises(SchemaVersionError):
        PlanStore.open(p, readonly=True)


def test_close_context_manager_and_closed_errors():
    s = PlanStore.open()
    with s as same:
        assert same is s
    assert s.closed
    s.close()  # idempotent
    with pytest.raises(StoreError, match="closed"):
        s.rows("x")
    with pytest.raises(StoreError, match="closed"):
        s.insert_row("x")


# ---------------------------------------------------------------------------- rows
def test_insert_and_ordering(store):
    a = store.insert_row("Income", label="a")
    b = store.insert_row("Income", label="b")
    c = store.insert_row("Income", label="c", sort_order=0)  # ties with a -> row_id breaks tie
    z = store.insert_row("Assets", label="z")
    assert [r["row_id"] for r in store.rows("Income")] == [a, c, b]
    assert [r["sort_order"] for r in store.rows("Income")] == [0, 0, 1]
    assert store.rows("Assets")[0]["sort_order"] == 0
    assert store.sections() == ["Assets", "Income"]
    assert store.rows("Nope") == []
    row = store.get_row(z)
    assert type(row) is dict
    assert row == {"row_id": z, "section": "Assets", "subsection": "", "label": "z", "value": "",
                   "units": "", "notes": "", "sort_order": 0}
    assert [r["label"] for r in store.all_rows()] == ["z", "a", "c", "b"]


def test_set_row_and_delete(store):
    rid = store.insert_row("S", label="x", value="1")
    out = store.set_row(rid, value="2", notes="from # comment", sort_order=5)
    assert out["value"] == "2" and out["notes"] == "from # comment" and out["sort_order"] == 5
    assert store.get_row(rid) == out
    moved = store.set_row(rid, section="T")
    assert store.rows("S") == [] and store.rows("T") == [moved]
    store.delete_row(rid)
    with pytest.raises(NotFoundError):
        store.get_row(rid)
    with pytest.raises(NotFoundError):
        store.delete_row(rid)
    with pytest.raises(NotFoundError):
        store.set_row(rid, value="3")


@pytest.mark.parametrize(
    "kwargs",
    [{}, {"bogus": "x"}, {"value": 3}, {"value": None}, {"section": ""}, {"sort_order": "1"}, {"sort_order": True}],
)
def test_set_row_validation(store, kwargs):
    rid = store.insert_row("S", value="v")
    with pytest.raises(ValidationError):
        store.set_row(rid, **kwargs)
    assert store.get_row(rid)["value"] == "v"


def test_insert_validation(store):
    with pytest.raises(ValidationError):
        store.insert_row("")
    with pytest.raises(ValidationError):
        store.insert_row("S", value=1.5)
    with pytest.raises(ValidationError):
        store.insert_row("S", sort_order=1.0)
    with pytest.raises(ValidationError):
        store.get_row("1")
    assert store.sections() == []


def test_find_rows_and_set_value_write_the_effective_row(store):
    """WP4.1 keyed access: a repeated key's effective row is the last in display order."""
    a = store.insert_row("Scenarios", subsection="Base", label="mode", value="x")
    b = store.insert_row("Scenarios", subsection="Base", label="mode", value="y")
    assert [r["row_id"] for r in store.find_rows("Scenarios", "Base", "mode")] == [a, b]
    assert store.find_rows("Scenarios", "Base", "nope") == []
    assert store.set_value("Scenarios", "Base", "mode", "z") == b
    assert store.get_row(a)["value"] == "x" and store.get_row(b)["value"] == "z"
    store.set_row(a, sort_order=5)  # a now displays last, so it becomes the effective row
    assert store.set_value("Scenarios", "Base", "mode", "w", notes="n") == a
    assert store.get_row(a)["notes"] == "n" and store.get_row(a)["units"] == ""
    new = store.set_value("Plan Settings", "Profile", "plan_tier", "simple", units="choice")
    assert store.get_row(new) == {"row_id": new, "section": "Plan Settings", "subsection": "Profile",
                                  "label": "plan_tier", "value": "simple", "units": "choice", "notes": "",
                                  "sort_order": 0}
    with pytest.raises(ValidationError):
        store.set_value("Plan Settings", "Profile", "plan_tier", 3)
    with pytest.raises(ValidationError):
        store.set_value("", "Profile", "plan_tier", "x")


def test_set_value_inside_a_transaction_rolls_back_with_it(store):
    with pytest.raises(RuntimeError):
        with store.transaction():
            store.set_value("S", "", "k", "1")
            raise RuntimeError("boom")
    assert store.find_rows("S", "", "k") == []


def test_sectioned_data_is_the_load_csv_shape(store):
    store.insert_row("B", label="b", value=" 2 ")
    store.insert_row("A", subsection="s", label="x", value="1")
    store.insert_row("A", subsection="s", label="y", value="2")
    store.insert_row("A", subsection="s", label="x", value="3")       # repeated key: last wins
    store.insert_row("A", subsection="t", label="", value="ignored")  # no label: skipped
    store.insert_row("#C", label="z", value="ignored")               # comment section: skipped
    first_c = store.insert_row("C", label="c", value="0", sort_order=0)
    view = store.sectioned_data()
    assert view == {"B": {"": {"b": "2"}}, "A": {"s": {"x": "3", "y": "2"}}, "C": {"": {"c": "0"}}}
    assert list(view) == ["B", "A", "C"]  # sections in creation order, not by name or sort_order
    assert list(view["A"]["s"]) == ["x", "y"]
    store.delete_row(first_c)
    assert "C" not in store.sectioned_data()


def test_row_ids_are_never_reused(store):
    a = store.insert_row("S")
    b = store.insert_row("S")
    store.delete_row(b)
    c = store.insert_row("S")
    assert c > b > a


# ---------------------------------------------------------------------- transactions
def test_transaction_commits_and_rolls_back(store):
    with store.transaction() as s:
        assert s is store
        store.insert_row("S", label="1")
        store.insert_row("S", label="2")
    assert len(store.rows("S")) == 2
    with pytest.raises(RuntimeError):
        with store.transaction():
            store.insert_row("S", label="3")
            store.set_row(store.rows("S")[0]["row_id"], value="changed")
            raise RuntimeError
    assert [r["label"] for r in store.rows("S")] == ["1", "2"]
    assert all(r["value"] == "" for r in store.rows("S"))


def test_failed_write_inside_transaction_rolls_back_only_itself(store):
    with store.transaction():
        store.insert_row("S", label="kept")
        with pytest.raises(NotFoundError):
            store.set_row(9999, value="x")
        with pytest.raises(StoreError):
            with store.transaction():  # nested block -> savepoint
                store.insert_row("S", label="dropped")
                raise StoreError("abort inner")
    assert [r["label"] for r in store.rows("S")] == ["kept"]


def test_bare_write_failure_is_atomic(store):
    rid = store.insert_row("S", value="v")
    store.snapshot_revision("t")
    rev = store.list_revisions()[0]["id"]
    store.set_row(rid, value="after")
    # A copy that passes the hash check but violates plan_rows' CHECK (empty section):
    # restore gets as far as the backup snapshot and the DELETE before the INSERT fails.
    con = store._con
    con.execute("UPDATE revision_rows SET section = ''")
    con.execute("UPDATE plan_revisions SET rows_sha256 = ?", (hash_rows([("", "", "", "v", "", "")]),))
    before_revs = store.list_revisions()
    with pytest.raises(IntegrityError):
        store.restore_revision(rev)  # must leave rows and revisions exactly as they were
    assert store.get_row(rid)["value"] == "after"
    assert store.list_revisions() == before_revs
    assert not con.in_transaction

    con.execute("UPDATE revision_rows SET value = 'tampered'")
    with pytest.raises(IntegrityError, match="hash"):
        store.restore_revision(rev)


def test_sqlite_errors_are_mapped(store):
    with pytest.raises(IntegrityError):
        with store.transaction() as s:
            s._con.execute("INSERT INTO plan_rows(section, sort_order) VALUES ('', 0)")
    with pytest.raises(StoreError) as ei:
        with store.transaction() as s:
            s._con.execute("SELECT * FROM no_such_table")
    assert isinstance(ei.value.__cause__, sqlite3.Error)


# --------------------------------------------------------------------------- revision
def _fill(s, rows):
    for sec, label, value in rows:
        s.insert_row(sec, label=label, value=value)


def test_revision_is_content_and_order_not_ids():
    data = [("B", "b1", "1"), ("A", "a1", "x"), ("A", "a2", "é ✓"), ("B", "b2", "2")]
    with PlanStore.open() as s1, PlanStore.open() as s2:
        _fill(s1, data)
        # same content, different ids (gaps) and sort_order numbers
        for _ in range(5):
            s2.delete_row(s2.insert_row("junk"))
        s2.insert_row("A", label="a1", value="x", sort_order=10)
        s2.insert_row("B", label="b1", value="1", sort_order=100)
        s2.insert_row("A", label="a2", value="é ✓", sort_order=20)
        s2.insert_row("B", label="b2", value="2", sort_order=200)
        assert s1.revision() == s2.revision()

        # pin the canonical format
        canon = ["plan_rows/v1"] + [
            json.dumps([sec, "", label, value, "", ""], ensure_ascii=False, separators=(",", ":"))
            for sec, label, value in sorted(data, key=lambda t: (t[0], t[1]))
        ]
        assert s1.revision() == hashlib.sha256("\n".join(canon).encode("utf-8")).hexdigest()
        assert re.fullmatch(r"[0-9a-f]{64}", s1.revision())

        h = s1.revision()
        rid = s1.rows("A")[0]["row_id"]
        s1.set_row(rid, notes="n")
        assert s1.revision() != h
        s1.set_row(rid, notes="")
        assert s1.revision() == h
        s1.set_row(rid, sort_order=99)  # move a1 after a2
        assert s1.revision() != h


def test_hash_rows_accepts_dicts_and_tuples(store):
    _fill(store, [("A", "x", "1")])
    rows = store.all_rows()
    assert hash_rows(rows) == store.revision()
    assert hash_rows([("A", "", "x", "1", "", "")]) == store.revision()


def test_snapshot_list_and_restore(store):
    a = store.insert_row("S", label="a", value="1")
    b = store.insert_row("S", label="b", value="2")
    h1 = store.revision()
    r1 = store.snapshot_revision("manual", "first")
    revs = store.list_revisions()
    assert revs == [{"id": r1, "created_at": "2026-01-01T00:00:01+00:00", "source": "manual", "note": "first",
                     "rows_sha256": h1, "row_count": 2}]
    assert [r["row_id"] for r in store.revision_rows(r1)] == [a, b]

    store.set_row(a, value="changed")
    store.delete_row(b)
    c = store.insert_row("T", label="new")
    h2 = store.revision()

    backup = store.restore_revision(r1)
    assert store.revision() == h1
    assert [r["row_id"] for r in store.rows("S")] == [a, b]  # original ids come back
    assert store.rows("T") == []
    latest = store.list_revisions()[0]
    assert latest["id"] == backup and latest["source"] == "pre-restore" and latest["rows_sha256"] == h2
    assert store.insert_row("S") > c  # ids still not reused after restore

    assert store.restore_revision(backup, backup=False) is None
    assert store.revision() == h2
    assert len(store.list_revisions()) == 2

    with pytest.raises(NotFoundError):
        store.restore_revision(12345)
    with pytest.raises(NotFoundError):
        store.revision_rows(12345)
    with pytest.raises(ValidationError):
        store.snapshot_revision("")
    with pytest.raises(ValidationError):
        store.snapshot_revision("x", note=None)


def test_snapshot_of_empty_plan_and_restore(store):
    r0 = store.snapshot_revision("init")
    store.insert_row("S")
    store.restore_revision(r0, backup=False)
    assert store.sections() == []


def test_retention_prunes_oldest(store):
    store.insert_row("S")
    store.set_revision_retention(3)
    ids = [store.snapshot_revision("auto", str(i)) for i in range(5)]
    assert [r["id"] for r in store.list_revisions()] == ids[:1:-1]
    kept = {r[0] for r in store._con.execute("SELECT DISTINCT revision_id FROM revision_rows")}
    assert kept == set(ids[2:])
    store.set_revision_retention(1)
    assert [r["id"] for r in store.list_revisions()] == [ids[-1]]
    assert store.revision_retention == 1
    for bad in (0, -1, "2", 1.0, True):
        with pytest.raises(ValidationError):
            store.set_revision_retention(bad)


def test_meta(store):
    assert store.get_meta("plan_name") is None
    assert store.get_meta("plan_name", "dflt") == "dflt"
    store.set_meta("plan_name", "Ours")
    store.set_meta("plan_name", "Ours 2")
    assert store.get_meta("plan_name") == "Ours 2"
    with pytest.raises(ValidationError):
        store.set_meta("revision_retention", "5")
    with pytest.raises(ValidationError):
        store.set_meta("", "x")
    with pytest.raises(ValidationError):
        store.set_meta("k", 5)


# ----------------------------------------------------------------------- plan_paths
def test_plan_paths_from_base_dir(tmp_path):
    p = plan_paths("demo", base_dir=tmp_path)
    assert p.plan_id == "demo"
    assert p.outputs_dir == tmp_path / "output" / "plans" / "demo"
    assert p.backups_dir == tmp_path / "local_state" / "plan_backups" / "demo"
    assert not p.outputs_dir.exists() and not p.backups_dir.exists()
    assert plan_paths("a1b2", base_dir=tmp_path).outputs_dir != p.outputs_dir


def test_plan_paths_default_base_is_workspace_root(tmp_path, monkeypatch):
    monkeypatch.setenv("RETIREMENT_SYSTEM_WORKSPACE_ROOT", str(tmp_path))
    assert plan_paths("x").outputs_dir == tmp_path / "output" / "plans" / "x"


@pytest.mark.parametrize("bad", ["", "../x", "a/b", "a\\b", ".hidden", "-x", "con", "LPT1", "x" * 65, 5, None])
def test_plan_paths_rejects_unsafe_ids(tmp_path, bad):
    with pytest.raises(ValidationError):
        plan_paths(bad, base_dir=tmp_path)


# ------------------------------------------------------------------ repositories / errors
def test_repository_protocols_are_structural():
    class FakeHoldings:
        def __init__(self):
            self._rows = []

        def rows(self):
            return list(self._rows)

        def replace_all(self, rows):
            self._rows = list(rows)
            return len(self._rows)

    class NotARepo:
        def rows(self):
            return []

    assert isinstance(FakeHoldings(), HoldingsLotsRepository)
    assert isinstance(FakeHoldings(), DatasetRepository)
    assert not isinstance(NotARepo(), HoldingsLotsRepository)


def test_error_hierarchy_and_db_compat():
    assert db.StoreError is errors.StoreError and db.SchemaVersionError is errors.SchemaVersionError
    assert issubclass(IntegrityError, ValidationError)
    for cls in (NotFoundError, ValidationError, IntegrityError, SchemaVersionError):
        assert issubclass(cls, StoreError)
    assert issubclass(NotFoundError, LookupError) and issubclass(ValidationError, ValueError)


def test_product_code_reaches_the_plan_store_only_through_the_active_plan_module():
    """WP3 switched product code to the read-only reference getters. WP4.2 gave PlanStore
    its first consumers: the active plan accessor (src/active_plan.py), the at-rest
    row migration of a plan file (src/plan_data_migration.py) and the plan file replace
    validation (src/plan_db_replace.py). Everything else goes through src/active_plan.py. AppStore and the db helpers stay unused until WP8."""
    pat = re.compile(r"^\s*(from\s+(src\.stores|\.+stores)(\.\w+)?\s+import\s+[^\n]+|import\s+src\.stores\b[^\n]*)", re.M)
    allowed = ("ref_getters", "ref_access", "ref_data")
    # plan_db_replace opens a candidate plan file as a PlanStore to validate it before a swap (WP4.5)
    plan_store_users = {"src/active_plan.py", "src/plan_data_migration.py", "src/plan_db_replace.py"}
    offenders = []
    for f in (ROOT / "src").rglob("*.py"):
        if f.relative_to(ROOT / "src").parts[:1] == ("stores",):
            continue
        rel = f.relative_to(ROOT).as_posix()
        for m in pat.finditer(f.read_text(encoding="utf-8")):
            line = m.group(0)
            if any(a in line for a in allowed):
                continue
            if rel in plan_store_users and re.search(r"import\s+(PlanStore(,\s*StoreError)?|validate_plan_id(\s*#.*)?)\s*$", line.strip()):
                continue
            offenders.append(f"{rel}: {line.strip()}")
    assert offenders == []


def test_review_fixes_plan_id_newline_and_restore_keeps_target():
    import pytest
    from src.stores import PlanStore, ValidationError
    from src.stores.plan_store import validate_plan_id
    with pytest.raises(ValidationError):
        validate_plan_id("abc\n")
    s = PlanStore.open()
    s.insert_row("A", label="x", value="1")
    first = s.snapshot_revision("t")
    s.set_revision_retention(1)
    s.insert_row("A", label="y", value="2")
    s.restore_revision(first)
    assert any(r["id"] == first for r in s.list_revisions())
