// Contextual help registry (Contextual Help Panel plan, Phase 1; was help_glossary.js, WI-033):
// one source for page, section and field help, the glossary, and the right panel's follow-focus
// behaviour. Data and lookup only for the center panel: window.plainHelpHtml(stepId) still feeds
// the page help box in dashboard.js until Phase 2 removes it. Plain-English text is written for
// a high-school reader with little financial experience (documentation/future/WI-033_*.md).
// Pages without a full HELP_PAGES record (only summary + terms) keep the old STEP_HELP text.
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

// HELP_PAGES[stepId] = { summary, terms } for every page; pages with whatFor also carry title,
// connections, options and impact and render in the panel's fixed layout (pilot: Household & People).
export const HELP_PAGES = {
  "start": {"summary": "Open or create your plan, see what is still missing, and pick what to do next.", "terms": ["Readiness (readiness checks)"]},
  "household_people": {
    "title": "Household & People",
    "summary": "Who is in the household, when each person was born and plans to retire, and where you live and file taxes.",
    "whatFor": "This page defines the people, tax identity, state, and filing status used by the model, plus when earned income stops, when retirement spending begins, and how long the household should be projected. These are identity and tax-foundation inputs rather than strategy levers. Mortality age is a planning horizon, not a prediction.",
    "connections": "Birth dates set ages. Ages connect to retirement timing, Social Security, Medicare, RMDs, mortality horizon, survivor years, and estate planning. Filing status and state connect to tax brackets, state taxes, and survivor tax treatment. Retirement dates connect to work income, savings contributions, healthcare bridge years, withdrawals, Roth conversion room, and Monte Carlo sequence risk. Life expectancy and survivor assumptions determine late-life taxes, RMD pressure, and legacy values.",
    "options": "Use actual dates when possible. Use MFJ for married filing jointly, Single after a survivor period when appropriate, HOH only when household rules truly apply, and the resident state expected for the modeled period. Earlier retirement increases years funded by assets. Later retirement adds income, reduces withdrawals, and shortens the funding horizon.",
    "impact": "Changing ages or filing status can materially change lifetime taxes, RMD timing, Social Security timing, Medicare years, survivor cash flow, and terminal net worth. Changing state may affect state tax, estate tax, and residency optimizer output. Retiring later usually increases terminal net worth and probability of success. Retiring earlier usually lowers liquidity and may reduce success unless spending, income, or home-equity assumptions compensate.",
    "terms": ["Filing status", "Planning horizon", "Mortality age", "Survivor assumptions", "Tax bracket"],
  },
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

// HELP_SECTIONS[key]: key is the section's data-help-section attribute, "<pageId>.<section>".
export const HELP_SECTIONS = {
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

// Panel page help in the fixed layout; null when the page has no full record (caller falls back to STEP_HELP).
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
  window.RPHelp = { pageHtml: pageHelpHtml, arrive: arriveAtPage, pinned: pinHelp, fieldEntry: fieldHelpEntry, sectionButtonHtml: sectionHelpButtonHtml };
  Object.assign(window, { plainHelpHtml, pageHelpButtonHtml, openStepHelp });
  if (window.document && window.document.addEventListener) {
    window.document.addEventListener("focusin", onHelpFocusIn);
    window.document.addEventListener("toggle", onHelpToggle, true);
    window.document.addEventListener("click", onHelpClick);
    window.document.addEventListener("keydown", onHelpKeydown);
  }
}
