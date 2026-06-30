from __future__ import annotations
"""Local path helpers for the single-user desktop package.

Plan Data lives in the local SQLite store. Generated files are written to output/.
"""

import re
from pathlib import Path
from typing import Iterable, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _runtime_cfg():
    try:
        from .runtime_config import load_runtime_config
    except Exception:
        from src.runtime_config import load_runtime_config
    return load_runtime_config()


def sanitize_id(value: object, default: str = "local") -> str:
    text = str(value or "").strip() or default
    text = re.sub(r"[^A-Za-z0-9_.-]+", "-", text).strip(".-_")
    return text or default


def active_workspace_id(default: str = "local") -> str:
    return "local"


def active_client_id(default: str = "local") -> str:
    return "local"


def workspace_plan_data_dir(workspace_id: Optional[str] = None, root: Path = PROJECT_ROOT) -> Path:
    return root / "input"


# Name used by existing call sites; intentionally points to the new plan_data folder.
def workspace_input_dir(workspace_id: Optional[str] = None, root: Path = PROJECT_ROOT) -> Path:
    return workspace_plan_data_dir(workspace_id, root)


def workspace_output_dir(workspace_id: Optional[str] = None, root: Path = PROJECT_ROOT) -> Path:
    cfg = _runtime_cfg()
    override = getattr(cfg, "output_dir", "")
    if override:
        p = Path(override)
        return p if p.is_absolute() else root / p
    return root / "output"


def workspace_file(filename: str, workspace_id: Optional[str] = None, root: Path = PROJECT_ROOT, prefer_existing: bool = True) -> Path:
    return root / "input" / Path(filename).name


def candidate_input_files(filename: str, workspace_id: Optional[str] = None, root: Path = PROJECT_ROOT) -> list[Path]:
    name = Path(filename).name
    candidates = [
        workspace_plan_data_dir(workspace_id, root) / name,
        root / "input" / name,
        root / "reference_data" / name,
    ]
    out: list[Path] = []
    seen = set()
    for p in candidates:
        key = str(p)
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def first_existing(paths: Iterable[Path]) -> Optional[Path]:
    for p in paths:
        if p.exists():
            return p
    return None
