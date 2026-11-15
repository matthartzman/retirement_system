from __future__ import annotations
"""Remote mode: the switch and the shared helpers for running one worker per remote user.

``RETIREMENT_SYSTEM_REMOTE_MODE=1`` turns a server process into a worker behind the multi-user
gateway (``documentation/future/multi-user-server-plan.md``, "Remote mode (Phase 1 contract)").
It is off by default, and every helper here is a no-op when it is off, so desktop mode is
unchanged. The flag is read from the environment on every call (cheap), so tests can switch it.

What this module owns:

* :func:`enabled` - the flag.
* :func:`worker_token` / :func:`assert_startup_ok` - the per-worker token, taken only from the
  environment the supervisor sets (never from a stored setting the user's own worker can write).
* :func:`confine_path` - the one workspace-confinement resolver every request-borne,
  settings-borne and registry-borne path goes through.
* :func:`subprocess_env` - the scrubbed environment for build and tool subprocesses.
* :func:`scrub` - rewrites server paths inside a JSON-able value (responses, error texts).

Like ``platform_runtime`` it imports nothing from the rest of the application at load time.
"""

import os
import tempfile
from pathlib import Path
from typing import Any

from . import platform_runtime

REMOTE_MODE_ENV = "RETIREMENT_SYSTEM_REMOTE_MODE"
TOKEN_ENV = "RETIREMENT_SYSTEM_SERVER_API_TOKEN"
TOKEN_HEADER = "X-API-Token"

_TRUE = {"1", "yes", "y", "true", "t", "on"}

# Environment names a build or tool subprocess may inherit in remote mode. Everything else
# (the gateway's own secrets, the owner's shell settings, PYTHONPATH and friends) is dropped.
_OS_KEYS = frozenset({
    "SYSTEMROOT", "WINDIR", "SYSTEMDRIVE", "COMSPEC", "PATH", "PATHEXT", "TEMP", "TMP",
    "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE", "PROCESSOR_IDENTIFIER", "OS",
    "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "HOME", "USERNAME", "LOCALAPPDATA", "APPDATA",
    "PROGRAMDATA", "PROGRAMFILES", "PROGRAMFILES(X86)", "COMMONPROGRAMFILES",
    "LANG", "LC_ALL", "TZ", "PYTHONIOENCODING", "PYTHONUTF8", "PYTHONUNBUFFERED", "PYTHONDONTWRITEBYTECODE",
})
# Shared price-provider keys: the gateway passes one to workers that need it (plan decision 6).
_PROVIDER_KEYS = frozenset({
    "RETIREMENT_SYSTEM_FMP_API_KEY", "FMP_API_KEY", "FINANCIAL_MODELING_PREP_API_KEY",
    "RETIREMENT_SYSTEM_ALPHA_VANTAGE_API_KEY", "ALPHA_VANTAGE_API_KEY",
})
# Application settings the build reads (``RETIREMENT_SYSTEM_*``, ``RETIREMENT_MC_*``, tax-year
# overrides). The worker token is never passed on.
_APP_PREFIXES = ("RETIREMENT_SYSTEM_", "RETIREMENT_MC_", "RETIREMENT_TAX_")
_NEVER_PASSED = frozenset({TOKEN_ENV})


class RemoteModeError(RuntimeError):
    """A remote-mode rule refused an action (start-up without a token, a disabled feature)."""


class PathOutsideWorkspace(ValueError):
    """A path resolved outside the worker's workspace root while remote mode is on."""


def enabled() -> bool:
    """True when this process runs as a remote worker (``RETIREMENT_SYSTEM_REMOTE_MODE``)."""
    return (os.environ.get(REMOTE_MODE_ENV) or "").strip().lower() in _TRUE


def worker_token() -> str:
    """The worker's access token, from the environment only ('' when unset)."""
    return (os.environ.get(TOKEN_ENV) or "").strip()


def assert_startup_ok() -> None:
    """Refuse to start a remote worker without a token. A no-op when remote mode is off."""
    if enabled() and not worker_token():
        raise RemoteModeError(
            f"Refusing to start in remote mode: {TOKEN_ENV} is empty. The supervisor must set a "
            "random per-worker token in the environment."
        )


def confine_path(value: str | Path, *, root: str | Path | None = None, what: str = "path") -> Path:
    """Resolve ``value`` against the workspace and, in remote mode, require it to stay inside.

    A relative value is joined onto ``root`` (default: the workspace root). When remote mode is
    off this only does that join (an absolute value is returned unchanged), which is what every
    caller did before. When it is on, the result is fully resolved (``..`` and links followed)
    and must lie inside the resolved workspace root, else :class:`PathOutsideWorkspace`.
    The message names ``what`` but never the path itself, so it is safe to show a remote user.
    """
    base = Path(root) if root is not None else platform_runtime.workspace_root()
    p = Path(value).expanduser()
    joined = p if p.is_absolute() else base / p
    if not enabled():
        return joined
    workspace = platform_runtime.workspace_root().resolve()
    resolved = joined.resolve()
    if not resolved.is_relative_to(workspace):
        raise PathOutsideWorkspace(f"The {what} must be inside your own workspace.")
    return resolved


def is_inside_workspace(value: str | Path) -> bool:
    try:
        return Path(value).resolve().is_relative_to(platform_runtime.workspace_root().resolve())
    except OSError:
        return False


def subprocess_env(base: dict[str, str] | None = None) -> dict[str, str]:
    """The environment for a build or tool subprocess.

    Off: a plain copy of ``base`` (default ``os.environ``), exactly as before. On: only the OS
    essentials, the application's own settings and the shared provider keys, never the token.
    """
    source = dict(os.environ if base is None else base)
    if not enabled():
        return source
    out: dict[str, str] = {}
    for key, value in source.items():
        upper = key.upper()
        if upper in _NEVER_PASSED:
            continue
        if upper in _OS_KEYS or upper in _PROVIDER_KEYS or upper.startswith(_APP_PREFIXES):
            out[key] = value
    return out


def _path_spellings(root: Path) -> list[str]:
    """The ways a path can appear in a response: as given, resolved, with forward slashes."""
    spellings: set[str] = set()
    for p in (root, _safe_resolve(root)):
        text = str(p).rstrip("\\/")
        if len(text) < 4:  # never rewrite a bare drive or "/"
            continue
        spellings.update({text, text.replace("\\", "/")})
    return sorted(spellings, key=len, reverse=True)


def _safe_resolve(p: Path) -> Path:
    try:
        return p.resolve()
    except OSError:
        return p


def _replacements() -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for root, label in ((platform_runtime.workspace_root(), "~workspace"),
                        (platform_runtime.package_root(), "~install"),
                        (Path(tempfile.gettempdir()), "~temp"),
                        (Path.home(), "~home")):
        pairs.extend((spelling, label) for spelling in _path_spellings(root))
    # Longest first, so the workspace wins over a package root that contains it, and so on.
    return sorted(pairs, key=lambda pair: len(pair[0]), reverse=True)


def scrub_text(text: str, replacements: list[tuple[str, str]] | None = None) -> str:
    """Rewrite server paths in ``text`` (case-insensitive on Windows)."""
    pairs = replacements if replacements is not None else _replacements()
    out = text
    for needle, label in pairs:
        if needle in out:
            out = out.replace(needle, label)
        elif os.name == "nt" and needle.lower() in out.lower():
            low, start, parts = out.lower(), 0, []
            needle_low = needle.lower()
            while True:
                i = low.find(needle_low, start)
                if i < 0:
                    parts.append(out[start:])
                    break
                parts.append(out[start:i] + label)
                start = i + len(needle)
            out = "".join(parts)
    return out


def scrub(value: Any, replacements: list[tuple[str, str]] | None = None) -> Any:
    """``value`` with every server path inside its strings rewritten (dicts and lists walked)."""
    pairs = replacements if replacements is not None else _replacements()
    if isinstance(value, str):
        return scrub_text(value, pairs)
    if isinstance(value, dict):
        return {k: scrub(v, pairs) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [scrub(v, pairs) for v in value]
    return value


GENERIC_ERROR = "Something went wrong on the server. Please try again; if it keeps happening, report the error id."
DISABLED_FEATURE = "This feature is not available on the server."
