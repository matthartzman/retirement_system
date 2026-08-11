## Triage & Subagent Routing
- When a prompt is prefixed with `[SYSTEM DIRECTIVE: AUTOMATED TRIAGE ENFORCED]`, pass the evaluation task to `@triage-evaluator`.
- Do not attempt direct file edits until the `triage-evaluator` summary has been output and confirmed.