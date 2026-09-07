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

## What is NOT being corrected here

- **3.11** (frontend leaf-module real-import conversion, finding ARC-1) is tracked separately as Wave 5 item
  W4-6, since its correction requires a decision (reopen vs. formally close), not just a status-label edit —
  see `documentation/reports/WAVE5_IMPLEMENTATION_PLAN_2026-09-07.md`.
- No other Wave 2/3 item's status is disputed by the 2026-09-07 review; this table is exhaustive for the
  findings it raised (ARC-2, N7, N8, ARC-3).

## Verification

A fresh check of each cited file/metric as of this document's date confirms the corrected status column above
matches the code. Re-run the same checks (`wc -l` on the two named functions/files; a count of registered
sheet builders vs. `results_model` coverage) at any future review to confirm these labels haven't silently
drifted again.
