from __future__ import annotations
"""One-time upgrade of stored Plan Data from retired shapes to the current schema.

Historically the engine tolerated old plan shapes by aliasing them at parse time
(e.g. ``husband_*`` keys -> ``member_1_*`` in data_io.parse_client). Those
in-memory compatibility shims are load-bearing but obscure the real schema and
have to be duplicated everywhere the data is read. This module instead migrates
the data *at rest* so the read paths can assume the current schema and drop the
shims.

The transforms are pure and row-based so they can be applied to a raw CSV
string, an in-memory row list, or the DB-backed client_files content
identically. This first version covers the member_1/member_2 (formerly
husband/wife) rename; wellness->healthcare terminology and deprecated-row purges
are follow-ups that plug into the same ``migrate_rows`` pipeline.
"""

import csv
import io
from typing import List, Sequence

# Bump when a new transform is added so the version-gated startup migration
# re-runs against already-stored plans.
PLAN_DATA_SCHEMA_VERSION = 2

# (section, subsection) -> {old_label: new_label}. A ``None`` subsection matches
# any subsection within the section.
_LABEL_RENAMES = {
    ("Household", None): {
        "husband_name": "member_1_name", "husband_dob": "member_1_dob",
        "husband_retirement_date": "member_1_retirement_date",
        "husband_mortality_age": "member_1_mortality_age",
        "wife_name": "member_2_name", "wife_dob": "member_2_dob",
        "wife_retirement_date": "member_2_retirement_date",
        "wife_mortality_age": "member_2_mortality_age",
    },
    ("Model Constants", "Retirement"): {
        "husband_rmd_start_age": "member_1_rmd_start_age",
        "wife_rmd_start_age": "member_2_rmd_start_age",
    },
    ("Scenarios", "Retire Later"): {
        "husband_retire_year": "member_1_retire_year",
        "wife_retire_year": "member_2_retire_year",
    },
}

# section -> {old_subsection: new_subsection}
_SUBSECTION_RENAMES = {
    "Social Security": {"Wife": "Member 2", "Husband": "Member 1"},
    "Income Streams": {
        "Wife Pension": "Member 2 Pension",
        "Wife Single Annuity": "Member 2 Single Annuity",
        "Wife Joint Annuity": "Member 2 Joint Annuity",
        "Husband Single Annuity": "Member 1 Single Annuity",
        "Husband Joint Annuity": "Member 1 Joint Annuity",
    },
}


def _target_key(row: Sequence[str]) -> tuple[str, str, str]:
    """The (section, subsection, label) this row maps to after renames."""
    if len(row) < 3:
        return ("", "", "")
    sec, sub, lbl = str(row[0]), str(row[1]), str(row[2])
    new_sub = _SUBSECTION_RENAMES.get(sec, {}).get(sub, sub)
    renames = _LABEL_RENAMES.get((sec, sub)) or _LABEL_RENAMES.get((sec, None)) or {}
    new_lbl = renames.get(lbl, lbl)
    return (sec, new_sub, new_lbl)


def migrate_rows(rows: Sequence[Sequence[str]]) -> tuple[List[list], int]:
    """Return (migrated_rows, changed_count).

    Renames retired subsections/labels to their current names. Mirrors the old
    shim's "new key wins" rule: if a row already carries the current key, a
    legacy row that would collide with it is dropped rather than overwriting it.
    """
    existing_current = set()
    for row in rows:
        if len(row) >= 3:
            key = (str(row[0]), str(row[1]), str(row[2]))
            if _target_key(row) == key:  # already in current shape
                existing_current.add(key)

    out: List[list] = []
    changed = 0
    for row in rows:
        if len(row) < 3:
            out.append(list(row))
            continue
        sec, sub, lbl = str(row[0]), str(row[1]), str(row[2])
        tgt = _target_key(row)
        if tgt == (sec, sub, lbl):
            out.append(list(row))
            continue
        # This row is a legacy shape. Drop it if the current key already exists.
        if tgt in existing_current:
            changed += 1
            continue
        new_row = list(row)
        new_row[1], new_row[2] = tgt[1], tgt[2]
        out.append(new_row)
        existing_current.add(tgt)
        changed += 1
    return out, changed


def migrate_csv_content(content: str) -> tuple[str, int]:
    """Apply migrate_rows to a raw sectioned-CSV string. Returns (content, changed)."""
    rows = list(csv.reader(io.StringIO(content or "")))
    migrated, changed = migrate_rows(rows)
    if not changed:
        return content, 0
    out = io.StringIO()
    csv.writer(out, lineterminator="\n").writerows(migrated)
    return out.getvalue(), changed
