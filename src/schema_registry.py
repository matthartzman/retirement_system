from __future__ import annotations
"""Schema-driven validation/help registry for Plan Data rows."""
import math, re
from .plan_data_registry import client_data_csv_files
from . import plan_dates as _plan_dates
PLAN_FILES = [*client_data_csv_files(), 'target_allocation.csv']

def schema_key(row: dict) -> tuple[str,str,str]:
    return ((row.get('section') or '').strip(), (row.get('subsection') or '').strip(), (row.get('label') or '').strip())

def load_schema() -> dict[tuple[str,str,str], dict]:
    """The field catalog from the shipped reference.db (fresh dicts on every call)."""
    from .stores.ref_getters.schema_fields import schema_fields
    return schema_fields()

def validate_value(value: str, spec: dict) -> list[str]:
    errors=[]; typ=(spec.get('type') or '').lower(); val=str(value or '').strip()
    if str(spec.get('required','')).upper()=='TRUE' and not val:
        errors.append('required value missing')
    if not val: return errors
    if typ in {'percent','pct'} and not val.endswith('%'):
        errors.append('expected percentage format ending with %')
    if typ in {'integer','year'}:
        try: int(float(val.replace(',','').replace('$','').strip()))
        except Exception: errors.append('expected integer/year')
    if typ in {'number','currency'}:
        try: float(val.replace('$','').replace(',','').replace('%',''))
        except Exception: errors.append('expected numeric/currency value')
    # WI-401: NaN/inf parse as floats and every min/max comparison against
    # NaN is False, so a non-finite value used to pass every numeric check.
    if typ in {'integer','year','number','currency','percent','pct'}:
        _x = _numeric_value(val, typ)
        if _x is not None and not math.isfinite(_x):
            errors.append('expected a finite number')
    # WI-401: date fields previously got only the required check, so an
    # ambiguous '8/3/62' or garbage text passed validation.
    if typ == 'date':
        _date_err = _plan_dates.date_format_error(val)
        if _date_err:
            errors.append(_date_err)
    if typ in {'boolean','yes/no'} and val.upper() not in {'TRUE','FALSE','YES','NO'}:
        errors.append('expected TRUE/FALSE or YES/NO')
    # Enforce schema min/max where present. Percent schema bounds are in human
    # percent units (0..100), matching the CSV presentation.
    x = _numeric_value(val, typ)
    if x is not None:
        for bound_name, cmp in (('min', lambda a,b: a < b), ('max', lambda a,b: a > b)):
            raw = str(spec.get(bound_name,'')).strip()
            if raw == '':
                continue
            try:
                b = float(raw.replace('$','').replace(',','').replace('%',''))
            except Exception:
                continue
            if cmp(x, b):
                errors.append(f'{bound_name} {raw} violated')
    return errors



def _numeric_value(value: str, typ: str = '') -> float | None:
    val = str(value or '').strip()
    if not val:
        return None
    try:
        x = float(val.replace('$','').replace(',','').replace('%',''))
        if (typ or '').lower() in {'percent','pct'} or val.endswith('%'):
            # Schema min/max for percent fields is stored as human percent units.
            return x
        return x
    except Exception:
        return None


def validate_rows(rows: list[dict]) -> list[str]:
    schema = load_schema()
    errors: list[str] = []
    index: dict[tuple[str,str,str], str] = {}
    for r in rows:
        key = (str(r.get('section','')).strip(), str(r.get('subsection','')).strip(), str(r.get('label','')).strip())
        if not key[0] or key[0].startswith('#') or not key[2]:
            continue
        val = str(r.get('value','')).strip()
        index[key] = val
        spec = schema.get(key)
        if not spec:
            continue
        for msg in validate_value(val, spec):
            errors.append(f"{key}: {msg}; got {val!r}")
    def _num(key, default=None):
        spec = schema.get(key, {})
        x = _numeric_value(index.get(key, ''), spec.get('type',''))
        return default if x is None else x
    # Recurring extra ranges must be chronological.
    extra_subs = {k[1] for k in index if k[0] == 'Large Discretionary Expenses'}
    for sub in extra_subs:
        s = _num(('Large Discretionary Expenses', sub, 'repeat_start_year'), None)
        e = _num(('Large Discretionary Expenses', sub, 'repeat_end_year'), None)
        if s is not None and e is not None and int(s) > int(e):
            errors.append(f"('{sub}','repeat_start_year/repeat_end_year'): start year must be <= end year")
    return errors
