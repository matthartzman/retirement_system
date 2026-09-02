# Scope, Evidence, and Document Eligibility

## Read-only boundary

Do not edit source, tests, configuration, canonical data, inputs, or history. Do not commit, modify GitHub issues, create/update pull requests, create branches, push files, or create implementation patches. The designated report is the only file that may be written in the project. Temporary validation artifacts must remain outside the canonical project and be cleaned up afterward.

## CI exclusion

CI is outside the scope of this skill. Do not inspect, resolve, classify, summarize, or remediate GitHub Actions, workflow runs, jobs, checks, logs, test-run outcomes, or CI failures. Do not make CI-related claims in the health assessment, findings, recommendations, implementation waves, validation plan, or limitations. The report may state only: `CI was intentionally excluded from this review.`

## GitHub-authorized review context

Claude has authorized GitHub MCP access for repository contents, Git history, issues, pull requests, releases, tags, collaborators/teams, and secret scanning. Treat GitHub as the primary source for repository state and work-tracking context.

Resolve GitHub information before asking the user. If access, permissions, history, or evidence are incomplete, record the limitation and request only what is missing.

## Review manifest

Create a manifest before reconnaissance:

```yaml
review_run:
  date: YYYY-MM-DD
  scope: the entire system
  depth: standard
  repository:
    provider: github
    owner: ""
    name: ""
    default_branch: ""
    reviewed_ref: ""
    commit_sha: ""
    pull_request_number: null
    working_tree_state: clean|dirty|unknown
  workflow:
    version: ""
    run_id: ""
  github_context:
    pending_issues: []
    flagged_issues: []
    open_pull_requests: []
    relevant_merged_pull_requests: []
    recent_commits: []
    releases: []
    tags: []
  security_context:
    secret_scanning: ""
  inventories:
    design_documents: []
    implementation_documents: []
    source_roots: []
    test_roots: []
    configuration_files: []
    external_dependencies: []
  exclusions: []
  explicit_exclusions:
    - ci_and_github_actions
```

## Document eligibility

Include every design or implementation document unless conclusively excluded.

Exclude only when authoritative evidence identifies it as implemented and closed, superseded by a named replacement, archived/historical-only, or generated output without normative design content.

For each excluded document, record path, status, authoritative evidence, replacement if applicable, and confidence. If status is ambiguous, include it and mark it `status-uncertain`. An implemented document that is the only record of an active design decision remains historical context.

Use Git history, linked issues, merged pull requests, document front matter, and named replacement documents to establish status. A closed issue or merged pull request alone does not prove complete implementation.

## Evidence ledger

Classify each reviewed area as:

1. Inspected and no material finding.
2. Inspected and finding identified.
3. Partially inspected.
4. Not inspected.
5. Could not validate.
6. Requires external/domain verification.
7. Not applicable.

Preferred citation:

```text
- path/to/file.py:142-161 — symbol or test name — what this establishes
```

A reviewer must open every cited file. GitHub metadata is contextual evidence and cannot substitute for direct file evidence. Incomplete evidence lowers confidence.

## GitHub work context

During reconnaissance, inspect GitHub issues and pull requests relevant to scope. Include open or explicitly flagged/pending work in the system map, coverage matrix, or evidence ledger. Classify each tracked item as `confirmed`, `contextual-only`, `resolved`, `duplicate`, `out-of-scope`, or `insufficient-evidence`.

An issue or pull request is not proof of a defect. Independently inspect linked source, tests, documentation, configuration, or other evidence before making a material finding.

## Reconnaissance

Run three passes in parallel:

1. Engine, architecture, and calculations.
2. UI and workflows.
3. Tests, documentation, data, and configuration.

Produce one normalized shared system map covering entry points, modules, calculations, financial logic, data models, persistence, imports/exports, UI/routes/components, workflows, tests, documentation, configuration, dependencies, generated files, compatibility layers, known risks, relevant GitHub work items, access context, and secret-scan results. Exclude CI entirely.

## Completion gate

Do not finalize until every inventory item has a status, all Critical/High findings have verification disposition, all material financial findings have planner review, material work has validation/exit criteria, and runtime/external/domain evidence gaps are explicit.

If repository size, access, time, or tooling prevents completion, issue a partial review and list coverage gaps.
