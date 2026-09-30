"""DOC-008: the committed architecture diagram must equal a fresh generator run."""
import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_committed_architecture_diagram_matches_generator_output(tmp_path):
    spec = importlib.util.spec_from_file_location("generate_system_diagram_for_test", ROOT / "tools/generate_system_diagram.py")
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    committed = gen.OUT_PATH
    fresh = tmp_path / "SYSTEM_ARCHITECTURE_DIAGRAM.md"
    gen.OUT_PATH = fresh
    try:
        gen.main()
    except ValueError:
        # main() prints a path relative to ROOT; a tmp path is outside it.
        pass
    assert fresh.exists()
    assert committed.read_text(encoding="utf-8") == fresh.read_text(encoding="utf-8"), (
        "documentation/reference/SYSTEM_ARCHITECTURE_DIAGRAM.md is stale; "
        "run `python tools/generate_system_diagram.py`"
    )
