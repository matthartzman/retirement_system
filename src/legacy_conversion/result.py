"""``ConversionResult``: what ``convert_workspace`` returns and the first-launch UI (WP10.4)
renders (WP10.3). Privacy-safe by construction: statuses, counts, file and key NAMES, never a
plan value or an exception message.

* ``status``: ``not_needed`` | ``done`` (converted, verified, live and active; done marker set) |
  ``blocked`` (nothing became live: the live plan and every original are as they were; see
  ``blocked_reason``) | ``failed`` (the verified plan replaced the live one, ``plan_replaced``,
  but an install step failed: not active, no done marker; the next run finishes it) |
  ``dry_run`` (nothing written; ``verified`` / ``blocked_reason`` say what a real run would do).
* ``blocked_reason`` codes: ``verification_differences`` (plan rows, engine, datasets),
  ``tier_mapping_changes_results`` (the tier safeguard), ``verification_error`` (the engine
  raised, so the numbers could not be compared), ``step_failed``, ``backup_failed``,
  ``sources_modified``, ``plan_changed_during_conversion``, ``swap_failed``, ``busy``,
  ``internal_error``. The first three can be accepted by the user
  (``extra["accept_differences"]``, ``can_accept``); for the tier safeguard the user can also keep
  the plan's switches (``extra["tier_mapping"] = "keep"``).
* ``differing_keys``: per check, the differing key names (capped).
* :meth:`summary` is what is kept in app.db (``LAST_RESULT_KEY``).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .verify import Check

LAST_RESULT_KEY = "legacy_conversion.last_result"
ACCEPTABLE = frozenset({"verification_differences", "tier_mapping_changes_results", "verification_error"})
SUMMARY_NAME_LIMIT = 20


@dataclass
class ConversionResult:
    needed: bool
    reason: str = ""
    mode: str = "normal"
    dry_run: bool = False
    status: str = "not_needed"
    verified: bool = False
    blocked_reason: str = ""
    failed_step: str = ""
    error_type: str = ""
    accepted_differences: bool = False
    checks: list[Check] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    backup: dict[str, Any] | None = None
    plan_backup: str | None = None  # name of the live plan's pre-conversion copy
    plan_replaced: bool = False  # the verified copy replaced the live plan in this run
    steps: list[dict[str, Any]] = field(default_factory=list)
    removable: dict[str, Any] = field(default_factory=dict)
    sources_unchanged: bool = True
    started_at: str = ""
    finished_at: str = ""

    @property
    def ok(self) -> bool:
        """True when nothing is left to do or decide: not needed, done, or a clean dry run."""
        return self.status in ("not_needed", "done") or (self.status == "dry_run" and not self.blocked_reason)

    @property
    def blocked(self) -> bool:
        return self.status == "blocked"

    @property
    def can_accept(self) -> bool:
        """The user may convert anyway (after seeing ``differing_keys``)."""
        return self.blocked_reason in ACCEPTABLE

    @property
    def differing_keys(self) -> dict[str, list[str]]:
        return {c.name: list(c.names) for c in self.checks if c.status in ("diff",) and c.names}

    def check(self, name: str) -> Check | None:
        return next((c for c in self.checks if c.name == name), None)

    def step(self, step_id: str) -> dict[str, Any] | None:
        return next((s for s in self.steps if s.get("step") == step_id), None)

    def as_dict(self) -> dict[str, Any]:
        return {"needed": self.needed, "reason": self.reason, "mode": self.mode, "dry_run": self.dry_run,
                "status": self.status, "ok": self.ok, "verified": self.verified,
                "blocked_reason": self.blocked_reason, "can_accept": self.can_accept,
                "failed_step": self.failed_step, "error_type": self.error_type,
                "accepted_differences": self.accepted_differences,
                "checks": [c.as_dict() for c in self.checks], "differing_keys": self.differing_keys,
                "warnings": list(self.warnings), "backup": self.backup, "plan_backup": self.plan_backup,
                "plan_replaced": self.plan_replaced, "steps": list(self.steps), "removable": dict(self.removable),
                "sources_unchanged": self.sources_unchanged, "started_at": self.started_at,
                "finished_at": self.finished_at}

    def summary(self) -> dict[str, Any]:
        """The compact record kept in app.db: no step details, names capped."""
        steps = [{"step": s.get("step"), "status": s.get("status"),
                  **({"error_type": s["error_type"]} if s.get("error_type") else {})} for s in self.steps]
        checks = [{"name": c.name, "status": c.status, "blocking": c.blocking, "differing": c.differing,
                   "names": list(c.names[:SUMMARY_NAME_LIMIT])} for c in self.checks]
        return {"status": self.status, "verified": self.verified, "blocked_reason": self.blocked_reason,
                "failed_step": self.failed_step, "error_type": self.error_type, "mode": self.mode,
                "reason": self.reason, "accepted_differences": self.accepted_differences, "checks": checks,
                "warnings": list(self.warnings), "backup": self.backup, "plan_backup": self.plan_backup,
                "plan_replaced": self.plan_replaced, "steps": steps, "removable": dict(self.removable),
                "started_at": self.started_at, "finished_at": self.finished_at}
