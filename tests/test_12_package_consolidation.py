from pathlib import Path
import py_compile

ROOT = Path(__file__).resolve().parents[1]


def test_release_notes_are_under_documentation_release_notes():
    root_notes = list(ROOT.glob('RELEASE_NOTES*.md'))
    assert root_notes == []
    notes_dir = ROOT / 'documentation' / 'release_notes'
    assert notes_dir.exists()


def test_readmes_are_under_documentation_readme():
    # .claude/worktrees holds full parallel checkouts for other Claude Code
    # sessions; each has its own documentation/readme/ copy that is out of
    # scope for this project's own README-location policy.
    outside = [p.relative_to(ROOT) for p in ROOT.rglob('*README*.md') if '.pytest_cache' not in p.parts and 'input' not in p.parts and 'dist' not in p.parts and 'worktrees' not in p.parts and not p.is_relative_to(ROOT / 'documentation' / 'readme')]
    assert outside == []
    assert (ROOT / 'documentation' / 'readme' / 'README.md').exists()
    assert (ROOT / 'documentation' / 'readme' / 'CLEAN_PACKAGE_README.md').exists()


def test_launchers_and_desktop_installer_are_consolidated_under_tools():
    forbidden_root = [
        'START_UI.py', 'START_SERVER.py', 'START_UI.command', 'START_SERVER.command',
        'START_SERVER.sh', 'START_SERVER.bat', 'start_ui.bat', 'start_ui.sh',
        'start_wsgi_server.bat', 'start_wsgi_server.sh', 'RESET_TO_LOCAL_MODE.bat',
        'RESET_TO_LOCAL_MODE.sh', 'INSTALL_DESKTOP_ICON.py',
    ]
    assert [name for name in forbidden_root if (ROOT / name).exists()] == []
    for rel in [
        'tools/launchers/START_UI.py',
        'tools/launchers/START_SERVER.py',
        'tools/launchers/start_ui.bat',
        'tools/launchers/start_wsgi_server.sh',
        'tools/INSTALL_DESKTOP_ICON.py',
    ]:
        assert (ROOT / rel).exists(), rel


def test_moved_python_launchers_compile_and_use_package_root():
    for rel in ['tools/launchers/START_UI.py', 'tools/launchers/START_SERVER.py', 'tools/INSTALL_DESKTOP_ICON.py']:
        py_compile.compile(str(ROOT / rel), doraise=True)
    icon_text = (ROOT / 'tools' / 'INSTALL_DESKTOP_ICON.py').read_text(encoding='utf-8')
    assert "START_DESKTOP.py" in icon_text
