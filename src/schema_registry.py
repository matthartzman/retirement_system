from __future__ import annotations
"""Schema-driven validation/help registry for Plan Data rows."""
import csv, re
from pathlib import Path
from typing import Dict, Tuple
ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / 'reference_data' / 'schema.csv'
GENERATED_SCHEMA_PATH = ROOT / 'reference_data' / 'generated_schema_coverage.csv'
PLAN_FILES = ['client_data.csv','client_household.csv','client_income.csv','client_spending.csv','client_assets.csv','client_policy.csv','client_insurance_estate.csv','client_optional_functions.csv','asset_class_optimizer_controls.csv','target_allocation.csv']

def schema_key(row: dict) -> tuple[str,str,str]:
    return ((row.get('section') or '').strip(), (row.get('subsection') or '').strip(), (row.get('label') or '').strip())

def infer_type(units: str, value: str, label: str='', notes: str='') -> str:
    u=(units or '').lower().strip(); v=str(value or '').strip(); l=(label or '').lower(); n=(notes or '').lower()
    choice_labels = {
        'filing_status','survivor_filing_status','net_worth_method','roth_conversion_policy',
        'roth_objective_mode','estate_tax_objective_mode','irmaa_guardrail_mode',
        'roth_irmaa_target_tier','legacy_objective_mode','allocation_selection_mode',
        'selection_action','alternate_asset_class'
    }
    if u == 'choice' or l in choice_labels or '|' in str(notes or ''):
        return 'choice'
    if u in {'yes/no','true/false','boolean'} or v.upper() in {'YES','NO','TRUE','FALSE'}: return 'boolean'
    if 'date' in l or re.match(r'\d{1,2}/\d{1,2}/\d{4}$', v): return 'date'
    if '%' in v or 'pct' in u or 'percent' in u: return 'percent'
    if u in {'year','years'} or l.endswith('_year'): return 'year'
    if 'usd' in u or '$' in v or any(tok in l for tok in ['amount','balance','income','spending','premium','benefit','salary','value','cost']): return 'currency'
    try:
        float(v.replace(',',''))
        return 'number'
    except Exception:
        return 'text'

def load_schema() -> dict[tuple[str,str,str], dict]:
    out={}
    for path in [SCHEMA_PATH, GENERATED_SCHEMA_PATH]:
        if not path.exists(): continue
        with path.open(newline='', encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                key=schema_key(row)
                if not (key[0] and key[2]):
                    continue
                # schema.csv is authoritative. Generated coverage is a backfill for
                # rows missing from the hand-maintained schema, so it must not
                # downgrade a manual choice/boolean/percent definition.
                if key in out:
                    continue
                clean = {str(k): v for k, v in dict(row).items() if k is not None}
                extras = row.get(None)
                if extras:
                    desc = str(clean.get('description') or '').strip()
                    extra = ','.join(str(x).strip() for x in extras if str(x).strip())
                    if extra:
                        clean['description'] = (desc + ', ' + extra).strip(', ') if desc else extra
                out[key]=clean
    return out

def generate_schema_coverage(input_dir: Path | None = None, output_path: Path | None = None) -> dict:
    input_dir = input_dir or ROOT / 'input'
    output_path = output_path or GENERATED_SCHEMA_PATH
    existing=load_schema()
    generated=[]; seen=set()
    for name in PLAN_FILES:
        p=input_dir/name
        if not p.exists(): continue
        with p.open(newline='', encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                sec=(row.get('section') or '').strip(); label=(row.get('label') or '').strip()
                if not sec or sec.startswith('#') or not label: continue
                key=(sec,(row.get('subsection') or '').strip(),label)
                if key in existing or key in seen: continue
                seen.add(key)
                units=(row.get('units') or '').strip(); val=(row.get('value') or '').strip(); notes=(row.get('notes') or '').strip()
                generated.append({'section':key[0],'subsection':key[1],'label':key[2], 'type':infer_type(units,val,label,notes),
                                  'required':'FALSE','default':'','min':'','max':'',
                                  'description': notes or f'Generated schema help for {key[0]} / {key[1]} / {key[2]}.'})
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fields=['section','subsection','label','type','required','default','min','max','description']
    with output_path.open('w', newline='', encoding='utf-8') as f:
        w=csv.DictWriter(f, fieldnames=fields, lineterminator='\n'); w.writeheader(); w.writerows(generated)
    return {'generated':len(generated), 'output':str(output_path), 'total_schema':len(existing)+len(generated)}

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
    # Cross-field rules called out by the expert assessment.
    h_ret = _num(('Household','','husband_retirement_date'), None)
    earn_last = _num(('Cashflow','Earned Income','earned_income_last_year'), None)
    # Dates generally are not numeric; infer year from common date strings.
    raw_h_ret = index.get(('Household','','husband_retirement_date'), '') or index.get(('Household','','retirement_date'), '')
    m = re.search(r'(20\d{2}|19\d{2})', raw_h_ret)
    h_ret_year = int(m.group(1)) if m else None
    # Note: earned income may legitimately extend past the formal retirement date
    # (part-year work, business transition, consulting, etc.) — no cross-field
    # constraint enforced here.
    # Annuity dividend split must sum to 100% when both are present.
    ann_subs = {k[1] for k in index if k[0] == 'Income Streams'}
    for sub in ann_subs:
        a = _num(('Income Streams', sub, 'additional_income_pct'), None)
        b = _num(('Income Streams', sub, 'pay_in_cash_pct'), None)
        if a is not None and b is not None and abs((a + b) - 100.0) > 0.01:
            errors.append(f"('Income Streams','{sub}','additional_income_pct/pay_in_cash_pct'): percentages must sum to 100%; got {a+b:.2f}%")
    # Recurring extra ranges must be chronological.
    extra_subs = {k[1] for k in index if k[0] == 'Large Discretionary Expenses'}
    for sub in extra_subs:
        s = _num(('Large Discretionary Expenses', sub, 'repeat_start_year'), None)
        e = _num(('Large Discretionary Expenses', sub, 'repeat_end_year'), None)
        if s is not None and e is not None and int(s) > int(e):
            errors.append(f"('{sub}','repeat_start_year/repeat_end_year'): start year must be <= end year")
    return errors
