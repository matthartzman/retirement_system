# Finding and Verification Schema

The structured finding register is the source of truth. The Markdown report is a readable synthesis, not a divergent copy.

## Required finding fields

```text
Finding ID
Title
Expert
Category
Severity
Confidence
Inspection status
Verification status
Evidence citations
Observed behavior
Impact
Affected workflows/scenarios
Root cause
Assumptions, jurisdiction, and rule year when relevant
GitHub contextual evidence when relevant
Options and tradeoffs
Recommendation
Dependencies
Implementation considerations
Risk of change
Verification method
Linked implementation-item IDs
```

Do not create CI-related findings. CI is an explicit review exclusion.

## Severity

- **Critical:** materially incorrect financial results, harmful financial guidance, data loss/corruption, severe privacy/security exposure, catastrophic workflow failure, or widespread calculation errors.
- **High:** significant incorrect results, major workflow failure, important financial-domain omission, substantial impact, major regression risk, or serious maintainability problem.
- **Medium:** meaningful functional, usability, documentation, test, or maintainability issue.
- **Low:** minor polish, wording, consistency, or low-impact debt.

Severity and effort are separate. Do not inflate severity because a finding is interesting.

## Confidence

Use `high`, `medium`, or `low`. Confidence reflects evidence quality, not impact severity.

## Options

Provide 2–3 real options when meaningful, including correctness, user impact, effort, maintenance, regression risk, financial implications, dependencies, and future flexibility. For objective correctness defects, state: `No credible alternative; this is a correctness defect.`

## Adversarial verification

Verify every Critical/High finding, material architecture or finance finding, medium/low-confidence finding, and scope-changing finding. Test evidence sufficiency, severity, mitigations, duplication, solution fit, counterexamples, possible greater impact, and unresolved assumptions.

Allowed dispositions: `confirmed`, `partially-confirmed`, `refuted`, `duplicate`, `superseded`, `insufficient-evidence`.

Retain material refuted, duplicate, superseded, and insufficient-evidence items in the final disposition appendix.

## Conflict record

```text
Conflict
Alternatives
Decision criterion
Decision
Rationale
Consequence
```

Default priority hierarchy: financial safety; data integrity; legal/regulatory correctness; security/privacy; functional correctness; maintainability; usability/accessibility; documentation; performance/cost; cosmetic polish.
