"""Dev tool: regenerate ``reference_src/generated_schema_coverage.csv`` (WP3.7).

Backfills schema rows for plan-data fields the hand-maintained ``reference_src/schema.csv``
lacks, inferring a type from each field's units/value/notes in the plan CSVs under
``input/``. Run ``python tools/build_reference_db.py`` afterwards to ship the result.
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.plan_data_registry import client_data_csv_files  # noqa: E402
from tools.reference_slices.schema_fields import FIELDS, load_merged  # noqa: E402

SRC_DIR = ROOT / "reference_src"
GENERATED_PATH = SRC_DIR / "generated_schema_coverage.csv"
PLAN_FILES = [*client_data_csv_files(), "target_allocation.csv"]


def infer_type(units: str, value: str, label: str='', notes: str='') -> str:
    u=(units or '').lower().strip(); v=str(value or '').strip(); l=(label or '').lower(); n=(notes or '').lower()
    choice_labels = {
        'filing_status','survivor_filing_status','roth_conversion_policy',
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


def generate_schema_coverage(input_dir: Path | None = None, output_path: Path | None = None) -> dict:
    input_dir = input_dir or ROOT / "input"
    output_path = output_path or GENERATED_PATH
    existing = load_merged(SRC_DIR, ("schema.csv",))  # the hand-maintained catalog only
    generated = []
    seen = set()
    for name in PLAN_FILES:
        p = input_dir / name
        if not p.exists():
            continue
        with p.open(newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                sec = (row.get("section") or "").strip()
                label = (row.get("label") or "").strip()
                if not sec or sec.startswith("#") or not label:
                    continue
                key = (sec, (row.get("subsection") or "").strip(), label)
                if key in existing or key in seen:
                    continue
                seen.add(key)
                units = (row.get("units") or "").strip()
                val = (row.get("value") or "").strip()
                notes = (row.get("notes") or "").strip()
                generated.append({"section": key[0], "subsection": key[1], "label": key[2],
                                  "type": infer_type(units, val, label, notes),
                                  "required": "FALSE", "default": "", "min": "", "max": "",
                                  "description": notes or f"Generated schema help for {key[0]} / {key[1]} / {key[2]}."})
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(FIELDS), lineterminator="\n")
        w.writeheader()
        w.writerows(generated)
    return {"generated": len(generated), "output": str(output_path), "total_schema": len(existing) + len(generated)}


if __name__ == "__main__":
    print(generate_schema_coverage())
