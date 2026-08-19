"""Ticket 288: bump_version.py's folder-reference sweep and rename preflight.

Two things this file deliberately does NOT do, both per the ticket's own
Step 6.4:
  - It never calls rename_folder_out_of_process() for real -- that function
    launches a detached PowerShell process and calls sys.exit(0), which would
    kill the test runner. Only its pure string-builder half
    (_build_rename_script) is exercised.
  - It never runs the actual Move-Item against this checkout. All rename
    tests are against temp directories the test creates and owns.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tools.bump_version as bv  # noqa: E402


# --------------------------------------------------------------------------
# sweep_folder_references
# --------------------------------------------------------------------------


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def test_sweep_rewrites_the_allowlisted_file(tmp_path):
    swept = tmp_path / 'src' / 'thing.py'
    _write(swept, "PATH = r'C:\\RetirementPlanning\\Version 10\\input'\n")

    report = bv.sweep_folder_references(
        'Version 10', 'Version 11', roots=[tmp_path / 'src'], apply=True,
    )

    assert swept in report
    assert 'Version 11' in swept.read_text(encoding='utf-8')
    assert 'Version 10' not in swept.read_text(encoding='utf-8')


def test_sweep_dry_run_reports_without_writing(tmp_path):
    swept = tmp_path / 'src' / 'thing.py'
    original = "PATH = 'Version 10'\n"
    _write(swept, original)

    report = bv.sweep_folder_references(
        'Version 10', 'Version 11', roots=[tmp_path / 'src'], apply=False,
    )

    assert swept in report
    assert swept.read_text(encoding='utf-8') == original, 'dry run must not write'


def test_sweep_leaves_a_report_root_untouched(tmp_path):
    """The exclusion decision, exercised directly: a caller that does not pass
    a documentation/reports-style root in `roots` gets no changes there, even
    if such a file exists on disk with the old name in it."""
    report_dir = tmp_path / 'documentation' / 'reports'
    report_file = report_dir / 'SYSTEM_REVIEW_2026-07-18.md'
    _write(report_file, 'cd "C:/RetirementPlanning/Version 10"\n')
    swept = tmp_path / 'src' / 'thing.py'
    _write(swept, 'Version 10\n')

    report = bv.sweep_folder_references(
        'Version 10', 'Version 11', roots=[tmp_path / 'src'], apply=True,
    )

    assert swept in report
    assert report_file not in report
    assert 'Version 10' in report_file.read_text(encoding='utf-8'), (
        'a root not passed to sweep_folder_references must never be touched'
    )


def test_sweep_skips_binary_suffixes(tmp_path):
    binary = tmp_path / 'src' / 'icon.ico'
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_bytes(b'Version 10' + bytes(range(256)))

    report = bv.sweep_folder_references(
        'Version 10', 'Version 11', roots=[tmp_path / 'src'], apply=True,
    )

    assert binary not in report
    assert binary.read_bytes().startswith(b'Version 10'), 'binary file was rewritten'


def test_sweep_preserves_the_chatpgpt_suffix_verbatim(tmp_path):
    """The specific wrinkle the brief calls out: documentation/CLAUDE.md says
    "Version 10 - ChatpGPT", not bare "Version 10". Plain substring replacement
    must rewrite only the "Version 10" prefix and leave " - ChatpGPT" -- typo
    included -- exactly as it was; correcting the typo is a different ticket."""
    claude_md = tmp_path / 'documentation' / 'CLAUDE.md'
    _write(claude_md, 'Workspace: C:\\RetirementPlanning\\Version 10 - ChatpGPT\n')

    report = bv.sweep_folder_references(
        'Version 10', 'Version 11', roots=[tmp_path / 'documentation' / 'CLAUDE.md'], apply=True,
    )

    text = claude_md.read_text(encoding='utf-8')
    assert 'Version 11 - ChatpGPT' in text, 'suffix was not preserved after the new name'
    assert 'Version 10' not in text
    assert 'ChatpGPT' in text, 'the existing typo must be preserved verbatim, not corrected'
    assert report[claude_md] == [(1, 'Workspace: C:\\RetirementPlanning\\Version 10 - ChatpGPT',
                                   'Workspace: C:\\RetirementPlanning\\Version 11 - ChatpGPT')]


def test_sweep_include_history_adds_the_excluded_roots(tmp_path, monkeypatch):
    report_file = tmp_path / 'documentation' / 'reports' / 'SOME_REPORT.md'
    _write(report_file, 'Version 10\n')
    monkeypatch.setattr(bv, 'HISTORY_ROOTS', [tmp_path / 'documentation' / 'reports'])

    without = bv.sweep_folder_references('Version 10', 'Version 11', roots=[], include_history=False)
    with_history = bv.sweep_folder_references('Version 10', 'Version 11', roots=[], include_history=True)

    assert report_file not in without
    assert report_file in with_history


# --------------------------------------------------------------------------
# preflight_folder_rename -- all real dependencies faked, per Step 6.4
# --------------------------------------------------------------------------


def test_preflight_clear_when_everything_is_fine(tmp_path):
    blockers = bv.preflight_folder_rename(
        tmp_path / 'root', tmp_path / 'new',
        git_status_dirty_fn=lambda root: False,
        process_lister_fn=lambda root: [],
        db_handle_probe_fn=lambda root: False,
    )
    assert blockers == []


def test_preflight_blocks_on_dirty_git_tree(tmp_path):
    blockers = bv.preflight_folder_rename(
        tmp_path / 'root', tmp_path / 'new',
        git_status_dirty_fn=lambda root: True,
        process_lister_fn=lambda root: [],
        db_handle_probe_fn=lambda root: False,
    )
    assert any('dirty' in b.lower() for b in blockers)


def test_preflight_blocks_when_target_already_exists(tmp_path):
    existing = tmp_path / 'new'
    existing.mkdir()
    blockers = bv.preflight_folder_rename(
        tmp_path / 'root', existing,
        git_status_dirty_fn=lambda root: False,
        process_lister_fn=lambda root: [],
        db_handle_probe_fn=lambda root: False,
    )
    assert any('already exists' in b for b in blockers)


def test_preflight_blocks_and_names_a_running_process(tmp_path):
    blockers = bv.preflight_folder_rename(
        tmp_path / 'root', tmp_path / 'new',
        git_status_dirty_fn=lambda root: False,
        process_lister_fn=lambda root: ['4321:Code.exe'],
        db_handle_probe_fn=lambda root: False,
    )
    assert any('4321:Code.exe' in b for b in blockers), (
        'the blocker must NAME the process, not just say "something is running" -- '
        '"rename failed" with no name sends the user hunting, per the brief'
    )


def test_preflight_blocks_on_open_db_handle(tmp_path):
    blockers = bv.preflight_folder_rename(
        tmp_path / 'root', tmp_path / 'new',
        git_status_dirty_fn=lambda root: False,
        process_lister_fn=lambda root: [],
        db_handle_probe_fn=lambda root: True,
    )
    assert any('handle' in b.lower() for b in blockers)


def test_preflight_reports_every_blocker_at_once(tmp_path):
    """A user should not have to run this five times to discover five problems."""
    existing = tmp_path / 'new'
    existing.mkdir()
    blockers = bv.preflight_folder_rename(
        tmp_path / 'root', existing,
        git_status_dirty_fn=lambda root: True,
        process_lister_fn=lambda root: ['111:python.exe'],
        db_handle_probe_fn=lambda root: True,
    )
    assert len(blockers) == 4


def test_default_db_handle_probe_detects_no_lock_when_file_absent(tmp_path):
    assert bv._default_db_handle_open(tmp_path) is False


def test_default_db_handle_probe_is_false_when_unlocked(tmp_path):
    db = tmp_path / 'local_state' / 'retirement_system_v10.db'
    db.parent.mkdir(parents=True)
    db.write_bytes(b'not a real sqlite file, just needs to exist')
    assert bv._default_db_handle_open(tmp_path) is False


# --------------------------------------------------------------------------
# _build_rename_script -- pure string builder; the only part of the actual
# rename mechanism this test file is allowed to exercise (see module docstring)
# --------------------------------------------------------------------------


def test_rename_script_waits_for_parent_pid():
    script = bv._build_rename_script(12345, Path('C:/old'), Path('C:/new'))
    assert '$parentPid = 12345' in script
    assert 'Get-Process -Id $parentPid' in script


def test_rename_script_moves_and_reports_success():
    script = bv._build_rename_script(1, Path('C:/old'), Path('C:/new'))
    assert 'Move-Item -Path $root -Destination $newPath' in script
    assert 'Renamed to: $newPath' in script


def test_rename_script_mentions_install_desktop_icon_on_success():
    script = bv._build_rename_script(1, Path('C:/old'), Path('C:/new'))
    assert 'INSTALL_DESKTOP_ICON.py' in script


def test_rename_script_does_not_attempt_rollback_on_failure():
    """The brief is explicit: do not roll back the reference sweep on rename
    failure. This asserts the negative -- no `git checkout` or `git revert`
    machinery appears in the generated script -- and the positive: it tells
    the user how to revert manually instead."""
    script = bv._build_rename_script(1, Path('C:/old'), Path('C:/new'))
    assert 'git checkout' not in script.lower().replace('`git checkout --`', '')
    # The instruction to the user is present even though the script itself
    # doesn't run it:
    assert 'git checkout --' in script
    assert 'Rename FAILED' in script


def test_rename_script_self_deletes():
    script = bv._build_rename_script(1, Path('C:/old'), Path('C:/new'))
    assert 'Remove-Item -Path $MyInvocation.MyCommand.Path' in script


def test_rename_script_is_bounded_not_infinite():
    script = bv._build_rename_script(1, Path('C:/old'), Path('C:/new'))
    assert 'AddSeconds(30)' in script, 'the wait for the parent PID must be bounded'


# --------------------------------------------------------------------------
# CLI wiring
# --------------------------------------------------------------------------


def test_rename_folder_without_apply_fails_fast(tmp_path, monkeypatch, capsys):
    """--rename-folder must require --apply -- this is the step that actually
    moves the folder, so it must not be reachable via the sweep's --apply
    alone.

    preflight_folder_rename and rename_folder_out_of_process are BOTH faked --
    the first to always report clear, the second to raise if it is ever
    reached -- so this test fails for the right reason (the --apply gate is
    what stops it) regardless of whatever git/process state this worktree
    happens to be in when the suite runs. Without those fakes, an earlier
    version of this test "passed" only because the real preflight incidentally
    found this worktree dirty -- which would not have caught the same defect
    on a clean tree."""
    monkeypatch.setattr(bv, 'bump', lambda v: '10')
    monkeypatch.setattr(bv, 'preflight_folder_rename', lambda root, new_path: [])

    def _must_not_be_reached(root, new_path):
        raise AssertionError('rename_folder_out_of_process must not run without --apply')

    monkeypatch.setattr(bv, 'rename_folder_out_of_process', _must_not_be_reached)

    with pytest.raises(SystemExit) as exc:
        bv.main(['11', '--rename-folder'])
    assert exc.value.code != 0
    assert 'requires --apply' in capsys.readouterr().err


def test_folder_work_without_a_version_change_fails_with_a_clear_message(monkeypatch, capsys):
    monkeypatch.setattr(bv, 'bump', lambda v: None)  # already at target version
    with pytest.raises(SystemExit):
        bv.main(['11', '--sweep-folder-refs'])
    assert 'Already at this version' in capsys.readouterr().err
