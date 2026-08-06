from pathlib import Path
from src.version import VERSION


def test_v11_version_surfaces_are_v11():
    index = Path('frontend/index.html').read_text(encoding='utf-8')
    assert 'Version' in index
    assert f'<span>{VERSION}</span>' in index
    assert 'Log out' not in index


def test_v11_local_only_user_visible_package_text():
    for path in [Path('frontend/index.html'), Path('documentation/readme/README.md'), Path('documentation/readme/CLEAN_PACKAGE_README.md')]:
        text = path.read_text(encoding='utf-8')
        assert 'multi_user' not in text
        assert 'SaaS' not in text
        assert 'Log out' not in text
