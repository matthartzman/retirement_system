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
#   2 -> 3 (2026-08-17): wellness -> healthcare for the Monte Carlo shock params
#   and the premium category ids, including the flat-table foreign keys.
PLAN_DATA_SCHEMA_VERSION = 3

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
    # wellness -> healthcare, 2026-08-17. Scope set by
    # docs/superpowers/plans/2026-08-10-wellness-rename-inventory.md.
    #
    # Only the MEDICAL keys move. "Wellness" is the parent group in this
    # product's hierarchy and "Healthcare" is the medical subset of it --
    # gym_fitness, massage_bodywork and vitamins_supplements sit under Wellness
    # too, and no Healthcare name covers them. So the `Wellness` SECTION and the
    # `Wellness Budget Detail` SUBSECTION are correct as they stand and are
    # deliberately absent from these tables. See
    # test_the_wellness_section_name_is_never_renamed.
    ("Model Constants", "Monte Carlo"): {
        "wellness_cost_shocks": "healthcare_cost_shocks",
        "wellness_shock_annual_prob": "healthcare_shock_annual_prob",
        "wellness_shock_mean_cost": "healthcare_shock_mean_cost",
    },
    ("Wellness", "Healthcare Premium"): {
        "pre65_wellness_premium": "pre65_healthcare_premium",
        "wellness_premium": "healthcare_premium",
    },
}

# Category ids are foreign keys in flat tables that migrate_rows cannot reach:
# it walks (section, subsection, label) triples, and these files have neither.
# Renaming the sectioned taxonomy without them would leave budget lines, mapping
# rules and aliases pointing at an id that no longer exists.
_FLAT_CATEGORY_RENAMES = {
    "pre65_wellness_premium": "pre65_healthcare_premium",
    "wellness_premium": "healthcare_premium",
}

# Only these column headers hold a category id. Restricting by header is what
# keeps the transform from touching two things that also contain "wellness":
# spending_category_map.csv's `tracking` column (a functional grouping bucket
# whose value IS "wellness", correctly, because healthcare rolls up into it),
# and ytd_transactions.csv's imported product descriptions, which are the
# client's own purchase records rather than terminology to tidy.
_FLAT_CATEGORY_COLUMNS = ("category_id", "category")

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


def migrate_flat_category_content(content: str) -> tuple[str, int]:
    """Rename category-id foreign keys in a FLAT (non-sectioned) CSV string.

    Returns ``(content, changed)``. Used for client_spending_budget.csv, its
    recovery seed, client_spending_rules.csv and client_spending_aliases.csv --
    four files that carry a category id in a named column rather than as a
    (section, subsection, label) triple, and which migrate_rows therefore cannot
    see at all.

    Two deliberate narrownesses, each of which prevented a real mistake when the
    rename surface was inventoried:

    * Only columns named in ``_FLAT_CATEGORY_COLUMNS`` are considered. The
      `tracking` column of spending_category_map.csv holds the literal value
      "wellness" and must keep it -- that is the umbrella bucket healthcare
      rolls up into, and it feeds wellness_base_yr through the engine.
    * Only whole-cell exact matches are renamed, never substrings. A substring
      sweep would rewrite the "Optimal Wellness" inside imported Amazon product
      titles in ytd_transactions.csv, i.e. falsify the client's purchase log.
    """
    rows = list(csv.reader(io.StringIO(content or "")))
    if not rows:
        return content, 0

    header = [str(c).strip().lower() for c in rows[0]]
    targets = [i for i, name in enumerate(header) if name in _FLAT_CATEGORY_COLUMNS]
    if not targets:
        return content, 0

    changed = 0
    for row in rows[1:]:
        for i in targets:
            if i >= len(row):
                continue
            new = _FLAT_CATEGORY_RENAMES.get(str(row[i]).strip())
            if new and new != row[i]:
                row[i] = new
                changed += 1
    if not changed:
        return content, 0

    out = io.StringIO()
    csv.writer(out, lineterminator="\n").writerows(rows)
    return out.getvalue(), changed


def migrate_sectioned_data(data: dict) -> tuple[dict, int]:
    """Upgrade a parsed sectioned dict ({section:{subsection:{label:value}}}) in place.

    Applies the same subsection/label renames as migrate_rows so every load path
    (CSV, DB snapshot, JSON plan) can funnel through one call and the read code
    can assume the current schema. "Current key wins": when both the legacy and
    current key are present the legacy one is dropped without overwriting.
    """
    changed = 0
    for sec, sub_map in _SUBSECTION_RENAMES.items():
        sec_data = data.get(sec)
        if not isinstance(sec_data, dict):
            continue
        for old_sub, new_sub in sub_map.items():
            if old_sub in sec_data:
                if new_sub not in sec_data:
                    sec_data[new_sub] = sec_data.pop(old_sub)
                else:
                    sec_data.pop(old_sub)
                changed += 1
    for (sec, sub), lbl_map in _LABEL_RENAMES.items():
        sec_data = data.get(sec)
        if not isinstance(sec_data, dict):
            continue
        sub_keys = [sub] if sub is not None else list(sec_data.keys())
        for sk in sub_keys:
            labels = sec_data.get(sk)
            if not isinstance(labels, dict):
                continue
            for old_lbl, new_lbl in lbl_map.items():
                if old_lbl in labels:
                    if new_lbl not in labels:
                        labels[new_lbl] = labels.pop(old_lbl)
                    else:
                        labels.pop(old_lbl)
                    changed += 1
    return data, changed


# Key under which the applied schema version is stamped in local_settings. A
# store that has never been migrated has no row and reads back as 0.
PLAN_DATA_SCHEMA_KEY = "plan_data_schema_version"


def stored_schema_version(db_path=None) -> int:
    """Schema version already applied to the data at rest (0 = never migrated).

    ``local_store`` is imported lazily: ``plan_data_migration`` is imported at
    module load by ``data_io``, and a top-level import here would be circular.
    """
    from .local_store import get_local_setting
    try:
        return int(get_local_setting(PLAN_DATA_SCHEMA_KEY, 0, db_path=db_path) or 0)
    except (TypeError, ValueError):
        return 0


def set_stored_schema_version(version: int, db_path=None) -> None:
    """Stamp the applied schema version after a successful migration."""
    from .local_store import set_local_setting
    set_local_setting(PLAN_DATA_SCHEMA_KEY, int(version), db_path=db_path)


def needs_migration(db_path=None) -> bool:
    """True when the data at rest predates PLAN_DATA_SCHEMA_VERSION."""
    return stored_schema_version(db_path=db_path) < PLAN_DATA_SCHEMA_VERSION


def migrate_plan_data_at_rest(input_dir, db_path=None, dry_run: bool = False) -> dict:
    """Migrate every sectioned Plan Data CSV under ``input_dir`` once, in place.

    Returns ``{"migrated": {name: changed}, "total_changed": int, "skipped": bool}``.

    Only files that actually change are rewritten, so untouched files keep their
    mtime and their plan_data_manifest.json hash -- otherwise a migration that
    changed one file would look like it changed all of them. When the store is
    already stamped at the current version this is a no-op (``skipped=True``).
    ``dry_run=True`` reports what would change without writing or stamping.
    """
    from pathlib import Path

    if not dry_run and not needs_migration(db_path=db_path):
        return {"migrated": {}, "total_changed": 0, "skipped": True}

    root = Path(input_dir)
    migrated: dict = {}
    total = 0
    for path in sorted(root.glob("*.csv")):
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            # A file we cannot read is left exactly as it is. The per-load
            # migrate_sectioned_data normalization still covers it in memory.
            continue
        # Both transforms are attempted on every file, and each is a no-op on
        # data it does not recognise: migrate_rows needs a (section, subsection,
        # label) triple, migrate_flat_category_content needs a category-id
        # column header. Running both beats maintaining a filename list that
        # would silently miss the next flat file added -- which is exactly how
        # client_spending_aliases.csv was missed on the first inventory pass.
        new_content, changed = migrate_csv_content(content)
        flat_content, flat_changed = migrate_flat_category_content(new_content)
        if flat_changed:
            new_content, changed = flat_content, changed + flat_changed
        if not changed:
            continue
        migrated[path.name] = changed
        total += changed
        if not dry_run:
            path.write_text(new_content, encoding="utf-8", newline="")

    if not dry_run:
        set_stored_schema_version(PLAN_DATA_SCHEMA_VERSION, db_path=db_path)
    return {"migrated": migrated, "total_changed": total, "skipped": False}


def run_startup_plan_data_migration(input_dir=None, db_path=None) -> dict:
    """Startup entry point: migrate stored Plan Data once, never fatally.

    Any failure degrades to the existing per-load ``migrate_sectioned_data``
    normalization, which still yields correct reads -- a bad CSV must not stop
    the server from booting.

    The input directory is resolved through ``platform_runtime.workspace_root()``
    and NOT from a ``__file__``-derived repo root. That distinction is the whole
    of the 2026-08-12 frozen-gate bug: a hardcoded root in data_io silently
    ignored RETIREMENT_SYSTEM_WORKSPACE_ROOT, so every run under a custom
    workspace resolved plan data against the wrong directory. A migration that
    got this wrong would not merely read the wrong files -- it would REWRITE
    them, which is not recoverable the way a bad read is.
    """
    try:
        if input_dir is None:
            from .platform_runtime import workspace_root
            input_dir = workspace_root() / "input"
        return migrate_plan_data_at_rest(input_dir, db_path=db_path)
    except Exception:
        return {"migrated": {}, "total_changed": 0, "skipped": True}
