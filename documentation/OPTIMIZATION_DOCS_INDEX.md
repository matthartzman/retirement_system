# Optimization Planning Docs — Index

**Purpose:** finding DOC-205 (system review 2026-09-07, Wave 6 item W6-6) — `documentation/` root holds
several overlapping, ambiguously-titled documents about the retirement-engine optimization/decision-model
rewrite, with no index distinguishing current from superseded. This file is purely additive: it lists what
exists, its actual date, and — only where a document's own content already states the relationship — what it
supersedes or tracks. No listed document is deleted, renamed, or has its substantive content changed by this
index.

There are two distinct, related tracks in this cluster. Do not read them as one linear history.

## Track 1 — The "Optimization Implementation Plan" design lineage

| Document | Date (last touched) | What it is |
|---|---|---|
| `Final Optimization Upgrade Plan.md` | 2026-09-02 | An early metrics-proposal discussion (switching Terminal Net Worth → Lifetime Consumption Value, Lifetime Taxes → NPV of Future Taxes, Probability of Success → 5th-percentile ending wealth, adding an Effective Future Tax Rate metric) with a response evaluating it. Predates and motivates the formal plan below; not itself a step-by-step implementation plan. |
| `Final Optimization Implementation Plan.md` | 2026-09-02 | The first formal design/implementation plan (self-described: "no changes in this document have been executed"). Titled `# Final Optimization Implementation Plan`. |
| `Latest Optimization Implementation Plan.md` | 2026-09-02 | **Despite the filename, this is a *revision* of the plan above, not a separate document** — its own `<h1>` reads the identical `# Final Optimization Implementation Plan`, and its status line says "revised for robust policy selection and adaptive execution." **This is the current plan document in this track.** |
| `OPTIMIZATION_REFACTOR_STATUS.md` | 2026-08-28 | The live status tracker for this track. Its own opening line names what it tracks: `"Final Optimization Implementation Plan — Revised"` — i.e. it tracks `Latest Optimization Implementation Plan.md`, not the original `Final Optimization Implementation Plan.md`. **Read this file first for current status**, then the "Latest" plan for the design itself. |

**Reading order for current state:** `OPTIMIZATION_REFACTOR_STATUS.md` (status) → `Latest Optimization
Implementation Plan.md` (the design it tracks) → `Final Optimization Implementation Plan.md` and `Final
Optimization Upgrade Plan.md` (earlier drafts/inputs, kept for history).

## Track 2 — The "F0-F5" execution playbook

| Document | Date (last touched) | What it is |
|---|---|---|
| `F0_F1_F2_COMPLETION_SUMMARY.md` | 2026-08-12 | A point-in-time summary: "All work complete, ready for local commit/push" for phases F0-F2 of a separate, phase-numbered execution plan. |
| `REMAINING_WORK_EXECUTION_PLAYBOOK.md` | 2026-08-12 (later same day) | States its own basis explicitly: `Plan Basis: REMAINING_WORK_PLAN_2026-08-12.md`. Status line: "F0-F2 Complete \| F3/F4/F5 Ready to Execute" — i.e. it is the successor/continuation of the completion summary above, covering the same F0-F2 work plus what comes next (F3-F5). **This is the current document in this track.** |

Track 2 predates Track 1 by three weeks and uses a different phase-numbering scheme (F0-F5 vs. the
Track 1 documents' own internal structure) — nothing here establishes whether Track 2's remaining phases
(F3-F5) were folded into Track 1's plan or are tracked separately; that determination is out of scope for
this index (additive documentation only, no editorial judgment about work status).
