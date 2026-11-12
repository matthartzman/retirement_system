# Retirement Planner

A local-only retirement planning workspace. You enter your plan, the app saves
it to a database on this computer, and it builds an Excel and HTML report package
you can review with an advisor.

- **Where to start:** open the app and begin on **Plan Status** (the first item
  in the left-hand menu, which shows the Welcome message), then work down the
  menu. The **Open Demo Plan** button there shows a made-up household so you
  can look around safely.
- **If a word is unfamiliar:** the plain-English **Concepts Guide** opens from
  **Settings -> Data & Backups** in the app (the **Help: Concepts Guide** card). It has a page for
  every screen and a glossary, built from the same text as the help panel.
- **Developers:** setup, commands and tests are in
  `documentation/reference/CONTRIBUTING.md`, not here.

## Running the app

Double-click the desktop shortcut (or `launchers/START_APP.bat`) to open the
planner. Everything you enter is saved automatically to a local database on
this computer, and your plan data is never uploaded. The one exception is
market prices: in the default **LIVE** pricing mode the app looks up current
quotes from outside price services (for example Yahoo, Stooq, Nasdaq, and
Financial Modeling Prep or Alpha Vantage if you add a key), which means the
ticker symbols of your holdings, and your IP address, are sent to those
services. Choose **CACHE** or **OFFLINE** pricing mode to stop this (**Settings → Data & Backups → Open
System Configuration Console**, then the **pricing_mode** setting): OFFLINE makes no outside calls
at all and uses saved prices (or your cost basis when none exist). Use the
in-app **Build & Results** page to generate the Excel and HTML report package once your
Plan Data is complete.

## Optional features

**Third-party import auto-update** — if another process places exported
transactions and daily account balances in a folder, this app can import new
and changed ones once a day. Turn it on from **Settings → Data & Backups**,
on the card headed **Third-party import auto-update**: check
**Enable daily auto-update**, confirm the source folder and run time, and it saves on its own,
with no separate save button. Use **Import now** on the same card any time you
want to pull in the latest files without waiting for the daily run. The
**Account Reconciliation** page (under **Track & Reconcile**) then shows the app's
account numbers beside the imported balances.

**Rental Properties** — turn on under **Settings → Plan Features** if you own
rental real estate; the **Rental Properties** page then appears in the left menu
under **Accounts & Property**.

**Local backups** — **Settings → Data & Backups** also holds the automatic
backup controls and **Export CSV backup**.

**Financial Insight app** — a small companion dashboard that charts your
net worth and spending over time, alongside the main planner. Run it with
`python financial_trends_reporter/main.py` from this folder; it opens its own
browser tab showing a running history built from the same plan data. Its
**Current Snapshot** switch shows today's balance sheet instead: your holdings at
market prices (delayed about 15 minutes, refreshed every minute while the
market is open), today's and this year's change by asset class, and net worth
after debt and estimated taxes. To have
it log a fresh snapshot automatically every weekday at 5pm instead of only
when you open it, run
`financial_trends_reporter/tools/launchers/register_trends_report_task.ps1`
once to register the scheduled task.
