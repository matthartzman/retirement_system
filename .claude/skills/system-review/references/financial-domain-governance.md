# Financial-Domain Governance

For every tax, retirement, benefits, healthcare, estate, inheritance, beneficiary, or legal-rule finding:

- Identify jurisdiction and rule year, or state they are unknown.
- State whether the rule is configurable, hard-coded, sourced, or assumed.
- Classify authority as authoritative, secondary, user-provided, or unverified.
- Separate arithmetic correctness from suitability of advice.
- State whether qualified human professional review is required.
- Do not present planning assumptions as legal, tax, fiduciary, or benefits advice.

Where claimed or supported, assess household/filer composition, ownership, beneficiary designations, survivor status, retirement age, longevity, returns, sequence risk, withdrawals, account types, RMD/inherited-account paths, Social Security/survivor workflows, Medicare/IRMAA/healthcare assumptions, state/relocation tax assumptions, and estate/inheritance/remarriage scenarios.

If a feature is outside the declared product scope, classify it as a potential scope/workflow gap rather than automatically a calculation defect.

## Planner sign-off

The financial planner reviews the complete synthesized report and returns `approved`, `approved-with-changes`, or `not-approved`.

If required planner changes affect severity, recommendation, architecture, scope, priority, dependencies, test requirements, or assumptions, the orchestrator performs impact analysis and re-verification. Record unresolved dissent.
