from __future__ import annotations

"""First-launch conversion service (WP10.4): status, check (dry run) and run of the one-time
conversion of an old install (``legacy_conversion.convert_workspace``) for the first-launch UI.

Nothing converts by itself: the UI shows what is found and the user starts the check or the
conversion. A run is one background thread; ``status`` reports ``running`` and, when it ends,
the privacy-safe result summary (statuses, counts, file and key NAMES only, never values).
"""

import threading
from pathlib import Path
from typing import Any, Callable

JsonDict = dict[str, Any]
# The only choices the UI may pass to the converter (decisions of the 10.3 checkpoint).
OPTION_KEYS = ("accept_differences", "backup_legacy_secrets", "delete_legacy_secrets")


class ConversionService:
    def __init__(self, workspace: Callable[[], Path], after_run: Callable[[], None] | None = None,
                 audit: Callable[[str, dict[str, Any] | None], None] | None = None):
        self._workspace = workspace
        self._after_run = after_run
        self._audit = audit
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._last: JsonDict | None = None  # summary of the most recent run in this process

    @staticmethod
    def _options(body: JsonDict) -> JsonDict:
        extra: JsonDict = {k: True for k in OPTION_KEYS if body.get(k) is True}
        if body.get("tier_mapping") == "keep":
            extra["tier_mapping"] = "keep"
        return extra

    @staticmethod
    def _found(sources: Any) -> JsonDict | None:
        """File NAMES grouped by where they were found (never contents)."""
        if sources is None:
            return None
        by_origin: dict[str, list[str]] = {}
        for name, (origin, _path, _text) in sorted(sources.chosen.items()):
            by_origin.setdefault(str(origin), []).append(name)
        return {"mode": sources.mode, "files": by_origin, "legacy_database": sources.legacy_db is not None}

    def status(self) -> JsonDict:
        from ..app_state import app_store_path_for, open_app_store  # noqa: PLC0415
        from ..legacy_conversion import workspace as lc  # noqa: PLC0415
        from ..legacy_conversion.result import LAST_RESULT_KEY  # noqa: PLC0415

        ws = self._workspace()
        d = lc.decide(ws)
        last = self._last
        if last is None:
            try:
                with open_app_store(app_store_path_for(ws), readonly=True) as app:
                    last = app.get_setting(LAST_RESULT_KEY)
            except Exception:  # noqa: BLE001 - no app.db yet
                last = None
        sources = d.get("sources")
        return {"needed": bool(d["needed"]), "reason": d["reason"], "mode": d["mode"],
                "running": bool(self._thread and self._thread.is_alive()),
                "found": self._found(sources),
                "last_result": last}

    def start(self, body: JsonDict, *, dry_run: bool) -> tuple[JsonDict, int]:
        from ..legacy_conversion import workspace as lc  # noqa: PLC0415

        with self._lock:
            if self._thread and self._thread.is_alive():
                return {"success": False, "error": "A conversion is already running."}, 409
            ws, extra = self._workspace(), self._options(body or {})

            def work() -> None:
                try:
                    res = lc.convert_workspace(ws, dry_run=dry_run, extra=extra)
                    self._last = res.summary()
                    if not dry_run and res.plan_replaced and self._after_run:
                        self._after_run()
                    if self._audit:
                        self._audit("legacy_conversion", {"dry_run": dry_run, "status": res.status,
                                                          "blocked_reason": res.blocked_reason})
                except Exception as exc:  # noqa: BLE001 - never leak a message (it can quote plan values)
                    self._last = {"status": "failed", "blocked_reason": "internal_error", "error_type": type(exc).__name__}

            self._last = None
            self._thread = threading.Thread(target=work, name="legacy-conversion", daemon=True)
            self._thread.start()
        return {"success": True, "started": True, "dry_run": dry_run}, 202
