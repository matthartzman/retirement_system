"""Typed engine-configuration contract and runtime normalization.

This module defines the required engine fields and validates normalized
configuration dictionaries before they reach the projection engine.

``PlanConfig`` preserves the dict interface used by the model while making
loader errors explicit, recording the source loader, and deriving account-ID
indexes from the account registry.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, TypedDict


class MemberConfig(TypedDict, total=False):
    name: str
    role: str
    dob_yr: int
    retire_yr: int
    mortality_age: float
    death_yr: int


class AccountConfig(TypedDict, total=False):
    id: str
    owner_idx: int
    owner_name: str
    acct_type: str
    tax: str
    rmd: bool
    label: str
    balance: float


class EngineConfigDict(TypedDict, total=False):
    plan_start: int
    plan_end: int
    filing_status: str
    survivor_filing: str
    members: List[MemberConfig]
    balances: Dict[str, float]
    account_registry: List[AccountConfig]
    all_acct_ids: List[str]
    pre_tax_ids: List[str]
    roth_ids: List[str]
    taxable_ids: List[str]
    hsa_ids: List[str]
    cash_ids: List[str]
    invest_ids: List[str]
    ret: float
    inf: float
    brk_inf: float
    mc_sigma: float
    roth_policy: str



def _freeze_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({k: _freeze_value(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_value(v) for v in value)
    if isinstance(value, tuple):
        return tuple(_freeze_value(v) for v in value)
    if isinstance(value, set):
        return frozenset(_freeze_value(v) for v in value)
    return value


def _thaw_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {k: _thaw_value(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return [_thaw_value(v) for v in value]
    if isinstance(value, frozenset):
        return [_thaw_value(v) for v in value]
    return value

REQUIRED_KEYS = (
    'plan_start', 'plan_end', 'filing_status', 'survivor_filing',
    'members', 'balances', 'account_registry', 'all_acct_ids',
    'pre_tax_ids', 'roth_ids', 'taxable_ids', 'hsa_ids', 'cash_ids',
    'ret', 'inf', 'brk_inf', 'mc_sigma',
)

@dataclass(frozen=True)
class PlanConfig:
    values: Mapping[str, Any] = field(default_factory=dict)
    source: str = 'unknown'
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, 'values', _freeze_value(dict(self.values or {})))
        object.__setattr__(self, 'warnings', tuple(self.warnings or ()))

    def as_engine_dict(self) -> Dict[str, Any]:
        # The public engine receives a mutable execution copy; the PlanConfig
        # boundary itself remains immutable.
        out = _thaw_value(self.values)
        existing = list(out.get('config_contract_warnings', []) or [])
        for warning in self.warnings:
            if warning not in existing:
                existing.append(warning)
        out['config_contract_source'] = self.source
        out['config_contract_version'] = 'v1'
        out['config_contract_warnings'] = existing
        out['config_immutable_boundary'] = True
        return out


def _as_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def _ids_from_registry(registry: Iterable[Mapping[str, Any]], tax: str | None = None) -> List[str]:
    ids: List[str] = []
    for acct in registry or []:
        if tax is None or acct.get('tax') == tax:
            aid = acct.get('id')
            if aid:
                ids.append(str(aid))
    return ids


def normalize_engine_config(config: Mapping[str, Any] | PlanConfig, source: str = 'unknown') -> PlanConfig:
    """Return a validated ``PlanConfig`` from either a dict or PlanConfig.

    The function is intentionally conservative: it fills aliases and obvious
    registry-derived IDs, but it does not invent balances or household data.
    Missing critical values raise ``ValueError`` so API callers get an error
    instead of a clean but wrong projection.
    """
    if isinstance(config, PlanConfig):
        return config
    c: Dict[str, Any] = dict(config or {})
    warnings: list[str] = []

    registry = list(c.get('account_registry', []) or [])
    if registry:
        c.setdefault('all_acct_ids', _ids_from_registry(registry))
        c.setdefault('pre_tax_ids', _ids_from_registry(registry, 'pre_tax'))
        c.setdefault('roth_ids', _ids_from_registry(registry, 'roth'))
        c.setdefault('hsa_ids', _ids_from_registry(registry, 'hsa'))
        c.setdefault('cash_ids', _ids_from_registry(registry, 'cash'))
        c.setdefault('taxable_ids', [a.get('id') for a in registry if a.get('id') and a.get('tax') in ('taxable', 'cash')])
        c.setdefault('invest_ids', [a.get('id') for a in registry if a.get('id') and a.get('tax') != 'cash'])

    # Make sure every registry account has a balance entry and vice versa.
    balances = dict(c.get('balances', {}) or {})
    for aid in c.get('all_acct_ids', []) or []:
        balances.setdefault(aid, 0.0)
    c['balances'] = {str(k): _as_float(v) for k, v in balances.items()}

    c.setdefault('tax_withdrawal_fixed_point_iterations', 3)
    c.setdefault('enforce_release_gate', True)
    c.setdefault('tax_table_currency_max_lag_years', 1)

    missing = [k for k in REQUIRED_KEYS if k not in c]
    if missing:
        raise ValueError(f'Engine config missing required keys: {", ".join(missing)}')
    if int(c['plan_end']) < int(c['plan_start']):
        raise ValueError('Engine config has plan_end before plan_start')
    if not c.get('members'):
        raise ValueError('Engine config has no household members')
    if not c.get('account_registry'):
        raise ValueError('Engine config has no account registry')
    if sum(_as_float(v) for v in c.get('balances', {}).values()) <= 0:
        raise ValueError('Engine config has zero starting account balances')

    # Registry IDs should be a subset of balances. Warn, but do not fail, for
    # extra balances because imported holdings can contain inactive accounts.
    for aid in c.get('all_acct_ids', []) or []:
        if aid not in c['balances']:
            raise ValueError(f'Engine config registry account {aid!r} has no balance')
    extra = sorted(set(c['balances']) - set(c.get('all_acct_ids', [])))
    if extra:
        warnings.append('Balances include non-registry accounts: ' + ', '.join(extra[:8]))

    return PlanConfig(c, source=source, warnings=tuple(warnings))


def ensure_engine_config(config: Mapping[str, Any] | PlanConfig, source: str = 'runtime') -> Dict[str, Any]:
    """Validate and return an engine-ready dict."""
    return normalize_engine_config(config, source=source).as_engine_dict()
