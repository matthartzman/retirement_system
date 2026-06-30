from __future__ import annotations
import csv, re, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.version import VERSION
USER_SURFACES=[ROOT/'src',ROOT/'frontend',ROOT/'tools',ROOT/'system_config.csv']
IGNORE_PARTS={'documentation','tests'}
ALLOWED_PATTERNS=[r'/api/v8', r'API_NAMESPACE = "v8"', r'test_v8_', r'v8_1', r'v8_2', r'Version 7\.8\.1 correction']
STALE=[r'v8\.0', r'v8\.1', r'Version 8\.0', r'Version 8\.1', r'Retirement System v8\.0', r'Retirement System v8\.1', r'RetirementPlanSystem/8\.0', r'RetirementPlanSystem/8\.1', r'rs_v78_token', r'LAN_TEST_CHANGE_ME_.*_7_8']
def allowed(line): return any(re.search(p,line) for p in ALLOWED_PATTERNS)
def main():
    errors=[]
    cfg=ROOT/'system_config.csv'
    if cfg.exists():
        with cfg.open(newline='', encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                if row.get('section')=='System Configuration' and row.get('subsection')=='Runtime' and row.get('label')=='system_version':
                    if str(row.get('value')).strip()!=VERSION:
                        errors.append(f'system_config system_version={row.get("value")} expected {VERSION}')
    for base in USER_SURFACES:
        paths=[base] if base.is_file() else list(base.rglob('*'))
        for p in paths:
            if p.resolve() == Path(__file__).resolve(): continue
            if p.is_dir() or any(part in IGNORE_PARTS for part in p.parts): continue
            if p.suffix.lower() in {'.pyc','.pyo','.png','.jpg','.jpeg','.ico','.svg','.db','.xlsx','.pdf','.zip'}: continue
            try: text=p.read_text(encoding='utf-8', errors='ignore')
            except Exception: continue
            for i,line in enumerate(text.splitlines(),1):
                if allowed(line): continue
                for pat in STALE:
                    if re.search(pat,line): errors.append(f'{p.relative_to(ROOT)}:{i}: stale version token: {line[:140]}')
    if errors:
        print('VERSION SURFACE CHECK FAILED')
        for e in errors: print('- '+e)
        return 1
    print('VERSION SURFACE CHECK PASSED')
    return 0
if __name__=='__main__': raise SystemExit(main())
