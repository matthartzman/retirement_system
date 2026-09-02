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

See linked references for detailed procedure:

- [Scope and evidence](references/scope-and-evidence.md)
- [Review criteria](references/review-criteria.md)
- [Finding schema](references/findings-schema.md)
- [Financial governance](references/financial-domain-governance.md)
- [Runtime-validation policy](references/runtime-validation.md)
- [Report template](references/report-template.md)

## Completion response

Report final document path; per-expert counts for confirmed, partially-confirmed, refuted, duplicate/superseded, and insufficient-evidence findings; planner verdict; 3–5 recommendations; and major limitations.

Then say: “I can start Wave 1 when you’re ready.” Do not start Wave 1 automatically.
