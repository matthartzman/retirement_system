"""Storage access layer (file-elimination phase P1). Nothing imports it yet."""
from .app_store import APP_SCHEMA_VERSION, PLAN_KINDS, AppStore
from .db import connect, get_version, migrate, transaction
from .errors import IntegrityError, NotFoundError, SchemaVersionError, StoreError, ValidationError
from .ref_data import REF_SCHEMA_VERSION, RefData, RefDataError
from .ref_access import REFERENCE_DB_ENV, reference, set_reference_for_tests
from .plan_store import (
    DEFAULT_REVISION_RETENTION,
    PLAN_SCHEMA_VERSION,
    DatasetRepository,
    HoldingLot,
    HoldingsLotsRepository,
    HsaScheduleRepository,
    LiabilitiesRepository,
    PlanPaths,
    PlanStore,
    TargetAllocationRepository,
    plan_paths,
)
from .spending_repo import SpendingRepo, SpendingRepository

__all__ = [
    "APP_SCHEMA_VERSION",
    "AppStore",
    "DEFAULT_REVISION_RETENTION",
    "DatasetRepository",
    "HoldingLot",
    "HoldingsLotsRepository",
    "HsaScheduleRepository",
    "IntegrityError",
    "LiabilitiesRepository",
    "NotFoundError",
    "PLAN_KINDS",
    "PLAN_SCHEMA_VERSION",
    "PlanPaths",
    "PlanStore",
    "REFERENCE_DB_ENV",
    "REF_SCHEMA_VERSION",
    "RefData",
    "RefDataError",
    "SchemaVersionError",
    "SpendingRepo",
    "SpendingRepository",
    "StoreError",
    "TargetAllocationRepository",
    "ValidationError",
    "connect",
    "get_version",
    "migrate",
    "plan_paths",
    "reference",
    "set_reference_for_tests",
    "transaction",
]
