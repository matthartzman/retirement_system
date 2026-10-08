"""``build_results``: what a build computed, as rows of the plan file (WP7.2).

One row per build: the KPI summary, the Results Explorer model, the report package manifest, the
build snapshot and the pricing diagnostics, each a JSON document in its own column. They replace the JSON sidecars
(``plan_summary.json``, ``results_explorer_model.json``, ``report_package.json``,
``build_snapshot.json``, ``pricing_diagnostics.json``) the server used to re-read from the output folder. The workbook, HTML and
PDF stay files. A build writes its parts as it goes (``put`` merges into the build's row); the
latest rows are kept (``RETENTION``).
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from .errors import NotFoundError, ValidationError

SCHEMA_V7_DDL = """
CREATE TABLE build_results (
    build_id      TEXT NOT NULL PRIMARY KEY,
    plan_state    TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL,
    summary_json  TEXT NOT NULL DEFAULT '',
    explorer_json TEXT NOT NULL DEFAULT '',
    package_json  TEXT NOT NULL DEFAULT '',
    snapshot_json TEXT NOT NULL DEFAULT ''
);
"""

SCHEMA_V8_DDL = "ALTER TABLE build_results ADD COLUMN pricing_json TEXT NOT NULL DEFAULT '';"

#: part name -> column
PARTS: dict[str, str] = {
    "summary": "summary_json",
    "explorer": "explorer_json",
    "package": "package_json",
    "snapshot": "snapshot_json",
    "pricing": "pricing_json",
}
RETENTION = 5


def dumps(doc: Any) -> str:
    """The stored text of a part (also what its artifact hash is taken over)."""
    return json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class BuildResultsRepo:
    """The ``build_results`` table of a ``PlanStore`` (``store.build_results``)."""

    def __init__(self, store: Any) -> None:
        self._store = store

    @staticmethod
    def part_record(part: str, doc: Any) -> dict[str, Any]:
        """The artifact record of a part (what a file record is for a file): where it is
        stored, its size and the SHA-256 of its stored text."""
        text = dumps(doc)
        return {
            "file": f"build_results.{PARTS[part]}",
            "exists": bool(doc),
            "stored_in": "plan_file",
            "bytes": len(text.encode("utf-8")),
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        }

    def put(self, build_id: str, *, plan_state: str | None = None, **parts: Mapping[str, Any]) -> None:
        """Create or update the row of ``build_id``; ``summary=``/``explorer=``/``package=``/
        ``snapshot=``/``pricing=`` replace that part, parts not given are kept. Older rows beyond
        ``RETENTION`` are dropped."""
        if not isinstance(build_id, str) or not build_id:
            raise ValidationError("build_id must be non-empty text")
        unknown = set(parts) - set(PARTS)
        if unknown:
            raise ValidationError(f"unknown build result part(s): {sorted(unknown)}")
        cols = {PARTS[k]: dumps(v) for k, v in parts.items()}
        if plan_state is not None:
            cols["plan_state"] = plan_state
        with self._store._write() as con:
            con.execute("INSERT OR IGNORE INTO build_results (build_id, created_at) VALUES (?, ?)",
                        (build_id, self._store._clock()))
            cols["created_at"] = self._store._clock()  # the latest write is the latest build
            sets = ", ".join(f"{c} = ?" for c in cols)
            con.execute(f"UPDATE build_results SET {sets} WHERE build_id = ?", (*cols.values(), build_id))
            con.execute(
                "DELETE FROM build_results WHERE rowid NOT IN "
                "(SELECT rowid FROM build_results ORDER BY created_at DESC, rowid DESC LIMIT ?)", (RETENTION,))

    def latest_stamp(self) -> tuple[str, str] | None:
        """``(build_id, created_at)`` of the latest build: changes whenever a build writes."""
        with self._store._read() as con:
            r = con.execute("SELECT build_id, created_at FROM build_results ORDER BY created_at DESC, rowid DESC LIMIT 1").fetchone()
        return None if r is None else (r[0], r[1])

    def get(self, build_id: str | None = None) -> dict[str, Any]:
        """``{build_id, plan_state, created_at, summary, explorer, package, snapshot}`` of one
        build (the latest when ``build_id`` is None); a part not written is ``{}``."""
        with self._store._read() as con:
            if build_id is None:
                r = con.execute("SELECT * FROM build_results ORDER BY created_at DESC, rowid DESC LIMIT 1").fetchone()
            else:
                r = con.execute("SELECT * FROM build_results WHERE build_id = ?", (build_id,)).fetchone()
        if r is None:
            raise NotFoundError(f"no build results for {build_id or 'any build'}")
        out: dict[str, Any] = {k: r[k] for k in ("build_id", "plan_state", "created_at")}
        for part, col in PARTS.items():
            out[part] = _loads(r[col])
        return out

    def part_text(self, part: str, build_id: str | None = None) -> str:
        """The stored JSON text of one part ('' when not written)."""
        col = PARTS[part]
        with self._store._read() as con:
            if build_id is None:
                r = con.execute(f"SELECT {col} FROM build_results ORDER BY created_at DESC, rowid DESC LIMIT 1").fetchone()
            else:
                r = con.execute(f"SELECT {col} FROM build_results WHERE build_id = ?", (build_id,)).fetchone()
        return "" if r is None else r[0]

    def clear(self) -> int:
        with self._store._write() as con:
            return con.execute("DELETE FROM build_results").rowcount


def _loads(text: str) -> dict[str, Any]:
    if not text:
        return {}
    try:
        doc = json.loads(text)
    except ValueError:
        return {}
    return doc if isinstance(doc, dict) else {}
