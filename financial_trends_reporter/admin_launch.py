"""Start the Admin app (loopback 5056) on demand, the way the launchers do, for the "Manage people" button."""
from __future__ import annotations

import socket
import subprocess
import sys
from pathlib import Path

ADMIN_PORT = 5056
_REPO_ROOT = Path(__file__).resolve().parent.parent


def _listening(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.3)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def ensure_admin_app(retirement_system_dir: Path, port: int = ADMIN_PORT) -> bool:
    """True when the Admin app is (now) running. Starts it detached, without opening a browser, if it is not."""
    if _listening(port):
        return True
    flags = (subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP) if sys.platform == "win32" else 0
    try:
        subprocess.Popen([sys.executable, "-m", "admin_app", "--no-open", "--port", str(port),
                          "--retirement-system-dir", str(retirement_system_dir)],
                         cwd=str(_REPO_ROOT), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, creationflags=flags)
    except OSError:
        return False
    return True
