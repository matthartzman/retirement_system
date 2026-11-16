"""``python -m src.gateway``: run the multi-user gateway (see ``server.py``)."""
from __future__ import annotations

from .server import main

if __name__ == "__main__":
    raise SystemExit(main())
