# Review Criteria

## Panel

| Role | Charter |
|---|---|
| Architect | Architecture, efficiency, dead code, compatibility shims, modularity, coupling, reuse, data flow, performance |
| Usability / Accessibility | Workflow, consistency, compactness, readability, accessibility, cognitive load, error handling |
| Documentation | Clarity for a 60-year-old non-expert, accuracy, discoverability, terminology, redundancy, layout |
| Quality | Test coverage, boundaries, regression risk, testability, determinism, and static test-quality assessment |
| Financial Planner | Retirement, taxation, benefits, healthcare, estate, inheritance, beneficiaries, survivor scenarios, domain correctness |
| Orchestrator | Recon, dependencies, evidence, GitHub work context, deduplication, conflicts, synthesis, waves, validation, consistency |

Run the five expert reviews in parallel after creating the shared map and coverage matrix. The orchestrator is not a sixth expert.

## Explicit CI exclusion

Do not evaluate CI, GitHub Actions, workflow configuration outcomes, run failures, job failures, checks, logs, or CI remediation. Do not mention CI health as a positive or negative system characteristic.

## GitHub review context

The orchestrator must include relevant open/flagged GitHub issues, pending work, open pull requests, and recent merged pull requests in coverage or finding context. Categorize each as confirmed, contextual-only, resolved, duplicate, out-of-scope, or insufficient evidence.

GitHub metadata does not replace direct file evidence. A merged PR establishes context and change provenance but must be corroborated before it establishes product behavior or full design completion.

## Coverage matrix

At minimum assess applicability of architecture, calculation engine, financial logic, retirement/tax/benefits/healthcare/estate/survivor workflows, data integrity, validation, precision, dates, UI, accessibility, performance, privacy/security, documentation, testing, configuration, persistence/import/export, error handling, and logging/observability.

For each area record inspection status, evidence, responsible expert, findings, and residual uncertainty. CI is not a coverage category.

## Cross-cutting checks

### Calculation correctness

Inspect rounding, precision, compounding, inflation, tax brackets, marginal/effective rates, annual/monthly conversion, dates, withdrawals, account sequencing, depletion, deterministic behavior, and Monte Carlo assumptions where applicable.

### Boundaries and scenarios

Consider early/late retirement, claiming and RMD boundaries, depletion, zero/large balances, income extremes, high inflation, poor returns, longevity, either spouse’s death, survivor household, remarriage, beneficiaries, inherited accounts, and missing inputs where applicable.

### Data integrity

Inspect missing/invalid/duplicate values, units, stale data, ownership, household relationships, serialization, migrations, imports/exports, and rounding/storage mismatch.

### Security and privacy

Where applicable inspect financial-data exposure, secrets, auth, permissions, logs, exports, backups, integrations, AI disclosure, and sensitive error messages. Secret scanning may be considered only as security evidence, not as CI evidence.

### Accessibility

Inspect font/contrast, keyboard/focus, semantics, screen-reader support, touch targets, errors, cognitive load, and terminology. Do not equate age-friendly design with accessibility.

## Implementation waves

Each work item contains ID, change, finding IDs, dependencies, priority, effort, risk, owner, parallel group, validation, exit criteria, and model tier. Do not call work parallel when shared components or unresolved dependencies prevent it.
