# Mobile / Phone Manual Test Checklist

Generated: 2026-07-03 (Phase 1 of the Android mobile enhancement plan — see
`ANDROID_MOBILE_ENHANCEMENT_PLAN.md`)

Automated coverage for the mobile-responsive frontend lives in
`tests/test_phase1_mobile_responsive_shell.py` (DOM/CSS hooks exist) and
`tools/run_regression.py` (frontend string/behavior markers). Neither drives a
real browser, so use this checklist to manually verify the actual rendered
experience — in Chrome DevTools device emulation during development, and on a
real Android/iOS device before considering a phone-facing change done.

## Setup

```
python main.py --mode server        # http://127.0.0.1:5050
```

Open the URL in Chrome DevTools with device toolbar enabled (iPhone 12/13
mini — 390×844 — is a good baseline phone width; also spot-check 768px for
tablet and a real device when possible).

## 1.1 — Navigation drawer and collapsible help

- [ ] At ≤768px, the hamburger icon (☰) appears top-left of the header; the
      full left nav (steps list) is off-screen until opened.
- [ ] Tapping ☰ slides the nav drawer in from the left with a dimmed backdrop
      over the rest of the page.
- [ ] Tapping the backdrop (outside the drawer), the ✕ close button, clicking
      a step inside the drawer, or pressing Escape all close the drawer.
- [ ] Selecting a step from the drawer navigates to that step's content and
      closes the drawer automatically.
- [ ] The right-hand "Context Help" panel is collapsed by default; tapping the
      "Context Help" header expands/collapses it in place.
- [ ] On desktop (>768px), the hamburger and drawer/backdrop are invisible,
      and "Context Help" is always expanded with **no button-style border or
      cursor change** — it must look and act exactly like a plain heading.

## 1.2 — Touch ergonomics

- [ ] Buttons, step-list entries, and the help icon are comfortably tappable
      (no accidental taps on adjacent controls) at 390px width.
- [ ] Tapping a text input inside a form field does **not** trigger the
      iOS/Android browser's auto-zoom (inputs render at 16px on real
      touch devices at ≤480px).
- [ ] No leftover hover-only affordance makes a control look "stuck" after a
      tap on a touch-only device.

## 1.3 — Dense tables (Investment Holdings, Liabilities)

- [ ] At ≤480px, each holding lot and each liability renders as an individual
      card with a label above/beside each value (Account, Symbol, Purchase
      Date, Shares, Purchase Price, Lot Type, Actions, etc.) — no tiny
      horizontally-scrolling table.
- [ ] Between ~480–900px (tablet), the same tables fall back to the
      horizontal-scroll table baseline with a visible edge-fade hinting more
      columns are off-screen.
- [ ] On desktop, these tables are pixel-identical to before Phase 1 — full
      table, no cards, no edge-fade.
- [ ] Editing a value inside a card (e.g., Purchase Price) updates state the
      same way it does in the desktop table (check the unsaved-changes
      indicator appears).

## 1.4 — Bottom navigation bar and header progress

- [ ] At ≤768px, a "← Previous / Step Help / Next →" bar is fixed to the
      bottom of the viewport on every guided step and stays visible while the
      page content scrolls underneath it.
- [ ] The fixed bar never overlaps the last few pixels of scrollable content
      (page has enough bottom padding to fully reveal the last field/button).
- [ ] The thin progress strip along the bottom edge of the header updates as
      you move between steps (mirrors the percentage shown inside the nav
      drawer's progress bar).

## 1.5 — Results Explorer / charts

- [ ] Navigate to Reports & Review → Results (or Detailed Results) at 390px:
      no page-level horizontal scrollbar appears.
- [ ] Any wide result tables or chart-type tab strips scroll **within their
      own container**, not the whole page.
- [ ] Chart/metric cards stack to a single readable column at phone widths.

## 1.6 — File import pickers

- [ ] Investment Holdings → "Preview & replace CSV" opens the native
      file-picker (Android document picker / iOS Files) and a selected CSV
      is accepted.
- [ ] YTD Transactions → CSV upload behaves the same way.

## 1.7 — Regression safety net

- [ ] `pytest tests/test_phase1_mobile_responsive_shell.py -v` passes (DOM
      hooks, CSS breakpoints, and the desktop-chrome-reset regression guard).
- [ ] `python tools/run_regression.py` shows no *new* failures versus the
      pre-Phase-1 baseline (16 pre-existing frontend markers are tracked
      separately and are not part of this checklist's scope).
- [ ] `pytest tests/` passes in full (`--tb=short -q`).

## Known pre-existing gaps (not introduced by Phase 1, not blocking)

- 16 `dashboard.js` content markers flagged by `tools/run_regression.py`
  (chart y-axis formatting, column-group data attributes, etc.) predate this
  work and are tracked as follow-on frontend cleanup, not a mobile
  regression.
