"""Monarch MCP connector (multi-user Phase 4, item 6) against a fake Monarch: no live calls.

The fake reproduces what the owner's probe measured on 2026-11-16: discovery on api.monarch.com, dynamic client
registration that accepts only ``http://127.0.0.1/callback``, PKCE S256, rotated refresh tokens, Streamable HTTP
JSON-RPC, tool results wrapped as ``{"result": "<json string>"}``, transactions in pages of 100 with
``next_offset``, and a per-account daily history from ``GetNetWorthHistory(accounts=[name], interval="day")``.
Synthetic data only; the long number is built at run time.
"""
from __future__ import annotations

import base64
import hashlib
import json
import secrets as _secrets
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from src import active_plan, monarch_connector as mc, platform_runtime, remote_mode, secrets_store
from src import ytd_tracking as ytd

TODAY = date(2026, 11, 16)
NOW = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)
LONG_NUMBER = "7" * 9  # synthetic


class FakeMonarch:
    def __init__(self, n_tx: int = 230) -> None:
        self.clients: dict[str, str] = {}
        self.codes: dict[str, tuple[str, str]] = {}
        self.access: set[str] = set()
        self.refresh: set[str] = set()
        self.revoked: list[str] = []
        self.calls: list[tuple[str, dict]] = []
        self.meta_override: dict = {}
        self.refresh_error: str | None = None
        self.accounts = [
            {"id": "acc-1", "name": "Joint  Checking (...4821)", "type": "Checking", "balance": 1300.0},
            {"id": "acc-2", "name": f"Brokerage {LONG_NUMBER}", "type": "Brokerage (Taxable)", "balance": 5300.0},
        ]
        self.history_ids = {"acc-1": "acc-1", "acc-2": "acc-2"}
        self.transactions = [
            {"id": f"tx-{i}", "date": (TODAY - timedelta(days=i % 60)).isoformat(), "pending": i == 0,
             "merchant": f"Shop {i}", "amount": -float(i) - 0.5, "category": "Groceries",
             "account": self.accounts[i % 2]["name"], "account_id": self.accounts[i % 2]["id"]}
            for i in range(n_tx)]

    # -- the browser part, done by the user in their own browser
    def authorize(self, url: str, *, state: str | None = None) -> str:
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
        assert q["redirect_uri"] == mc.REDIRECT_URI and q["scope"] == mc.SCOPE
        assert q["code_challenge_method"] == "S256" and q["resource"] == mc.MCP_URL
        assert self.clients[q["client_id"]] == q["redirect_uri"]
        code = _secrets.token_urlsafe(8)
        self.codes[code] = (q["client_id"], q["code_challenge"])
        return f"{mc.REDIRECT_URI}?code={code}&state={state or q['state']}"

    # -- the transport
    def __call__(self, method, url, *, data=None, headers=None, form=False):
        path = urllib.parse.urlsplit(url).path
        if path == "/.well-known/oauth-authorization-server":
            meta = {"issuer": mc.ISSUER, "authorization_endpoint": mc.ISSUER + "/oauth/authorize/",
                    "token_endpoint": mc.ISSUER + "/oauth/token/", "registration_endpoint": mc.ISSUER + "/oauth/register",
                    "revocation_endpoint": mc.ISSUER + "/oauth/revoke/", **self.meta_override}
            return 200, {}, json.dumps(meta).encode()
        if path == "/oauth/register":
            redirect = data["redirect_uris"][0]
            if redirect != mc.REDIRECT_URI:
                return 400, {}, json.dumps({"error": "invalid_redirect_uri",
                                            "error_description": "Redirect URI is not supported"}).encode()
            cid = f"client-{len(self.clients) + 1}"
            self.clients[cid] = redirect
            return 201, {}, json.dumps({"client_id": cid}).encode()
        if path == "/oauth/token/":
            return self._token(data)
        if path == "/oauth/revoke/":
            self.revoked.append(data["token_type_hint"])
            return 200, {}, b""
        if path == "/mcp":
            return self._mcp(data, headers)
        return 404, {}, b"{}"

    def _issue(self) -> tuple[int, dict, bytes]:
        access, refresh = "at-" + _secrets.token_hex(8), "rt-" + _secrets.token_hex(8)
        self.access.add(access)
        self.refresh.add(refresh)
        return 200, {}, json.dumps({"access_token": access, "refresh_token": refresh, "token_type": "Bearer",
                                    "expires_in": 3600, "scope": mc.SCOPE}).encode()

    def _token(self, data):
        if data["grant_type"] == "authorization_code":
            client_id, challenge = self.codes.pop(data["code"], (None, None))
            digest = base64.urlsafe_b64encode(hashlib.sha256(data["code_verifier"].encode()).digest()).rstrip(b"=")
            if client_id != data["client_id"] or digest.decode() != challenge or data["redirect_uri"] != mc.REDIRECT_URI:
                return 400, {}, b'{"error": "invalid_grant"}'
            return self._issue()
        if self.refresh_error or data["refresh_token"] not in self.refresh:
            return 400, {}, json.dumps({"error": self.refresh_error or "invalid_grant"}).encode()
        self.refresh.discard(data["refresh_token"])  # rotated
        return self._issue()

    def _mcp(self, msg, headers):
        if headers.get("Authorization", "").removeprefix("Bearer ") not in self.access:
            return 401, {}, b"{}"
        if "id" not in msg:
            return 202, {}, b""
        if msg["method"] == "initialize":  # answered as an event stream, like Streamable HTTP may
            body = {"jsonrpc": "2.0", "id": msg["id"], "result": {"serverInfo": {"name": "Monarch Money"}}}
            return 200, {"Mcp-Session-Id": "s-1"}, f"event: message\ndata: {json.dumps(body)}\n\n".encode()
        assert headers.get("Mcp-Session-Id") == "s-1"
        name, args = msg["params"]["name"], msg["params"]["arguments"]
        assert args["intent"] == "financial_planning"
        self.calls.append((name, args))
        payload = getattr(self, "_tool_" + name)(args)
        result = {"structuredContent": {"result": json.dumps(payload)}, "isError": False}
        return 200, {}, json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": result}).encode()

    def _tool_GetAccounts(self, args):  # noqa: N802
        return {"accounts": self.accounts, "finicity_excluded": {"hidden_account_count": 1}}

    def _tool_GetNetWorthHistory(self, args):  # noqa: N802
        acct = next(a for a in self.accounts if a["name"] == args["accounts"][0])
        start = max(date.fromisoformat(args["start_date"]), TODAY - timedelta(days=2))
        days = [(start + timedelta(days=i)).isoformat() for i in range((TODAY - start).days + 1)]
        snaps = [{"date": d, "net_worth": acct["balance"] - 100 * (len(days) - 1 - i)} for i, d in enumerate(days)]
        return {"snapshots": snaps, "account_deltas": [{"account_id": self.history_ids[acct["id"]]}]}

    def _tool_GetTransactions(self, args):  # noqa: N802
        rows = [t for t in self.transactions if args["start_date"] <= t["date"] <= args["end_date"]]
        page = rows[args["offset"]:args["offset"] + args["limit"]]
        more = args["offset"] + len(page) < len(rows)
        return {"transactions": page, "transaction_count": len(rows),
                **({"next_offset": args["offset"] + len(page)} if more else {})}


@pytest.fixture
def fake(monkeypatch):
    store: dict[str, str] = {}
    monkeypatch.setattr(secrets_store, "get_secret", lambda name, *a, **k: store.get(name, ""))
    monkeypatch.setattr(secrets_store, "set_secret", lambda name, value, *a, **k: store.__setitem__(name, value))
    monkeypatch.setattr(secrets_store, "delete_secret", lambda name, *a, **k: store.pop(name, None))
    monkeypatch.setattr(secrets_store, "encryption_status", lambda *a, **k: {"store_active": True})
    monkeypatch.setenv(mc.ENABLE_ENV, "1")
    monarch = FakeMonarch()
    monarch.store = store
    monkeypatch.setattr(mc, "_transport", monarch)
    mc._pending.clear()
    yield monarch
    mc._pending.clear()


@pytest.fixture
def base(tmp_path):
    ws = tmp_path / "ws"
    (ws / "input").mkdir(parents=True)
    return ws


def _connect(fake) -> dict:
    started = mc.start()
    return mc.complete(fake.authorize(started["authorize_url"]))


def _no_token_in(fake, payload) -> None:
    text = json.dumps(payload)
    for value in [*fake.access, *fake.refresh, *fake.codes]:
        assert value not in text
    assert LONG_NUMBER not in text


# ---------------------------------------------------------------- availability

def test_off_by_default(monkeypatch):
    monkeypatch.delenv(mc.ENABLE_ENV, raising=False)
    assert mc.status() == {"available": False, "connected": False,
                           "reason": "The Monarch connector is not turned on here."}
    with pytest.raises(mc.ConnectorError) as exc:
        mc.start()
    assert exc.value.status == 403


def test_a_same_account_server_worker_cannot_connect(monkeypatch):
    """The Phase 4 secrets guard applies: no private credential store, no connector."""
    monkeypatch.setenv(mc.ENABLE_ENV, "1")
    monkeypatch.setenv(remote_mode.REMOTE_MODE_ENV, "1")
    monkeypatch.delenv(secrets_store.DEDICATED_ACCOUNT_ENV, raising=False)
    st = mc.status()
    assert st["available"] is False and "own Windows account" in st["reason"]
    with pytest.raises(mc.ConnectorError):
        mc.start()


def test_transport_refuses_addresses_outside_monarch():
    with pytest.raises(mc.ConnectorError, match="outside Monarch"):
        mc._urllib_transport("GET", "https://example.invalid/steal")


def test_discovery_naming_another_host_is_refused(fake):
    fake.meta_override = {"token_endpoint": "https://evil.example/token"}
    with pytest.raises(mc.ConnectorError, match="unexpected address"):
        mc.start()


# ---------------------------------------------------------------- sign-in

def test_sign_in_round_trip_stores_tokens_only_in_the_credential_store(fake):
    st = _connect(fake)
    assert st["connected"] is True and st["available"] is True and st["connected_at"]
    assert set(fake.store) == {mc.S_CLIENT, mc.S_ACCESS, mc.S_REFRESH, mc.S_META}
    assert fake.store[mc.S_ACCESS] in fake.access and fake.store[mc.S_REFRESH] in fake.refresh
    _no_token_in(fake, st)
    assert fake.clients == {"client-1": mc.REDIRECT_URI}
    _connect(fake)
    assert len(fake.clients) == 1, "the registered client is reused"


def test_complete_refuses_a_foreign_state_and_is_single_use(fake):
    started = mc.start()
    with pytest.raises(mc.ConnectorError, match="not the one started here"):
        mc.complete(fake.authorize(started["authorize_url"], state="someone-elses"))
    good = fake.authorize(started["authorize_url"])
    mc.complete(good)
    with pytest.raises(mc.ConnectorError, match="not the one started here"):
        mc.complete(good)


def test_complete_refuses_an_expired_sign_in(fake, monkeypatch):
    started = mc.start()
    mc._pending["expires"] = 0
    with pytest.raises(mc.ConnectorError, match="ten minutes"):
        mc.complete(fake.authorize(started["authorize_url"]))


@pytest.mark.parametrize("pasted", ["https://127.0.0.1/callback?code=a&state=b", "http://evil.example/callback?code=a",
                                    "http://127.0.0.1/other?code=a", "", "x" * 5000])
def test_complete_accepts_only_the_loopback_return_address(fake, pasted):
    mc.start()
    with pytest.raises(mc.ConnectorError):
        mc.complete(pasted)


def test_query_string_alone_is_accepted(fake):
    started = mc.start()
    url = fake.authorize(started["authorize_url"])
    assert mc.complete(url.split("?", 1)[1])["connected"] is True


def test_a_declined_consent_is_reported(fake):
    started = mc.start()
    state = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(started["authorize_url"]).query))["state"]
    with pytest.raises(mc.ConnectorError, match="access_denied"):
        mc.complete(f"{mc.REDIRECT_URI}?error=access_denied&state={state}")


def test_registration_uses_only_the_redirect_monarch_accepts(fake):
    status, _h, raw = fake("POST", mc.ISSUER + "/oauth/register",
                           data={"redirect_uris": ["https://node.example.ts.net:8443/gateway/monarch/callback"]})
    assert status == 400 and b"not supported" in raw
    mc.start()
    assert list(fake.clients.values()) == [mc.REDIRECT_URI]


# ---------------------------------------------------------------- tokens

def test_an_expired_access_token_is_refreshed_and_the_rotation_kept(fake, base):
    _connect(fake)
    old_refresh = fake.store[mc.S_REFRESH]
    mc._save_meta(access_expires=0)
    mc.sync(base, dry_run=True, today=TODAY, now=NOW)
    assert fake.store[mc.S_REFRESH] != old_refresh and fake.store[mc.S_REFRESH] in fake.refresh


def test_a_revoked_grant_forgets_the_tokens(fake, base):
    _connect(fake)
    mc._save_meta(access_expires=0)
    fake.refresh_error = "invalid_grant"
    with pytest.raises(mc.ConnectorError, match="Connect again") as exc:
        mc.sync(base, today=TODAY, now=NOW)
    assert exc.value.status == 409
    assert mc.S_REFRESH not in fake.store and mc.status()["connected"] is False


def test_disconnect_revokes_and_deletes(fake):
    _connect(fake)
    out = mc.disconnect()
    assert out["revoked"] is True and out["connected"] is False
    assert sorted(fake.revoked) == ["access_token", "refresh_token"]
    assert mc.S_ACCESS not in fake.store and mc.S_REFRESH not in fake.store


# ---------------------------------------------------------------- sync

def _stored(base: Path) -> list[dict]:
    return ytd.read_transactions(base / "input")


def test_sync_imports_transactions_and_daily_balances(fake, base):
    _connect(fake)
    out = mc.sync(base, today=TODAY, now=NOW)
    assert out["success"] is True and out["window"] == [mc.HISTORY_START, TODAY.isoformat()]
    tx = out["transactions"]
    assert tx["rows_read"] == 229 and tx["added"] == 229 and out["pending_skipped"] == 1
    assert sum(1 for name, _a in fake.calls if name == "GetTransactions") == 3, "paged by next_offset"
    rows = _stored(base)
    assert len(rows) == 229 and {r["Monarch Id"] for r in rows} == {f"tx-{i}" for i in range(1, 230)}
    assert {r["Account"] for r in rows} == {"Joint Checking (...4821)", f"Brokerage {LONG_NUMBER}"}, "spaces cleaned"
    bal = out["balances"]
    assert bal["status"] == "ok" and bal["rows"] == 6 and bal["latest_date"] == TODAY.isoformat()
    assert out["hidden_by_monarch"] == 1 and out["accounts_seen"] == 2
    with active_plan.workspace_store(base) as store:
        assert store.monarch.last_import(ok_only=True)["source_file"] == mc.SOURCE
    _no_token_in(fake, out)


def test_second_sync_is_incremental_and_idempotent(fake, base):
    _connect(fake)
    mc.sync(base, today=TODAY, now=NOW)
    fake.calls.clear()
    out = mc.sync(base, today=TODAY, now=NOW)
    start = (TODAY - timedelta(days=mc.OVERLAP_DAYS)).isoformat()
    assert out["window"] == [start, TODAY.isoformat()]
    assert {a["start_date"] for n, a in fake.calls if n != "GetAccounts"} == {start}
    assert out["transactions"]["added"] == 0 and len(_stored(base)) == 229
    assert mc.status()["last_sync"]["through"] == TODAY.isoformat()


def test_dry_run_writes_nothing(fake, base):
    _connect(fake)
    out = mc.sync(base, dry_run=True, today=TODAY, now=NOW)
    assert out["balances"]["status"] == "dry_run" and out["transactions"]["added"] == 0
    assert _stored(base) == [] and mc.status()["last_sync"] is None


def test_an_account_the_history_filter_did_not_pick_out_is_skipped(fake, base):
    _connect(fake)
    fake.history_ids["acc-2"] = "acc-other"
    out = mc.sync(base, today=TODAY, now=NOW)
    assert out["accounts_unverified"] == 1 and out["balances"]["accounts"] == 1


def test_connector_drop_guard_compares_with_its_own_earlier_syncs(fake, base):
    """A CSV export lists closed accounts too; the connector only open ones. Comparing the two would always fail."""
    from src import monarch_balances_import as mbi

    csv_rows = [(TODAY.isoformat(), f"acct {i}", f"Acct {i}", 1.0) for i in range(10)]
    assert mbi.import_balance_rows(base, csv_rows, source="browser upload", today=TODAY, now=NOW)["status"] == "ok"
    _connect(fake)
    assert mc.sync(base, today=TODAY, now=NOW)["balances"]["status"] == "ok"
    fake.accounts.extend({"id": f"acc-{i}", "name": f"Extra {i}", "type": "Other", "balance": 1.0} for i in range(3, 13))
    fake.history_ids.update({f"acc-{i}": f"acc-{i}" for i in range(3, 13)})
    assert mc.sync(base, today=TODAY, now=NOW)["balances"]["accounts"] == 12
    del fake.accounts[2:]
    out = mc.sync(base, today=TODAY, now=NOW)
    assert out["success"] is False and out["balances"]["status"] == "rejected"
    assert mc.status()["last_sync"]["status"] == "balances rejected"


def test_a_second_sync_at_once_is_refused(fake, base):
    _connect(fake)
    assert mc._sync_lock.acquire(blocking=False)
    try:
        with pytest.raises(mc.ConnectorError, match="already running"):
            mc.sync(base, today=TODAY, now=NOW)
    finally:
        mc._sync_lock.release()


# ---------------------------------------------------------------- routes (remote mode, in process)

TOKEN = "test-worker-token-0123456789"


@pytest.fixture
def remote(monkeypatch, base):
    from src.server import app_core, base_routes, create_app, monarch_routes, plan_routes, workbook_routes

    live = platform_runtime.workspace_root()
    for module in (app_core, base_routes, plan_routes, workbook_routes):
        monkeypatch.setattr(module, "WORKSPACE_ROOT", live, raising=False)
    monkeypatch.setenv(remote_mode.REMOTE_MODE_ENV, "1")
    monkeypatch.setenv(remote_mode.TOKEN_ENV, TOKEN)
    monkeypatch.setattr(monarch_routes, "_ytd_input_root", lambda: base / "input")
    return create_app().test_client()


def _call(client, method, path, body=None):
    return client.open(path, method=method, json=body, headers={"X-API-Token": TOKEN})


def test_connector_routes_round_trip_in_remote_mode(remote, fake, base, monkeypatch):
    monkeypatch.setattr(platform_runtime, "today", lambda: TODAY)
    assert _call(remote, "GET", "/api/monarch/connector").get_json()["connected"] is False
    started = _call(remote, "POST", "/api/monarch/connector/start").get_json()
    done = _call(remote, "POST", "/api/monarch/connector/complete",
                 {"callback_url": fake.authorize(started["authorize_url"])})
    assert done.status_code == 200 and done.get_json()["connected"] is True
    synced = _call(remote, "POST", "/api/monarch/connector/sync", {})
    assert synced.status_code == 200 and synced.get_json()["transactions"]["added"] == 229
    _no_token_in(fake, synced.get_json())
    gone = _call(remote, "POST", "/api/monarch/connector/disconnect")
    assert gone.get_json()["connected"] is False


def test_connector_routes_refuse_when_off(remote, monkeypatch):
    monkeypatch.delenv(mc.ENABLE_ENV, raising=False)
    assert _call(remote, "GET", "/api/monarch/connector").get_json()["available"] is False
    assert _call(remote, "POST", "/api/monarch/connector/start").status_code == 403
    assert _call(remote, "POST", "/api/monarch/connector/complete", {"callback_url": "x"}).status_code == 403


def test_gateway_flag_turns_the_connector_on_for_workers():
    from src.gateway import server as gateway_server

    assert gateway_server.MONARCH_CONNECTOR_ENV == mc.ENABLE_ENV
    args = gateway_server._parser().parse_args(["--db", "g.db", "--monarch-connector"])
    assert args.monarch_connector is True
