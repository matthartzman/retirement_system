# Host Adapter Contract

`workflows/system-review.js` calls a set of host/project adapter functions it does not define,
plus a `github` object it does not import. Both are bindings the runtime is expected to inject.
This document is the source of truth for their signatures, return shapes, and failure behavior —
implement against this, not against inferred call sites in the workflow file.

## `github` object

Provided by the host's GitHub MCP integration. Each method name below corresponds directly to
the GitHub MCP tool of the same name (see `SKILL.md` and `references/scope-and-evidence.md` for
the allowed command list — read-only only; no mutation tools).

All methods are `async`, take a single options object matching the underlying MCP tool's
parameters, and resolve to that tool's normal return shape. On a GitHub-side error, a method
should reject with an `Error` carrying the underlying status/message — callers that tolerate
absence (see `.catch(...)` usage in the workflow) depend on rejection, not on a sentinel return
value.

## Project/repository resolution adapters

### `getLinkedProjectRepository()`
Returns `{ owner: string, name: string } | null | undefined`. Resolves the GitHub repository
linked to the current Claude Code project, if the host maintains that linkage. Returning a
falsy value signals "unknown" and causes the workflow to fall back to
`selectRepositoriesMatchingProject`.

### `getLinkedProjectRef()`
Returns `{ ref: string } | null | undefined`. Resolves the ref (branch or PR head) the current
project is checked out against, if known. Falsy signals "unknown" and the workflow falls back to
the repository's default branch.

### `inferDefaultBranch(repository, branches)`
Sync or async. `repository` is `{ owner, name }`; `branches` is the array returned by
`github.list_branches`. Returns the default branch name as a string. Must not throw for a
non-empty `branches` array.

### `selectRepositoriesMatchingProject(candidates, scope)`
Sync or async. `candidates` is the array returned by `github.search_repositories`; `scope` is
the user-provided or default scope string. Returns the subset of `candidates` plausibly matching
the current project (e.g. by name similarity or local remote config). The workflow requires
exactly one match — return `[]` or multiple entries only when resolution is genuinely ambiguous;
the caller throws rather than guessing.

## Evidence-shaping adapters

### `selectRelevantWorkItems(openIssues, scopedIssues, scope)`
Sync or async. Merges and filters `openIssues` and `scopedIssues` (both arrays from
`github.list_issues` / `github.search_issues`) down to items relevant to `scope`. Returns an
array. Should deduplicate by issue number.

### `selectFlaggedOrPendingIssues(openIssues, scopedIssues)`
Sync or async. Returns the subset of the combined issue set that carry a "flagged" or "pending"
signal (label, title convention, or project-specific marker — host-defined). Returns an array,
possibly empty.

### `mergeUniqueByNumber(listA, listB)`
Sync. Merges two arrays of GitHub objects carrying a `.number` field, deduplicating by that
field, `listA` entries winning on conflict. Returns an array.

### `flattenAndDedupeCodeSearch(results)`
Sync. `results` is an array of `github.search_code` responses (one per query in
`buildRepositoryInventory`). Flattens all matches into one array and deduplicates by `path`.
Returns an array of `{ path, ... }` objects.

### `decodeGitHubContent(content)`
Sync. `content` is a single `github.get_file_contents` response (base64-encoded per the GitHub
API). Returns the decoded UTF-8 file content as a string. Should not throw on binary files;
returning a placeholder or empty string is acceptable — the workflow does not special-case binary
content.

### `classifyInventory(files, scope)`
Sync or async. `files` is the array of `{ path, sha, content }` produced by
`buildRepositoryInventory`. Returns the shaped inventory object matching the
`inventories` block in the manifest schema (`design_documents`, `implementation_documents`,
`source_roots`, `test_roots`, `configuration_files`, `external_dependencies` — see
`references/scope-and-evidence.md`'s manifest example). Apply the document-eligibility rules
from that same reference when classifying.

### `isPotentiallyRelevant(pr)`
Sync. `pr` is a single pull-request object from `github.list_pull_requests`. Returns a boolean —
used as a fallback relevance filter in `hydratePullRequests` when a PR's head/base ref doesn't
match the reviewed ref directly (e.g. a PR referencing the scope in its title/body).

## System-map and coverage adapters

### `normalizeSystemMap(recon, manifest)`
Sync or async. `recon` is the array of three results from the parallel reconnaissance passes
(`engine-architecture-calculations`, `ui-workflows`, `tests-docs-data-config`); `manifest` is the
manifest built by `buildManifest`. Merges the three passes into the single shared system map
described in `references/scope-and-evidence.md` under "Reconnaissance". Must exclude CI content
entirely — no `ci`/`github actions`/`pipeline` entries in the returned map.

### `createCoverageMatrix(systemMap, manifest)`
Sync or async. Returns the initial coverage matrix (pre-expert-review) covering at minimum the
areas listed in `references/review-criteria.md` under "Coverage matrix". Each entry should be
shaped to satisfy `schemas/coverage.schema.json` once `status`/`expert`/`evidence`/
`residual_uncertainty` are filled in by the expert panel.

### `runParallel(specs, context)`
Async. `specs` is an array of `{ name, model }` (the recon passes, or the expert panel from
`panelForDepth`). `context` carries whatever the phase needs (`manifest`, `config`, and for the
expert-panel call also `systemMap`/`coverage`). Runs each spec as an independent reasoning pass
using the given `model` capability alias, in parallel, and returns an array of per-spec results
in the same order as `specs`. A single spec's failure should not silently drop it from the
result array — surface the failure so `normalizeAndDeduplicateFindings` /
`normalizeSystemMap` can account for it as a coverage gap rather than an unreported item.

## Findings pipeline adapters

### `normalizeAndDeduplicateFindings(expertReviews)`
Sync or async. `expertReviews` is the array from `runParallel(panelForDepth(...), ...)`. Flattens
each expert's findings, deduplicates, and shapes each finding to satisfy
`schemas/findings.schema.json`. Do not filter CI content here — that's `notCiRelated`'s job,
applied by the caller immediately after.

### `verifyFindings(findings, context)`
Async. `findings` is the CI-filtered finding array; `context` carries `manifest`, `systemMap`,
`coverage`, `config`. Performs the adversarial-verification pass described in
`references/findings-schema.md` ("Adversarial verification") for every finding requiring it, and
sets each finding's `verification_status` accordingly (`confirmed`, `partially-confirmed`,
`refuted`, `duplicate`, `superseded`, `insufficient-evidence`). Returns the finding array with
`verification_status` populated on every item.

### `synthesizeReport(context)`
Async. `context` is `{ manifest, systemMap, coverage, findings, config }`. Produces the
Markdown report matching `references/report-template.md`'s 14-section structure. Returns a
string.

### `plannerSignOff({ report, model })`
Async. Runs the financial-planner sign-off pass described in
`references/financial-domain-governance.md`. Returns
`{ verdict: "approved" | "approved-with-changes" | "not-approved", requestedChanges: [...],
materialChanges: boolean, ... }`. `materialChanges` gates whether the workflow re-verifies and
re-synthesizes.

### `applyPlannerChanges(report, plannerSignoff)`
Sync. Applies the planner's requested edits to `report`. Returns the updated report string.

### `reverifyAndResynthesize({ report, plannerSignoff, manifest, systemMap, coverage, config })`
Async. Invoked only when `plannerSignoff.materialChanges` is true. Re-runs verification and
synthesis to account for planner-driven changes to severity, recommendation, architecture, scope,
priority, dependencies, test requirements, or assumptions (per
`references/financial-domain-governance.md`). Returns the updated report string.

### `stripCiSectionsAndClaims(report, replacementStatement)`
Sync. Removes any CI-related section or claim from `report`, leaving `replacementStatement`
(`"CI was intentionally excluded from this review."`) as the sole CI-related content. Called
after every stage that could reintroduce CI content (initial synthesis, planner edits,
re-synthesis).

### `validateReportQualityGate(report)`
Async. Throws (or returns a rejected promise) if `report` fails the quality-gate checklist in
`references/report-template.md` ("Report quality gate"). Does not modify `report`.

### `writeFinalReportOnly({ outPath, report, overwrite })`
Async. Writes `report` to `outPath`. Must honor `overwrite: false` by refusing to write (and
signaling the caller, e.g. by throwing) if a file already exists at `outPath` — the workflow
never overwrites an existing report; see `SKILL.md`'s "Output and invocation" for the
`-2`, `-3`, ... suffix convention the caller applies before calling this adapter.

### `completionSummary(report, plannerSignoff, outPath)`
Sync. Builds the final completion response described in `SKILL.md`'s "Completion response"
section: document path, per-expert finding-disposition counts, planner verdict, 3-5
recommendations, and major limitations. Returns a string or structured object per host
convention.

## Failure behavior, generally

Adapters that represent optional/best-effort evidence (`getLinkedProjectRepository`,
`getLinkedProjectRef`, collaborators/teams lookups, secret scanning) should resolve to a falsy
value or an explicit `{ status: "unavailable" }`-shaped result rather than throwing, so the
workflow can record a coverage gap instead of aborting. Adapters representing a required step
(`classifyInventory`, `synthesizeReport`, `validateReportQualityGate`,
`writeFinalReportOnly`) should throw on failure — the workflow has no silent-continue path for
these, consistent with `SKILL.md`'s "Never equate 'no finding' with 'healthy'" rule.