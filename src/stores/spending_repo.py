"""The spending set of a plan file (WP6.3, P4.3): ``SpendingRepo``, reached as ``store.spending``.

The spending set was a family of flat workspace CSV files read and written by
``spending_tracker`` and its neighbours. WP6.3 moves it into ``plan.db`` tables, one dataset at
a time, behind this one repository so that every consumer has a single access shape:

==================  ===========================================  =========  ================
attribute           replaces                                     table      unit
==================  ===========================================  =========  ================
``taxonomy``        ``client_spending_taxonomy.csv``             v3         WP6.3a (done)
``aliases``         ``client_spending_aliases.csv``              v3         WP6.3a (done)
``budget``          ``client_spending_budget.csv``               v4         WP6.3b (done)
``budget_lines``    ``client_spending_budget_lines.csv``         v4         WP6.3b (done)
``tier_overrides``  ``client_spending_tier_overrides.csv``       v4         WP6.3b (done)
``rules``           ``client_spending_rules.csv``                v5         WP6.3c (done)
``category_map``    ``spending_category_map.csv``                v5         WP6.3c (done)
``group_budget``    ``spending_budget.csv``                      v5         WP6.3c (done)
==================  ===========================================  =========  ================

Recovery copies (``client_spending_budget.recovery_seed.csv`` and the pre-recovery budget copy)
are plan revisions with revision-scoped dataset copies (``PlanStore.snapshot_revision(...,
datasets=...)``), not tables and not files.

Every implemented dataset is a ``FlatDatasetRepository`` (``datasets.py``): text columns equal
to the CSV columns, stored exactly as written, row order = ``position`` (file order), columns the
file carried beyond the known ones kept per row in ``extra``. ``rows()`` / ``replace_all()`` /
``count()`` / ``extra_columns()``; the legacy CSV text form is in ``csv_exchange.flat_csv``.
A planned dataset would raise ``NotImplementedError`` naming the unit that adds it (none are
left); that unit adds its table in a new schema version, registers it in ``datasets._DATASETS``
and in ``SPENDING_DATASETS`` below, and replaces the stub with a property like ``taxonomy``.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping, Protocol, runtime_checkable

from .datasets import FlatDatasetRepository

# Plan revision sources of the spending recovery copies (never pruned: plan_store.PROTECTED_REVISION_SOURCES).
RECOVERY_SEED_SOURCE = "budget-recovery-seed"
PRE_RECOVERY_SOURCE = "pre-recovery"

# Implemented spending datasets: short name -> plan.db table.
SPENDING_DATASETS: dict[str, str] = {
    "taxonomy": "spending_taxonomy",
    "aliases": "spending_aliases",
    "budget": "spending_budget",
    "budget_lines": "spending_budget_lines",
    "tier_overrides": "spending_tier_overrides",
    "rules": "spending_rules",
    "category_map": "spending_category_map",
    "group_budget": "spending_group_budget",
}
# Planned spending datasets: short name -> the unit that implements it.
PLANNED_SPENDING_DATASETS: dict[str, str] = {}


@runtime_checkable
class SpendingRepository(Protocol):
    """The access shape of a plan's spending set (``store.spending``).

    Each attribute is a dataset repository (``rows()``, ``replace_all()``, ``count()``,
    ``extra_columns()``, ``columns``). ``budget``, ``budget_lines``, ``tier_overrides``,
    ``rules``, ``category_map`` and ``group_budget`` complete the set (WP6.3c).
    """

    @property
    def taxonomy(self) -> FlatDatasetRepository: ...

    @property
    def aliases(self) -> FlatDatasetRepository: ...

    @property
    def budget(self) -> FlatDatasetRepository: ...

    @property
    def budget_lines(self) -> FlatDatasetRepository: ...

    @property
    def tier_overrides(self) -> FlatDatasetRepository: ...

    @property
    def rules(self) -> FlatDatasetRepository: ...

    @property
    def category_map(self) -> FlatDatasetRepository: ...

    @property
    def group_budget(self) -> FlatDatasetRepository: ...

    def dataset(self, name: str) -> FlatDatasetRepository: ...


def _planned(name: str) -> NotImplementedError:
    return NotImplementedError(
        f"spending dataset {name!r} is not in the plan file yet ({PLANNED_SPENDING_DATASETS[name]} adds it)"
    )


class SpendingRepo:
    """The spending set of one open ``PlanStore`` (implements ``SpendingRepository``).

    Cheap to create; it holds no state beyond the store. Writes join the store's enclosing
    ``transaction()`` like every other store write.
    """

    def __init__(self, store: Any) -> None:
        self._store = store

    # ---------------------------------------------------------------- WP6.3a (implemented)
    @property
    def taxonomy(self) -> FlatDatasetRepository:
        """``spending_taxonomy``: tracking_type, group, category_id, label, origin, status, notes."""
        return FlatDatasetRepository(self._store, SPENDING_DATASETS["taxonomy"])

    @property
    def aliases(self) -> FlatDatasetRepository:
        """``spending_aliases``: match_value, match_field, exact, priority, category_id, source."""
        return FlatDatasetRepository(self._store, SPENDING_DATASETS["aliases"])

    # ---------------------------------------------------------------- WP6.3b (implemented)
    @property
    def budget(self) -> FlatDatasetRepository:
        """``spending_budget``: kind, key, label, annual_budget, start_year, end_year,
        one_time_year, notes, _mode, line_section, line_mode, no_annualize."""
        return FlatDatasetRepository(self._store, SPENDING_DATASETS["budget"])

    @property
    def budget_lines(self) -> FlatDatasetRepository:
        """``spending_budget_lines``: section, line_id, label, category_id, start_year, end_year,
        one_time_year, amount_per_year, mode, notes."""
        return FlatDatasetRepository(self._store, SPENDING_DATASETS["budget_lines"])

    @property
    def tier_overrides(self) -> FlatDatasetRepository:
        """``spending_tier_overrides``: category_id, tier, notes."""
        return FlatDatasetRepository(self._store, SPENDING_DATASETS["tier_overrides"])

    # ---------------------------------------------------------------- WP6.3c (implemented)
    @property
    def rules(self) -> FlatDatasetRepository:
        """``spending_rules``: keyword, category_id, match_field, exact, priority."""
        return FlatDatasetRepository(self._store, SPENDING_DATASETS["rules"])

    @property
    def category_map(self) -> FlatDatasetRepository:
        """``spending_category_map``: super_group, group, category, tracking."""
        return FlatDatasetRepository(self._store, SPENDING_DATASETS["category_map"])

    @property
    def group_budget(self) -> FlatDatasetRepository:
        """``spending_group_budget``: group, budget_pct, budget_override, notes."""
        return FlatDatasetRepository(self._store, SPENDING_DATASETS["group_budget"])

    # ------------------------------------------------------------ recovery copies (WP6.3c)
    def recovery_seed(self) -> list[dict[str, str]]:
        """The recovery seed: the ``spending_budget`` rows of the newest ``budget-recovery-seed``
        revision (``[]`` when there is none)."""
        head = self._store.latest_revision(RECOVERY_SEED_SOURCE)
        return [] if head is None else self._store.revision_dataset_rows(head["id"], SPENDING_DATASETS["budget"])

    def set_recovery_seed(self, rows: Iterable[Mapping[str, Any]]) -> int:
        """Make ``rows`` the recovery seed (a ``budget-recovery-seed`` revision; older seeds are
        discarded). Returns the rows kept; empty ``rows`` just clears the seed."""
        rows = list(rows)
        with self._store.transaction():
            self._store.discard_revisions(RECOVERY_SEED_SOURCE)
            if rows:
                self._store.snapshot_revision(
                    RECOVERY_SEED_SOURCE, "known-good spending budget", datasets={SPENDING_DATASETS["budget"]: rows}
                )
        return len(rows)

    def keep_pre_recovery_copy(self, rows: Iterable[Mapping[str, Any]]) -> bool:
        """Keep ``rows`` (the budget before a recovery merge) as the one-time ``pre-recovery``
        revision. False (nothing written) when there is one already or ``rows`` is empty."""
        rows = list(rows)
        if not rows or self._store.latest_revision(PRE_RECOVERY_SOURCE) is not None:
            return False
        self._store.snapshot_revision(
            PRE_RECOVERY_SOURCE, "spending budget before recovery", datasets={SPENDING_DATASETS["budget"]: rows}
        )
        return True

    def restore_pre_recovery_copy(self) -> int:
        """Put the live budget back to the ``pre-recovery`` copy; returns the rows restored
        (0 when there is no copy)."""
        head = self._store.latest_revision(PRE_RECOVERY_SOURCE)
        if head is None:
            return 0
        return self._store.restore_dataset_from_revision(head["id"], SPENDING_DATASETS["budget"])

    # ------------------------------------------------------------------------- by name
    def dataset(self, name: str) -> FlatDatasetRepository:
        """The dataset with short name ``name`` (``"taxonomy"``, ``"aliases"`` ...)."""
        if name in SPENDING_DATASETS or name in PLANNED_SPENDING_DATASETS:
            return getattr(self, name)
        raise KeyError(f"unknown spending dataset {name!r}")
