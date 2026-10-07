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
``rules``           ``client_spending_rules.csv``                planned    WP6.3c
``category_map``    ``spending_category_map.csv``                planned    WP6.3c
==================  ===========================================  =========  ================

Recovery copies (``client_spending_budget.recovery_seed.csv``) become plan revisions in WP6.3c,
not a table.

Every implemented dataset is a ``FlatDatasetRepository`` (``datasets.py``): text columns equal
to the CSV columns, stored exactly as written, row order = ``position`` (file order), columns the
file carried beyond the known ones kept per row in ``extra``. ``rows()`` / ``replace_all()`` /
``count()`` / ``extra_columns()``; the legacy CSV text form is in ``csv_exchange.flat_csv``.
The planned datasets raise ``NotImplementedError`` naming the unit that adds them; that unit adds
its table in a new schema version, registers it in ``datasets._DATASETS`` and in
``SPENDING_DATASETS`` below, and replaces the stub with a property like ``taxonomy``.
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from .datasets import FlatDatasetRepository

# Implemented spending datasets: short name -> plan.db table.
SPENDING_DATASETS: dict[str, str] = {
    "taxonomy": "spending_taxonomy",
    "aliases": "spending_aliases",
    "budget": "spending_budget",
    "budget_lines": "spending_budget_lines",
    "tier_overrides": "spending_tier_overrides",
}
# Planned spending datasets: short name -> the unit that implements it.
PLANNED_SPENDING_DATASETS: dict[str, str] = {
    "rules": "WP6.3c",
    "category_map": "WP6.3c",
}


@runtime_checkable
class SpendingRepository(Protocol):
    """The access shape of a plan's spending set (``store.spending``).

    Each attribute is a dataset repository (``rows()``, ``replace_all()``, ``count()``,
    ``extra_columns()``, ``columns``). ``budget``, ``budget_lines``, ``tier_overrides``,
    ``rules`` and ``category_map`` are part of the interface now and implemented by WP6.3b/c.
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

    # ------------------------------------------------------------ WP6.3c (planned stubs)
    @property
    def rules(self) -> FlatDatasetRepository:
        """``spending_rules`` (``client_spending_rules.csv``). Stub until WP6.3c."""
        raise _planned("rules")

    @property
    def category_map(self) -> FlatDatasetRepository:
        """``spending_category_map`` (``spending_category_map.csv``). Stub until WP6.3c."""
        raise _planned("category_map")

    # ------------------------------------------------------------------------- by name
    def dataset(self, name: str) -> FlatDatasetRepository:
        """The dataset with short name ``name`` (``"taxonomy"``, ``"aliases"`` ...)."""
        if name in SPENDING_DATASETS or name in PLANNED_SPENDING_DATASETS:
            return getattr(self, name)
        raise KeyError(f"unknown spending dataset {name!r}")
