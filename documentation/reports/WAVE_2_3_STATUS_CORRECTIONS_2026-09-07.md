# Wave 2/3 Status Corrections

**Date:** 2026-09-07. **Source:** `documentation/reports/SYSTEM_REVIEW_2026-09-07.md`, Wave 5 item W4-9
(findings ARC-2, N7, N8, ARC-3). Corrects how items 2.4, 2.5, 3.10, 3.12, and 3.13 — originally scoped in
`documentation/reports/SYSTEM_REVIEW_2026-08-31.md` §9 (Waves 2-3) — were being described ("done"/"open"/
"ongoing") against what the code and commit history actually show. This is a process fix per the review's
own recommendation (§7): the mismatch itself doesn't block anything, but leaving it uncorrected is what let
the 2026-09-07 review have to re-verify these by hand rather than trust the existing record.

Per the review's §8 target-design guidance ("status-tracking discipline: wave/phase status tables should
carry a machine-checkable metric wherever the original finding had one"), each corrected entry below states
the metric a future review (or this project's own regression suite) can check without re-deriving it from
scratch.

## Corrected status table

| Item | Original scope (2026-08-31 review) | Was tracked as | **Corrected status** | Evidence |
|---|---|---|---|---|
| 2.4 | Retire JSON/YAML config backends | Done | **Partial** — the read path was retired (`_sync_config_backends()` no longer reads from the JSON/YAML mirrors), but the **write path is retained by design**: the mirrors are still written on every save. This was a deliberate scope decision, not an oversight. | `src/server/app_core.py:1846-1913` |
| 2.5 | Collapse the two SQLite stores into one | Open | **Won't-fix (documented)** — a 60-line, reasoned won't-fix rationale exists in-code with a real cost measurement (the collapse was evaluated and rejected on its own merits, not simply left undone). | `src/server/app_core.py:1846-1905` |
| 3.10 | Continue engine decomposition into registered pipeline stages | Ongoing | **Re-scoped, flat-to-negative on its own metric** — `run_deterministic_projection_stage` is **3,210 lines** as of this correction (AST-measured, lines 69-3278 in the current file), up from 3,073 lines when it was first marked "ongoing" and up again from the 3,194 lines the same-day system review measured a few hours earlier. An "ongoing" label implies monotonic progress toward decomposition; this metric keeps moving the wrong direction. Re-scope with an explicit target (e.g. "no net growth in this function's line count without an accompanying stage extraction") rather than an open-ended "ongoing." | AST-measured line count of `run_deterministic_projection_stage` in `src/projection_stages/deterministic_engine.py` (currently 3,210) |
| 3.12 | Extend `results_model` page by page, deleting scraper paths | Ongoing | **Re-scoped, no measured movement** — page coverage remains 6 of ~32 registered sheet builders, unchanged since the item was opened. Re-scope as either (a) a committed target of 3-4 additional high-traffic sheets with a deadline, or (b) formally park the "ongoing" label until someone picks it up, rather than reporting a flat metric as advancing. | registered-sheet-builder coverage count vs. `SHEET_REGISTRY` in `src/module_catalog.py` |
| 3.13 | Split `parse_client` into `src/parsing/` siblings; move validation out | Ongoing | **Re-scoped, net-negative on its own metric** — `parse_client` is **2,089 lines** as of this correction (AST-measured, lines 504-2592 in the current file) versus the 2,072 lines the same-day system review measured a few hours earlier, and essentially unchanged from before the commit that claimed to "extract" from it; that commit's 391 removed lines came from elsewhere in `data_io.py`, not from `parse_client` itself. The item's own stated goal (shrinking `parse_client`) has not progressed — if anything the function has grown slightly since. Re-scope with the line-count ratchet actually targeting `parse_client`'s own line count, not a proxy file. | AST-measured line count of `parse_client` in `src/data_io.py` (currently 2,089) |

## W4-6 (finding ARC-1): item 3.11 formally closed

**Decision (2026-09-08, explicit direction):** formally accept the current state as complete; do not
reopen with a new script-tag-count target.

**Why the original "script-tag count shrinks" criterion was the wrong metric, not evidence of stalled
work:** re-checked `frontend/index.html` directly rather than trusting the review's raw count. 36 of the 37
`<script>` tags are already `type="module"`; the 37th is a one-line inline `keydown` listener (an Escape-key
handler for a chart modal) that was never a "leaf module" conversion candidate in the first place. The count
grew from 25 to 37 because legitimate new features (Monarch auto-import, allocation optimizer, housing
scenarios, and others) each shipped their own script tag — every one of them already added as a real
`type="module"` script, per `frontend/js/modules/phase3_module_manifest.js`'s own `remaining_classic_by_
design: []`. The item's actual goal — real ES modules for load-order safety, not a shrinking tag count — is
substantively met; the tag-count proxy metric just wasn't designed to distinguish "more classic scripts"
from "more module scripts."

**Unused exports:** no cross-module unused-export audit was performed. This codebase has an AST-based
cross-reference tool for `dashboard.js` itself (`tools/js_codemod/census.mjs`), but nothing equivalent for
the ~30 converted leaf modules, and building one is disproportionate to what remains of this item (the
lowest-effort option was the explicit direction given). If a genuinely dead export in one of the converted
leaf modules is found in the course of other work, remove it then rather than as a standalone audit here.

## What is NOT being corrected here

No other Wave 2/3 item's status is disputed by the 2026-09-07 review; this table (plus the W4-6 section
above) is exhaustive for the findings it raised (ARC-1, ARC-2, N7, N8, ARC-3).

## Verification

A fresh check of each cited file/metric as of this document's date confirms the corrected status column above
matches the code. Re-run the same checks (`wc -l` on the two named functions/files; a count of registered
sheet builders vs. `results_model` coverage) at any future review to confirm these labels haven't silently
drifted again.
