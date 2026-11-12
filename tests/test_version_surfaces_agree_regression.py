"""Every displayed or packaged version agrees with src/version.py.

System review 2026-11-10, W1-05 / ARC-006. The server banners still said v11 after the
app moved to v12, and package.json / pyproject.toml said 10.0.0.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tools.bump_version as bv  # noqa: E402
import tools.check_version_surfaces as cvs  # noqa: E402
from src.version import VERSION, release_label  # noqa: E402


def test_the_extended_check_passes_on_the_repository():
    errors: list[str] = []
    cvs._check_current_banners(errors)
    errors.extend(cvs.manifest_version_errors(VERSION))
    assert errors == []


def test_the_check_flags_a_planted_v11_banner_case_insensitively():
    planted = "print('  RETIREMENT PLAN SYSTEM v11  [server mode]')\nok = 'Retirement System v%s'" % VERSION
    hits = cvs.find_stale_banners(planted, VERSION)
    assert [line for line, _ in hits] == [1]
    assert cvs.find_stale_banners("retirement system v11", VERSION)


def test_the_check_flags_a_manifest_that_does_not_track_the_version(tmp_path):
    (tmp_path / "package.json").write_text('{\n  "version": "10.0.0"\n}\n', encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "%s.0.0"\n' % VERSION, encoding="utf-8")
    errors = cvs.manifest_version_errors(VERSION, root=tmp_path)
    assert len(errors) == 1 and errors[0].startswith("package.json")


def test_bump_version_rewrites_both_manifests():
    pkg = bv.apply_package_json_version('{\n  "name": "x",\n  "version": "10.0.0",\n  "type": "module"\n}', "13")
    assert '"version": "13.0.0"' in pkg and '"name": "x"' in pkg
    toml = bv.apply_pyproject_version('[build-system]\nrequires = []\n[project]\nname = "x"\nversion = "10.0.0"\n', "13")
    assert 'version = "13.0.0"' in toml


def test_server_banners_derive_from_release_label():
    for rel in ("main.py", "src/server/__main__.py"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "release_label()" in text or "_release_label()" in text, rel
    assert release_label().endswith("v" + VERSION)
