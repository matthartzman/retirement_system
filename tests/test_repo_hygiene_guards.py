"""Two repo-hygiene guards, both added after a real incident on a pushed branch.

Origin (2026-08-12, branch `claude/clever-cannon-05accc`, never merged): a
single commit labelled "Fix EOL conversion issues in codemod" actually carried
an aborted `git stash pop` straight into production code plus the live
household plan data. Specifically:

  * 16 unresolved conflict-marker lines across src/planning_engines.py,
    src/projection_stages/deterministic_engine.py and
    src/reporting/sheets_stress.py. planning_engines.py did not even parse
    (`SyntaxError`), and the "Stashed changes" side silently deleted
    sustainable_spending_solve() and its call sites.

  * input/client_data.json and input/client_data.yaml (2,164 lines of real
    dob / name / balance_today / per-member 401k-HSA-IRA-Roth-Trust account
    policy) force-added past .gitignore's `/input/*` rule, plus a
    metrics_dump.json debug artifact at the repo root.

Neither class had a guard. The CI workflow's "Fail if the test suite mutated
input/" step is a `git diff --exit-code -- input/`, which catches a test
MUTATING a tracked input file -- it cannot see a brand-new ignored file being
force-ADDED, because after the commit there is nothing left to diff.

Why these live here as tests rather than as extra CI steps: CI already runs
`pytest tests/`, so a test gets the same gate for free while also failing
locally, before the push that is the actual damage. For the data half that
distinction is the whole point -- once ignored financial data reaches a remote,
deleting the branch does not reliably purge it, since the commit stays
reachable by SHA until GitHub garbage-collects.

Both guards are structural (does this file exist / does this line appear), not
behavioural, so they are outside what test_freeze_frontend_source_grep.py
freezes.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# Only the opening and closing markers, each 7 characters plus a space and then
# content ("<<<<<<< Updated upstream", ">>>>>>> Stashed changes", or a branch
# name / SHA). The bare `=======` middle marker is deliberately NOT matched on
# its own: it is indistinguishable from a decorative separator line in Markdown
# and in this repo's own comment banners, and a real committed conflict always
# brings an opening and closing marker with it.
CONFLICT_MARKER_RE = r"^(<<<<<<<|>>>>>>>) \S"


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


@pytest.fixture(scope="module")
def git_available() -> None:
    if not (ROOT / ".git").exists():
        pytest.skip("not a git checkout (packaged release or exported tree)")
    if _git("rev-parse", "--git-dir").returncode != 0:
        pytest.skip("git is unavailable in this environment")


def test_no_unresolved_conflict_markers_in_tracked_files(git_available: None) -> None:
    """An aborted merge/rebase/stash-pop must never reach a commit.

    `git grep -I` skips binary files. Scoped to tracked files only, so an
    untracked scratch file in a working tree cannot fail the suite.
    """
    result = _git("grep", "-I", "-n", "-E", CONFLICT_MARKER_RE, "--", ".")

    # git grep exits 1 with empty stdout when there are no matches, which is the
    # passing case; anything above 1 is a real git failure worth surfacing.
    if result.returncode > 1:
        pytest.skip(f"git grep failed: {result.stderr.strip()}")

    hits = [
        line
        for line in result.stdout.splitlines()
        # This file necessarily contains the marker pattern as a string literal.
        if not line.startswith(f"{Path(__file__).name}:")
        and not line.startswith(f"tests/{Path(__file__).name}:")
    ]
    assert not hits, (
        "Unresolved conflict markers found in tracked files. Finish the merge "
        "or stash-pop before committing:\n  " + "\n  ".join(hits)
    )


def test_no_tracked_file_is_gitignored(git_available: None) -> None:
    """Nothing tracked may be a file .gitignore claims to exclude.

    This is the force-add guard. `/input/*` exists precisely because input/
    holds real financial data, and `git add -f` overrides it without warning.
    A file that is both tracked and ignored is therefore either leaked private
    data or a build artifact that should never have been committed.

    --no-index makes check-ignore evaluate the ignore rules against every path
    handed to it, instead of short-circuiting to "not ignored" for paths that
    are already in the index -- which is exactly the case being tested.
    """
    tracked = _git("ls-files", "-z")
    if tracked.returncode != 0:
        pytest.skip(f"git ls-files failed: {tracked.stderr.strip()}")

    check = subprocess.run(
        ["git", "check-ignore", "--stdin", "-z", "--no-index"],
        cwd=ROOT,
        input=tracked.stdout,
        capture_output=True,
        text=True,
    )
    if check.returncode > 1:
        pytest.skip(f"git check-ignore failed: {check.stderr.strip()}")

    offenders = [path for path in check.stdout.split("\0") if path]
    assert not offenders, (
        "These files are tracked but .gitignore excludes them, so they were "
        "force-added. If any hold private data, removing them from HEAD is not "
        "enough -- the blobs stay reachable in history:\n  "
        + "\n  ".join(offenders)
    )
