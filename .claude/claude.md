## Triage & Subagent Routing
- When a prompt is prefixed with `[SYSTEM DIRECTIVE: AUTOMATED TRIAGE ENFORCED]`, pass the evaluation task to `@triage-evaluator`.
- Do not attempt direct file edits until the `triage-evaluator` summary has been output and confirmed.

## Design Specs & Implementation Plans
- For each phase/step/task of an implementation plan:
    - Include recommended model and effort
    - Estimate expected Claude Code usage:
        - approximate tokens needed, 
        - what's driving context size (file sizes, search scope, test-loop iterations), and 
        - whether it's light/moderate/heavy relative to a 5-hour session on my ProPlan.
- Flag any step likely to be disproportionately expensive (broad searches, large file reads, repeated test-fix cycles) and suggest ways to scope it down. 
- Give relative estimates, not fabricated token count. Include a note to check /usage against these estimates as the plan executes.