# Cash tracking and transaction log: integration

Date: 2026-11-02.

Status: implemented (merged to main as PRs #349, #351, #353 and #354, 2026-11-02)

Settles where two plans overlap, so neither is built in a way the other has to undo:
- `2026-10-31-transaction-log-design-and-plan.md` (the "log")
- `2026-10-31-investment-account-cash-tracking-design-and-plan.md` (the "cash plan")

The two stay separate documents. The cash plan's phases 0 to 3 and the log's phases 1 and 2 do not depend on each other and
can ship in either order. This note governs the points where they meet, and defines one combined phase.

## 1. Decisions

### 1.1 Who writes which holdings rows (**Claude's call**)
- The log's `materialize` (log 3.7) rewrites a managed account's `holdings_lots` rows **except the `CASH` lot**. It leaves
  `CASH` untouched.
- The cash ledger (cash 4.5) is the only writer of the `CASH` lot, for managed and unmanaged accounts alike.
- Money-market sweep rows are never log rows (they are not `buy`/`sell` kinds), so the log ignores them; the cash ledger
  counts them as cash (cash decision 1).
- Test: `test_materialize_leaves_cash_lot_untouched`, and an import that moves the balance does not change the managed
  account's other lots.

### 1.2 Sale confirmation edits the path once (**Claude's call**)
- Cash gap 2 asks whether confirming a sale credits the `CASH` lot. Cash Phase 0(a) answers it first.
- Whatever it finds, for an account whose cash comes from a broker file the **confirm path must not credit `CASH`**: the
  sale settlement is already a ledger row, and the anchored import writes the balance (cash decision 4). Crediting in
  confirm as well would count the proceeds twice.
- Log task 3.2 (managed sell goes through the log) and any cash change to `confirm_in`/`undo` land in the same task, in
  one edit of those functions.

### 1.3 One transfer pairing (**Claude's call**)
- Build the pairing once, in cash Phase 3, as a function the log's importer also uses (log task 2.7).
- A parsed transfer row is **in kind** when it has a symbol and shares, and **cash** when it has an amount only. In-kind
  rows go to the log (`transfer_out`/`transfer_in`, `transfer_group`); cash rows go to the cash ledger. The cash ledger
  shows an in-kind transfer as a zero-cash line, never as a flow.
- Same rule for both: pair only when exactly one candidate exists within 3 days; leave the rest unmatched.
- A transfer that carries both a security and cash (for example a full account move) is two rows, one of each kind.

### 1.4 Schema version numbers (**Claude's call**)
- Neither plan fixes its version number. Each migration takes the next free version when it merges. The log's `v20` and
  `v21` and the cash plan's Fidelity balance column are all "next version". Update any test that asserts the number.

### 1.5 Shared housekeeping
- Both add panels to the Sales Ledger page area. Whichever merges second rebases its `TOTAL_JS_MAX_LINES` note and
  regenerates `SYSTEM_ARCHITECTURE_DIAGRAM.md`.
- Both use `accountDisplayLabel` and show masked account names only (account-number protection plan).

## 2. Sequence

1. Cash Phase 0 (verification). Run first; it decides 1.2 and sizes the rest.
2. In either order: cash Phases 1 to 3, and log Phases 1 and 2. Pairing (cash 3) comes before log task 2.7.
3. **Combined phase** (section 3), only after both gates:
   - log gate: `reconcile` shows zero drift through one more real import cycle;
   - cash gate: ledger builder and pairing merged, and cash difference against the `CASH` lot explained on the real plan.
4. Cash Phase 5 (screen) may ship before or after the combined phase.

## 3. Combined phase: ownership, confirm path and engine checks

Replaces log tasks 3.1 and 3.2 and cash Phases 4 and 6 as one unit of work, split into tasks below. Log task 3.3
(per-account switch-over with golden check) follows unchanged.

**Task C.1: managed-account state and `materialize` (log 3.1 with decision 1.1)**
- Files: `src/stores/transactions_repo.py`, `src/transactions.py`; test `tests/test_transactions_materialize_unit.py`.
- Tests: those listed under log 3.1, plus `test_materialize_leaves_cash_lot_untouched`.
- Model/effort: Opus, high. Usage: heavy. Driver: the replay and materialize tests; keep fixtures small.

**Task C.2: anchored balance and automatic `CASH` write (cash Phase 4)**
- Files: the reconcile/cash module (Grep to the cash-lot code; 53 Monarch references, do not read whole); new tests.
- Tests: anchored import writes the balance with old and new values and an undo; unanchored import writes nothing;
  large-change warning; a managed account's import does not touch its other lots.
- Model/effort: Opus, high. Usage: moderate-heavy.

- **Built 2026-11-02 (C.2):** `src/cash_anchor.py`, wired into `src/broker_import.py` (preview shows old/new and the warning; commit writes the lot; `revert` is the undo and refuses if the lot was edited since). No schema change: old and new values live in the import's `summary.cash_write`. Anchor 1 only (the file's latest running balance, today Fidelity); an unanchored file, an account with no single `CASH` lot, or a file ending before the lot's date writes nothing. Large-change threshold is provisional (over $1,000 and over 25% of the old balance); the owner sets it from real data. Anchor 2 (confirmed lot plus flows) was added 2026-11-03: cash plan section 12. Tests: `tests/test_cash_anchor_unit.py`.

**Task C.3: confirm path and holdings editor (log 3.2 with decision 1.2)**
- Files: `src/sales_confirm.py` (`confirm_in`/`undo`, read only those), `frontend/js/dashboard_decomp_holdings.js`
  (grep the row renderer).
- Tests: those listed under log 3.2, plus `test_confirm_does_not_credit_cash_for_broker_covered_account`.
- Model/effort: Opus, high. Usage: heavy. Run `tests/test_sales_*` and `tests/test_broker_*` after each edit, the full
  suite once.

**Task C.4: engine and spending checks (cash Phase 6)**
- Confirm the engine treats the `CASH` lot per account class; exclude non-external flows from spending.
- Run `tools/regen_golden_master.py measure` first. Never regenerate in a loop; verify one delta by hand.
- Model/effort: Opus, high. Usage: moderate to heavy if golden masters move.

**Built 2026-11-02 (C.3):** the log half (managed sell through the log, Monarch confirm refused, read-only holdings rows) shipped in #349; the cash half, `test_confirming_a_sale_does_not_credit_cash`, shipped with C.2 (#353). Nothing further.

**Built 2026-11-02 (C.4, spending half):** `spending_tracker.load_transactions_extended` flags rows of Investment-role accounts and `_shared_ytd_class` treats them as transfers, so fees, misc income and contributions inside an investment account no longer count as household spending or income (Phase 0 finding (b)); an external withdrawal reaches spending once, as the checking-side row. Golden master `measure` unchanged. Test: `tests/test_spending_investment_cash_excluded_unit.py`. Not done: the engine's per-account-class treatment of the `CASH` lot and the `excess_return` / pair-status tax rules (cash plan section 8, items 4 and 5): they need the pairing wired into a screen and are left for the owner's call.

Usage is relative to a 5-hour Pro session; check `/usage` against these as the work proceeds. Expected total: two to
three sessions. The expensive risks are C.3 (two hot paths, large JS file) and C.4 (golden-master loops); scope them by
running single test files while iterating.

## 4. Anti-goals

- Two writers for the `CASH` lot, or a materialize that deletes it.
- Sale proceeds counted twice (confirm and import).
- A transfer counted as spending or income, or an in-kind transfer shown as a cash flow.
- Any engine, workbook or golden-master change not explained by an owner-approved cash correction.

**Built 2026-11-02 (C.4, engine half):** CASH-lot audit recorded in the cash plan section 10 (no engine change, golden master MATCH); the Cash panel reports withdrawals by pair status and returned excess contributions, report only. The engine does not use the pair-status rule yet (owner approval first).
