"""WI-204 (ARC-003): rotating log file at bootstrap and audit rows reach SQLite."""
import logging
import sqlite3

import pytest

from src import bootstrap


@pytest.fixture
def clean_logger():
    logger = logging.getLogger(bootstrap.LOG_LOGGER_NAME)
    saved = list(logger.handlers)
    logger.handlers = []
    yield logger
    for h in logger.handlers:
        h.close()
    logger.handlers = saved


def test_configure_logging_writes_retrievable_file_and_is_idempotent(tmp_path, clean_logger):
    path = bootstrap.configure_logging(tmp_path / "logs")
    assert path == bootstrap.configure_logging(tmp_path / "other")
    assert len([h for h in clean_logger.handlers if getattr(h, bootstrap._LOG_HANDLER_TAG, False)]) == 1
    logging.getLogger("retirement_system.build").warning("materialize failed")
    for h in clean_logger.handlers:
        h.flush()
    assert "materialize failed" in path.read_text(encoding="utf-8")


def test_facade_logger_routes_through_logging(tmp_path, clean_logger):
    from src.http_runtime.wsgi_facade import _Logger
    path = bootstrap.configure_logging(tmp_path)
    _Logger().warning("hello %s", "world")
    for h in clean_logger.handlers:
        h.flush()
    assert "hello world" in path.read_text(encoding="utf-8")


def test_audit_log_enabled_by_default_and_opt_out(monkeypatch):
    from src.runtime_config import load_runtime_config
    monkeypatch.delenv("RETIREMENT_SYSTEM_AUDIT_LOG_ENABLED", raising=False)
    assert load_runtime_config().audit_log_enabled is True
    monkeypatch.setenv("RETIREMENT_SYSTEM_AUDIT_LOG_ENABLED", "NO")
    assert load_runtime_config().audit_log_enabled is False


def test_audit_inserts_audit_events_row(tmp_path, monkeypatch):
    from src.server import security_audit
    db = tmp_path / "t.db"
    monkeypatch.delenv("RETIREMENT_SYSTEM_AUDIT_LOG_ENABLED", raising=False)
    monkeypatch.setattr(security_audit._app_core, "_sqlite_db", lambda: db)
    monkeypatch.setattr(security_audit, "_workspace_output", lambda: tmp_path)
    security_audit._audit("secret_set", {"name": "x"})
    with sqlite3.connect(db) as conn:
        rows = conn.execute("select event from audit_events").fetchall()
    assert ("secret_set",) in rows
