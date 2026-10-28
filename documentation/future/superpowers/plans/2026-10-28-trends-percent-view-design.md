# Financial Trends — Percent View (design, draft for review)

Status: approved. Decisions made 2026-10-28 (§7); implementation plan written.

## 1. Goal

Let a viewer see the *shape* of the finances (growth, mix, pace of spending) without seeing dollar amounts.
A per-person setting in **People & Activity** picks **$**, **%** or **Both**. "Both" shows a **$ | %** toggle
next to the *Financial Trends* title. The owner on the PC (local listener, 5057) is "Both" by default.

## 2. The decision that shapes everything: privacy screen or security boundary?

| | Privacy screen | Security boundary |
|---|---|---|
| Protects against | Shoulder-surfing, screen-sharing, a casual glance | A signed-in person who should never learn the amounts |
| Where % is computed | Browser (the page already has the dollars) | **Server**, per session; dollars never leave the PC |
| Cost | Light | Moderate–heavy: every money endpoint gets a ratio form |

**Recommendation:** treat a remote person set to **%** as a security boundary. With client-side conversion the
dollars are still in `/api/history`, `/api/spending`, `/api/live-snapshot` etc., and one look at DevTools shows them.
"Both" and "$" can convert in the browser.

## 3. What each number becomes (numerator / denominator)

Rule: every % shown must have a denominator the viewer **cannot** turn back into dollars from other things on screen.

| Screen | Dollar figure today | Percent form (recommended) | Alternative | Watch out for |
|---|---|---|---|---|
| Net Worth chart | NW on each day | % change since the first day in the Time scope: `NW_t / NW_0 − 1` | Index, first day = 100 | NW_0 ≤ 0 or near 0 → meaningless; fall back to "n/a". Changing scope rebases the line, so 1W and YTD look unrelated. |
| Liquid Investments and Cash | Balance per day | Same % change since scope start | Share of Net Worth (`liquid / NW`) as a second line | Same as above |
| Investment Net Flows | $ in / out | Flows as % of liquid balance at scope start; split the period's change into **flows %** + **market %** (they add to the total %) | Flows as % of income | This is the most useful % view; it answers "did it grow because I saved or because markets rose?" |
| Tax line (taxable accounts) | Estimated tax $ | % of taxable balance | Hide | Small numbers; one decimal |
| Spending categories | $ per category | % of total spending in the period | % of budget used (the budget marker already is a ratio) | Refunds make a category negative; budget of 0 → divide by zero |
| Spending markers | Prior year, period budget, full-year budget | Marker positions are already relative; label them as % of bar | — | Fine as is |
| Merchant / transaction levels | $ per merchant / txn | % of the category | **Hide for %-only people** | See §4: one known bill decodes everything |
| Live Snapshot holdings | $ per account / lot | % of portfolio (allocation) | — | Lot-level detail with % of lot cost reveals little; account-level is fine |
| Live Snapshot reconciliation | $ differences | **Hide for %-only people** | Difference as % of the account | A 0.1% gap on a large account is a real $ problem; % hides it. Owner work, not a guest view |
| Axis ticks, tooltips, CSV / copy | $ | % with sign (+3.2%) | — | Every label path must switch, not just the chart lines |

## 4. Unintended consequences and challenges

1. **One known amount decodes everything.** If a viewer knows the mortgage is $2,400 and sees Housing = 18% of
   spending, they know total spending, and from it every category. Same for "my contribution was $23,000" against
   Net Flows %. Mitigations: hide the transaction and merchant levels for %-only people; don't show two % series
   that share a denominator *and* a known anchor; round to whole % on the guest view.
2. **Percent of a moving base misleads.** −20% then +20% is not back to even. Show change from a fixed start, never
   day-to-day % chained.
3. **Rebasing on every scope change.** A 1-week chart starts at 0%; a YTD chart starts at 0% on Jan 1. Viewers may
   compare them as if they shared a base. Label the base: "% change since 30 Sep 2026".
4. **Small or negative denominators.** Near-zero or negative Net Worth, accounts that open mid-period, debts.
   Need a defined "n/a" rule, not a 4,000% spike.
5. **Reconciliation and data-quality warnings lose meaning.** Missing-price notes and balance warnings mention $;
   reword or hide for %-only people.
6. **Activity log and errors.** Error messages and log details must not carry amounts to a %-only person.
7. **Test burden.** Every new money field added later must also get a % form or be withheld. Needs a guard test
   (§6) or the leak returns silently.
8. **Two code paths in charts.js.** Formatting is spread across chart functions; a single `fmtMoney()` /
   `fmtValue(mode)` seam is a prerequisite, otherwise each chart diverges.

## 5. Alternatives considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **A. Per-person $ / % / Both (this design)** | Fits the request; reuses People screen | Server work for real protection | Recommended |
| B. "Privacy mode" toggle only, client-side | Very cheap | Not protection from a signed-in person | Do for local "Both" anyway |
| C. Index = 100 instead of % change | Familiar from fund fact sheets; no negative-base confusion in display | Still needs the same denominators | Offer as the Net Worth / Liquid variant if % reads badly |
| D. Rounded / banded dollars ("~$1.2M") | Keeps scale | Still discloses wealth | No |
| E. Scaled fake dollars (× secret factor) | Charts unchanged | Deceptive, and ratios leak the same way | No |
| F. A separate "Guest summary" page with a few chosen ratios (savings rate, allocation, spending mix, YoY growth) | Small, easy to make leak-proof; no long tail of fields | Not the full app | Strong option if the remote viewers only need a summary |

## 6. Shape of the build

- `users.money_view` column: `'dollars' | 'percent' | 'both'`, default `'percent'` for new remote people.
  Local listener: an owner preference, default `'both'`.
- `/api/whoami` returns `money_view`. People & Activity dialog gets a $ / % / Both selector per person (staged like the
  other changes, sent on Save & Exit).
- Server: for a `percent` person, every money number in every `/api/` response is divided by one hidden constant
  (today's net worth). Sums and ratios survive, so the page still re-sums account toggles and applies the Time
  scope itself; the dollars never leave the PC. (Decided in the implementation plan; per-endpoint finished
  percentages would not work because scope and toggles are applied in the browser.)
  Endpoints that only make sense with dollars (reconciliation, transactions) return 403 or an empty, labelled result.
- Client: one formatting seam; the title toggle appears only for `both`, remembered per browser (guarded storage).
- Guard test: sign in as a %-only person, call every GET route, assert no field holds a dollar amount
  (no numbers above a threshold outside known non-money keys, no `$`). New routes fail the test until classified.

### Phases (estimates are relative; check `/usage` against them as the plan runs)

| Phase | Work | Model / effort | Usage | Drivers / how to keep it small |
|---|---|---|---|---|
| 1 | `money_view` column, whoami, People dialog selector | Sonnet / medium | Light | `access_store.py`, `access_routes.py`, `access.js` are small |
| 2 | Formatting seam in `charts.js` / `live_snapshot.js` / `spending_dock.js`, client toggle for "Both" | Sonnet / high | Moderate | `charts.js` is 1,128 lines: grep the format calls, don't read it whole |
| 3 | Server ratio transforms per endpoint, withholding of transaction / reconciliation routes | Opus / high | **Heavy — flag** | Many payload shapes; do one endpoint per step with its test, not all at once |
| 4 | Leak guard test + wording of notes / errors | Sonnet / medium | Light–moderate | Test-fix loop can repeat; cap at the guard's route list |

Phases 1 and 2 alone deliver the "privacy screen" version; phase 3 is what makes % a real boundary.

## 7. Decisions (2026-10-28)

1. **Security boundary.** A %-only person never receives dollar amounts; the server converts (phases 1–4 all in scope).
2. **Baseline:** Net Worth and Liquid show % change since the start of the selected Time scope, labelled with that date.
3. **Spending:** each category as % of total spending in the period.
4. **Detail views:** merchant / transaction levels and the reconciliation page are hidden for %-only people.
5. **Default for a new remote person:** %.
6. **Scope:** convert the whole app (Trends and Live Snapshot); no separate Guest summary page.
