"""local_settings is a declared-but-unused table; these pin the accessors."""
from __future__ import annotations

import tempfile
from pathlib import Path

from src.local_store import get_local_setting, set_local_setting


def _db() -> Path:
    return Path(tempfile.mkdtemp()) / "test_store.sqlite"


def test_missing_key_returns_default():
    assert get_local_setting("nope", 7, db_path=_db()) == 7


def test_roundtrip_int():
    p = _db()
    set_local_setting("schema", 3, db_path=p)
    assert get_local_setting("schema", 0, db_path=p) == 3


def test_set_overwrites_existing_key():
    p = _db()
    set_local_setting("schema", 2, db_path=p)
    set_local_setting("schema", 5, db_path=p)
    assert get_local_setting("schema", 0, db_path=p) == 5


def test_roundtrip_dict_survives_json():
    p = _db()
    set_local_setting("meta", {"a": 1, "b": [2, 3]}, db_path=p)
    assert get_local_setting("meta", None, db_path=p) == {"a": 1, "b": [2, 3]}


def test_corrupt_value_falls_back_to_default():
    """A hand-edited or half-written row must not take the app down at startup.

    This matters more than it looks: the first consumer of these helpers is the
    schema-version gate, which runs during boot. A json.JSONDecodeError here
    would abort startup on a database the user can still otherwise open.
    """
    import sqlite3
    from src.local_store import init_local_store, now_utc
    p = _db()
    init_local_store(p)
    with sqlite3.connect(p) as con:
        con.execute(
            "INSERT INTO local_settings(key, value_json, updated_at) VALUES(?,?,?)",
            ("bad", "{not json", now_utc()),
        )
    assert get_local_setting("bad", "fallback", db_path=p) == "fallback"
