"""W3-10 / DOC-003: the in-app Concepts Guide is generated from the help registry and is reachable from the app."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_page_matches_the_registry():
    out = subprocess.run([sys.executable, str(ROOT / "tools" / "generate_concepts_page.py"), "--check"],
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stdout + out.stderr


def test_every_registry_page_title_is_in_the_guide():
    sys.path.insert(0, str(ROOT / "tools"))
    import generate_concepts_page as g
    reg = g.load_registry()
    page = g.OUT.read_text(encoding="utf-8")
    missing = [p["title"] for p in reg["pages"].values() if p.get("title") and g.html.escape(p["title"]) not in page]
    assert missing == []
