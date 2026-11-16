"""Remote mode: GET /api/ytd/status must not scan sibling install folders or stored roots for account setup files."""
from __future__ import annotations

from src.server_services import ytd_service

HEADER = "Account,Role,Mapped Investment Account,Prior Year End Balance,Current Value\n"


def test_recovery_ignores_files_outside_the_workspace_in_remote_mode(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("RETIREMENT_SYSTEM_REMOTE_MODE", "1")
    monkeypatch.setenv("RETIREMENT_SYSTEM_WORKSPACE_ROOT", str(ws))
    install = tmp_path / "apps" / "install"
    install.mkdir(parents=True)
    other = tmp_path / "apps" / "ownercopy" / "input"
    other.mkdir(parents=True)
    (other / "ytd_account_setup.csv").write_text(HEADER + "OWNER SECRET ACCT,Brokerage,X,999999,888888\n")
    stored_root = tmp_path / "stored"
    (stored_root / "input").mkdir(parents=True)
    (stored_root / "input" / "ytd_account_setup.csv").write_text(HEADER + "STORED ROOT ACCT,Brokerage,X,1,2\n")
    ctx = ytd_service.YtdServiceContext(
        base_dir=install, plan_data_path=lambda n, prefer_existing=False: ws / "input" / n,
        path_roots_from_config=lambda: [stored_root], server_path_allowed=lambda p: (True, ""),
        audit=lambda *a, **k: None)
    svc = ytd_service.YtdService(ctx)
    svc.account_setup_text = lambda: ""
    texts = " ".join(c["text"] for c in svc.account_setup_recovery_candidates())
    assert "OWNER SECRET ACCT" not in texts and "STORED ROOT ACCT" not in texts
