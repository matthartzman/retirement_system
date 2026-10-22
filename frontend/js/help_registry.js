// Contextual help registry (Contextual Help Panel plan, Phases 1-2; was help_glossary.js, WI-033):
// one source for page, section and field help, the glossary, and the right panel's follow-focus
// behaviour. HELP_PAGES holds one reviewed record per page; the nav one-liner and the panel both
// read it. Plain-English text is written for a high-school reader with little financial experience
// (documentation/future/WI-033_*.md).
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

// HELP_PAGES[stepId] = { title, summary, whatFor, connections, options, impact, terms }: one reviewed record per
// page (Phase 2b; drafted from the former STEPS desc/intro/help and STEP_HELP, ledger in tools/page_help_ledger.py).
// The left nav one-liner is the summary.
export const HELP_PAGES = {
  "start": {
    title: "Plan Status",
    summary: "Open or create your plan, see what is still missing, and pick what to do next.",
    whatFor: "This is the home base. It shows your setup progress, report readiness (what is still missing before you can build), and the next step. Start with opening or creating a plan. Once a plan is loaded, save changes, build reports, and review results from here. Start New and Open Current are the two starting points, and they are mutually exclusive.",
    connections: "Starting new clears all household-specific data (entered client facts, income, spending, and asset values) but keeps system defaults (inflation, return, and tax assumptions). Opening the current plan reloads everything previously saved: income, assets, Roth strategy, Social Security, account balances, and YTD transactions.",
    options: "Start New when building a first draft or testing a completely different household. Open Current to continue where you left off. Bulk import and export utilities are in Data & Maintenance (the System Configuration Console, under Settings).",
    impact: "Starting new on top of existing work permanently clears the saved data unless you have exported a backup first, so if unsure, export a backup before starting new.",
    terms: ["Readiness (readiness checks)"],
  },
  "household_people": {
    title: "Household & People",
    summary: "Who is in the household, when each person was born and plans to retire, and where you live and file taxes.",
    whatFor: "Enter each person's legal name, date of birth, retirement date, and mortality/planning-horizon age, plus the household's filing status, state of residence, and the survivor income and filing assumptions. This page defines the people, tax identity, state, and filing status used by the model, plus when earned income stops, when retirement spending begins, and how long the household should be projected. These are identity and tax-foundation inputs rather than strategy levers. Mortality age is the planning horizon, meaning how long the plan should last, not a prediction of how long you will live.",
    connections: "Birth dates set ages. Ages connect to retirement timing, Social Security, Medicare, required distributions (RMDs), mortality horizon, survivor years, and estate planning. Filing status and state connect to tax brackets, state taxes, and survivor tax treatment. Filing status sets the brackets across the entire projection. Retirement dates connect to work income, savings contributions, healthcare bridge years, withdrawals, Roth conversion room, and Monte Carlo sequence risk. Life expectancy and survivor assumptions determine late-life taxes, RMD pressure, and legacy values. Survivor assumptions drive the Survivor stress report and also appear there for review before a rebuild.",
    options: "Use actual dates when possible. Use MFJ (married filing jointly) for a married couple, Single after a survivor period when appropriate, HOH (head of household) only when its rules truly apply, and the resident state expected for the modeled period. Earlier retirement increases years funded by assets. Later retirement adds income, reduces withdrawals, and shortens the funding horizon.",
    impact: "Changing ages or filing status can materially change lifetime taxes, RMD timing, Social Security timing, Medicare years, survivor cash flow, and terminal net worth. Changing state may affect state tax, estate tax, and residency optimizer output. Retiring later usually increases terminal net worth and probability of success. Retiring earlier usually lowers liquidity and may reduce success unless spending, income, or home-equity assumptions compensate.",
    terms: ["Filing status", "Planning horizon", "Mortality age", "Survivor assumptions", "Tax bracket"],
  },
  "income_work": {
    title: "Work Income",
    summary: "Pay you still earn and what you save from it until you retire.",
    whatFor: "This page captures earned income (salary or self-employment), payroll assumptions, employer benefits, and savings including retirement plan contributions, while the household is still working.",
    connections: "Earned income feeds cash flow, payroll taxes, retirement-plan contributions, taxable income, ACA/IRMAA-sensitive income in transition years, and the YTD income comparison. Business salary level affects payroll tax and business-income deductions. Contribution amounts add to account balances annually until the retirement date, and connect to future withdrawal sources.",
    options: "Salary/W-2 values are gross annual amounts. Self-employment or S-Corp fields should match the intended entity strategy. Contribution fields should reflect annual expected savings, not current account balances.",
    impact: "Higher earned income generally improves near-term cash flow and the final net worth (TNW), but can increase lifetime taxes and reduce ACA subsidy eligibility. Higher contributions usually improve terminal net worth but reduce spendable current cash. High earned income in late working years compresses Roth conversion room below the bracket ceiling — coordinate with the Roth Conversion page when the retirement date is near.",
    terms: ["Payroll assumptions", "Retirement plan contributions", "Business-income deductions", "Roth conversion room", "Bracket ceiling"],
  },
  "income_retirement": {
    title: "SS, Pensions, & Annuities",
    summary: "Social Security, pension and annuity income: how much, when it starts, and what continues to a surviving spouse.",
    whatFor: "This page captures Social Security (claiming age and benefit for each person), pension amounts, annuity income and their start ages, and other retirement income streams. These are income floors that can reduce portfolio withdrawals.",
    connections: "Claim ages, survivor percentages, COLA settings, and present-value horizons connect to cash flow, tax brackets, survivor results, and allocation coverage. Survivor percentages control how much pension or annuity income continues to the survivor after the first death. Pensions and annuities with survivor protection can be treated as fixed-income-equivalent coverage in the allocation analysis (fixed-income-like coverage); set the coverage option in the Asset allocation & location section of Optimize.",
    options: "Enter each person’s Social Security benefit from their SSA statement when available, along with the planned claiming age and the household spousal/survivor policy. COLA choices indicate whether the payment keeps pace with inflation. Delaying past full retirement age adds about 8% per year up to age 70; the higher earner’s delay has the greatest survivor income impact.",
    impact: "Higher guaranteed income usually improves probability of success and reduces withdrawals, but may increase taxable income and affect Roth conversion room. Delayed claiming may reduce early liquidity but raise later survivor-protected income. Early claiming opens gap years for Roth conversion if other income is low — model the joint timing strategy on the Roth Conversion page.",
    terms: ["Claiming age", "Full retirement age", "Spousal / survivor policy", "Cost-of-living settings (COLA)", "Fixed-income-equivalent coverage"],
  },
  "spending_core": {
    title: "Spending Model",
    summary: "Everything you spend and earn, sorted into categories.",
    whatFor: "This page is the category manager and the comprehensive category model for income and expenses: review the full Tracking Type → Group → Category model here, and manage the canonical category tree. It should account for all income and all expenses, including taxes, except internal transfers (401k/HSA contributions, brokerage buys/sells, credit card payments); lifestyle detail pages still hold scheduled spending inputs. Budget references and projection spending controls live here, with one editable accordion per Tracking Type: Core Expenses, Housing, Wellness, Travel, Large Discretionary, Taxes, and Business. Actual Spending (YTD) and Spending Analysis are under Reports & Review. This page captures all housing-related costs and plans: current mortgage, home operating costs, a planned home sale, and up to two next-step housing arrangements. Rent appears only when configured with a positive rent value. This page captures flexible large expenses that are not Housing, Wellness, Travel, taxes, or recurring Core Spending: weddings, vehicles, gifts, or family support. Travel is the only editable source for Travel budgets and scheduled trip spending.",
    connections: "Core spending flows directly into annual withdrawals, taxable income, liquidity stress, Monte Carlo success, and planning-lever sensitivity. Growth mode and freeze year determine how that spending changes over time. Spending Categories controls how actual transactions roll up by Tracking Type, Group, and Category. Canonical categories carry their Tracking Type and Group, so a separate flat group-mapping table is no longer part of the workflow. Accounts & Sources live with Income & Expense Transactions because they classify where money came from, not what it was for. Mortgage payments and housing operating costs reduce annual cash flow. The home sale year and price affect net worth and liquidity. Next-step housing costs (rent or new mortgage) replace current housing spending in the projection. Each row adds cash-flow needs in a specific year or recurring range. These rows connect to the Optimize page because they are often adjustable if markets or liquidity are stressed. Travel budgets flow into the projection and can be referenced read-only elsewhere.",
    options: "Use CPI/general inflation when spending should rise with inflation. Use manual override when lifestyle spending should grow at a different rate. Use the freeze year when spending increases stop or intentionally flatten. Most users should map categories directly in the Spending Categories hierarchy. Transaction assignment appears here as Advanced Auto-Mapping Rules only when needed: use them only for merchant/category text rules that should repeat automatically. Enter insurance, utilities, and maintenance as annual amounts. For the next-step housing, enter the purchase price and financing plus the ongoing operating costs for that property. Use category budgets or detail lines to document whether the item is must-fund, flexible, or aspirational. Enter category budgets or time-bounded lines for trips and travel memberships.",
    impact: "Higher recurring spending usually lowers terminal net worth and probability of success. Lower spending or earlier spending freezes usually improve both, especially in the first retirement decade. Lower mortgage payments improve near-term cash flow. Selling and downsizing can unlock home equity. Renting instead of buying reduces balance-sheet exposure but may increase long-term housing costs. Higher discretionary spending lowers terminal net worth and can sharply reduce probability of success when it occurs early. Delaying, reducing, or making these items conditional can improve success without changing core lifestyle assumptions. Separating Travel prevents double-counting with Core Spending and Large Discretionary.",
    terms: ["Tracking Type", "Group (spending)", "Category", "Internal transfers", "Auto-Mapping Rules"],
  },
  "holdings": {
    title: "Investment Holdings",
    summary: "Each investment you own, one row per purchase.",
    whatFor: "One row per tax lot: each purchase or reinvestment of a security, with account, ticker, shares, price, cost basis, and purchase date. Add holdings from your broker here — a broker statement or CSV export usually lists everything a row needs directly.",
    connections: "Holdings drive account totals, allocation drift, pricing, tax-lot sell guidance, rebalancing recommendations, and year-to-date growth for investment accounts. Account names must match names used on Withdrawal Sequencing and Asset Allocation. Lot-level cost basis enables tax-aware sell guidance in the allocation output.",
    options: "Use CASH at price 1.00 for money market and cash positions. Keep separate lots per purchase when tax-basis guidance matters — blended basis reduces sell-guidance precision. For large broker downloads, export a backup before importing to replace all.",
    impact: "More complete cost basis and purchase dates improve taxable sell guidance and estimated tax impact on trade recommendations.",
    terms: ["Tax lot", "Cost basis", "Ticker", "Tax-aware sell guidance"],
  },
  "assets_home_cash": {
    title: "Reserve Requirements",
    summary: "How much cash to keep on the side before the plan sells investments.",
    whatFor: "This page captures liquidity reserve rules: the cash reserve floor the plan protects before drawing investments. Home value and mortgage balance are on Other Assets and Liabilities; home sale is in Optimize → Next Housing Move.",
    connections: "Reserve rules connect to withdrawal sequencing, liquidity floors, and Monte Carlo failure modes. The reserve floor is the last buffer in probability analysis — the plan counts as failing when it cannot maintain this floor without depleting all accounts.",
    options: "Reserve rules set how many years of spending to hold outside the investment portfolio, and which account bucket should be protected.",
    impact: "Higher cash reserves improve liquidity resilience but can reduce expected return if too much capital stays out of the portfolio.",
    terms: ["Reserve floor", "Probability analysis"],
  },
  "assets_special": {
    title: "Other Assets and Liabilities",
    summary: "Things you own or owe that are not in your investment accounts, such as HSA, 529 and a note owed to you.",
    whatFor: "This page captures non-portfolio assets such as notes receivable, HSA, DAF, 529 plans, equity compensation, collectibles, vehicles, personal property, and policy-related assets.",
    connections: "Asset type controls where the value appears, whether it is liquid, how it is taxed, and whether it affects estate, education, Wellness, charitable, or growth modules. Planned sale dates connect non-liquid assets to future cash flow. Donor-advised fund configuration is set on Charitable Giving.",
    options: "Pick the asset type that best describes each item's economic purpose, then enter today's fair value, timing assumptions (for anything illiquid, a planned sale date), and whether the asset is liquid or restricted. Notes receivable should use principal and schedule fields, not straight-line extrapolation. HSA balances grow tax-free and should reflect intended use.",
    impact: "Higher liquid asset values usually improve success probability. Higher illiquid asset values increase terminal net worth and estate values but may not fund spending unless sale or borrowing is modeled.",
    terms: ["Note receivable", "HSA (Health Savings Account)", "529 plan", "Equity compensation", "Illiquid", "Donor-advised fund (DAF)"],
  },
  "heloc_strategy": {
    title: "Home Equity Line",
    summary: "Borrow against your home for big purchases instead of selling investments early.",
    whatFor: "Model a home equity line of credit (HELOC) that bridges large discretionary spending in early retirement years with home equity, instead of drawing from liquid assets, keeping invested assets untouched.",
    connections: "HELOC draw reduces gap filled by liquid assets, allowing taxable/IRA balances to compound longer. Interest is paid from cash flow annually. The projection automatically draws from the line, up to available credit, when large discretionary spending creates a cash gap, then repays the outstanding balance from home sale proceeds.",
    options: "Enter a credit limit, the last draw year (the last year of the draw period), an initial interest rate, and an annual rate drift.",
    impact: "HELOC improves TNW when the compound benefit of undisturbed liquid assets exceeds borrowing costs. It worsens outcomes when interest drag or reduced home equity at sale outweigh the investment benefit.",
    terms: ["Credit limit", "Draw year", "Rate drift", "Discretionary spending", "Home sale proceeds"],
  },
  "rental_properties": {
    title: "Rental Properties",
    summary: "Income, costs and eventual sale of each rental property.",
    whatFor: "One record per rental property: add each rental property, or convert your own home to a rental. The summary here is an estimate from your entries; the build applies your real income.",
    connections: "Rent, operating expenses, mortgage interest and depreciation net on Schedule E into AGI; passive-loss limits, NIIT, state tax, cash flow, net worth and the sale (with depreciation recapture) follow. Rental income is taxed on Schedule E: rent less expenses, interest and depreciation.",
    options: "Fill the Standard fields for each property; Show advanced adds the Expert fields (placed-in-service month, capital improvements, per-year overrides). Enter a property once: here, not also in Other Assets. Turn the feature on in Plan Features.",
    impact: "Rent above expenses adds taxable income; a loss is limited by the passive-activity rules and carried forward until you sell. Converting your home moves its carrying costs from spending to Schedule E.",
    terms: ["Depreciation", "Passive-activity rules", "Schedule E"],
  },
  "annuity_death_benefits": {
    title: "Insurance",
    summary: "Your insurance policies and the yearly benefit values from each insurer's illustration.",
    whatFor: "This page records year-by-year carrier illustration values (death benefits) for annuities, riders and special income, plus all insurance policies (life, disability, long-term care, umbrella, auto, home, property and casualty, and other), with the owner, insured, beneficiary, face amount, and premiums for each. It combines a year-by-year schedule with individual policy records — not a generic account balance table.",
    connections: "Each annuity policy row connects to survivor, estate, and legacy reporting; these totals appear in the Survivor and Estate report sections. Year columns show how protection changes over time and whether a benefit disappears before the end of the plan. Policy premiums connect to cash flow each year; benefit amounts appear in the Survivor and Long-Term Care Stress report sections.",
    options: "Enter the carrier illustration values for each year for annuities, from each policy illustration; use 0 for years with no benefit (no death benefit available). For any insurance policy, use policy type, premium end, term end, benefit amount, and owner/insured fields consistently. Keep policy names consistent with other insurance/annuity entries; they must match any cross-references on stress pages.",
    impact: "Higher death benefits improve survivor/legacy protection but may come with lower investment growth, liquidity restrictions, or ongoing rider costs that should be reflected elsewhere. More insurance coverage can reduce downside risk but premiums may lower terminal net worth if no claim occurs. Rider benefits that step down or expire early can leave the survivor without protection — compare benefit schedules against the planning horizon set on Household & People.",
    terms: ["Carrier illustration", "Rider", "Beneficiary", "Face amount"],
  },
  "estate": {
    title: "Estate Inputs",
    summary: "What you plan to leave, to whom, and how, including gifts and charity.",
    whatFor: "This page captures estate-tax, trust, beneficiary, legacy-planning, and gifting assumptions. It tells the model how assets should be interpreted after death or for survivor planning. Enter federal and state exemption elections, trust structure, beneficiary needs, lifetime gifting, and charitable intent for this household.",
    connections: "Federal/state exemptions, CST/QTIP settings, beneficiary needs, special-needs planning, gifting, and charitable intent connect to legacy value, estate-tax exposure, survivor analysis, Roth strategy scoring, and executor-oriented workbook notes. Insurance policies (life, disability, long-term care, umbrella, and property and casualty) are entered on Insurance. Long-term-care hybrid policies with an investment component should also appear on Other Assets and Liabilities.",
    options: "Use monitor/balanced/strong estate objectives depending on whether estate tax is a watch item or a decision driver. Enter trust and beneficiary facts only when they are part of the intended plan. The federal exemption can change with law updates — confirm the current-law amount in Settings and model the impact of any reduction in Scenarios.",
    impact: "More aggressive estate-tax planning may reduce projected estate tax and improve legacy quality, but can reduce flexibility if assets are transferred, restricted, or earmarked too early.",
    terms: ["Federal / state exemption (estate)", "Trust structure", "Lifetime gifting"],
  },
  "roth_conversion": {
    title: "Roth Conversion",
    summary: "Decide how much pre-tax money to move into a Roth account each year, and how to weigh the trade-offs.",
    whatFor: "This page sets how voluntary Roth conversions are sized and scored: the conversion policy, the ceiling (bracket or fixed dollar), Medicare income surcharge guardrails, and objective weights for tax, legacy, survivor, and estate. It is a planning optimizer, not a record of taxes already paid. Forced conversion rows are separate: they represent actions already taken or imposed for a scenario, and run before the optimizer, reducing the space available for voluntary conversions.",
    connections: "The Roth objective, tax-bracket ceiling, IRMAA guardrail, legacy weight, estate-tax weight, and survivor-risk weight work together. Tight guardrails preserve near-term liquidity and Medicare premium control; loose guardrails allow larger conversions when long-term tax savings or legacy value justify the current tax cost.",
    options: "Choose the policy first — the page shows only controls relevant to that policy. Bracket-fill policies convert up to a tax bracket, a marginal rate ceiling determined by the filing status on Household & People. Medicare income surcharge (IRMAA) guardrails stop or warn near Medicare premium cliffs, preventing projected income from crossing premium tiers during conversion years. Fixed-dollar options force a chosen annual amount. Objective weights tell the scorer whether taxes, terminal net worth, survivor outcomes, or legacy value matter most.",
    impact: "Higher conversion amounts usually increase current-year taxes and may reduce liquid assets, but can lower future RMDs, survivor tax compression, and lifetime taxes. More conservative guardrails usually protect near-term cash flow and Medicare premiums, but may leave future tax savings unused.",
    terms: ["Roth conversion", "Conversion policy", "Bracket ceiling", "Medicare income surcharge", "Premium tiers", "Objective weights", "Marginal rate"],
  },
  "entity_charitable": {
    title: "Charitable Giving",
    summary: "How you give to charity: direct gifts, a donor-advised fund, or gifts straight from an IRA.",
    whatFor: "This strategy page covers the charitable giving vehicle: cash (direct gift), donor-advised fund, or qualified charitable distribution. Annual giving amounts are entered on Core spending. Business-entity choice (S-Corp vs LLC) is entered on Work Income.",
    connections: "Charitable vehicle choice connects to deductions, lifetime taxes, and legacy, and appears in a dedicated workbook sheet.",
    options: "Choose how charitable gifts are funded. Donor-advised funds are most effective when contributed in a high-income year and granted over time. Qualified charitable distributions (QCDs) are available at age 70½ and satisfy required distributions tax-free; use them after RMD age where appropriate.",
    impact: "Qualified charitable distributions also reduce adjusted gross income, which can lower income-related Medicare surcharge tiers — model in combination with Roth Conversion. Charitable vehicle choice can lower taxes and increase legacy, but may reduce near-term liquidity.",
    terms: ["Donor-advised fund (DAF)", "Qualified charitable distribution (QCD)", "Adjusted gross income (AGI)", "Required distributions"],
  },
  "family_business": {
    title: "Education & Equity Comp",
    summary: "College savings plans and stock awards from an employer.",
    whatFor: "This page collects the Family & Business plan inputs: 529 education savings sections and equity compensation grants. The same rows are editable on Other Assets and Liabilities; business entity choice (S-Corp vs LLC) is on Work Income.",
    connections: "529 balances and contributions connect to education spending and legacy. Equity compensation connects to earned income, payroll and capital-gains tax, and the projection reads it directly when its module is on. Each feature here is an optional module. A feature that is off keeps everything you have entered and says so on its own section, so turning one off never removes your data.",
    options: "Enter one 529 section per beneficiary or goal, and the grant, vesting and exercise assumptions for any equity compensation; use grant-level assumptions rather than a single blended figure where the vesting years differ.",
    impact: "Equity compensation can concentrate both portfolio risk and taxable income in a few years — check the lifetime-tax and allocation results after entering it.",
    terms: ["529 plan", "Vesting", "Exercise", "Optional module"],
  },
  "strategy_optimize": {
    title: "Optimize",
    summary: "One place to adjust the main levers: Roth conversions, investment mix, giving and home-equity borrowing.",
    whatFor: "One decision workspace for the main levers: Roth conversions, asset allocation and location, charitable giving, and home-equity borrowing. This is your decision hub: it shows your current projected outcome and screens the practical changes most likely to move terminal net worth or probability of success, then links to every strategy and stress test. Open a section to work on one lever at a time. Each section is the same input page it always was — collapsed sections are not rendered, so the page stays fast while you edit. Decide the strategy here, then test its resilience on Stress Test and compare alternatives on Scenarios. Sections whose optional module is off show how to enable it. This strategy page compares the baseline home state with a target relocation state for tax and geographic cost differences. The baseline state is set on Household & People, and current budgeted amounts are the baseline. This page defines supporting assumptions for portfolio recommendation logic: risk tolerance, glide path, capital-market assumptions, and optimizer inputs. This page chooses the allocation target, asset-class inclusion policy, alternates, user targets, optimizer overrides, and trade recommendation context. This page sets the order and constraints used to fund annual spending from available account buckets.",
    connections: "Each lever estimates a separate effect using latest build KPIs and current plan inputs. Spending, retirement timing, reserve, home-equity, Roth, tax, and risk levers relate to source pages where actual values must be changed. State income tax connects to net cash flow and lifetime taxes. Estimated geographic deltas for auto insurance, homeowners insurance, utilities, and home maintenance connect to the State Residency workbook sheet. Risk tolerance and glide path connect household capacity to target allocation. Expected return, volatility, and correlations connect to optimizer scoring and Monte Carlo assumptions when enabled. Selection mode determines whether user targets or optimizer recommendations drive the workbook. Include/exclude/alternate controls connect non-liquid assets, pensions, home equity, or notes to liquid target recommendations. Holdings and tax lots connect to trade guidance. Withdrawal priority connects to taxable income, RMDs, Roth preservation, trust withdrawals, cash reserve rules, survivor cash flow, and annual cash-flow schedules. HSA withdrawal timing is controlled on Other Assets and Liabilities: use it when you want to intentionally spend HSA balances over a window; those scheduled withdrawals still feed the same cash-flow engine.",
    options: "Edit one test amount at a time to isolate the likely effect. Rank by terminal net worth when legacy/estate value is the goal; rank by probability of success when liquidity and funded-spending reliability are the goal. Enter the target state. The workbook estimates the annual and lifetime change for each cost category from relative cost-of-living factors — replace them with real quotes when available. Expected return is the long-term reward assumption. Volatility is downside bumpiness. Correlation describes diversification. Glide path controls whether the portfolio de-risks over time. Use user target when the allocation is advisor-directed. Use optimizer recommendation when model constraints should choose the mix. Include allows target exposure; Exclude prevents it; Consider alternate first lets an existing asset satisfy the sleeve before new trades are recommended. Earlier priority means the bucket is used sooner. Preserving Roth usually supports legacy and tax diversification; spending taxable first may manage RMDs but can trigger capital gains.",
    impact: "Levers that improve both TNW and success are strongest. Some levers trade one against the other: higher risk may increase TNW but lower success; larger reserves may improve success but reduce return; Roth conversions may lower lifetime taxes but reduce near-term liquidity. A lower-tax or lower-cost state can improve lifetime net cash flow, but verify housing, healthcare, and lifestyle differences before treating relocation as a plan decision. Higher return assumptions usually increase recommended growth exposure and TNW projections, but can overstate success if risk is understated. Higher volatility usually lowers optimizer preference unless diversification benefits offset it. Increasing growth assets may raise expected TNW but can lower success in bad early markets. Excluding or covering an asset class can reduce unnecessary trades. Tax-aware sell guidance can lower realized tax cost but may leave more drift. Changing withdrawal order can shift lifetime taxes, terminal net worth, liquidity failures, and survivor outcomes. It can improve one metric while worsening another, so rebuild and compare.",
    terms: ["Asset allocation and location", "Lever"],
  },
  "strategy_stress": {
    title: "Stress Test",
    summary: "See how the plan holds up if things go badly: poor markets, early death, long-term care, divorce.",
    whatFor: "Stress assumptions are adverse tests, not forecasts: Monte Carlo probability, survivor/early death, long-term care, and divorce. This page controls how uncertainty is simulated across market, inflation, tax-indexing, and Wellness-shock paths. It determines how probability of success is measured. This stress test reviews how the plan holds up if one spouse dies early. This stress test models a long-term-care cost shock and how existing coverage absorbs it. This page models divorce-specific assumptions only when that optional module is enabled. It should not be used for ordinary married/survivor planning.",
    connections: "Every section here is an optional workbook module — a section only has inputs once its module is enabled on Plan Features, and this whole page is hidden when all four are off. Simulation count, engine mode, return volatility, liquidity floors, and stress assumptions connect to probability of success, downside wealth, failure timing, and build time. Mortality ages, survivor filing status, and spousal rollover connect to survivor tax compression, RMD timing, income loss, and late-life net worth. The full result is the Survivor workbook sheet. LTC policy details also appear on Other Assets and Liabilities. LTC cost, duration, and coverage connect to late-life spending shocks, liquidity, and the combined LTC / life insurance workbook section. Filing status, QDRO transfers, alimony, asset division, property assumptions, and health costs connect to taxes, ownership, cash flow, survivor-like outcomes, and risk.",
    options: "Set the inputs for whichever tests apply, then rebuild to see them in the workbook. Quick/vectorized mode is faster and approximate. Advanced/exact mode is slower but advisor-ready. More trials reduce random noise. Tighter liquidity floors make success harder but more realistic. Review the surfaced survivor assumptions (they also appear on Household & People), then rebuild to see the survivor stress outcome; adjust the source values on Household & People if needed. Enter or review the LTC assumptions and coverage, then rebuild. If results do not appear, turn on the Long-Term-Care Stress (LTC stress) module in Plan Features. Turn the module on only for an explicit divorce scenario. Use actual legal or negotiated assumptions when available; otherwise label the case as hypothetical.",
    impact: "More conservative settings usually lower probability of success but make the risk result more reliable. Faster settings help drafts but should not drive final recommendations without confirmation. Early death often compresses tax brackets for the survivor and reduces household income; adequate insurance and Roth balances can soften the impact. A long-term-care event is a major downside risk; coverage reduces the shock but adds premium cost. Compare funded outcomes with and without coverage. Changing from married to split-household assumptions can materially reduce terminal net worth, raise lifetime taxes, change Wellness costs, and reduce probability of success.",
    terms: ["Monte Carlo", "Survivor stress", "Long-term care"],
  },
  "strategy_scenarios": {
    title: "Scenarios",
    summary: "Save \"what if\" versions of your plan, such as retiring two years later.",
    whatFor: "Change sets are named, deterministic what-if cases that you stage and save from any source page and compare side by side in the Workbench; each compares a specific bundle of lever/assumption changes against the base plan. It is a comparison mode, not a random-draw stress test like Monte Carlo. Rank individual levers and review saved cases there.",
    connections: "Scenario rows can change returns, inflation, home sale assumptions, spending, tax, or timing for workbook scenario sheets and risk narratives. Economy and home-sale stress cases belong here.",
    options: "Use one scenario per clear question with a specific answer: retire later (for example two years later), sell the home (for example in 2028), inflation stress, low returns, spending cut, or tax change. Keep scenario labels descriptive so workbook comparisons are readable. Use Stress Test for probability ranges and adverse assumptions.",
    impact: "Scenarios that lean adverse often reduce TNW and success indicators, but comparing bundles side by side shows which lever combinations protect the plan best.",
    terms: ["Change set", "Deterministic", "Lever"],
  },
  "strategy_workbench": {
    title: "Workbench",
    summary: "Compare your plan with the saved what-ifs and decide which to adopt.",
    whatFor: "The unified planning flow for comparing the baseline, named change sets, scenario ideas, stress assumptions and stress-suite results in one place, then deciding what to adopt (final decisions). Planning cases are browser-local change sets (notes) that do not alter the saved plan.",
    connections: "The workbench connects Optimize (the strategy levers), Scenarios, Stress Test settings, and Build & Results around the same Baseline → Change Set → Run Type → Impact → Decision vocabulary. Saved cases help organize what you are testing without mutating the saved plan.",
    options: "Pick a baseline, stage a change set to test (or save a staged edit or strategy as a case), choose Scenario or Stress as the run type, then review Impact and record a Decision: use the Decision panel to adopt, archive, or leave it as reference. Adopted changes do not alter the saved plan until you explicitly jump to source pages, edit inputs, save, and rebuild.",
    impact: "A planning case can clarify what to test next, but it does not change workbook results by itself. Only saved source-page edits followed by a rebuild affect terminal net worth, lifetime taxes, Monte Carlo success, and report outputs.",
    terms: ["Baseline", "Change set", "Run type", "Planning cases"],
  },
  "actual_spending": {
    title: "Actual Spending",
    summary: "Compare what you really spent this year with what the plan assumed.",
    whatFor: "Import and manage current-year income and expense transactions for the selected year, and see how they compare with the spending model: a current-year performance summary (spending, income, portfolio growth), a budget vs actuals tracker, and the link to the 30-year retirement model.",
    connections: "Transactions from Income & Expense Transactions feed both the summary and the tracker. Category assignment happens on Spending Model: Spending Categories controls how transactions are assigned to the canonical Tracking Type → Group → Category hierarchy. Accounts & Sources controls account/source type, prior-year balances, and current values.",
    options: "Import and assign transactions for the selected year on the page for that year. Upload a CSV from your bank or brokerage. Use Replace all to start fresh or Add to merge new transactions with existing ones. Remove Duplicates deduplicates by Date + Merchant + Amount + Account. Required CSV columns: Date, Merchant, Category, Account, Amount. Optional: Original Statement, Notes, Tags, Owner. Only current-year rows are imported. The summary shows actual vs projected spending, income, and growth. The tracker compares annualized actuals to category budgets and to the retirement model core spending assumption. Compare annualized spending with the plan on Analysis, then use Sync Actual Rate to update the 30-year model before building.",
    impact: "Spending rate above the model assumption reduces projected net worth. Identifying over-budget groups early — before the annual rebuild — gives time to recalibrate Core spending or adjust plans. More complete transaction data improves the accuracy of the YTD spending, income, and growth analysis in Spending Analysis.",
    terms: ["Annualized", "Sync actual rate", "Accounts & Sources"],
  },
  "monarch_reconciliation": {
    title: "Account Reconciliation",
    summary: "Check the plan's account balances against your imported daily balances and fix differences.",
    whatFor: "Compares each account number in the app with the balance the import reports (the imported daily balances), as of a date you pick, lists what needs a decision, and offers a way to copy the imported number into the app.",
    connections: "Accounts match by name, by a match you save, or by importing your mapping CSV. Each match has a policy: ask me, always update (copied at the nightly import unless the change is large or a plan-start input), app is source, or ignore. Investments are never changed here: investment accounts are valued from holdings, so they are report only.",
    options: "Each difference needs a choice: update the app, ignore it this time, always update from the import, or keep the app as the source. Every change is logged and can be undone: use Undo in the change log, or Undo all automatic updates; it refuses if the value was edited since. Update app previews the old and new value before anything is written.",
    impact: "A corrected balance changes net worth, YTD growth and the starting values the next build uses. Plan inputs (home, autos, mortgage) are plan-start figures; rebuild after changing or applying them.",
    terms: ["Reconciliation", "Report only", "Plan-start figures"],
  },
  "reports_and_review": {
    title: "Build & Results",
    summary: "Check the plan is ready, build the reports, then review and download them.",
    whatFor: "One workspace for anything related to output, keeping report readiness and results in one flow: readiness, build, impact, results, downloads, and plan data review. This page is a pre-build interpretation checklist. It does not create new calculations; it helps confirm that the assumptions behind the report are coherent. This page explains what changed in the latest build compared with the session baseline. It is a review and revert tool, not a data-entry page. A read-only view of everything you have entered across all plan sections.",
    connections: "Risk tolerance, spending flexibility, longevity, tax strategy, Roth objectives, inflation, returns, estate intent, and liquidity assumptions all connect to multiple workbook sections and recommendations. Save Changes stores all entered values. Download Workbook saves, builds, and delivers in one click when there are unsaved changes or no current build, so you do not need to save separately before downloading. The comparison uses values captured before this editing session and values after the last successful build. It helps connect changed assumptions to terminal net worth, lifetime taxes, Roth conversions, liquidity, and output warnings. Every field from every input page is shown here, grouped by section. Holdings are summarized by account.",
    options: "Build current reports (readiness checks appear right above the Build button), review impact and results, then download or print the final package. Use Save Changes when you want to save without triggering a rebuild. Use Download when ready for final output. Resolve any required-field warnings before downloading. Bulk import/export is in Data & Maintenance (the System Configuration Console, under Settings). Use this page to decide whether assumptions are documented, estimated, or scenario-specific. If a checklist item reveals uncertainty, edit the source page before building. Revert restores captured before-values for edited inputs. Rebuild confirms whether the reverted or edited plan changes the authoritative workbook output. Use this after filling in the plan to do a final review before building outputs.",
    impact: "Better assumptions reduce false precision. Changing checklist-related inputs can affect TNW, lifetime taxes, Monte Carlo success, survivor results, and report narratives. A successful build refreshes projected net worth, lifetime taxes, Monte Carlo success, allocation recommendations, and all narrative sections. The downloaded file reflects the last successful build — download again after each rebuild to get the latest. Large differences identify high-leverage assumptions. A positive terminal-net-worth change is not automatically better if it increases lifetime taxes, liquidity stress, survivor risk, or Monte Carlo failure. If a field looks wrong here, go to the input page that holds it and correct it there.",
    terms: ["Readiness (readiness checks)", "Impact"],
  },
  "detailed_results": {
    title: "Results",
    summary: "View every report sheet and chart inside the app after a build.",
    whatFor: "In-app view of every workbook sheet, chart and data table after a build — Cash Flow Projection, Monte Carlo, Allocation, Lifetime Taxes, Estate, and all strategy comparisons. Each sheet matches the same-named sheet in the Excel workbook.",
    connections: "Column groups can be collapsed to focus on key metrics. Row-level search finds any value across all sheets.",
    options: "Use the sheet selector in the left panel to navigate between sections; sheet navigation and row-level search are in the left panel. Download the workbook when you need full Excel fidelity: complex charts and conditional formatting can't be approximated here. The Cash Flow Projection, Monte Carlo, and Allocation sheets have the most complex rendering. If a chart or table looks incomplete in this view, the downloaded workbook is authoritative.",
    impact: "If a sheet shows unexpected values, the issue is in the plan inputs — identify the relevant input page, correct the value, and rebuild.",
    terms: ["Column groups", "Conditional formatting"],
  },
  "economic_tax_assumptions": {
    title: "Economic & Tax Assumptions",
    summary: "Growth, inflation and tax-rule assumptions used for every year of the plan.",
    whatFor: "This System page holds the default baseline return rates, inflation, medical cost escalation, COLA, tax bracket indexing, payroll, and Wellness assumptions, applied system-wide across all projections. Changes here affect every projection year simultaneously.",
    connections: "Inflation connects spending, Social Security COLA, tax brackets, IRMAA thresholds, Wellness costs, and capital-market projections. Tax constants and indexing assumptions connect to Roth and lifetime-tax analysis.",
    options: "Use current-law/default assumptions for base plans; use Scenarios to compare alternative assumption sets and test alternatives without altering the base assumptions. Keep tax data source years current before relying on tax-sensitive recommendations. Return assumptions should reflect long-term expected rates, not recent performance.",
    impact: "Medical inflation is the most sensitive late-life input — a 1% change compounds across 30 years and materially shifts Medicare and care costs. Higher inflation usually lowers real purchasing power and can reduce success unless income/assets adjust. Higher Wellness inflation raises late-life spending. Changing tax assumptions can materially change lifetime taxes and Roth recommendations.",
    terms: ["Medical inflation", "Tax bracket indexing", "Cost-of-living settings (COLA)"],
  },
  "optional_functions": {
    title: "Plan Features",
    summary: "Turn optional parts of the plan on or off. Turning one off never deletes your entries.",
    whatFor: "Enables or disables entire planning sections — long-term care stress, divorce planning, home equity line, charitable giving, special needs, equity compensation, 529 education funding, and others — chosen for this plan. Features are grouped by the part of life they cover (taxes, housing, protection, risk, and the rest) and can be filtered by the kind of question they answer.",
    connections: "Features that add navigation steps (their own page in the left menu, such as Home Equity Line and Rental Properties) must be turned on here before that step appears; features that only add workbook output can be toggled without changing the navigation. A feature that is on but depends on another that is off says what it is leaving out.",
    options: "Enable a feature before entering its detail elsewhere in the plan — its input page won't appear in navigation until it's turned on. Turn a feature off to exclude it from the build without deleting its saved data; the row then shows how many entries are being held.",
    impact: "Turning a feature off removes its section from the workbook build entirely, not just from navigation. Turning one on can add new required fields to complete before the plan is build-ready.",
    terms: ["Optional module", "Navigation steps (nav steps)"],
  },
  "all_assumptions": {
    title: "Field Finder",
    summary: "Search for any plan value that you cannot find on a guided page.",
    whatFor: "Every editable plan field in one searchable view — a safety net for values that don't surface clearly on their guided pages. Use it when a value doesn't appear on its guided page. Holdings, budget lines, transactions, and liabilities are not here — those are managed on their dedicated tabs. This view covers only structured plan rows.",
    connections: "Fields on this page belong to many different sections. Changing a field here has the same build effect as changing it on the source page, but without the surrounding related fields as context.",
    options: "Search by label, section, or keyword. Review field help before changing unfamiliar inputs. Prefer the source page when nearby related values need to be consistent.",
    impact: "Because this page combines fields from every section, a change can affect almost any output.",
    terms: ["Structured plan rows"],
  },
  "workbook_formatting": {
    title: "Workbook Formatting",
    summary: "Set Excel column widths for the downloaded workbook.",
    whatFor: "Adjusts the Excel column widths in the generated workbook per sheet, table, and column: organized by sheet, then by table (for multi-table sheets like Net Worth and Cash Flow), then by column. Each sheet expands to its tables and columns.",
    connections: "Widths are read from the most recently built workbook; a built workbook is required to read the current column structure. Each edit is saved as a per-column override and layered on top of the standard layout, so a width you set wins over the default sizing; a column you never touch keeps its automatic width.",
    options: "Edit a column width and save — overrides are stored and applied the next time you build the workbook. Widen a column when its numbers or labels look cramped or clipped; narrow one to fit more columns on a printed page.",
    impact: "No planning impact — this changes only the appearance of the Excel output, never any calculated value.",
    terms: ["Overrides"],
  },
  "system_configuration": {
    title: "Data & Maintenance",
    summary: "Backups, exports, price snapshots and the change log. Not plan inputs.",
    whatFor: "Operational tools for this workspace, not plan inputs: pricing snapshots, local backups, CSV export, the recent-change log, and the raw System Configuration Console, plus advanced configuration for build settings, market data pricing, state tax reference tables, and bulk data management. Changes here apply across all plans.",
    connections: "Pricing mode determines how holding values are updated — live market data vs cached values. Tax and reference tables drive projection tax calculations, IRMAA thresholds, and bracket indexing. Build flags control what the workbook build includes.",
    options: "Use focused input pages for normal plan edits; change how the plan is modeled on the other Settings pages (Economic & Tax Assumptions, Plan Features with its optional modules, Field Finder, Workbook Formatting). Use bulk CSV adapters here only for reference table maintenance or data recovery. Rebuild after any change to pricing, tax, or optimizer settings.",
    impact: "System changes affect account values, allocation recommendations, lifetime taxes, Monte Carlo results, and build output. Isolate one settings family at a time when diagnosing unexpected results.",
    terms: ["Pricing snapshot", "System Configuration Console"],
  },
};

// HELP_SECTIONS[key]: key is the section's data-help-section attribute, "<pageId>.<section>".
export const HELP_SECTIONS = {
  // Phase 3b: section help for Insurance/Estate/Taxes, Strategy, Reports and Review, and Settings.
  "estate.state_estate_tax": {
    pageId: "estate",
    title: "State estate-tax references",
    body: "The states listed come from the reference table in reference_data/state_tax.csv. Add a state to Plan Data when it should appear in the estate-analysis inputs.",
  },
  "estate.trusts": {
    pageId: "estate",
    title: "Trusts",
    body: "Trust accounts are shown in a compact table. Each trust has a type pulldown and can be expanded for additional fields. Investment accounts with Trust in the account name still flow through the holdings page; add trust rows here when you want estate metadata. For the QTIP and Credit Shelter trusts, start with Enabled: the trust's mechanics appear only when it is enabled. Enable Special Needs Planning in Optional workbook modules to edit the ABLE, trust and government-benefit rows.",
  },
  "estate.beneficiary_titling": {
    pageId: "estate",
    title: "Beneficiary and titling",
    body: "One panel per account from Holdings, for primary and contingent beneficiaries and titling. It drives the Beneficiary and Titling Audit and each account's own basis step-up on Sheet 14. Leave Titling blank to use the household-wide default instead.",
  },
  "entity_charitable.charitable": {
    pageId: "entity_charitable",
    title: "Charitable giving and QCDs",
    body: "Qualified charitable distributions (QCDs, age 70½ and over) satisfy required distributions without the amount appearing as taxable income. Each QCD is capped at the person's own required distribution and the annual QCD limit. A blank start year means the year they turn 70½; a blank end year means through plan end. An S-Corp election is a self-employment decision, entered on Work Income.",
  },
  "annuity_death_benefits.annuity_death_benefits": {
    pageId: "annuity_death_benefits",
    title: "Annuity death benefits",
    body: "Each row is a separate annuity policy and each column is a calendar year. Enter the benefit payable to heirs if death occurs in that year. Use Tab or Return to move across the editable year cells; scroll horizontally to reach later years, the policy column stays visible.",
  },
  "annuity_death_benefits.life_illustrations": {
    pageId: "annuity_death_benefits",
    title: "Life insurance illustrations",
    body: "Enter values from each life policy's carrier illustration for the years shown. Each policy below matches a policy added under Insurance Policies.",
  },
  "annuity_death_benefits.life_cash_value": {
    pageId: "annuity_death_benefits",
    title: "Life illustration: cash value",
    body: "Cash surrender value in each year, per the illustration.",
  },
  "annuity_death_benefits.life_death_benefit": {
    pageId: "annuity_death_benefits",
    title: "Life illustration: death benefit",
    body: "Death benefit payable to beneficiaries in each year, per the illustration.",
  },
  "annuity_death_benefits.life_premium": {
    pageId: "annuity_death_benefits",
    title: "Life illustration: premium",
    body: "Premium due in each year, per the illustration.",
  },
  "economic_tax_assumptions.tax_assumptions": {
    pageId: "economic_tax_assumptions",
    title: "Tax assumptions",
    body: "Model values come from the tax-law dataset and your state. Type a value (for example 3% or 0.03) to override one; leave it blank to use Auto. The Higher rates tax-law scenario is a stress: federal ordinary income is taxed at pre-2018 rates with thresholds unchanged.",
  },
  "roth_conversion.guardrails": {
    pageId: "roth_conversion",
    title: "Conversion guardrails",
    body: "Conversion is always the lowest active cap, whatever order you set. Your order controls how guardrails are listed; the badges follow the dollars. The what-if figures come from re-running your plan with that guardrail off. Changes to settings take effect at the next build.",
  },
  "roth_conversion.bracket_targets": {
    pageId: "roth_conversion",
    title: "Tax bracket targets",
    body: "Tax bracket target rows appear here rather than in Economic and Tax Assumptions because they are strategy inputs: they define the conversion ceiling, not a general economic forecast.",
  },
  "roth_conversion.policy": {
    pageId: "roth_conversion",
    title: "Conversion policy",
    body: "Choose a conversion policy first; the page then shows only the controls relevant to that choice. Fill-to-IRMAA uses the Medicare premium tier boundary as the conversion ceiling; choosing it hides the separate IRMAA guardrail to avoid duplicate controls. Bracket strategy options appear only for bracket-fill and optimizer policies.",
  },
  "roth_conversion.forced_conversions": {
    pageId: "roth_conversion",
    title: "Forced conversions",
    body: "Use this only for conversions that are already done or intentionally required in a scenario. Enter one row per conversion: source account, year and dollar amount. The optimizer will not remove these rows.",
  },
  "all_assumptions.field_list": {
    pageId: "all_assumptions",
    title: "Field list",
    body: "Grouped by plan area, matching the left navigation, alphabetical within each area. Each field shows its own source page beneath its label.",
  },
  "all_assumptions.inactive_values": {
    pageId: "all_assumptions",
    title: "Inactive values",
    body: "Inactive values are saved in Plan Data but hidden as ordinary inputs because the current build settings will not consume them. Use the action column only when you intentionally want to change the controlling setting or value so the build starts using it. Use page search or All assumptions to review broader configuration.",
  },
  "all_assumptions.batch_edit": {
    pageId: "all_assumptions",
    title: "Batch edit assumptions",
    body: "Preview first, then stage many plan-row edits at once. Applying a preview only marks fields edited; click Save Changes to persist.",
  },
  "strategy_optimize.levers": {
    pageId: "strategy_optimize",
    title: "Strategy levers",
    body: "Ranked lever estimates, measured baseline figures and source-page jumps for changing the actual plan. Levers rank against the latest successful baseline, so build reports first; until then use the Roth Conversion, Asset Allocation, Spending Categories, Scenarios and Monte Carlo pages to stage inputs. Estimates assume all other inputs stay fixed; change the test amount to resize any estimate without affecting your plan. After ranking, use the Source button beside a lever to change the actual input, rebuild, and check Build History for the measured effect on projected net worth and success rate. TNW is terminal net worth, the projected portfolio at the end of the plan horizon. PTI (Post-Tax Inheritance) is terminal net worth minus the embedded taxes heirs would owe on pre-tax accounts and unrealized gains, what beneficiaries actually keep. Success rate is the share of Monte Carlo trials where the plan keeps the reserve floor through the planning horizon.",
  },
  "strategy_optimize.allocation_mode": {
    pageId: "strategy_optimize",
    title: "Allocation mode",
    body: "Choose the allocation source with the buttons; the page then shows only the controls for that source.",
  },
  "strategy_optimize.holding_period": {
    pageId: "strategy_optimize",
    title: "Holding-period allocation",
    body: "Optional: use this household's own projected withdrawal schedule to nudge the optimizer or max-Sharpe recommendation toward Cash for near-term money and growth for long-horizon money. It has no effect on user-target or tangency modes; selecting the holding-period real-loss-aware mode enables the underlying discovery automatically, whatever this toggle says.",
  },
  "strategy_optimize.override": {
    pageId: "strategy_optimize",
    title: "Optimizer override allocation",
    body: "Leave override rows blank to use the computed optimizer target. Enter percentages only when you want to override the computed result; if any are entered, the override total must equal 100%. Override percentages lock a specific target, bypassing the optimizer.",
  },
  "strategy_optimize.total_wealth": {
    pageId: "strategy_optimize",
    title: "Total wealth allocation",
    body: "Combines the liquid portfolio with illiquid sources credited against allocation targets. Illiquid values use a 20% haircut on home equity and the present value of guaranteed income. This panel is read-only.",
  },
  "strategy_optimize.recommendation": {
    pageId: "strategy_optimize",
    title: "Optimizer recommendation",
    body: "The selection table controls which asset classes the optimizer may use and whether existing holdings satisfy a sleeve before new trades are recommended. This is a second-opinion mix based on risk tolerance or auto risk score, age, withdrawal rate, years to retirement, human-capital stability, existing assets credited against class targets, concentration flags, enabled asset classes, capital-market assumptions, correlations, glide path, and inflation-sensitive spending. Consider it because it can reflect household-specific risk capacity and diversification relationships that a static mix cannot see. The preview's computed targets are read-only and are not written into the user-defined allocation file; Active target used reflects optimizer overrides plus covered or excluded classes.",
  },
  "strategy_optimize.max_sharpe": {
    pageId: "strategy_optimize",
    title: "Max-Sharpe recommendation",
    body: "Keeps the same risk level as the allocation optimizer recommendation (risk tolerance or auto risk score, glide path, guaranteed-income and home-equity coverage), but chooses the equity sleeve's sub-class weights to maximize the sleeve's own Sharpe ratio (return in excess of the risk-free rate, per unit of volatility) instead of a fixed risk-aversion utility. The sleeve's candidate classes are driven by the Selection column: a class set to Exclude never enters it, and a class set to Consider alternate first and mapped to a covered source (guaranteed income, home equity, and so on) is left out once that source meets the target, so large annuities or home equity already covering the bond and real-estate sleeves keep this scoped to the classes it does not already decide. It does not itself re-optimize the equity, bond and cash split, and does not support a manual override.",
  },
  "strategy_optimize.roth_result": {
    pageId: "strategy_optimize",
    title: "Roth optimizer result",
    body: "Score (0-100) ranks the candidates relative to each other (100 is best in this set); it is a scoring unit, not a projected dollar outcome. The workbook's Roth Conversion sheet lists the scored candidates beyond those shown.",
  },
  "strategy_optimize.tax_loss_harvesting": {
    pageId: "strategy_optimize",
    title: "Tax loss harvesting",
    body: "Controls whether and how the projection harvests capital losses from taxable-account lots each year.",
  },
  "strategy_optimize.gain_harvest": {
    pageId: "strategy_optimize",
    title: "Gain harvest",
    body: "Controls whether and how the projection harvests capital gains from taxable-account lots each year (for example to fill up a low tax bracket).",
  },
  "strategy_optimize.funding_rollover": {
    pageId: "strategy_optimize",
    title: "Funding and rollover settings",
    body: "Annual funding tolerance and spousal rollover settings are operational assumptions. They affect workbook QC, survivor account consolidation, RMD timing and late-life cash-flow output.",
  },
  "strategy_optimize.social_security": {
    pageId: "strategy_optimize",
    title: "Social Security",
    body: "Claiming age and benefit assumptions. Pensions and annuities are entered on SS, Pensions and Annuities.",
  },
  "strategy_optimize.hsa_schedule": {
    pageId: "strategy_optimize",
    title: "HSA withdrawal schedule",
    body: "Per-year HSA withdrawal plan for Optimizer mode. There is no separate calculation step: Add Year adds a row for a year, type an amount in Override for it, and that amount applies the next time you save or build, like any other plan field. Optimizer shows the search's own proposal once that feature computes one (not yet available); until then it stays blank and that year draws an even, level amount instead. Locked pins whatever the optimizer proposed, so it has nothing to do yet either.",
  },
  "spending_core.where_to_live": {
    pageId: "spending_core",
    title: "Where to live",
    body: "The Where to live engine searches, given the places you would consider, which location, year and action for each move leaves the plan best off. It does not weigh moving against staying put across a range of timings; that is the When to move engine, the workbook's Housing Comparison sheet, which holds the location fixed and varies the timing instead. Move costs are estimated in the dollars of the year you move, not today's dollars; earlier results understated future moves and favored moving later. The candidate locations are the ZIPs the move's search runs on, pre-checked as the screen promoted them; tick or untick to change the search. Concurrent mode keeps both homes and is only available with Full grid search mode.",
  },
  "spending_core.where_to_live_apply": {
    pageId: "spending_core",
    title: "Apply a housing result",
    body: "This applies the starred (rank 1) option. To apply a different row, change the search so it wins, or edit the Home and Housing fields directly. Estimated utilities, maintenance and insurance re-scale automatically with the price or rent this writes. Because that is a ratio, undoing a price change restores the price exactly and those estimates to within rounding.",
  },
  "spending_core.current_home": {
    pageId: "spending_core",
    title: "Current home",
    body: "Home value, basis and the mortgage balance at plan start. Mortgage payment timing and recurring housing costs are entered in the Housing costs section of Spending Model.",
  },
  "spending_core.next_housing_move": {
    pageId: "spending_core",
    title: "Next housing move",
    body: "Choose whether each housing step is a purchase or a rental; rent stays visible even when the saved rent amount is currently zero. Keeping your home and renting it out? Convert my home to a rental opens Rental Properties with the conversion year set to your next move; you enter the rent, and you leave the sale year blank. Not sure what year or location to plan for? The Where to live search sweeps candidate sale and purchase years, locations and dwelling specs (area type, bedrooms, bathrooms, property type, square footage, lot size) with the same engine as the rest of the plan. Each result reports the ZIP code, an estimated price and the distance to your anchor; transcribe the winning candidate's state, area type, population, ZIP and dwelling fields into the steps here. Once a sale year is set, enter the sale price, commission and related details; home value and basis are managed in Current Home.",
  },
  "spending_core.home_improvements": {
    pageId: "spending_core",
    title: "Home improvement projects",
    body: "Planned improvement costs are entered here as part of Housing. Other pages may reference them read-only.",
  },
  "spending_core.sale_proceeds_split": {
    pageId: "spending_core",
    title: "Split sale proceeds",
    body: "Optional: divide house sale proceeds across more than one account by percentage instead of depositing the full amount to a single account above. Leave empty to use the single account setting instead. Rows must sum to 100%.",
  },
  "spending_core.residency_periods": {
    pageId: "spending_core",
    title: "Residency periods",
    body: "Optional: model a move to another state at a known year instead of one fixed state for the whole plan. All state income tax, estate tax and other state-dependent figures use the state that applies in each projection year. Leave empty to use the single Household residence state for the whole plan. The last row is always open-ended (no end year): it applies from its start year through the end of the plan.",
  },
  "strategy_scenarios.stress_rows": {
    pageId: "strategy_scenarios",
    title: "Home sale stress test",
    body: "Home sale stress-test rows apply to scenario workbook outputs only. Base-plan sale year, future rent, renters insurance and rental utilities are managed on the Housing page. These rows are used by the Scenario Analysis workbook sheet, but they do not change the base-plan Build Impact cards. To change headline terminal net worth, set the Base Plan Home Sale Year on the Housing page. The Home Value and Home Basis shown here are shared canonical Home asset facts. The sale value used by this stress test is projected from the Home Value and appreciation.",
  },
  "strategy_scenarios.change_sets": {
    pageId: "strategy_scenarios",
    title: "Scenario change sets",
    body: "Templates stage common deterministic what-if overrides. Saved sets are browser-local change sets; review the diff, apply a set, then Save Changes, rebuild, and compare in the Planning Workbench. Save the current scenario assumptions when you want a reusable package of what-if overrides. Scenario Change Sets are deterministic planning cases. Use the Stress Suite & Monte Carlo page for probabilistic or adverse-assumption testing. Economy shocks and scenario enable/year controls are grouped first because they determine which dependent assumptions matter. Home sale in this section is the stress-test panel only, affecting scenario sheets; the base-plan home sale is entered once on the Housing page under Spending.",
  },
  "strategy_stress.survivor": {
    pageId: "strategy_stress",
    title: "Survivor stress",
    body: "These are the key inputs driving the Survivor workbook sheet. The primary risks are single-filer tax bracket compression, loss of one Social Security stream, and accelerated required distributions. Change mortality ages or filing status on Household and People to adjust the base assumptions. After rebuilding, view the full Survivor analysis on Retirement Plan Workbook.",
  },
  "strategy_stress.long_term_care": {
    pageId: "strategy_stress",
    title: "Long-term care stress",
    body: "Set care cost and duration, then rebuild. Policy details (benefit amount, elimination period) are on Other assets, where you add a Hybrid LTC policy.",
  },
  "strategy_stress.monte_carlo_mode": {
    pageId: "strategy_stress",
    title: "Monte Carlo engine mode",
    body: "Use Simple for fast assumption testing and Complex for final or advisor-ready workbooks, because each simulated path then runs the fuller planning engine. Simple shows only the settings that materially affect the faster approximation; switch to Complex to see sensitivity grids, stochastic tax and IRMAA, inflation-path, serial-correlation and Wellness-shock controls. Advanced mode runs more trials with higher precision and suits final outputs; quick mode is faster and suits working sessions. Raise the trial count for final runs only when the build time budget allows.",
  },
  "strategy_workbench.decision_panel": {
    pageId: "strategy_workbench",
    title: "Decision panel",
    body: "Every comparison ends with one deliberate choice: adopt selected changes into the saved plan via source pages, keep as a named scenario only, or archive with no action.",
  },
  "strategy_workbench.impact_matrix": {
    pageId: "strategy_workbench",
    title: "Impact matrix",
    body: "LCV is Lifetime Consumption-and-Transfer Value and ELTR is Effective Lifetime Tax Rate. Save staged edits, strategy levers, scenario overrides or stress assumptions as a reusable planning case with the actions above the matrix.",
  },
  "strategy_workbench.forward_looking": {
    pageId: "strategy_workbench",
    title: "Forward-looking figures",
    body: "Supplemental to the Impact matrix, not a substitute: what is left from today forward in the latest build, not the whole-lifetime figures used for comparing cases. FCV is Future Consumption Value and EFTR is Effective Future Tax Rate; build the plan to see them.",
  },
  "strategy_workbench.stress_suite": {
    pageId: "strategy_workbench",
    title: "Stress suite target",
    body: "Run adverse assumptions against the baseline or a saved planning case. Stress tests remain labels and inputs until you save and build deliberately.",
  },
  "strategy_workbench.comparison_context": {
    pageId: "strategy_workbench",
    title: "Comparison context",
    body: "Build Impact uses the same Baseline / Change Set / Run Type / Impact vocabulary as Strategy, Scenario Change Sets and Stress Suite. The selected planning case is for comparison context only; adopt changes on source pages before rebuilding.",
  },
  "detailed_results.workbook": {
    pageId: "detailed_results",
    title: "Retirement Plan Workbook",
    body: "Every workbook result sheet, charts and tables. Charts are rendered natively and tables are enhanced for the UI. Selected result pages load separately, and other pages load only when selected, so large workbooks do not freeze the explorer; the explorer times out instead of staying on a loading message.",
  },
  "monarch_reconciliation.inbox": {
    pageId: "monarch_reconciliation",
    title: "Needs a decision",
    body: "Nothing needs a decision when every matched account agrees with the app, is handled automatically, or is set to ignore. Account balances arrive with the daily account balance import: another process writes balances.csv to the source folder, then the scheduled job loads it. Your choices for each number that differs: Update app copies the imported number once, after a preview. Always update does that now and copies the imported number automatically at each import. App is source keeps the app's number and only reports. Ignore this time hides the difference until the imported number changes.",
  },



  "actual_spending.accounts_sources": {
    pageId: "actual_spending",
    title: "Accounts and sources",
    body: "Where the money came from or is held. Transaction accounts are added automatically from uploaded transactions. This section does not assign spending categories; it identifies account or source type, prior-year balance, current value and any mapped investment account. Add non-transaction sources for annuities, pensions, Social Security, offline assets, real estate, notes, credit cards, loans or other manual assets and liabilities. Investment current value is derived from mapped Holdings accounts, and the mapping dropdowns stay blank until holdings are loaded. Add account/source adds the typed account with the selected type, no pop-up. Recover previous setup is a one-time recovery from a previous SQLite mirror, local Plan Data folder or sibling extracted package. If there are no accounts yet, upload transactions to seed transaction accounts automatically, or use the inline account/source controls to add manual rows.",
  },
  "reports_and_review.build_impact": {
    pageId: "reports_and_review",
    title: "Build impact",
    body: "Dials are heat-mapped: green is the best across all entries, red the worst. LCV (Expected After-Tax Lifetime Consumption-and-Transfer Value) is total lifetime spending plus the after-tax, after-estate-tax terminal transfer to heirs. All-In LCV adds lifetime taxes paid back in, for a single figure that includes every tax dollar. Scenario-only changes are used in the workbook Scenario Analysis sheet but do not move the headline Build Impact cards unless the matching base-plan input is also changed.",
  },
  // End Phase 3b.
  "household_people.people": {
    pageId: "household_people",
    title: "People",
    body: "One row per person; leave Person 2 blank for a single-person household. Birth dates set each person's age, which drives retirement timing, Social Security, Medicare, required distributions and survivor years. The retirement date is when work income stops and retirement spending begins. Mortality age sets how long the plan runs (birth year plus this age); it is a planning horizon, not a prediction. RMD start age is when Required Minimum Distributions begin (SECURE 2.0). The nickname replaces \"Member 1 / Member 2\" in every report, chart and workbook label.",
  },
  "household_people.tax_survivor": {
    pageId: "household_people",
    title: "State, filing status and survivor",
    body: "The state of residence sets state income tax and state estate tax for the modeled period. Filing status sets the tax brackets for every year of the plan. After the first death the plan switches to the survivor filing status (Single or head of household) in the following year, and \"survivor has dependent\" turns on Qualifying Surviving Spouse brackets for two years when they apply.",
  },
  "income_retirement.social_security": {
    pageId: "income_retirement",
    title: "Social Security",
    body: "Enter each person’s FRA Age, Monthly at FRA, and claim date (month/year benefits start) — leave claim date blank to default to age 70, claimed in that person’s own birth month. Claim Age is calculated from the claim date and date of birth, not entered directly. Monthly at Claim Age is calculated: it’s looked up from a saved SSA benefit-table entry for that exact age when available, otherwise it’s derived from FRA Age and Monthly at FRA using the SSA reduction/delayed-credit factor. FRA Age defaults to 67 (SSA birth-year rule) if left blank.",
  },
  "income_retirement.pensions_annuities": {
    pageId: "income_retirement",
    title: "Pensions and annuities",
    body: "Each card starts with Type, then the payment and valuation fields for that income stream. Recovery Age is the age at which each stream's cash dividend payout stops (the guaranteed payment continues for life).",
  },
  "income_retirement.ss_policy": {
    pageId: "income_retirement",
    title: "Social Security policy and benefit details",
    body: "Household-wide spousal, survivor, and funding-discount policy settings.",
  },
  "holdings.plan_holdings": {
    pageId: "holdings",
    title: "Plan Holdings",
    body: "Enter investment holdings by account and lot. A lot is a separate purchase, reinvestment, or cash position. Use CASH with price 1 for cash balances. CSV import columns: account, symbol, purchase_date, shares, purchase_price, lot_type, note — date as YYYY-MM-DD, lot_type as standard, reinvestment, or cash. Download a template from your broker CSV export or use Export CSV backup in Settings first.",
  },
  "holdings.pricing_tester": {
    pageId: "holdings",
    title: "Live pricing tester",
    body: "Type one ticker to see every live pricing command and response trace without relying on the workbook build.",
  },
  "spending_core.large_discretionary": {
    pageId: "spending_core",
    title: "Large Discretionary",
    body: "The table shows the year selected on Actual Spending; change it with the Year pull-down there. Add one row per one-time expense. A row counts toward that year's budget only when its year is the year shown. Each row is one-time: it projects only in its own year (inflated from today's dollars) and is never annualized. Large Discretionary rows are one-time: Weddings, Large Gifts, Education (not 529-funded), Auto, or Other. Enter amounts in today's dollars; the projection inflates each to its year.",
  },
  "spending_core.adjustments": {
    pageId: "spending_core",
    title: "Spending Adjustments",
    body: "A step change to a category (or a whole tracking type) from a start year; inflation continues on the stepped amount. Rows on the same category compound in start-year order, and an \"All\" row compounds with a category's own rows. Leave End year blank to run through plan end. Large Discretionary, Taxes and Business are not adjustable.",
  },
  "spending_core.housing_costs": {
    pageId: "spending_core",
    title: "Housing costs",
    body: "Housing costs: mortgage payment timing and other recurring home costs. Real-estate taxes, homeowners insurance, maintenance, utilities, and HOA are budgeted in the groups below. Click Seed Housing Fields to add any missing housing fields. Housing is the only editable place for mortgage/rent, homeowners insurance, home maintenance, utilities, real-estate taxes, and home improvement projects.",
  },
  "spending_core.wellness": {
    pageId: "spending_core",
    title: "Wellness",
    body: "Wellness is the authoritative view for healthcare spending. Enter Pre-65 premiums, Medicare Part B/D/G premiums, and non-premium medical, dental, vision, Rx/OTC, and out-of-pocket estimates. The projection uses these values as-entered for cash flow and income impact; Medicare premium categories are split to match spending taxonomy. Wellness is the only editable place for the Healthcare Premium group (Pre-65 Healthcare Premium plus Medicare Part B, Part D, and Part G), medical, dental, vision, drugs Rx/OTC, vitamins/supplements, and the medical OOP cap/reference.",
  },
  "spending_core.travel_budget": {
    pageId: "spending_core",
    title: "Travel",
    body: "Travel is the only editable place for recurring travel projection inputs plus transaction-based travel detail. Domestic-travel and lifestyle labels are intentionally not used here. A group in Summary mode budgets the whole group -- group number wins over its categories.",
  },
  "spending_core.home_links": {
    pageId: "spending_core",
    title: "Home value and housing moves",
    body: "Home value and mortgage balance are on Other Assets and Liabilities; home sale, next housing steps and state residency are in Optimize → Next Housing Move.",
  },
  "spending_core.projection_controls": {
    pageId: "spending_core",
    title: "Projection Controls",
    body: "Core spending base and growth feed recurring lifestyle spending in the projection. If a control is missing, the expected rows are Core Spending Base, Core Spending Increase Stops, Core Spending Increase Method, and the relevant increase-rate field.",
  },
  "spending_core.category_manager": {
    pageId: "spending_core",
    title: "Category Manager",
    body: "Manage the canonical Tracking Type → Group → Category tree. Transaction assignment uses these canonical categories, so there is no separate group-mapping table to maintain.",
  },
  "spending_core.category_rules": {
    pageId: "spending_core",
    title: "Advanced Auto-Mapping Rules",
    body: "Optional rules auto-assign imported merchant or category text to a canonical Spending Category. Most users should use the category picker in Spending Categories; use these rules only when the same text should be classified automatically every time. Add a rule only for merchant/category text that should be classified the same way every time.",
  },
  "spending_core.spending_categories": {
    pageId: "spending_core",
    title: "Spending Categories",
    body: "Spending Categories shows Tracking Types, Groups, and Categories with non-zero YTD Actual, Annualized, Annual Budget, or Projection. Use Income & Expense Transactions to import transactions, or add budget/projection values on the source page, then Reload. This section is organised by Tracking Types, Groups and Categories. Spending Categories is comprehensive: Income and every expense Tracking Type, including Taxes, should appear in the hierarchy -- only internal transfers are excluded. Housing, Wellness, and Travel are edited in their own accordions below. Each group header shows both Annual Budget (what you entered) and Projection (the value the projection engine actually uses as the starting spend amount). They are usually equal — expand the help below to see when and why they can differ.",
  },
  "spending_core.budget_vs_projection": {
    pageId: "spending_core",
    title: "Annual Budget vs. Projection",
    body: "▸ Annual Budget vs. Projection — when do they differ?Annual Budget is what you entered. Projection is what the engine uses as the year-one spending base for that category. In most cases they are equal. They diverge in four scenarios:Cap/reference categories (e.g., Medical OOP Cap in Wellness): Annual Budget holds the cap value so you can see it; Projection is forced to $0 because a cap is a ceiling on out-of-pocket costs, not a recurring spending input.Group in Summary mode: The single group-level override number becomes the Projection for the whole group. Any per-category Annual Budget values that were entered before switching to Summary are stale — the engine ignores them and uses the group total.Detail-line total disagrees with the Annual Budget override: In Detail mode, Projection equals the sum of the detail lines. If you also typed a manual value in the Annual field, it is stored but overridden by the line sum in the projection.$0 budget categories with transaction history: The category appears in the table because transactions were imported, but Projection = $0, so it contributes nothing to the projected spend base.The Projection column in each group header shows the value that feeds the projection. If it looks wrong compared to Annual Budget, check whether Summary mode is active or whether a cap/reference flag is set on that category.",
  },
  "actual_spending.actions": {
    pageId: "actual_spending",
    title: "Budget and model actions",
    body: "Initialize Budget from Actual Spending creates category budget targets based on current actual spending proportions. Sync Actual Rate → 30-Year Model updates the spending categories assumption used by the 30-year retirement projection, and sets the retirement model's core spending assumption to the annualized rate.",
  },
  "actual_spending.kpis": {
    pageId: "actual_spending",
    title: "Spending totals",
    body: "The five KPI tiles include income taxes and exclude only internal transfers. The All-In row adds transfer transactions back in; when no transfer transactions are logged for the year, the All-In totals would match the tiles and are omitted. The \"! >3%\" badge in the left nav appears when annualized spending (all Tracking Types, including taxes) exceeds the annual budget by more than 3%. Review the categories, or raise the budget if this is the right run rate.",
  },
  "actual_spending.monthly_trajectory": {
    pageId: "actual_spending",
    title: "Monthly Trajectory",
    body: "Includes Housing, Wellness/healthcare, Travel, Large Discretionary, Business, Core Expense, and Taxes outflows when present in transactions. Internal transfers are excluded.",
  },
  "actual_spending.model_managed": {
    pageId: "actual_spending",
    title: "Model-Managed (Not in Core Budget)",
    body: "These categories are tracked separately by the projection model and excluded from the spending categories budget.",
  },
  "actual_spending.business": {
    pageId: "actual_spending",
    title: "Business Expenses",
    body: "Business expenses tracked separately from personal core budget.",
  },
  "rental_properties.list": {
    pageId: "rental_properties",
    title: "Rental properties",
    body: "Net yield = (rent - operating expenses) / value.",
  },
  "rental_properties.convert_home": {
    pageId: "rental_properties",
    title: "Convert my home to a rental",
    body: "Pre-filled from your plan's home. Change anything before creating. Conversion year defaults to your next housing move year. Value at conversion is your home's value grown to that year. Depreciation basis is the lesser of value and adjusted basis, land excluded. Monthly rent is what you expect to charge; it is required. Section 121 applies to this property only: owned and lived in 2 of the 5 years before sale. Depreciation is never excluded.",
  },
  "rental_properties.detail": {
    pageId: "rental_properties",
    title: "Property detail",
    body: "A converted home keeps your plan's own mortgage for the home. A converted home is sold with your plan's home (Other Assets and Liabilities). Gain, depreciation recapture (capped at 25%) and the tax at sale are computed by the projection. A loss on the sale is treated as ordinary. Per-year overrides (an Expert feature) replace the rent and expense formulas for years that differ.",
  },
  "assets_special.other_asset_items": {
    pageId: "assets_special",
    title: "Other Asset Items",
    body: "One row per non-portfolio asset — auto, boat, start-up equity, art, or collectible. Enter today's estimated value and as-of date. Use a positive annual rate for appreciating assets (e.g., collectibles, equity) and a negative rate for depreciating ones (e.g., vehicles). For appreciating assets such as start-up equity, art, or collectibles, enter a basis when you know the purchase price or tax basis. For depreciating assets, basis can be left blank unless it matters for a later sale scenario.",
  },
  "assets_special.note_interest": {
    pageId: "assets_special",
    title: "Note interest by year",
    body: "Interest by year: Enter the expected taxable interest income from this note for each calendar year. This affects cash flow, taxable income, NIIT exposure, and projected note income. Years run across the top.",
  },
  "assets_special.notes_receivable": {
    pageId: "assets_special",
    title: "Notes receivable",
    body: "One or more promissory notes receivable. Each note has a descriptive name plus its own face value, payment schedule, and interest-by-year detail. The current note is named \"RedMane Note\".",
  },
  "assets_special.hsa_withdrawals": {
    pageId: "assets_special",
    title: "HSA withdrawal timing",
    body: "Withdrawal timing: choose how the HSA is used in Cash Flow. Spend as needed uses HSA for qualified Wellness costs/gaps. Annual percentage and Smooth window use the start/end years below to schedule HSA withdrawals across the cash-flow projection.",
  },
  "assets_special.hsa_contributions": {
    pageId: "assets_special",
    title: "HSA contributions",
    body: "Contribution limits and eligibility feed annual HSA additions before Medicare eligibility.",
  },
  "assets_special.education_529": {
    pageId: "assets_special",
    title: "529 plans",
    body: "Purpose: 529 plans are education savings accounts. Enter one section per beneficiary or goal, then add another 529 when a different beneficiary or goal should be tracked separately.",
  },
  "assets_special.family_business": {
    pageId: "assets_special",
    title: "Family & Business",
    body: "These are the Family & Business features that carry plan inputs. They are also editable in place on Other Assets and Liabilities, beside the rest of the non-portfolio assets. Business entity choice (S-Corp vs LLC) is entered on Work Income.",
  },
  "assets_special.heloc_summary": {
    pageId: "assets_special",
    title: "HELOC summary",
    body: "Read-only summary — shown here with other liabilities so the borrowing assumption is not stranded on the Strategy page; edit on the HELOC Strategy page.",
  },
  "assets_special.liabilities": {
    pageId: "assets_special",
    title: "Liabilities",
    body: "Purpose: Track loans the plan must pay down over time. Choose a type, then enter the fields needed to forecast its cash flow. Each liability is amortized into the yearly cash-flow forecast and its outstanding balance reduces net worth. Auto and student loans use standard fixed amortization; credit cards take a balance, APR and monthly payment (no payment = interest-only; add a payoff month/year to retire the card on that date); HELOC line items amortize over the years to payoff. On the payoff date the remaining balance is paid off and carried at $0 afterwards (untick \"Carry $0\" to keep a residual balance instead). Leave a field blank to use sensible defaults (no monthly payment = interest-only unless a payoff year is set). Carry $0 after payoff: the balance is $0 from the payoff date onward; untick it to keep any residual balance on the books.",
  },
  "heloc_strategy.inputs": {
    pageId: "heloc_strategy",
    title: "HELOC modeling inputs",
    body: "Turn on HELOC strategy to reveal the borrowing assumptions.",
  },
  "strategy_optimize.withdrawal_account_order": {
    pageId: "strategy_optimize",
    title: "Account draw order",
    body: "Drag the handle on a row to reorder accounts. Accounts nearer the top are drawn first within their account type. The order saves automatically when you leave this section, and you can use Reset to default order to go back to the standard order.",
  },
  "optional_functions.tiers": {
    pageId: "optional_functions",
    title: "Plan tiers",
    body: "Picking a tier sets every switch to that tier's preset; you can still change any switch afterwards. Until you pick a tier, the plan keeps the switches it already has, which are read as Expert.",
  },
  "assets_special.reporting_fields": {
    pageId: "assets_special",
    title: "Reporting-only fields",
    body: "Some fields on this page feed reporting and workbook narrative only. They do not directly affect cash-flow or tax calculations. Review the workbook output after a rebuild to confirm what affected each projection year.",
  },
  "strategy_optimize.hsa_policy": {
    pageId: "strategy_optimize",
    title: "HSA withdrawal policy",
    body: "Start here: choose the HSA withdrawal mode. The schedule fields below change based on that mode. The default is spend as needed, which hides the annual-percentage and window controls.",
  },
  "strategy_workbench.model": {
    pageId: "strategy_workbench",
    title: "Planning Workbench model",
    body: "The workbench follows one chain: Baseline, then Change Set, then Run Type, then Impact, then Decision. A Planning Case is stored only in your browser and never changes the saved plan by itself.",
  },
  "assets_home_cash.reserve_rules": {
    pageId: "assets_home_cash",
    title: "Reserve requirements",
    body: "Purpose: a reserve requirement keeps a chosen number of years of expenses in reserve for the selected year range. The default is 0 years. Add rows only when the reserve policy changes over time.\n\nTip: leave End year blank for an open-ended rule. If rows overlap, the model uses the first matching row.",
  },
  "workbook_formatting.widths": {
    pageId: "workbook_formatting",
    title: "Adjusting column widths",
    body: "Adjust Excel column widths per sheet, table and column. Widths come from the most recently built workbook. Every edit saves immediately, so there is no separate Save step, and no other part of the app ever touches these saved widths except this page. Columns you do not touch keep their automatic width.",
  },
  "actual_spending.import_transactions": {
    pageId: "actual_spending",
    title: "Importing transactions",
    body: "CSV columns: Date, Merchant, Category, Account, Original Statement, Notes, Amount, Tags, Owner. Only Date and Amount are required. Column order does not matter, capitalization is ignored, and extra columns are skipped. All rows with a valid date are imported, regardless of year. Use the Year pull-down above to choose which calendar year's actuals are shown.\n\nUploading transaction data enables YTD spending, income, growth charts, transaction editing and account mapping. All years of transaction history are kept. Use Accounts and Sources below the import to identify account or source type and balances.",
  },
  "strategy_optimize.withdrawal_order": {
    pageId: "strategy_optimize",
    title: "Withdrawal order",
    body: "Individual-account draw order is user-configurable below. Each account defaults to its registry order and draws first within its account type when priority is tied; set a lower number to draw an account earlier relative to others of the same type (for example, which of two taxable brokerage accounts drains first).\n\nThe account-type sequence itself is fixed by the engine and is not user-configurable, because it follows tax rules rather than preference (shown above the table). RMDs are mandatory income; Roth and home equity are preserved until other liquid sources are exhausted.",
  },
  "strategy_optimize.selection_modes": {
    pageId: "strategy_optimize",
    title: "Allocation policy modes",
    body: "Optimizer mode: user target percentages are hidden because the next build will not use them; they are listed in Inactive values above when saved. The workbook uses the computed optimizer target, unless you enter a full optional optimizer override. Excluded rows and covered rows are removed from the active liquid target before the remaining recommendation is normalized.\n\nMax-Sharpe (risk-budgeted) mode: keeps the same risk level as the optimizer recommendation (risk tolerance, glide path, guaranteed-income and home-equity coverage) but chooses the equity sleeve with the best risk-adjusted (Sharpe) return, using the same Selection-driven candidate classes as the optimizer recommendation (Excluded classes, and classes already covered by a mapped guaranteed-income or home-equity source, are left out). It does not support a manual override.\n\nPure tangency mode: ignores risk tolerance and glide path entirely and solves for the single portfolio with the highest Sharpe ratio across the enabled and uncovered classes below (Excluded classes, and classes already covered by a mapped guaranteed-income or home-equity source, are left out). It does not support a manual override. Review the recommended risk level carefully before using it to drive the plan.\n\nHolding-period real-loss-aware mode: splits today's liquid balance into holding-period buckets from this household's own projected withdrawal schedule and solves each bucket separately across the enabled and uncovered classes below, with an added real-loss-probability penalty (Excluded and covered classes are left out). It does not support a manual override.\n\nUser-defined mode: this table edits the active user target %. Rows are grouped by Equity, Fixed income, and Other. Choose exactly one action per row. Include and Consider alternate first activate the user target %. Exclude ignores that row's target.",
  },
  "strategy_optimize.tangency": {
    pageId: "strategy_optimize",
    title: "Pure tangency recommendation",
    body: "No risk budget: this solves for the single long-only portfolio, across the enabled and uncovered asset classes, with the highest possible Sharpe ratio. It still respects the Selection column below: Excluded classes are never candidates, and a class set to Consider alternate first and mapped to a covered source (guaranteed income, home equity, and so on) is left out once that source meets the target. So if this household's annuities or home equity already cover the bond and real-estate sleeves, tangency is automatically scoped to the remaining liquid classes, driven by that configuration rather than a fixed list.\n\nRisk tolerance and glide path are not applied, and it does not support a manual override. It can concentrate heavily in a single class depending on the configured capital-market assumptions, so review it as an analytical reference before using it to drive the plan.",
  },
  "strategy_optimize.real_loss_aware": {
    pageId: "strategy_optimize",
    title: "Holding-period real-loss-aware recommendation",
    body: "No risk budget: today's liquid balance is split into holding-period buckets based on this household's own projected withdrawal schedule, and each bucket is solved separately across the enabled and uncovered asset classes with an added penalty for that bucket's probability of a real (inflation-adjusted) loss at that holding period. Near-term buckets are penalized for holding equities; long-horizon buckets are penalized for sitting in cash. The final recommendation blends each bucket's solution by its dollar share of today's balance.\n\nIt still respects the Selection column below: Excluded classes are never candidates, and a class set to Consider alternate first and mapped to a covered source (guaranteed income, home equity, and so on) is left out once that source meets the target. Risk tolerance and glide path are not applied, and it does not support a manual override.",
  },
  "annuity_death_benefits.policies": {
    pageId: "annuity_death_benefits",
    title: "Insurance policies",
    body: "Each policy appears as a collapsible section with a policy-type pulldown. Premium-end and term-end fields are YYYY year inputs. Add another policy from the selector below the sections; duplicate types receive a sequential number.",
  },
  "reports_and_review.model_used": {
    pageId: "reports_and_review",
    title: "What the model used in this build",
    body: "Plain-English checks for assumptions that materially change cash flow, taxes, risk, and terminal net worth. These are not extra recommendations; they explain which model switches were actually consumed so you can run targeted what-if tests.",
  },
  "reports_and_review.dynamic_suggestions": {
    pageId: "reports_and_review",
    title: "Suggestions to improve the plan without lowering risk",
    body: "These suggestions are generated from this build's LCV, NPV of Future Taxes, Worst-Case Ending Wealth (5th percentile), and model-heard assumptions. Keep Worst-Case Ending Wealth flat or better when improving LCV or lowering NPV of Future Taxes.",
  },
};

// HELP_FIELDS[key]: purpose/impact/consider merged over fieldGuidance() by showFieldHelp. The key
// is the row label with the person number dropped (member_1_nickname -> member_nickname).
export const HELP_FIELDS = {
  member_nickname: {
    purpose: "The short name the plan uses for this person everywhere it names them: reports, charts and workbook labels.",
    impact: "Changes labels only, not any calculation.",
    consider: "Use the name the household goes by. Leave it blank to use the first name.",
  },
  member_mortality_age: {
    purpose: "How long the plan runs for this person: the plan horizon is the birth year plus this age. It is a planning horizon, not a prediction.",
    impact: "A higher age adds years the savings must pay for, with more late-life taxes and required distributions, which can lower terminal net worth and the probability of success.",
    consider: "Use an age the person is unlikely to outlive, so the plan does not end too early. Test a higher age as a stress case.",
  },
  survivor_filing_status: {
    purpose: "The filing status used after the first death: Single, or HOH (head of household) when its rules truly apply.",
    impact: "Sets the tax brackets for the survivor's years. Single brackets are narrower than married filing jointly, so the same income is usually taxed more.",
    consider: "Use Single unless the survivor will keep a qualifying dependent at home.",
  },
  survivor_has_dependent: {
    purpose: "Whether the survivor will have a dependent child at home after the first death.",
    impact: "When yes, the plan uses Qualifying Surviving Spouse brackets for two years after the first death when they apply.",
    consider: "Answer yes only if a dependent child will live with the survivor.",
  },
};

// The 11 pre-build input pages, Household through Estate & Legacy in nav order: the help panel
// opens on arrival here unless the user closed it (retirementHelpOpen = "0").
export const PRE_BUILD_PAGES = [
  "household_people", "income_work", "income_retirement", "spending_core", "holdings",
  "assets_home_cash", "assets_special", "heloc_strategy", "rental_properties",
  "annuity_death_benefits", "estate",
];
export const NARROW_QUERY = "(max-width:1180px)";

const escHtml = (v) =>
  String(v).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const win = typeof window !== "undefined" ? window : {};
const prose = (s) => escHtml(typeof win.addParentheticals === "function" ? win.addParentheticals(s) : s);

function termsHtml(terms) {
  const list = (terms || []).filter((t) => GLOSSARY[t]);
  return list.length
    ? `<h3>Words on this page</h3><dl class="help-terms">${list.map((t) => `<dt>${escHtml(t)}</dt><dd>${escHtml(GLOSSARY[t])}</dd>`).join("")}</dl>`
    : "";
}

// HTML for the "In plain English" line and the page's glossary terms; "" for pages without an entry.
export function plainHelpHtml(stepId) {
  const page = HELP_PAGES[stepId];
  if (!page) return "";
  const terms = page.terms.filter((t) => GLOSSARY[t]);
  const list = terms.length
    ? `<details class="plain-terms"><summary>Words on this page (${terms.length})</summary><dl>${terms
        .map((t) => `<dt>${escHtml(t)}</dt><dd>${escHtml(GLOSSARY[t])}</dd>`)
        .join("")}</dl></details>`
    : "";
  return `<div class="plain-help"><b>In plain English:</b> ${escHtml(page.summary)}${list}</div>`;
}

// Panel page help in the fixed layout; null only for an unknown page id.
export function pageHelpHtml(stepId) {
  const p = HELP_PAGES[stepId];
  if (!p || !p.whatFor) return null;
  const parts = [
    ["What this page is for", p.whatFor],
    ["How the values work together", p.connections],
    ["How to choose values", p.options],
    ["Likely planning impact", p.impact],
  ].filter((x) => x[1]);
  const acronyms = typeof win.acronymDefinitionsHtml === "function" ? win.acronymDefinitionsHtml(parts.map((x) => x[1])) : "";
  return `<div class="help-title">${escHtml(p.title)}</div><div class="help-body"><p class="help-plain"><b>In plain English:</b> ${escHtml(p.summary)}</p>${parts
    .map((x) => `<h3>${x[0]}</h3><p>${prose(x[1])}</p>`)
    .join("")}${termsHtml(p.terms)}${acronyms}</div>`;
}

export function sectionHelpHtml(key) {
  const s = HELP_SECTIONS[key];
  if (!s) return null;
  const page = HELP_PAGES[s.pageId] || {};
  return `<div class="help-title">${escHtml(s.title)}</div><div class="help-body"><p class="small">Section of ${escHtml(page.title || s.pageId)} <button type="button" class="btn tiny" onclick="openStepHelp('${s.pageId}')">Page help</button></p><p>${prose(s.body)}</p>${termsHtml(page.terms)}</div>`;
}

export function fieldHelpEntry(label) {
  const key = String(label || "").trim().toLowerCase().replace(/^member_\d+_/, "member_");
  return HELP_FIELDS[key] || null;
}

// Small "?" beside a page title / section heading; aria-controls marks it as a panel opener.
export function pageHelpButtonHtml(stepId) {
  return `<button type="button" class="page-help-btn" aria-controls="helpPanel" aria-label="Help for this page" title="Help for this page" onclick="openStepHelp('${escHtml(stepId)}')">?</button>`;
}
export function sectionHelpButtonHtml(key) {
  const s = HELP_SECTIONS[key];
  return s
    ? `<button type="button" class="section-help-btn" aria-controls="helpPanel" aria-label="Help for the ${escHtml(s.title)} section" data-help-section-btn="${escHtml(key)}">?</button>`
    : "";
}

// Open state on arriving at a page: the remembered choice wins; otherwise open on pre-build pages.
// Never auto-open below 1180px, where the panel is a slide-over sheet covering the page.
export function helpOpenOnArrival(stepId, pref, narrow) {
  if (narrow) return false;
  if (pref === "1") return true;
  if (pref === "0") return false;
  return PRE_BUILD_PAGES.includes(stepId);
}

// What the panel currently shows, so a re-render of the same page keeps pinned field/section help.
const state = { step: null, kind: null, ref: null };
export function helpPanelState() {
  return { ...state };
}
export function pinHelp(kind, ref) {
  state.kind = kind;
  state.ref = ref === undefined ? null : ref;
}

function readPref() {
  try {
    return win.localStorage ? win.localStorage.getItem("retirementHelpOpen") : null;
  } catch (_e) {
    return null;
  }
}
function isNarrow() {
  return !!(win.matchMedia && win.matchMedia(NARROW_QUERY).matches);
}
function setOpen(open) {
  const doc = win.document;
  if (!doc || !doc.body) return;
  doc.body.classList.toggle("help-open", open);
  const btn = doc.querySelector && doc.querySelector("#helpPane .help-toggle");
  if (btn) btn.setAttribute("aria-expanded", open ? "true" : "false");
}

// Called by showStepHelp: applies the open policy when the page changes and returns whether
// the page help should be written (false keeps a pinned field or section entry on a re-render).
export function arriveAtPage(stepId, force) {
  const changed = stepId !== state.step;
  if (changed) {
    state.step = stepId;
    setOpen(helpOpenOnArrival(stepId, readPref(), isNarrow()));
  }
  if (!force && !changed && state.kind && state.kind !== "page") return false;
  pinHelp("page");
  return true;
}

export function showSectionHelp(key) {
  const html = sectionHelpHtml(key);
  const panel = win.document && win.document.getElementById("helpPanel");
  if (!html || !panel || (state.kind === "section" && state.ref === key)) return;
  panel.innerHTML = html;
  pinHelp("section", key);
}

export function openStepHelp(stepId) {
  setOpen(true);
  if (typeof win.showStepHelp === "function") win.showStepHelp(stepId || win.activeStep, true);
}

// Follow focus inside the center panel: field help on field focus, section help when focus enters
// a section outside a field (its "?" button, summary, links). Content only: never moves focus.
export function onHelpFocusIn(e) {
  const t = e && e.target;
  if (!t || !t.closest || !t.closest("#mainPane")) return;
  const field = t.closest('.field[id^="field-"]');
  if (field) {
    const idx = Number(field.id.slice(6));
    if (Number.isFinite(idx) && !(state.kind === "field" && state.ref === idx) && typeof win.showFieldHelp === "function")
      win.showFieldHelp(idx);
    return;
  }
  const sec = t.closest("[data-help-section]");
  if (sec && !/^(INPUT|SELECT|TEXTAREA)$/.test(t.tagName || "")) showSectionHelp(sec.getAttribute("data-help-section"));
}
export function onHelpToggle(e) {
  const d = e && e.target;
  const doc = win.document;
  if (!d || d.tagName !== "DETAILS" || !d.open || !d.matches || !d.matches("[data-help-section]")) return;
  // renderMain restores open <details> after every render; only a user toggle (focus inside) counts.
  if (doc && d.contains(doc.activeElement)) showSectionHelp(d.getAttribute("data-help-section"));
}
// Explicit openers ("i", "?", section "?"): anything with aria-controls="helpPanel" except the sheet toggle.
export function onHelpClick(e) {
  const t = e && e.target;
  const b = t && t.closest && t.closest('[aria-controls="helpPanel"]');
  if (!b || b.classList.contains("help-toggle")) return;
  const key = b.getAttribute("data-help-section-btn");
  if (key) showSectionHelp(key);
  setOpen(true);
}
export function onHelpKeydown(e) {
  const doc = win.document;
  if (!e || e.key !== "Escape" || !doc || !isNarrow() || !doc.body.classList.contains("help-open")) return;
  const pane = doc.getElementById("helpPane");
  const back = pane && pane.contains(doc.activeElement) ? doc.querySelector(".page-help-btn") : null;
  if (typeof win.toggleHelpSheet === "function") win.toggleHelpSheet();
  else setOpen(false);
  if (back) back.focus();
}

if (typeof window !== "undefined") {
  window.RPHelp = { pageHtml: pageHelpHtml, summary: (id) => (HELP_PAGES[id] || {}).summary || "", arrive: arriveAtPage, pinned: pinHelp, fieldEntry: fieldHelpEntry, sectionButtonHtml: sectionHelpButtonHtml };
  Object.assign(window, { plainHelpHtml, pageHelpButtonHtml, openStepHelp });
  if (window.document && window.document.addEventListener) {
    window.document.addEventListener("focusin", onHelpFocusIn);
    window.document.addEventListener("toggle", onHelpToggle, true);
    window.document.addEventListener("click", onHelpClick);
    window.document.addEventListener("keydown", onHelpKeydown);
  }
}
