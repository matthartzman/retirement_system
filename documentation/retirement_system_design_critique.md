## Design Critique: Retirement Planning System UI

*No Figma file or screenshot was available, so this is a code-level review of the shipped frontend (`index.html`, `admin.html`, `dashboard.css`, `admin.css`, `navigation.js`, and the `dashboard.js`/decomp JS files that render the app). Findings on hierarchy, consistency, and accessibility are drawn directly from the markup, CSS tokens, and JS render functions rather than a visual walkthrough — flag any spots where a screenshot would sharpen this.*

### Overall Impression
The app has a genuine information architecture — a three-column shell (steps nav / content / contextual help) with 44 guided steps grouped into 7 logical phases (household, income, spending, assets/protection, strategy, stress tests, review) — but it's being rendered by one 16,786-line script that builds nearly every screen as a concatenated HTML string. That's the single biggest risk to UI quality: the structure is thoughtful, the implementation is fragile, and it's already produced at least one shipped visual bug (undefined CSS tokens rendering with no color).

### Usability
| Finding | Severity | Recommendation |
|---------|----------|----------------|
| Redirect layer silently reroutes ~6+ nominal steps (e.g. `ss_timing`, `roth_conversion`) into merged "workspace" pages with internal tabs | 🟡 Moderate | If a user navigates to what they think is "Social Security Timing" and lands on a combined workspace, the step list is lying about the app's real structure. Either update the step list to reflect the real destinations, or make the merge visible (e.g., breadcrumbs showing "Income Workspace > SS Timing tab"). |
| Zero `<label>` elements anywhere in the codebase; form fields rely on `aria-label` only | 🔴 Critical | Sighted mouse users get no clickable label-to-input association (can't click a label to focus a field), and hundreds of inputs across `dashboard.js` appear to lean on adjacent `.field-label` divs with no `for`/`id` link. Add real `<label for="...">` elements — this is both a usability and accessibility fix in one. |
| 67+ inline `style="..."` overrides in `dashboard.js` despite a full CSS system existing | 🟡 Moderate | Ad hoc styling at the template-string call site (`style="color:var(--muted)"`, `style="margin-top:4px"`) means the same visual intent is implemented inconsistently across the app. Convert to utility classes so spacing/color stay uniform as the app grows. |
| Duplicated table/card markup patterns (lot-table, matrix-table, feature-card, planning-case-card) hand-reimplemented across 3+ files | 🟡 Moderate | Each surface reinvents its own wrapper markup instead of sharing a helper, so a table in the Workbench and a similar table in Supplemental Tables can drift apart in padding, borders, or row behavior without anyone noticing. |

### Visual Hierarchy
- **What draws the eye first**: With a 3-column shell (nav / content / help pane), the guided-steps nav on the left is likely the first anchor — appropriate for a 44-step guided flow, assuming the content pane's primary CTA has enough visual weight to compete with 44 nav items.
- **Reading flow**: Left-to-right through nav → content → contextual help matches western reading order and a typical "wizard" mental model. The redirect layer complicates this: users following the nav order will sometimes land on a page that internally branches into tabs they didn't choose, which breaks the otherwise linear flow.
- **Emphasis**: Can't confirm from code alone whether the right elements are visually emphasized (e.g., whether "Build Plan" or "Save" has enough contrast against secondary actions) — this needs an actual screenshot or live walkthrough to verify.

### Consistency
| Element | Issue | Recommendation |
|---------|-------|----------------|
| CSS custom properties | `--brand`, `--text`, and `--well` are referenced (`dashboard.css:619,627,630,647,174,199,376,383,391-395`) but never defined in either stylesheet — those elements render with unset color today | Define the missing tokens or replace references with the existing `--ink`/`--accent`/`--bg` set. This is a live bug, not a style nit. |
| Accent color | A "Build History" block (`dashboard.css:294-309`) uses a parallel fallback convention — `var(--accent,#0057b7)` — with a different blue than the app's real `--accent` (`#1f4f8f`) | Consolidate to one accent color; the fallback pattern suggests this block was added without cross-checking the existing token set. |
| Two stylesheets, shared root tokens | `dashboard.css` and `admin.css` both define the same `:root` token block verbatim — good | Keep this pattern going forward rather than letting Admin drift into its own system. |
| Sequential patch comments | Dozens of comments like "Item 70," "WP-C," "Change 127," "5.6," "5.8" scattered through `dashboard.css` | Not a user-facing issue, but it signals the stylesheet has grown by append-only patches rather than deliberate design — worth a consolidation pass before it gets harder to safely touch. |

### Accessibility
- **Color contrast**: Not verifiable from code alone (tokens exist but need to be checked against actual hex/rendered values) — recommend running the `design:accessibility-review` skill against a live screenshot or running the app once it's available.
- **Touch targets**: Can't confirm sizing from CSS alone without seeing computed styles; flag for a follow-up pass.
- **Semantic structure**: 0 `<label>` elements in the entire codebase; ~37 `aria-*` attributes and ~18 `role=` attributes total across a codebase with hundreds of form inputs — coverage is thin relative to the number of interactive elements, meaning most fields likely have no accessible name beyond a non-linked label div.
- **Images**: No `<img>` tags found, so the "0 `alt=` attributes" finding isn't a defect — just confirms the UI is markup/CSS-driven rather than image-driven.

### What Works Well
- The underlying information architecture (44 steps → 7 phases, redirect layer consolidating related steps into workspaces) reflects real thought about how a retirement plan actually gets built, not just a flat form dump.
- Shared root color/spacing tokens between `dashboard.css` and `admin.css` show an intent toward one visual system even across two separate "apps" (main + admin).
- No stray TODO/FIXME/HACK comments — either the code is genuinely clean or debt isn't being left as breadcrumbs; worth confirming which.

### Priority Recommendations
1. **Fix the undefined CSS tokens (`--brand`, `--text`, `--well`) and reconcile the second accent-color dialect** — this is a shipped visual bug affecting real users today, and it's a small, contained fix.
2. **Add real `<label for>` elements to every form input** — closes both a usability gap (click-to-focus) and an accessibility gap (screen reader association) in one pass, and is more foundational than anything else here since it touches every guided step.
3. **Decide whether the redirect/workspace-merge behavior should be visible in the nav** — either rename the step list to match real destinations or add breadcrumbs, so the guided flow doesn't quietly diverge from what the nav promises.

*Recommend a follow-up visual pass (screenshot or live app) once available — this review can confirm what's structurally present but can't judge actual contrast, spacing rhythm, or first-impression weight without seeing it rendered.*
