---
name: system-review
description: Perform a read-only, evidence-backed, system-wide review of a retirement-planning application. Use for complete system reviews, health checks, consolidated improvement plans, expert-panel reviews, and full architectural, usability, documentation, quality, and financial-planning assessments. Do not use for a single diff or isolated change; use /code-review instead.
---

# System Review

Produce one auditable Markdown report covering:

coverage → findings → options → recommendation → target design → implementation plan → validation plan

## Operating rules

- The review is read-only except for the designated report and temporary artifacts outside the canonical project.
- Use the `Workflow` tool and authorized GitHub MCP access for repository, Git history, issues, pull requests, files, releases, tags, access, and secret-scanning evidence.
- Do not resolve, inspect, report on, or attempt to remediate CI errors, GitHub Actions outcomes, workflow runs, jobs, checks, logs, or test-run statuses as CI evidence. CI is explicitly outside this skill’s scope.
- Do not ask the user for repository, ref, commit, issue, pull-request, document-status, or GitHub information that authorized GitHub access can resolve.
- Never equate “no finding” with “healthy.” Record inspection status and residual uncertainty.
- Cite evidence only from files actually opened by the reporting expert or verifier.
- Never claim tests pass or runtime behavior is correct unless safely validated in an isolated environment.
- The financial planner must review the completed synthesis before finalization. Material edits require impact analysis and re-verification.
- Use configured capability aliases: `expert_reasoning`, `standard_reasoning`, `recon`, and `synthesis`.

## GitHub evidence

Claude has authorized GitHub MCP access for the linked repository. Use it to resolve repository/ref/commit context; design and implementation documents; Git history; open, flagged, or pending issues; relevant pull requests; releases/tags; access context; and secret-scan results.

GitHub metadata is contextual evidence. It does not replace direct inspection of repository files or safe runtime validation.

## Scope and depth

Use the user’s explicit scope verbatim. Otherwise use `the entire system`. Do not ask for scope unless genuinely ambiguous.

Default depth is `standard`. Use `deep` for deep, thorough, exhaustive, full, comprehensive, pre-release, or post-major-architecture-change review.

| Depth | Architect / Planner | Usability / Docs / Quality | Recon | Verification | Synthesis |
|---|---|---|---|---|---|
| standard | expert_reasoning | standard_reasoning | recon | standard_reasoning | synthesis |
| deep | expert_reasoning | expert_reasoning | recon | standard_reasoning | synthesis |

## Output and invocation

Default: `documentation/reports/SYSTEM_REVIEW_<YYYY-MM-DD>.md`. Use the date from context, not `Date.now()`. If occupied, append `-2`, `-3`, and so on; never overwrite.

```text
Workflow({
  name: "system-review",
  args: {
    scope: "<scope, or 'the entire system'>",
    date: "<YYYY-MM-DD>",
    outPath: "<selected path>",
    depth: "standard|deep"
  }
})
```

See linked references for detailed procedure. Read each when its phase of the review is reached, not all up front:

- [Scope and evidence](references/scope-and-evidence.md) — read before reconnaissance: read-only boundary, CI exclusion, the review manifest shape, document eligibility, and the evidence ledger.
- [Review criteria](references/review-criteria.md) — read before running the expert panel: panel charters, coverage matrix areas, cross-cutting checks (calculations, boundaries, data integrity, security, accessibility).
- [Finding schema](references/findings-schema.md) — read when recording or verifying findings: required fields, severity/confidence definitions, adversarial-verification dispositions. Findings must also satisfy `schemas/findings.schema.json`; the JSON schema is authoritative on field names and types where the two differ.
- [Financial governance](references/financial-domain-governance.md) — read for any tax, retirement, benefits, healthcare, estate, or legal-rule finding: jurisdiction/rule-year requirements, planner sign-off process.
- [Runtime-validation policy](references/runtime-validation.md) — read before claiming anything about test or runtime behavior.
- [Report template](references/report-template.md) — read before synthesis: the 14-section report structure and the pre-finalization quality gate.
- [Coverage schema](schemas/coverage.schema.json) / [Findings schema](schemas/findings.schema.json) — machine-checkable shapes for the coverage matrix and finding register; validate the structured data against these before treating the Markdown report as final.
- [Host adapter contract](references/adapter-contract.md) — read only if implementing or debugging `workflows/system-review.js`: signatures and failure behavior for every host/project adapter the workflow calls.

## If the `Workflow` tool is unavailable

The skill and its references still load and are still useful without it: parse scope and depth,
resolve GitHub context directly through the authorized MCP commands, and work through
reconnaissance → coverage → expert review → findings → synthesis manually, one phase at a time,
applying the same rules (read-only boundary, CI exclusion, evidence citation, adversarial
verification) at each step. Say explicitly, up front, that this run is proceeding without
workflow orchestration — do not silently emit the `Workflow(...)` instructions and stop.

## Completion response

Report final document path; per-expert counts for confirmed, partially-confirmed, refuted, duplicate/superseded, and insufficient-evidence findings; planner verdict; 3–5 recommendations; and major limitations.

Then say: “I can start Wave 1 when you’re ready.” Do not start Wave 1 automatically.