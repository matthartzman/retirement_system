"""Bump the release version across all surfaces in one command.

Usage:
    python tools/bump_version.py 11

What it does:
    1. Updates src/version.py  VERSION = '<new>'
    2. Updates frontend/index.html  <span>OLD</span> → <span>NEW</span>
    3. Updates system_config.csv  system_version,OLD → system_version,NEW
    4. Re-runs tools/check_plan_data_sync.py --write  (regenerates manifest)
    5. Re-runs tools/check_version_surfaces.py  (validates no stale tokens)
    6. Prints a reminder to regenerate tests/fixtures/results_model_v10_contract.json
       if the results model schema changed (run: python -m pytest tests/test_80... -k contract)

Ticket 288 -- optional workspace folder rename
-----------------------------------------------
The workspace folder itself (currently "Version 10") is a separate surface this
script did not know about. Two more flags handle it, deliberately split into a
safe half and a dangerous half:

    --sweep-folder-refs [--apply] [--include-history] [--folder-name NAME]
        Rewrites literal "Version <old>" text across the codebase to the new
        folder name. Dry-run by default -- prints every file and line that
        would change; nothing is written until --apply is also passed. This
        half is ordinary text editing, ships independently of any rename, and
        is exactly as reversible as any other commit (`git checkout --`).

    --rename-folder --apply
        Actually moves the directory on disk. Requires --apply explicitly
        (deliberately not implied by the ordinary sweep --apply, since this
        one can sever an open editor, a running server, or this very worktree
        if run carelessly). Runs preflight checks, then launches a detached
        PowerShell helper and exits immediately -- see rename_folder_out_of_
        process()'s docstring for why an in-process rename cannot work on
        Windows.

Swept vs. excluded roots (decision, not a config default -- read this before
wondering why a report didn't update): historical plans and dated review
reports are records of what was true when they were written; rewriting a `cd
"C:/.../Version 10"` command inside a 2026-07-18 report would falsify that
record, not fix it. So the default sweep covers only roots where a stale path
is a live bug, not a historical fact:

    Swept by default:   src/, frontend/, tools/, launchers/, .claude/,
                         documentation/CLAUDE.md
    Excluded by default: documentation/reports/, documentation/archive/,
                         docs/superpowers/plans/, dist/, build/, node_modules/,
                         output/, saved_plans/

--include-history adds the three excluded documentation roots back in, for the
rare case where every historical path genuinely should move too.

Manual verification checklist (NOT run in CI -- an integration test here would
move the checkout the test runner is executing out from under itself):
    1. python tools/bump_version.py <N> --sweep-folder-refs --apply
    2. Review the diff, commit it.
    3. python tools/bump_version.py <N> --rename-folder --apply
       (or re-run with just --rename-folder --apply once the version bump and
       sweep are already committed, since bump()/sweep are idempotent no-ops
       once applied)
    4. Confirm the folder moved to the new path.
    5. Relaunch via <new path>\\launchers\\START_APP.bat -- confirm the app boots.
    6. Confirm tools/backup_to_onedrive.py writes its archive under the new
       "Version <N>" prefix, not the old one.
    7. Re-run tools/INSTALL_DESKTOP_ICON.py from the new location -- the old
       desktop shortcut holds an absolute path into the now-gone folder.
"""
from __future__ import annotations
import argparse, os, re, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Same binary-suffix skip list as check_version_surfaces.py:26 -- a folder-name
# sweep has no more business rewriting a .db or .xlsx than a version sweep does.
BINARY_SUFFIXES = {'.pyc', '.pyo', '.png', '.jpg', '.jpeg', '.ico', '.svg', '.db', '.xlsx', '.pdf', '.zip'}

# Step 6.1's "safe half" -- ships independently of any rename. Kept separate
# from the "excluded" roots below: this list IS the sweep; the exclusions are
# just what --include-history adds back in, not a second filter on top of it.
DEFAULT_SWEEP_ROOTS = [
    ROOT / 'src',
    ROOT / 'frontend',
    ROOT / 'tools',
    ROOT / 'launchers',
    ROOT / '.claude',
    ROOT / 'documentation' / 'CLAUDE.md',
]

# Added to the sweep only when --include-history is passed. Excluded by
# default because these are dated records of what was true at the time --
# see the module docstring.
HISTORY_ROOTS = [
    ROOT / 'documentation' / 'reports',
    ROOT / 'documentation' / 'archive',
    ROOT / 'docs' / 'superpowers' / 'plans',
]


def fail(msg: str) -> None:
    print(f'ERROR: {msg}', file=sys.stderr)
    sys.exit(1)


def bump(new_version: str) -> str | None:
    """Bump the version across the usual surfaces. Returns the OLD version string
    (needed by --sweep-folder-refs/--rename-folder to know what to rewrite), or
    None if already at the target version and nothing was done."""
    new_version = new_version.strip()
    if not re.fullmatch(r'\d+', new_version):
        fail(f'Version must be a plain integer (e.g. 11), got: {new_version!r}')

    # 1. Read current version
    version_py = ROOT / 'src' / 'version.py'
    text = version_py.read_text(encoding='utf-8')
    m = re.search(r"VERSION\s*=\s*'(\d+)'", text)
    if not m:
        fail(f'Could not find VERSION = \'...\' in {version_py}')
    old_version = m.group(1)
    if old_version == new_version:
        print(f'Already at version {new_version}. Nothing to do.')
        return None
    print(f'Bumping {old_version} → {new_version}')

    # 2. src/version.py
    new_text = re.sub(r"VERSION\s*=\s*'\d+'", f"VERSION = '{new_version}'", text)
    version_py.write_text(new_text, encoding='utf-8')
    print(f'  updated {version_py.relative_to(ROOT)}')

    # 3. frontend/index.html
    html_path = ROOT / 'frontend' / 'index.html'
    html = html_path.read_text(encoding='utf-8')
    updated_html = html.replace(f'<span>{old_version}</span>', f'<span>{new_version}</span>')
    if updated_html == html:
        print(f'  WARNING: <span>{old_version}</span> not found in index.html — update manually')
    else:
        html_path.write_text(updated_html, encoding='utf-8')
        print(f'  updated {html_path.relative_to(ROOT)}')

    # 4. system_config.csv
    csv_path = ROOT / 'system_config.csv'
    csv_text = csv_path.read_text(encoding='utf-8')
    updated_csv = re.sub(
        r'(system_version,)' + re.escape(old_version),
        r'\g<1>' + new_version,
        csv_text,
    )
    if updated_csv == csv_text:
        print(f'  WARNING: system_version,{old_version} not found in system_config.csv — update manually')
    else:
        csv_path.write_text(updated_csv, encoding='utf-8')
        print(f'  updated {csv_path.relative_to(ROOT)}')

    # 5. Re-generate plan data manifest
    print('\nRegenerating plan data manifest...')
    r = subprocess.run(
        [sys.executable, 'tools/check_plan_data_sync.py', '--write'],
        cwd=ROOT, text=True, capture_output=True,
    )
    print(r.stdout.strip())
    if r.returncode != 0:
        print(r.stderr.strip(), file=sys.stderr)
        fail('check_plan_data_sync.py --write failed')

    # 6. Validate version surfaces
    print('\nValidating version surfaces...')
    r = subprocess.run(
        [sys.executable, 'tools/check_version_surfaces.py'],
        cwd=ROOT, text=True, capture_output=True,
    )
    print(r.stdout.strip())
    if r.returncode != 0:
        print(r.stderr.strip(), file=sys.stderr)
        fail('check_version_surfaces.py found stale tokens — fix them and re-run')

    print(f'\nDone. Version is now {new_version}.')
    print('Next steps:')
    print('  • If the results model schema changed, regenerate the contract fixture:')
    print('      python -m pytest tests/test_detailed_results_ui_functional.py -k contract -s')
    print('  • Commit all changed files.')
    return old_version


# --------------------------------------------------------------------------
# Step 6.1 -- reference sweep
# --------------------------------------------------------------------------

def sweep_folder_references(
    old_name: str,
    new_name: str,
    *,
    roots: list[Path] | None = None,
    include_history: bool = False,
    apply: bool = False,
) -> dict[Path, list[tuple[int, str, str]]]:
    """Rewrite every literal occurrence of ``old_name`` to ``new_name`` across the
    allowlisted roots. Returns ``{path: [(line_no, old_line, new_line), ...]}``
    for every file that changed (or would change, if ``apply`` is False).

    Plain substring replacement, not regex -- ``old_name`` is a fixed string
    like "Version 10", and a substring match against "Version 10 - ChatpGPT"
    naturally leaves the " - ChatpGPT" suffix untouched without any special
    casing (the suffix is simply outside the matched span). This also means
    the deliberate "ChatpGPT" typo in that suffix is preserved verbatim,
    exactly as the ticket requires -- correcting it is a different ticket.

    Skips the same binary suffixes check_version_surfaces.py does, and any
    file that fails to decode as UTF-8 (never crash a sweep on a stray binary
    the suffix list didn't anticipate).
    """
    swept_roots = list(roots) if roots is not None else list(DEFAULT_SWEEP_ROOTS)
    if include_history:
        swept_roots += HISTORY_ROOTS

    report: dict[Path, list[tuple[int, str, str]]] = {}
    for base in swept_roots:
        if not base.exists():
            continue
        paths = [base] if base.is_file() else list(base.rglob('*'))
        for p in paths:
            if p.is_dir():
                continue
            if p.suffix.lower() in BINARY_SUFFIXES:
                continue
            try:
                text = p.read_text(encoding='utf-8')
            except (UnicodeDecodeError, OSError):
                continue
            if old_name not in text:
                continue
            new_text = text.replace(old_name, new_name)
            old_lines = text.splitlines()
            new_lines = new_text.splitlines()
            changed = [
                (i + 1, ol, nl)
                for i, (ol, nl) in enumerate(zip(old_lines, new_lines))
                if ol != nl
            ]
            report[p] = changed
            if apply:
                p.write_text(new_text, encoding='utf-8')
    return report


def print_sweep_report(report: dict[Path, list[tuple[int, str, str]]], applied: bool) -> None:
    if not report:
        print('No references found -- nothing to change.')
        return
    verb = 'Changed' if applied else 'Would change'
    for path, changes in sorted(report.items()):
        rel = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
        print(f'{verb} {rel} ({len(changes)} line(s)):')
        for line_no, old_line, new_line in changes:
            print(f'    {line_no}: {old_line.strip()!r} -> {new_line.strip()!r}')
    if not applied:
        print(f'\n{len(report)} file(s) would change. Re-run with --apply to write them.')
    else:
        print(f'\n{len(report)} file(s) updated.')


# --------------------------------------------------------------------------
# Step 6.2 -- preflight
# --------------------------------------------------------------------------

def _default_git_status_dirty(root: Path) -> bool:
    r = subprocess.run(
        ['git', 'status', '--porcelain'], cwd=root, text=True, capture_output=True,
    )
    return bool(r.stdout.strip())


def _default_list_blocking_processes(root: Path) -> list[str]:
    """Processes whose executable or command line path into ``root``. Uses
    PowerShell's CIM process table rather than plain tasklist, since only CIM
    exposes CommandLine/ExecutablePath for matching a path substring."""
    root_str = str(root)
    ps = (
        'Get-CimInstance Win32_Process | '
        f'Where-Object {{ ($_.ExecutablePath -and $_.ExecutablePath -like "{root_str}*") -or '
        f'($_.CommandLine -and $_.CommandLine -like "*{root_str}*") }} | '
        'ForEach-Object { "$($_.ProcessId):$($_.Name)" }'
    )
    r = subprocess.run(
        ['powershell', '-NoProfile', '-Command', ps],
        text=True, capture_output=True,
    )
    if r.returncode != 0:
        # Can't determine -- fail open on the side of NOT blocking a rename
        # over a PowerShell error; the rename script's own retry loop and
        # Move-Item failure message are the real backstop.
        return []
    return [line.strip() for line in r.stdout.splitlines() if line.strip()]


def _default_db_handle_open(root: Path) -> bool:
    """Best-effort probe: on Windows, renaming a file to itself fails with
    PermissionError if another process holds an incompatible handle on it.
    Not airtight (a handle opened with FILE_SHARE_DELETE would not trip this),
    but catches the common case -- the app or a stray script has the DB open --
    which is exactly what this preflight exists to warn about."""
    db = root / 'local_state' / 'retirement_system_v10.db'
    if not db.exists():
        return False
    try:
        os.rename(db, db)
        return False
    except OSError:
        return True


def preflight_folder_rename(
    root: Path,
    new_path: Path,
    *,
    git_status_dirty_fn=None,
    process_lister_fn=None,
    db_handle_probe_fn=None,
) -> list[str]:
    """Returns a list of human-readable blocker messages; empty means clear to
    proceed. Every check is behind an injectable function so this can be unit-
    tested with fakes instead of touching real git/PowerShell/the filesystem's
    lock state -- see tests/test_bump_version_folder_rename.py."""
    git_status_dirty_fn = git_status_dirty_fn or _default_git_status_dirty
    process_lister_fn = process_lister_fn or _default_list_blocking_processes
    db_handle_probe_fn = db_handle_probe_fn or _default_db_handle_open

    blockers: list[str] = []

    if git_status_dirty_fn(root):
        blockers.append(
            'The git tree is dirty. Commit or stash before renaming -- a rename '
            'mid-edit makes it hard to tell what changed from where.'
        )

    if new_path.exists():
        blockers.append(f'Target folder already exists: {new_path}')

    procs = process_lister_fn(root)
    if procs:
        names = ', '.join(procs)
        blockers.append(
            f'Process(es) running out of this tree: {names}. Close them first -- a VS '
            'Code window with this folder open, a terminal cd\'d here, or the running '
            'app itself are the most likely culprits and will otherwise turn a rename '
            'into a confusing partial failure.'
        )

    if db_handle_probe_fn(root):
        blockers.append(
            'local_state/retirement_system_v10.db appears to have an open handle. '
            'Close the running app (or whatever else has the plan open) first.'
        )

    return blockers


# --------------------------------------------------------------------------
# Step 6.3 -- out-of-process rename
# --------------------------------------------------------------------------

def _build_rename_script(pid: int, root: Path, new_path: Path) -> str:
    """Pure string-builder, unit-testable without launching anything. The
    script waits for the parent PID to exit (bounded ~30s, so a hung parent
    can't wedge it forever), moves the folder, and self-deletes either way.

    On failure it deliberately does NOT try to roll back a folder-reference
    sweep that already ran -- that sweep is a normal commit, and telling the
    user to `git checkout --` it is more reliable than a half-written undo
    path racing against whatever caused Move-Item to fail in the first place.
    """
    return (
        '$ErrorActionPreference = "Stop"\n'
        f'$parentPid = {pid}\n'
        f'$root = "{root}"\n'
        f'$newPath = "{new_path}"\n'
        '$deadline = (Get-Date).AddSeconds(30)\n'
        'while ((Get-Date) -lt $deadline) {\n'
        '    $p = Get-Process -Id $parentPid -ErrorAction SilentlyContinue\n'
        '    if (-not $p) { break }\n'
        '    Start-Sleep -Milliseconds 250\n'
        '}\n'
        'try {\n'
        '    Move-Item -Path $root -Destination $newPath -ErrorAction Stop\n'
        '    Write-Host "Renamed to: $newPath"\n'
        '    Write-Host "The old desktop shortcut holds an absolute path into the folder '
        'that no longer exists there -- re-run tools\\INSTALL_DESKTOP_ICON.py from the new '
        'location to refresh it."\n'
        '    Write-Host "Relaunch with: $newPath\\launchers\\START_APP.bat"\n'
        '} catch {\n'
        '    Write-Host "Rename FAILED: $_"\n'
        '    Write-Host "Nothing was moved. If a reference sweep already ran and was '
        'committed, that commit is untouched -- `git checkout --` in the original '
        'location reverts it if you want to undo the whole attempt."\n'
        '}\n'
        'Remove-Item -Path $MyInvocation.MyCommand.Path -Force -ErrorAction SilentlyContinue\n'
    )


def rename_folder_out_of_process(root: Path, new_path: Path) -> None:
    """Launch a detached PowerShell helper that waits for this process to exit,
    then moves ``root`` to ``new_path``, and exit immediately.

    Why out-of-process at all: on Windows a process cannot rename a directory
    that is its own current working directory, or that holds any open file
    handle underneath it (and this interpreter's own module-loading machinery,
    plus anything this script imported from ROOT, can pin such a handle). The
    only reliable way to release every handle this process holds on ``root``
    is for the process to actually exit -- so the rename has to happen in a
    process that outlives this one, and this one has to get out of the way.
    """
    script = _build_rename_script(os.getpid(), root, new_path)
    script_path = Path(tempfile.gettempdir()) / f'bump_version_rename_{os.getpid()}.ps1'
    script_path.write_text(script, encoding='utf-8')

    DETACHED_PROCESS = 0x00000008
    CREATE_NEW_PROCESS_GROUP = 0x00000200
    subprocess.Popen(
        ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(script_path)],
        creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
        cwd=str(Path(tempfile.gettempdir())),  # not root -- avoid pinning a handle on it
    )
    print(f'Launched detached rename helper: {script_path}')
    print(f'This process is exiting now so its handle on {root} is released.')
    print(f'Watch for the PowerShell window/output to confirm the move to {new_path}.')
    sys.exit(0)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('new_version')
    parser.add_argument(
        '--folder-name', default=None,
        help='New workspace folder name. Default: "Version <new_version>".',
    )
    parser.add_argument(
        '--sweep-folder-refs', action='store_true',
        help='Also rewrite "Version <old>" text references (see module docstring for scope).',
    )
    parser.add_argument(
        '--include-history', action='store_true',
        help='Also sweep documentation/reports, documentation/archive, docs/superpowers/plans.',
    )
    parser.add_argument(
        '--apply', action='store_true',
        help='Write the folder-reference sweep. Without this, --sweep-folder-refs only reports.',
    )
    parser.add_argument(
        '--rename-folder', action='store_true',
        help='Run preflight checks and rename the workspace folder out-of-process. Requires --apply.',
    )
    return parser


def main(argv: list[str]) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    old_version = bump(args.new_version)

    wants_folder_work = args.sweep_folder_refs or args.rename_folder
    if not wants_folder_work:
        return 0

    if old_version is None:
        fail(
            'Already at this version, so there is no "Version <old>" to sweep or rename '
            'from. Re-run without --sweep-folder-refs/--rename-folder, or bump to a new '
            'version number first.'
        )

    old_name = f'Version {old_version}'
    new_name = args.folder_name or f'Version {args.new_version}'

    if args.sweep_folder_refs:
        print(f'\nSweeping folder references: {old_name!r} -> {new_name!r}')
        report = sweep_folder_references(
            old_name, new_name, include_history=args.include_history, apply=args.apply,
        )
        print_sweep_report(report, applied=args.apply)

    if args.rename_folder:
        if not args.apply:
            fail('--rename-folder requires --apply -- this is the step that actually moves the folder.')
        new_path = ROOT.parent / new_name
        print(f'\nPreflight for renaming {ROOT} -> {new_path}')
        blockers = preflight_folder_rename(ROOT, new_path)
        if blockers:
            print('Refusing to rename -- blocked by:', file=sys.stderr)
            for b in blockers:
                print(f'  - {b}', file=sys.stderr)
            return 1
        print('Preflight clear. Launching detached rename...')
        rename_folder_out_of_process(ROOT, new_path)  # exits the process on success

    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
