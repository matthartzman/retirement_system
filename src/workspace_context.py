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


def _is_live_workspace(root: Optional[Path]) -> bool:
    if root is None:
        return True
    try:
        return Path(root).resolve() == platform_runtime.workspace_root().resolve()
    except OSError:
        return False


def active_plan_id(workspace_id: Optional[str] = None, root: Optional[Path] = None) -> str:
    """The id naming a plan's output folder (``output/plans/<plan_id>/``, ``plan_store.plan_paths``).

    The live workspace: the plan registry's id of the active plan (WP8.4). Under
    ``RETIREMENT_SYSTEM_PLAN_DB`` (the build subprocess) the id the server passed
    (``RETIREMENT_SYSTEM_PLAN_ID``), else the registry id of that file. A plan file the registry
    does not know (another workspace ``root``, an unregistered override) falls back to
    ``plan_registry.file_plan_id``: the ``plan_id`` in its meta, else its stem.
    """
    import os

    from . import active_plan, plan_registry

    if not _is_live_workspace(root):
        return plan_registry.file_plan_id(Path(root) / active_plan.PLAN_FILE_NAME)
    override = active_plan.plan_db_override()
    if override is None:
        return plan_registry.active_plan_id()
    passed = str(os.environ.get(active_plan.PLAN_ID_ENV, "") or "").strip()
    if passed:
        try:
            return active_plan.validate_plan_id(passed)
        except Exception:
            pass
    return plan_registry.plan_id_for_path(override) or plan_registry.file_plan_id(override)


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
