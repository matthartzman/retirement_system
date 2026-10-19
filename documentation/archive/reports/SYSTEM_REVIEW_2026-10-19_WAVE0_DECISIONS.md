# System Review 2026-10-19 — Wave 0 Decision Record

Companion to `SYSTEM_REVIEW_2026-10-19.md` (section 9, Wave 0). Decisions recorded 2026-10-19 by the repository owner. No code changed. CI was intentionally excluded from the review.

## WI-001 — Trends-log backup (QA-001)

| Item | Decision |
|---|---|
| Remote visibility | Public |
| Clone/fork list | Owner verified (2026-10-19) that no clones or forks exist outside the owner's own copies |
| Chosen option | Purge history (git filter-repo, then force-push) after the HEAD fix |
| Follow-up | A separate scheduled task is required for the purge; with no external clones, no clone-notification step is needed beyond the owner's own copies, which must be re-cloned or reset after the force-push. Before purging, the owner reviews which account labels and balances the file holds and decides whether anything needs rotating or renaming. Never copy values from the file into any document. |

Exit criteria met: decision recorded. Purge itself is not scheduled yet (see open items).

## WI-002 — Scope and policy

| Item | Decision | Professional review |
|---|---|---|
| (a) Retiring before 59.5 (FIN-004) | In scope: model the 10% additional tax and its IRC 72(t) exceptions | CPA for the exceptions |
| (b) Earnings test (FIN-007) | In scope. Owner reviewed `income.py:322-396` on 2026-10-19 and confirmed the earnings test is missing; FIN-007 moves from insufficient_evidence to confirmed (owner-verified) | Benefits counselor or CPA |
| (c) Brokerage-gain MAGI phasing (FIN-001) | Two phases. Phase 1: IRMAA MAGI only, pinned separately. Phase 2: NIIT, ACA MAGI and Social Security taxation | Planner sign-off before each golden re-pin; CPA review recommended for phase 2 |
| (d) Monte Carlo headline (FIN-002) | "Funded as asked". The secondary "without using Roth for extras" figure is removed from the tile | Planner reviews the displayed success definition |
| (e) Federal estate defaults (FIN-009) | Derive the exemption from the household: single exemption for one-person households; married default only for couples with a portability election | Estate attorney |

Jurisdiction for all items: US federal (state rows are covered by WI-003). Rule year: statutory structure, with 2026 parameters from the dataset.

## WI-003 — External rule-value verification

Status: verified by the owner acting as advisor (2026-10-19), covering the checklist below. The per-row table of value, source citation and retrieval date was not supplied, so this record states the outcome only. Add the table here if it is needed for audit, and mark any row not individually verified as unverified.

- 2026 AMT exemption, phase-out start and rate (FIN-005)
- 2026 QLAC and QCD limits (FIN-011)
- NC, IN, CA and NY state rows, NY estate exemption (FIN-006)
- Part D base premium and Social Security wage-base status (FIN-006)
- SSA mortality table (FIN-006)
- Federal estate exemption and portability treatment (FIN-009)
- Current ACA enhanced-subsidy law

The estate-attorney review for FIN-009 portability and credit-shelter arithmetic is a separate requirement and is not covered by this verification.

## Other owner decisions (from the section 11 open questions)

- Monarch may be named in the README and UI; describe extraction as vendor-neutral, since more integrations are planned.
- Hosted use is planned: ARC-001 and ARC-009 (authentication, Host allow-list, remove `ALLOW_UNAUTHENTICATED_SAAS=YES`, non-loopback startup guard) are required before any hosted deployment.

## Purge status (2026-10-19)

The owner stated a history purge was done "as of 10/1/2026". A repository check did not support that for this file: `financial_trends_log.jsonl.bak` was added in commit 0bd50f3 (#215, 2026-10-14, after 10/1) and was still tracked and in history on `main`.

Executed 2026-10-19 on the owner's explicit instruction ("Full purge now"):

- The file was removed from every commit with git-filter-repo and `main` was force-pushed (new head e363ce4). All commit hashes on `main` changed.
- `.gitignore` now ignores all of `financial_trends_reporter/data/` except `.gitkeep`.
- `tests/test_repo_hygiene_guards.py::test_trends_data_dir_tracks_only_gitkeep` fails if anything but `.gitkeep` is tracked there. It passes on the clean tree and fails with a planted `.bak` file. The wider test suite was not run.
- Only two branches existed on the remote; both were rewritten.

**Residual exposure (open).** GitHub keeps read-only pull-request refs (`refs/pull/N/head`) that a push cannot rewrite. PR #215's ref was fetched after the purge and still contains the file, so anyone with the old commit hash can reach it. Closing this needs GitHub Support to remove the cached views and PR refs for the old commits. Until then QA-001 is mitigated, not closed.

Owner follow-ups: contact GitHub Support (old commit 0bd50f3); decide whether account names or balances in the file need changing; re-clone or hard-reset any other local copy.

## Open items blocking Wave 1

1. GitHub Support request for the residual PR refs (QA-001 stays open until done).
2. Optional: the per-row WI-003 verification table, if an audit trail is wanted.
