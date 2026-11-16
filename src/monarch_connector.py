from __future__ import annotations

"""Monarch's MCP connector: read-only sign-in and sync, feeding the CSV upload's import seam (multi-user Phase 4).

Off unless ``RETIREMENT_SYSTEM_MONARCH_CONNECTOR=1`` is in the worker's environment (the gateway sets it with
``--monarch-connector``). Design and probe results:
``documentation/future/multi-user-server-monarch-secrets-design.md`` section 6.

Sign-in. Monarch's client registration accepts only a loopback redirect (``http://127.0.0.1/callback``), so the
callback cannot reach the server. The flow is "paste back": :func:`start` registers a public client once,
creates a PKCE S256 verifier and a state in this process's memory (ten minutes, one at a time) and returns
Monarch's sign-in address. The user signs in in their own browser, which then lands on an
``http://127.0.0.1/callback?code=...&state=...`` page that does not load; they paste that address into
:func:`complete`, which checks the state and exchanges the code with the verifier. A pasted code is useless
without the verifier, which never leaves this process.

Tokens live only in the worker account's own credential store (``secrets_store``; its remote-mode guard
applies, so a same-account server worker cannot connect at all). Deleting the user's Windows profile deletes
them. Nothing is written to a file; no token, code, account name or number is logged or returned.

Sync pulls ``GetAccounts``, one ``GetNetWorthHistory(accounts=[name], interval="day")`` per account (a
per-account daily history, checked against the account's id or current balance) and ``GetTransactions`` in
pages of 100, then imports through ``monarch_upload.import_transaction_rows`` and
``monarch_upload.import_balance_rows_for_upload`` (the same guards, masking and mapping seed as the upload).
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from . import monarch_upload as up
from . import platform_runtime, secrets_store

LOG = logging.getLogger("retirement_system.monarch_connector")

ENABLE_ENV = "RETIREMENT_SYSTEM_MONARCH_CONNECTOR"
ISSUER = "https://api.monarch.com"
ENDPOINT_PREFIX = ISSUER + "/"
MCP_URL = "https://api.monarch.com/mcp"
SCOPE = "mcp:read"
REDIRECT_URI = "http://127.0.0.1/callback"
CLIENT_NAME = "Retirement Planner"
PROTOCOL_VERSION = "2025-06-18"
SOURCE = "monarch connector"
PENDING_SECONDS = 600
REFRESH_MARGIN = 120
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
PAGE_SIZE = 100
MAX_PAGES = 1000
HISTORY_START = "2000-01-01"
OVERLAP_DAYS = 30
INTENT = {"intent": "financial_planning"}

S_CLIENT, S_ACCESS, S_REFRESH, S_META = ("monarch.client_id", "monarch.access_token", "monarch.refresh_token",
                                         "monarch.connector_meta")
SECRET_NAMES = (S_CLIENT, S_ACCESS, S_REFRESH, S_META)

Transport = Callable[..., tuple[int, dict, bytes]]


class ConnectorError(RuntimeError):
    """A refusal or failure; the message is masked and safe to show the user."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(up.mask_names(message))
        self.status = status


# ---------------------------------------------------------------- transport (tests replace it)

def _urllib_transport(method: str, url: str, *, data: Any = None, headers: dict | None = None,
                      form: bool = False) -> tuple[int, dict, bytes]:
    if not url.startswith(ENDPOINT_PREFIX):
        raise ConnectorError("refused a request to an address outside Monarch's API")
    body = None
    hdrs = {"User-Agent": "retirement-planner/1", "Accept": "application/json"}
    if data is not None:
        body = (urllib.parse.urlencode(data) if form else json.dumps(data)).encode()
        hdrs["Content-Type"] = "application/x-www-form-urlencoded" if form else "application/json"
    hdrs.update(headers or {})
    req = urllib.request.Request(url, data=body, method=method, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 - https only, prefix checked above
            return resp.status, dict(resp.headers), resp.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers or {}), exc.read(MAX_RESPONSE_BYTES + 1)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ConnectorError(f"Monarch could not be reached ({exc.__class__.__name__}).", 502) from None


_transport: Transport = _urllib_transport
_pending: dict[str, Any] = {}
_lock = threading.Lock()
_sync_lock = threading.Lock()


def _http(method: str, url: str, **kw) -> tuple[int, dict, bytes]:
    status, headers, raw = _transport(method, url, **kw)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ConnectorError("Monarch's response was too large.", 502)
    return status, headers, raw


def _json(raw: bytes) -> dict:
    try:
        value = json.loads(raw.decode("utf-8", "replace") or "{}")
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


# ---------------------------------------------------------------- availability and stored state

def enabled() -> bool:
    return (os.environ.get(ENABLE_ENV) or "").strip() == "1"


def _store_error() -> str | None:
    status = secrets_store.encryption_status()
    return None if status.get("store_active") else str(status.get("error") or "no credential store")


def _get(name: str) -> str:
    return secrets_store.get_secret(name)


def _meta() -> dict:
    try:
        value = json.loads(_get(S_META) or "{}")
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def _save_meta(**changes: Any) -> None:
    meta = {**_meta(), **changes}
    secrets_store.set_secret(S_META, json.dumps(meta, sort_keys=True))


def status() -> dict[str, Any]:
    """What the page shows: available or why not, connected, since, last sync summary. Never raises."""
    if not enabled():
        return {"available": False, "connected": False, "reason": "The Monarch connector is not turned on here."}
    err = _store_error()
    if err:
        return {"available": False, "connected": False, "reason": up.mask_names(err)}
    try:
        connected = bool(_get(S_REFRESH))
        meta = _meta()
    except secrets_store.SecretStoreUnavailable as exc:
        return {"available": False, "connected": False, "reason": up.mask_names(exc)}
    return {"available": True, "connected": connected, "connected_at": meta.get("connected_at") if connected else None,
            "last_sync": meta.get("last_sync") if connected else None,
            "sign_in_pending": bool(_pending and _pending.get("expires", 0) > time.time())}


def _require_available() -> None:
    if not enabled():
        raise ConnectorError("The Monarch connector is not turned on here; upload Monarch's CSV exports instead.", 403)
    err = _store_error()
    if err:
        raise ConnectorError(f"The Monarch connector needs this account's own credential store: {err}", 403)


# ---------------------------------------------------------------- OAuth

def _discover() -> dict:
    status_code, _h, raw = _http("GET", ISSUER + "/.well-known/oauth-authorization-server")
    meta = _json(raw)
    if status_code != 200 or meta.get("issuer") != ISSUER:
        raise ConnectorError("Monarch's sign-in service did not answer as expected.", 502)
    for key in ("authorization_endpoint", "token_endpoint", "registration_endpoint"):
        if not str(meta.get(key) or "").startswith(ENDPOINT_PREFIX):
            raise ConnectorError("Monarch's sign-in service named an unexpected address.", 502)
    if meta.get("revocation_endpoint") and not str(meta["revocation_endpoint"]).startswith(ENDPOINT_PREFIX):
        meta.pop("revocation_endpoint")
    return meta


def _client_id(meta: dict) -> str:
    existing = _get(S_CLIENT)
    if existing:
        return existing
    status_code, _h, raw = _http("POST", meta["registration_endpoint"], data={
        "client_name": CLIENT_NAME, "redirect_uris": [REDIRECT_URI], "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"], "token_endpoint_auth_method": "none", "scope": SCOPE})
    client = _json(raw)
    if status_code not in (200, 201) or not client.get("client_id"):
        raise ConnectorError("Monarch refused to register this app "
                             f"({client.get('error_description') or client.get('error') or status_code}).", 502)
    secrets_store.set_secret(S_CLIENT, str(client["client_id"]))
    return str(client["client_id"])


def start() -> dict[str, Any]:
    """Begin sign-in: ``{"authorize_url", "redirect_uri", "expires_in"}``. Replaces any earlier unfinished one."""
    _require_available()
    meta = _discover()
    client_id = _client_id(meta)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(24)
    with _lock:
        _pending.clear()
        _pending.update({"state": state, "verifier": verifier, "client_id": client_id,
                         "token_endpoint": meta["token_endpoint"], "expires": time.time() + PENDING_SECONDS})
    url = meta["authorization_endpoint"] + "?" + urllib.parse.urlencode({
        "response_type": "code", "client_id": client_id, "redirect_uri": REDIRECT_URI, "scope": SCOPE,
        "state": state, "code_challenge": challenge, "code_challenge_method": "S256", "resource": MCP_URL})
    return {"authorize_url": url, "redirect_uri": REDIRECT_URI, "expires_in": PENDING_SECONDS}


def _callback_params(pasted: str) -> dict[str, str]:
    text = str(pasted or "").strip()
    if not text or len(text) > 4096:
        raise ConnectorError("Paste the whole address your browser showed after signing in to Monarch.")
    if "://" in text:
        parts = urllib.parse.urlsplit(text)
        if parts.scheme != "http" or parts.hostname != "127.0.0.1" or parts.path.rstrip("/") != "/callback":
            raise ConnectorError(f"That is not the sign-in return address (it starts with {REDIRECT_URI}).")
        query = parts.query
    else:
        query = text.lstrip("?")
    return {k: v[0] for k, v in urllib.parse.parse_qs(query, keep_blank_values=True).items()}


def _store_tokens(tok: dict) -> None:
    access, refresh = str(tok.get("access_token") or ""), str(tok.get("refresh_token") or "")
    if not access or not refresh:
        raise ConnectorError("Monarch did not return the tokens the connector needs.", 502)
    secrets_store.set_secret(S_ACCESS, access)
    secrets_store.set_secret(S_REFRESH, refresh)
    try:
        lifetime = int(tok.get("expires_in") or 3600)
    except (TypeError, ValueError):
        lifetime = 3600
    _save_meta(access_expires=int(time.time()) + lifetime)


def complete(pasted: str) -> dict[str, Any]:
    """Finish sign-in from the pasted return address; the state must match the unfinished sign-in."""
    _require_available()
    params = _callback_params(pasted)
    with _lock:
        pending = dict(_pending)
        live = bool(pending) and pending.get("expires", 0) > time.time()
        if live and hmac.compare_digest(str(params.get("state") or ""), pending["state"]):
            _pending.clear()  # single use
        else:
            live = False
    if not live:
        raise ConnectorError("This sign-in is not the one started here, or it took more than ten minutes. "
                             "Start again.")
    if params.get("error"):
        raise ConnectorError(f"Monarch did not grant access ({params.get('error')}).")
    if not params.get("code"):
        raise ConnectorError("The pasted address has no sign-in code.")
    status_code, _h, raw = _http("POST", pending["token_endpoint"], form=True, data={
        "grant_type": "authorization_code", "code": params["code"], "redirect_uri": REDIRECT_URI,
        "client_id": pending["client_id"], "code_verifier": pending["verifier"], "resource": MCP_URL})
    tok = _json(raw)
    if status_code != 200:
        raise ConnectorError(f"Monarch refused the sign-in code ({tok.get('error') or status_code}).", 502)
    if SCOPE not in str(tok.get("scope") or SCOPE).split():
        raise ConnectorError("Monarch granted a different access than read-only.", 502)
    _store_tokens(tok)
    _save_meta(connected_at=datetime.now(timezone.utc).isoformat(timespec="seconds"), last_sync=None)
    return status()


def _forget_tokens() -> None:
    for name in (S_ACCESS, S_REFRESH):
        secrets_store.delete_secret(name)


def _access_token() -> str:
    access, refresh = _get(S_ACCESS), _get(S_REFRESH)
    if not refresh:
        raise ConnectorError("Monarch is not connected.", 409)
    if access and int(_meta().get("access_expires") or 0) - REFRESH_MARGIN > time.time():
        return access
    meta = _discover()
    status_code, _h, raw = _http("POST", meta["token_endpoint"], form=True, data={
        "grant_type": "refresh_token", "refresh_token": refresh, "client_id": _get(S_CLIENT), "resource": MCP_URL})
    tok = _json(raw)
    if status_code != 200:
        if status_code in (400, 401) and tok.get("error") in ("invalid_grant", "invalid_client", "unauthorized_client"):
            _forget_tokens()
            raise ConnectorError("Monarch's sign-in has expired or was revoked. Connect again.", 409)
        raise ConnectorError(f"Monarch's sign-in could not be renewed ({tok.get('error') or status_code}).", 502)
    if not tok.get("refresh_token"):
        tok["refresh_token"] = refresh  # not rotated
    _store_tokens(tok)
    return str(tok["access_token"])


def disconnect() -> dict[str, Any]:
    """Revoke at Monarch (best effort) and delete the stored tokens. The registered client id is kept."""
    _require_available()
    revoked = False
    tokens = {"refresh_token": _get(S_REFRESH), "access_token": _get(S_ACCESS)}
    if any(tokens.values()):
        try:
            meta = _discover()
            if meta.get("revocation_endpoint"):
                for hint, value in tokens.items():
                    if value:
                        code, _h, _raw = _http("POST", meta["revocation_endpoint"], form=True, data={
                            "token": value, "token_type_hint": hint, "client_id": _get(S_CLIENT)})
                        revoked = revoked or code == 200
        except ConnectorError:
            pass
    _forget_tokens()
    _save_meta(connected_at=None, last_sync=None, access_expires=0)
    return {**status(), "revoked": revoked}


# ---------------------------------------------------------------- MCP (Streamable HTTP, JSON-RPC over POST)

class _Mcp:
    def __init__(self, token: str) -> None:
        self.token, self.session, self.n = token, None, 0

    def _post(self, msg: dict) -> tuple[int, dict, bytes]:
        headers = {"Authorization": f"Bearer {self.token}", "Accept": "application/json, text/event-stream",
                   "MCP-Protocol-Version": PROTOCOL_VERSION}
        if self.session:
            headers["Mcp-Session-Id"] = self.session
        status_code, resp_headers, raw = _http("POST", MCP_URL, data=msg, headers=headers)
        lower = {str(k).lower(): v for k, v in resp_headers.items()}
        self.session = lower.get("mcp-session-id") or self.session
        if status_code in (401, 403):
            raise ConnectorError("Monarch refused the stored sign-in. Connect again.", 409)
        return status_code, resp_headers, raw

    def request(self, method: str, params: dict | None = None) -> dict:
        self.n += 1
        msg = {"jsonrpc": "2.0", "id": self.n, "method": method, "params": params or {}}
        status_code, _h, raw = self._post(msg)
        text = raw.decode("utf-8", "replace")
        obj: dict = {}
        if text.lstrip().startswith("{"):
            obj = _json(raw)
        else:
            for line in text.splitlines():  # an event stream: the data line answering our id
                if line.startswith("data:"):
                    try:
                        cand = json.loads(line[5:].strip())
                    except ValueError:
                        continue
                    if isinstance(cand, dict) and cand.get("id") == self.n:
                        obj = cand
        if status_code != 200 or "result" not in obj:
            raise ConnectorError(f"Monarch's connector answered {status_code} to {method}.", 502)
        return obj["result"]

    def open(self) -> "_Mcp":
        self.request("initialize", {"protocolVersion": PROTOCOL_VERSION, "capabilities": {},
                                    "clientInfo": {"name": "retirement-planner", "version": "1"}})
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return self

    def tool(self, name: str, **args: Any) -> dict:
        result = self.request("tools/call", {"name": name, "arguments": {**INTENT, **args}})
        content = result.get("structuredContent")
        texts = [c.get("text", "") for c in result.get("content") or [] if isinstance(c, dict) and c.get("type") == "text"]
        if result.get("isError"):
            raise ConnectorError(f"Monarch's {name} failed: {(texts or [''])[0][:200]}", 502)
        if content is None and texts:
            content = _json(texts[0].encode())
        if isinstance(content, dict) and set(content) == {"result"} and isinstance(content["result"], str):
            content = _json(content["result"].encode())  # Monarch wraps its JSON in a string
        if not isinstance(content, dict):
            raise ConnectorError(f"Monarch's {name} returned no data.", 502)
        return content


# ---------------------------------------------------------------- sync

def _date10(value: Any) -> str:
    text = str(value or "")[:10]
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        return ""


def _amount_text(value: Any) -> str:
    try:
        return repr(round(float(value), 2))
    except (TypeError, ValueError):
        return ""


def fetch_transactions(mcp: _Mcp, start: str, end: str) -> tuple[list[dict[str, Any]], int]:
    """Posted transactions in the upload's normalised shape, and how many pending ones were left out."""
    out, pending, offset = [], 0, 0
    for _ in range(MAX_PAGES):
        page = mcp.tool("GetTransactions", start_date=start, end_date=end, limit=PAGE_SIZE, offset=offset)
        for t in page.get("transactions") or []:
            if not isinstance(t, dict):
                continue
            if t.get("pending"):
                pending += 1  # its amount or merchant may still change; the next sync takes it once posted
                continue
            out.append({"id": str(t.get("id") or ""), "date": _date10(t.get("date")),
                        "merchant": str(t.get("merchant") or ""), "amount": _amount_text(t.get("amount")),
                        # cleaned like the balances' names: Monarch's connector and its CSV export differ in
                        # spaces (non-breaking, doubled) for some accounts; measured on the owner's data
                        "account": up._clean_account_name(str(t.get("account") or "")),
                        "category": str(t.get("category") or ""),
                        "source_columns": {}})
        nxt = page.get("next_offset")
        if not isinstance(nxt, int) or nxt <= offset:
            return out, pending
        offset = nxt
    raise ConnectorError(f"Monarch returned more than {MAX_PAGES * PAGE_SIZE:,} transactions; sync stopped.", 502)


def fetch_balances(mcp: _Mcp, start: str, end: str) -> tuple[list[tuple[str, str, str, float]], dict[str, int]]:
    """Daily ``(date, account_key, account, balance)`` rows for every account whose history checks out."""
    accounts_doc = mcp.tool("GetAccounts")
    accounts = [a for a in accounts_doc.get("accounts") or [] if isinstance(a, dict) and a.get("name")]
    names = [up._clean_account_name(str(a["name"])) for a in accounts]
    counts = {"accounts_seen": len(accounts), "accounts_ambiguous": 0, "accounts_unverified": 0,
              "accounts_without_history": 0,
              "hidden_by_monarch": int(((accounts_doc.get("finicity_excluded") or {}).get("hidden_account_count")) or 0)}
    rows: dict[tuple[str, str], tuple[str, str, str, float]] = {}
    for a, name in zip(accounts, names):
        if names.count(name) > 1 or any(n != name and n.casefold() == name.casefold() for n in names):
            counts["accounts_ambiguous"] += 1  # the history filter matches by name
            continue
        doc = mcp.tool("GetNetWorthHistory", start_date=start, end_date=end, accounts=[str(a["name"])], interval="day")
        snaps = [s for s in doc.get("snapshots") or [] if isinstance(s, dict) and _date10(s.get("date"))]
        if not snaps:
            counts["accounts_without_history"] += 1
            continue
        delta_ids = {str(d.get("account_id")) for d in doc.get("account_deltas") or [] if isinstance(d, dict)}
        latest = max(snaps, key=lambda s: _date10(s.get("date")))
        try:
            balance_ok = abs(float(latest.get("net_worth") or 0) - float(a.get("balance") or 0)) < 0.015
        except (TypeError, ValueError):
            balance_ok = False
        if (delta_ids and delta_ids != {str(a.get("id"))}) or (not delta_ids and not balance_ok):
            counts["accounts_unverified"] += 1  # the filter did not pick out exactly this account
            continue
        for s in snaps:
            try:
                value = round(float(s.get("net_worth")), 2)
            except (TypeError, ValueError):
                continue
            iso = _date10(s.get("date"))
            rows[(iso, name.casefold())] = (iso, name.casefold(), name, value)
    return sorted(rows.values(), key=lambda r: (r[0], r[1])), counts


def sync(base_dir: str | Path, *, dry_run: bool = False, full: bool = False, today: date | None = None,
         now: datetime | None = None) -> dict[str, Any]:
    """Pull from Monarch and import. Incremental after the first sync (30 days of overlap, so edits arrive)."""
    _require_available()
    if not _sync_lock.acquire(blocking=False):
        raise ConnectorError("A Monarch sync is already running.", 409)
    try:
        today = today or platform_runtime.today()
        last = (_meta().get("last_sync") or {}) if not full else {}
        since = last.get("through") if isinstance(last, dict) else None
        start = HISTORY_START
        if since and _date10(since):
            start = (date.fromisoformat(_date10(since)) - timedelta(days=OVERLAP_DAYS)).isoformat()
        end = today.isoformat()
        mcp = _Mcp(_access_token()).open()
        balances, counts = fetch_balances(mcp, start, end)
        transactions, pending = fetch_transactions(mcp, start, end)
        result: dict[str, Any] = {"success": True, "dry_run": dry_run, "window": [start, end], **counts,
                                  "pending_skipped": pending}
        if transactions:
            result["transactions"] = up.import_transaction_rows(base_dir, transactions, dry_run=dry_run)
        else:
            result["transactions"] = {"rows_read": 0, "added": 0, "updated": 0, "adopted": 0, "skipped": 0}
        if balances:
            result["balances"] = up.import_balance_rows_for_upload(
                base_dir, balances, dry_run=dry_run, today=today, now=now, source=SOURCE, compare_same_source=True)
            if not result["balances"].get("success"):
                result["success"] = False
                result["error"] = result["balances"].get("error") or "the balances were rejected"
        else:
            result["balances"] = {"rows": 0, "status": "skipped"}
        if not dry_run:
            summary = {"at": (now or datetime.now(timezone.utc)).isoformat(timespec="seconds"),
                       "through": end if result["success"] else (since or None),
                       "transactions_added": result["transactions"].get("added", 0),
                       "transactions_updated": result["transactions"].get("updated", 0),
                       "balance_rows": result["balances"].get("rows", 0),
                       "status": "ok" if result["success"] else "balances rejected"}
            _save_meta(last_sync=summary)
        LOG.info("Monarch connector sync%s: %s transactions, %s balance rows, %s accounts, status %s",
                 " (dry run)" if dry_run else "", result["transactions"].get("rows_read"),
                 result["balances"].get("rows"), counts["accounts_seen"], "ok" if result["success"] else "rejected")
        return result
    except up.UploadError as exc:
        raise ConnectorError(str(exc)) from None
    finally:
        _sync_lock.release()
