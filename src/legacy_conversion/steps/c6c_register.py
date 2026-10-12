"""Conversion step C6c: register the converted plan in app.db and make it the active plan.

* The converted plan file is registered as a ``user`` plan (``plan_registry.register_plan_file``;
  the existing record when its path is known, so ``plan.rpx`` keeps its id and output folder) and
  activated (``plan_registry.activate``, which validates the file first). When the registry's
  active plan is the demo (a WP8.4+ install that was in the demo), the demo stays open and the
  converted plan becomes the plan Exit demo returns to.
* Mid-demo upgrade (an old demo was open): the demo is recreated from the bundled seed as
  ``<workspace>/demo.rpx`` (only when that file does not exist) and registered as the demo
  plan; ``plan.rpx.before_demo`` is never touched.

The registry belongs to the running install, so the step works only when ``workspace`` is the
install's workspace (``platform_runtime.workspace_root()``); otherwise it reports
``skipped: other workspace`` and changes nothing. Marker: plan meta
``legacy_conversion.c6c``. Dry run reports what it would do.
"""
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

STEP_ID = "C6c"
MARKER_KEY = "legacy_conversion.c6c"


@dataclass
class C6cReport:
    step: str
    skipped: bool
    reason: str = ""
    plan_id: str = ""
    activated: bool = False
    demo_return_set: bool = False
    demo_created: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {"step": self.step, "skipped": self.skipped, "reason": self.reason, "plan_id": self.plan_id,
                "activated": self.activated, "demo_return_set": self.demo_return_set,
                "demo_created": self.demo_created}


def _same(a: Path, b: Path) -> bool:
    try:
        return Path(a).resolve() == Path(b).resolve()
    except OSError:
        return False


def build_demo_file(dest: Path) -> bool:
    """Build ``dest`` from the bundled demo seed when it does not exist; True when built."""
    from ...active_plan import build_plan_file_from_csv_folder  # noqa: PLC0415
    from ...plan_db_replace import remove_sidecars  # noqa: PLC0415
    from ..sources import demo_seed_dir  # noqa: PLC0415

    if dest.exists() or not demo_seed_dir().is_dir():
        return False
    fd, name = tempfile.mkstemp(dir=str(dest.parent), prefix=dest.name + ".", suffix=".seed")
    os.close(fd)
    tmp = Path(name)
    try:
        if not build_plan_file_from_csv_folder(tmp, demo_seed_dir()):
            return False
        remove_sidecars(tmp)
        os.replace(str(tmp), str(dest))
        return True
    finally:
        tmp.unlink(missing_ok=True)
        remove_sidecars(tmp)


def run(store: Any, workspace: Path, plan_file: Path, *, mid_demo: bool = False, dry_run: bool = False) -> C6cReport:
    from ... import plan_registry  # noqa: PLC0415
    from ...platform_runtime import workspace_root  # noqa: PLC0415

    if store.get_meta(MARKER_KEY) is not None:
        return C6cReport(STEP_ID, skipped=True)
    if not _same(workspace, workspace_root()):
        return C6cReport(STEP_ID, skipped=True, reason="other workspace")
    rep = C6cReport(STEP_ID, skipped=False)
    demo = Path(workspace) / plan_registry.DEMO_FILE_NAME
    if dry_run:
        rep.reason = "dry run"
        rep.demo_created = mid_demo and not demo.exists()
        return rep
    if mid_demo:
        rep.demo_created = build_demo_file(demo)
        if demo.exists():
            plan_registry.register_plan_file(demo, name=plan_registry.DEMO_PLAN_NAME, kind="demo",
                                             plan_id=plan_registry.DEMO_PLAN_ID)
    rec = plan_registry.register_plan_file(plan_file, name=plan_registry.DEFAULT_PLAN_NAME, kind="user",
                                           plan_id=plan_registry.file_plan_id(plan_file))
    rep.plan_id = rec["plan_id"]
    current = plan_registry.active_record()
    if current.get("kind") == "demo" and not mid_demo:
        from ...app_state import open_app_store  # noqa: PLC0415
        with open_app_store() as app:
            app.set_setting(plan_registry.DEMO_RETURN_KEY, rec["plan_id"])
        plan_registry.invalidate()
        rep.demo_return_set = True
    else:
        # The runner holds the plan open mid-conversion; it was just written by the steps, so
        # the registry's file validation (which opens it again) is skipped.
        plan_registry.activate(rec["plan_id"], check=False)
        rep.activated = True
    with store.transaction():
        store.set_meta(MARKER_KEY, rep.plan_id)
    return rep
