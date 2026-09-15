"""ZIP-code screening (Stage 1) for the housing optimizer.

Everything ZIP-shaped lives in this package and stops at its boundary: the
screener's output is a list of ordinary ``Location`` objects, so
``optimizer.py``, ``search.py``, ``scoring.py``, ``constraints.py`` and
``plan_variant.py`` never learn that ZIP codes exist. See
docs/superpowers/specs/2026-09-15-zip-code-housing-screening-design.md.
"""
from __future__ import annotations
