"""Startup check for where the local apps keep their data (F-11, F-12).

Financial data and the per-boot token file are plain files. Two things make them easier to reach than intended:
a folder other accounts can read, and a folder under OneDrive (which uploads it, and a corrupted partial sync once
truncated a source file here). This warns about both; it never blocks start-up and never changes a permission.
Windows reads the real DACL through ``src.gateway.acl.read_dacl``; elsewhere the POSIX mode bits are used.
"""
from __future__ import annotations

import html
import logging
import os
import stat
import sys
from pathlib import Path
from typing import Callable, Iterable

LOG = logging.getLogger("retirement.data_exposure")
_ADMINS, _SYSTEM = "S-1-5-32-544", "S-1-5-18"


def onedrive_problem(path: Path | str, env: dict[str, str] | None = None) -> str | None:
    """A message when ``path`` is inside a OneDrive folder (by name or by the OneDrive environment variables)."""
    env = dict(os.environ) if env is None else env
    p = Path(os.path.abspath(path))
    roots = [Path(os.path.abspath(v)) for k in ("OneDrive", "OneDriveCommercial", "OneDriveConsumer") if (v := env.get(k))]
    if any(r == p or r in p.parents for r in roots) or any(part.lower().startswith("onedrive") for part in p.parts):
        return f"{p} is inside a OneDrive folder, so its contents are uploaded and can be corrupted by a partial sync"
    return None


def _windows_problem(path: Path, read_dacl: Callable, current_sid: Callable[[], str]) -> list[str]:
    dacl = read_dacl(path)
    if dacl.aces is None:
        return [f"{path} has no access list at all (everyone can read it)"]
    allowed = {_ADMINS, _SYSTEM, current_sid()}
    if dacl.owner:
        allowed.add(dacl.owner)
    return [f"{path} can be read by account {a.sid}" for a in dacl.effective(allowed)
            if a.allow and a.reads and not a.inherit_only and a.sid not in allowed]


def permission_problems(path: Path | str, *, platform: str | None = None, read_dacl: Callable | None = None,
                        current_sid: Callable[[], str] | None = None,
                        mode_of: Callable[[Path], int] | None = None) -> list[str]:
    """Messages when ``path`` (a folder or a file) is readable by accounts other than its owner, Administrators, SYSTEM."""
    p = Path(path)
    if not p.exists():
        return []
    platform = platform or sys.platform
    try:
        if platform == "win32":
            if read_dacl is None or current_sid is None:
                from src.gateway import acl, winapi  # noqa: PLC0415

                read_dacl, current_sid = read_dacl or acl.read_dacl, current_sid or winapi.current_user_sid
            return _windows_problem(p, read_dacl, current_sid)
        mode = (mode_of or (lambda q: stat.S_IMODE(q.stat().st_mode)))(p)
        return [f"{p} is accessible to group or other users (mode {mode:o}); run: chmod go-rwx"] if mode & 0o077 else []
    except Exception as exc:  # noqa: BLE001 - a check that cannot run is itself worth one line, never a crash
        return [f"{p}: permissions could not be checked ({type(exc).__name__})"]


def check_paths(paths: Iterable[tuple[str, Path | str]], **kw) -> list[str]:
    """One line per problem for each labelled path."""
    found: list[str] = []
    for label, path in paths:
        if (msg := onedrive_problem(path, kw.get("env"))):
            found.append(f"{label}: {msg}")
        for msg in permission_problems(path, **{k: v for k, v in kw.items() if k != "env"}):
            found.append(f"{label}: {msg}")
    return found


def announce(app_name: str, problems: list[str]) -> None:
    """Log each problem and print a boxed notice to the console the app was launched from."""
    if not problems:
        return
    for line in problems:
        LOG.warning("%s: %s", app_name, line)
    bar = "=" * 72
    print(f"\n{bar}\nWARNING ({app_name}): your data may be more exposed than intended\n" + "\n".join(f"  - {x}" for x in problems)
          + f"\n{bar}\n", file=sys.stderr)


def banner_html(problems: list[str]) -> str:
    """A visible, self-contained notice for the top of a served page ('' when there is nothing to say)."""
    if not problems:
        return ""
    items = "".join(f"<li>{html.escape(x)}</li>" for x in problems)
    return ('<div role="alert" id="data-exposure-banner" style="margin:0;padding:10px 16px;background:#fff3cd;color:#664d03;'
            'border-bottom:2px solid #e0a800;font:14px system-ui,sans-serif"><strong>Data location warning.</strong> '
            f'Fix this, then restart the app.<ul style="margin:4px 0 0 18px">{items}</ul></div>')


def inject_banner(page: str, problems: list[str]) -> str:
    """Put the banner right after ``<body ...>`` (or at the top when there is none)."""
    banner = banner_html(problems)
    if not banner:
        return page
    low = page.lower()
    i = low.find("<body")
    if i < 0:
        return banner + page
    j = page.find(">", i)
    return page if j < 0 else page[: j + 1] + banner + page[j + 1:]
