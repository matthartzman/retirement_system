# Workflow Script Contract

`workflows/system-review.js` is a self-contained Workflow tool script (see the `workflow-authoring`
skill for the script API: `agent()`, `parallel()`, `pipeline()`, `phase()`, `log()`, `args`,
`budget`). It has no filesystem access, no clock, and no direct GitHub binding of its own — every
GitHub MCP read and every file read/write is delegated to an `agent()` call whose prompt embeds
the read-only rules, the GitHub read-command allowlist, and the CI exclusion (the shared `RULES`
string built near the top of the script). There are no host/project adapter functions or
injected `github` object; this document describes the stage contract instead.

## Invocation

```text
Workflow({
  scriptPath: ".claude/workflows/system-review.js",
  args: {
    scope: "<scope, or 'the entire system'>",
    date: "<YYYY-MM-DD>",       // required — the runtime has no clock
    outPath: "<path, optional>", // defaults to documentation/archive/reports/SYSTEM_REVIEW_<date>.md
    depth: "standard|deep",       // optional, defaults to "standard"
    scratch: "<absolute dir outside the project>" // required — the runtime has no filesystem of its own
  }
})
```

`date` and `scratch` are required and the script throws immediately if either is missing or
malformed. `outPath` must end in `.md`; the script never overwrites — it tries the given path,
then `-2.md`, `-3.md`, ... up to `-20.md`, and only the report-writing agent (last stage) actually
checks existence and writes.

## Scratch artifacts

All intermediate state lives under `args.scratch` as JSON/Markdown files, written and read by
successive agents (never by the script itself, which has no filesystem access):

| File | Produced by | Consumed by |
|---|---|---|
| `repo.json` | resolve-repo | every later stage (via `REPO_LINE` summary) |
| `manifest-github.json`, `manifest-inventory.json`, `manifest-access-security.json` | Recon collectors (parallel) | system-map+coverage stage |
| `recon-<pass>.json` (one per reconnaissance pass) | Recon passes (parallel) | system-map+coverage stage |
| `manifest.json`, `system-map.json`, `coverage.json` | system-map+coverage stage | expert stages, synthesis |
| (returned in-line, not filed) expert findings + coverage updates + GitHub dispositions | each `expert:<key>` agent | its own `verify:<key>` agent, then synthesis |
| `findings.json` | synthesize stage | planner sign-off, quality gate |
| `report-draft.md` | synthesize stage, then overwritten by apply-signoff and gate-repair | quality gate, final write |

## Stage-by-stage contract

### resolve-repo (Recon)
Resolves `{owner, name, default_branch, reviewed_ref, commit_sha, pull_request_number,
working_tree_state, authenticated_user, scratch_outside_project, notes}` via `git remote`/`git
status`/`git rev-parse` and `github.get_me`/`get_commit`/`list_branches`. Must set
`scratch_outside_project: false` (not throw) when `args.scratch` resolves inside the repository —
the script itself then aborts with a clear error. Must set `resolved: false` with an explanatory
`notes` rather than guessing when the repository can't be uniquely identified from the local
remote.

### Recon collectors (parallel: `collect:github-work`, `collect:inventory`, `collect:access-security`)
Each returns `{artifact_path, summary, gaps}` (`ARTIFACT_SCHEMA`) and writes its own JSON file.
`collect:github-work` uses only the allowed GitHub read commands and never CI/check/workflow-run
data. `collect:inventory` applies the document-eligibility rules from
`scope-and-evidence.md`. `collect:access-security` treats collaborators/teams/secret-scanning as
best-effort: a failed call becomes `{status: "unavailable", reason}` in its own output, not a
thrown error, and never includes raw secret values. A stage that throws is caught by the script
and folded into `collectorGaps` as a named gap — it does not abort the run.

### Recon passes (parallel: `recon:engine-architecture-calculations`, `recon:ui-workflows`,
### `recon:tests-docs-data-config`)
Each returns `{artifact_path, summary, gaps}` and writes its map to `recon-<pass>.json`. Mapping
only — no findings, no CI content.

### system-map+coverage
Reads the four manifest parts and three recon files (paths passed in the prompt), and returns
`{manifest_path, system_map_path, coverage_path, coverage_areas, summary}` (`MAP_SCHEMA`) after
writing `manifest.json` (per `scope-and-evidence.md`'s manifest shape), `system-map.json`, and
`coverage.json` (validating against `schemas/coverage.schema.json`, one area per named expert).
The script throws if this stage returns nothing — every later stage depends on it.

### expert:<key> (Panel, one per panelist, piped into verify:<key>)
Each of the five panelists (`architect`, `financial_planner`, `usability_accessibility`,
`documentation`, `quality`) returns `{findings, coverage_updates, github_items_reviewed,
limitations}` shaped to satisfy `schemas/findings.schema.json` per finding (IDs prefixed per
expert: `ARC-`, `FIN-`, `UX-`, `DOC-`, `QA-`). The script — not the agent — strips any
CI-flavored finding (matched on `category`/`title` only, per `notCiRelated` logic) before
verification; dropped findings are logged, not silently discarded. A panelist that fails is
recorded in `expertFailures` and treated as a coverage gap by the synthesis stage, never as
"healthy".

### verify:<key> (Panel, second half of each pipeline stage)
Given that expert's kept findings, returns `{verdicts: [{id, verification_status, severity?,
confidence?, rationale, duplicate_of?}]}` (`VERDICT_SCHEMA`) — one verdict per finding ID,
defaulting unmatched or missing verdicts to `unverified` (the script's `applyVerdicts`, not the
agent, does this merge). Skipped entirely (no agent call) when an expert kept zero findings.

### synthesize (Synthesis)
Given the full verified register, per-expert coverage/GitHub/limitations context, and the list of
failed experts/verifiers, performs cross-expert dedup (returned as `cross_expert_duplicates`,
applied by the script — not asked to silently drop items), builds implementation waves, and
writes `findings.json` (validating against `schemas/findings.schema.json`), an updated
`coverage.json`, and the full 14-section `report-draft.md` per `report-template.md`, with section
14 left as a literal placeholder pending sign-off. Returns `SYNTH_SCHEMA`. The script throws if
this stage fails — there is no silent-continue path to a report.

### planner-signoff (Planner sign-off)
Reads the complete draft and register (opening cited source files) and returns `{verdict,
material_changes, requested_changes[], dissent[], summary}` (`PLANNER_SCHEMA`). Never edits any
file. `material_changes` gates whether the script runs the `reverify:<id>` stage.

### reverify:<id> (Planner sign-off, parallel over material changes)
One per planner-requested change flagged material (or every change, if `material_changes` is
true but no individual change was marked so — the script re-verifies all of them in that case,
logging the inconsistency). Returns `{change_id, outcome: upheld|partially_upheld|rejected,
impact_analysis, finding_updates[]}` (`REVERIFY_SCHEMA`). Read-only; a `rejected` outcome means
the apply-signoff stage must not apply that change.

### apply-signoff (Planner sign-off)
Given the planner result and all reverify outcomes, edits only scratch files: applies every
non-material change and every upheld/partially-upheld material change (with its
`finding_updates`), skips rejected changes (recorded as dissent instead), fills in section 14,
and re-strips any CI content. Returns `{draft_path, unresolved_dissent[], summary}`
(`REVISE_SCHEMA`). The script throws if this stage fails — the run does not fall back to an
unsigned draft.

### gate:1 / gate-repair / gate:2 (Quality gate)
`gate:N` checks the revised draft/register/coverage against `report-template.md`'s quality gate,
`scope-and-evidence.md`'s completion gate, section presence, the mandatory CI/runtime sentences,
and schema validity; returns `{pass, failures[]}` (`GATE_SCHEMA`) without editing anything. On a
first failure, `gate-repair` (no schema — free-text confirmation) edits only the scratch draft/
register/coverage to fix each listed failure without weakening any check, then `gate:2` re-checks
once. There is only one repair attempt; a second failure blocks the write.

### write-report (Quality gate, only if the gate passed)
Given the ordered `-2.md`, `-3.md`, ... candidate list, checks existence locally and via
`github.get_file_contents` for each candidate in order, takes the first that exists nowhere,
copies the draft byte-for-byte with a create-only write, and re-reads it to confirm. Returns
`{written, final_path, skipped_existing[], reason}` (`WRITE_SCHEMA`). Uses no GitHub write tool
and does not `git add`/`commit`. If every candidate already exists, returns `written: false`
rather than overwriting anything.

## Failure behavior, generally

Optional/best-effort stages (collectors, individual recon passes, individual expert/verifier
calls, material-change re-verification) degrade to a logged gap rather than aborting the run —
`agent()` itself returns `null` on an unrecoverable subagent failure, and the script treats that
uniformly with an explicit `{status: "unavailable"}`-style response. Required stages
(system-map+coverage, synthesize, apply-signoff) make the script throw when they fail, since
there is no meaningful report without them. The quality gate and report-write stages are the only
ones permitted to end the run with `status: "blocked"` / `"not_written"` instead of a written
report — see the script's final return value.
