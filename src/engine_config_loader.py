from __future__ import annotations
"""Phase 1 seam for the DB-canonical migration (see
documentation/DB_CANONICAL_MIGRATION_PLAN.md).

This module is ADDITIVE: it introduces one new entry point,
``load_engine_config``, that can obtain the engine config either from
whatever the build uses today (``source='current'``), directly from the
canonical local SQLite plan snapshot (``source='db'``), or from an explicit
CSV/JSON/YAML adapter file (``source='import_file'``). It does not change any
existing call site, does not remove any CSV read, and does not alter default
build behavior — ``load_engine_config()`` with no arguments reproduces exactly
what ``config_backend.load_active_config()`` + ``report_compute.
prepare_config_from_sectioned_data()`` already do.

Both the 'db' and 'import_file' paths funnel through the same
``prepare_config_from_sectioned_data`` normalization that the current build
uses, so behavior (defaults, Roth optimization, engine-contract shaping) is
identical regardless of where the sectioned data came from — only the
*acquisition* of the sectioned dict differs.
"""

from pathlib import Path
from typing import Any, Dict, Optional

from . import config_backend as _config_backend
from .report_compute import prepare_config_from_sectioned_data

__all__ = ["load_engine_config"]

_VALID_SOURCES = {"current", "db", "import_file"}


def _bootstrap_sections() -> Dict[str, Any]:
    """Return the system-config sections merged into engine config today.

    Mirrors the merge ``config_backend.load_active_config`` performs so that
    'db' and 'import_file' sources see the same Market Pricing / Plan Settings
    / Asset Class Assumptions / Asset Correlations sections a normal build
    would merge in from the active bootstrap CSV.
    """
    bootstrap_csv = _config_backend.discover_bootstrap_csv()
    try:
        from .system_config import load_system_config
        return load_system_config(bootstrap_csv)
    except Exception:
        return {}


def _load_from_canonical_db(db_path: str | Path | None) -> Dict[str, Any]:
    """Read the sectioned adapter view of the canonical local plan snapshot.

    This bypasses config_backend.load_active_config()'s backend dispatch
    (CSV/JSON/YAML/SQLITE selection, bootstrap-from-CSV fallback) entirely and
    goes straight to local_store's plan_snapshots table, which is the
    canonical source of truth per the DB-canonical migration plan.
    """
    from .local_store import latest_sectioned_data

    resolved_db = _config_backend.resolve_path(db_path, _config_backend.DEFAULT_DB)
    data = latest_sectioned_data(resolved_db)
    return _config_backend._merge_system_config_sections(data, _bootstrap_sections())


def _load_from_import_file(path: str | Path | None, backend: Optional[str]) -> Dict[str, Any]:
    """Read an explicit CSV/JSON/YAML adapter file (an *import*, not the build path).

    This is the only source that touches an adapter file directly, and it does
    so only because the caller explicitly asked to import one — it is not part
    of any normal build's data acquisition.
    """
    if not path:
        raise ValueError("load_engine_config(source='import_file', ...) requires path=<adapter file>")
    p = Path(path)
    inferred = (backend or p.suffix.lstrip(".") or "csv").strip().upper()
    if inferred == "YML":
        inferred = "YAML"
    data = _config_backend.load_config(inferred, p)
    return _config_backend._merge_system_config_sections(data, _bootstrap_sections())


def load_engine_config(
    source: str = "current",
    *,
    path: str | Path | None = None,
    backend: str | None = None,
    db_path: str | Path | None = None,
    workspace_id: str | None = None,
    url_template: str = "",
    optimize_roth: bool = True,
) -> Dict[str, Any]:
    """Obtain the engine config from the given source.

    Parameters
    ----------
    source:
        - ``'current'`` (default): reproduce whatever the build uses today —
          ``config_backend.load_active_config()`` (CSV/JSON/YAML/SQLITE
          per the active System Configuration backend setting). This is the
          only source that preserves 100% of today's behavior, including the
          one-time CSV-to-SQLite bootstrap import inside
          ``load_active_config``. It is the default so nothing that calls
          ``load_engine_config()`` with no arguments changes behavior.
        - ``'db'``: read directly from the canonical local SQLite plan
          snapshot (``local_store.latest_sectioned_data``), independent of
          whatever the "active backend" System Configuration setting says.
          This is the Phase 2/3 target acquisition path.
        - ``'import_file'``: read a single explicit CSV/JSON/YAML adapter
          file (``path=...``), for explicit import flows only — not the
          normal build path.
    path:
        Adapter file path. Required for ``source='import_file'``; ignored
        (accepted as a ``cli_path`` override) for ``source='current'``.
    backend:
        Explicit backend name ("CSV" | "JSON" | "YAML" | "SQLITE"). For
        ``source='import_file'`` it overrides the extension-based inference.
        For ``source='current'`` it is passed through to
        ``load_active_config(cli_backend=...)``.
    db_path:
        SQLite database path. Used by ``source='db'``; ignored otherwise.
    workspace_id:
        Passed through to ``load_active_config`` for ``source='current'``.
    url_template, optimize_roth:
        Passed through to ``prepare_config_from_sectioned_data`` unchanged.

    Returns
    -------
    The same shape of dict that every other engine-config caller in this
    codebase (``report_compute.prepare_config_from_sectioned_data``,
    ``workbook_builder.main``, ``server_services.config_service``) already
    produces and consumes.
    """
    normalized_source = (source or "current").strip().lower()
    if normalized_source not in _VALID_SOURCES:
        raise ValueError(
            f"Unknown load_engine_config source {source!r}; expected one of {sorted(_VALID_SOURCES)}"
        )

    if normalized_source == "current":
        data, _meta = _config_backend.load_active_config(
            cli_backend=backend, cli_path=path, workspace_id=workspace_id
        )
    elif normalized_source == "db":
        data = _load_from_canonical_db(db_path)
    else:  # 'import_file'
        data = _load_from_import_file(path, backend)

    return prepare_config_from_sectioned_data(data, url_template, optimize_roth=optimize_roth)
