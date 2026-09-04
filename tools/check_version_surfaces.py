from __future__ import annotations
import argparse, csv, re, sys
from pathlib import Path

# Same fix as main.py's (2026-09-03) and bump_version.py's (2026-09-04):
# Windows defaults stdout/stderr to cp1252, and this script (run standalone,
# never through main.py's own reconfigure) can otherwise crash on any
# non-cp1252 character it prints -- e.g. a flagged line of source containing
# one, or a future docstring using a Unicode arrow like bump_version.py's did.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.version import VERSION

# Directories/files actually scanned for stale text. Historically only
# src/frontend/tools/system_config.csv -- documentation and tests were
# excluded entirely (see IGNORE_PARTS), which let two real gaps through
# undetected: (1) documentation/*.md files outside CLAUDE.md silently kept
# stale "Version <old>" path text after a bump, and (2) a hardcoded absolute
# "C:\...\Version <old>" path could creep back into a test file with no
# regression guard (this happened for real once -- 33 test files, per
# documentation/GOLDEN_MASTER_CHANGELOG.md). Both are now covered below,
# each with its own narrow allowance for legitimate non-current-version text
# (dated historical docs, and this tool's own fixture-only test file).
USER_SURFACES=[ROOT/'src',ROOT/'frontend',ROOT/'tools',ROOT/'system_config.csv']
IGNORE_PARTS={'documentation','tests'}
ALLOWED_PATTERNS=[r'/api/v8', r'API_NAMESPACE = "v8"', r'test_v8_', r'v8_1', r'v8_2', r'Version 7\.8\.1 correction']

# Fixed historical tokens from the v7->v8 cleanup this script was originally
# written for. Kept permanently as a regression guard against those specific
# strings recurring -- NOT a stand-in for checking the *current* bump, which
# is what --old-version (below) is for.
STALE=[r'v8\.0', r'v8\.1', r'Version 8\.0', r'Version 8\.1', r'Retirement System v8\.0', r'Retirement System v8\.1', r'RetirementPlanSystem/8\.0', r'RetirementPlanSystem/8\.1', r'rs_v78_token', r'LAN_TEST_CHANGE_ME_.*_7_8']

# Documentation files that are dated records of what was true when written --
# rewriting or flagging their historical version mentions would falsify the
# record, not fix a bug. Mirrors bump_version.py's own default-excluded roots
# (see that module's docstring for the reasoning).
DOC_HISTORY_DIRS = {'reports', 'archive'}

# This file's own fixtures are literal old-path strings used to test the
# sweep/rename logic itself -- they are supposed to contain "stale" paths
# forever and must never be flagged as a real leak.
TEST_ALLOWLIST = {'test_bump_version_folder_rename.py', 'test_bump_version_comprehensiveness_regression.py'}

# Top-level documentation/*.md files that are dated records by nature (a
# changelog, a one-time migration's completion summary) even though they
# don't live under documentation/reports/ or documentation/archive/. Same
# reasoning as DOC_HISTORY_DIRS: their historical version mentions are the
# record, not a bug. Matched by filename since new ones follow this same
# naming convention (CHANGELOG, COMPLETION_SUMMARY) rather than needing a
# name added here one at a time.
DOC_HISTORY_NAME_PATTERNS = [r'CHANGELOG', r'COMPLETION_SUMMARY']


def allowed(line: str) -> bool:
    return any(re.search(p, line) for p in ALLOWED_PATTERNS)


def _is_history_doc(path: Path) -> bool:
    return any(re.search(pat, path.name) for pat in DOC_HISTORY_NAME_PATTERNS)


def _top_level_doc_md_files() -> list[Path]:
    """documentation/*.md at the top level only -- not documentation/reports/
    or documentation/archive/ (excluded by directory), and not a changelog or
    completion-summary file living at the top level (excluded by name) --
    both are historical records by design, just not physically filed under
    reports/ or archive/."""
    doc_dir = ROOT / 'documentation'
    if not doc_dir.exists():
        return []
    return sorted(p for p in doc_dir.glob('*.md') if p.is_file() and not _is_history_doc(p))


def _dynamic_stale_patterns(old_version: str) -> list[str]:
    """Patterns specific to the version this bump just moved away from.
    Separate from STALE (which never changes) so a bump from 11->12 actually
    checks for leftover displayed-version text instead of silently passing
    just because no v8-era token happens to remain.

    Deliberately narrow, matching the same discipline as the hand-picked v8
    STALE list above: exact functional version-string formats this codebase
    actually renders to a user or sends as an identifier (the release label,
    the User-Agent string, the index.html version badge), NOT a bare
    ``\\bv11\\b`` or ``Version 11\\b``. A bare token match sounds more
    "comprehensive" but is wrong here -- this codebase uses "v11" throughout
    as an architecture-era label in comments/docstrings ("Typed local-only
    plan input domain model for v11") and changelog headers ("## v11 Results
    Explorer semantic model refactor"), which are accurate historical
    statements about when that code/entry was written, not stale displayed
    version numbers. A first pass with the bare token produced ~50 matches
    against this repo, nearly all of them exactly that kind of false
    positive -- see this function's git history for the actual output.
    """
    v = re.escape(old_version)
    return [
        rf'Retirement System v{v}\b',
        rf'RetirementPlanSystem/{v}\b',
        rf'<span>{v}</span>',
    ]


def _check_user_surfaces(stale_patterns: list[str], errors: list[str]) -> None:
    for base in USER_SURFACES:
        paths = [base] if base.is_file() else list(base.rglob('*'))
        for p in paths:
            if p.resolve() == Path(__file__).resolve():
                continue
            if p.is_dir() or any(part in IGNORE_PARTS for part in p.parts):
                continue
            if p.suffix.lower() in {'.pyc', '.pyo', '.png', '.jpg', '.jpeg', '.ico', '.svg', '.db', '.xlsx', '.pdf', '.zip'}:
                continue
            try:
                text = p.read_text(encoding='utf-8', errors='ignore')
            except Exception:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if allowed(line):
                    continue
                for pat in stale_patterns:
                    if re.search(pat, line):
                        errors.append(f'{p.relative_to(ROOT)}:{i}: stale version token: {line[:140]}')


def _check_top_level_docs(stale_patterns: list[str], errors: list[str]) -> None:
    """documentation/*.md files outside the historical reports/archive
    subdirs -- these are living docs (API contracts, design specs, runbooks),
    not dated records, so a stale version mention here is a real bug."""
    for p in _top_level_doc_md_files():
        try:
            text = p.read_text(encoding='utf-8', errors='ignore')
        except Exception:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if allowed(line):
                continue
            for pat in stale_patterns:
                if re.search(pat, line):
                    errors.append(f'{p.relative_to(ROOT)}:{i}: stale version token in living doc: {line[:140]}')


def _check_tests_for_hardcoded_workspace_path(old_version: str, errors: list[str]) -> None:
    """Regression guard for a real past incident (see
    documentation/GOLDEN_MASTER_CHANGELOG.md): 33 test files once hardcoded
    the absolute "C:\\...\\Version <N>" workspace path, which breaks the
    instant that folder is renamed. tests/ is deliberately NOT part of the
    general sweep (fixture files legitimately contain literal path/version
    strings as test data), so this checks only for the one concrete failure
    mode that actually bit this project before: an absolute path into the
    workspace folder by its old name."""
    tests_dir = ROOT / 'tests'
    if not tests_dir.exists():
        return
    pattern = re.compile(
        r'RetirementPlanning[\\/]{1,2}Version\s+' + re.escape(old_version) + r'\b'
    )
    for p in sorted(tests_dir.rglob('*.py')):
        if p.name in TEST_ALLOWLIST:
            continue
        try:
            text = p.read_text(encoding='utf-8', errors='ignore')
        except Exception:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if pattern.search(line):
                errors.append(
                    f'{p.relative_to(ROOT)}:{i}: hardcoded absolute workspace path '
                    f'(breaks on the next folder rename): {line.strip()[:140]}'
                )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--old-version', default=None,
        help='Also flag leftover references to this version (the one bump_version.py just '
             'moved away from) across USER_SURFACES, top-level documentation/*.md, and '
             'tests/ absolute-path leaks. Omit to run only the fixed historical (v7/v8) check.',
    )
    args = parser.parse_args(argv)

    errors: list[str] = []
    cfg = ROOT / 'system_config.csv'
    if cfg.exists():
        with cfg.open(newline='', encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                if row.get('section') == 'System Configuration' and row.get('subsection') == 'Runtime' and row.get('label') == 'system_version':
                    if str(row.get('value')).strip() != VERSION:
                        errors.append(f'system_config system_version={row.get("value")} expected {VERSION}')

    _check_user_surfaces(STALE, errors)

    if args.old_version:
        dynamic = _dynamic_stale_patterns(args.old_version)
        _check_user_surfaces(dynamic, errors)
        _check_top_level_docs(dynamic, errors)
        _check_tests_for_hardcoded_workspace_path(args.old_version, errors)

    if errors:
        print('VERSION SURFACE CHECK FAILED')
        for e in errors:
            print('- ' + e)
        return 1
    print('VERSION SURFACE CHECK PASSED')
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
