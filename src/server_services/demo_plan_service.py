from __future__ import annotations

"""Feature-owned Open demo / Exit demo / Reset demo (design F section 5A, WP8.4).

The demo plan and the user's plan coexist as separate plan files, one active at a time (the
plan registry in ``app.db``, ``src/plan_registry.py``):

* **Open demo** creates ``<workspace>/demo.rpx`` (kind ``demo``, id ``demo``) from the bundled
  seed (``input/demo``, read once through the ``csv_exchange`` importer) when it does not exist,
  then makes it the active plan. Edits made in the demo stay in ``demo.rpx`` for next time.
* **Exit demo** switches the active plan back to the plan that was active when the demo was
  opened (else the most recently opened non-demo plan).
* **Reset demo** rebuilds ``demo.rpx`` from the seed (validated, then swapped in through
  ``plan_db_replace``).

The user's plan file is never modified, copied over or restored by any of this; the demo builds
write to ``output/plans/demo/``, so the real workbook is never overwritten. ``input/demo`` is
never written.
"""

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .. import plan_registry
from ..active_plan import build_plan_file_from_csv_folder
from ..plan_db_replace import PLAN_FILE_TABLES, remove_sidecars, replace_active_db, validate_plan_file

JsonDict = dict[str, Any]


@dataclass(frozen=True)
class DemoPlanServiceContext:
    # The bundled demo seed (the ``input/demo`` CSV set); only read.
    demo_dir: Callable[[], Path]
    # Where the demo plan file lives (default ``<workspace>/demo.rpx``).
    demo_plan_file: Callable[[], Path] = plan_registry.demo_plan_file
    audit: Callable[[str, dict[str, Any]], None] | None = None
    # Runs on the plan file that just became active (open, exit, and a reset of the active demo):
    # the at-rest row migration and the UI-row backfill.
    after_switch: Callable[[Path], Any] | None = None


def _plan_view(rec: dict[str, Any] | None) -> JsonDict | None:
    if not rec:
        return None
    return {k: rec.get(k) for k in ("plan_id", "name", "kind", "path", "last_opened")}


class DemoPlanService:
    """Framework-neutral owner for Open demo / Exit demo / Reset demo."""

    def __init__(self, context: DemoPlanServiceContext):
        self.context = context

    def _audit(self, event: str, details: dict[str, Any] | None = None) -> None:
        if self.context.audit:
            self.context.audit(event, details or {})

    def _after_switch(self, path: Path) -> None:
        if self.context.after_switch is None:
            return
        try:
            self.context.after_switch(path)
        except Exception as exc:  # noqa: BLE001 - never undoes a completed switch
            self._audit("plan_after_switch_warning", {"path": str(path), "error": str(exc)})

    def _build_seed(self, dest: Path) -> None:
        """Build the demo plan from the seed into a temp file beside ``dest`` and return nothing;
        the caller moves it into place."""
        if not build_plan_file_from_csv_folder(dest, self.context.demo_dir()):
            raise FileNotFoundError(f"no demo plan rows found in {self.context.demo_dir()}")

    def _temp_beside(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".seed")
        os.close(fd)
        return Path(name)

    def _create_demo_file(self, demo: Path) -> None:
        tmp = self._temp_beside(demo)
        try:
            self._build_seed(tmp)
            remove_sidecars(tmp)
            remove_sidecars(demo)
            os.replace(str(tmp), str(demo))
        finally:
            tmp.unlink(missing_ok=True)
            remove_sidecars(tmp)

    def _demo_record(self, demo: Path) -> dict[str, Any]:
        return plan_registry.register_plan_file(
            demo, name=plan_registry.DEMO_PLAN_NAME, kind="demo", plan_id=plan_registry.DEMO_PLAN_ID)

    def is_active(self) -> bool:
        return plan_registry.is_demo_active()

    def status_payload(self) -> JsonDict:
        rec = plan_registry.active_record()
        active = rec.get("kind") == "demo"
        return {
            "success": True,
            "active": active,
            "opened_at": rec.get("last_opened") if active else None,
            "plan": _plan_view(rec),
            "demo_exists": Path(self.context.demo_plan_file()).is_file(),
        }

    def open_demo_payload(self) -> JsonDict:
        demo = Path(self.context.demo_plan_file())
        created = False
        if not demo.is_file():
            self._create_demo_file(demo)
            created = True
        rec = plan_registry.activate(self._demo_record(demo)["plan_id"])
        self._after_switch(demo)
        self._audit("demo_plan_opened", {"plan_id": rec["plan_id"], "created": created})
        return {"success": True, "active": True, "created": created, "plan": _plan_view(rec)}

    def exit_demo_payload(self) -> JsonDict:
        if not self.is_active():
            return {"success": True, "restored": False, "plan": _plan_view(plan_registry.active_record())}
        target = plan_registry.demo_return_plan_id()
        if target is None:  # the demo was the only plan ever registered: the workspace plan
            target = plan_registry.register_plan_file(
                plan_registry.workspace_plan_file(), name=plan_registry.DEFAULT_PLAN_NAME)["plan_id"]
        try:
            rec = plan_registry.activate(target, check=Path(plan_registry.get_plan(target)["path"]).is_file())
        except plan_registry.PlanRegistryError as exc:
            self._audit("demo_plan_exit_failed", {"plan_id": target, "error": str(exc)})
            return {"success": False, "restored": False, "error": f"Could not switch back to your plan: {exc}"}
        self._after_switch(Path(rec["path"]))
        self._audit("demo_plan_exited", {"plan_id": rec["plan_id"]})
        return {"success": True, "restored": True, "plan": _plan_view(rec)}

    def reset_demo_payload(self) -> JsonDict:
        """Rebuild ``demo.rpx`` from the bundled seed (allowed whether or not the demo is open)."""
        demo = Path(self.context.demo_plan_file())
        if not demo.is_file():
            self._create_demo_file(demo)
        else:
            tmp = self._temp_beside(demo)
            try:
                self._build_seed(tmp)
                result = replace_active_db(tmp, demo, required_tables=PLAN_FILE_TABLES, validate=validate_plan_file)
            finally:
                tmp.unlink(missing_ok=True)
                remove_sidecars(tmp)
            if not result.get("success"):
                return {"success": False, "error": result.get("error") or "Could not reset the demo plan."}
        self._demo_record(demo)
        if self.is_active():
            self._after_switch(demo)
        self._audit("demo_plan_reset", {"path": str(demo)})
        return {"success": True, "reset": True}
