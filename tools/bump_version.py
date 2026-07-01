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
"""
from __future__ import annotations
import re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fail(msg: str) -> None:
    print(f'ERROR: {msg}', file=sys.stderr)
    sys.exit(1)


def bump(new_version: str) -> None:
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
        return
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
    print('      python -m pytest tests/test_80_detailed_results_ui.py -k contract -s')
    print('  • Commit all changed files.')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    bump(sys.argv[1])
