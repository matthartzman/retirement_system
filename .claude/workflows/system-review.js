export const meta = {
  name: 'system-review',
  description: 'Read-only expert-panel system review (CI excluded) that writes one new Markdown report',
  whenToUse: 'Whole-system reviews and health checks driven by the system-review skill; not for a single diff',
  phases: [
    { title: 'Recon', detail: 'resolve repo/ref, collect GitHub context + inventory, 3 recon passes, system map + coverage' },
    { title: 'Panel', detail: '5 experts, each followed by its own adversarial verifier' },
    { title: 'Synthesis', detail: 'finding register + 14-section draft in scratch' },
    { title: 'Planner sign-off', detail: 'planner review, re-verify material changes, revise draft' },
    { title: 'Quality gate', detail: 'gate check, at most one repair pass, no-overwrite write' },
  ],
}

/*
 * System Review — self-contained Workflow script.
 *
 * Invoke with Workflow({ scriptPath: ".claude/workflows/system-review.js", args: {...} }).
 * args: { date (required, YYYY-MM-DD), scratch (required, absolute dir OUTSIDE the project),
 *         scope?, outPath?, depth?: "standard" | "deep" }
 *
 * The Workflow runtime has no filesystem, no clock, and no GitHub binding, so every GitHub MCP
 * read and every file write is delegated to an agent. Intermediate artifacts (manifest, system
 * map, coverage, finding register, report draft) live in args.scratch; the only file ever written
 * inside the project is the final report, at a path that did not previously exist.
 * See ../skills/system-review/references/adapter-contract.md for the stage-by-stage contract.
 */

// ---------------------------------------------------------------- args
const A = args || {}
const DATE = A.date
if (!/^\d{4}-\d{2}-\d{2}$/.test(DATE || '')) {
  throw new Error('args.date (YYYY-MM-DD) is required: the Workflow runtime has no clock.')
}
if (!A.scratch || !/^([A-Za-z]:[\\/]|\/)/.test(String(A.scratch))) {
  throw new Error('args.scratch is required: an absolute directory outside the project for intermediate artifacts.')
}
const SCRATCH = String(A.scratch).replace(/[\\/]+$/, '')
const SCOPE = (A.scope && String(A.scope).trim()) || 'the entire system'
const DEPTH = A.depth === 'deep' ? 'deep' : 'standard'
const OUT_PATH = A.outPath || `documentation/archive/reports/SYSTEM_REVIEW_${DATE}.md`
if (!/\.md$/i.test(OUT_PATH)) throw new Error(`args.outPath must end in .md (got ${OUT_PATH}).`)
// Never overwrite: the writer takes the first candidate that does not exist yet.
const OUT_CANDIDATES = [OUT_PATH].concat(
  Array.from({ length: 19 }, (_, i) => OUT_PATH.replace(/\.md$/i, `-${i + 2}.md`)))

const S = name => `${SCRATCH}/${name}`
const REF = '.claude/skills/system-review'

// Capability aliases from SKILL.md, mapped onto per-agent reasoning effort (models are inherited).
const EFFORT = {
  expert_reasoning: 'high',
  standard_reasoning: 'medium',
  recon: 'medium',
  synthesis: 'high',
  mechanical: 'low',
}
const VERIFY_EFFORT = EFFORT.standard_reasoning

// ---------------------------------------------------------------- policy
const GH_READ = [
  'get_me', 'search_repositories', 'list_branches', 'get_commit', 'list_commits', 'search_commits',
  'search_code', 'get_file_contents', 'list_issues', 'search_issues', 'issue_read',
  'list_pull_requests', 'search_pull_requests', 'pull_request_read', 'list_releases',
  'get_latest_release', 'get_release_by_tag', 'list_tags', 'get_tag',
  'list_repository_collaborators', 'get_teams', 'get_team_members', 'run_secret_scanning',
]
const GH_WRITE = [
  'create_or_update_file', 'delete_file', 'create_pull_request', 'update_pull_request',
  'update_pull_request_branch', 'merge_pull_request', 'pull_request_review_write',
  'add_reply_to_pull_request_comment', 'add_comment_to_pending_review', 'request_copilot_review',
  'issue_write', 'add_issue_comment', 'sub_issue_write', 'create_branch', 'push_files',
  'fork_repository', 'create_repository',
]
const CI_SENTENCE = 'CI was intentionally excluded from this review.'
const RUNTIME_SENTENCE = 'Runtime behavior was not validated during this review.'

// Scoped to category/title only: matching the whole finding would drop legitimate findings whose
// evidence merely mentions e.g. src/pipeline/calc.py.
const CI_RE = /(\bci\b|github actions|workflow run|workflow job|check run|pipeline)/i
const isCi = f => CI_RE.test(`${f.category || ''} ${f.title || ''}`)

const RULES = `You are one stage of a read-only system review of the repository checked out in your working directory (linked to a GitHub repository).

Hard rules:
- READ-ONLY. Do not create, edit, move, or delete any file inside the repository. Only read-only git commands are allowed (status, log, show, diff, rev-parse, remote, ls-files, branch --list); never commit, checkout, switch, stash, reset, add, push, tag, or create branches.
- The ONLY place you may write is the scratch directory ${SCRATCH} (outside the project). Write artifacts there as UTF-8.
- GitHub MCP: use only these read tools: ${GH_READ.join(', ')}. Never call: ${GH_WRITE.join(', ')}. The GitHub tools are deferred — load them with ToolSearch (keyword queries such as "list_issues pull_request_read") before calling. If GitHub MCP is unavailable, fall back to read-only local git and record the gap.
- CI IS EXCLUDED. Do not inspect, resolve, summarize, or make claims about CI, GitHub Actions, workflow runs, jobs, checks, logs, or test-run outcomes. Never produce CI findings, coverage areas, recommendations, waves, or validation steps. The only permitted CI statement is exactly: "${CI_SENTENCE}"
- This review is static: do not run tests, builds, or the application. Never claim tests pass because test code exists.
- Cite only evidence you opened yourself in this run, as "path:lines — symbol — what it establishes". GitHub metadata is context, not proof of product behavior.
- Never equate "no finding" with "healthy"; record inspection status and residual uncertainty.
- Never copy secret values into any artifact; refer to them by location only.

Review parameters: scope="${SCOPE}", date=${DATE}, depth=${DEPTH}. Skill references: ${REF}/references/*.md and ${REF}/schemas/*.json.`

// ---------------------------------------------------------------- schemas
const STR = { type: 'string' }
const STRS = { type: 'array', items: STR }
const BOOL = { type: 'boolean' }
const INSPECTION = [
  'inspected_no_material_finding', 'finding_identified', 'partially_inspected', 'not_inspected',
  'could_not_validate', 'requires_external_domain_verification', 'not_applicable',
]
const DISPOSITIONS = [
  'confirmed', 'partially_confirmed', 'refuted', 'duplicate', 'superseded', 'insufficient_evidence',
]
const GH_DISPOSITIONS = [
  'confirmed', 'contextual_only', 'resolved', 'duplicate', 'out_of_scope', 'insufficient_evidence',
]
const SEVERITY = { type: 'string', enum: ['critical', 'high', 'medium', 'low'] }
const CONFIDENCE = { type: 'string', enum: ['high', 'medium', 'low'] }

const ARTIFACT_SCHEMA = {
  type: 'object',
  required: ['artifact_path', 'summary', 'gaps'],
  properties: { artifact_path: STR, summary: STR, gaps: STRS },
}

const REPO_SCHEMA = {
  type: 'object',
  required: ['resolved', 'owner', 'name', 'default_branch', 'reviewed_ref', 'commit_sha',
    'working_tree_state', 'authenticated_user', 'scratch_outside_project', 'notes'],
  properties: {
    resolved: BOOL, owner: STR, name: STR, default_branch: STR, reviewed_ref: STR, commit_sha: STR,
    pull_request_number: { type: ['integer', 'null'] },
    working_tree_state: { type: 'string', enum: ['clean', 'dirty', 'unknown'] },
    authenticated_user: STR, scratch_outside_project: BOOL, notes: STR,
  },
}

const MAP_SCHEMA = {
  type: 'object',
  required: ['manifest_path', 'system_map_path', 'coverage_path', 'coverage_areas', 'summary'],
  properties: {
    manifest_path: STR, system_map_path: STR, coverage_path: STR, summary: STR,
    coverage_areas: {
      type: 'array',
      items: { type: 'object', required: ['area', 'expert'], properties: { area: STR, expert: STR } },
    },
  },
}

const findingSchema = prefix => ({
  type: 'object',
  required: ['id', 'title', 'category', 'severity', 'confidence', 'inspection_status', 'evidence',
    'observed_behavior', 'impact', 'affected_workflows', 'root_cause', 'options', 'recommendation',
    'dependencies', 'implementation_considerations', 'risk_of_change', 'verification_method'],
  properties: {
    id: { type: 'string', pattern: `^${prefix}-[0-9]{3,}$` },
    title: STR, category: STR, severity: SEVERITY, confidence: CONFIDENCE,
    inspection_status: { type: 'string', enum: INSPECTION },
    evidence: {
      type: 'array', minItems: 1,
      items: {
        type: 'object', required: ['path', 'description'],
        properties: { path: STR, lines: STR, symbol: STR, description: STR },
      },
    },
    github_context: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          type: { type: 'string', enum: ['issue', 'pull_request', 'commit', 'release', 'tag'] },
          id: STR, url: STR, disposition: { type: 'string', enum: GH_DISPOSITIONS },
        },
      },
    },
    observed_behavior: STR, impact: STR, affected_workflows: STRS, root_cause: STR,
    assumptions: STR, jurisdiction: STR, rule_year: STR,
    options: { type: 'array', minItems: 1, items: STR },
    recommendation: STR, dependencies: STRS, implementation_considerations: STR,
    risk_of_change: STR, verification_method: STR,
  },
})

const expertSchema = prefix => ({
  type: 'object',
  required: ['findings', 'coverage_updates', 'github_items_reviewed', 'limitations'],
  properties: {
    findings: { type: 'array', items: findingSchema(prefix) },
    coverage_updates: {
      type: 'array',
      items: {
        type: 'object', required: ['area', 'status', 'evidence', 'residual_uncertainty'],
        properties: {
          area: STR, status: { type: 'string', enum: INSPECTION }, evidence: STRS,
          residual_uncertainty: STR, finding_ids: STRS, github_items: STRS,
        },
      },
    },
    github_items_reviewed: {
      type: 'array',
      items: {
        type: 'object', required: ['ref', 'disposition'],
        properties: { ref: STR, disposition: { type: 'string', enum: GH_DISPOSITIONS }, note: STR },
      },
    },
    limitations: STRS,
  },
})

const VERDICT_SCHEMA = {
  type: 'object',
  required: ['verdicts'],
  properties: {
    verdicts: {
      type: 'array',
      items: {
        type: 'object', required: ['id', 'verification_status', 'rationale'],
        properties: {
          id: STR, verification_status: { type: 'string', enum: DISPOSITIONS },
          severity: SEVERITY, confidence: CONFIDENCE, rationale: STR, duplicate_of: STR,
        },
      },
    },
  },
}

const SYNTH_SCHEMA = {
  type: 'object',
  required: ['draft_path', 'register_path', 'coverage_path', 'cross_expert_duplicates',
    'top_recommendations', 'limitations'],
  properties: {
    draft_path: STR, register_path: STR, coverage_path: STR,
    cross_expert_duplicates: {
      type: 'array',
      items: { type: 'object', required: ['id', 'duplicate_of'], properties: { id: STR, duplicate_of: STR } },
    },
    top_recommendations: STRS, limitations: STRS,
  },
}

const PLANNER_SCHEMA = {
  type: 'object',
  required: ['verdict', 'material_changes', 'requested_changes', 'dissent', 'summary'],
  properties: {
    verdict: { type: 'string', enum: ['approved', 'approved-with-changes', 'not-approved'] },
    material_changes: BOOL,
    requested_changes: {
      type: 'array',
      items: {
        type: 'object', required: ['id', 'description', 'material', 'affects', 'finding_ids'],
        properties: {
          id: STR, description: STR, material: BOOL, finding_ids: STRS,
          affects: {
            type: 'array',
            items: {
              type: 'string',
              enum: ['severity', 'recommendation', 'architecture', 'scope', 'priority',
                'dependencies', 'test_requirements', 'assumptions', 'wording'],
            },
          },
        },
      },
    },
    dissent: STRS, summary: STR,
  },
}

const REVERIFY_SCHEMA = {
  type: 'object',
  required: ['change_id', 'outcome', 'impact_analysis', 'finding_updates'],
  properties: {
    change_id: STR,
    outcome: { type: 'string', enum: ['upheld', 'partially_upheld', 'rejected'] },
    impact_analysis: STR,
    finding_updates: {
      type: 'array',
      items: {
        type: 'object', required: ['id', 'rationale'],
        properties: {
          id: STR, verification_status: { type: 'string', enum: DISPOSITIONS },
          severity: SEVERITY, rationale: STR,
        },
      },
    },
  },
}

const REVISE_SCHEMA = {
  type: 'object',
  required: ['draft_path', 'unresolved_dissent', 'summary'],
  properties: { draft_path: STR, unresolved_dissent: STRS, summary: STR },
}

const GATE_SCHEMA = {
  type: 'object',
  required: ['pass', 'failures'],
  properties: {
    pass: BOOL,
    failures: {
      type: 'array',
      items: { type: 'object', required: ['check', 'detail'], properties: { check: STR, detail: STR } },
    },
  },
}

const WRITE_SCHEMA = {
  type: 'object',
  required: ['written', 'final_path', 'skipped_existing', 'reason'],
  properties: { written: BOOL, final_path: STR, skipped_existing: STRS, reason: STR },
}

// ---------------------------------------------------------------- panel
const PANEL = [
  {
    key: 'architect', prefix: 'ARC', tier: 'expert_reasoning',
    charter: 'Architecture, efficiency, dead code, compatibility shims, modularity, coupling, reuse, data flow, performance.',
  },
  {
    key: 'financial_planner', prefix: 'FIN', tier: 'expert_reasoning',
    charter: 'Retirement, taxation, benefits, healthcare, estate, inheritance, beneficiaries, survivor scenarios, domain correctness. Apply references/financial-domain-governance.md to every tax/retirement/benefits/healthcare/estate/legal-rule finding: jurisdiction and rule year (or "unknown"), configurable vs hard-coded vs sourced vs assumed, authority class, arithmetic correctness vs suitability of advice, whether professional review is required.',
  },
  {
    key: 'usability_accessibility', prefix: 'UX',
    tier: DEPTH === 'deep' ? 'expert_reasoning' : 'standard_reasoning',
    charter: 'Workflow, consistency, compactness, readability, accessibility (font/contrast, keyboard/focus, semantics, screen readers, touch targets, errors), cognitive load, error handling. Do not equate age-friendly design with accessibility.',
  },
  {
    key: 'documentation', prefix: 'DOC',
    tier: DEPTH === 'deep' ? 'expert_reasoning' : 'standard_reasoning',
    charter: 'Clarity for a 60-year-old non-expert, accuracy, discoverability, terminology, redundancy, layout. Apply the document-eligibility rules in references/scope-and-evidence.md.',
  },
  {
    key: 'quality', prefix: 'QA',
    tier: DEPTH === 'deep' ? 'expert_reasoning' : 'standard_reasoning',
    charter: 'Test coverage, boundaries, regression risk, testability, determinism, and static test-quality assessment (structure, assertions, fixtures, mocks, edge cases). Static only — never infer test outcomes.',
  },
]

const expertPrompt = (p, map) => `${RULES}

You are the ${p.key} expert on the review panel. Charter: ${p.charter}

Before reviewing, read ${REF}/references/review-criteria.md and ${REF}/references/findings-schema.md, then load the shared context from scratch:
- manifest: ${map.manifest_path}
- system map: ${map.system_map_path}
- coverage matrix: ${map.coverage_path}
Coverage areas assigned to you: ${JSON.stringify(map.coverage_areas.filter(c => c.expert === p.key).map(c => c.area))}

Review the codebase within scope against your charter and the cross-cutting checks that apply to you. Open every file you cite. Consider the relevant GitHub issues/PRs listed in the manifest; independently inspect linked files before turning any into a finding, and give each a disposition.

Return:
- findings: material findings only, IDs ${p.prefix}-001, ${p.prefix}-002, ... in order. Severity per findings-schema.md (do not inflate). For objective correctness defects, options = ["No credible alternative; this is a correctness defect."]. No CI findings.
- coverage_updates: one entry per assigned area (and any other area you inspected) with status, evidence citations, finding_ids, residual uncertainty.
- github_items_reviewed: each issue/PR you considered with its disposition.
- limitations: what you could not inspect or validate.`

const verifyPrompt = (p, findings) => `${RULES}

You are an adversarial verifier for the ${p.key} expert's findings. Your job is to try to REFUTE each finding below, following "Adversarial verification" in ${REF}/references/findings-schema.md.

For every finding: open each cited file yourself and check evidence sufficiency, severity calibration, existing mitigations, duplication (within this batch — set duplicate_of), solution fit, counterexamples, possibly greater impact, and unresolved assumptions. For financial-rule findings, confirm jurisdiction/rule year are stated or explicitly unknown. If you cannot substantiate a finding from files you opened, it is insufficient_evidence or refuted — when uncertain, choose the more skeptical disposition. You may adjust severity/confidence; explain why in rationale.

Return exactly one verdict per finding ID.

Findings:
${JSON.stringify(findings)}`

// ---------------------------------------------------------------- helpers
function applyVerdicts(findings, result) {
  const byId = new Map(((result && result.verdicts) || []).map(v => [v.id, v]))
  return findings.map(f => {
    const v = byId.get(f.id)
    if (!v) return { ...f, verification_status: 'unverified' }
    return {
      ...f,
      verification_status: v.verification_status,
      severity: v.severity || f.severity,
      confidence: v.confidence || f.confidence,
      verification_rationale: v.rationale,
      ...(v.duplicate_of ? { duplicate_of: v.duplicate_of } : {}),
    }
  })
}

function countByExpert(register) {
  const counts = {}
  for (const p of PANEL) {
    counts[p.key] = {
      confirmed: 0, partially_confirmed: 0, refuted: 0,
      duplicate_or_superseded: 0, insufficient_evidence: 0, unverified: 0,
    }
  }
  for (const f of register) {
    const s = f.verification_status
    const k = s === 'duplicate' || s === 'superseded' ? 'duplicate_or_superseded' : s
    if (counts[f.expert]) counts[f.expert][k] += 1
  }
  return counts
}

// ================================================================ Recon
phase('Recon')

const repo = await agent(`${RULES}

Task: resolve the review target and prepare scratch. Do not collect issues/PRs/inventory yet.
1. Create ${SCRATCH} if missing. Confirm it is NOT inside the repository (compare against \`git rev-parse --show-toplevel\`, case-insensitively on Windows) and is writable; set scratch_outside_project accordingly.
2. GitHub get_me for authenticated_user.
3. owner/name from the local \`git remote get-url origin\`, confirmed via GitHub. If you cannot identify exactly one repository, set resolved=false and explain in notes — do not guess.
4. reviewed_ref = current branch; commit_sha via get_commit on that ref (note in notes if local HEAD differs or the branch is unpushed); default_branch via list_branches / search_repositories; pull_request_number = open PR whose head is reviewed_ref, else null.
5. working_tree_state from \`git status --porcelain\`.
Write the result as JSON to ${S('repo.json')}.`, { label: 'resolve-repo', phase: 'Recon', schema: REPO_SCHEMA, effort: EFFORT.mechanical })

if (!repo) throw new Error('Repository resolution did not complete.')
if (!repo.scratch_outside_project) {
  throw new Error(`args.scratch (${SCRATCH}) is inside the project or not writable; choose a directory outside the repository.`)
}
if (!repo.resolved) throw new Error(`Unable to uniquely resolve the GitHub repository: ${repo.notes}`)
const REPO_LINE = `Repository ${repo.owner}/${repo.name}, reviewed ref ${repo.reviewed_ref} @ ${repo.commit_sha}` +
  `${repo.pull_request_number ? ` (PR #${repo.pull_request_number})` : ''}, default branch ${repo.default_branch}. Details: ${S('repo.json')}.`
log(REPO_LINE)

// Barrier: every recon pass needs the complete manifest parts.
const collectors = await parallel([
  () => agent(`${RULES}

${REPO_LINE}
Task: collect GitHub work context. Use list_issues (open), search_issues (scope-related), list_pull_requests (open), search_pull_requests (scope-related), pull_request_read (method "get") for up to 30 relevant PRs (head/base = reviewed ref, or scope-relevant), list_commits on the reviewed ref (30 most recent), search_commits (scope-related, 30), list_tags (30), list_releases (10), get_latest_release. Identify flagged/pending issues (labels, title conventions). Dedupe issues/PRs by number. If you truncate anything beyond these limits, say so in gaps.
Write JSON { open_issues, flagged_or_pending_issues, open_pull_requests, relevant_merged_pull_requests, recent_commits, scope_related_commits, tags, releases, latest_release } to ${S('manifest-github.json')}. Do not include CI/check/workflow-run data.`,
  { label: 'collect:github-work', phase: 'Recon', schema: ARTIFACT_SCHEMA, effort: EFFORT.recon }),
  () => agent(`${RULES}

${REPO_LINE}
Task: build the repository inventory from the local checkout (use GitHub search_code/get_file_contents only for what the checkout lacks). Identify design_documents, implementation_documents, source_roots, test_roots, configuration_files, external_dependencies (manifests such as package.json, pyproject.toml, requirements.txt). Apply "Document eligibility" in ${REF}/references/scope-and-evidence.md: include every design/implementation document unless conclusively excluded, recording path, status, authoritative evidence, replacement, and confidence for each exclusion; mark ambiguous ones status-uncertain. Exclude CI configuration from the inventory. Record any truncation in gaps.
Write the JSON inventory (plus an "exclusions" array) to ${S('manifest-inventory.json')}.`,
  { label: 'collect:inventory', phase: 'Recon', schema: ARTIFACT_SCHEMA, effort: EFFORT.recon }),
  () => agent(`${RULES}

${REPO_LINE}
Task: collect access and security context — read-only. Call list_repository_collaborators, get_teams (and get_team_members if teams exist), and run_secret_scanning. Any call that fails or is unauthorized is recorded as { "status": "unavailable", "reason": "..." }, not retried in a loop. Redact secret values; keep only type and location.
Write JSON { collaborators, teams, secret_scanning, note: "Review access configuration only; do not modify it." } to ${S('manifest-access-security.json')}.`,
  { label: 'collect:access-security', phase: 'Recon', schema: ARTIFACT_SCHEMA, effort: EFFORT.mechanical }),
])
const collectorGaps = collectors.map((c, i) => c
  ? c.gaps
  : [`${['GitHub work context', 'repository inventory', 'access/security context'][i]} collection failed`]).flat()
if (collectorGaps.length) log(`Recon collection gaps: ${collectorGaps.length}`)

const MANIFEST_PARTS = [S('repo.json'), S('manifest-github.json'), S('manifest-inventory.json'),
  S('manifest-access-security.json')].join(', ')
const RECON_PASSES = [
  { key: 'engine-architecture-calculations', focus: 'entry points, modules, calculation engine, financial logic, data models, persistence, imports/exports, dependencies, compatibility layers' },
  { key: 'ui-workflows', focus: 'UI, routes/components, user workflows, error handling, accessibility surface' },
  { key: 'tests-docs-data-config', focus: 'tests and fixtures, documentation, canonical data, configuration, generated files' },
]
const recon = await parallel(RECON_PASSES.map(r => () => agent(`${RULES}

${REPO_LINE}
Manifest parts: ${MANIFEST_PARTS}.
Task: reconnaissance pass "${r.key}" (see "Reconnaissance" in ${REF}/references/scope-and-evidence.md). Map ${r.focus}. Note known risks and which GitHub work items touch your area. This is a map, not a review — no findings yet. Exclude CI entirely.
Write your map as JSON to ${S(`recon-${r.key}.json`)}.`,
  { label: `recon:${r.key}`, phase: 'Recon', schema: ARTIFACT_SCHEMA, effort: EFFORT.recon })))
const reconGaps = recon.map((r, i) => r ? r.gaps : [`recon pass ${RECON_PASSES[i].key} failed`]).flat()

const map = await agent(`${RULES}

${REPO_LINE}
Inputs: ${MANIFEST_PARTS}, ${RECON_PASSES.map(r => S(`recon-${r.key}.json`)).join(', ')}.
Known gaps so far: ${JSON.stringify(collectorGaps.concat(reconGaps))}
Task:
1. Assemble the review manifest in the shape shown in ${REF}/references/scope-and-evidence.md (explicit_exclusions: ["ci_and_github_actions"]) and write it to ${S('manifest.json')}.
2. Merge the three recon passes into one normalized shared system map (entry points, modules, calculations, financial logic, data models, persistence, imports/exports, UI, workflows, tests, docs, configuration, dependencies, generated files, compatibility layers, known risks, relevant GitHub work items, access context, secret-scan results). No CI entries. Write it to ${S('system-map.json')}.
3. Create the initial coverage matrix covering at least the areas in "Coverage matrix" of ${REF}/references/review-criteria.md, each assigned to exactly one expert from: ${PANEL.map(p => p.key).join(', ')}; status "not_inspected", empty evidence, residual_uncertainty "not yet reviewed". Must satisfy ${REF}/schemas/coverage.schema.json. No CI area. Write it to ${S('coverage.json')}.`,
  { label: 'system-map+coverage', phase: 'Recon', schema: MAP_SCHEMA, effort: EFFORT.recon })
if (!map) throw new Error(`System map / coverage matrix could not be produced; partial artifacts are in ${SCRATCH}.`)

// ================================================================ Panel
phase('Panel')

const panel = await pipeline(PANEL,
  p => agent(expertPrompt(p, map),
    { label: `expert:${p.key}`, phase: 'Panel', schema: expertSchema(p.prefix), effort: EFFORT[p.tier] }),
  (review, p) => {
    if (!review) return { expert: p.key, failed: true, findings: [], dropped: [], review: null }
    const kept = [], dropped = []
    for (const f of review.findings) {
      (isCi(f) ? dropped : kept).push({ ...f, expert: p.key, verification_status: 'unverified' })
    }
    if (!kept.length) return { expert: p.key, failed: false, findings: [], dropped, review }
    return agent(verifyPrompt(p, kept),
      { label: `verify:${p.key}`, phase: 'Panel', schema: VERDICT_SCHEMA, effort: VERIFY_EFFORT })
      .then(v => ({
        expert: p.key, failed: false, verifierFailed: !v,
        findings: applyVerdicts(kept, v), dropped, review,
      }))
  })

const panelOut = panel.map((r, i) => r || { expert: PANEL[i].key, failed: true, findings: [], dropped: [], review: null })
const expertFailures = panelOut.filter(r => r.failed).map(r => r.expert)
const verifierFailures = panelOut.filter(r => r.verifierFailed).map(r => r.expert)
const ciDropped = panelOut.flatMap(r => r.dropped.map(f => `${f.id} ${f.title}`))
let register = panelOut.flatMap(r => r.findings)
if (expertFailures.length) log(`Expert reviews that did not complete (recorded as coverage gaps): ${expertFailures.join(', ')}`)
if (verifierFailures.length) log(`Verifiers that did not complete (findings left unverified): ${verifierFailures.join(', ')}`)
if (ciDropped.length) log(`Dropped ${ciDropped.length} CI-related finding(s): ${ciDropped.join('; ')}`)
const unmatched = register.filter(f => f.verification_status === 'unverified').length
if (unmatched) log(`${unmatched} finding(s) have no verification disposition`)
log(`Panel produced ${register.length} findings across ${PANEL.length - expertFailures.length} experts`)

// ================================================================ Synthesis
phase('Synthesis')

const expertContext = panelOut.filter(r => r.review).map(r => ({
  expert: r.expert,
  coverage_updates: r.review.coverage_updates,
  github_items_reviewed: r.review.github_items_reviewed,
  limitations: r.review.limitations,
}))

const synth = await agent(`${RULES}

${REPO_LINE}
You are the orchestrator (not a sixth expert). Read ${REF}/references/report-template.md, ${REF}/references/findings-schema.md, ${REF}/references/review-criteria.md ("Implementation waves"), ${REF}/references/financial-domain-governance.md, and ${REF}/references/runtime-validation.md. Load ${map.manifest_path}, ${map.system_map_path}, ${map.coverage_path}.

Inputs from this run:
- Verified finding register (JSON): ${JSON.stringify(register)}
- Expert coverage updates, GitHub item dispositions, limitations (JSON): ${JSON.stringify(expertContext)}
- Experts that did not complete: ${JSON.stringify(expertFailures)} — their areas are coverage gaps, never "healthy".
- Verifiers that did not complete: ${JSON.stringify(verifierFailures)}
- Recon gaps: ${JSON.stringify(collectorGaps.concat(reconGaps))}
- Model tiers used (capability alias → reasoning effort): ${JSON.stringify(EFFORT)}; panel: ${JSON.stringify(PANEL.map(p => ({ expert: p.key, tier: p.tier })))}

Task:
1. Cross-expert dedup: where findings from different experts describe the same defect, keep the stronger one and mark the other verification_status "duplicate" with duplicate_of. Do not change any other disposition. Resolve conflicts with the priority hierarchy in findings-schema.md and record each as a conflict record.
2. Build implementation waves (dependency-ordered, genuinely parallel only when no shared components) and set linked_implementation_items on findings.
3. Write the finding register to ${S('findings.json')}; it must validate against ${REF}/schemas/findings.schema.json.
4. Merge the expert coverage updates into ${map.coverage_path} (every area gets a status); it must validate against ${REF}/schemas/coverage.schema.json. Include inspected GitHub issues/PRs with their dispositions.
5. Write the 14-section report draft to ${S('report-draft.md')} following report-template.md exactly. Section 5 covers confirmed and partially_confirmed findings with all required fields; section 13 lists material refuted/duplicate/superseded/insufficient_evidence items with reasons; any finding still "unverified" is flagged as such. Section 12 must contain, verbatim, "${CI_SENTENCE}" and "${RUNTIME_SENTENCE}". Section 14 contains only the line "PENDING PLANNER SIGN-OFF". No CI content anywhere else.
Return the paths, your cross-expert duplicate markings, 3–5 top recommendations, and the major limitations.`,
  { label: 'synthesize', phase: 'Synthesis', schema: SYNTH_SCHEMA, effort: EFFORT.synthesis })
if (!synth) throw new Error(`Synthesis did not complete; artifacts so far are in ${SCRATCH}.`)

const byId = new Map(register.map(f => [f.id, f]))
for (const d of synth.cross_expert_duplicates) {
  const f = byId.get(d.id)
  if (f) byId.set(d.id, { ...f, verification_status: 'duplicate', duplicate_of: d.duplicate_of })
}
register = Array.from(byId.values())

// ================================================================ Planner sign-off
phase('Planner sign-off')

const planner = await agent(`${RULES}

You are the financial planner performing sign-off on the COMPLETE synthesized report, per "Planner sign-off" in ${REF}/references/financial-domain-governance.md. Read ${synth.draft_path} and ${synth.register_path} in full, opening source files where you need to test a claim.

Return verdict (approved | approved-with-changes | not-approved) and every requested change. A change is material when it affects severity, recommendation, architecture, scope, priority, dependencies, test requirements, or assumptions; set material_changes=true if any change is material. Do not edit any file. Record dissent you expect to remain unresolved.`,
  { label: 'planner-signoff', phase: 'Planner sign-off', schema: PLANNER_SCHEMA, effort: EFFORT.expert_reasoning })
if (!planner) throw new Error(`Planner sign-off did not complete; the unsigned draft is at ${synth.draft_path}.`)
log(`Planner verdict: ${planner.verdict} (${planner.requested_changes.length} change(s), material=${planner.material_changes})`)

const material = planner.requested_changes.filter(c => c.material)
if (planner.material_changes && !material.length) log('Planner flagged material changes but marked no individual change material; re-verifying all changes')
const toReverify = material.length ? material : (planner.material_changes ? planner.requested_changes : [])

const reverified = (await parallel(toReverify.map(c => () => agent(`${RULES}

A planner-requested material change must be re-verified before it is applied. Change ${c.id}: ${c.description}
Affects: ${c.affects.join(', ')}. Findings: ${c.finding_ids.join(', ') || '(none named)'}.
Read ${synth.draft_path} and ${synth.register_path}, open the cited evidence yourself, and adversarially test whether the change is justified. Produce an impact analysis (which findings, recommendation, target design, waves, and validation items it touches) and the finding_updates it implies. When evidence does not support the change, outcome = rejected. Do not edit any file.`,
  { label: `reverify:${c.id}`, phase: 'Planner sign-off', schema: REVERIFY_SCHEMA, effort: VERIFY_EFFORT })))).filter(Boolean)
if (reverified.length < toReverify.length) log(`${toReverify.length - reverified.length} material change re-verification(s) did not complete`)

for (const r of reverified) {
  if (r.outcome === 'rejected') continue
  for (const u of r.finding_updates) {
    const f = byId.get(u.id)
    if (!f) continue
    byId.set(u.id, {
      ...f,
      ...(u.verification_status ? { verification_status: u.verification_status } : {}),
      ...(u.severity ? { severity: u.severity } : {}),
    })
  }
}
register = Array.from(byId.values())

const revised = await agent(`${RULES}

Apply the planner sign-off to the draft. Edit only files in ${SCRATCH}.
- Draft: ${synth.draft_path}; register: ${synth.register_path}; coverage: ${synth.coverage_path}.
- Planner result (JSON): ${JSON.stringify(planner)}
- Re-verification of material changes (JSON): ${JSON.stringify(reverified)}
Apply every non-material change, and every material change whose re-verification outcome is upheld or partially_upheld (partially: only the supported part), including its finding_updates. Do not apply rejected changes — record them as dissent. Keep the register, coverage matrix, recommendation, target design, waves, and validation plan consistent with each other after the changes; the register must still validate against ${REF}/schemas/findings.schema.json.
Replace section 14's placeholder with: planner verdict, requested changes, resolution of each, impact analysis for material changes, and unresolved dissent. Remove any CI content that crept in, leaving only "${CI_SENTENCE}" in section 12.`,
  { label: 'apply-signoff', phase: 'Planner sign-off', schema: REVISE_SCHEMA, effort: EFFORT.synthesis })
if (!revised) throw new Error(`Applying the planner sign-off did not complete; draft is at ${synth.draft_path}.`)

// ================================================================ Quality gate
phase('Quality gate')

const gatePrompt = pass => `${RULES}

Quality gate (pass ${pass}) — read-only; do not edit any file. Check ${revised.draft_path}, ${synth.register_path}, and ${synth.coverage_path} against:
1. "Report quality gate" in ${REF}/references/report-template.md: evidence was actually inspected (spot-check at least five citations by opening the files); uninspected areas are not called healthy; every High/Critical finding has a disposition other than "unverified"; target design, waves, and recommendation agree; material work has validation and exit criteria; financial claims are bounded by jurisdiction/rule-year uncertainty; runtime claims are truthful.
2. "Completion gate" in ${REF}/references/scope-and-evidence.md: every inventory item has a status; material financial findings have planner review; evidence gaps are explicit.
3. All 14 sections from report-template.md are present, and section 14 is filled in (no "PENDING PLANNER SIGN-OFF").
4. Section 12 contains verbatim "${CI_SENTENCE}" and "${RUNTIME_SENTENCE}"; nowhere else does the report make any CI / GitHub Actions / workflow-run / check claim, finding, wave, or validation step.
5. The register validates against ${REF}/schemas/findings.schema.json and the coverage matrix against ${REF}/schemas/coverage.schema.json.
Return pass=true only if every check holds; otherwise list each failure precisely.`

let gate = await agent(gatePrompt(1), { label: 'gate:1', phase: 'Quality gate', schema: GATE_SCHEMA, effort: VERIFY_EFFORT })
if (gate && !gate.pass) {
  log(`Quality gate failed ${gate.failures.length} check(s); running one repair pass`)
  const repaired = await agent(`${RULES}

The report failed the quality gate. Fix every failure below by editing only ${revised.draft_path}, ${synth.register_path}, and ${synth.coverage_path} (all in scratch). Do not weaken the gate — where evidence is missing, state the limitation instead of asserting health. Do not change finding dispositions or the planner verdict.
Failures (JSON): ${JSON.stringify(gate.failures)}`,
    { label: 'gate-repair', phase: 'Quality gate', effort: EFFORT.synthesis })
  gate = repaired ? await agent(gatePrompt(2), { label: 'gate:2', phase: 'Quality gate', schema: GATE_SCHEMA, effort: VERIFY_EFFORT }) : null
}

const summaryBase = {
  scope: SCOPE, date: DATE, depth: DEPTH,
  repository: { owner: repo.owner, name: repo.name, ref: repo.reviewed_ref, commit_sha: repo.commit_sha, pull_request_number: repo.pull_request_number ?? null },
  per_expert_counts: countByExpert(register),
  planner_verdict: planner.verdict,
  planner_material_changes: planner.material_changes,
  unresolved_dissent: revised.unresolved_dissent,
  recommendations: synth.top_recommendations,
  limitations: synth.limitations.concat(
    expertFailures.map(e => `Expert review did not complete: ${e}`),
    verifierFailures.map(e => `Adversarial verification did not complete: ${e}`)),
  ci_findings_dropped: ciDropped.length,
  scratch: SCRATCH,
}

if (!gate || !gate.pass) {
  log('Quality gate did not pass; the report was NOT written to the project')
  return { ...summaryBase, status: 'blocked', draft_path: revised.draft_path, gate_failures: gate ? gate.failures : [{ check: 'gate', detail: 'gate agent did not complete' }] }
}

const write = await agent(`${RULES}

Write the final report — the ONE file this review may create inside the project. Never overwrite.
Candidate paths, in order (relative to the repository root): ${JSON.stringify(OUT_CANDIDATES)}
1. For each candidate in order, check whether the file exists (in the local checkout, and via GitHub get_file_contents on ${repo.reviewed_ref}). Take the first candidate that exists in neither; list skipped ones in skipped_existing.
2. If its parent directory is missing, you may create that directory only.
3. Copy ${revised.draft_path} to the chosen path byte-for-byte, using a create-only write (if the file appeared since you checked, stop and report written=false). Do not use any GitHub write tool, and do not git add or commit.
4. Re-read the written file and confirm it matches the draft.
If every candidate already exists, write nothing and return written=false.`,
  { label: 'write-report', phase: 'Quality gate', schema: WRITE_SCHEMA, effort: EFFORT.mechanical })

if (!write || !write.written) {
  return { ...summaryBase, status: 'not_written', draft_path: revised.draft_path, reason: write ? write.reason : 'writer agent did not complete' }
}
log(`Report written to ${write.final_path}`)
return { ...summaryBase, status: 'written', report_path: write.final_path, draft_path: revised.draft_path }
