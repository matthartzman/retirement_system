"""Module loggers live under 'retirement_system.*'; startup migration is logged.

System review 2026-11-10, W1-03 / ARC-003. ``configure_logging`` attaches its
masking, size-bounded handler to the ``retirement_system`` logger only, so a
``getLogger(__name__)`` logger (``src.*``) never reaches it and its records are
lost. And ``run_startup_bootstrap`` used to drop migration errors silently.
"""
from __future__ import annotations

import ast
import logging
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_src_never_uses_getlogger_dunder_name():
    offenders = []
    for path in sorted((ROOT / "src").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "getLogger"
                and node.args
                and isinstance(node.args[0], ast.Name)
                and node.args[0].id == "__name__"
            ):
                offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert not offenders, f"use a 'retirement_system.*' logger name, not __name__: {offenders}"


@pytest.fixture
def app_log(tmp_path):
    from src import bootstrap

    env_before = dict(os.environ)  # run_startup_bootstrap sets local-mode env defaults
    root = logging.getLogger(bootstrap.LOG_LOGGER_NAME)
    before = list(root.handlers)
    level = root.level
    for h in before:
        if getattr(h, bootstrap._LOG_HANDLER_TAG, False):
            root.removeHandler(h)
    log_file = bootstrap.configure_logging(tmp_path)
    assert log_file is not None
    yield log_file
    for h in list(root.handlers):
        if h not in before:
            h.close()
            root.removeHandler(h)
    for h in before:
        if h not in root.handlers:
            root.addHandler(h)
    root.setLevel(level)
    os.environ.clear()
    os.environ.update(env_before)


def _flush():
    for h in logging.getLogger("retirement_system").handlers:
        h.flush()


def test_sales_tax_year_record_reaches_the_masking_handler(app_log):
    from src import sales_tax_year

    sales_tax_year.log.warning("lookup failed for account number 555566667777")  # acct-scan: ok
    _flush()
    text = app_log.read_text(encoding="utf-8")
    assert "retirement_system.sales_tax_year" in text
    assert "555566667777" not in text  # acct-scan: ok
    assert "7777" in text


def test_injected_migration_error_is_logged_by_run_startup_bootstrap(app_log, monkeypatch):
    from src import bootstrap
    import src.plan_data_migration as m

    monkeypatch.setattr(bootstrap, "_BOOTSTRAPPED", False)
    monkeypatch.setattr(
        m, "migrate_plan_data_at_rest",
        lambda *a, **k: {"migrated": {}, "total_changed": 0, "skipped": False, "error": "RuntimeError: injected"},
    )
    result = bootstrap.run_startup_bootstrap()
    _flush()
    assert result["error"].endswith("injected")
    text = app_log.read_text(encoding="utf-8")
    assert "startup plan-data migration failed" in text and "injected" in text


def test_a_raising_migration_is_logged_and_does_not_stop_startup(app_log, monkeypatch):
    from src import bootstrap
    import src.plan_data_migration as m

    monkeypatch.setattr(bootstrap, "_BOOTSTRAPPED", False)

    def boom():
        raise RuntimeError("kaboom")

    monkeypatch.setattr(m, "run_startup_plan_data_migration", boom)
    result = bootstrap.run_startup_bootstrap()
    _flush()
    assert result["skipped"] is True
    assert "kaboom" in app_log.read_text(encoding="utf-8")
