from __future__ import annotations
"""Runtime settings of this install: built-in defaults overlaid by ``app.db`` settings (WP8.1).

``system_config.csv`` is gone. The runtime flags (dashboard, security, governance, pricing,
downloads, build timeout ...) are the ``SYSTEM_DEFAULTS`` rows below; a value the user changes
is stored in ``AppStore`` ``settings`` under ``"section|subsection|label"`` (``setting_key``)
and a key that is unset reads its default. Engine knobs (Rebalancing, Asset Class Assumptions,
Asset Correlations, Annuity Calibration, Plan Settings) are plan rows with code defaults
(``engine_defaults``); the app version is ``src/version.py``.

Every ``path`` argument below is an ``app.db`` path (default ``app_state.app_store_path()``).
Reading never creates the database: a missing file reads as all defaults.
"""

import hashlib
import json
from pathlib import Path
from typing import Dict, Iterable

SettingMap = Dict[str, Dict[str, Dict[str, str]]]
Key = tuple[str, str, str]
SETTINGS_HEADER = ["section", "subsection", "label", "value", "units", "notes"]
KEY_SEPARATOR = "|"

_SC = "System Configuration"
# (section, subsection, label, value, units, notes): the defaults of a fresh install.
SYSTEM_DEFAULTS: tuple[tuple[str, str, str, str, str, str], ...] = (
    (_SC, "Runtime", "app_mode", "LOCAL", "choice", "Local desktop mode only; public-hosting and client-registry modes have been removed."),
    (_SC, "Runtime", "config_backend", "SQLITE", "choice", "SQLITE: the plan file (plan.rpx) holds the plan rows; CSV import/export arrives with csv_exchange."),
    (_SC, "Runtime", "output_dir", "output", "path", "Local output folder for generated workbook, PDF, and diagnostics."),
    (_SC, "Dashboard", "enabled", "YES", "yes/no", "Enable web dashboard routes in src/server/."),
    (_SC, "Dashboard", "host", "127.0.0.1", "text", "Local desktop host. Public/LAN binding has been removed from this package."),
    (_SC, "Dashboard", "port", "5050", "integer", "Dashboard port. Open this TCP port in the local OS firewall."),
    (_SC, "Security", "encryption_enabled", "NO", "yes/no", "YES encrypts API keys in SQLite/secret store. Requires cryptography package for strong encryption."),
    (_SC, "Security", "secrets_store", "local_state/secrets.db", "path", "Local encrypted/obfuscated API key storage for optional Plan Chat and pricing keys."),
    (_SC, "Price Refresh", "nightly_enabled", "TRUE", "yes/no", "YES enables scheduled/manual nightly price refresh tool."),
    (_SC, "Price Refresh", "nightly_time", "2:00", "HH:MM", "Preferred local refresh time for scheduler/cron."),
    (_SC, "Price Refresh", "snapshot_retention_days", "365", "days", "Historical price snapshot retention."),
    (_SC, "Portfolio Drift", "rebalance_threshold_pct", "5.00%", "pct", "Report assets outside target allocation by this absolute threshold."),
    ("Market Pricing", "Holdings", "pricing_mode", "LIVE", "choice", "CACHE = use any cache first, even stale; LIVE = prefer live providers before cache/fallback; OFFLINE = no live calls. Cost basis is used only when no cache exists."),
    ("Market Pricing", "Holdings", "cache_hours", "24", "hours", "Fresh cache window for holdings prices."),
    ("Market Pricing", "API", "fmp_api_key", "", "secret", "Saved to the local secret store, never to settings; or set an environment variable."),
    ("Market Pricing", "API", "alpha_vantage_api_key", "", "secret", "Saved to the local secret store, never to settings; or set an environment variable."),
    (_SC, "Security", "lan_auth_opt_out_ack", "NO", "yes/no", "Required YES to run LAN mode unauthenticated on 0.0.0.0. Use only on a trusted private LAN."),
    (_SC, "Tax Governance", "block_stale_tax_tables", "YES", "yes/no", "Advisor-ready status is blocked when tax table freshness warnings exist."),
    (_SC, "Tax Governance", "max_tax_table_lag_years", "1", "years", "Maximum permitted lag for federal/state/IRMAA/Social Security/RMD constants before blocking advisor-ready status."),
    (_SC, "Advisor Governance", "require_assumption_signoff", "NO", "yes/no", "Assumption signoff is available as an advisor workflow but does not force illustration-only language by default."),
    (_SC, "Advisor Governance", "output_status_mode", "STANDARD_WITH_WARNINGS", "choice", "Outputs show warnings and model-risk labels without mandatory illustration-until-signed language."),
    ("Market Pricing", "Holdings", "advisor_ready_max_fallback_value_pct", "10.00%", "pct", "Block advisor-ready status when fallback/stale pricing exceeds this share of priced holdings value."),
    (_SC, "Runtime", "max_build_seconds", "1800", "seconds", "Maximum local workbook build runtime before timeout. Default is 30 minutes; increase for very large Advanced Exact Scalar Monte Carlo, sensitivity grids, or slower machines."),
    (_SC, "Downloads", "filename_root", "Retirement Workbook", "text", "Root name for downloaded workbook files."),
    (_SC, "Downloads", "desktop_download_folder", "", "path", "Desktop app only: folder workbook downloads are saved to. Blank uses the OS Downloads folder."),
)
_DEFAULTS: dict[Key, tuple[str, str, str]] = {(s, ss, l): (v, u, n) for s, ss, l, v, u, n in SYSTEM_DEFAULTS}


def _clean_text(value: object, default: str = "") -> str:
    text = str(value if value is not None else "").strip()
    return text if text else default


def setting_key(section: str, subsection: str, label: str) -> str:
    """The ``AppStore`` settings key of one runtime setting: ``"section|subsection|label"``."""
    return KEY_SEPARATOR.join((section, subsection, label))


def split_setting_key(key: str) -> Key | None:
    """``(section, subsection, label)`` of a settings key, ``None`` for a key of another kind.

    The subsection may itself contain the separator; section and label never do.
    """
    if key.count(KEY_SEPARATOR) < 2:
        return None
    section, rest = key.split(KEY_SEPARATOR, 1)
    subsection, label = rest.rsplit(KEY_SEPARATOR, 1)
    return (section, subsection, label) if section and label else None


def _store_path(path: str | Path | None) -> Path:
    if path is None:
        from .app_state import app_store_path  # noqa: PLC0415
        return app_store_path()
    return Path(path)


def stored_settings(path: str | Path | None = None) -> dict[Key, str]:
    """The runtime settings ``app.db`` holds (values the user changed), keyed by row key."""
    p = _store_path(path)
    if not p.is_file():
        return {}
    from .app_state import open_app_store  # noqa: PLC0415
    with open_app_store(p, readonly=True) as store:
        raw = store.settings()
    out: dict[Key, str] = {}
    for k, v in raw.items():
        key = split_setting_key(k)
        if key is not None:
            out[key] = "" if v is None else str(v)
    return out


def _effective(path: str | Path | None) -> dict[Key, str]:
    values = {k: v[0] for k, v in _DEFAULTS.items()}
    values.update(stored_settings(path))
    return values


def load_system_config(path: str | Path | None = None) -> SettingMap:
    """Every runtime setting (defaults overlaid by ``app.db``) as section -> subsection -> label."""
    result: SettingMap = {}
    for (sec, sub, lbl), value in _effective(path).items():
        result.setdefault(sec, {}).setdefault(sub, {})[lbl] = _clean_text(value)
    return result


def settings_fingerprint(path: str | Path | None = None) -> str:
    """sha256 of the effective runtime settings (part of the build input fingerprint)."""
    doc = sorted([list(k) + [v] for k, v in _effective(path).items()])
    return hashlib.sha256(json.dumps(doc, separators=(",", ":")).encode("utf-8")).hexdigest()


def settings_rows(path: str | Path | None = None) -> list[list[str]]:
    """The runtime settings as editor rows: header, then defaults order, then any extra keys."""
    stored = stored_settings(path)
    rows = [list(SETTINGS_HEADER)]
    for sec, sub, lbl, value, units, notes in SYSTEM_DEFAULTS:
        rows.append([sec, sub, lbl, stored.get((sec, sub, lbl), value), units, notes])
    for (sec, sub, lbl), value in stored.items():
        if (sec, sub, lbl) not in _DEFAULTS:
            rows.append([sec, sub, lbl, value, "", ""])
    return rows


def is_system_setting(section: str, subsection: str, label: str) -> bool:
    return (section, subsection, label) in _DEFAULTS


def set_system_settings(updates: dict[Key, object], path: str | Path | None = None) -> None:
    """Write runtime settings in one transaction. A value equal to its default unsets the key
    (an unset key follows the built-in default)."""
    if not updates:
        return
    from .app_state import open_app_store  # noqa: PLC0415
    with open_app_store(_store_path(path)) as store, store.transaction():
        for (sec, sub, lbl), value in updates.items():
            text = "" if value is None else str(value).strip()
            key = setting_key(sec, sub, lbl)
            default = _DEFAULTS.get((sec, sub, lbl))
            if default is not None and text == default[0]:
                store.delete_setting(key)
            else:
                store.set_setting(key, text)


def save_settings_rows(rows: Iterable[Iterable[object]], path: str | Path | None = None) -> None:
    """Store the value cell of each editor row (header and ``#`` comment rows are skipped)."""
    updates: dict[Key, object] = {}
    for row in rows:
        cells = [str(c if c is not None else "") for c in row]
        if len(cells) < 3:
            continue
        sec, sub, lbl = (c.strip() for c in cells[:3])
        if not sec or sec.startswith("#") or not lbl or lbl.lower() == "label":
            continue
        updates[(sec, sub, lbl)] = cells[3] if len(cells) > 3 else ""
    set_system_settings(updates, path)


def system_setting(data: SettingMap, subsection: str, label: str, default: str = "") -> str:
    return data.get("System Configuration", {}).get(subsection, {}).get(label, default)


def setting(data: SettingMap, section: str, subsection: str, label: str, default: str = "") -> str:
    return data.get(section, {}).get(subsection, {}).get(label, default)


WORKBOOK_DOWNLOAD_SUBSECTION = "Downloads"
DEFAULT_WORKBOOK_FILENAME_ROOT = "Retirement Workbook"


def workbook_filename_root(data: SettingMap) -> str:
    root = system_setting(data, WORKBOOK_DOWNLOAD_SUBSECTION, "filename_root", DEFAULT_WORKBOOK_FILENAME_ROOT).strip()
    return root or DEFAULT_WORKBOOK_FILENAME_ROOT


def workbook_desktop_download_folder(data: SettingMap) -> str:
    return system_setting(data, WORKBOOK_DOWNLOAD_SUBSECTION, "desktop_download_folder", "").strip()


def upsert_system_setting(
    path: str | Path | None,
    subsection: str,
    label: str,
    value: object,
    units: str = "",
    notes: str = "",
) -> None:
    """Set one "System Configuration" setting in ``app.db`` (``units``/``notes`` are kept
    for call-site compatibility; the built-in defaults carry them)."""
    set_system_settings({("System Configuration", subsection, label): value}, path)
