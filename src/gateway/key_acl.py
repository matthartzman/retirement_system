"""SEC-08: is the backup key file readable only by the accounts that should read it?

The key file lives next to nothing else of the gateway's, but ``0o600`` means nothing on Windows and a copy into a
folder that inherits ``Users:(R)`` would silently expose it. This reads the file's DACL (through ``acl.read_dacl``;
``acl`` itself is not changed) and reports every allow entry for another account that can read it. It is a point-in-
time check: the service runs it at start, ``ops key check`` runs it on demand.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

from . import acl


def key_file_findings(path: Path | str, *, gateway_sid: str | None = None,
                      reader: Callable[[Path], "acl.Dacl"] | None = None) -> list[str]:
    """Findings (empty = fine) for a key file. Only SYSTEM, Administrators, the gateway account and the file's owner
    may be granted read. Off Windows there is no DACL to read: nothing is reported (documented, not silent)."""
    if reader is None and sys.platform != "win32":
        return []
    read = reader or acl.read_dacl
    p = Path(path)
    try:
        dacl = read(p)
    except (OSError, acl.AclError) as exc:
        return [f"{p}: its permissions could not be read ({type(exc).__name__}); treat the key as exposed until checked"]
    if dacl.aces is None:
        return [f"{p}: has no access list at all (everyone can read it)"]
    allowed = {acl.SYSTEM, acl.ADMINISTRATORS}
    if gateway_sid:
        allowed.add(gateway_sid)
    if dacl.owner:
        allowed.add(dacl.owner)
    found = []
    for ace in dacl.effective(allowed):
        if ace.allow and ace.reads and not ace.inherit_only and ace.sid not in allowed:
            found.append(f"{p}: account {ace.sid} can read the backup key")
    return found
