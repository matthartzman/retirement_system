# Runtime-Validation Policy

## CI is excluded

This skill does not inspect, resolve, summarize, or make claims about CI, GitHub Actions, workflow runs, jobs, checks, logs, or CI failures. CI is intentionally excluded from this review.

## Static validation

The default review is static and read-only. The Quality expert may inspect test structure, coverage intent, assertions, fixtures, mocks, edge cases, regression coverage, test redundancy, and determinism by reading repository files.

## Isolated runtime validation

Runtime validation is permitted only when an isolated disposable environment is explicitly available and all of the following hold:

- Source remains unchanged.
- Canonical inputs and production/personal data remain unchanged.
- Temporary artifacts remain outside the canonical project.
- Results can be captured safely.

If runtime validation is not performed, state exactly: `Runtime behavior was not validated during this review.`

Never state or imply that tests pass merely because test code was inspected.
