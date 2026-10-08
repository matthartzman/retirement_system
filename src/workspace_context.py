from __future__ import annotations
"""Local path helpers for the single-user desktop package.

Plan data lives in the plan file (``active_plan``); the build reads it through one read
transaction (WP7.1), so there is no input-file lookup here. Generated files are written to
output/.
"""

import re
from pathlib import Path
from typing import Optional

from . import platform_runtime

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _default_root(root: Optional[Path]) -> Path:
    """Resolve the writable root for a call, honoring an explicit override.

    When a caller passes ``root`` explicitly (as the server routes do with their
    package BASE_DIR) that value wins. Otherwise the writable tree is resolved
    from :func:`platform_runtime.workspace_root`. Resolving lazily (rather than
    baking PROJECT_ROOT into the default arg) lets a test redirect the
    workspace after import.
    """
    if root is not None:
        return root
    return platform_runtime.workspace_root()


def _runtime_cfg():
    from .runtime_config import load_runtime_config
    return load_runtime_config()


def sanitize_id(value: object, default: str = "local") -> str:
    text = str(value or "").strip() or default
    text = re.sub(r"[^A-Za-z0-9_.-]+", "-", text).strip(".-_")
    return text or default


def active_workspace_id(default: str = "local") -> str:
    return "local"


def active_client_id(default: str = "local") -> str:
    return "local"


def workspace_plan_data_dir(workspace_id: Optional[str] = None, root: Optional[Path] = None) -> Path:
    return _default_root(root) / "input"


# Name used by existing call sites; intentionally points to the new plan_data folder.
def workspace_input_dir(workspace_id: Optional[str] = None, root: Optional[Path] = None) -> Path:
    return workspace_plan_data_dir(workspace_id, root)


PLAN_ID_META_KEY = "plan_id"


def active_plan_id(workspace_id: Optional[str] = None, root: Optional[Path] = None) -> str:
    """The id naming a plan's output folder.

    The one place the id is derived until the plan registry (WP8.4) supplies it: the
    ``plan_id`` stored in the plan file's meta when present, else the plan file's name
    (``plan.rpx`` -> ``plan``), made safe for use as a directory name.
    """
    from . import active_plan
    path = active_plan.plan_path_for_workspace(_default_root(root))
    stored = None
    if path.exists():
        try:
            store = active_plan.PlanStore.open(path, create=False, readonly=True)
            try:
                stored = store.get_meta(PLAN_ID_META_KEY)
            finally:
                store.close()
        except Exception:
            stored = None
    for candidate in (stored, path.stem):
        text = re.sub(r"[^A-Za-z0-9_-]+", "-", str(candidate or "")).strip("-_")[:64]
        try:
            return active_plan.validate_plan_id(text)
        except Exception:
            continue
    return "plan"


def legacy_output_dir(root: Optional[Path] = None) -> Path:
    """The pre-WP7.3 shared output folder; older artifacts there stay downloadable."""
    return _default_root(root) / "output"


def workspace_output_dir(workspace_id: Optional[str] = None, root: Optional[Path] = None) -> Path:
    """Per-plan output folder: ``<output>/plans/<plan_id>/`` (xlsx, html, pdf)."""
    root = _default_root(root)
    cfg = _runtime_cfg()
    override = getattr(cfg, "output_dir", "")
    base = root / "output"
    if override:
        p = Path(override)
        base = p if p.is_absolute() else root / p
    return base / "plans" / active_plan_id(workspace_id, root)
