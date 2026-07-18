# Phase E: Usability Improvements — Design Brief for Opus 4.8 & Sonnet 5

**Status:** Design phase — ready for architectural review  
**Risk Level:** MEDIUM — high-visibility user-facing changes  
**Date:** 2026-07-07

---

## Executive Summary

This phase eliminates boilerplate help text, consolidates duplicate content, performs terminology normalization (wellness→healthcare), and improves accessibility. The work is medium-risk because:

1. **High visibility** — Users see every help string and copy change
2. **Cross-cutting** — Changes span Python backend (system config), JavaScript frontend (dashboard), and Excel reports
3. **Manifest coordination** — Help content must be curated centrally and distributed to 3 surfaces
4. **Accessibility debt** — Current UI lacks ARIA labels, semantic markup, color contrast guidance

---

## Current State — Usability Debt

### 1. Generated Boilerplate Help Text

**Problem:** `dashboard.js` generates field help by keyword-matching the field label against fallback templates:

```javascript
// Current boilerplate generation (lines ~1800-1850)
function fieldDefaultMeaning(fieldId) {
  const templates = {
    default: "Documents the *{field}* assumption within *{page}*. The projection reads it with nearby fields…",
    premium: "Premiums may lower terminal net worth if no claim occurs…",
    // ... 12 more generic templates
  }
  // Match field label against template keys; return default if no match
}
```

**Scale:** ~180 fields across 8 planning steps generate help this way. ~40 fields fall back to the generic "Documents the X assumption" filler.

**Outcome:** Help text is longer than field labels, adds visual clutter, provides no actual guidance.

**Example mismatches:**
- "Desired return" field gets: "Documents the desired return assumption within Asset Allocation. The projection reads it with nearby fields…" (23 words of filler for a 2-word label)
- Same text for 3 fields on different pages (HSA withdrawal timing mentioned verbatim on Pages 5, 6, 7)

### 2. Duplicate Help Content

**Problem:** Several concepts are re-explained across pages:

| Concept | Pages | Occurrences | Total Words |
|---------|-------|-------------|------------|
| HSA withdrawal timing | 5, 6, 7 | 3 | 127 |
| Sequence of return risk | Dashboard, Strategy | 2 | 89 |
| Roth conversion rules | Income, Strategy, Tax | 3 | 156 |
| Rebalancing costs | Asset Allocation, Strategy | 2 | 72 |
| Bond allocation rationale | Asset Allocation, Strategy | 2 | 81 |

**Recommendation:** One help topic per concept; link or reference from other pages.

### 3. Wellness ↔ Healthcare Terminology

**Current state:** Phase C (legacy removal) will retire the wellness term from saved plan data. But UI still uses "wellness" in 37 places:

- "Wellness premium" (5 occurrences in dashboard.js)
- "Wellness bridge" (8 occurrences)
- "Pre-65 wellness premium" (3 occurrences)
- Help text using "wellness" (12 occurrences)
- Excel report headers (4 occurrences)

**Action:** After Phase C removes legacy shims, rename everywhere to "healthcare" for consistency.

### 4. Page-Level Help Fragmentation

**Problem:** Each planning page has a 4-paragraph `pageHelp` block explaining the concept:

```javascript
pageHelp: {
  summary: "This page controls your income strategy…",
  goals: "Goals in this step are…",
  interactions: "This step interacts with…",
  next_steps: "After configuring this…"
}
```

**Scale:** 8 pages × 4 blocks = 32 help blocks total. Many are 50+ words and repeat similar information.

**Opportunity:** Consolidate to 1–2 clear sentences per page; move detail to field-specific help.

### 5. Accessibility Gaps

**Current state:** No ARIA labels, minimal semantic HTML, no color contrast guidance for low-vision users:

| Gap | Impact | Fix |
|-----|--------|-----|
| Missing `aria-label` on 40+ interactive elements | Screen readers can't identify purpose | Add descriptive labels |
| `<div>` used for form sections (should be `<fieldset>`) | Logical grouping lost for assistive tech | Refactor to semantic HTML |
| Help icon without `role="img"` + `aria-label` | Unclear why icon appears | Add accessibility context |
| No color contrast checks (≥4.5:1 for normal text) | Low-vision users miss UI cues | Audit and adjust palette |
| No focus indicators on custom controls | Keyboard navigation invisible | Add `:focus` styling |

---

## Phase E Workstreams

### Workstream 1: Help-Content Architecture (Opus 4.8)

**Scope:** Design a manifest-driven help system that eliminates boilerplate generation.

**Current flow:**
```
field label → keyword match → fallback template → help text shown
```

**Proposed flow:**
```
field id → help manifest (JSON) → curated text → shown + reported to Excel
```

**Design requirements:**

1. **Help manifest** (`frontend/help_manifest.json` or `src/help_content.py`):
   ```json
   {
     "help_topics": {
       "hsa_withdrawal_timing": {
         "title": "HSA withdrawal timing",
         "brief": "When to withdraw from HSA accounts (before Medicare)",
         "detail": "HSAs can be withdrawn tax-free for medical expenses before age 65…",
         "see_also": ["hsa_contribution", "roth_conversion"]
       },
       "income_strategy": {
         "title": "Income strategy",
         "page_intro": "This page plans your Social Security, pension, and annuity drawdown…",
         "fields": {
           "ss_start_age": "Age when you claim Social Security (62–70 recommended…)",
           "pension_start_age": "Age when pension income begins…"
         }
       }
     }
   }
   ```

2. **Field linking:**
   - Each field `id` maps to a help topic or topic field
   - Fallback: if no mapping, field shows nothing (not boilerplate)
   - Page intro points to a concept topic (e.g. `income_strategy`)

3. **Distribution:**
   - Frontend: Load manifest; render help on demand
   - Backend: Serve manifest via API (`GET /api/help-content`)
   - Reports: Inject help summaries into Excel sheets

4. **Content curation:**
   - 60–80 total help entries (down from 180+ auto-generated)
   - Each entry unique, specific to its field/concept
   - ~5–10 words for field help; ~30–50 for topic explanations
   - No duplication; cross-references instead

**Acceptance criteria:**
- ✅ Help manifest defined and validated (JSON schema)
- ✅ All 180 fields have explicit help entries or "no help" flag
- ✅ No duplicate text across fields
- ✅ Page intros point to concept topics; concept topics explain once
- ✅ Backend API serves manifest
- ✅ Frontend consumes manifest; renders correctly
- ✅ Excel reports include curated help summaries

---

### Workstream 2: Content Sweep & Terminology (Sonnet 5)

**Scope:** Replace "wellness" with "healthcare" everywhere (after Phase C); consolidate duplicate help; improve page-level copy.

#### 2.1 Wellness → Healthcare Sweep

**Files to update:**
- `frontend/js/dashboard.js` (37 occurrences)
- `src/reporting/sheets_summary.py` (4 occurrences in headers)
- `documentation/` (help text and examples)
- Test files (5 occurrences)

**Pattern:**
```python
# Before: wellness_premium, wellness bridge, pre_65_wellness_premium
# After:  healthcare_premium, healthcare bridge, pre_65_healthcare_premium
```

**Validation:**
```bash
grep -r "wellness" src/ frontend/ --include="*.py" --include="*.js" | grep -v "# Phase C migrator" | wc -l
# Should be 0 after sweep
```

#### 2.2 Page-Level Help Consolidation

**Current 4-paragraph format:** Consolidate to 1–2 sentences + link to detailed help topic.

| Page | Current Help (words) | Proposed Help (words) | Reduction |
|------|---------------------|----------------------|-----------|
| Income | 87 | 18 | 79% |
| Assets | 92 | 22 | 76% |
| Insurance | 78 | 15 | 81% |
| Spending | 102 | 28 | 73% |
| Strategy | 95 | 20 | 79% |
| Assumptions | 110 | 25 | 77% |
| Summary | 68 | 14 | 79% |
| Workbook | 54 | 12 | 78% |

**Example rewrite:**

Before (87 words):
> "This page controls your income strategy. Goals in this step are to model when you start Social Security, pensions, and annuities. This step interacts closely with Assets (to determine portfolio longevity) and Spending (income covers expenses). After configuring this step, review the Strategy page to compare scenarios."

After (18 words):
> "Plan when you claim Social Security, pensions, and annuities. See Help for income-interaction details."

#### 2.3 Duplicate Consolidation

**Action:** For each duplicate concept (HSA timing, Roth rules, etc.):
1. Keep primary help entry (best-written version)
2. Replace secondaries with cross-reference: "See [concept name] in Help"
3. Verify all fields point to same entry

**Example:**
```javascript
// Before: 3 separate HSA explanations (127 words total)
// After: 1 entry (32 words) + references from other pages
hsa_withdrawal_timing: "Withdraw HSAs tax-free for medical before 65; after 65, treat as regular income. See Help for interaction with Medicare."
```

---

### Workstream 3: Accessibility Pass (Sonnet 5)

**Scope:** Audit and fix accessibility compliance (WCAG 2.1 Level AA).

#### 3.1 ARIA Labels

**Files:** `frontend/js/dashboard.js`, step modules, batch editors

**Changes:**
- Add `aria-label` to all interactive elements without visible labels
- Add `aria-describedby` linking inputs to help text
- Add `role="img"` + `aria-label` to icon-only buttons

**Example:**
```javascript
// Before
<button class="help-icon">?</button>

// After
<button class="help-icon" aria-label="Show help for this field">?</button>
```

#### 3.2 Semantic HTML

**Files:** `frontend/index.html`, step templates

**Changes:**
- Replace `<div class="form-group">` with `<fieldset>`
- Use `<legend>` for section titles
- Replace generic `<div>` step containers with `<section>`

**Example:**
```html
<!-- Before -->
<div class="step-income">
  <div class="form-group">
    <label>Social Security Start Age</label>
  </div>
</div>

<!-- After -->
<section class="step-income" aria-labelledby="income-title">
  <h2 id="income-title">Income</h2>
  <fieldset>
    <legend>Social Security</legend>
    <label for="ss_start_age">Start age</label>
  </fieldset>
</section>
```

#### 3.3 Color Contrast & Low-Vision Support

**Changes:**
- Audit all text/background combos: must be ≥4.5:1 contrast ratio (WCAG AA)
- Add focus indicators (`:focus` visible on all interactive elements)
- Ensure icons have text labels; don't rely on color alone for meaning

**Example:**
```css
/* Add focus indicator */
button:focus, input:focus {
  outline: 2px solid #0066cc;
  outline-offset: 2px;
}

/* Ensure red-only errors are also marked with icon/text */
.error {
  border: 2px solid #d9534f; /* Red */
  position: relative;
}
.error::after {
  content: "✕"; /* Also show symbol for colorblind users */
}
```

#### 3.4 Keyboard Navigation

**Changes:**
- Ensure all interactive elements reachable via Tab key
- Test with screen reader (NVDA, JAWS) on Windows; VoiceOver on Mac
- Custom controls (sliders, toggles) must support arrow keys

---

## Sequencing & Dependencies

### Hard blocker

**Phase D (module decomposition) must complete first:**
- Phase E's dashboard.js changes depend on D's modularization
- Help manifest distributed to D's new modules
- Can't consolidate help before routes are clean

### Phase C integration

**Phase E must wait for Phase C to complete for wellness→healthcare sweep:**
- Phase C removes legacy data shims
- Phase E updates UI terminology to match
- Old plans with "wellness_premium" keys won't exist post-migration

### Timeline

| Step | Work | Model | Days | Blocker? |
|------|------|-------|------|----------|
| 1 | Design help manifest schema + architecture | **Opus 4.8** | 1 | Must complete |
| 2 | Curate 60–80 help entries | Sonnet 5 | 1.5 | After Opus design |
| 3 | Implement manifest loader + distribution | Opus 4.8 | 1 | After curation |
| 4 | Frontend integration (load manifest, render) | Sonnet 5 | 0.5 | After implementation |
| 5 | Wellness→healthcare sweep | Sonnet 5 | 0.5 | After Phase C |
| 6 | Page-level help consolidation | Sonnet 5 | 0.5 | After sweep |
| 7 | Accessibility audit + ARIA/semantic HTML | Sonnet 5 | 1 | Parallel with steps 5–6 |
| 8 | Excel report integration | Opus 4.8 | 0.5 | After manifest design |
| 9 | Code review + verification | **Opus 4.8** | 0.5 | Before merge |

**Total:** ~6–7 days, 3–4 PRs

---

## Risk Assessment

### Medium risks

1. **Help content curation takes longer than estimated**
   - Mitigation: Start with high-traffic fields (top 20 by frequency); defer others to follow-up
   - Fallback: "No help" is acceptable; boilerplate is not

2. **Accessibility refactor breaks existing layouts**
   - Mitigation: Add semantic HTML incrementally; use CSS to preserve visual layout
   - Test: Verify each step still renders correctly after semantic changes

3. **Wellness sweep misses references**
   - Mitigation: Post-merge, grep for "wellness" in all files (code + docs + comments)
   - Catch: CI gate can include this check

### Low risks

1. **Manifest distribution latency**
   - Mitigation: Manifest is static JSON; cache aggressively
   
2. **Excel report help too verbose**
   - Mitigation: Truncate to 1-sentence summaries in reports; full help in UI

---

## Acceptance Criteria

1. ✅ Help manifest schema defined and validated
2. ✅ 60–80 curated help entries (no boilerplate)
3. ✅ Zero duplicate help text across fields
4. ✅ Wellness→healthcare terminology complete (0 occurrences of "wellness")
5. ✅ Page-level help consolidated to 1–2 sentences
6. ✅ ARIA labels on all interactive elements
7. ✅ Semantic HTML in place (fieldset, legend, section)
8. ✅ Color contrast ≥4.5:1 for all text
9. ✅ Focus indicators visible on all controls
10. ✅ Keyboard navigation working (Tab, arrow keys)
11. ✅ Help content distributed to Excel reports
12. ✅ No test regressions
13. ✅ Accessibility audit passed (WCAG 2.1 Level AA)

---

## Key Decisions for Opus 4.8

1. **Help manifest format:** JSON file or Python data structure? Where should it live (frontend/, src/, or documentation/)?
2. **Help content depth:** 5–10 words for field help vs 30–50 words? Any variation by field complexity?
3. **Cross-references:** How should "See Help for X" links work in the UI? Clickable modal, sidebar, or external link?
4. **Excel report help:** Include brief help in report sheets, or full summaries? How much space?
5. **Accessibility baseline:** WCAG 2.1 Level AA (our target) or AAA (stricter)?
6. **Fallback for unmapped fields:** Show nothing, a placeholder, or a generic "No help available" message?

---

## Out of Scope (Phase F)

- Schema-driven forms (dynamic form generation)
- Scenario comparison UI improvements
- Report unification (those are Phase F enhancements)
- Accessibility for assistive technology beyond ARIA/semantic HTML (VoiceOver, JAWS integration testing)

---

## Related Files

- `frontend/js/dashboard.js` (lines 1800–1850: help generation)
- `frontend/index.html` (layout, semantic markup)
- `src/reporting/sheets_summary.py` (report headers)
- `documentation/SYSTEM_MODERNIZATION_PLAN.md` Section 5 (Phase E workstream)
- Tests: `tests/test_80_detailed_results_ui.py`, `tests/frontend/load_dashboard.mjs`

---

## Next Steps

1. **Opus 4.8:** Review this brief, answer 6 key decisions, design help manifest
2. **Phase D:** Complete module decomposition (blocker for Phase E)
3. **Phase C:** Complete legacy removal + wellness→healthcare data migration
4. **Sonnet 5:** Curate help content, execute sweep, accessibility pass
5. **Opus 4.8:** Final review + merge

**Target:** Start Phase E after Phase D merges; complete before Phase F (enhancements).

---

Generated by Claude Code
