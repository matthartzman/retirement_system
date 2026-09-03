"""Regression tests for the 2026-09-04 audit of bump_version.py's
comprehensiveness (six gaps found by review, none through execution -- see
the corresponding commit): admin.html was never updated by a version bump,
check_version_surfaces.py's stale-token check was frozen to a one-time v7/v8
migration and could not have caught the current bump's own leftovers,
top-level documentation/*.md files outside CLAUDE.md fell through the sweep,
tests/ had no guard against a hardcoded absolute workspace path recurring
(it did once, for real -- see documentation/GOLDEN_MASTER_CHANGELOG.md), and
hardcoded "name_v<N>" filename/schema literals (e.g.
"retirement_system_v10.db") were invisible to every check.

Each test below exercises the specific fix, not the tool end-to-end --
bump()/check_version_surfaces.main() both operate against this repo's real
ROOT and are not designed for tmp_path isolation (matching this test file's
sibling, test_bump_version_folder_rename.py, which tests
sweep_folder_references/preflight_folder_rename/_build_rename_script as
separable units for the same reason).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tools.bump_version as bv  # noqa: E402
import tools.check_version_surfaces as cvs  # noqa: E402


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


# --------------------------------------------------------------------------
# Gap 1: admin.html was never touched by a version bump
# --------------------------------------------------------------------------


def test_apply_admin_html_version_updates_title_and_heading():
    html = (
        '<title>Retirement System v11 Control Center</title>\n'
        '<link rel="stylesheet" href="css/admin.css?v=v11-pricing-symbol-tester-msg-fix-1">\n'
        '<h1>Retirement System v11</h1>\n'
    )
    updated = bv.apply_admin_html_version(html, '11', '12')
    assert '<title>Retirement System v12 Control Center</title>' in updated
    assert '<h1>Retirement System v12</h1>' in updated


def test_apply_admin_html_version_leaves_cache_buster_query_strings_alone():
    """The ?v=v11-<fix-name> cache buster names a specific past fix, not the
    app version -- it must survive a bump untouched."""
    html = '<script src="js/admin.js?v=v11-pricing-symbol-tester-msg-fix-1"></script>'
    updated = bv.apply_admin_html_version(html, '11', '12')
    assert updated == html


def test_apply_admin_html_version_is_a_no_op_when_phrase_absent():
    html = '<p>Nothing version-related here.</p>'
    assert bv.apply_admin_html_version(html, '11', '12') == html


# --------------------------------------------------------------------------
# Gap 2: check_version_surfaces.py's stale-token check was frozen to v7/v8
# --------------------------------------------------------------------------


def test_dynamic_stale_patterns_catch_the_real_functional_strings():
    patterns = cvs._dynamic_stale_patterns('11')
    import re
    real_hits = [
        'Retirement System v11 Control Center',
        'USER_AGENT = f"RetirementPlanSystem/11 (+local-advisor-tool)"',
        '<span>11</span>',
    ]
    for line in real_hits:
        assert any(re.search(p, line) for p in patterns), f'expected a match against: {line!r}'


def test_dynamic_stale_patterns_do_not_flag_architecture_era_comments():
    """The first draft of this check used a bare \\bv11\\b / Version 11\\b
    token and matched ~50 lines of legitimate prose like "Typed local-only
    plan input domain model for v11" and changelog headers -- exactly the
    false-positive flood this test guards against recurring."""
    import re
    patterns = cvs._dynamic_stale_patterns('11')
    false_positives = [
        'Typed local-only plan input domain model for v11.',
        '# v11 canonical: the typed sectioned snapshot is the sole source of truth.',
        '## v11 Results Explorer semantic model refactor',
        'raise FileNotFoundError("No local v11 plan snapshot exists")',
    ]
    for line in false_positives:
        assert not any(re.search(p, line) for p in patterns), f'unexpected match against: {line!r}'


def test_is_history_doc_excludes_changelog_and_completion_summary_by_name():
    assert cvs._is_history_doc(Path('documentation/GOLDEN_MASTER_CHANGELOG.md'))
    assert cvs._is_history_doc(Path('documentation/F0_F1_F2_COMPLETION_SUMMARY.md'))
    assert not cvs._is_history_doc(Path('documentation/API_CONTRACTS.md'))


def test_check_tests_for_hardcoded_workspace_path_flags_a_real_leak(tmp_path, monkeypatch):
    monkeypatch.setattr(cvs, 'ROOT', tmp_path)
    _write(tmp_path / 'tests' / 'test_something.py', 'PATH = r"C:\\RetirementPlanning\\Version 11\\input"\n')
    errors: list[str] = []
    cvs._check_tests_for_hardcoded_workspace_path('11', errors)
    assert errors, 'expected the hardcoded absolute path to be flagged'
    assert 'test_something.py' in errors[0]


def test_check_tests_for_hardcoded_workspace_path_allowlists_its_own_fixture_file(tmp_path, monkeypatch):
    """test_bump_version_folder_rename.py's own fixtures ARE literal old-path
    strings used to test the sweep -- flagging them would be a false alarm
    on every single run of this checker, forever."""
    monkeypatch.setattr(cvs, 'ROOT', tmp_path)
    _write(
        tmp_path / 'tests' / 'test_bump_version_folder_rename.py',
        'PATH = r"C:\\RetirementPlanning\\Version 11\\input"\n',
    )
    errors: list[str] = []
    cvs._check_tests_for_hardcoded_workspace_path('11', errors)
    assert errors == []


# --------------------------------------------------------------------------
# Gap 3: hardcoded "name_v<N>" filename/schema literals were invisible
# --------------------------------------------------------------------------


def test_detect_hardcoded_version_filenames_finds_the_underscore_convention(tmp_path):
    _write(tmp_path / 'src' / 'config_backend.py', 'DEFAULT_DB = ROOT / "local_state" / "retirement_system_v10.db"\n')
    hits = bv.detect_hardcoded_version_filenames('10', roots=[tmp_path / 'src'])
    assert len(hits) == 1
    assert hits[0][0].name == 'config_backend.py'


def test_detect_hardcoded_version_filenames_does_not_require_a_second_bare_token_on_the_line():
    """Regression for a real bug in this function's first draft: it also
    required a separate bare \\bv10\\b match on the same line, which regex
    \\b can never satisfy immediately after an underscore (a word character),
    so lines with ONLY "retirement_system_v10.db" and no second, separately
    quoted "v10" elsewhere were silently dropped."""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        _write(d / 'thing.py', 'DEFAULT_DB = "local_state/retirement_system_v10.db"\n')
        hits = bv.detect_hardcoded_version_filenames('10', roots=[d])
        assert len(hits) == 1


def test_detect_hardcoded_version_filenames_excludes_its_own_tool_files(tmp_path):
    _write(tmp_path / 'bump_version.py', '# example: "retirement_system_v10.db"\n')
    _write(tmp_path / 'check_version_surfaces.py', '# example: "tax_law_v10"\n')
    hits = bv.detect_hardcoded_version_filenames('10', roots=[tmp_path])
    assert hits == []


def test_detect_hardcoded_version_filenames_ignores_unrelated_version_text(tmp_path):
    """A bare "Version 10" or "v10" with no underscore prefix is a different
    convention (folder name / display string), not this function's job."""
    _write(tmp_path / 'thing.py', 'RELEASE_LABEL = "Retirement System v10"\n')
    hits = bv.detect_hardcoded_version_filenames('10', roots=[tmp_path])
    assert hits == []


# --------------------------------------------------------------------------
# Gap 4: top-level documentation/*.md outside CLAUDE.md fell through the sweep
# --------------------------------------------------------------------------


def test_top_level_doc_md_files_includes_living_docs_and_excludes_history_named_ones(tmp_path):
    doc_dir = tmp_path / 'documentation'
    _write(doc_dir / 'API_CONTRACTS.md', 'living doc\n')
    _write(doc_dir / 'GOLDEN_MASTER_CHANGELOG.md', 'historical\n')
    _write(doc_dir / 'F0_F1_F2_COMPLETION_SUMMARY.md', 'historical\n')
    _write(doc_dir / 'reports' / 'dated_report.md', 'should not be picked up by a top-level glob anyway\n')

    result = {p.name for p in bv._top_level_doc_md_files(doc_dir)}
    assert result == {'API_CONTRACTS.md'}


def test_default_sweep_roots_includes_top_level_docs(tmp_path, monkeypatch):
    monkeypatch.setattr(bv, 'ROOT', tmp_path)
    _write(tmp_path / 'documentation' / 'API_CONTRACTS.md', 'living doc\n')
    _write(tmp_path / 'documentation' / 'GOLDEN_MASTER_CHANGELOG.md', 'historical\n')
    roots = bv._default_sweep_roots()
    doc_paths = {p.name for p in roots if p.suffix == '.md'}
    assert doc_paths == {'API_CONTRACTS.md'}
