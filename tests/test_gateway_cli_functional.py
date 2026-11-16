"""Server-side gateway CLIs: create the first admin, and break-glass reset of an admin's password and TOTP."""
from __future__ import annotations

import io
import os
import subprocess
import sys
from pathlib import Path

import pytest

from src.gateway import cli
from src.gateway.app import create_gateway_app
from src.gateway.store import Actor, GatewayStore

ROOT = Path(__file__).resolve().parents[1]
PW = "a long enough password"
NEW_PW = "break glass password 9"


def _run(db: Path, *args: str, password: str | None = PW) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    stdin = io.StringIO((password + "\n") if password is not None else "")
    code = cli.main([*args, "--db", str(db), "--password-stdin"], stdin=stdin, stdout=out, stderr=err, scrypt_n=2**4)
    return code, out.getvalue(), err.getvalue()


def test_create_admin_on_an_empty_database(tmp_path):
    db = tmp_path / "gateway.db"
    code, out, err = _run(db, "create-admin", "--username", "Root", "--display-name", "The Owner")
    assert code == 0, err
    store = GatewayStore(db, scrypt_n=2**4)
    user = store.find_user("root")
    assert user["role"] == "admin" and user["display_name"] == "The Owner" and not user["must_change"]
    assert store.totp_status(user["id"]) == "none"  # enrols at first login
    assert store.verify_password("root", PW, now=1).ok
    assert PW not in out and PW not in err
    assert any(r["event"] == "first admin created" and r["actor_user_id"] is None and r["actor_username"].startswith("cli:")
               for r in store.read_audit(limit=5))


def test_create_admin_refuses_when_an_admin_exists(tmp_path):
    db = tmp_path / "gateway.db"
    assert _run(db, "create-admin", "--username", "root")[0] == 0
    code, _out, err = _run(db, "create-admin", "--username", "second")
    assert code == 1 and "already" in err
    assert GatewayStore(db, scrypt_n=2**4).find_user("second") is None


def test_create_admin_rejects_a_short_password(tmp_path):
    code, _out, err = _run(tmp_path / "gateway.db", "create-admin", "--username", "root", password="short")
    assert code == 2 and "at least" in err


def test_break_glass_resets_password_totp_lock_disable_and_sessions(tmp_path):
    db = tmp_path / "gateway.db"
    store = GatewayStore(db, scrypt_n=2**4)
    t = Actor(None, "t")
    a = store.create_user("root", "Root", "admin", PW, now=0, actor=t, must_change=False)
    b = store.create_user("second", "Second", "admin", PW, now=0, actor=t, must_change=False)
    secret = store.begin_totp_enrolment(a, now=0)
    from src.gateway import totp
    assert store.confirm_totp(a, totp.code_at(secret, 0), now=1)
    token, _ = store.create_session(a, "active", now=1, client_ip="")
    store.set_disabled(a, True, now=1, actor=t)
    for _ in range(5):
        store.record_failure(a, now=2)
    code, _out, err = _run(db, "break-glass", "--username", "root", password=NEW_PW)
    assert code == 0, err
    store = GatewayStore(db, scrypt_n=2**4)
    assert store.verify_password("root", NEW_PW, now=3).ok  # unlocked, enabled, new password
    assert store.totp_status(a) == "none"
    assert store.get_session(token, now=3) is None
    assert store.get_user(b)["role"] == "admin"
    assert any(r["event"] == "break-glass reset" and r["target_user_id"] == a for r in store.read_audit(limit=10))


def test_break_glass_only_for_admins(tmp_path):
    db = tmp_path / "gateway.db"
    store = GatewayStore(db, scrypt_n=2**4)
    store.create_user("ann", "Ann", "user", PW, now=0, actor=Actor(None, "t"), must_change=False)
    code, _out, err = _run(db, "break-glass", "--username", "ann", password=NEW_PW)
    assert code == 1 and "not an admin" in err
    code, _out, err = _run(db, "break-glass", "--username", "nobody", password=NEW_PW)
    assert code == 1 and "no such" in err


def test_password_mismatch_on_interactive_prompt(tmp_path, monkeypatch):
    answers = iter([PW, PW + "x"])
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt="": next(answers))
    err = io.StringIO()
    code = cli.main(["create-admin", "--db", str(tmp_path / "g.db"), "--username", "root"], stdout=io.StringIO(),
                    stderr=err, scrypt_n=2**4)
    assert code == 2 and "do not match" in err.getvalue()


def test_cli_is_not_reachable_from_the_web(tmp_path):
    app = create_gateway_app(GatewayStore(tmp_path / "gateway.db", scrypt_n=2**4))
    rules = [r.rule for r in app.url_map.iter_rules()]
    assert not any("glass" in r or "create-admin" in r or "cli" in r for r in rules)
    import src.gateway.app as app_mod
    assert "cli" not in {name for name in vars(app_mod)}


def test_cli_runs_as_a_module(tmp_path):
    db = tmp_path / "gateway.db"
    env = {k: v for k, v in os.environ.items()}
    proc = subprocess.run([sys.executable, "-m", "src.gateway.cli", "create-admin", "--db", str(db), "--username", "root",
                           "--password-stdin"], input=PW + "\n", capture_output=True, text=True, cwd=ROOT, env=env,
                          timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert GatewayStore(db).find_user("root")["role"] == "admin"


@pytest.mark.parametrize("args", [[], ["create-admin"], ["break-glass", "--db", "x"]])
def test_cli_usage_errors(args):
    with pytest.raises(SystemExit) as exc:
        cli.main(args, stdout=io.StringIO(), stderr=io.StringIO())
    assert exc.value.code == 2
