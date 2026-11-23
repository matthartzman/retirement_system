from __future__ import annotations

"""Append-only JSON Lines trend log (ticket 306).

One JSON object per weekday-5pm run, keyed by ``as_of_date``. A JSON category
breakdown is used (not CSV) because the category key set changes as
categories are added/renamed -- CSV would need a header rewrite every time
that happens; JSONL just appends. Re-running on the same ``as_of_date``
overwrites that date's line rather than duplicating it, so a manual re-run
or a retried scheduled fire is safe.
"""

import hashlib
import hmac
import json
import logging
import os
import secrets
import shutil
import time
from pathlib import Path
from typing import Any

from src.http_runtime.local_token_gate import restrict_to_current_user
from src.plan_file_io import write_text_atomic

LOG = logging.getLogger("retirement.trends_log")

LOG_FILENAME = "financial_trends_log.jsonl"


def default_log_path(base_dir: str | Path) -> Path:
    return Path(base_dir) / "data" / LOG_FILENAME


def rejected_path(log_path: str | Path) -> Path:
    """Sidecar that holds lines quarantined from the log (WI-203)."""
    path = Path(log_path)
    return path.with_name(path.name + ".rejected")


# ---- integrity (F-03) -----------------------------------------------------------------------------------------
# Every line carries ``_mac``, an HMAC-SHA256 over the entry (canonical JSON) under a key kept beside the log, owner
# only. A sidecar ``<log>.head`` holds the line count and an HMAC over the sorted line MACs, so a deleted, truncated or
# re-ordered-in-place log is detected too. A line that fails is NEVER silently dropped: it is quarantined to the
# ``.rejected`` sidecar on the next write, every discrepancy is appended to ``<log>.integrity.json``, and the report
# is available to the UI and the verify tool. A log with no head file is a legacy (unsigned) log: its lines are
# accepted once and signed by the next write. Once a head exists, an unsigned line is treated as tampered.
# The key sits next to the data, so this defeats accidental damage and anyone who can edit the log but not read the
# key (it does not defeat a process that can read both).

MAC_FIELD = "_mac"


def _key_path(log_path: Path) -> Path:
    return log_path.with_name(log_path.name + ".key")


def head_path(log_path: str | Path) -> Path:
    path = Path(log_path)
    return path.with_name(path.name + ".head")


def integrity_path(log_path: str | Path) -> Path:
    path = Path(log_path)
    return path.with_name(path.name + ".integrity.json")


def _load_key(log_path: Path, *, create: bool) -> bytes | None:
    kp = _key_path(log_path)
    try:
        return bytes.fromhex(kp.read_text(encoding="ascii").strip())
    except (OSError, ValueError):
        pass
    if not create:
        return None
    kp.parent.mkdir(parents=True, exist_ok=True)
    key = secrets.token_bytes(32)
    tmp = kp.with_name(kp.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="ascii") as fh:
        fh.write(key.hex() + "\n")
    restrict_to_current_user(tmp)
    os.replace(tmp, kp)
    return key


def _canonical(entry: dict[str, Any]) -> bytes:
    body = {k: v for k, v in entry.items() if k != MAC_FIELD}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _mac(key: bytes, entry: dict[str, Any]) -> str:
    return hmac.new(key, b"line\0" + _canonical(entry), hashlib.sha256).hexdigest()


def _head_mac(key: bytes, macs: list[str]) -> str:
    return hmac.new(key, b"head\0" + str(len(macs)).encode() + b"\0" + "\n".join(sorted(macs)).encode(),
                    hashlib.sha256).hexdigest()


def _serialise(key: bytes, entries: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    """The signed file text and the head record for ``entries``."""
    signed = [{**{k: v for k, v in e.items() if k != MAC_FIELD}, MAC_FIELD: _mac(key, e)} for e in entries]
    text = "\n".join(json.dumps(e, sort_keys=True) for e in signed) + ("\n" if signed else "")
    macs = [e[MAC_FIELD] for e in signed]
    return text, {"count": len(macs), "mac": _head_mac(key, macs)}


def _read_head(path: Path) -> dict[str, Any] | None:
    try:
        obj = json.loads(head_path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return obj if isinstance(obj, dict) else None


def _raw_lines(path: Path) -> list[dict[str, Any] | str]:
    """Each non-empty line as a dict, or as the raw string when it is not a JSON object."""
    out: list[dict[str, Any] | str] = []
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            out.append(line)
            continue
        out.append(obj if isinstance(obj, dict) else line)
    return out


def verify_log(log_path: str | Path) -> dict[str, Any]:
    """Check a log. Returns ``{"entries": [...trusted entries, without _mac...], "bad": [raw lines that failed],
    "status": "ok" | "legacy" | "damaged" | "missing", "problems": [str], "legacy_lines": n}``. Reads only."""
    path = Path(log_path)
    lines = _raw_lines(path)
    head = _read_head(path)
    key = _load_key(path, create=False)
    entries: list[dict[str, Any]] = []
    bad: list[str] = []
    problems: list[str] = []
    legacy = 0
    signed_mode = head is not None
    macs: list[str] = []
    for item in lines:
        if isinstance(item, str):
            bad.append(item)
            problems.append("a line that is not a JSON object")
            continue
        mac = item.get(MAC_FIELD)
        body = {k: v for k, v in item.items() if k != MAC_FIELD}
        if not signed_mode:
            # No head record: a log from before signing, or one restored from a backup (which carries the log but not
            # its key or head). Accepted once; the next write signs it with a fresh key.
            legacy += 1
            entries.append(body)
            continue
        if mac is None:
            bad.append(json.dumps(item, sort_keys=True))
            problems.append(f"an unsigned line in a signed log ({item.get('as_of_date')})")
            continue
        if key is None or not isinstance(mac, str) or not hmac.compare_digest(mac, _mac(key, body)):
            bad.append(json.dumps(item, sort_keys=True))
            problems.append(f"a line whose signature does not match ({item.get('as_of_date')})")
            continue
        entries.append(body)
        macs.append(mac)
    if signed_mode and key is not None:
        expected = int(head.get("count") or 0)
        if not hmac.compare_digest(str(head.get("mac") or ""), _head_mac(key, macs)):
            lost = max(0, expected - len(macs))
            problems.append(f"the log does not match its signed record: {expected} line(s) were signed, {len(macs)} "
                            f"verify ({lost} missing or altered)")
    elif signed_mode and key is None:
        problems.append("the log key is missing, so no line can be verified")
    status = "missing" if not path.exists() else "damaged" if problems else "legacy" if legacy else "ok"
    return {"entries": entries, "bad": bad, "status": status, "problems": problems, "legacy_lines": legacy}


def _record_event(path: Path, report: dict[str, Any]) -> None:
    """Append the discrepancy to the integrity sidecar so it outlives the rewrite that follows."""
    ip = integrity_path(path)
    try:
        events = json.loads(ip.read_text(encoding="utf-8"))
        events = events if isinstance(events, list) else []
    except (OSError, ValueError):
        events = []
    events.append({"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "problems": report["problems"][:20],
                   "quarantined_lines": len(report["bad"])})
    write_text_atomic(ip, json.dumps(events[-50:], indent=1) + "\n")


def integrity_summary(log_path: str | Path) -> dict[str, Any]:
    """A small, read-only status for the UI: nothing is changed and no line content is included."""
    path = Path(log_path)
    report = verify_log(path)
    try:
        events = json.loads(integrity_path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        events = []
    return {"status": report["status"], "problems": report["problems"][:5], "legacy_lines": report["legacy_lines"],
            "quarantined_ever": sum(int(e.get("quarantined_lines") or 0) for e in events if isinstance(e, dict)),
            "events": len(events) if isinstance(events, list) else 0}


def _write_signed(path: Path, entries: list[dict[str, Any]]) -> None:
    key = _load_key(path, create=True)
    text, head = _serialise(key, entries)
    write_text_atomic(path, text)
    write_text_atomic(head_path(path), json.dumps(head) + "\n")


def read_history(log_path: str | Path) -> list[dict[str, Any]]:
    """The trusted entries. A corrupted, edited or unsigned-in-a-signed-log line is left out (never used for money
    figures) but not lost: it is logged here and quarantined by the next write; see :func:`integrity_summary`."""
    report = verify_log(log_path)
    if report["problems"]:
        LOG.warning("trends log %s failed its integrity check: %s", Path(log_path).name, "; ".join(report["problems"][:3]))
    return report["entries"]


def _parse_lines(path: Path, *, record: bool = True) -> tuple[list[dict[str, Any]], list[str]]:
    """Return (trusted entries, raw lines to quarantine). ``record`` appends any discrepancy to the integrity sidecar
    (a rewrite follows; a dry run passes False and changes nothing)."""
    report = verify_log(path)
    if report["problems"] and record:
        _record_event(path, report)
    return report["entries"], report["bad"]


def append_or_replace_entry(log_path: str | Path, entry: dict[str, Any]) -> list[dict[str, Any]]:
    """Add ``entry`` to the log, replacing any existing line with the same
    ``as_of_date`` (the run day). Unparseable lines are moved to a
    ``.rejected`` sidecar rather than dropped, and the rewrite is atomic.
    Returns the full history after the write."""
    as_of = entry.get("as_of_date")
    if not as_of:
        raise ValueError("entry must have an as_of_date")
    path = Path(log_path)
    existing, bad = _parse_lines(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if bad:
        # Quarantine first: if the main rewrite then fails, nothing is lost.
        with rejected_path(path).open("a", encoding="utf-8") as fh:
            fh.write("\n".join(bad) + "\n")
    history = [e for e in existing if e.get("as_of_date") != as_of]
    history.append(entry)
    history.sort(key=lambda e: str(e.get("as_of_date") or ""))
    _write_signed(path, history)
    return history


def prune_entries(log_path: str | Path, start: str, end: str | None = None, *, dry_run: bool = True) -> list[str]:
    """Drop entries whose ``as_of_date`` is in ``[start, end]`` (ISO dates, ``end`` defaults to
    ``start``). Returns the dates that match. With ``dry_run=False`` the original is first copied
    to ``<log>.bak`` and the log is rewritten atomically; unparseable lines go to the
    ``.rejected`` sidecar as in :func:`append_or_replace_entry`."""
    end = end or start
    path = Path(log_path)
    existing, bad = _parse_lines(path, record=not dry_run)
    hit = [str(e.get("as_of_date") or "") for e in existing if start <= str(e.get("as_of_date") or "") <= end]
    if dry_run or not hit:
        return hit
    shutil.copy2(path, path.with_name(path.name + ".bak"))
    if bad:
        with rejected_path(path).open("a", encoding="utf-8") as fh:
            fh.write("\n".join(bad) + "\n")
    keep = [e for e in existing if not start <= str(e.get("as_of_date") or "") <= end]
    _write_signed(path, keep)
    return hit


def realized_ytd_of(entry: dict[str, Any] | None) -> dict[str, Any] | None:
    """The year-to-date realized block of a log entry, or None ("no data") for an entry that has none: every entry
    written before the sales ledger, and any day the ledger could not be read. Never a block of zeros."""
    block = (entry or {}).get("realized_ytd")
    return block if isinstance(block, dict) else None
