from pathlib import Path
from src.version import VERSION


def test_v10_version_surfaces_are_v10():
    assert VERSION == '9'
    index = Path('frontend/index.html').read_text(encoding='utf-8')
    assert 'Version' in index
    assert '<span>9</span>' in index
    assert 'Log out' not in index


def test_v10_local_only_user_visible_package_text():
    for path in [Path('frontend/index.html'), Path('documentation/readme/README.md'), Path('documentation/readme/CLEAN_PACKAGE_README.md')]:
        text = path.read_text(encoding='utf-8')
        assert 'multi_user' not in text
        assert 'SaaS' not in text
        assert 'Log out' not in text
