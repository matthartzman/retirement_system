"""Standalone financial trends reporter (ticket 306).

A separate app from retirement_system: its own entry point (main.py), own
local server, own data file (data/financial_trends_log.jsonl) -- but it
imports retirement_system's src/ calculation modules as a library so its
numbers stay consistent with the main app's dashboard rather than
re-deriving spending/holdings math independently. See
docs/superpowers/specs/2026-09-02-monarch-autoupdate-reporting-design.md.
"""
