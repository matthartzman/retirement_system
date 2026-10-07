"""A ``StrategyAssetService`` over a real plan file holding given rows, for unit tests that
exercise a service method without the Flask app (WP4.4b).

``read_plan`` and ``edit_plan`` are the real thing minus the CSV set: the plan's open store
(the edit has no write-back, there is no CSV set).
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from src.server_services.strategy_asset_service import StrategyAssetService, StrategyAssetServiceContext
from src.stores import PlanStore


def service_over_rows(tmp_path: Path, rows: list[tuple[str, str, str, str]], **context: Any):
    """``(service, store, audit_events)``; ``rows`` are ``(section, subsection, label, value)``.

    ``context`` overrides or adds ``StrategyAssetServiceContext`` fields."""
    store = PlanStore.open(tmp_path / "unit.rpx", create=True)
    for section, subsection, label, value in rows:
        store.insert_row(section, subsection=subsection, label=label, value=value)
    events: list[tuple[str, dict]] = []

    @contextmanager
    def read_plan():
        yield store

    @contextmanager
    def edit_plan():
        with store.transaction():
            yield SimpleNamespace(store=store)

    fields: dict[str, Any] = dict(
        base_dir=tmp_path,
        reference_file_path=lambda name: tmp_path / name,
        normalize_large_discretionary_type=lambda value: str(value),
        pre_tax_account_options_from_holdings=lambda: [],
        ensure_user_ui_plan_data_rows=lambda: None,
        sync_config_backends=lambda: {"success": True},
        audit=lambda event, details=None: events.append((event, details or {})),
        edit_plan=edit_plan,
        read_plan=read_plan,
    )
    fields.update(context)
    return StrategyAssetService(StrategyAssetServiceContext(**fields)), store, events
