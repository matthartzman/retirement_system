"""Start a real gateway plus per-user workers for the remote-mode Playwright spec.

Same stack as ``tests/test_multi_user_isolation_integration.py`` (gateway subprocess, same-account launcher, no
elevation, temp data root, demo-provisioned plan), with one enrolled user and one enrolled admin (same password). Prints one JSON line
``{"port": ..., "username": ..., "password": ..., "totp_secret": ...}`` when ready, then runs until stopped. With
``--shared-views`` it also adds an enrolled viewer sponsored by the user and turns the gateway's flag on (Phase 9).
The password is a throwaway test value that exists only in this temp gateway database.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.gateway import totp  # noqa: E402
from src.gateway.store import Actor, GatewayStore  # noqa: E402

PASSWORD = "remote e2e test password 1"


def main() -> int:
    base = Path(tempfile.mkdtemp(prefix="gateway_e2e_"))
    db, ready_file = base / "gateway.db", base / "ready.json"
    store = GatewayStore(db, scrypt_n=2**12)
    now = time.time()
    uid = store.create_user("carol", "Carol", "user", PASSWORD, now=now, actor=Actor(None, "e2e"), must_change=False)
    secret = store.begin_totp_enrolment(uid, now - 3600)
    assert store.confirm_totp(uid, totp.code_at(secret, int((now - 3600) // 30)), now - 3600)
    # An admin too, for the Admin console journeys (tests/e2e_gateway/admin-console.spec.js).
    admin_id = store.create_user("root", "Root Admin", "admin", PASSWORD, now=now, actor=Actor(None, "e2e"), must_change=False)
    admin_secret = store.begin_totp_enrolment(admin_id, now - 3600)
    assert store.confirm_totp(admin_id, totp.code_at(admin_secret, int((now - 3600) // 30)), now - 3600)
    extra: dict = {}
    shared = "--shared-views" in sys.argv[1:]
    if shared:
        # Phase 9 (tests/e2e_gateway/shared-view.spec.js): a viewer sponsored by carol, enrolled, and the flag on.
        vid = store.create_viewer("vera", "Vera Viewer", PASSWORD, sponsor_user_id=uid, now=now, actor=Actor(None, "e2e"),
                                  must_change=False)
        vsecret = store.begin_totp_enrolment(vid, now - 3600)
        assert store.confirm_totp(vid, totp.code_at(vsecret, int((now - 3600) // 30)), now - 3600)
        extra = {"viewer_username": "vera", "viewer_totp_secret": vsecret, "viewer_id": vid}
    env = {k: v for k, v in __import__("os").environ.items() if not k.startswith("RETIREMENT_SYSTEM_")}
    cmd = [sys.executable, "-m", "src.gateway", "--db", str(db), "--local-port", "0", "--funnel-port", "0",
           "--public-origin", "https://node.example.ts.net:8443", "--no-tailscale-check",
           "--data-root", str(base / "data"), "--provision", "demo", "--ready-file", str(ready_file),
           "--build-concurrency", "1", "--insights", "--worker-env", "RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS=1"]
    if shared:
        cmd.append("--shared-views")
    proc = subprocess.Popen(cmd, cwd=str(ROOT), env=env)
    deadline = time.time() + 60
    while not ready_file.is_file():
        if proc.poll() is not None or time.time() > deadline:
            proc.kill()
            return 1
        time.sleep(0.1)
    ready = json.loads(ready_file.read_text(encoding="utf-8"))
    print(json.dumps({"port": ready["local_port"], "username": "carol", "password": PASSWORD, "totp_secret": secret,
                      "admin_username": "root", "admin_totp_secret": admin_secret, **extra}), flush=True)
    try:
        proc.wait()
    except KeyboardInterrupt:
        pass
    finally:
        proc.terminate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
