"""The release packager copies the working tree, so untracked local folders must be excluded by name."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_release_package as pkg  # noqa: E402


def test_node_modules_and_input_backup_are_never_packaged() -> None:
    assert pkg._skip_rel(Path("node_modules") / "ast-types" / "README.md")
    assert pkg._skip_rel(Path("node_modules") / "@babel" / "core" / "README.md")
    assert pkg._skip_rel(Path("input_backup") / "demo" / "README.md")
    assert pkg._skip_rel(Path("input_backup") / "README_INPUT_PACKAGE.md")


def test_normal_source_is_still_packaged() -> None:
    assert not pkg._skip_rel(Path("src") / "money.py")
