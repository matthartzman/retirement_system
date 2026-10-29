# Financial Insight: Readable Recent Projections and New Names, October 2026

Companion reporter only. No projection or build result moves; the golden masters are unchanged.
Design and plan: `documentation/future/superpowers/plans/2026-10-29-financial-insight-readability-design.md`.

## What you see

- **New names.** The companion app is now **Financial Insight** (page heading, browser tab, sign-in and
  change-password pages, exit screen, desktop shortcut). The first view is now **Current Snapshot**
  (formerly Live Snapshot). Rerunning `tools/INSTALL_DESKTOP_ICON.py` replaces the old
  "Financial Trends Reporter" shortcut.
- **Recent Projections tables are easier to read** (Net Worth and Cash Flow):
  - Group subtotals are bold; an inner group's subtotal is regular; individual accounts and lines are
    grey and a size smaller.
  - An open group has a vertical rule on each side (lighter for a group inside a group), and the
    table's total (Total NW, or Net Worth on Cash Flow) has a heavier rule on its left.
  - Every other year is shaded, including the frozen Year column.

## Fixes

- Opening Recent Projections while a rebuild is replacing its file now shows the rebuild prompt instead
  of an error.
- The "plan changed since this build" check is cached until the plan file changes, so it no longer
  re-reads every plan dataset on each visit.
- For a viewer who sees percentages only, the "groups don't add up to Total NW" warning now shows a
  mismatch of any real size (before, it hid anything under 1% of net worth).
- Year and age cells are HTML-escaped.
