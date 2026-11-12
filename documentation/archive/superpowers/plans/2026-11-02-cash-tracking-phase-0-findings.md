# Cash tracking: Phase 0 findings

Date: 2026-11-02.

Status: implemented (findings document; merged to main as PR #343 on 2026-11-02)
(section 6, Phase 0). Read-only: no code changed. Account numbers are deliberately left out (account-number protection
plan); accounts are named by type. Evidence for (c) and (d) is the owner's real downloads of 2026-10-31, kept outside
the repo.

## (a) Does confirming a sale credit the CASH lot? **No.**

`src/sales_confirm.py` has no reference to cash or the `CASH` symbol; `confirm_in` only reduces or removes the sold
lot's shares, and `undo` restores them. Consequences:
- Nothing in the app moves an Investment account's `CASH` lot when a buy, sale, dividend or contribution happens.
- This matches the integration note's rule (1.2): the confirm path stays cash-free, and the ledger plus the anchored
  import write the balance. No change to `confirm_in`/`undo` is needed for cash.
- `src/reconcile.py` writes a `CASH` lot only for an account whose holdings are exactly one `CASH` lot
  (`reconcile.py:632-643`). An Investment account that holds securities and a `CASH` lot is therefore not writable by the
  existing reconcile code, so cash Phase 4 needs a new write path rather than reusing it.

## (b) Are the kept investment-account cash rows counted in spending? **Partly: some are, wrongly.**

The Spending Budget Tracker (`spending_tracker.py:1366-1402`) classifies every stored row with
`_shared_ytd_class`, which is `classify_cash_transaction` (`ytd_tracking.py:863`). It does not look at the account's
role and does not filter Investment accounts. For the rows kept after the 2026-10-31 purge:

| Kept category | Effect today |
|---|---|
| Transfer, 401k Contribution, 401K Match | Excluded (`EXCLUDED_SPENDING_CATEGORIES`, `ytd_tracking.py:137`) |
| Financial Fees | **Counted as spending** (negative amount, no exclusion) |
| Uncategorized (negative) | **Counted as spending** |
| Other Income (positive) | **Counted as income** (`ALLOWED_INCOME_CATEGORY_KINDS`) |

So a fee charged inside an IRA lowers household spending capacity, and misc income inside an account counts as
household income. A role-aware classifier already exists (`classify_investment_transaction`, `ytd_tracking.py:892`, used
by `classify_transaction(..., role="Investment")`) but the spending tracker does not use it.
- Impact on the cash plan: Phase 6 ("exclude non-external flows from spending") is a real fix, not a check. It should
  route Investment-role rows through the role-aware classifier, so only an external withdrawal reaches spending.
- Run `tools/regen_golden_master.py measure` before the change; it will move spending figures if the real plan has such rows.

## (c) What does Fidelity's `Cash Balance ($)` include? **Core cash plus the sweep fund. It is usable as an anchor.**

Three Fidelity history files (one HSA account; ranges overlap) were checked.
- The column is filled on every row (103 of 103 across the files), newest row first.
- It reconciles with the amounts: in the file for 2026-02-05 to 2026-10-30, the balance change between consecutive
  rows equals the row's amount for 28 of 37 rows.
- The 9 exceptions are all the monthly "REINVESTMENT FIDELITY GOVERNMENT CASH RESERVE" rows, where the balance does not
  move. The matching "DIVIDEND RECEIVED" row already raised the balance, so dividends reinvested in the sweep fund stay
  in the balance. The balance therefore **includes the money-market fund**, which agrees with owner decision 1.
- Design consequence: the sweep reinvestment leg must be excluded from the ledger as internal (cash 4.2) or the ledger
  double counts the dividend. The tests for the ledger builder should use exactly this pair.
- Anchor choice stays as planned: the balance on the newest row of the newest file (here a small balance, about 44
  dollars, as the account holds mostly funds). Overlapping files give two anchors for the same days; they should agree,
  and a mismatch is worth surfacing.
- Not yet checked: a Fidelity account that holds a core cash position other than the Government Cash Reserve fund, and
  the days around a file boundary.

## (d) What do E*Trade and Vanguard files say about contributions and withdrawals?

**E\*Trade (four files, 2025-02-01 to 2026-10-30; no running balance column).** Columns: dates, `Activity Type`,
`Description`, `Symbol`, `Quantity #`, `Price $`, `Amount $`, `Commission`. Contrary to the earlier assumption, the files
**do** carry contributions and withdrawals:
- Individual 401(k): 48 `Contribution` rows (ACH deposits, employer, employee deferral), `Distribution` rows (direct
  rollover, wire out), a `Service Fee`, `Misc Income`.
- Roth IRA: `Distribution` rows, including a transfer to another own account.
- Rollover IRA and Trust: `Transfer`, `Online Transfer`, `Funds Received`, `Funds Transferred`, `Redemption`,
  `Margin Interest`, `Adjustment`.
- Own-account cash moves exist in both directions with a reference id (for example Roth to Trust, 2025-07-03), so
  pairing by amount and date plus the reference is possible; the reference id gives more than the ±3-day rule alone.
- The "TRNSFR CASH TO MARGIN / MARGIN TO CASH" and `Adjustment` rows are internal journals (38 `Transfer` and 14
  `Adjustment` rows in the Trust file), paired plus and minus inside one account. They are the cash plan's "Adjustment"
  class and must net to zero.
- In-kind transfers have a symbol and quantity but no price or amount (for example a "TFR FROM ACCT" row); cash plan
  and log plan agree these go to the log, not the cash ledger.
- Consequence for source precedence (4.4): for E*Trade, the file carries the flows the cash plan expected to take from
  Monarch, so the Monarch rows are needed only for days no file covers. There is still no running balance, so these
  accounts are anchored by the last confirmed `CASH` lot, not by the file.

**Vanguard (one file, three accounts, 310 rows, 2025 only; no running balance).** Checked on 2026-11-02:
- Cash flows are present: `Rollover (incoming)` and `Transfer (incoming)` with CASH (cash in), `Transfer (incoming)` with a
  symbol and shares (in kind, with an amount), `Transfer (Outgoing)`, `Withdrawal` ("To: <bank>"), `Distribution` (a Roth
  distribution), `Funds Received`, `Interest`, and a `Corp Action (Redemption)`.
- The VMFXX money-market settlement fund appears as `Sweep in` / `Sweep out` rows (39 of 310). They are internal and
  must be excluded from the ledger, as for Fidelity.
- The trailing `Account Type` column is misaligned on some rows (amounts appear in it), so a parser must not rely on it.
- A multi-account file means rows must be split by the account number before the cash ledger is built.
- The file ends in 2025, so it does not reach today: a Vanguard account anchors on a confirmed balance on or near the
  file's last date, not on the current `CASH` lot alone. A 12/31/2025 balance per account would serve as that anchor
  and as a check.

## What this changes in the plans

1. Cash Phase 6 becomes a defined fix: route Investment-role rows through `classify_investment_transaction` in the
   spending tracker. Size it after a `measure` run.
2. Cash Phase 4 needs a new `CASH`-lot write path for accounts that also hold securities; `reconcile.py` cannot do it.
3. Cash Phase 1 stands: parse Fidelity `Cash Balance ($)`. Add a ledger test for the dividend plus sweep reinvestment pair.
4. Cash Phase 2 can read contributions and withdrawals from E*Trade files; Monarch fills only uncovered days.
5. Open: 12/31/2025 cash balances for the E*Trade and Vanguard accounts (a check, not a blocker), and the large-change warning threshold (set it from the real data before Phase 4).

Next: Phase 1 (parse running balance; schema migration with backup), after confirming the next free schema version with
the log phase 2 work now in progress.
