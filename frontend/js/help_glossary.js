// Plain-English help layer (WI-033, DOC-008): a one-line summary per page plus a glossary,
// written for a high-school reader with little financial experience. Kept out of
// dashboard.js (size ratchet). Sources: documentation/future/WI-033_*.md.
// Exposes window.plainHelpHtml(stepId), called from the page help box in dashboard.js.
export const GLOSSARY = {
  "Accounts & Sources": "The list of your bank, credit card and investment accounts, and where the app gets each account's numbers (typed in or imported).",
  "Adjusted gross income (AGI)": "Your total income for the year after a few specific subtractions. Many tax rules and Medicare costs are based on this one number.",
  "Annualized": "Turned into a full-year amount. If you spent $2,000 in the first two months, the annualized figure is $12,000 (six times as much).",
  "Asset allocation and location": "Allocation is how your money is split among kinds of investments, such as stocks and bonds. Location is which account holds each kind (for example, a tax-free account or a regular one), because that changes how much tax you pay.",
  "Auto-Mapping Rules": "Rules you set once so the app files transactions in the right spending category by itself, such as \"anything from Corner Grocery goes under Food.\"",
  "Baseline": "Your plan as it stands today. Other versions are compared against it.",
  "Beneficiary": "The person or group who receives money or property from you, for example from a life insurance policy or a will.",
  "Bracket ceiling": "The top of a tax bracket you choose not to go above. Staying under it keeps the tax rate on your extra income from rising. See Tax bracket.",
  "Business-income deductions": "Business costs you can subtract from business income before tax is figured, so only the profit is taxed.",
  "Carrier illustration": "A document from an insurance company (the \"carrier\") that shows year by year what a policy is expected to be worth or pay.",
  "Category": "One kind of spending or income, such as Groceries or Rent. Categories are grouped. See Group and Tracking Type.",
  "Change set": "A saved list of \"what if\" changes to your plan, such as \"retire two years later.\" It lets you try an idea without changing your real plan.",
  "Claiming age": "The age at which you start taking Social Security. Starting later gives a larger monthly check. Starting earlier gives a smaller one.",
  "Column groups": "Sets of related table columns that you can fold up or open so you see only what you need.",
  "Conditional formatting": "Spreadsheet colors or marks that change automatically based on the numbers, such as red for a negative amount.",
  "Conversion policy": "The rule you choose for how much to move into a Roth account each year. See Roth conversion.",
  "Cost basis": "What you originally paid for an investment, including fees. When you sell, you generally pay tax on the gain: the sale price minus the cost basis.",
  "Cost-of-living settings (COLA)": "How much a payment is expected to rise each year to keep up with higher prices. COLA stands for cost-of-living adjustment.",
  "Credit limit": "The most you are allowed to borrow on a credit line.",
  "Depreciation": "A yearly tax deduction that spreads the cost of a building or equipment over many years, because it wears out over time.",
  "Deterministic": "Gives the same answer every time you run it, because it uses fixed assumptions and no chance. The opposite of Monte Carlo.",
  "Discretionary spending": "Spending you could skip or change, such as travel or dining out. The opposite of must-pay bills.",
  "Donor-advised fund (DAF)": "A charity-run account where you put money now, get the tax benefit now, and choose which charities receive gifts from it later.",
  "Draw year": "A year in which you take money from a credit line. The \"last draw year\" is the final year you plan to borrow.",
  "Equity compensation": "Pay in the form of company stock or the right to buy it, on top of salary.",
  "Exercise": "Using a stock option to actually buy the company stock at the set price.",
  "Face amount": "The amount a life insurance policy pays out when the insured person dies.",
  "Federal / state exemption (estate)": "The amount you can leave to others before estate tax applies. Only the part above the exemption is taxed. Federal means the national government. State means your state's.",
  "Filing status": "The category you use on your tax return, such as single or married filing jointly. It decides which tax brackets and deductions apply.",
  "Fixed-income-equivalent coverage": "Counting steady, guaranteed payments (like a pension) as if they were bonds, because they pay a predictable amount. This lets the plan hold fewer bonds.",
  "Full retirement age": "The age when you get your full Social Security amount, with no cut for starting early and no bonus for waiting. For people born in 1960 or later it is 67.",
  "Group (spending)": "A set of related categories. For example, the Housing group might hold Rent, Utilities and Repairs.",
  "Home sale proceeds": "The cash left over when you sell your home, after paying off the mortgage and the costs of selling.",
  "HSA (Health Savings Account)": "A savings account for medical costs. Money goes in without income tax, grows tax-free, and comes out tax-free when used for medical costs.",
  "Illiquid": "Hard to turn into cash quickly. A house or a collectible is illiquid. A savings account is not.",
  "Impact": "How much a change moves your results, such as how much longer your money lasts.",
  "Internal transfers": "Moving your own money between your own accounts, for example from checking to savings. It is not income and not spending.",
  "Lever": "One setting you can adjust to change the plan's outcome, such as the retirement date or how much you convert to a Roth.",
  "Lifetime gifting": "Giving money or property to people while you are alive, rather than leaving it to them after your death.",
  "Long-term care": "Ongoing help with daily living, such as bathing and dressing, from a nursing home, assisted living or a home aide. It is often costly and is not covered by regular health insurance.",
  "Marginal rate": "The tax rate on your next dollar of income. It is not the average rate on all of your income.",
  "Medical inflation": "How fast health-care prices rise each year. It usually rises faster than ordinary prices.",
  "Medicare income surcharge": "An extra monthly charge added to Medicare premiums when your income is above set limits. Also called IRMAA.",
  "Monte Carlo": "A way to test your plan by running it thousands of times with randomly varied market results. It shows how often the plan works, not one single answer.",
  "Mortality age": "The age the plan assumes you will live to. The plan checks that your money lasts that long.",
  "Navigation steps (nav steps)": "The pages listed in the left-hand menu. Some appear only after you turn on the related feature.",
  "Note receivable": "Money someone else owes you under a written promise to repay, such as a loan you made.",
  "Objective weights": "Sliders that tell the app how much each goal matters, such as paying less tax versus leaving more to heirs, when it suggests a choice.",
  "Optional module": "A feature you can switch on or off. Off means it is left out of the plan. Your entries stay saved.",
  "Overrides": "Settings you choose yourself that replace the automatic ones.",
  "Passive-activity rules": "Tax rules that limit how much loss from something you do not work at (like a rental) can reduce your other income. Unused losses carry forward to later years.",
  "Payroll assumptions": "Assumptions about taxes and deductions taken from your paycheck, such as Social Security and Medicare taxes.",
  "Plan-start figures": "Balances and values as of the day the plan begins. They do not change on their own as time passes in the projection.",
  "Planning cases": "Saved \"what if\" versions of your plan kept in your browser. They do not change your real plan until you decide to.",
  "Planning horizon": "How many years the plan looks ahead, usually to a very old age so that you do not run out of money.",
  "Premium tiers": "Levels of Medicare cost. When your income crosses a limit, you move to a higher level and pay more each month.",
  "Pricing snapshot": "A saved copy of investment prices on one date.",
  "Probability analysis": "Shows the chance that your plan works out, for example \"it works in 85 of 100 test runs.\"",
  "Qualified charitable distribution (QCD)": "A gift sent straight from your IRA (a retirement account) to a charity, available from age 70½. It is not counted as taxable income.",
  "Rate drift": "How an interest rate is expected to change over time rather than stay fixed.",
  "Readiness (readiness checks)": "Checks that your plan has the information it needs before you build reports. They list anything missing.",
  "Reconciliation": "Comparing two sets of numbers that should match, such as the app's balances and your bank's, and fixing differences.",
  "Report only": "Shown for information. You cannot change it here.",
  "Required distributions": "Money the law makes you take out of certain retirement accounts each year once you reach a set age, and usually pay tax on.",
  "Reserve floor": "The minimum amount of cash the plan keeps untouched as a safety cushion.",
  "Retirement plan contributions": "Money you put into a retirement account, such as a 401(k), from your pay.",
  "Rider": "An add-on to an insurance policy that adds or changes a benefit.",
  "Roth conversion": "Moving money from a regular retirement account into a Roth account. You pay income tax on the amount moved now. After that it can grow and be withdrawn tax-free later.",
  "Roth conversion room": "How much you can convert before reaching the top of your chosen tax bracket. See Bracket ceiling.",
  "Run type": "Which kind of test you are running: a Scenario (fixed what-if) or a Stress test (bad-luck test).",
  "Schedule E": "The tax form section where rental income and expenses are reported.",
  "Spousal / survivor policy": "The rules for what a spouse receives, such as extra Social Security, and what the surviving spouse keeps after the other dies.",
  "Structured plan rows": "Plan entries that follow a fixed layout of labeled fields, as opposed to long lists like transactions.",
  "Survivor assumptions": "The plan's guesses about what happens to income, spending and taxes after one spouse dies.",
  "Survivor stress": "A test of how the plan holds up if one spouse dies earlier than expected.",
  "Sync actual rate": "Update the plan's spending assumption to match what you actually spent.",
  "System Configuration Console": "A technical screen showing all the app's raw settings. It is meant for advanced use.",
  "Tax bracket": "A range of income taxed at one rate. As income rises, the next slice is taxed at a higher rate. Only the income inside each range is taxed at that range's rate.",
  "Tax bracket indexing": "The yearly increase of bracket limits to keep up with inflation, so rising prices alone do not push you into higher brackets.",
  "Tax-aware sell guidance": "Suggestions for which investments to sell first so that you owe the least tax.",
  "Tax lot": "One purchase of an investment on one date at one price. Buying the same stock twice creates two tax lots, each with its own cost basis.",
  "Ticker": "The short code for a stock or fund, such as AAPL.",
  "Tracking Type": "The top level of the spending list: income, expenses and so on. Beneath it are groups, then categories.",
  "Trust structure": "How a trust is set up: who holds the assets, who manages them, and who receives them.",
  "Vesting": "Earning full ownership over time. Stock awards from an employer often vest in stages, such as a quarter each year over four years.",
  "529 plan": "A savings account for education costs. Growth is tax-free when the money is used for school."
};

export const PLAIN_PAGE_HELP = {
  "start": {"summary": "Open or create your plan, see what is still missing, and pick what to do next.", "terms": ["Readiness (readiness checks)"]},
  "household_people": {"summary": "Who is in the household, when each person was born and plans to retire, and where you live and file taxes.", "terms": ["Filing status", "Planning horizon", "Mortality age", "Survivor assumptions", "Tax bracket"]},
  "income_work": {"summary": "Pay you still earn and what you save from it until you retire.", "terms": ["Payroll assumptions", "Retirement plan contributions", "Business-income deductions", "Roth conversion room", "Bracket ceiling"]},
  "income_retirement": {"summary": "Social Security, pension and annuity income: how much, when it starts, and what continues to a surviving spouse.", "terms": ["Claiming age", "Full retirement age", "Spousal / survivor policy", "Cost-of-living settings (COLA)", "Fixed-income-equivalent coverage"]},
  "spending_core": {"summary": "Everything you spend and earn, sorted into categories.", "terms": ["Tracking Type", "Group (spending)", "Category", "Internal transfers", "Auto-Mapping Rules"]},
  "holdings": {"summary": "Each investment you own, one row per purchase.", "terms": ["Tax lot", "Cost basis", "Ticker", "Tax-aware sell guidance"]},
  "assets_home_cash": {"summary": "How much cash to keep on the side before the plan sells investments.", "terms": ["Reserve floor", "Probability analysis"]},
  "assets_special": {"summary": "Things you own or owe that are not in your investment accounts, such as HSA, 529 and a note owed to you.", "terms": ["Note receivable", "HSA (Health Savings Account)", "529 plan", "Equity compensation", "Illiquid", "Donor-advised fund (DAF)"]},
  "annuity_death_benefits": {"summary": "Your insurance policies and the yearly benefit values from each insurer's illustration.", "terms": ["Carrier illustration", "Rider", "Beneficiary", "Face amount"]},
  "estate": {"summary": "What you plan to leave, to whom, and how, including gifts and charity.", "terms": ["Federal / state exemption (estate)", "Trust structure", "Lifetime gifting"]},
  "reports_and_review": {"summary": "Check the plan is ready, build the reports, then review and download them.", "terms": ["Readiness (readiness checks)", "Impact"]},
  "heloc_strategy": {"summary": "Borrow against your home for big purchases instead of selling investments early.", "terms": ["Credit limit", "Draw year", "Rate drift", "Discretionary spending", "Home sale proceeds"]},
  "rental_properties": {"summary": "Income, costs and eventual sale of each rental property.", "terms": ["Depreciation", "Passive-activity rules", "Schedule E"]},
  "roth_conversion": {"summary": "Decide how much pre-tax money to move into a Roth account each year, and how to weigh the trade-offs.", "terms": ["Roth conversion", "Conversion policy", "Bracket ceiling", "Medicare income surcharge", "Premium tiers", "Objective weights", "Marginal rate"]},
  "entity_charitable": {"summary": "How you give to charity: direct gifts, a donor-advised fund, or gifts straight from an IRA.", "terms": ["Donor-advised fund (DAF)", "Qualified charitable distribution (QCD)", "Adjusted gross income (AGI)", "Required distributions"]},
  "family_business": {"summary": "College savings plans and stock awards from an employer.", "terms": ["529 plan", "Vesting", "Exercise", "Optional module"]},
  "strategy_optimize": {"summary": "One place to adjust the main levers: Roth conversions, investment mix, giving and home-equity borrowing.", "terms": ["Asset allocation and location", "Lever"]},
  "strategy_stress": {"summary": "See how the plan holds up if things go badly: poor markets, early death, long-term care, divorce.", "terms": ["Monte Carlo", "Survivor stress", "Long-term care"]},
  "strategy_scenarios": {"summary": "Save \"what if\" versions of your plan, such as retiring two years later.", "terms": ["Change set", "Deterministic", "Lever"]},
  "strategy_workbench": {"summary": "Compare your plan with the saved what-ifs and decide which to adopt.", "terms": ["Baseline", "Change set", "Run type", "Planning cases"]},
  "actual_spending": {"summary": "Compare what you really spent this year with what the plan assumed.", "terms": ["Annualized", "Sync actual rate", "Accounts & Sources"]},
  "monarch_reconciliation": {"summary": "Check the plan's account balances against your imported daily balances and fix differences.", "terms": ["Reconciliation", "Report only", "Plan-start figures"]},
  "detailed_results": {"summary": "View every report sheet and chart inside the app after a build.", "terms": ["Column groups", "Conditional formatting"]},
  "economic_tax_assumptions": {"summary": "Growth, inflation and tax-rule assumptions used for every year of the plan.", "terms": ["Medical inflation", "Tax bracket indexing", "Cost-of-living settings (COLA)"]},
  "optional_functions": {"summary": "Turn optional parts of the plan on or off. Turning one off never deletes your entries.", "terms": ["Optional module", "Navigation steps (nav steps)"]},
  "all_assumptions": {"summary": "Search for any plan value that you cannot find on a guided page.", "terms": ["Structured plan rows"]},
  "workbook_formatting": {"summary": "Set Excel column widths for the downloaded workbook.", "terms": ["Overrides"]},
  "system_configuration": {"summary": "Backups, exports, price snapshots and the change log. Not plan inputs.", "terms": ["Pricing snapshot", "System Configuration Console"]}
};

const escHtml = (v) =>
  String(v).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

// HTML for the "In plain English" line and the page's glossary terms; "" for pages without an entry.
export function plainHelpHtml(stepId) {
  const page = PLAIN_PAGE_HELP[stepId];
  if (!page) return "";
  const terms = page.terms.filter((t) => GLOSSARY[t]);
  const list = terms.length
    ? `<details class="plain-terms"><summary>Words on this page (${terms.length})</summary><dl>${terms
        .map((t) => `<dt>${escHtml(t)}</dt><dd>${escHtml(GLOSSARY[t])}</dd>`)
        .join("")}</dl></details>`
    : "";
  return `<div class="plain-help"><b>In plain English:</b> ${escHtml(page.summary)}${list}</div>`;
}

if (typeof window !== "undefined") window.plainHelpHtml = plainHelpHtml;
