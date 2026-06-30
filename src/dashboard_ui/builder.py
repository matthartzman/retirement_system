from __future__ import annotations
from pathlib import Path
import shutil

# ``frontend/`` is the authoritative source for all HTML/CSS/JS assets.
# ``src/dashboard_ui/static/`` is kept as a legacy reference only and is
# never written to output; builds copy FROM frontend/ TO output/.
PACKAGE_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = PACKAGE_ROOT / "frontend"


def _copy_frontend_to(target_dir: Path, frontend_dir: Path) -> None:
    """Copy the canonical frontend tree (index.html + css/ + js/) to target_dir."""
    target_dir.mkdir(parents=True, exist_ok=True)

    src_index = frontend_dir / "index.html"
    if src_index.exists():
        shutil.copy2(src_index, target_dir / "index.html")

    for subdir in ("css", "js"):
        src_sub = frontend_dir / subdir
        if not src_sub.exists():
            continue
        dst_sub = target_dir / subdir
        dst_sub.mkdir(parents=True, exist_ok=True)
        for src in src_sub.rglob("*"):
            if src.is_file():
                rel = src.relative_to(src_sub)
                dst = dst_sub / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)


def write_dashboard_ui(output_dir: str | Path, frontend_dir: str | Path | None = None) -> Path:
    """Copy the canonical frontend/ assets into output_dir for offline workbook bundles.

    ``frontend/`` is the source of truth (PyWebView-compatible, no Flask HTTP
    server dependency).  ``output_dir`` receives a copy so the generated
    workbook bundle can open the dashboard without a running server.

    The old behaviour of refreshing ``frontend/`` from ``src/dashboard_ui/static/``
    has been removed: that static directory is a legacy snapshot and is
    intentionally no longer propagated.
    """
    front = Path(frontend_dir) if frontend_dir is not None else FRONTEND_DIR
    out = Path(output_dir)
    _copy_frontend_to(out, front)
    return out / "index.html"
