#!/usr/bin/env node
// Standalone Workflow runner: executes .claude/workflows/*.js scripts outside a client that has a
// native Workflow tool. Each agent() call is a headless `claude -p` subprocess.
//
// Usage: node .claude/workflows/run.mjs <script.js> '<args-json>' [--args-file f.json]
//        [--concurrency 4] [--permission-mode auto] [--dry-run]
// Env:   CLAUDE_BIN overrides the claude executable (used by tests).
import { spawn } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const argv = process.argv.slice(2)
const opt = (name, dflt) => {
  const i = argv.indexOf(`--${name}`)
  if (i < 0) return dflt
  const [, v] = argv.splice(i, 2)
  return v
}
const flag = name => { const i = argv.indexOf(`--${name}`); if (i < 0) return false; argv.splice(i, 1); return true }
const argsFile = opt('args-file')
const CONCURRENCY = Number(opt('concurrency', 4))
const PERMISSION = opt('permission-mode', 'auto')
const DRY = flag('dry-run')
const [scriptArg, argsJson] = argv
if (!scriptArg) {
  console.error('usage: run.mjs <script.js> [args-json] [--args-file f] [--concurrency n] [--permission-mode m] [--dry-run]')
  process.exit(2)
}
// Dry-run stub: a minimal value satisfying a JSON Schema's required fields.
function stub(sc) {
  if (!sc) return ''
  if (sc.enum) return sc.enum[0]
  const t = Array.isArray(sc.type) ? sc.type.find(x => x !== 'null') : sc.type
  if (t === 'object') {
    const o = {}
    for (const k of sc.required || []) o[k] = stub((sc.properties || {})[k])
    return o
  }
  if (t === 'array') return []
  if (t === 'boolean') return true
  if (t === 'integer' || t === 'number') return 1
  return 'x'
}
const CLAUDE = process.env.CLAUDE_BIN || 'claude'

// ---- simple semaphore so parallel() cannot spawn unbounded subprocesses
let active = 0
const waiters = []
const acquire = () => active < CONCURRENCY ? (active++, Promise.resolve()) : new Promise(r => waiters.push(r))
const release = () => { const w = waiters.shift(); if (w) w(); else active-- }

let currentPhase = ''
const stamp = () => new Date().toISOString().slice(11, 19)
const log = msg => console.error(`[${stamp()}] ${msg}`)
const phase = title => { currentPhase = title; console.error(`\n== ${title} ==`) }

function runClaude(prompt, o) {
  const a = ['-p', '--output-format', 'json', '--permission-mode', PERMISSION]
  if (o.schema) a.push('--json-schema', JSON.stringify(o.schema))
  if (o.effort) a.push('--effort', o.effort)
  if (o.model) a.push('--model', o.model)
  return new Promise(res => {
    const p = spawn(CLAUDE, a, { stdio: ['pipe', 'pipe', 'pipe'] })
    let out = '', err = ''
    p.stdout.on('data', d => out += d)
    p.stderr.on('data', d => err += d)
    p.on('error', e => res({ ok: false, why: e.message }))
    p.on('close', code => res(code === 0 ? { ok: true, out } : { ok: false, why: `exit ${code}: ${err.slice(-300)}` }))
    p.stdin.end(prompt)
  })
}

// Resolves to the parsed result (object when a schema is given, else text); null on failure.
async function agent(prompt, o = {}) {
  const label = o.label || 'agent'
  if (DRY) { log(`[dry-run] ${label}`); return o.schema ? stub(o.schema) : '' }
  await acquire()
  try {
    log(`start ${label}${o.phase ? ` (${o.phase})` : ''}`)
    const r = await runClaude(prompt, o)
    if (!r.ok) { log(`FAILED ${label}: ${r.why}`); return null }
    let j
    try { j = JSON.parse(r.out) } catch { log(`FAILED ${label}: unparseable output`); return null }
    if (j.is_error) { log(`FAILED ${label}: ${String(j.result).slice(0, 200)}`); return null }
    log(`done  ${label}`)
    if (!o.schema) return j.result ?? ''
    if (j.structured_output) return j.structured_output
    try { return JSON.parse(j.result) } catch { log(`FAILED ${label}: no structured output`); return null }
  } finally { release() }
}

const settle = t => Promise.resolve().then(t).catch(e => { log(`task error: ${e.message}`); return null })
const parallel = thunks => Promise.all(thunks.map(settle))
const pipeline = (items, ...stages) => Promise.all(items.map(async item => {
  let v = item
  for (const s of stages) { v = await settle(() => s(v, item)); if (v === null) return null }
  return v
}))

const args = argsFile ? JSON.parse(readFileSync(argsFile, 'utf8')) : JSON.parse(argsJson || '{}')

// Scripts use function-body semantics (top-level await and `return`), so wrap rather than import.
const src = readFileSync(resolve(scriptArg), 'utf8').replace(/^export\s+const\s+meta\b/m, 'const meta')
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor
const names = ['args', 'agent', 'parallel', 'pipeline', 'phase', 'log', 'budget']
const result = await new AsyncFunction(...names, src)(args, agent, parallel, pipeline, phase, log, {})
console.log(JSON.stringify(result ?? null, null, 2))
