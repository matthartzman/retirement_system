from __future__ import annotations

import threading
import webbrowser

from . import BASE_DIR, create_app, _runtime_config
from ..http_runtime.server import run_local_server
from .. import platform_runtime


def main() -> int:
    cfg = _runtime_config()
    url = f"http://{cfg.dashboard_host}:{cfg.dashboard_port}"
    print(f"""
======================================================
  RETIREMENT PLAN SYSTEM v10
======================================================
  Dashboard:  {url}
  Runtime:    stdlib local HTTP
  App mode:   {cfg.app_mode}
  Storage:    single local Plan Data folder
  Files in:   {BASE_DIR}
======================================================
""")
    if cfg.app_mode == "LOCAL" and platform_runtime.can_open_browser():
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    run_local_server(create_app(), host=cfg.dashboard_host, port=int(cfg.dashboard_port), debug=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
