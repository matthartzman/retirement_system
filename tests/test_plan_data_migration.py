"""Backward-compat migration: legacy husband/wife Plan Data -> member_1/2 schema.

These prove the at-rest migration upgrades old plans correctly, which is the
prerequisite for removing the in-memory husband/wife aliasing shim in
data_io.parse_client and the husband_name/wife_name fallbacks in domain_models.
"""
import csv
import io
from pathlib import Path

from src.plan_data_migration import migrate_csv_content, migrate_rows

ROOT = Path(__file__).resolve().parents[1]
LEGACY = ROOT / "tests" / "fixtures" / "legacy_plans" / "legacy_household.csv"


def _sectioned(content):
    out = {}
    for row in csv.reader(io.StringIO(content)):
        if len(row) >= 4 and row[0] and row[0] != "section":
            out[(row[0], row[1], row[2])] = row[3]
    return out


def test_legacy_labels_and_subsections_are_renamed():
    migrated, changed = migrate_csv_content(LEGACY.read_text(encoding="utf-8"))
    assert changed > 0
    keys = _sectioned(migrated)
    # Household label renames
    assert keys[("Household", "", "member_1_name")] == "Robert"
    assert keys[("Household", "", "member_2_name")] == "Susan"
    assert keys[("Household", "", "member_1_mortality_age")] == "92"
    # Subsection renames
    assert keys[("Social Security", "Member 1", "claim_age")] == "70"
    assert keys[("Social Security", "Member 2", "claim_age")] == "67"
    assert keys[("Income Streams", "Member 2 Pension", "base")] == "50000"
    assert keys[("Income Streams", "Member 1 Single Annuity", "base")] == "20000"
    # Model Constants + Scenarios label renames
    assert keys[("Model Constants", "Retirement", "member_1_rmd_start_age")] == "73"
    assert keys[("Scenarios", "Retire Later", "member_1_retire_year")] == "2030"
    # No legacy keys survive
    assert not any(lbl.startswith(("husband_", "wife_")) for (_, _, lbl) in keys)
    assert not any(sub in ("Husband", "Wife", "Wife Pension", "Husband Single Annuity")
                   for (_, sub, _) in keys)


def test_migration_is_idempotent():
    once, _ = migrate_csv_content(LEGACY.read_text(encoding="utf-8"))
    twice, changed = migrate_csv_content(once)
    assert changed == 0
    assert twice == once


def test_current_key_wins_on_collision():
    # A plan carrying both the legacy and current key must keep the current value.
    rows = [
        ["Household", "", "member_1_name", "NewName"],
        ["Household", "", "husband_name", "OldName"],
    ]
    migrated, changed = migrate_rows(rows)
    keys = {(r[0], r[1], r[2]): r[3] for r in migrated}
    assert keys[("Household", "", "member_1_name")] == "NewName"
    assert ("Household", "", "husband_name") not in keys
    assert changed == 1  # the legacy row was dropped


def test_current_format_is_unchanged():
    current = "section,subsection,label,value\nHousehold,,member_1_name,Alice\n"
    migrated, changed = migrate_csv_content(current)
    assert changed == 0
    assert migrated == current


def test_parse_client_reads_legacy_household_via_migration():
    # End-to-end: a legacy husband/wife sectioned dict parses into the current
    # member_1/member_2 config with no inline shim in parse_client.
    from src.plan_data_migration import migrate_sectioned_data
    from src.data_io import parse_client
    data = {
        "Household": {"": {"husband_name": "Robert", "wife_name": "Susan"}},
        "Social Security": {"Husband": {"claim_age": "70"}, "Wife": {"claim_age": "67"}},
    }
    migrated, _ = migrate_sectioned_data({k: {s: dict(v) for s, v in sd.items()} for k, sd in data.items()})
    assert migrated["Household"][""]["member_1_name"] == "Robert"
    c = parse_client({k: {s: dict(v) for s, v in sd.items()} for k, sd in data.items()}, "")
    assert c["h_name"] == "Robert"
    assert c["w_name"] == "Susan"
