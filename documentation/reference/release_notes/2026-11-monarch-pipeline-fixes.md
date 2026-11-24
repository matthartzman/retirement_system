# Monarch pipeline fixes, November 2026

Two silent data gaps found while checking a manual Monarch refresh on 2026-11-24. No projection or
build result moves; the golden masters are unchanged.

## A category that goes back to an earlier value is now delivered

- **What went wrong.** The extractor keeps one outbox row per Monarch id and transaction state. When a
  transaction returned to a state it had been in before (category A, then B, then A, then B again), the
  last change landed on a row that had already been delivered and was dropped as a duplicate. The
  extractor's history and its "changed" count moved on, but the plan kept the old category.
- **Now.** A change always queues its row again: it becomes pending under the run that saw it, so the
  next import delivers it and acknowledges it with that run. A transaction seen for the first time still
  never replays an event that was already delivered, so a lost history file does not resend everything.
- A run whose "changed" count was higher than the rows it wrote was hitting this; the two now agree.

## The Monarch import no longer writes into a demo plan or a saved case

- **What went wrong.** The import writes into whichever plan is active. On 2026-11-15 the demo plan was
  open at 03:00, so that night's transactions, account-setup rows and the whole balance history went into
  `demo.rpx`. The household's own plan never received them, and the extractor was told the run was
  delivered.
- **Now.** The job writes only while a plan of kind *user* is active (a plan the registry does not know,
  such as a bare workspace, is written as before). With a demo plan or a saved case active it skips the
  run, says why on the Monarch status panel, exits 1 so Task Scheduler shows it, and acknowledges nothing:
  the extractor keeps the events pending, and the next run on your own plan delivers them.
- **Import now** follows the same rule: HTTP 400 with `skip_reason` `not_user_plan` and the explanation
  in `error` (see `API_CONTRACTS.md`).
