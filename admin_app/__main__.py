"""``python -m admin_app`` starts the console; ``python -m admin_app create-admin ...`` makes the first administrator."""
from __future__ import annotations

import sys

if __name__ == "__main__":
    argv = sys.argv[1:]
    if argv and argv[0] == "create-admin":
        from src.identity.cli import main as cli_main

        raise SystemExit(cli_main(argv))
    from admin_app.main import main

    raise SystemExit(main(argv))
