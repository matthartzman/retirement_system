from __future__ import annotations

"""Feature-owned service logic for YTD transactions/account setup.

This module intentionally has no dependency on the HTTP runtime or route
decorators.  The route layer injects path, SQLite, and audit callbacks so YTD
behavior can be tested and maintained independently from HTTP
route modules.
"""

import csv
import hashlib
import io
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable


YTD_PERSISTED_FILES = ("ytd_transactions.csv", "ytd_account_setup.csv", "ytd_import_history.csv")


def _load_ytd_module():
    try:
        from .. import ytd_tracking as ytd
    except Exception:  # pragma: no cover - direct execution fallback
        from src import ytd_tracking as ytd
    return ytd


@dataclass(frozen=True)
class YtdServiceContext:
    base_dir: Path
    plan_data_path: Callable[..., Path]
    path_roots_from_config: Callable[[], list[Path]]
    server_path_allowed: Callable[[Path], tuple[bool, str]]
    workspace_id: Callable[[], str]
    client_id: Callable[[], str]
    sqlite_db: Callable[[], Path]
    current_user_id: Callable[[], str]
    get_client_file: Callable[..., str | None]
    set_client_file: Callable[..., None]
    audit: Callable[[str, dict[str, Any]], None]


class YtdService:
    def __init__(self, ctx: YtdServiceContext):
        self.ctx = ctx
        self.ytd = _load_ytd_module()

    def input_root(self) -> Path:
        return self.ctx.plan_data_path("ytd_transactions.csv", prefer_existing=False).parent

    def _plan_path(self, name: str, *, prefer_existing: bool = True) -> Path:
        return self.ctx.plan_data_path(name, prefer_existing=prefer_existing)

    def _csv_rows_from_text(self, text: str, columns: list[str]) -> list[dict[str, str]]:
        reader = csv.DictReader(io.StringIO(text or ""))
        if not reader.fieldnames:
            return []
        rows: list[dict[str, str]] = []
        for raw in reader:
            rows.append({col: str(raw.get(col, "") or "") for col in columns})
        return rows

    def _money_abs(self, value: Any) -> float:
        try:
            return abs(float(self.ytd.parse_money(value)))
        except Exception:
            try:
                return abs(float(str(value or "").replace("$", "").replace(",", "").strip() or 0))
            except Exception:
                return 0.0

    def account_setup_row_score(self, row: dict[str, Any]) -> int:
        score = 0
        account = str(row.get("Account", "") or "").strip()
        if account:
            score += 5
        role = str(row.get("Role", "") or "").strip()
        if role and role != "Cash / spending":
            score += 10
        if str(row.get("Mapped Investment Account", "") or "").strip():
            score += 120
        if self._money_abs(row.get("Prior Year End Balance")) >= 1:
            score += 150
        if self._money_abs(row.get("Current Value")) >= 1 or self._money_abs(row.get("Current Balance")) >= 1:
            score += 90
        notes = str(row.get("Notes", "") or "").strip().lower()
        if notes and "created from transaction upload" not in notes:
            score += 3
        return score

    def account_setup_text_score(self, text: str) -> dict[str, int]:
        try:
            rows = [
                self.ytd.normalize_account_setup(r)
                for r in self._csv_rows_from_text(text, list(self.ytd.ACCOUNT_SETUP_COLUMNS))
            ]
        except Exception:
            rows = []
        row_scores = [self.account_setup_row_score(r) for r in rows]
        return {
            "rows": len(rows),
            "score": int(sum(row_scores)),
            "mapped_rows": sum(1 for r in rows if str(r.get("Mapped Investment Account", "") or "").strip()),
            "prior_balance_rows": sum(1 for r in rows if self._money_abs(r.get("Prior Year End Balance")) >= 1),
            "current_value_rows": sum(
                1
                for r in rows
                if self._money_abs(r.get("Current Value")) >= 1 or self._money_abs(r.get("Current Balance")) >= 1
            ),
        }

    def mirror_file_to_sqlite(self, name: str) -> None:
        if name not in YTD_PERSISTED_FILES:
            return
        path = self._plan_path(name, prefer_existing=True)
        if not path.exists():
            return
        try:
            self.ctx.set_client_file(
                name,
                path.read_text(encoding="utf-8-sig"),
                self.ctx.workspace_id(),
                self.ctx.client_id(),
                self.ctx.current_user_id(),
                self.ctx.sqlite_db(),
            )
        except Exception as exc:
            self.ctx.audit("ytd_sqlite_mirror_warning", {"file": name, "error": str(exc)})

    def mirror_files_to_sqlite(self, names: Iterable[str] = YTD_PERSISTED_FILES) -> None:
        for name in names:
            self.mirror_file_to_sqlite(str(name))

    def rehydrate_files_from_sqlite(self) -> dict[str, list[str]]:
        recovered: list[str] = []
        for name in YTD_PERSISTED_FILES:
            path = self._plan_path(name, prefer_existing=False)
            text = ""
            if path.exists():
                try:
                    text = path.read_text(encoding="utf-8-sig")
                except Exception:
                    text = ""
            if text.strip():
                continue
            try:
                db_text = self.ctx.get_client_file(name, self.ctx.workspace_id(), self.ctx.client_id(), self.ctx.sqlite_db())
            except Exception:
                db_text = None
            if not db_text or not str(db_text).strip():
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(str(db_text), encoding="utf-8")
            recovered.append(name)
        return {"files_rehydrated_from_sqlite": recovered}

    def account_setup_recovery_candidates(self, extra_path: str | None = None) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        seen: set[str] = set()

        def add_text(source: str, text: str | None) -> None:
            if not text or not str(text).strip():
                return
            key = hashlib.sha256(str(text).encode("utf-8")).hexdigest()
            if key in seen:
                return
            seen.add(key)
            metrics = self.account_setup_text_score(str(text))
            if metrics["rows"] <= 0:
                return
            candidates.append({"source": source, "text": str(text), **metrics})

        def add_path(path: Path) -> None:
            try:
                p = path.expanduser().resolve()
            except Exception:
                return
            if not p.exists() or not p.is_file():
                return
            try:
                add_text(str(p), p.read_text(encoding="utf-8-sig"))
            except Exception:
                return

        add_path(self._plan_path("ytd_account_setup.csv", prefer_existing=True))
        try:
            add_text(
                "sqlite://client_files/ytd_account_setup.csv",
                self.ctx.get_client_file("ytd_account_setup.csv", self.ctx.workspace_id(), self.ctx.client_id(), self.ctx.sqlite_db()),
            )
        except Exception:
            pass

        if extra_path:
            p = Path(str(extra_path)).expanduser()
            if p.is_dir():
                add_path(p / "ytd_account_setup.csv")
                add_path(p / "input" / "ytd_account_setup.csv")
            else:
                add_path(p)

        for root in self.ctx.path_roots_from_config():
            add_path(root / "ytd_account_setup.csv")
            add_path(root / "input" / "ytd_account_setup.csv")

        search_roots = []
        for raw in [self.ctx.base_dir.parent, self.ctx.base_dir.parent.parent]:
            try:
                r = raw.resolve()
            except Exception:
                continue
            if r not in search_roots:
                search_roots.append(r)
        for root in search_roots:
            try:
                for path in list(root.glob("*/input/ytd_account_setup.csv"))[:200]:
                    add_path(path)
            except Exception:
                continue
        return sorted(candidates, key=lambda x: (x.get("score", 0), x.get("rows", 0)), reverse=True)

    def merge_account_setup_candidates(self, texts: list[str]) -> list[dict[str, str]]:
        best_by_account: dict[str, dict[str, str]] = {}
        for text in texts:
            for raw in self._csv_rows_from_text(text or "", list(self.ytd.ACCOUNT_SETUP_COLUMNS)):
                row = self.ytd.normalize_account_setup(raw)
                account = str(row.get("Account", "") or "").strip()
                if not account:
                    continue
                key = re.sub(r"\s+", " ", account).strip().lower()
                prev = best_by_account.get(key)
                if prev is None or self.account_setup_row_score(row) > self.account_setup_row_score(prev):
                    best_by_account[key] = row
        return [best_by_account[k] for k in sorted(best_by_account)]

    def recover_account_setup(self, *, force: bool = False, extra_path: str | None = None) -> dict[str, Any]:
        current_path = self._plan_path("ytd_account_setup.csv", prefer_existing=True)
        current_text = current_path.read_text(encoding="utf-8-sig") if current_path.exists() else ""
        current_metrics = self.account_setup_text_score(current_text)
        candidates = self.account_setup_recovery_candidates(extra_path=extra_path)
        best = candidates[0] if candidates else None
        if not best:
            return {
                "success": False,
                "recovered": False,
                "reason": "No ytd_account_setup.csv recovery candidates found.",
                "current": current_metrics,
                "candidates": [],
            }
        should_apply = force or best.get("score", 0) > current_metrics.get("score", 0)
        if not should_apply:
            return {
                "success": True,
                "recovered": False,
                "reason": "Current account setup is at least as complete as recovered candidates.",
                "current": current_metrics,
                "best_candidate": {k: best[k] for k in best if k != "text"},
                "candidates": [{k: c[k] for k in c if k != "text"} for c in candidates[:10]],
            }
        merged = self.merge_account_setup_candidates([current_text, best.get("text", "")])
        self.ytd.write_account_setup(self.input_root(), merged)
        self.mirror_file_to_sqlite("ytd_account_setup.csv")
        new_text = current_path.read_text(encoding="utf-8-sig") if current_path.exists() else ""
        new_metrics = self.account_setup_text_score(new_text)
        result = {
            "success": True,
            "recovered": True,
            "source": best.get("source"),
            "before": current_metrics,
            "after": new_metrics,
            "best_candidate": {k: best[k] for k in best if k != "text"},
            "candidates": [{k: c[k] for k in c if k != "text"} for c in candidates[:10]],
        }
        self.ctx.audit("ytd_account_setup_recovered", result)
        return result

    def status_payload(self) -> dict[str, Any]:
        recovery = self.rehydrate_files_from_sqlite()
        auto = self.recover_account_setup(force=False)
        payload = self.ytd.status_payload(self.input_root())
        if recovery.get("files_rehydrated_from_sqlite") or auto.get("recovered"):
            payload["recovery"] = {"sqlite": recovery, "account_setup": auto}
        return payload

    def account_setup_recover_payload(self, body: dict[str, Any]) -> tuple[dict[str, Any], int]:
        extra_path = str(body.get("path") or "").strip() or None
        if extra_path:
            p = Path(extra_path).expanduser()
            check = p if p.is_dir() else p.parent
            if not check.is_absolute():
                check = (self.ctx.base_dir / check).resolve()
            allowed, reason = self.ctx.server_path_allowed(check)
            if not allowed:
                return {"success": False, "error": reason}, 403
        result = self.recover_account_setup(force=bool(body.get("force", True)), extra_path=extra_path)
        return result, 200 if result.get("success") else 404

    def transactions_template_csv(self) -> str:
        return self.ytd.csv_template()

    def preview_transactions_import(self, body: dict[str, Any]) -> tuple[dict[str, Any], int]:
        try:
            from ..import_preview import preview_ytd_transactions_import
        except Exception:  # pragma: no cover - direct execution fallback
            from src.import_preview import preview_ytd_transactions_import
        text = body.get("csv_text") or body.get("csv") or body.get("content") or ""
        mode = body.get("mode") or "replace"
        payload = preview_ytd_transactions_import(self.input_root(), str(text), str(mode))
        return payload, 200 if payload.get("success") else 422

    def upload_transactions(self, body: dict[str, Any]) -> tuple[dict[str, Any], int]:
        text = body.get("csv_text") or body.get("text") or ""
        mode = body.get("mode") or "replace"
        result = self.ytd.import_transactions(self.input_root(), str(text), str(mode))
        if result.get("success"):
            self.mirror_files_to_sqlite()
        self.ctx.audit(
            "ytd_transactions_uploaded",
            {"mode": mode, "success": bool(result.get("success")), "added": result.get("added"), "total": result.get("total")},
        )
        return result, 200 if result.get("success") else 422

    def add_transaction(self, body: dict[str, Any]) -> dict[str, Any]:
        rows = self.ytd.read_transactions(self.input_root())
        rows.append(self.ytd.normalize_transaction(body.get("row") or body))
        self.ytd.write_transactions(self.input_root(), rows)
        self.ytd.ensure_account_setup_for_transactions(self.input_root())
        self.mirror_files_to_sqlite(("ytd_transactions.csv", "ytd_account_setup.csv"))
        self.ctx.audit("ytd_transaction_added", {"total": len(rows)})
        return {"success": True, "total": len(rows), "summary": self.ytd.ytd_summary(self.input_root())}

    def update_transaction(self, index: int, body: dict[str, Any]) -> tuple[dict[str, Any], int]:
        rows = self.ytd.read_transactions(self.input_root())
        if index < 0 or index >= len(rows):
            return {"success": False, "error": "Transaction index not found"}, 404
        rows[index] = self.ytd.normalize_transaction(body.get("row") or body)
        self.ytd.write_transactions(self.input_root(), rows)
        self.ytd.ensure_account_setup_for_transactions(self.input_root())
        self.mirror_files_to_sqlite(("ytd_transactions.csv", "ytd_account_setup.csv"))
        self.ctx.audit("ytd_transaction_updated", {"index": index})
        return {"success": True, "index": index, "summary": self.ytd.ytd_summary(self.input_root())}, 200

    def delete_transaction(self, index: int) -> tuple[dict[str, Any], int]:
        rows = self.ytd.read_transactions(self.input_root())
        if index < 0 or index >= len(rows):
            return {"success": False, "error": "Transaction index not found"}, 404
        rows.pop(index)
        self.ytd.write_transactions(self.input_root(), rows)
        self.ytd.ensure_account_setup_for_transactions(self.input_root())
        self.mirror_files_to_sqlite(("ytd_transactions.csv", "ytd_account_setup.csv"))
        self.ctx.audit("ytd_transaction_deleted", {"index": index, "total": len(rows)})
        return {"success": True, "total": len(rows), "summary": self.ytd.ytd_summary(self.input_root())}, 200

    def delete_all_transactions(self) -> dict[str, Any]:
        self.ytd.write_transactions(self.input_root(), [])
        self.mirror_file_to_sqlite("ytd_transactions.csv")
        self.ctx.audit("ytd_transactions_deleted_all", {})
        return {"success": True, "total": 0, "summary": self.ytd.ytd_summary(self.input_root())}

    def save_account_setup(self, body: dict[str, Any]) -> dict[str, Any]:
        accounts = body.get("accounts") if isinstance(body.get("accounts"), list) else []
        self.ytd.write_account_setup(self.input_root(), accounts)
        self.mirror_file_to_sqlite("ytd_account_setup.csv")
        self.ctx.audit("ytd_account_setup_saved", {"accounts": len(accounts)})
        return {"success": True, "accounts": self.ytd.read_account_setup(self.input_root()), "summary": self.ytd.ytd_summary(self.input_root())}

    def bulk_save_transactions(self, body: dict[str, Any]) -> dict[str, Any]:
        rows = body.get("transactions") if isinstance(body.get("transactions"), list) else []
        cleaned = [self.ytd.normalize_transaction(r) for r in rows]
        self.ytd.write_transactions(self.input_root(), cleaned)
        self.ytd.ensure_account_setup_for_transactions(self.input_root())
        self.mirror_files_to_sqlite(("ytd_transactions.csv", "ytd_account_setup.csv"))
        self.ctx.audit("ytd_transactions_bulk_saved", {"total": len(cleaned)})
        return {"success": True, "total": len(cleaned), "summary": self.ytd.ytd_summary(self.input_root())}
