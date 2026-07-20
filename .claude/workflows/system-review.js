export const meta = {
  name: 'system-review',
  description: 'Five-expert full system review producing one recommendation + design + implementation plan document',
  whenToUse: 'Periodic deep review of the whole retirement-planning system by an architect, usability, documentation, QA, and financial-planning panel.',
  phases: [
    { title: 'Recon', detail: 'map the system so experts do not re-derive it (haiku)' },
    { title: 'Expert Review', detail: '5 domain experts in parallel; model tier set by the depth arg' },
    { title: 'Cross-Check', detail: 'adversarial verification of high-impact claims (sonnet)' },
    { title: 'Synthesis', detail: 'orchestrator sequences work and writes the single document (opus)' },
    { title: 'Planner Sign-off', detail: 'financial planner reviews the final document, orchestrator applies edits' },
  ],
}

// ---------------------------------------------------------------------------
// args: { scope?: string, date?: string, outPath?: string, depth?: 'standard' | 'deep' }
//
// depth controls the model tier of the expert panel only. Recon is always haiku and
// synthesis/sign-off is always opus -- those tiers are not worth economising on.
//   standard (default): architect + planner on opus, the other three on sonnet
//   deep:               all five experts on opus
// ---------------------------------------------------------------------------
// args may arrive as an object or, depending on how the caller passed it, as a
// JSON string. A string silently fell through to every default on the first
// real run -- a `deep` request executed at `standard` and the report was named
// SYSTEM_REVIEW_undated.md. Normalise before reading any field.
let A = args
if (typeof A === 'string') {
  try { A = JSON.parse(A) } catch (e) { A = {} }
}
if (!A || typeof A !== 'object') A = {}

const scope = A.scope || 'the entire system'
const date = A.date || 'undated'
const outPath = A.outPath || `documentation/reports/SYSTEM_REVIEW_${date}.md`
const depth = A.depth === 'deep' ? 'deep' : 'standard'
if (date === 'undated') {
  log('WARNING: no date arg received -- report will be written to SYSTEM_REVIEW_undated.md.')
}
// Model for an expert whose charter is judgement-dense enough to want opus at standard depth.
const CORE = 'opus'
// Model for the remaining experts -- opus only when the caller asked for depth: 'deep'.
const AUX = depth === 'deep' ? 'opus' : 'sonnet'

const REPO_HINTS = `
Repository layout (verify before relying on it):
- src/            Python engine + server. Notable: src/dashboard_ui/, src/reporting/, src/projection_stages/,
                  src/server/, src/server_services/, src/http_runtime/, core.py, domain_models.py.
- frontend/       index.html, admin.html, css/, js/  -- the user-facing UI.
- tests/          ~200 numbered pytest modules + tests/frontend/.
- documentation/  design specs, plans, runbooks, release notes, reports/.
- tools/          operational scripts. input/, output/, reference_data/, saved_plans/ hold data.
Read documentation/CLAUDE.md and PROJECT_MANIFEST.md early -- they encode house rules.
NOTE: some tests overwrite files under input/. Do NOT run the test suite; read tests, do not execute them.
This review is READ-ONLY: no source edits, no commits. The only file written is the final report.
`

const FINDINGS_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['summary', 'findings'],
  properties: {
    summary: { type: 'string', description: '3-6 sentence state-of-the-domain assessment' },
    findings: {
      type: 'array',
      maxItems: 14,
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['id', 'title', 'evidence', 'impact', 'effort', 'options', 'recommendation'],
        properties: {
          id: { type: 'string', description: 'stable slug, e.g. arch-dead-compat-shims' },
          title: { type: 'string' },
          evidence: { type: 'string', description: 'concrete file:line references proving the finding is real' },
          impact: { enum: ['critical', 'high', 'medium', 'low'] },
          effort: { enum: ['S', 'M', 'L', 'XL'] },
          options: {
            type: 'array',
            minItems: 2,
            maxItems: 3,
            items: {
              type: 'object',
              additionalProperties: false,
              required: ['name', 'approach', 'tradeoff'],
              properties: {
                name: { type: 'string' },
                approach: { type: 'string' },
                tradeoff: { type: 'string' },
              },
            },
          },
          recommendation: { type: 'string', description: 'which option, and why' },
          risk: { type: 'string' },
          dependsOn: { type: 'array', items: { type: 'string' }, description: 'ids of other findings, if known' },
        },
      },
    },
  },
}

const VERDICT_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['id', 'refuted', 'reason'],
  properties: {
    id: { type: 'string' },
    refuted: { type: 'boolean', description: 'true if the evidence does not hold up when checked in the repo' },
    reason: { type: 'string' },
    correction: { type: 'string', description: 'restated finding if it was partly right' },
  },
}

// --- Phase 1: recon ---------------------------------------------------------
phase('Recon')
log('Mapping the system before the panel convenes...')

const RECON = [
  {
    key: 'code',
    prompt: `Map the Python/engine side of this repo. Produce a compact map: top-level modules and what each owns,
the data flow from inputs to outputs, obvious layering, and where the same responsibility appears in more than one place.
Cite file paths. Be terse -- this is a briefing for other reviewers, not a report.`,
  },
  {
    key: 'ui',
    prompt: `Map the user-facing surface: frontend/index.html, frontend/admin.html, frontend/js/, frontend/css/, and src/dashboard_ui/.
List the screens/tabs, the navigation model, and where UI state lives. Note anything that looks like a generated report
or workbook the user reads. Cite file paths. Be terse.`,
  },
  {
    key: 'tests-docs',
    prompt: `Map tests/ and documentation/. For tests: how they are organised, what layers they cover (unit / integration /
golden-master / frontend / e2e), and roughly where the mass sits. For documentation: what the live documents are versus
archived or superseded ones. Do NOT run any tests. Cite paths. Be terse.`,
  },
]

const recon = (await parallel(RECON.map(r => () =>
  agent(`${REPO_HINTS}\n\n${r.prompt}`, { label: `recon:${r.key}`, phase: 'Recon', model: 'haiku' })
))).filter(Boolean)

const BRIEF = `SYSTEM BRIEFING (from recon agents -- verify anything you rely on):\n\n${recon.join('\n\n---\n\n')}`

// --- Phase 2 + 3: experts, each cross-checked as soon as it lands -----------
phase('Expert Review')
log(`Depth: ${depth} -- architect/planner on ${CORE}, usability/documentation/quality on ${AUX}.`)

const COMMON = `${REPO_HINTS}\n\n${BRIEF}\n
Review scope: ${scope}.
Ground every finding in files you actually opened -- cite file:line. A finding with no evidence is worse than no finding.
For each finding give 2-3 genuinely different options (not strawmen) with tradeoffs, then recommend one.
Rank by impact, not by how much you enjoyed finding it. Cap at 14 findings; fewer, sharper is better.`

const EXPERTS = [
  {
    key: 'architect',
    model: CORE,
    prompt: `You are a systems architect reviewing this codebase.
Look for: dead code and unreachable branches; backward-compatibility shims that no longer have a caller and can be
retired; duplicated logic that should become shared/common code; modules that have grown past one responsibility and
should be decomposed into cohesive siblings; inefficient data flows (repeated recomputation, redundant passes, N+1 style
loading); and layering violations. Distinguish "unused today" from "load-bearing compat" -- prove it with a search before
you call something dead. Where you propose a decomposition, name the resulting modules and what each owns.`,
  },
  {
    key: 'usability',
    model: AUX,
    prompt: `You are a usability expert reviewing the user interface (frontend/ and any generated dashboards/reports).
Evaluate: workflow -- can a user complete a real task without backtracking; consistency of controls, labels, and
interaction patterns across screens; and above all information density. Every avoidable scroll and every avoidable click
is a defect: find places where content that belongs together is split across screens, where a value requires drilling in
to see, where a multi-step flow could be one screen, and where whitespace or oversized components push content below the
fold. Propose a more compact screen design where warranted -- describe the layout concretely (what moves where, what
collapses, what becomes inline). Note the assumed viewport(s) you are designing against.`,
  },
  {
    key: 'documentation',
    model: AUX,
    prompt: `You are a documentation and content expert. The reader is 60 years old, smart, and has little financial-planning
experience. Review all user-facing content: on-screen labels, helper text, tooltips, generated report and workbook prose,
and the user-facing docs under documentation/.
Judge every passage against: does a non-expert understand it; is the term defined the first time it appears; is it saying
something specific or is it boilerplate; and is it repeated somewhere else in the product. Flag redundant and boilerplate
text for deletion, not rewriting, where deletion is enough. Also check layout hygiene of rendered output: margins,
gutters, and column widths must be preserved -- flag anywhere text runs to the edge, columns collide, or content is
clipped in reports/workbooks/PDF output. Give exact before/after wording for your top rewrites.`,
  },
  {
    key: 'quality',
    model: AUX,
    prompt: `You are a test-quality enforcer. Review tests/ (read only -- do NOT execute the suite; some tests overwrite files
under input/).
Assess two axes. Redundancy: tests that assert the same behaviour as another test, tests pinned to implementation detail
rather than behaviour, and golden-master coverage that duplicates what unit tests already prove. Comprehensiveness: which
user-visible behaviours and failure modes have no test at all, with specific attention to functional coverage per module
and true end-to-end coverage of the real user journeys (data in -> projection -> dashboard/report out).
Propose a target test pyramid for this system: what should be unit, what integration, what golden-master, what e2e, and
what should be deleted. Name specific test files for consolidation or removal.`,
  },
  {
    key: 'planner',
    model: CORE,
    prompt: `You are a CFP-level financial planner with depth across retirement income, tax, estate, and inheritance planning.
You are reviewing this software as a practitioner, not as an engineer.
Assess: does the planning workflow match how a plan is actually built and revisited; are the modelling assumptions and
outputs ones a planner would defend; what does a client or planner need to see that the system does not currently show.
Propose enhancements across retirement (withdrawal sequencing, Roth conversion strategy, Social Security timing, RMDs,
Medicare/IRMAA), tax (multi-year bracket management, capital-gain harvesting, state considerations), and estate/inheritance
(beneficiary and titling review, step-up basis, gifting strategy, trust interaction, the SECURE Act 10-year rule, survivor
transition). For each, say what the system would have to compute and show. This is product guidance for a planning tool --
not personalised investment advice for any individual.`,
  },
]

const reviewed = await pipeline(
  EXPERTS,
  e => agent(`${COMMON}\n\n${e.prompt}`, {
    label: `expert:${e.key}`,
    phase: 'Expert Review',
    model: e.model,
    effort: 'high',
    schema: FINDINGS_SCHEMA,
  }),
  (res, e) => {
    if (!res) return null
    // Only the expensive claims get adversarially checked.
    const hot = res.findings.filter(f => f.impact === 'critical' || f.impact === 'high' || f.effort === 'L' || f.effort === 'XL')
    if (!hot.length) return { key: e.key, ...res }
    return parallel(hot.map(f => () =>
      agent(`${REPO_HINTS}\n
Adversarially verify this review finding by opening the files yourself. Your job is to REFUTE it if it does not hold.
Default to refuted=true when the cited evidence does not exist, is stale, or the claimed problem is actually load-bearing.
If it is real but overstated, set refuted=false and supply a corrected statement.

id: ${f.id}
title: ${f.title}
evidence: ${f.evidence}
recommendation: ${f.recommendation}`,
        { label: `verify:${f.id}`, phase: 'Cross-Check', model: 'sonnet', schema: VERDICT_SCHEMA })
    )).then(verdicts => {
      const byId = {}
      verdicts.filter(Boolean).forEach(v => { byId[v.id] = v })
      const kept = res.findings
        .filter(f => !(byId[f.id] && byId[f.id].refuted))
        .map(f => byId[f.id] && byId[f.id].correction ? { ...f, corrected: byId[f.id].correction } : f)
      const dropped = res.findings.filter(f => byId[f.id] && byId[f.id].refuted)
      if (dropped.length) log(`${e.key}: ${dropped.length} finding(s) refuted on cross-check`)
      return { key: e.key, summary: res.summary, findings: kept, refuted: dropped.map(f => ({ id: f.id, title: f.title, why: byId[f.id].reason })) }
    })
  }
)

const panel = reviewed.filter(Boolean)
log(`Panel complete: ${panel.map(p => `${p.key}=${p.findings.length}`).join(', ')}`)

// --- Phase 4: synthesis -----------------------------------------------------
phase('Synthesis')

const PACKET = JSON.stringify(panel, null, 1)

const SYNTH_BRIEF = `${REPO_HINTS}

You are the orchestrator. Five experts have reviewed ${scope}; their verified findings are below as JSON.

${PACKET}

Write ONE document to ${outPath} (create parent directories if needed). It must stand alone -- a reader who has not seen
this conversation can act on it. Required structure:

1. Executive summary -- the 5-8 things that matter, in plain language, with the expected payoff of each.
2. Panel findings by discipline -- architecture, usability, documentation/content, quality, financial planning.
   For each finding: what it is, evidence (file:line), the options considered with tradeoffs, and the recommendation.
   Keep options visible; the reader must be able to overrule you.
3. Cross-cutting analysis -- where experts agree, where they CONFLICT (name the conflict and resolve it explicitly with
   your reasoning), and what one change unlocks several others.
4. Recommendation -- the single coherent plan you are proposing, and what you are deliberately NOT doing and why.
5. Design -- for each accepted recommendation, the target-state design: modules and their responsibilities, screen layouts,
   content/wording changes, test-pyramid shape, new planning capabilities and what they must compute.
6. Implementation plan -- ordered workstreams with explicit dependencies. For each item: prerequisite items, effort (S/M/L/XL),
   risk, what proves it worked (the verification step), and whether it can run in PARALLEL with its siblings.
   Include a dependency-ordered wave table: Wave 1 / 2 / 3, with what runs concurrently inside each wave, and for each
   item the MINIMAL EFFECTIVE MODEL to execute it (haiku for mechanical sweeps, sonnet for scoped changes,
   opus for design-heavy or cross-cutting work) with a one-line justification.
7. Appendix -- findings refuted during cross-check, and open questions for the user to decide.

Rules: no invented file paths; every claim traceable to the packet or to a file you opened; write for a reader who is
technical but has not memorised this codebase. Do not modify any source file -- the report is the only write.
Return the absolute path of the file you wrote plus a 5-line summary of what is in it.`

const written = await agent(SYNTH_BRIEF, { label: 'orchestrator:synthesis', phase: 'Synthesis', model: 'opus', effort: 'high' })

// --- Phase 5: planner sign-off ---------------------------------------------
phase('Planner Sign-off')

const signoff = await agent(`${REPO_HINTS}

You are the CFP-level financial planner from the panel. Read the final review document at ${outPath}.
Judge it as the practitioner who has to live with the result: does the recommended plan serve the way real financial
plans get built and revisited? Is anything recommended that would degrade planning quality, hide a number a planner needs,
or mislead a 60-year-old non-expert reader? Is any planning capability mis-sequenced -- scheduled after work that depends on it?
Return specific, actionable edits: section, what is wrong, what it should say instead. If the document is sound, say so
plainly and list only genuine improvements.`, { label: 'planner:signoff', phase: 'Planner Sign-off', model: 'opus', effort: 'high' })

const revised = await agent(`${REPO_HINTS}

You are the orchestrator. The financial planner reviewed the document at ${outPath} and returned this:

${signoff}

Apply the edits that are correct. Where you disagree with the planner, do not silently drop the point -- record it in the
open-questions appendix as a noted disagreement with both positions stated. Then append a short "Planner Sign-off" section
summarising the planner's verdict and what changed as a result. Edit only ${outPath}.
Return a 10-line summary of the final document and the list of changes the planner caused.`, { label: 'orchestrator:revision', phase: 'Planner Sign-off', model: 'opus' })

return {
  document: outPath,
  depth,
  synthesis: written,
  plannerSignoff: signoff,
  revision: revised,
  counts: panel.map(p => ({ expert: p.key, kept: p.findings.length, refuted: (p.refuted || []).length })),
}
