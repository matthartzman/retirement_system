// Housing move optimizer panel. Split out of
// dashboard_decomp_housing_scenarios.js on 2026-09-16: that file also owns the
// spending/housing screen and had reached 1,841 lines, and the optimizer block
// roughly doubles in size under the refinement design
// (docs/superpowers/specs/2026-09-16-housing-optimizer-refinement-design.md
// §9.1). renderScenarioManagementPanel() still embeds the panel, so its
// position in Strategy -> Scenarios is unchanged; index.html loads this module
// BEFORE dashboard_decomp_housing_scenarios.js so the bare-global call in
// renderScenarioManagementPanel resolves.
//
// Layout rule (design §9.2): every control is wrapped by housingOptField,
// which stacks the label ABOVE the control. A label placed to the left adds
// its width to every field and pushes a six-field row into horizontal
// scrolling, whereas a stacked cell is exactly as wide as its control. Helper
// text is never inline for the same reason -- it lives in the app's right-hand
// Context Help pane, reached via the "i" affordance and the field row's own
// showHousingOptFieldHelp() click (design §9.5).
//
// Sizing is CSS-class-driven (`year`, `zip`, `money`, `count` under a
// .housing-optimize-panel scope) rather than an inline width style attribute,
// so the widths stay in one place and can be tuned without touching this
// markup. Task 14 defines those classes.

const HOUSING_OPT_MIN_ANCHORS = 2;
const HOUSING_OPT_MAX_ANCHORS = 5;

// Persistence (§9.6). The <details> wrapper renderHousingOptimizePanelHtml()
// returns carries this id so saveHousingOptInputs() can scope its
// querySelectorAll to just the panel (never picking up unrelated page
// controls that happen to share an id-less coincidence) and so the details
// open/closed state has something stable to read and restore.
export const HOUSING_OPT_PANEL_ID = "housingOptPanel";
const HOUSING_OPT_RESULTS_ID = "housingOptimizeResults";
export const HOUSING_OPT_STORAGE_KEY = "retirement.housing_optimizer.v1";

// Keys in the stored payload that are not themselves a DOM element's id --
// the per-move anchor *count* has no backing control (it is the module-level
// housingOptAnchorCounts map below) and the details open state belongs to
// the panel wrapper itself, not a form field. Prefixed with a double
// underscore so they can never collide with a real field id, which are all
// plain camelCase.
const HOUSING_OPT_PERSIST_META_KEYS = new Set([
  "__move1AnchorCount",
  "__move2AnchorCount",
  "__detailsOpen",
]);

// Enum/range constants mirroring src/housing/models.py and
// src/housing/zip_screen/schema.py exactly (Task 12) -- validateHousingOptForm
// checks these client-side so the Run button disables before a doomed request
// is ever sent, but src/housing/api.py's validate_request is the copy that is
// trusted. Both lists must be kept in sync by hand; there is no shared source
// a browser script can import from a Python module.
const HOUSING_OPT_OBJECTIVES = ["net_worth", "lifetime_cost", "mc_success_rate"];
const HOUSING_OPT_SEARCH_MODES = ["full", "narrowed"];
const HOUSING_OPT_MOVE2_STRATEGIES = ["anchored", "cross_product"];
const HOUSING_OPT_DISPOSITIONS = ["sell", "keep", "auto"];
const HOUSING_OPT_ALLOWED_RADII_MILES = [5, 10, 25, 50];
const HOUSING_OPT_FAMILY_RADII_MILES = [10, 25, 50, 100];

// Per-move anchor counts, keyed by move index. Rendered markup and the
// add/remove controls both read this, so the two never disagree.
const housingOptAnchorCounts = { 1: HOUSING_OPT_MIN_ANCHORS, 2: HOUSING_OPT_MIN_ANCHORS };

// Populated from src/housing/zip_screen/data/top_cities.csv, served alongside
// the screen endpoint. Falls back to the free-entry ZIP field when unavailable.
let HOUSING_OPT_TOP_CITIES = [];
let housingOptTopCitiesLoaded = false;

// Field help content registry (design §9.5), keyed by field id. Each value
// is DATA -- {title, meaning, connections, options, impact} -- not the
// rendered HTML. It is turned into HTML by calling the app's pageHelp()
// (dashboard.js:963) lazily, inside showHousingOptFieldHelp() below, at the
// moment a field is actually clicked.
//
// This has to be lazy rather than `pageHelp(...)` calls made right here at
// module-eval time: index.html loads dashboard_decomp_*.js modules (this one
// included -- see the file banner above) BEFORE dashboard.js, so pageHelp is
// not yet defined while this module's top level runs. Calling it here would
// throw a ReferenceError on every page load and take down the whole panel,
// not just housing help. Building a plain data object costs nothing at
// load time and defers the pageHelp() call to a point where dashboard.js has
// long since finished loading.
//
// Per-move fields (Move 1 and Move 2 share the same six real-content
// controls -- anchors, radius, min score, area type, max population,
// shortlist size, lot size) are generated once by housingOptMoveHelpEntries()
// below and registered under both `housingOptMove1<Field>` and
// `housingOptMove2<Field>` so the wording only has to be written once.
function housingOptMoveHelpEntries() {
  return {
    Anchors: {
      title: "Anchors",
      meaning:
        "The cities or ZIPs the search radiates from for this move. Between 2 and 5 are required.",
      connections:
        "Every anchor's radius search runs independently and the results are unioned and de-duplicated before the rest of the funnel (in_radius -> with_data -> ...) runs, so more anchors widen the candidate pool rather than narrowing it.",
      options:
        "Pick a handful of places the household would actually consider, spread out enough that their radii do not just overlap the same ZIPs. Toggle City/ZIP per anchor; City uses the built-in top-cities list, ZIP accepts any 5-digit code.",
      impact:
        "More anchors (up to 5) can only add candidates to the shortlist, never remove one; fewer anchors narrows the search area the optimizer can consider.",
    },
    Radius: {
      title: "Within (radius)",
      meaning: "How far from each anchor a candidate ZIP may be, in miles.",
      connections:
        "Applied per anchor at the in_radius funnel stage, the very first filter -- everything downstream (score, area type, population, price) only ever sees ZIPs that passed this test for at least one anchor.",
      options:
        "One of 5, 10, 25, or 50 miles. A tighter radius keeps the search close to the anchor; a wider one trades relevance for a larger candidate pool, which matters most when a small anchor area has few ZIPs with data.",
      impact:
        "Widening the radius can only add candidates (never removes ones already in range); narrowing it can empty the funnel if the anchor area is sparse.",
    },
    MinScore: {
      title: "Min score",
      meaning:
        "A floor on the ZIP's neighborhood stability score (0-100), which measures housing and economic stability -- not crime or safety.",
      connections:
        "Enforced at the above_score funnel stage, after in_radius and with_data. A ZIP below this floor is dropped regardless of how well it otherwise fits the dwelling spec.",
      options:
        "Raise it to bias the shortlist toward more established neighborhoods; lower it (default 60) to admit more ZIPs, especially in areas where high-quality data is thin.",
      impact:
        "Raising the floor shrinks the shortlist and can empty the funnel entirely in a sparsely-covered area; the shortlist preview's relaxation hint names this stage explicitly when it is the one that emptied the funnel.",
    },
    AreaType: {
      title: "Area type",
      meaning:
        "A single choice -- Any, Urban, Suburban, Exurban, or Rural -- compared against each ZIP's density-derived area type.",
      connections:
        "Enforced at the matching_area_type funnel stage. Any is the default and always passes every ZIP through this stage without hiding the stage from the funnel readout.",
      options:
        "Choose a specific type only when the household has a real preference for density; leave it at Any otherwise so the search is not narrowed on a dimension nobody cares about.",
      impact:
        "Choosing anything other than Any removes every ZIP whose density classification does not match, which can be severe in areas that skew heavily toward one type.",
    },
    MaxPopulation: {
      title: "Max population",
      meaning:
        "An optional ceiling on the ZIP's population (its place population, falling back to ZCTA population when that is absent). There is no minimum -- a small town is never excluded for being small.",
      connections:
        "Enforced at the under_population_cap funnel stage. Leaving it blank skips the stage entirely; it is the only funnel stage with no default value.",
      options:
        "Set it to keep the search away from large cities; leave it blank for no ceiling at all.",
      impact:
        "A ceiling can remove every candidate anchored on or near a dense city; the shortlist preview's relaxation hint calls this out by name (\"the population cap\") when it is the stage that emptied the funnel.",
    },
    ShortlistSize: {
      title: "Shortlist size",
      meaning:
        "How many screened ZIPs are promoted from this move's funnel into the optimizer, at the final `promoted` stage.",
      connections:
        "Everything upstream (radius, score, area type, population cap, price range, distinctness, family presence) narrows the candidate pool; this is the last step, capping how many of the survivors actually reach candidate generation.",
      options:
        "A larger shortlist (up to 5) lets the optimizer consider more locations per move at the cost of a larger search (and, with a second move, a larger cross-product); a smaller one runs faster but may drop a ZIP that would have scored well.",
      impact:
        "Increasing it only ever adds candidates for the optimizer to score; it never changes which ZIPs pass screening, only how many of the survivors are kept.",
    },
    LotSize: {
      title: "Lot size",
      meaning:
        "A lot-size band (Under 1/4 acre through Over 3 acres) used only to adjust the estimated purchase price for this move's dwelling spec, the same way bedrooms, bathrooms, property type, and square footage do.",
      connections:
        "This value never screens ZIPs. The ZIP snapshot the search runs against has no per-ZIP lot-area column, so there is nothing for the funnel to filter on -- the shortlist reflects estimated price and the other funnel stages only, not lot size.",
      options:
        "Set it to match the kind of home the household actually wants; treat it purely as a price-estimate input, not as a way to narrow which ZIPs show up.",
      impact:
        "Changing the band shifts the estimated price up or down (and therefore whether a ZIP passes the price-range filter), but never adds or removes a ZIP on lot size itself -- do not read the shortlist as having been screened on lot size.",
    },
  };
}

// The remaining per-move dwelling-spec fields (§6.3): they only shape the
// estimated price a move's price-range filter is tested against, so their
// help is intentionally brief rather than a full four-section essay each --
// the real content for this group is "this feeds the price estimate, not
// the ZIP screen" (Lot size gets its own richer entry above, since it is the
// one of these most likely to be misread as a ZIP filter).
function housingOptMoveDwellingHelpEntries() {
  const pricesEstimate =
    "Feeds estimate_housing_cost as a multiplicative factor on the estimated purchase price for this move, exactly like bedrooms, bathrooms, property type, and square footage do.";
  const pricesEstimateConnections =
    "The estimated price this produces is what Price min/Price max are tested against at the affordable funnel stage -- this field does not filter ZIPs by itself.";
  return {
    Bedrooms: {
      title: "Bedrooms",
      meaning: "The bedroom count used for this move's dwelling spec.",
      connections: pricesEstimateConnections,
      options: "Match the household's real space needs; higher counts raise the estimated price.",
      impact: pricesEstimate,
    },
    Bathrooms: {
      title: "Bathrooms",
      meaning: "The bathroom count used for this move's dwelling spec.",
      connections: pricesEstimateConnections,
      options: "Match the household's real space needs; higher counts raise the estimated price.",
      impact: pricesEstimate,
    },
    PropertyType: {
      title: "Property type",
      meaning: "The property type (single family, townhome, condo, duplex) used for this move's dwelling spec.",
      connections: pricesEstimateConnections,
      options: "Pick the type the household would actually buy or rent; it shapes the price estimate, not which ZIPs are offered.",
      impact: pricesEstimate,
    },
    SqftBand: {
      title: "Square footage",
      meaning: "The square-footage band used for this move's dwelling spec.",
      connections: pricesEstimateConnections,
      options: "Pick the band that matches the size of home the household wants; a wider band is a reasonable choice when the exact size is undecided.",
      impact: pricesEstimate,
    },
    BuiltWithin: {
      title: "Built within",
      meaning: "An optional age ceiling, in years, on the dwelling used for the price estimate. Leave it blank for no ceiling.",
      connections: pricesEstimateConnections,
      options: "Set it only when new-construction-or-newer is a real requirement; otherwise leave it blank so older, otherwise-suitable homes are not excluded from the price estimate's basis.",
      impact: pricesEstimate,
    },
    PriceMin: {
      title: "Price min",
      meaning: "The low end of the target purchase-price range for this move.",
      connections:
        "Unlike the other dwelling fields, this one DOES filter the funnel directly: it is the affordable stage, applied to each ZIP's estimated price (shaped by bedrooms/bathrooms/property type/sqft/lot size/built-within above). Validation requires min <= max when both are set.",
      options: "Leave both price fields blank to skip the price filter entirely; set them to the range the household can actually afford.",
      impact: "Narrowing the range removes ZIPs whose estimated price falls outside it; setting min above max blocks the Run button.",
    },
    PriceMax: {
      title: "Price max",
      meaning: "The high end of the target purchase-price range for this move.",
      connections:
        "Unlike the other dwelling fields, this one DOES filter the funnel directly: it is the affordable stage, applied to each ZIP's estimated price. Validation requires min <= max when both are set.",
      options: "Leave both price fields blank to skip the price filter entirely; set them to the range the household can actually afford.",
      impact: "Narrowing the range removes ZIPs whose estimated price falls outside it; setting max below min blocks the Run button.",
    },
    Action: {
      title: "Action",
      meaning: "Whether this move buys, rents, or lets Auto search both and let the objective decide.",
      connections:
        "Buy makes the move's acquisition-year rules interact with dual-ownership and sale-timing validation (rules 4 and 5); Rent never does, since renting never creates an ownership conflict.",
      options: "Use Auto to compare buying and renting on the objective; force Buy or Rent only when the household has already decided.",
      impact: "Forcing Rent when 'Never own two homes at once' is on can resolve an otherwise-blocked combination, since renting is always permitted alongside owning the previous home.",
    },
  };
}

const HOUSING_OPT_FIELD_HELP = (() => {
  const help = {};
  const moveEntries = { ...housingOptMoveHelpEntries(), ...housingOptMoveDwellingHelpEntries() };
  for (const moveIndex of [1, 2]) {
    for (const field of Object.keys(moveEntries)) {
      help[`housingOptMove${moveIndex}${field}`] = moveEntries[field];
    }
  }

  help._panel = {
    title: "Optimize next housing move",
    meaning:
      "Searches three independent decisions -- what happens to the current home, and where/what/when each of up to two moves is -- against the same deterministic engine and Monte Carlo runner as the rest of the plan, and ranks every resulting candidate by one objective.",
    connections:
      "Objective picks what is ranked: Ending net worth, Lifetime housing cost (minimized), or Monte Carlo success rate. Each searched move runs its own ZIP-radius screen -- a funnel of in_radius -> with_data -> above_score -> matching_area_type -> under_population_cap -> affordable -> distinct -> near_family -> promoted -- before the survivors are combined into candidates and scored.",
    options:
      "Start with Full grid search mode for a thorough run; switch to Narrowed only when the search space is too large to run in full. Use the per-move 'Preview shortlist' button to see which ZIPs a move's screen would return before running the whole optimization.",
    impact:
      "Phase 1 limitation: keeping the current home (Disposition = Keep) is scored as a pure cost center -- its carrying costs keep accruing and no rental income is modelled. A kept home can still win on net worth or lifetime cost by avoiding a sale's costs and capital-gains tax while it appreciates, but the comparison does not yet credit any rent it could earn. That comparison is Phase 2 (see the Disposition field's help for the same note in context).",
  };

  return help;
})();

// General (non-per-move) field help. Real-content fields get all four
// sections; year fields get a short "what this means" plus the §8
// validation rule that governs them (their real content is the rule, not a
// four-section essay about a single number).
Object.assign(HOUSING_OPT_FIELD_HELP, {
  housingOptObjective: {
    title: "Objective",
    meaning:
      "What the ranking maximizes -- or, for lifetime housing cost, minimizes -- across every candidate the search generates.",
    connections:
      "Applied only after every candidate has already been generated and simulated; it never changes which candidates exist, only their order in the results table.",
    options:
      "Ending net worth for the household's overall financial outcome, Lifetime housing cost to minimize what housing costs over the plan, or Monte Carlo success rate to optimize for plan resilience under simulated market returns.",
    impact:
      "Changing the objective can reorder the results table -- including which candidate is rank 1 and carries the 'Recommended' label -- without re-running the search.",
  },
  housingOptSearchMode: {
    title: "Search mode",
    meaning: "Controls how thoroughly the where/what/when grid is searched.",
    connections:
      "Full evaluates the entire grid of candidates exhaustively. Narrowed instead runs coordinate descent, one axis at a time, which is faster but is not guaranteed to find the same best candidate. Concurrent second-move mode (validation rule 8) is only available when this is Full.",
    options:
      "Use Full grid for a thorough search when the grid is small enough to run in reasonable time; switch to Narrowed only when Full is too slow for the number of anchors, moves, and windows involved.",
    impact:
      "Narrowed can miss the single best candidate that Full would have found, in exchange for materially faster runs; it also disables the 'Concurrent with move 1' option for move 2.",
  },
  housingOptMove2Strategy: {
    title: "Move-2 strategy",
    meaning:
      "How move 2's search space is built when a second move is enabled.",
    connections:
      "Anchored branches move 2's search from each of move 1's winning candidates. Cross-product instead searches every move-2 possibility against every move-1 possibility independently.",
    options:
      "Anchored on move-1 winners keeps the search tractable for most windows. Full cross-product is more thorough but can be rejected outright by the safety cap on large search windows.",
    impact:
      "Cross-product can surface a move-2 combination that Anchored would never reach (because it did not originate from a move-1 winner), at the cost of a much larger search that may hit the safety cap.",
  },
  housingOptNoDualOwnership: {
    title: "Never own two homes at once",
    meaning:
      "Constrains ownership only. Renting a residence while still owning the previous home is always permitted and is the intended way to bridge a timing gap -- this checkbox never blocks that.",
    connections:
      "When on, two combinations are rejected during candidate generation: keeping the current home while any move buys (no rental income exists to offset owning two homes in Phase 1), and buying a move before the current home's sale year. Concurrent second-move mode always keeps both homes, so this checkbox is disabled and ignored while concurrent is active.",
    options:
      "Leave it on for a household that genuinely cannot carry two mortgages/insurance/tax bills at once. Turn it off to let the optimizer consider overlapping ownership windows and let the objective decide whether the overlap is worth it.",
    impact:
      "Turning it off can surface candidates with a dual-ownership window (flagged with a note on that result row) that would otherwise never be generated; turning it on can eliminate the Keep + Buy combination entirely, which validation blocks the Run button for if it is the only combination available.",
  },
  housingOptPresenceEnabled: {
    title: "Family presence -- enable",
    meaning:
      "Turns on a hard filter that drops any candidate whose residence, in any year of the presence window, is farther than the radius from the family ZIP.",
    connections:
      "When enabled, this becomes the near_family funnel stage, the last screen before scoring -- it runs after price and distinctness. A concurrent second residence satisfies presence for the years it is held, the same as it does today.",
    options:
      "Enable it when staying near a specific place (family, school, a job) during specific years is a real requirement, not merely a preference; leave it off otherwise so it does not needlessly shrink the candidate pool.",
    impact:
      "Enabling it can empty the funnel if the radius is too tight for the anchors chosen -- the near_family stage count in the funnel readout, and each shortlist row's distance-to-family annotation, are there to help diagnose that.",
  },
  housingOptPresenceZip: {
    title: "Family ZIP",
    meaning: "The 5-digit ZIP that proximity is measured from when family presence is enabled.",
    connections:
      "Distance from every candidate's residence to this ZIP is computed with the same haversine calculation used for anchor-radius screening, and is enforced by the near_family funnel stage.",
    options:
      "Use the ZIP of the place the household actually needs to stay near -- a relative's home, a school, or similar -- not necessarily an anchor ZIP for either move.",
    impact:
      "Changing it re-centers which candidates satisfy the presence requirement; combined with a tight radius this can flip a previously-passing candidate to rejected or vice versa.",
  },
  housingOptPresenceRadius: {
    title: "Family presence -- within",
    meaning: "How far from the family ZIP the household may live during the presence window.",
    connections:
      "Enforced by the near_family funnel stage together with the family ZIP and the from/through years -- all four values act as one combined filter.",
    options:
      "One of 10, 25, 50, or 100 miles. Use the smallest radius that still reflects the real requirement; an unnecessarily tight radius is a common way to accidentally empty the funnel.",
    impact:
      "A tighter radius removes more candidates (and can empty the funnel entirely); a wider one is more forgiving but weakens the guarantee that the household stays near the family ZIP.",
  },
  housingOptDisposition: {
    title: "Disposition (current home)",
    meaning:
      "What happens to the current home: Sell, Keep, or Auto (search both and let the objective decide).",
    connections:
      "Sell searches an earliest/latest sale-year window. Keep sets no sale at all -- the home's carrying costs keep accruing for the rest of the plan. Important: Keep does NOT mean the home is rented out. No rental income is modelled for a kept home in this phase; it is scored purely as an ongoing cost. (Turning a kept home into an income property is a separate, not-yet-built feature -- Phase 2.) 'Never own two homes at once' also treats Keep + any Buy move as disallowed by default, since there is no rental income in Phase 1 to justify owning two homes.",
    options:
      "Choose Sell or Keep only when the household has already decided; choose Auto to let the search compare both and report whichever wins on the objective.",
    impact:
      "Keep avoids selling costs and capital-gains tax and lets the home keep appreciating, which can make it win on net worth or lifetime cost despite earning no rental income -- but it also disables the sale-year fields and, with 'Never own two homes at once' on, rules out buying while keeping.",
  },
  housingOptDownPaymentPct: {
    title: "Down payment %",
    meaning: "The share of the purchase price paid up front, as a percentage. Applies to every move that ends up buying in this search.",
    connections:
      "Feeds the buy-move cost basis the same way api.py's own default (20%) does when this field is left at its default -- the principal financed is purchase price x (1 - down payment %).",
    options: "Raise it to shrink the financed principal and the monthly P&I payment shown in the results table; lower it to keep more cash available for other goals.",
    impact: "A higher down payment lowers the monthly P&I payment and total interest paid, at the cost of more cash committed up front -- it does not change the purchase price itself.",
  },
  housingOptMortgageRatePct: {
    title: "Mortgage rate %",
    meaning: "The fixed annual mortgage interest rate used for every move that ends up buying. Pre-filled with the app's own flat default rate.",
    connections:
      "Feeds the same monthly P&I calculation as Down payment %, using a fixed 30-year term (there is no loan-term input anywhere in this app). Clearing this field entirely reverts to a per-location rate lookup instead of one flat rate for every candidate -- but today every location resolves to the same flat default rate (6.85%), so clearing the field currently has no effect versus leaving it at its pre-filled value. The per-location lookup exists for when location-specific rates are added.",
    options: "Leave the pre-filled default if unsure; set a specific rate for a rate lock already in hand; clearing the field has no effect today (see Connections) but is available for when per-location rates are added.",
    impact: "A higher rate raises the monthly P&I payment shown in results without changing the purchase price. Clearing the field currently has no effect on ranking, since every location resolves to the same flat default rate today.",
  },
  housingOptMove2Enabled: {
    title: "Consider a second move",
    meaning:
      "Adds a second acquisition to the search, with its own anchors, where/what/when rows, and mode (sequential or concurrent).",
    connections:
      "When on, move 2 is combined with move 1 either by the Anchored or Cross-product strategy (see Move-2 strategy) and, unless Concurrent is checked, must be able to happen after move 1 (validation rule 3).",
    options:
      "Leave it off for a plan with a single relocation; turn it on to search a two-move sequence, such as an initial downsize followed by a later move, or a concurrent second residence.",
    impact:
      "Enabling it roughly squares the size of the search (every move-1 candidate combined with every move-2 candidate under the chosen strategy), which is the main driver of how long a run takes.",
  },
  housingOptMove2Concurrent: {
    title: "Concurrent with move 1",
    meaning:
      "Keeps the move-1 home and adds move 2 as a second residence, rather than move 2 replacing move 1's home.",
    connections:
      "Only available when Search mode is Full grid (validation rule 8); selecting Narrowed search mode disables and unchecks it. While concurrent, 'Never own two homes at once' is disabled and ignored, because both homes are always kept together.",
    options:
      "Check it to model owning two homes at once by design -- for example a second residence used for family presence -- rather than a sequential relocation.",
    impact:
      "Turning it on removes the requirement that move 2 happen after move 1 and forces dual ownership to be permitted for the years both homes are held; turning it off (or switching to Narrowed search mode, which forces it off) restores the sequential move-2 timing rule.",
  },
  housingOptMove2AnchorCount: {
    title: "Anchor count",
    meaning:
      "How many of move 1's winning candidates the Anchored move-2 strategy branches its search from.",
    connections:
      "Only meaningful when Move-2 strategy is Anchored -- Cross-product searches every move-2 possibility against every move-1 possibility and ignores this value.",
    options:
      "A higher count considers more of move 1's near-best outcomes as starting points for move 2, at the cost of a larger search; the default of 5 is a reasonable middle ground.",
    impact:
      "Raising it can surface a move-2 combination that branches from a move-1 candidate outside the top few, which a lower count would have excluded before move 2 was ever searched.",
  },
  // Year fields: a short "what this means" plus the §8 validation rule that
  // governs them, rather than a full four-section essay about a single
  // number -- the rule IS the content that matters for a year field.
  housingOptEarliestSale: {
    title: "Earliest sale year",
    meaning: "The first year the current home may be sold, when the disposition searches or forces a sale.",
    connections:
      "Validation rule 1 (design §8): must not be after the latest sale year. Ignored entirely -- and disabled in the form -- when Disposition is Keep, since there is no sale to schedule.",
    options: "Pick a year within the plan's timeline that reflects the earliest the household would realistically list the home.",
    impact: "Raising it narrows the sale-year window the optimizer may choose from; setting it past the latest sale year blocks the Run button until fixed.",
  },
  housingOptLatestSale: {
    title: "Latest sale year",
    meaning: "The last year the current home may be sold, when the disposition searches or forces a sale.",
    connections:
      "Validation rule 1 (design §8): must not be before the earliest sale year. Also interacts with rule 5: with 'Never own two homes at once' on and move 1 buying, move 1's latest acquisition year must be at least this value.",
    options: "Pick a year within the plan's timeline that reflects the latest the household would still consider selling.",
    impact: "Lowering it narrows the sale-year window; setting it before the earliest sale year, or before move 1's forced-buy year under no-dual-ownership, blocks the Run button until fixed.",
  },
  housingOptMove1Earliest: {
    title: "Move 1 -- earliest year",
    meaning: "The first year move 1 may be acquired -- the closing year for a purchase, the lease start year for a rental.",
    connections: "Validation rule 2 (design §8): must not be after move 1's latest year.",
    options: "Pick a year within the plan's timeline that reflects the earliest this move could realistically happen.",
    impact: "Raising it narrows the acquisition-year window the optimizer may choose move 1 within; setting it past the latest year blocks the Run button until fixed.",
  },
  housingOptMove1Latest: {
    title: "Move 1 -- latest year",
    meaning: "The last year move 1 may be acquired.",
    connections:
      "Validation rule 2 (design §8): must not be before move 1's earliest year. Also interacts with rule 3 (move 2 must be able to happen after move 1, when sequential) and rule 5 (no-dual-ownership forced-buy timing).",
    options: "Pick a year within the plan's timeline that reflects the latest this move could realistically happen.",
    impact: "Lowering it narrows the window and can conflict with move 2's timing or the no-dual-ownership rule, both of which block the Run button until resolved.",
  },
  housingOptMove2Earliest: {
    title: "Move 2 -- earliest year",
    meaning: "The first year move 2 may be acquired, when a second move is enabled.",
    connections: "Validation rule applied alongside move 1's: move 2's earliest year must not be after move 2's latest year.",
    options: "Pick a year within the plan's timeline that reflects the earliest move 2 could realistically happen.",
    impact: "Raising it narrows move 2's acquisition-year window; combined with a low latest year it can also violate rule 3 (move 2 must be able to happen after move 1) unless Concurrent is checked.",
  },
  housingOptMove2Latest: {
    title: "Move 2 -- latest year",
    meaning: "The last year move 2 may be acquired, when a second move is enabled.",
    connections:
      "Validation rule 3 (design §8): in sequential mode, must be after move 1's earliest year -- 'Move 2 must be able to happen after move 1.' Not enforced when Concurrent is checked.",
    options: "Pick a year within the plan's timeline that reflects the latest move 2 could realistically happen.",
    impact: "Lowering it too close to (or before) move 1's earliest year blocks the Run button with the rule-3 message, unless Concurrent mode is on.",
  },
  housingOptPresenceFrom: {
    title: "Family presence -- from year",
    meaning: "The first year of the family-presence window, when family presence is enabled.",
    connections: "Validation rule 7 (design §8): must not be after the through year, alongside the 5-digit-ZIP requirement.",
    options: "Pick the year the presence requirement should start applying.",
    impact: "Raising it narrows the window of years the near_family filter is enforced over; setting it past the through year blocks the Run button until fixed.",
  },
  housingOptPresenceThrough: {
    title: "Family presence -- through year",
    meaning: "The last year of the family-presence window, when family presence is enabled.",
    connections: "Validation rule 7 (design §8): must not be before the from year.",
    options: "Pick the year the presence requirement should stop applying.",
    impact: "Lowering it narrows the window of years the near_family filter is enforced over; setting it before the from year blocks the Run button until fixed.",
  },
});

// ---------------------------------------------------------------------------
// Layout primitives
// ---------------------------------------------------------------------------

// `key` is both the control's id and its help-registry key, so the DOM, the
// help registry and the persistence snapshot (Task 15) all agree on one name.
function housingOptField(key, labelText, controlHtml, hint) {
  return `<div class="housing-opt-field" onclick="showHousingOptFieldHelp('${key}')"><label for="${key}">${esc(labelText)}<sup class="field-info-i" tabindex="0" title="${esc(hint || labelText)}" aria-label="More info: ${esc(hint || labelText)}">i</sup></label>${controlHtml}</div>`;
}

function housingOptRow(title, fieldsHtml) {
  return `<div class="housing-opt-row"><div class="housing-opt-row-label">${esc(title)}</div><div class="housing-opt-row-fields">${fieldsHtml}</div></div>`;
}

function housingOptSelect(id, options, extraAttrs) {
  const opts = options
    .map(
      (o) =>
        `<option value="${esc(o.value)}"${o.selected ? " selected" : ""}>${esc(o.label)}</option>`,
    )
    .join("");
  return `<select id="${id}"${extraAttrs ? " " + extraAttrs : ""}>${opts}</select>`;
}

// ---------------------------------------------------------------------------
// Shared option sets (§6.2, §6.3, §7.1)
// ---------------------------------------------------------------------------
//
// The concrete value/label pairs live in HOUSING_DWELLING_OPTIONS
// (dashboard_shared_helpers.js), read here as a bare global via that file's
// window bridge, so this panel and the spending screen's next-housing-step
// fields (dashboard_decomp_housing_scenarios.js) render from one source
// (Task 16, design doc §10/§14). Only this panel's own defaults and its
// "any" search wildcard -- meaningless on the spending screen, which records
// one concrete dwelling -- are added locally.

function _withSelected(opts, selectedValue) {
  return opts.map((o) =>
    o.value === selectedValue ? { ...o, selected: true } : { ...o },
  );
}

const HOUSING_OPT_AREA_TYPES = [
  { value: "any", label: "Any", selected: true },
  ...HOUSING_DWELLING_OPTIONS.areaTypes,
];

const HOUSING_OPT_BEDROOMS = _withSelected(
  HOUSING_DWELLING_OPTIONS.bedrooms,
  "3",
);

const HOUSING_OPT_BATHROOMS = _withSelected(
  HOUSING_DWELLING_OPTIONS.bathrooms,
  "2",
);

const HOUSING_OPT_PROPERTY_TYPES = _withSelected(
  HOUSING_DWELLING_OPTIONS.propertyTypes,
  "single_family",
);

const HOUSING_OPT_SQFT_BANDS = _withSelected(
  HOUSING_DWELLING_OPTIONS.sqftBands,
  "1800_2500",
);

const HOUSING_OPT_LOT_SIZE_BANDS = _withSelected(
  HOUSING_DWELLING_OPTIONS.lotSizeBands,
  "quarter_half",
);

const HOUSING_OPT_MOVE_ACTIONS = [
  { value: "auto", label: "Auto (search buy & rent)", selected: true },
  { value: "buy", label: "Buy only" },
  { value: "rent", label: "Rent only" },
];

const HOUSING_OPT_MOVE_RADII = [
  { value: "5", label: "Within 5 miles" },
  { value: "10", label: "Within 10 miles" },
  { value: "25", label: "Within 25 miles", selected: true },
  { value: "50", label: "Within 50 miles" },
];

const HOUSING_OPT_PRESENCE_RADII = [
  { value: "10", label: "Within 10 miles" },
  { value: "25", label: "Within 25 miles", selected: true },
  { value: "50", label: "Within 50 miles" },
  { value: "100", label: "Within 100 miles" },
];

const HOUSING_OPT_SHORTLIST_SIZES = [
  { value: "2", label: "2" },
  { value: "3", label: "3" },
  { value: "4", label: "4", selected: true },
  { value: "5", label: "5" },
];

const HOUSING_OPT_OBJECTIVE_LABELS = {
  net_worth: "Ending net worth",
  lifetime_cost: "Lifetime housing cost",
  mc_success_rate: "Monte Carlo success rate",
};

// ---------------------------------------------------------------------------
// Anchors (§9.3)
// ---------------------------------------------------------------------------

function housingOptAnchorCityOptionsHtml() {
  return (
    `<option value="">Select a city</option>` +
    HOUSING_OPT_TOP_CITIES.map(
      (c) =>
        `<option value="${esc(c.anchor_zip)}">${esc(c.city)}, ${esc(c.state_abbrev)}</option>`,
    ).join("")
  );
}

// One compact anchor entry: a City/ZIP mode toggle plus either the top_cities
// select or a 5-character ZIP input. The mode select carries the field key so
// housingOptField's `for` attribute points at a real control.
export function housingOptAnchorEntryHtml(moveIndex, i) {
  const key = `housingOptMove${moveIndex}Anchor${i}`;
  const cityId = `housingOptMove${moveIndex}AnchorCity${i}`;
  const zipId = `housingOptMove${moveIndex}AnchorZip${i}`;
  const mode = housingOptSelect(
    key,
    [
      { value: "city", label: "City", selected: true },
      { value: "zip", label: "ZIP" },
    ],
    `onchange="toggleHousingOptAnchorMode(${moveIndex}, ${i}); debouncedRefreshHousingOptValidation()"`,
  );
  const city = `<select id="${cityId}" class="housing-opt-anchor-city" onchange="debouncedRefreshHousingOptValidation()">${housingOptAnchorCityOptionsHtml()}</select>`;
  const zip = `<input type="text" id="${zipId}" class="zip housing-opt-anchor-zip" maxlength="5" inputmode="numeric" placeholder="60521" hidden oninput="debouncedRefreshHousingOptValidation()">`;
  const remove =
    i >= HOUSING_OPT_MIN_ANCHORS
      ? `<button class="btn small housing-opt-anchor-remove" type="button" onclick="removeHousingOptAnchor(${moveIndex}, ${i})" aria-label="Remove anchor ${i + 1}">&times;</button>`
      : "";
  const control = `<div class="housing-opt-anchor-controls">${mode}${city}${zip}${remove}</div>`;
  return housingOptField(
    key,
    `Anchor ${i + 1}`,
    control,
    "A city or ZIP the search radiates from. Each searched move takes 2-5 anchors.",
  );
}

export function renderHousingOptAnchorsHtml(moveIndex) {
  const n = housingOptAnchorCounts[moveIndex] || HOUSING_OPT_MIN_ANCHORS;
  const entries = Array.from({ length: n }, (_, i) =>
    housingOptAnchorEntryHtml(moveIndex, i),
  ).join("");
  return `<div class="housing-opt-anchors" id="housingOptMove${moveIndex}Anchors">${entries}</div><div class="housing-opt-anchor-actions"><button class="btn small" type="button" id="housingOptMove${moveIndex}AddAnchor" onclick="addHousingOptAnchor(${moveIndex})">+ Add anchor</button></div>`;
}

export function toggleHousingOptAnchorMode(moveIndex, i) {
  const mode = String(
    document.getElementById(`housingOptMove${moveIndex}Anchor${i}`)?.value || "city",
  );
  const city = document.getElementById(`housingOptMove${moveIndex}AnchorCity${i}`);
  const zip = document.getElementById(`housingOptMove${moveIndex}AnchorZip${i}`);
  if (city) city.hidden = mode !== "city";
  if (zip) zip.hidden = mode !== "zip";
}

export function addHousingOptAnchor(moveIndex) {
  const n = housingOptAnchorCounts[moveIndex] || HOUSING_OPT_MIN_ANCHORS;
  if (n >= HOUSING_OPT_MAX_ANCHORS) return;
  housingOptAnchorCounts[moveIndex] = n + 1;
  redrawHousingOptAnchors(moveIndex, n);
  // +/- Add anchor is a click, not an input/change event, so it does not
  // reach the panel's delegated oninput/onchange listener (§9.6) on its own.
  debouncedSaveHousingOptInputs();
}

export function removeHousingOptAnchor(moveIndex, i) {
  const n = housingOptAnchorCounts[moveIndex] || HOUSING_OPT_MIN_ANCHORS;
  if (n <= HOUSING_OPT_MIN_ANCHORS || i < HOUSING_OPT_MIN_ANCHORS) return;
  housingOptAnchorCounts[moveIndex] = n - 1;
  redrawHousingOptAnchors(moveIndex, n);
  debouncedSaveHousingOptInputs();
}

// Snapshots each existing anchor's mode/city/zip before a redraw rebuilds the
// container's innerHTML from scratch -- innerHTML replacement discards the
// live <select>/<input> elements (and whatever the user had chosen or typed
// into them), so add/remove would otherwise reset every prior anchor back to
// its just-rendered default instead of only appending or dropping the one
// anchor that actually changed.
function housingOptAnchorSnapshot(moveIndex, n) {
  const snap = [];
  for (let i = 0; i < n; i++) {
    snap.push({
      mode: document.getElementById(`housingOptMove${moveIndex}Anchor${i}`)?.value,
      city: document.getElementById(`housingOptMove${moveIndex}AnchorCity${i}`)?.value,
      zip: document.getElementById(`housingOptMove${moveIndex}AnchorZip${i}`)?.value,
    });
  }
  return snap;
}

function housingOptAnchorRestore(moveIndex, snap) {
  snap.forEach((s, i) => {
    if (!s) return;
    const modeEl = document.getElementById(`housingOptMove${moveIndex}Anchor${i}`);
    if (modeEl && s.mode != null) modeEl.value = s.mode;
    const cityEl = document.getElementById(`housingOptMove${moveIndex}AnchorCity${i}`);
    if (cityEl && s.city != null) cityEl.value = s.city;
    const zipEl = document.getElementById(`housingOptMove${moveIndex}AnchorZip${i}`);
    if (zipEl && s.zip != null) zipEl.value = s.zip;
    toggleHousingOptAnchorMode(moveIndex, i);
  });
}

function redrawHousingOptAnchors(moveIndex, prevN) {
  const container = document.getElementById(`housingOptMove${moveIndex}Anchors`);
  if (!container) return;
  const n = housingOptAnchorCounts[moveIndex] || HOUSING_OPT_MIN_ANCHORS;
  const snap = housingOptAnchorSnapshot(moveIndex, Math.min(n, prevN ?? n));
  container.innerHTML = Array.from({ length: n }, (_, i) =>
    housingOptAnchorEntryHtml(moveIndex, i),
  ).join("");
  housingOptAnchorRestore(moveIndex, snap);
}

export async function loadHousingOptTopCities() {
  if (housingOptTopCitiesLoaded) return;
  try {
    const payload = await api("/api/housing/top-cities", { method: "GET" });
    if (payload && payload.success && Array.isArray(payload.cities)) {
      HOUSING_OPT_TOP_CITIES = payload.cities;
      housingOptTopCitiesLoaded = true;
      const selects = document.querySelectorAll?.(".housing-opt-anchor-city") || [];
      selects.forEach((select) => {
        const current = select.value;
        select.innerHTML = housingOptAnchorCityOptionsHtml();
        select.value = current;
      });
    }
  } catch (e) {
    // Non-fatal: the free-entry ZIP mode remains usable either way.
  }
}

// ---------------------------------------------------------------------------
// Persistence (§9.6)
//
// Follows the scenarioWriteSets pattern (dashboard_decomp_housing_scenarios.js
// SCENARIO_SET_STORAGE_KEY): one JSON object under one key, every access
// wrapped in try/catch, silently ignored when storage is blocked, cleared or
// unparseable -- the form simply starts at its defaults rather than surfacing
// an error the user can do nothing about.
//
// Stored: every panel input's value, the anchor lists (as a count -- see
// HOUSING_OPT_PERSIST_META_KEYS), the move-2 enabled flag and the <details>
// open state. Deliberately NOT stored: anything derived from a run --
// results, candidates, shortlists. saveHousingOptInputs() only reads actual
// form controls (input/select/textarea) and explicitly skips the results
// container and everything inside it, so a restored form always starts with
// an empty result area and a stale recommendation can never be mistaken for
// a fresh one. Unknown keys in a stored payload are simply never matched by
// housingOptHydratePanelHtml() below, and missing keys leave the
// already-rendered default in place, so the shape can grow without a
// migration.
// ---------------------------------------------------------------------------

export function loadHousingOptInputs() {
  try {
    return JSON.parse(localStorage.getItem(HOUSING_OPT_STORAGE_KEY) || "{}") || {};
  } catch (e) {
    // Blocked, cleared, or corrupt storage is not an error worth surfacing:
    // the form simply starts at its defaults.
    return {};
  }
}

export function saveHousingOptInputs() {
  try {
    const root = document.getElementById(HOUSING_OPT_PANEL_ID);
    if (!root || typeof root.querySelectorAll !== "function") return;
    const resultsRoot = document.getElementById(HOUSING_OPT_RESULTS_ID);
    const data = {};
    root.querySelectorAll("[id]").forEach((el) => {
      if (!el || !el.id) return;
      if (el.id === HOUSING_OPT_RESULTS_ID) return;
      if (
        resultsRoot &&
        typeof resultsRoot.contains === "function" &&
        resultsRoot.contains(el)
      ) {
        // Never persist anything living inside the results container -- it
        // is entirely derived from a run.
        return;
      }
      const tag = String(el.tagName || "").toUpperCase();
      if (tag === "INPUT") {
        data[el.id] =
          String(el.type || "").toLowerCase() === "checkbox" ? !!el.checked : el.value;
      } else if (tag === "SELECT" || tag === "TEXTAREA") {
        data[el.id] = el.value;
      }
    });
    data.__move1AnchorCount = housingOptAnchorCounts[1] || HOUSING_OPT_MIN_ANCHORS;
    data.__move2AnchorCount = housingOptAnchorCounts[2] || HOUSING_OPT_MIN_ANCHORS;
    data.__detailsOpen = !!root.open;
    localStorage.setItem(HOUSING_OPT_STORAGE_KEY, JSON.stringify(data));
  } catch (e) {
    // Blocked or unavailable storage is not worth surfacing -- the form
    // simply will not be remembered for next time.
  }
}

let housingOptSaveTimer = null;

// Wired to a single delegated oninput/onchange/ontoggle on the panel's
// <details> wrapper (they all bubble to it except ontoggle, which fires on
// the element itself) rather than to each of the ~30 individual fields, so
// adding a field never means remembering to also wire its persistence.
export function debouncedSaveHousingOptInputs() {
  if (housingOptSaveTimer) clearTimeout(housingOptSaveTimer);
  housingOptSaveTimer = setTimeout(saveHousingOptInputs, 400);
}

// ---- string-level hydration -------------------------------------------
//
// renderHousingOptimizePanelHtml() only ever returns an HTML *string* for a
// caller to assign into innerHTML -- by the time it runs there is no
// element tree yet for a restored value to be applied to via
// document.getElementById(...).value = ... . These helpers instead patch
// the generated markup itself before it is returned, which also means
// restoration works identically however the caller chooses to mount it.

// Finds the [start, end) range of the single element carrying id="id" --
// its whole `<select ...>...</select>` block if it is a select (so option
// `selected` flags can be rewritten), otherwise just its opening tag.
function housingOptFindTagRange(html, id) {
  const idAttr = `id="${id}"`;
  const idx = html.indexOf(idAttr);
  if (idx === -1) return null;
  const tagStart = html.lastIndexOf("<", idx);
  if (tagStart === -1) return null;
  const tagNameMatch = /^<(\w+)/.exec(html.slice(tagStart));
  const tagName = tagNameMatch ? tagNameMatch[1].toLowerCase() : "";
  const openTagEnd = html.indexOf(">", idx) + 1;
  if (openTagEnd <= 0) return null;
  if (tagName === "select") {
    const closeIdx = html.indexOf("</select>", openTagEnd);
    if (closeIdx !== -1) return [tagStart, closeIdx + "</select>".length];
  }
  return [tagStart, openTagEnd];
}

function housingOptHydrateOne(html, id, transform) {
  const range = housingOptFindTagRange(html, id);
  if (!range) return html; // unknown/removed id -- leave the default alone
  const [start, end] = range;
  return html.slice(0, start) + transform(html.slice(start, end)) + html.slice(end);
}

function housingOptSetAttr(block, attr, value) {
  const openEnd = block.indexOf(">");
  const openTag = openEnd === -1 ? block : block.slice(0, openEnd + 1);
  const rest = openEnd === -1 ? "" : block.slice(openEnd + 1);
  const re = new RegExp(` ${attr}="[^"]*"`);
  const newOpenTag = re.test(openTag)
    ? openTag.replace(re, ` ${attr}="${value}"`)
    : openTag.replace(/^<(\w+)/, `<$1 ${attr}="${value}"`);
  return newOpenTag + rest;
}

function housingOptSetBooleanAttr(block, attr, on) {
  const openEnd = block.indexOf(">");
  const openTag = openEnd === -1 ? block : block.slice(0, openEnd + 1);
  const rest = openEnd === -1 ? "" : block.slice(openEnd + 1);
  const has = new RegExp(`[ "]${attr}(=|>| |$)`).test(openTag);
  let newOpenTag = openTag;
  if (on && !has) newOpenTag = openTag.replace(/^<(\w+)/, `<$1 ${attr}`);
  if (!on && has) newOpenTag = openTag.replace(new RegExp(` ${attr}(="[^"]*")?`), "");
  return newOpenTag + rest;
}

function housingOptHydrateSelectBlock(block, rawValue) {
  let out = block.replace(/ selected(?=[ >])/g, "");
  const marker = `value="${rawValue}"`;
  const idx = out.indexOf(marker);
  if (idx === -1) return out; // stored value no longer a valid option: keep default
  const tagEnd = out.indexOf(">", idx);
  if (tagEnd === -1) return out;
  return out.slice(0, tagEnd) + " selected" + out.slice(tagEnd);
}

// Applies every key of a loadHousingOptInputs() payload onto freshly
// generated panel markup. Keys that do not correspond to any id in the
// markup (removed fields, or garbage from a corrupt/foreign payload) are
// simply no-ops -- see housingOptHydrateOne -- which is what lets the
// stored shape grow or shrink without a migration.
function housingOptHydratePanelHtml(html, stored) {
  let out = html;
  for (const [id, raw] of Object.entries(stored || {})) {
    if (HOUSING_OPT_PERSIST_META_KEYS.has(id)) continue;
    out = housingOptHydrateOne(out, id, (block) => {
      if (typeof raw === "boolean") return housingOptSetBooleanAttr(block, "checked", raw);
      if (/^<select/i.test(block)) return housingOptHydrateSelectBlock(block, raw);
      return housingOptSetAttr(block, "value", esc(String(raw)));
    });
    // An anchor's City/ZIP mode select has no `checked`/`selected` bearing on
    // which of its two sibling controls is visible -- that is a separate
    // `hidden` attribute toggleHousingOptAnchorMode() otherwise only sets at
    // click time. Restore it here too, or a restored "zip" mode would show
    // the city dropdown and hide the very zip field that holds the value.
    const anchorMode = /^housingOptMove(\d)Anchor(\d+)$/.exec(id);
    if (anchorMode && typeof raw !== "boolean") {
      const mode = String(raw);
      const cityId = `housingOptMove${anchorMode[1]}AnchorCity${anchorMode[2]}`;
      const zipId = `housingOptMove${anchorMode[1]}AnchorZip${anchorMode[2]}`;
      out = housingOptHydrateOne(out, cityId, (block) =>
        housingOptSetBooleanAttr(block, "hidden", mode !== "city"),
      );
      out = housingOptHydrateOne(out, zipId, (block) =>
        housingOptSetBooleanAttr(block, "hidden", mode !== "zip"),
      );
    }
  }
  if (stored && "__detailsOpen" in stored) {
    out = housingOptHydrateOne(out, HOUSING_OPT_PANEL_ID, (block) =>
      housingOptSetBooleanAttr(block, "open", !!stored.__detailsOpen),
    );
  }
  return out;
}

// ---------------------------------------------------------------------------
// Help (§9.5) -- Task 14 supplies the content.
// ---------------------------------------------------------------------------

export function showHousingOptFieldHelp(key) {
  const entry = HOUSING_OPT_FIELD_HELP[key] || HOUSING_OPT_FIELD_HELP._panel;
  if (!entry) return;
  ensureHelpPanelVisible();
  const panel = document.getElementById("helpPanel");
  // pageHelp() is defined in dashboard.js, which loads AFTER this module (see
  // the file banner above) -- it is only called here, lazily, at click time,
  // never at module-eval time, so its absence during page load never breaks
  // this module's own evaluation.
  if (panel) {
    panel.innerHTML = pageHelp(
      entry.title,
      entry.meaning,
      entry.connections,
      entry.options,
      entry.impact,
    );
  }
}

// ---------------------------------------------------------------------------
// Toggles
// ---------------------------------------------------------------------------

export function toggleHousingOptMove2Fields() {
  const el = document.getElementById("housingOptMove2Fields");
  const enabled = !!document.getElementById("housingOptMove2Enabled")?.checked;
  if (el) el.hidden = !enabled;
  if (!enabled) {
    // Move 2 is being disabled -- concurrent mode (and anything it implies)
    // is moot, so reset it rather than silently posting a stale
    // concurrent=true with no move-2 window.
    const concurrentCb = document.getElementById("housingOptMove2Concurrent");
    if (concurrentCb) concurrentCb.checked = false;
    const narrowedNote = document.getElementById("housingOptMove2ConcurrentNarrowedNote");
    if (narrowedNote) narrowedNote.hidden = true;
    toggleHousingOptNoDualOwnershipAvailability();
  }
}

export function toggleHousingOptMove2ConcurrentAvailability() {
  const searchMode = String(
    document.getElementById("housingOptSearchMode")?.value || "full",
  );
  const concurrentCb = document.getElementById("housingOptMove2Concurrent");
  const note = document.getElementById("housingOptMove2ConcurrentNarrowedNote");
  const narrowed = searchMode === "narrowed";
  if (concurrentCb) {
    if (narrowed) concurrentCb.checked = false;
    concurrentCb.disabled = narrowed;
  }
  if (note) note.hidden = !narrowed;
  toggleHousingOptNoDualOwnershipAvailability();
}

// no_dual_ownership does not apply to concurrent mode: concurrent candidates
// always keep both homes, so the checkbox's value is ignored by the backend.
// Disable it and explain why whenever concurrent mode is active, without
// touching its checked state.
export function toggleHousingOptNoDualOwnershipAvailability() {
  const concurrent = !!document.getElementById("housingOptMove2Concurrent")?.checked;
  const noDualCb = document.getElementById("housingOptNoDualOwnership");
  const note = document.getElementById("housingOptNoDualOwnershipConcurrentNote");
  if (noDualCb) noDualCb.disabled = concurrent;
  if (note) note.hidden = !concurrent;
}

// Keeping the current home means there is no sale to schedule, so the sale
// window is disabled and dimmed rather than silently ignored (§9.2).
export function toggleHousingOptDispositionFields() {
  const keep =
    String(document.getElementById("housingOptDisposition")?.value || "auto") === "keep";
  ["housingOptEarliestSale", "housingOptLatestSale"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.disabled = keep;
  });
  const note = document.getElementById("housingOptKeepNote");
  if (note) note.hidden = !keep;
}

// ---------------------------------------------------------------------------
// Panel markup (§9.2)
// ---------------------------------------------------------------------------

function housingOptMoveWhereRowHtml(n) {
  const p = `housingOptMove${n}`;
  return housingOptRow(
    `Move ${n} — where`,
    housingOptField(
      `${p}Anchors`,
      "Anchors (2-5)",
      renderHousingOptAnchorsHtml(n),
      "The search screens ZIPs around each anchor and unions the results before dedup.",
    ) +
      housingOptField(
        `${p}AreaType`,
        "Area type",
        housingOptSelect(`${p}AreaType`, HOUSING_OPT_AREA_TYPES, 'onchange="debouncedRefreshHousingOptValidation()"'),
        "Compared against the ZIP's density-derived area type. Any skips the filter.",
      ) +
      housingOptField(
        `${p}Radius`,
        "Within",
        housingOptSelect(`${p}Radius`, HOUSING_OPT_MOVE_RADII, 'onchange="debouncedRefreshHousingOptValidation()"'),
        "How far from each anchor a candidate ZIP may be.",
      ) +
      housingOptField(
        `${p}MinScore`,
        "Min score",
        `<input type="number" id="${p}MinScore" class="count" value="60" min="0" max="100">`,
        "Neighborhood stability score floor. Measures housing and economic stability, not crime or safety.",
      ) +
      housingOptField(
        `${p}MaxPopulation`,
        "Max population",
        `<input type="number" id="${p}MaxPopulation" class="money" min="0" placeholder="No cap">`,
        "Optional ceiling on the ZIP's population. There is no minimum -- a small town is never excluded for being small.",
      ) +
      housingOptField(
        `${p}ShortlistSize`,
        "Shortlist size",
        housingOptSelect(`${p}ShortlistSize`, HOUSING_OPT_SHORTLIST_SIZES),
        "How many screened ZIPs are promoted into the optimizer for this move.",
      ),
  );
}

function housingOptMoveWhatRowHtml(n) {
  const p = `housingOptMove${n}`;
  return housingOptRow(
    `Move ${n} — what`,
    housingOptField(
      `${p}Bedrooms`,
      "Bedrooms",
      housingOptSelect(`${p}Bedrooms`, HOUSING_OPT_BEDROOMS),
      "Shapes the estimated price the target price range is tested against.",
    ) +
      housingOptField(
        `${p}Bathrooms`,
        "Bathrooms",
        housingOptSelect(`${p}Bathrooms`, HOUSING_OPT_BATHROOMS),
        "Shapes the estimated price the target price range is tested against.",
      ) +
      housingOptField(
        `${p}PropertyType`,
        "Property type",
        housingOptSelect(`${p}PropertyType`, HOUSING_OPT_PROPERTY_TYPES),
        "Shapes the estimated price the target price range is tested against.",
      ) +
      housingOptField(
        `${p}SqftBand`,
        "Square footage",
        housingOptSelect(`${p}SqftBand`, HOUSING_OPT_SQFT_BANDS),
        "Shapes the estimated price the target price range is tested against.",
      ) +
      housingOptField(
        `${p}LotSize`,
        "Lot size",
        housingOptSelect(`${p}LotSize`, HOUSING_OPT_LOT_SIZE_BANDS),
        "Adjusts the estimated price only. ZIPs are not screened on lot size -- the snapshot has no lot-area column.",
      ) +
      housingOptField(
        `${p}BuiltWithin`,
        "Built within",
        `<input type="number" id="${p}BuiltWithin" class="count" min="0" placeholder="N yrs">`,
        "Optional age ceiling, in years, on the dwelling used for the price estimate.",
      ) +
      housingOptField(
        `${p}PriceMin`,
        "Price min",
        `<input type="number" id="${p}PriceMin" class="money" min="0" placeholder="e.g. 400000" oninput="debouncedRefreshHousingOptValidation()">`,
        "The only dwelling input that filters the funnel: ZIPs whose estimated price falls outside the range are dropped.",
      ) +
      housingOptField(
        `${p}PriceMax`,
        "Price max",
        `<input type="number" id="${p}PriceMax" class="money" min="0" placeholder="e.g. 700000" oninput="debouncedRefreshHousingOptValidation()">`,
        "The only dwelling input that filters the funnel: ZIPs whose estimated price falls outside the range are dropped.",
      ) +
      `<div class="housing-opt-field-actions"><button class="btn small" type="button" id="${p}Preview" onclick="previewHousingZipShortlist(${n})">Preview shortlist</button></div><div class="housing-opt-shortlist" id="${p}Shortlist"></div>`,
  );
}

function housingOptMoveWhenRowHtml(n) {
  const p = `housingOptMove${n}`;
  return housingOptRow(
    `Move ${n} — when`,
    housingOptField(
      `${p}Earliest`,
      "Earliest year",
      `<input type="number" id="${p}Earliest" class="year" oninput="debouncedRefreshHousingOptValidation()">`,
      "The first year this move may be acquired -- the closing year for a purchase, the lease start year for a rental.",
    ) +
      housingOptField(
        `${p}Latest`,
        "Latest year",
        `<input type="number" id="${p}Latest" class="year" oninput="debouncedRefreshHousingOptValidation()">`,
        "The last year this move may be acquired. Must not be earlier than the earliest year.",
      ) +
      housingOptField(
        `${p}Action`,
        "Action",
        housingOptSelect(`${p}Action`, HOUSING_OPT_MOVE_ACTIONS, 'onchange="debouncedRefreshHousingOptValidation()"'),
        "Auto searches both buying and renting and lets the objective decide.",
      ),
  );
}

export function renderHousingOptimizePanelHtml() {
  // Loaded first so the per-move anchor *count* (which has no backing DOM
  // element -- see HOUSING_OPT_PERSIST_META_KEYS above) can be applied to
  // housingOptAnchorCounts before the anchor rows below are built from it.
  // Everything else in the stored payload is applied afterwards, as a
  // string-level hydration pass over the fully-built markup (see
  // housingOptHydratePanelHtml).
  const housingOptStored = loadHousingOptInputs();
  const clampAnchorCount = (n) => {
    const v = Math.round(Number(n));
    if (!Number.isFinite(v)) return null;
    return Math.min(HOUSING_OPT_MAX_ANCHORS, Math.max(HOUSING_OPT_MIN_ANCHORS, v));
  };
  const storedMove1Anchors = clampAnchorCount(housingOptStored.__move1AnchorCount);
  if (storedMove1Anchors) housingOptAnchorCounts[1] = storedMove1Anchors;
  const storedMove2Anchors = clampAnchorCount(housingOptStored.__move2AnchorCount);
  if (storedMove2Anchors) housingOptAnchorCounts[2] = storedMove2Anchors;

  const objectiveRow = housingOptRow(
    "Objective & constraints",
    housingOptField(
      "housingOptObjective",
      "Objective",
      housingOptSelect("housingOptObjective", [
        { value: "net_worth", label: "Ending net worth", selected: true },
        { value: "lifetime_cost", label: "Lifetime housing cost" },
        { value: "mc_success_rate", label: "Monte Carlo success rate" },
      ]),
      "What the ranking maximizes (or minimizes, for lifetime cost).",
    ) +
      housingOptField(
        "housingOptSearchMode",
        "Search mode",
        housingOptSelect(
          "housingOptSearchMode",
          [
            { value: "full", label: "Full grid (thorough, slower)", selected: true },
            {
              value: "narrowed",
              label: "Narrowed (faster, may miss the best candidate)",
            },
          ],
          'onchange="toggleHousingOptMove2ConcurrentAvailability(); debouncedRefreshHousingOptValidation()"',
        ),
        "Full evaluates the whole grid; narrowed runs coordinate descent per axis.",
      ) +
      housingOptField(
        "housingOptMove2Strategy",
        "Move-2 strategy",
        housingOptSelect("housingOptMove2Strategy", [
          { value: "anchored", label: "Anchored on move-1 winners", selected: true },
          { value: "cross_product", label: "Full cross-product" },
        ]),
        "Cross-product is thorough but can be rejected for large windows by the safety cap.",
      ) +
      housingOptField(
        "housingOptNoDualOwnership",
        "Never own two homes at once",
        `<input type="checkbox" id="housingOptNoDualOwnership" checked onchange="debouncedRefreshHousingOptValidation()"><span class="housing-opt-note small" id="housingOptNoDualOwnershipConcurrentNote" hidden>Not applicable in concurrent mode -- both homes are always kept.</span>`,
        "Constrains ownership only. Renting a residence while still owning the previous home is always permitted.",
      ),
  );

  const presenceRow = housingOptRow(
    "Family presence",
    housingOptField(
      "housingOptPresenceEnabled",
      "Enable",
      `<input type="checkbox" id="housingOptPresenceEnabled" onchange="debouncedRefreshHousingOptValidation()">`,
      "When on, a candidate is dropped if the household lives farther than the radius from the family ZIP in any year of the window.",
    ) +
      housingOptField(
        "housingOptPresenceZip",
        "Family ZIP",
        `<input type="text" id="housingOptPresenceZip" class="zip" maxlength="5" inputmode="numeric" placeholder="60521" oninput="debouncedRefreshHousingOptValidation()">`,
        "The 5-digit ZIP proximity is measured from.",
      ) +
      housingOptField(
        "housingOptPresenceRadius",
        "Within",
        housingOptSelect("housingOptPresenceRadius", HOUSING_OPT_PRESENCE_RADII, 'onchange="debouncedRefreshHousingOptValidation()"'),
        "How far from the family ZIP the household may live during the presence window.",
      ) +
      housingOptField(
        "housingOptPresenceFrom",
        "From year",
        `<input type="number" id="housingOptPresenceFrom" class="year" oninput="debouncedRefreshHousingOptValidation()">`,
        "First year of the presence window. Must not be later than the through year.",
      ) +
      housingOptField(
        "housingOptPresenceThrough",
        "Through year",
        `<input type="number" id="housingOptPresenceThrough" class="year" oninput="debouncedRefreshHousingOptValidation()">`,
        "Last year of the presence window.",
      ),
  );

  const currentHomeRow = housingOptRow(
    "Current home",
    housingOptField(
      "housingOptDisposition",
      "Disposition",
      housingOptSelect(
        "housingOptDisposition",
        [
          { value: "auto", label: "Auto (search both)", selected: true },
          { value: "sell", label: "Sell" },
          { value: "keep", label: "Keep" },
        ],
        'onchange="toggleHousingOptDispositionFields(); debouncedRefreshHousingOptValidation()"',
      ),
      "Auto searches selling and keeping and lets the objective decide.",
    ) +
      housingOptField(
        "housingOptEarliestSale",
        "Earliest sale year",
        `<input type="number" id="housingOptEarliestSale" class="year" oninput="debouncedRefreshHousingOptValidation()">`,
        "First year the current home may be sold. Ignored when the disposition is Keep.",
      ) +
      housingOptField(
        "housingOptLatestSale",
        "Latest sale year",
        `<input type="number" id="housingOptLatestSale" class="year" oninput="debouncedRefreshHousingOptValidation()">`,
        "Last year the current home may be sold. Must not be earlier than the earliest sale year.",
      ) +
      `<div class="housing-opt-note small" id="housingOptKeepNote" hidden>Keeping the current home means its costs keep accruing. Rental income from a kept home is not modelled -- see the help panel.</div>`,
  );

  const purchaseAssumptionsRow = housingOptRow(
    "Purchase assumptions",
    housingOptField(
      "housingOptDownPaymentPct",
      "Down payment %",
      `<input type="number" id="housingOptDownPaymentPct" class="count" value="20" min="0" max="100" oninput="debouncedRefreshHousingOptValidation()">`,
      "Share of the purchase price paid up front. Applies to every move that ends up buying.",
    ) +
      housingOptField(
        "housingOptMortgageRatePct",
        "Mortgage rate %",
        `<input type="number" id="housingOptMortgageRatePct" class="count" value="6.85" min="0" max="100" step="0.01" oninput="debouncedRefreshHousingOptValidation()">`,
        "Fixed annual rate for every buy move. Clear this field to use each candidate's own location-based rate instead.",
      ),
  );

  const move2Row = housingOptRow(
    "Consider a second move",
    housingOptField(
      "housingOptMove2Enabled",
      "Consider a second move",
      `<input type="checkbox" id="housingOptMove2Enabled" onchange="toggleHousingOptMove2Fields(); debouncedRefreshHousingOptValidation()">`,
      "Adds a second acquisition with its own anchors, window and dwelling spec.",
    ) +
      `<div class="housing-opt-move2" id="housingOptMove2Fields" hidden>${housingOptMoveWhereRowHtml(2)}${housingOptMoveWhatRowHtml(2)}${housingOptMoveWhenRowHtml(2)}${housingOptRow(
        "Move 2 — mode",
        housingOptField(
          "housingOptMove2Concurrent",
          "Concurrent with move 1",
          `<input type="checkbox" id="housingOptMove2Concurrent" onchange="toggleHousingOptMove2ConcurrentAvailability(); debouncedRefreshHousingOptValidation()"><span class="housing-opt-note small" id="housingOptMove2ConcurrentNarrowedNote" hidden>Concurrent mode is only available with Full grid search mode.</span>`,
          "Keeps the move-1 home and adds this as a second residence rather than replacing it.",
        ) +
          housingOptField(
            "housingOptMove2AnchorCount",
            "Anchor count",
            `<input type="number" id="housingOptMove2AnchorCount" class="count" value="5" min="1" max="10" oninput="debouncedRefreshHousingOptValidation()">`,
            "How many move-1 winners the anchored move-2 strategy branches from.",
          ),
      )}</div>`,
  );

  const html = `<details class="housing-optimize-panel" id="${HOUSING_OPT_PANEL_ID}" oninput="debouncedSaveHousingOptInputs()" onchange="debouncedSaveHousingOptInputs()" ontoggle="debouncedSaveHousingOptInputs()"><summary>Optimize next housing move</summary><div class="housing-opt-body">
    <div class="housing-opt-head"><div class="section-note">Search the three decisions independently -- what happens to the current home, and where/what/when each move is -- against the same deterministic engine and Monte Carlo runner as the rest of the plan.</div><button class="btn small" type="button" id="housingOptPanelHelp" onclick="showHousingOptFieldHelp('_panel')">Help</button></div>
    ${objectiveRow}
    ${presenceRow}
    ${currentHomeRow}
    ${purchaseAssumptionsRow}
    ${housingOptMoveWhereRowHtml(1)}
    ${housingOptMoveWhatRowHtml(1)}
    ${housingOptMoveWhenRowHtml(1)}
    ${move2Row}
    <div class="housing-opt-run"><div class="housing-opt-validation" id="housingOptValidation" hidden></div><button class="btn primary" type="button" id="housingOptRun" onclick="startHousingOptimization()">Run optimization</button></div>
    <div id="${HOUSING_OPT_RESULTS_ID}"></div>
  </div></details>`;
  // Restore (§9.6) happens last, against the fully-built markup string above,
  // not against live DOM: this function only ever returns HTML for a caller
  // to assign into innerHTML, so there is no element tree to query yet. Only
  // inputs are restored -- the results div above is always emitted empty, so
  // a stale recommendation from a previous session can never be mistaken for
  // a fresh one.
  return housingOptHydratePanelHtml(html, housingOptStored);
}

// ---------------------------------------------------------------------------
// Shortlist preview (§7.3)
// ---------------------------------------------------------------------------

// Reads one move's search spec off the DOM. Task 12 builds the full optimize
// request on top of this; the preview endpoint takes the same `search` object
// for either move, so it does not need to know which one it serves.
export function housingOptMoveSearchBody(moveIndex) {
  const p = `housingOptMove${moveIndex}`;
  const val = (id) => String(document.getElementById(id)?.value || "").trim();
  const num = (id) => {
    const raw = val(id);
    return raw === "" ? null : Number(raw);
  };
  const anchors = [];
  const n = housingOptAnchorCounts[moveIndex] || HOUSING_OPT_MIN_ANCHORS;
  for (let i = 0; i < n; i++) {
    const kind = String(document.getElementById(`${p}Anchor${i}`)?.value || "city");
    const zip = kind === "zip" ? val(`${p}AnchorZip${i}`) : val(`${p}AnchorCity${i}`);
    if (zip) anchors.push({ kind, anchor_zip: zip });
  }
  const dwelling = {
    bedrooms: num(`${p}Bedrooms`) ?? 3,
    bathrooms: num(`${p}Bathrooms`) ?? 2,
    property_type: val(`${p}PropertyType`) || "single_family",
    sqft_band: val(`${p}SqftBand`) || "1800_2500",
    lot_size_band: val(`${p}LotSize`) || "quarter_half",
    built_within_years: num(`${p}BuiltWithin`),
  };
  const priceMin = num(`${p}PriceMin`);
  const priceMax = num(`${p}PriceMax`);
  if (priceMin !== null && priceMax !== null) {
    dwelling.target_purchase_price_range = [priceMin, priceMax];
  }
  return {
    anchors,
    radius_miles: num(`${p}Radius`) ?? 25,
    min_quality_score: num(`${p}MinScore`) ?? 60,
    area_type: val(`${p}AreaType`) || "any",
    max_population: num(`${p}MaxPopulation`),
    shortlist_size: num(`${p}ShortlistSize`) ?? 4,
    dwelling,
  };
}

export async function previewHousingZipShortlist(moveIndex) {
  const n = moveIndex || 1;
  const search = housingOptMoveSearchBody(n);
  if (search.anchors.length < HOUSING_OPT_MIN_ANCHORS) {
    showMessage(`Choose between 2 and 5 anchors for move ${n}.`, "error");
    return;
  }
  const target = document.getElementById(`housingOptMove${n}Shortlist`);
  showHousingOptOverlay(
    "Screening ZIPs",
    "Searching housing data around the chosen anchors for candidate ZIPs.",
  );
  try {
    const payload = await api("/api/housing/zip-screen", {
      method: "POST",
      body: JSON.stringify({ search }),
    });
    if (!payload || !payload.success) {
      if (target)
        target.innerHTML = `<p class="small warning">${esc((payload && payload.error) || "Screen failed.")}</p>`;
      return;
    }
    if (target) target.innerHTML = renderHousingZipShortlistHtml(payload);
  } catch (e) {
    showMessage("Error previewing shortlist: " + e.message, "error");
    if (target) target.innerHTML = "";
  } finally {
    hideHousingOptOverlay();
  }
}

// ---------------------------------------------------------------------------
// Results (§9.4)
// ---------------------------------------------------------------------------

// Human labels for the emptying-funnel field a relaxation hint names, so the
// suggestion reads as "the population cap" rather than the raw field name --
// and never defaults to "lowering the minimum score", which is only correct
// when `stage` really is `above_score` (design §9.4, Task 10's relaxation
// carries a `stage` naming the binding constraint precisely so this doesn't
// have to guess).
const HOUSING_ZIP_RELAX_FIELD_LABELS = {
  min_quality_score: "the minimum score",
  area_type: "the area type filter",
  max_population: "the population cap",
  target_purchase_price_range: "the target price range",
};

export function renderHousingZipShortlistHtml(payload, opts = {}) {
  const zs = payload && payload.zip_screen;
  if (!zs) return "";
  const note = `<div class="section-note">${esc(housingZipFunnelText(zs.funnel))}</div>`;
  const disclosure = `<div class="small">${esc(zs.disclosure)}</div>`;
  if (!zs.shortlist || !zs.shortlist.length) {
    const relax = zs.relaxation
      ? `<p class="small">${esc(housingZipRelaxationText(zs.relaxation))}</p>`
      : "";
    return note + relax + disclosure;
  }
  // "From family" only earns a column when there is family data to show --
  // the plain zip-screen preview never annotates family_distance_miles (only
  // a full optimizer run with family_presence set does), so an explicit
  // opts.familyPresence lets a caller force it while the data itself is the
  // default signal.
  const familyPresence =
    opts.familyPresence != null
      ? !!opts.familyPresence
      : zs.shortlist.some((z) => z.family_distance_miles != null);
  const rows = zs.shortlist.map((z) => housingZipRowHtml(z, familyPresence)).join("");
  const familyHeader = familyPresence ? "<th>From family</th>" : "";
  const table = `<table class="lot-table scenario-diff-table housing-optimize-table"><thead><tr><th>ZIP</th><th>Distance</th><th>Area type</th><th>Population</th><th>Stability score</th><th>Est. price</th>${familyHeader}</tr></thead><tbody>${rows}</tbody></table>`;
  return note + table + disclosure;
}

function housingZipRowHtml(z, familyPresence) {
  const cross = z.cross_state
    ? ` <span class="small warning">${esc(z.cross_state)} — different state tax treatment</span>`
    : "";
  const upi = z.upi_adjusted ? ' <span class="small">(university-adjusted)</span>' : "";
  const collapsed = (z.collapsed || []).length
    ? `<div class="small">+${z.collapsed.length} similar nearby: ${z.collapsed.map(esc).join(", ")}</div>`
    : "";
  const coverage =
    z.coverage_pct < 100 ? ` <span class="small">(${z.coverage_pct}% data coverage)</span>` : "";
  const areaType = z.area_type
    ? esc(z.area_type.charAt(0).toUpperCase() + z.area_type.slice(1))
    : "—";
  const population = z.population != null ? Number(z.population).toLocaleString() : "—";
  const familyCell = familyPresence
    ? `<td>${z.family_distance_miles != null ? `${z.family_distance_miles} mi` : "—"}</td>`
    : "";
  return `<tr><td>${esc(z.zip)} — ${esc(z.city)}, ${esc(z.state)}${cross}${collapsed}</td>
    <td>${z.distance_miles} mi</td>
    <td>${areaType}</td>
    <td>${population}</td>
    <td>${z.nss} <span class="small">${esc(z.band)}</span>${upi}${coverage}</td>
    <td>$${Math.round(z.est_price).toLocaleString()}</td>${familyCell}</tr>`;
}

// Nine stages (design §9.4/§7.2): in_radius -> with_data -> above_score ->
// matching_area_type -> under_population_cap -> affordable -> distinct ->
// near_family -> promoted. `distinct` replaced the old `after_dedup` name
// when the multi-anchor union and the near-family stage were added.
function housingZipFunnelText(f) {
  if (!f) return "";
  return (
    `${f.in_radius} ZIPs in range → ${f.with_data} with data → ` +
    `${f.above_score} above the score floor → ${f.matching_area_type} matching area type → ` +
    `${f.under_population_cap} under the population cap → ${f.affordable} affordable → ` +
    `${f.distinct} distinct → ${f.near_family} near family → ${f.promoted} sent to the optimizer`
  );
}

// `r.stage` names the binding constraint precisely (Task 10); using it rather
// than always saying "lowering the minimum score" matters because the
// population cap or the area-type filter can just as easily be what emptied
// the funnel.
function housingZipRelaxationText(r) {
  if (!r) return "";
  const label = HOUSING_ZIP_RELAX_FIELD_LABELS[r.field] || r.field;
  const stageNote = r.stage ? `The "${r.stage.replace(/_/g, " ")}" stage emptied the funnel. ` : "";
  return `${stageNote}Relaxing ${label} to ${r.suggested} would return ${r.would_return}.`;
}

// Human labels for the `rejections` tally (design §9.4/Task 10's known gap).
const HOUSING_OPT_REJECTION_LABELS = {
  dual_ownership: "dual ownership",
  family_presence: "family presence",
  move_order: "move order",
};

// A zero count is omitted rather than rendered: `rejections['move_order']` is
// only measured in `search_mode='full'` -- in narrowed mode the generators
// drop out-of-order move-2 points inside their own loops before the tally
// ever sees them, so it reads 0 there even though the rule was never
// actually checked. Displaying "0 rejected for move order" would assert
// something the optimizer did not measure (design §8, "Known gap (Task 9,
// 2026-09-16)").
function housingOptRejectionParts(rejections) {
  const parts = [];
  for (const key of Object.keys(rejections || {})) {
    const n = rejections[key];
    if (!n) continue;
    parts.push(`${n} rejected for ${HOUSING_OPT_REJECTION_LABELS[key] || key}`);
  }
  return parts;
}

// The zip screen's own relaxation hint (if any) names the binding constraint
// that emptied ITS funnel, which is a different diagnosis than the
// optimizer-level rejections tally: a move's shortlist can be non-empty while
// the optimizer still rejects every combination it produces (e.g. every
// candidate would require dual ownership).
function housingOptEmptyFunnelParts(zipScreens) {
  const parts = [];
  for (const key of ["move1", "move2"]) {
    const zs = zipScreens && zipScreens[key];
    if (zs && zs.relaxation) {
      const label = key === "move1" ? "Move 1" : "Move 2";
      parts.push(`${label}: ${housingZipRelaxationText(zs.relaxation)}`);
    }
  }
  return parts;
}

function renderHousingOptimizeEmptyHtml(payload) {
  const rejectionParts = housingOptRejectionParts(payload.rejections);
  const funnelParts = housingOptEmptyFunnelParts(payload.zip_screens);
  if (!rejectionParts.length && !funnelParts.length) {
    return '<p class="small">No candidates satisfied the search windows and constraints.</p>';
  }
  const rejectionHtml = rejectionParts.length
    ? `<p class="small">${esc(rejectionParts.join("; ") + ".")}</p>`
    : "";
  const funnelHtml = funnelParts.length
    ? `<p class="small">${funnelParts.map((p) => esc(p)).join("</p><p class=\"small\">")}</p>`
    : "";
  return `<div class="housing-opt-empty">${rejectionHtml}${funnelHtml}</div>`;
}

function housingOptCurrentHomeHtml(originalHome) {
  if (!originalHome) return "—";
  if (originalHome.disposition === "keep") return "Keep";
  return originalHome.sale_year != null ? `Sell ${originalHome.sale_year}` : "Sell";
}

function housingOptActionLabel(action) {
  if (!action) return "";
  return action.charAt(0).toUpperCase() + action.slice(1);
}

// `${year} · ${Buy|Rent} · ${zip} ${city}, ${state} · ${distance} mi · ${money}`
// (design §9.4), where ${money} is:
//   - for rent: `$${monthly_rent}/mo rent`
//   - for buy: `$${purchase_price} purchase · $${monthly_pi_payment}/mo P&I`
// Appends `· ${n} mi from family` only when family_distance_miles is non-null,
// so a plain search (no family presence) never implies a family-distance
// measurement that was never taken.
function housingOptMoveCellHtml(move) {
  if (!move) return "—";
  const loc = move.location || {};
  const financing = move.financing || {};
  const distance = loc.distance_miles != null ? `${Number(loc.distance_miles).toFixed(1)} mi` : "—";
  let money;
  if (move.action === "rent") {
    money =
      financing.monthly_rent != null
        ? `$${Math.round(financing.monthly_rent).toLocaleString()}/mo rent`
        : "—";
  } else {
    const price =
      financing.purchase_price != null
        ? `$${Math.round(financing.purchase_price).toLocaleString()} purchase`
        : "—";
    const pi =
      financing.monthly_pi_payment != null
        ? `$${Math.round(financing.monthly_pi_payment).toLocaleString()}/mo P&I`
        : "—";
    money = `${price} · ${pi}`;
  }
  let text =
    `${move.acquisition_year} · ${housingOptActionLabel(move.action)} · ` +
    `${loc.zip_code || ""} ${loc.city || ""}, ${loc.state || ""} · ${distance} · ${money}`;
  if (loc.family_distance_miles != null) {
    text += ` · ${loc.family_distance_miles} mi from family`;
  }
  return esc(text);
}

const HOUSING_OPT_OBJECTIVE_FORMATTERS = {
  net_worth: (v) => (v != null ? `$${Math.round(v).toLocaleString()}` : "—"),
  lifetime_cost: (v) => (v != null ? `$${Math.round(v).toLocaleString()}` : "—"),
  mc_success_rate: (v) => (v != null ? `${Math.round(v * 100)}%` : "—"),
};

function housingOptResultObjectiveHtml(c, objective) {
  const fmt = HOUSING_OPT_OBJECTIVE_FORMATTERS[objective] || ((v) => (v != null ? String(v) : "—"));
  return esc(fmt(c.objective_value));
}

// One row per candidate (design §9.4): a rank badge, current-home
// disposition, both move cells, the objective value, MC success, and notes.
// Rank 1 carries the "Recommended" label and the `housing-opt-result-top`
// class so the recommendation stays findable after the table wraps or the
// viewer scrolls -- alternating shading and a heavy rule between results
// (Task 14 CSS) are the other two boundary cues design §9.4 asks for.
function housingOptResultRowHtml(c, objective) {
  const shade = c.rank % 2 ? "housing-opt-result-odd" : "housing-opt-result-even";
  const topClass = c.rank === 1 ? " housing-opt-result-top" : "";
  const recommended = c.rank === 1 ? ' <span class="housing-opt-badge">Recommended</span>' : "";
  const rankCell = `<span class="housing-opt-rank">${esc(String(c.rank))}</span>${recommended}`;
  const moves = c.moves || [];
  const mc = c.mc_success_rate != null ? `${Math.round(c.mc_success_rate * 100)}%` : "—";
  const notes = (c.notes || []).length ? esc(c.notes.join("; ")) : "—";
  return `<tr class="housing-opt-result ${shade}${topClass}">
    <td>${rankCell}</td>
    <td>${esc(housingOptCurrentHomeHtml(c.original_home))}</td>
    <td>${housingOptMoveCellHtml(moves[0])}</td>
    <td>${housingOptMoveCellHtml(moves[1])}</td>
    <td>${housingOptResultObjectiveHtml(c, objective)}</td>
    <td>${esc(mc)}</td>
    <td>${notes}</td>
  </tr>`;
}

export function renderHousingOptimizeResultsHtml(payload) {
  if (!payload) return "";
  const candidates = payload.candidates || [];
  if (!candidates.length) {
    return renderHousingOptimizeEmptyHtml(payload);
  }
  const rows = candidates.map((c) => housingOptResultRowHtml(c, payload.objective)).join("");
  return (
    '<table class="lot-table scenario-diff-table housing-optimize-table"><thead><tr>' +
    "<th>Rank</th><th>Current home</th><th>Move 1</th><th>Move 2</th>" +
    "<th>Objective</th><th>MC success</th><th>Notes</th>" +
    `</tr></thead><tbody>${rows}</tbody></table>`
  );
}

// ---------------------------------------------------------------------------
// Request building (§7.1) and inline validation (§8)
// ---------------------------------------------------------------------------
//
// validateHousingOptForm() fires the same rules as src/housing/api.py's
// validate_request, in the same order, with character-identical messages
// (Task 12). The two copies are kept in sync by hand -- there is no shared
// source a browser script can import from a Python module -- but this is the
// fast/local check only; validate_request is the one that is trusted.

function housingOptDomVal(id) {
  return String(document.getElementById(id)?.value || "").trim();
}

function housingOptDomNum(id) {
  const raw = housingOptDomVal(id);
  return raw === "" ? 0 : Number(raw);
}

function housingOptDomChecked(id) {
  return !!document.getElementById(id)?.checked;
}

// Python's repr() of a str wraps it in single quotes -- validate_request's
// "Unknown X" messages are built with `{val!r}`, so this mirrors that exactly
// rather than JS's own (double-quoted) String() formatting.
function housingOptRepr(v) {
  return `'${v}'`;
}

// Builds the §7.1 v2 request body straight off the DOM. Never emits a
// `locations` key -- every candidate location comes from a per-move
// ZIP-radius screen (housingOptMoveSearchBody), not a hand-picked list.
export function buildHousingOptRequest() {
  const objective = housingOptDomVal("housingOptObjective") || "net_worth";
  const search_mode = housingOptDomVal("housingOptSearchMode") || "full";
  const move2_strategy = housingOptDomVal("housingOptMove2Strategy") || "anchored";
  const no_dual_ownership = housingOptDomChecked("housingOptNoDualOwnership");

  const disposition = (housingOptDomVal("housingOptDisposition") || "auto").toLowerCase();
  const original_home = { disposition };
  if (disposition !== "keep") {
    original_home.earliest_sale_year = housingOptDomNum("housingOptEarliestSale");
    original_home.latest_sale_year = housingOptDomNum("housingOptLatestSale");
  }

  const move1 = {
    earliest_acquisition_year: housingOptDomNum("housingOptMove1Earliest"),
    latest_acquisition_year: housingOptDomNum("housingOptMove1Latest"),
    action: housingOptDomVal("housingOptMove1Action") || "auto",
    search: housingOptMoveSearchBody(1),
  };

  const downPaymentRaw = housingOptDomVal("housingOptDownPaymentPct");
  const down_payment_pct = (downPaymentRaw === "" ? 20 : Number(downPaymentRaw)) / 100;
  const mortgageRaw = housingOptDomVal("housingOptMortgageRatePct");
  const mortgage_rate_pct = mortgageRaw === "" ? null : Number(mortgageRaw) / 100;

  const body = {
    objective,
    search_mode,
    move2_strategy,
    no_dual_ownership,
    original_home,
    move1,
    down_payment_pct,
    mortgage_rate_pct,
  };

  if (housingOptDomChecked("housingOptMove2Enabled")) {
    body.move2 = {
      earliest_acquisition_year: housingOptDomNum("housingOptMove2Earliest"),
      latest_acquisition_year: housingOptDomNum("housingOptMove2Latest"),
      action: housingOptDomVal("housingOptMove2Action") || "auto",
      concurrent: housingOptDomChecked("housingOptMove2Concurrent"),
      anchor_count: housingOptDomNum("housingOptMove2AnchorCount") || 5,
      search: housingOptMoveSearchBody(2),
    };
  }

  if (housingOptDomChecked("housingOptPresenceEnabled")) {
    body.family_presence = {
      zip: housingOptDomVal("housingOptPresenceZip"),
      radius_miles: housingOptDomNum("housingOptPresenceRadius"),
      from_year: housingOptDomNum("housingOptPresenceFrom"),
      through_year: housingOptDomNum("housingOptPresenceThrough"),
    };
  }

  return body;
}

// Mirrors src/housing/api.py's validate_request rule-for-rule and in the same
// order (the `locations` check is omitted: the panel has no control that
// could ever produce that key). Returns the first violated rule's message,
// or null when the form is valid.
export function validateHousingOptForm() {
  const objective = housingOptDomVal("housingOptObjective") || "net_worth";
  if (!HOUSING_OPT_OBJECTIVES.includes(objective)) {
    return `Unknown objective: ${housingOptRepr(objective)}.`;
  }

  const search_mode = housingOptDomVal("housingOptSearchMode") || "full";
  if (!HOUSING_OPT_SEARCH_MODES.includes(search_mode)) {
    return `Unknown search_mode: ${housingOptRepr(search_mode)}.`;
  }

  const move2_strategy = housingOptDomVal("housingOptMove2Strategy") || "anchored";
  if (!HOUSING_OPT_MOVE2_STRATEGIES.includes(move2_strategy)) {
    return `Unknown move2_strategy: ${housingOptRepr(move2_strategy)}.`;
  }

  const disposition = (housingOptDomVal("housingOptDisposition") || "auto").toLowerCase();
  if (!HOUSING_OPT_DISPOSITIONS.includes(disposition)) {
    return `Unknown disposition: ${housingOptRepr(disposition)}.`;
  }

  const sells = disposition === "sell" || disposition === "auto";
  const earliestSale = housingOptDomNum("housingOptEarliestSale");
  const latestSale = housingOptDomNum("housingOptLatestSale");
  if (sells && earliestSale > latestSale) {
    return "Earliest sale year must not be after the latest sale year.";
  }

  const e1 = housingOptDomNum("housingOptMove1Earliest");
  const l1 = housingOptDomNum("housingOptMove1Latest");
  if (e1 > l1) {
    return "Earliest move-1 year must not be after the latest.";
  }

  const move1Action = housingOptDomVal("housingOptMove1Action") || "auto";
  const move2Enabled = housingOptDomChecked("housingOptMove2Enabled");
  if (move2Enabled) {
    const e2 = housingOptDomNum("housingOptMove2Earliest");
    const l2 = housingOptDomNum("housingOptMove2Latest");
    const concurrent = housingOptDomChecked("housingOptMove2Concurrent");
    if (e2 > l2) {
      return "Earliest move-2 year must not be after the latest.";
    }
    if (!concurrent && l2 <= e1) {
      return `Move 2 must be able to happen after move 1. Raise the move-2 latest year above ${e1}.`;
    }
    if (concurrent && search_mode !== "full") {
      return "Concurrent mode is only available with Full grid search mode.";
    }
  }

  const noDual = housingOptDomChecked("housingOptNoDualOwnership");
  const actions = [move1Action];
  if (move2Enabled) actions.push(housingOptDomVal("housingOptMove2Action") || "auto");
  if (noDual && disposition === "keep" && actions.length && actions.every((a) => a === "buy")) {
    return (
      "Keeping the current home and buying another means owning two " +
      "homes. Choose Rent, sell the current home, or turn off " +
      "'Never own two homes at once'."
    );
  }
  if (noDual && disposition === "sell" && move1Action === "buy" && l1 < earliestSale) {
    return (
      "With no dual ownership, move 1 cannot be bought before the home " +
      `is sold. Raise the move-1 latest year to at least ${earliestSale}.`
    );
  }

  const areaTypeValues = HOUSING_OPT_AREA_TYPES.map((o) => o.value);
  const movesToCheck = move2Enabled ? [1, 2] : [1];
  for (const n of movesToCheck) {
    const search = housingOptMoveSearchBody(n);
    const label = `move ${n}`;
    if (!(search.anchors.length >= HOUSING_OPT_MIN_ANCHORS && search.anchors.length <= HOUSING_OPT_MAX_ANCHORS)) {
      return `Choose between 2 and 5 anchors for ${label}.`;
    }
    if (!HOUSING_OPT_ALLOWED_RADII_MILES.includes(search.radius_miles)) {
      return `Radius must be one of ${HOUSING_OPT_ALLOWED_RADII_MILES.join(", ")} miles.`;
    }
    if (!areaTypeValues.includes(search.area_type)) {
      return `Unknown area type ${housingOptRepr(search.area_type)}.`;
    }
    const rng = search.dwelling && search.dwelling.target_purchase_price_range;
    if (rng && Number(rng[0]) > Number(rng[1])) {
      return "Minimum target price must not exceed the maximum.";
    }
  }

  if (housingOptDomChecked("housingOptPresenceEnabled")) {
    const zip = housingOptDomVal("housingOptPresenceZip");
    const fromYear = housingOptDomNum("housingOptPresenceFrom");
    const throughYear = housingOptDomNum("housingOptPresenceThrough");
    if (zip.length !== 5 || !/^\d{5}$/.test(zip) || fromYear > throughYear) {
      return (
        "Family presence needs a 5-digit ZIP and a from-year no later " +
        "than the through-year."
      );
    }
    const radius = housingOptDomNum("housingOptPresenceRadius");
    if (!HOUSING_OPT_FAMILY_RADII_MILES.includes(radius)) {
      return `Family radius must be one of ${HOUSING_OPT_FAMILY_RADII_MILES.join(", ")} miles.`;
    }
  }

  const downPaymentRaw = housingOptDomVal("housingOptDownPaymentPct");
  if (downPaymentRaw !== "" && !(Number(downPaymentRaw) >= 0 && Number(downPaymentRaw) <= 100)) {
    return "Down payment % must be between 0 and 100.";
  }
  const mortgageRaw = housingOptDomVal("housingOptMortgageRatePct");
  if (mortgageRaw !== "" && !(Number(mortgageRaw) >= 0 && Number(mortgageRaw) <= 100)) {
    return "Mortgage rate % must be between 0 and 100.";
  }

  return null;
}

let housingOptValidationTimer = null;

// Runs validateHousingOptForm() immediately, disables the Run button while
// any rule fails, and writes the first violated message into
// #housingOptValidation (design §8: "renders messages next to the offending
// group[s] ... disables the Run button while any rule fails").
export function refreshHousingOptValidation() {
  const msg = validateHousingOptForm();
  const runBtn = document.getElementById("housingOptRun");
  if (runBtn) runBtn.disabled = !!msg;
  const box = document.getElementById("housingOptValidation");
  if (box) {
    box.textContent = msg || "";
    box.hidden = !msg;
  }
  return msg;
}

// Debounced entry point wired to oninput/onchange on every year, ZIP and
// price field (design §8: "Validation runs on every input event"), so a fast
// typist does not re-run validation on every keystroke.
export function debouncedRefreshHousingOptValidation() {
  if (housingOptValidationTimer) clearTimeout(housingOptValidationTimer);
  housingOptValidationTimer = setTimeout(refreshHousingOptValidation, 200);
}

// ---------------------------------------------------------------------------
// Run
// ---------------------------------------------------------------------------

// Shared progress popup for the panel's async calls (preview shortlist, run
// optimization): both hit the backend with no incremental progress to
// report, so this reuses the generic buildOverlay in "waiting" (indeterminate
// spinner) mode rather than a bespoke one, matching showYtdLoadOverlay /
// showSpendingModelLoadOverlay elsewhere in the dashboard. no-cancel is set
// because neither call is cancellable.
function showHousingOptOverlay(title, detail) {
  setBuildOverlay(true, title, detail, "waiting");
  const overlay = document.getElementById("buildOverlay");
  if (overlay) overlay.classList.add("no-cancel");
}
function hideHousingOptOverlay() {
  const overlay = document.getElementById("buildOverlay");
  if (overlay) overlay.classList.remove("no-cancel");
  hideBuildOverlay();
}

export async function runHousingOptimization() {
  const msg = refreshHousingOptValidation();
  if (msg) {
    showMessage(msg, "error");
    return;
  }
  const body = buildHousingOptRequest();
  const target = document.getElementById("housingOptimizeResults");
  showHousingOptOverlay(
    "Running Housing Optimization",
    "Searching move combinations across the configured anchors and windows. This can take a few seconds on a full grid search.",
  );
  try {
    const payload = await api("/api/housing/optimize", {
      method: "POST",
      body: JSON.stringify(body),
    });
    if (!payload || !payload.success) {
      if (target)
        target.innerHTML = `<p class="small warning">${esc((payload && payload.error) || "Optimization failed.")}</p>`;
      return;
    }
    if (target) target.innerHTML = renderHousingOptimizeResultsHtml(payload);
  } catch (e) {
    showMessage("Error running optimization: " + e.message, "error");
    if (target) target.innerHTML = "";
  } finally {
    hideHousingOptOverlay();
  }
}

// Thin alias for the panel's "Run optimization" button, kept distinct from
// runHousingOptimization so the button's onclick text does not shadow that
// function's definition for tooling that scans this file's source.
export function startHousingOptimization() {
  return runHousingOptimization();
}

// Every export above is also re-attached to window: inline onclick/onchange
// handlers in the markup this module renders resolve through window regardless
// of module scoping, and dashboard_decomp_housing_scenarios.js calls
// renderHousingOptimizePanelHtml() as a bare global.
Object.assign(window, {
  HOUSING_OPT_PANEL_ID,
  HOUSING_OPT_STORAGE_KEY,
  housingOptAnchorEntryHtml,
  renderHousingOptAnchorsHtml,
  toggleHousingOptAnchorMode,
  addHousingOptAnchor,
  removeHousingOptAnchor,
  loadHousingOptTopCities,
  loadHousingOptInputs,
  saveHousingOptInputs,
  debouncedSaveHousingOptInputs,
  showHousingOptFieldHelp,
  HOUSING_OPT_FIELD_HELP,
  toggleHousingOptMove2Fields,
  toggleHousingOptMove2ConcurrentAvailability,
  toggleHousingOptNoDualOwnershipAvailability,
  toggleHousingOptDispositionFields,
  renderHousingOptimizePanelHtml,
  housingOptMoveSearchBody,
  previewHousingZipShortlist,
  renderHousingZipShortlistHtml,
  renderHousingOptimizeResultsHtml,
  buildHousingOptRequest,
  validateHousingOptForm,
  refreshHousingOptValidation,
  debouncedRefreshHousingOptValidation,
  runHousingOptimization,
  startHousingOptimization,
});
