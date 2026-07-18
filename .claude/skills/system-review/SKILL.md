---
name: system-review
description: Run a full expert-panel system review — architect, usability, documentation, quality, and financial planner — and produce a single document containing the options, recommendation, design, and implementation plan. Use when the user asks for a complete/system-wide review, a health check of the whole system, or a consolidated improvement plan. Not for reviewing a single diff (use /code-review for that).
---

# System Review

Convenes a five-expert panel over the whole system and produces **one** document:
options → recommendation → design → implementation plan.

The panel:

| Expert | Charter |
|---|---|
| **Architect** | efficiency, dead code, retired backward-compat shims, modularity, common-code reuse |
| **Usability** | workflow, consistency, minimal scrolling and clicking, compact screen design |
| **Documentation** | clarity for a 60-year-old non-expert, no boilerplate or redundancy, margins/gutters preserved |
| **Quality** | non-redundant *and* comprehensive testing — functional through end-to-end |
| **Financial planner** | retirement, tax, estate, inheritance — workflow gaps and new features |
| **Orchestrator** | sequencing, dependencies, minimal effective model per task, parallelism, synthesis |

The financial planner always reviews the finished document, and the orchestrator applies the
resulting edits — this is non-negotiable and already encoded in the workflow.

## How to run it

1. **Scope it.** If the user named a scope ("just the reporting layer", "UI only"), use it verbatim.
   Otherwise the scope is `the entire system`. Don't ask unless the request is genuinely ambiguous.
2. **Read the depth.** `standard` unless the user said "deep", "thorough", "full", or similar.
3. **Pick the output path.** Default `documentation/reports/SYSTEM_REVIEW_<YYYY-MM-DD>.md` using today's
   date from context. If a file already exists there, suffix `-2`, `-3`, … — never overwrite a prior review.
4. **Run the workflow.** This skill is an explicit instruction to call the `Workflow` tool:

```
Workflow({
  name: "system-review",
  args: {
    scope:   "<scope, or 'the entire system'>",
    date:    "<YYYY-MM-DD>",
    outPath: "<path from step 3>",
    depth:   "standard"   // or "deep"
  }
})
```

`Date.now()` is unavailable inside workflow scripts, which is why the date is passed in as an arg.

5. **Report back** when it completes: the document path, the per-expert kept/refuted counts, the
   planner's verdict, and the 3–5 headline recommendations. Offer to start Wave 1 — do not start it
   unprompted.

## The depth arg

Depth changes the expert tier only. Recon stays on haiku and synthesis/sign-off stays on opus in both
modes — those are not worth economising on.

| depth | Architect · Planner | Usability · Documentation · Quality | Use when |
|---|---|---|---|
| `standard` *(default)* | opus | **sonnet** | routine cadence; most reviews |
| `deep` | opus | opus | pre-release, or after a large architectural change |

Architecture and financial-planning judgement stay on opus at both depths: those two carry the design
calls the rest of the plan hangs off. The other three are largely enumerate-and-evaluate work that
sonnet does well at a fraction of the cost.

## What the workflow does

- **Recon** (haiku, parallel ×3) — maps engine, UI, and tests/docs so the five experts don't each
  re-derive the same layout.
- **Expert review** (parallel ×5, structured output) — each expert returns findings with `file:line`
  evidence, 2–3 real options with tradeoffs, and a recommendation.
- **Cross-check** (sonnet) — every critical/high/large finding gets an adversarial verifier whose job
  is to *refute* it. Refuted findings drop to an appendix rather than disappearing silently. Runs
  per-expert as each finishes, not behind a barrier.
- **Synthesis** (opus) — orchestrator resolves conflicts between experts explicitly, then writes the
  single document including the dependency-ordered wave table with parallelism and
  minimal-effective-model per item.
- **Planner sign-off** (opus) — planner reviews the document; orchestrator applies the edits and records
  any disagreement in the open-questions appendix.

## Constraints baked into the run

- **Read-only.** No source edits, no commits. The report is the only file written.
- **The test suite is never executed** — some tests overwrite files under `input/`. Experts read tests.
- Every finding must cite files the agent actually opened; unevidenced findings are treated as noise.

## Cost and iteration

At `standard` this is roughly 15–25 agents with two on opus; at `deep`, five on opus. Appropriate for a
periodic deep review, not a routine check. To re-run after editing the script:
`Workflow({ scriptPath: ".claude/workflows/system-review.js", resumeFromRunId: "<runId>" })` — the
unchanged prefix returns from cache and only the edited stage onward re-runs.
