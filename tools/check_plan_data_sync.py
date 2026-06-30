from __future__ import annotations
import csv, hashlib, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PLAN_FILES=['client_data.csv','client_household.csv','client_income.csv','client_spending.csv','client_assets.csv','client_policy.csv','client_insurance_estate.csv','client_optional_functions.csv','asset_class_optimizer_controls.csv','client_holdings.csv','target_allocation.csv']
def sha(p:Path): return hashlib.sha256(p.read_bytes()).hexdigest()
def build_manifest(input_dir: Path):
    files={}
    for name in PLAN_FILES:
        p=input_dir/name
        if p.exists(): files[name]={'sha256':sha(p),'bytes':p.stat().st_size}
    return {'canonical_format':'CSV','version':'8.3','files':files}
def main():
    input_dir=ROOT/'input'
    manifest_path=input_dir/'plan_data_manifest.json'
    if not input_dir.exists():
        print('No input/ directory; complete release packages intentionally exclude Plan Data.')
        return 0
    current=build_manifest(input_dir)
    if not manifest_path.exists() or '--write' in sys.argv:
        manifest_path.write_text(json.dumps(current,indent=2,sort_keys=True), encoding='utf-8')
        print(f'Wrote {manifest_path}')
        return 0
    saved=json.loads(manifest_path.read_text(encoding='utf-8'))
    if saved != current:
        print('Plan Data manifest mismatch. CSV is canonical; regenerate JSON/YAML and run --write after intentional changes.')
        return 1
    print('PLAN DATA SYNC CHECK PASSED')
    return 0
if __name__ == '__main__': raise SystemExit(main())
