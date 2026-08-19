"""Backward-compat migration: legacy husband/wife Plan Data -> member_1/2 schema.

These prove the at-rest migration upgrades old plans correctly, which is the
prerequisite for removing the in-memory husband/wife aliasing shim in
data_io.parse_client and the husband_name/wife_name fallbacks in domain_models.
"""
import csv
import io
from pathlib import Path

from src.plan_data_migration import migrate_csv_content, migrate_rows, migrate_sectioned_data

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
        "Household": {"": {"husband_name": "Robert", "wife_name": "Susan",
                            "residence_state": "Illinois"}},
        "Social Security": {"Husband": {"claim_age": "70"}, "Wife": {"claim_age": "67"}},
    }
    migrated, _ = migrate_sectioned_data({k: {s: dict(v) for s, v in sd.items()} for k, sd in data.items()})
    assert migrated["Household"][""]["member_1_name"] == "Robert"
    c = parse_client({k: {s: dict(v) for s, v in sd.items()} for k, sd in data.items()}, "")
    assert c["h_name"] == "Robert"
    assert c["w_name"] == "Susan"


# --- Phase 2: the version gate and the one-shot at-rest runner -----------------
#
# Before this, PLAN_DATA_SCHEMA_VERSION had no consumer and migrate_csv_content
# had no caller: every load re-normalized legacy shapes in memory and nothing
# ever rewrote the data, so legacy rows lived forever and each new transform
# added permanent per-load cost.


def _tmp_db():
    import tempfile
    return Path(tempfile.mkdtemp()) / "s.sqlite"


def _staged_input(tmp_path):
    """An input/ dir holding one legacy file and one already-current file."""
    work = tmp_path / "input"
    work.mkdir(parents=True, exist_ok=True)
    (work / "client_data.csv").write_text(
        "section,subsection,label,value\n"
        "Household,,husband_name,Robert\n"
        "Household,,wife_name,Susan\n",
        encoding="utf-8", newline="",
    )
    (work / "client_policy.csv").write_text(
        "section,subsection,label,value\nHousehold,,member_1_name,Robert\n",
        encoding="utf-8", newline="",
    )
    return work


def test_a_never_migrated_store_reports_version_zero():
    from src.plan_data_migration import stored_schema_version
    assert stored_schema_version(db_path=_tmp_db()) == 0


def test_needs_migration_is_true_one_version_behind():
    from src.plan_data_migration import (
        PLAN_DATA_SCHEMA_VERSION, needs_migration, set_stored_schema_version,
    )
    db = _tmp_db()
    set_stored_schema_version(PLAN_DATA_SCHEMA_VERSION - 1, db_path=db)
    assert needs_migration(db_path=db) is True


def test_needs_migration_is_false_once_stamped_current():
    from src.plan_data_migration import (
        PLAN_DATA_SCHEMA_VERSION, needs_migration, set_stored_schema_version,
    )
    db = _tmp_db()
    set_stored_schema_version(PLAN_DATA_SCHEMA_VERSION, db_path=db)
    assert needs_migration(db_path=db) is False


def test_runner_rewrites_legacy_rows_and_stamps_the_version(tmp_path):
    from src.plan_data_migration import (
        PLAN_DATA_SCHEMA_VERSION, migrate_plan_data_at_rest, stored_schema_version,
    )
    work, db = _staged_input(tmp_path), _tmp_db()
    report = migrate_plan_data_at_rest(work, db_path=db)

    assert report["skipped"] is False
    assert report["total_changed"] == 2
    assert "client_data.csv" in report["migrated"]
    text = (work / "client_data.csv").read_text(encoding="utf-8")
    assert "member_1_name" in text and "husband_name" not in text
    assert stored_schema_version(db_path=db) == PLAN_DATA_SCHEMA_VERSION


def test_runner_leaves_already_current_files_untouched(tmp_path):
    """An unchanged file must keep its bytes AND its mtime.

    Rewriting every file unconditionally would churn every hash in
    plan_data_manifest.json on each upgrade, which is how a migration that
    changed nothing still looks like it changed everything.
    """
    from src.plan_data_migration import migrate_plan_data_at_rest
    work, db = _staged_input(tmp_path), _tmp_db()
    untouched = work / "client_policy.csv"
    before_text = untouched.read_text(encoding="utf-8")
    before_mtime = untouched.stat().st_mtime_ns

    report = migrate_plan_data_at_rest(work, db_path=db)

    assert "client_policy.csv" not in report["migrated"]
    assert untouched.read_text(encoding="utf-8") == before_text
    assert untouched.stat().st_mtime_ns == before_mtime


def test_runner_is_idempotent_and_skips_the_second_time(tmp_path):
    from src.plan_data_migration import migrate_plan_data_at_rest
    work, db = _staged_input(tmp_path), _tmp_db()
    migrate_plan_data_at_rest(work, db_path=db)
    after_first = (work / "client_data.csv").read_text(encoding="utf-8")

    second = migrate_plan_data_at_rest(work, db_path=db)

    assert second["skipped"] is True
    assert second["total_changed"] == 0
    assert (work / "client_data.csv").read_text(encoding="utf-8") == after_first


def test_dry_run_reports_without_writing_or_stamping(tmp_path):
    from src.plan_data_migration import (
        migrate_plan_data_at_rest, stored_schema_version,
    )
    work, db = _staged_input(tmp_path), _tmp_db()
    before = (work / "client_data.csv").read_text(encoding="utf-8")

    report = migrate_plan_data_at_rest(work, db_path=db, dry_run=True)

    assert report["total_changed"] == 2
    assert (work / "client_data.csv").read_text(encoding="utf-8") == before
    assert stored_schema_version(db_path=db) == 0


def test_startup_migration_is_safe_when_input_dir_is_missing():
    """A missing/unreadable input dir must not raise -- startup would die."""
    import tempfile
    from src.plan_data_migration import migrate_plan_data_at_rest
    work = Path(tempfile.mkdtemp())
    report = migrate_plan_data_at_rest(work / "does_not_exist", db_path=work / "s.sqlite")
    assert report["total_changed"] == 0


def test_startup_migration_survives_an_undecodable_csv():
    """One unreadable file must not stop the readable ones migrating."""
    import tempfile
    from src.plan_data_migration import migrate_plan_data_at_rest
    work = Path(tempfile.mkdtemp())
    (work / "broken.csv").write_bytes(b"\xff\xfe\x00\x00not utf8")
    (work / "client_household.csv").write_text(
        "section,subsection,label,value,units,notes\n"
        "Household,,husband_name,Matt,text,\n",
        encoding="utf-8",
    )
    report = migrate_plan_data_at_rest(work, db_path=work / "s.sqlite")
    assert report["total_changed"] == 1  # good file still migrated


def test_startup_wrapper_resolves_input_through_the_workspace_root(monkeypatch, tmp_path):
    """It must honour RETIREMENT_SYSTEM_WORKSPACE_ROOT, not a __file__ root.

    This is the 2026-08-12 frozen-gate bug as a migration: a hardcoded root
    there made runs under a custom workspace resolve plan data against the repo
    instead. Reading the wrong files is recoverable; REWRITING them is not.
    """
    from src.plan_data_migration import run_startup_plan_data_migration
    work = tmp_path / "ws"
    (work / "input").mkdir(parents=True)
    (work / "input" / "client_data.csv").write_text(
        "section,subsection,label,value\nHousehold,,husband_name,Robert\n",
        encoding="utf-8", newline="",
    )
    monkeypatch.setenv("RETIREMENT_SYSTEM_WORKSPACE_ROOT", str(work))

    report = run_startup_plan_data_migration(db_path=tmp_path / "s.sqlite")

    assert report["total_changed"] == 1
    assert "member_1_name" in (work / "input" / "client_data.csv").read_text(encoding="utf-8")


def test_startup_wrapper_never_raises_on_a_broken_store(monkeypatch, tmp_path):
    import src.plan_data_migration as m
    monkeypatch.setattr(m, "migrate_plan_data_at_rest", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    report = m.run_startup_plan_data_migration(input_dir=tmp_path, db_path=tmp_path / "s.sqlite")
    assert report == {"migrated": {}, "total_changed": 0, "skipped": True}


# --- Phase 3: wellness -> healthcare, namespaces 2 and 3 only -----------------
#
# Scope was set by the inventory at
# docs/superpowers/plans/2026-08-10-wellness-rename-inventory.md. The section
# name "Wellness" is the PARENT of Healthcare in this product's hierarchy
# (healthcare = premiums/doctor/dentist; wellness also covers gym, massage,
# supplements), so it is correct as-is and deliberately not renamed.


def test_mc_shock_params_are_renamed_to_healthcare():
    from src.plan_data_migration import migrate_csv_content
    content = (
        "section,subsection,label,value\n"
        "Model Constants,Monte Carlo,wellness_cost_shocks,TRUE\n"
        "Model Constants,Monte Carlo,wellness_shock_annual_prob,0.03\n"
        "Model Constants,Monte Carlo,wellness_shock_mean_cost,150000\n"
    )
    out, changed = migrate_csv_content(content)
    assert changed == 3
    assert "healthcare_cost_shocks" in out
    assert "healthcare_shock_annual_prob" in out
    assert "healthcare_shock_mean_cost" in out
    assert "wellness_" not in out


def test_premium_category_ids_are_renamed_in_the_taxonomy():
    from src.plan_data_migration import migrate_csv_content
    content = (
        "section,subsection,label,value\n"
        "Wellness,Healthcare Premium,pre65_wellness_premium,1\n"
        "Wellness,Healthcare Premium,wellness_premium,1\n"
    )
    out, changed = migrate_csv_content(content)
    assert changed == 2
    assert "pre65_healthcare_premium" in out
    assert "healthcare_premium" in out


def test_the_wellness_section_name_is_never_renamed():
    """Wellness is the parent group, not a stale synonym for healthcare.

    Renaming it would also be unsafe: migrate_rows has no section-rename
    support, and data_io's _v() returns its hardcoded DEFAULT when a section is
    missing rather than raising -- so a renamed section silently swaps real
    client values for defaults. Both reasons, one test.
    """
    from src.plan_data_migration import migrate_csv_content
    content = (
        "section,subsection,label,value\n"
        "Wellness,Medicare,part_b_base_premium_monthly,999\n"
        "Wellness,Wellness Budget Detail,gym_fitness,1200\n"
    )
    out, changed = migrate_csv_content(content)
    assert changed == 0
    assert "Wellness,Medicare" in out
    assert "Wellness Budget Detail" in out


def test_flat_category_columns_are_renamed_too():
    """The category id is a foreign key in four flat files migrate_rows cannot see.

    Renaming only the sectioned taxonomy would leave budget lines, rules and
    aliases pointing at an id that no longer exists.
    """
    from src.plan_data_migration import migrate_flat_category_content
    budget = (
        "section,line_id,label,category_id\n"
        "category,pre65_premium,Pre-65 Healthcare Premium,pre65_wellness_premium\n"
    )
    out, changed = migrate_flat_category_content(budget)
    assert changed == 1
    assert "pre65_healthcare_premium" in out
    assert "pre65_wellness_premium" not in out


def test_flat_migration_covers_the_aliases_foreign_key():
    from src.plan_data_migration import migrate_flat_category_content
    aliases = (
        "match_value,match_field,exact,priority,category_id,source\n"
        "Healthcare Premium,category,0,50,pre65_wellness_premium,user\n"
    )
    out, changed = migrate_flat_category_content(aliases)
    assert changed == 1
    assert "pre65_healthcare_premium" in out


def test_flat_migration_leaves_the_tracking_bucket_alone():
    """spending_category_map.csv's 4th column is `tracking`, a functional group.

    It reads `wellness` because healthcare rolls UP into wellness, and it feeds
    wellness_base_yr through report_compute/results_model. Renaming it would be
    an engine change, which this phase forbids.
    """
    from src.plan_data_migration import migrate_flat_category_content
    cat_map = (
        "super_group,group,category,tracking\n"
        "Expenses,Healthcare Premium,Healthcare Premium,wellness\n"
        "Expenses,Medical,Health Club,wellness\n"
    )
    out, changed = migrate_flat_category_content(cat_map)
    assert changed == 0
    assert out.count("wellness") == 2


def test_flat_migration_never_touches_transaction_descriptions():
    """Client transaction records are evidence, not terminology to tidy.

    ytd_transactions.csv carries Amazon product titles containing "Optimal
    Wellness". A sweep that rewrote those would falsify the client's own
    purchase log to satisfy a rename.
    """
    from src.plan_data_migration import migrate_flat_category_content
    txns = (
        "date,merchant,category,description\n"
        "2025-03-05,Amazon,Vitamins & Supplements,"
        "\"Nordic Naturals Omega-3 - Immune Support, Optimal Wellness\"\n"
    )
    out, changed = migrate_flat_category_content(txns)
    assert changed == 0
    assert "Optimal Wellness" in out


def test_runner_applies_both_sectioned_and_flat_transforms(tmp_path):
    """The at-rest runner must move the taxonomy AND its flat foreign keys.

    Renaming one without the other is the broken-join case: a budget line would
    point at a category id that no longer exists anywhere.
    """
    from src.plan_data_migration import migrate_plan_data_at_rest
    work = tmp_path / "input"
    work.mkdir(parents=True)
    (work / "client_spending_taxonomy.csv").write_text(
        "section,subsection,label,value\n"
        "Wellness,Healthcare Premium,pre65_wellness_premium,1\n",
        encoding="utf-8", newline="",
    )
    (work / "client_spending_aliases.csv").write_text(
        "match_value,match_field,exact,priority,category_id,source\n"
        "Healthcare Premium,category,0,50,pre65_wellness_premium,user\n",
        encoding="utf-8", newline="",
    )
    (work / "spending_category_map.csv").write_text(
        "super_group,group,category,tracking\n"
        "Expenses,Healthcare Premium,Healthcare Premium,wellness\n",
        encoding="utf-8", newline="",
    )

    report = migrate_plan_data_at_rest(work, db_path=tmp_path / "s.sqlite")

    assert "client_spending_taxonomy.csv" in report["migrated"]
    assert "client_spending_aliases.csv" in report["migrated"]
    # The tracking bucket is untouched, so its file never gets rewritten.
    assert "spending_category_map.csv" not in report["migrated"]
    assert "pre65_healthcare_premium" in (work / "client_spending_taxonomy.csv").read_text(encoding="utf-8")
    assert "pre65_healthcare_premium" in (work / "client_spending_aliases.csv").read_text(encoding="utf-8")
    assert "wellness" in (work / "spending_category_map.csv").read_text(encoding="utf-8")


# --- Estate Planning|Illinois -> Estate Planning|State, 2026-08-19 (item 291 Class 4) ---
#
# Subsection only -- the label (state_estate_exemption) was already
# state-generic on investigation, not "il_exempt" as the ticket assumed;
# only the SUBSECTION name baked Illinois in. Python identifiers
# (c['il_exempt'], the in-memory dict key) are deliberately unchanged.


def test_estate_planning_illinois_subsection_migrates_to_state():
    rows = [
        ["section", "subsection", "label", "value", "units", "notes"],
        ["Estate Planning", "Illinois", "state_estate_exemption", "4000000", "USD", ""],
    ]
    out, changed = migrate_rows(rows)
    assert changed == 1
    migrated_row = next(r for r in out if r[2] == "state_estate_exemption")
    assert migrated_row[0] == "Estate Planning"
    assert migrated_row[1] == "State"
    assert not any(r[1] == "Illinois" for r in out if r[0] == "Estate Planning")


def test_estate_planning_migration_respects_current_key_wins():
    """migrate_rows semantics: a legacy row colliding with an existing
    current row is DROPPED, never overwritten."""
    rows = [
        ["section", "subsection", "label", "value", "units", "notes"],
        ["Estate Planning", "State", "state_estate_exemption", "5000000", "USD", ""],
        ["Estate Planning", "Illinois", "state_estate_exemption", "4000000", "USD", ""],
    ]
    out, changed = migrate_rows(rows)
    values = [r[3] for r in out if r[0] == "Estate Planning" and r[2] == "state_estate_exemption"]
    assert values == ["5000000"], "the current row must survive; the legacy row must be dropped, not overwrite it"
    assert changed == 1


def test_estate_planning_migration_applies_to_sectioned_data_too():
    data = {"Estate Planning": {"Illinois": {"state_estate_exemption": "4000000"}}}
    out, changed = migrate_sectioned_data(data)
    assert out["Estate Planning"]["State"]["state_estate_exemption"] == "4000000"
    assert "Illinois" not in out["Estate Planning"]
    assert changed == 1


def test_estate_planning_already_current_shape_is_a_no_op():
    rows = [
        ["section", "subsection", "label", "value", "units", "notes"],
        ["Estate Planning", "State", "state_estate_exemption", "4000000", "USD", ""],
    ]
    out, changed = migrate_rows(rows)
    assert changed == 0
    assert out[1][1] == "State"


def test_other_estate_planning_subsections_are_not_touched():
    """Only the Illinois subsection renames -- Federal and Credit Shelter
    Trust are genuinely federal/generic concepts, not state-specific."""
    rows = [
        ["section", "subsection", "label", "value", "units", "notes"],
        ["Estate Planning", "Federal", "exemption_mfj", "30000000", "USD", ""],
        ["Estate Planning", "Credit Shelter Trust", "shelter_cap", "8000000", "USD", ""],
    ]
    out, changed = migrate_rows(rows)
    assert changed == 0
    assert [r[1] for r in out[1:]] == ["Federal", "Credit Shelter Trust"]


def test_dry_run_against_live_input_reports_the_expected_file(tmp_path):
    """Step 5.5's requirement: dry-run against live input/ and confirm the
    changed-file list matches expectations before applying. Never applies
    for real -- this test only reads the live input/ tree read-only via a
    dry_run call, which writes nothing, per this branch's binding safety
    constraint (never mutate live data)."""
    from pathlib import Path
    from src.plan_data_migration import migrate_plan_data_at_rest

    live_input = Path("input")
    if not (live_input / "client_insurance_estate.csv").exists():
        import pytest
        pytest.skip("no live client_insurance_estate.csv in this worktree")

    report = migrate_plan_data_at_rest(live_input, db_path=tmp_path / "s.sqlite", dry_run=True)

    # The live worktree file (restored locally for ticket 291 Class 1's own
    # blast-radius fix) still carries the legacy "Illinois" subsection, so a
    # dry run against it must report exactly this file as needing migration.
    assert "client_insurance_estate.csv" in report["migrated"]
    # Never written -- dry_run must leave the file untouched.
    original = (live_input / "client_insurance_estate.csv").read_text(encoding="utf-8")
    assert "Illinois" in original, "dry_run must not have written to the live file"
