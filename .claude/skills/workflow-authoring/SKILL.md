---
name: workflow-authoring
description: Script API and preflight for Workflow scripts (e.g. .claude/workflows/system-review.js). Use before writing, editing, or running a Workflow script, and before running /system-review.
---

# Workflow authoring

Project-local reference for the script API that `.claude/workflows/*.js` are written against. It was reconstructed from `.claude/workflows/system-review.js`; if the Claude Code client ships an official `workflow-authoring` skill, prefer that one.

## Preflight (do this before running any workflow)

1. Confirm a `Workflow` tool is in your tool list. This skill documents the API; it does not provide the tool.
2. If there is no `Workflow` tool (for example in a cloud session), stop and tell the user. Do not simulate the workflow by hand. Suggest running in a client that has the Workflow tool.
3. Confirm the script file exists (`ls .claude/workflows/<name>.js`).
4. Confirm every required arg is ready. The runtime has no clock or filesystem, so callers supply dates and paths.

## Invocation

```text
Workflow({ scriptPath: ".claude/workflows/<name>.js", args: { ... } })
```

Invoke by `scriptPath`, not `name`, unless the workflow is registered.

## Script shape

- ES module. `export const meta = { name, description, whenToUse, phases: [{ title, detail }] }`.
- Top-level `await` is allowed. Globals: `args`, `agent`, `parallel`, `pipeline`, `phase`, `log`, `budget`.
- No filesystem, clock, or network in the script itself. Delegate all I/O to `agent()` calls.

## API

- `phase(title)`: mark the current phase; titles match `meta.phases`.
- `log(message)`: progress line shown to the user.
- `agent(prompt, opts)`: run a subagent, resolves to its result, or a falsy value if it failed (always null-check). `opts`: `label`, `phase`, `schema` (JSON Schema; the result is parsed structured output), `effort` (`low|medium|high`).
- `parallel([() => agent(...), ...])`: run thunks concurrently; resolves to results in order (failed entries falsy).
- `pipeline(items, stage1, stage2, ...)`: run each item through the stages independently. A stage is `(prevResult, item) => value|Promise`. Items proceed without waiting on each other.
- `args`: caller-supplied object. Validate it at the top and throw clear errors.

## Conventions

- Put shared rules in a `RULES` string prepended to every agent prompt (read-only limits, scratch dir, evidence rules).
- Pass large intermediates between agents as files in a scratch directory outside the project, not through prompts.
- Treat any agent result as possibly missing and record the gap instead of crashing, unless the stage is essential (then `throw`).
- Never overwrite existing outputs; probe candidate paths.
- Keep effort low for mechanical stages and high only for reasoning stages, to limit tokens.

## Fallback runner (no native Workflow tool)

`.claude/workflows/run.mjs` executes a workflow script in plain Node, running each `agent()` as a headless `claude -p` subprocess (needs the `claude` CLI on PATH and Node 18+):

```text
node .claude/workflows/run.mjs .claude/workflows/system-review.js '{"date":"YYYY-MM-DD","scratch":"<abs dir outside project>"}'
```

Options: `--args-file f.json`, `--concurrency 4`, `--permission-mode auto`, `--dry-run` (no agents; validates the script). Progress goes to stderr. Limitations: `budget` is an empty object, and each agent is a fresh session with no shared context beyond its prompt.
