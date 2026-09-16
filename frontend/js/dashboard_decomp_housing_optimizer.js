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

// Field help content registry (design §9.5). Task 14 fills this with the
// four-section pageHelp() entries keyed by field id; the call sites below
// already exist so that task is content-only.
const HOUSING_OPT_FIELD_HELP = {};

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

const HOUSING_OPT_AREA_TYPES = [
  { value: "any", label: "Any", selected: true },
  { value: "urban", label: "Urban" },
  { value: "suburban", label: "Suburban" },
  { value: "exurban", label: "Exurban" },
  { value: "rural", label: "Rural" },
];

const HOUSING_OPT_BEDROOMS = [
  { value: "2", label: "2 BR" },
  { value: "3", label: "3 BR", selected: true },
  { value: "4", label: "4 BR" },
  { value: "5", label: "5+ BR" },
];

const HOUSING_OPT_BATHROOMS = [
  { value: "1", label: "1 BA" },
  { value: "1.5", label: "1.5 BA" },
  { value: "2", label: "2 BA", selected: true },
  { value: "2.5", label: "2.5 BA" },
  { value: "3", label: "3 BA" },
  { value: "3.5", label: "3.5+ BA" },
];

const HOUSING_OPT_PROPERTY_TYPES = [
  { value: "single_family", label: "Single family", selected: true },
  { value: "townhome", label: "Townhome" },
  { value: "condo", label: "Condo" },
  { value: "duplex", label: "Duplex" },
];

const HOUSING_OPT_SQFT_BANDS = [
  { value: "under_1200", label: "Under 1,200 sqft" },
  { value: "1200_1800", label: "1,200-1,800 sqft" },
  { value: "1800_2500", label: "1,800-2,500 sqft", selected: true },
  { value: "2500_3500", label: "2,500-3,500 sqft" },
  { value: "over_3500", label: "Over 3,500 sqft" },
];

const HOUSING_OPT_LOT_SIZE_BANDS = [
  { value: "under_quarter", label: "Under 1/4 acre" },
  { value: "quarter_half", label: "1/4 to 1/2 acre", selected: true },
  { value: "half_one", label: "1/2 to 1 acre" },
  { value: "one_three", label: "1 to 3 acres" },
  { value: "over_three", label: "Over 3 acres" },
];

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
  redrawHousingOptAnchors(moveIndex);
}

export function removeHousingOptAnchor(moveIndex, i) {
  const n = housingOptAnchorCounts[moveIndex] || HOUSING_OPT_MIN_ANCHORS;
  if (n <= HOUSING_OPT_MIN_ANCHORS || i < HOUSING_OPT_MIN_ANCHORS) return;
  housingOptAnchorCounts[moveIndex] = n - 1;
  redrawHousingOptAnchors(moveIndex);
}

function redrawHousingOptAnchors(moveIndex) {
  const container = document.getElementById(`housingOptMove${moveIndex}Anchors`);
  if (!container) return;
  const n = housingOptAnchorCounts[moveIndex] || HOUSING_OPT_MIN_ANCHORS;
  container.innerHTML = Array.from({ length: n }, (_, i) =>
    housingOptAnchorEntryHtml(moveIndex, i),
  ).join("");
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
// Help (§9.5) -- Task 14 supplies the content.
// ---------------------------------------------------------------------------

export function showHousingOptFieldHelp(key) {
  const entry = HOUSING_OPT_FIELD_HELP[key];
  if (!entry) return;
  ensureHelpPanelVisible();
  const panel = document.getElementById("helpPanel");
  if (panel) panel.innerHTML = entry;
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
        `${p}AreaType`,
        "Area type",
        housingOptSelect(`${p}AreaType`, HOUSING_OPT_AREA_TYPES, 'onchange="debouncedRefreshHousingOptValidation()"'),
        "Compared against the ZIP's density-derived area type. Any skips the filter.",
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

  return `<details class="housing-optimize-panel"><summary>Optimize next housing move</summary><div class="housing-opt-body">
    <div class="housing-opt-head"><div class="section-note">Search the three decisions independently -- what happens to the current home, and where/what/when each move is -- against the same deterministic engine and Monte Carlo runner as the rest of the plan.</div><button class="btn small" type="button" id="housingOptPanelHelp" onclick="showHousingOptFieldHelp('_panel')">Help</button></div>
    ${objectiveRow}
    ${presenceRow}
    ${currentHomeRow}
    ${housingOptMoveWhereRowHtml(1)}
    ${housingOptMoveWhatRowHtml(1)}
    ${housingOptMoveWhenRowHtml(1)}
    ${move2Row}
    <div class="housing-opt-run"><div class="housing-opt-validation" id="housingOptValidation" hidden></div><button class="btn primary" type="button" id="housingOptRun" onclick="startHousingOptimization()">Run optimization</button></div>
    <div id="housingOptimizeResults"></div>
  </div></details>`;
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
  }
}

// ---------------------------------------------------------------------------
// Results (§9.4) -- Task 13 rewrites these for the v2 candidates payload.
// ---------------------------------------------------------------------------

export function renderHousingZipShortlistHtml(payload) {
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
  const rows = zs.shortlist.map(housingZipRowHtml).join("");
  const table = `<table class="lot-table scenario-diff-table housing-optimize-table"><thead><tr><th>ZIP</th><th>Distance</th><th>Stability score</th><th>Est. price</th></tr></thead><tbody>${rows}</tbody></table>`;
  return note + table + disclosure;
}

function housingZipRowHtml(z) {
  const cross = z.cross_state
    ? ` <span class="small warning">${esc(z.cross_state)} — different state tax treatment</span>`
    : "";
  const upi = z.upi_adjusted ? ' <span class="small">(university-adjusted)</span>' : "";
  const collapsed = (z.collapsed || []).length
    ? `<div class="small">+${z.collapsed.length} similar nearby: ${z.collapsed.map(esc).join(", ")}</div>`
    : "";
  const coverage =
    z.coverage_pct < 100 ? ` <span class="small">(${z.coverage_pct}% data coverage)</span>` : "";
  return `<tr><td>${esc(z.zip)} — ${esc(z.city)}, ${esc(z.state)}${cross}${collapsed}</td>
    <td>${z.distance_miles} mi</td>
    <td>${z.nss} <span class="small">${esc(z.band)}</span>${upi}${coverage}</td>
    <td>$${Math.round(z.est_price).toLocaleString()}</td></tr>`;
}

function housingZipFunnelText(f) {
  if (!f) return "";
  return `${f.in_radius} ZIPs in range → ${f.with_data} with data → ${f.above_score} above the score floor → ${f.affordable} affordable → ${f.after_dedup} distinct → ${f.promoted} sent to the optimizer`;
}

function housingZipRelaxationText(r) {
  if (!r) return "";
  return `Lowering the minimum score to ${r.suggested} would return ${r.would_return}.`;
}

export function renderHousingOptimizeResultsHtml(payload) {
  if (!payload) return "";
  const candidates = payload.candidates || [];
  if (!candidates.length) {
    return '<p class="small">No candidates satisfied the search windows and constraints.</p>';
  }
  const objLabel =
    HOUSING_OPT_OBJECTIVE_LABELS[payload.objective] || String(payload.objective || "");
  const rows = candidates
    .map(
      (c) =>
        `<tr><td>${esc(String(c.rank))}</td><td>${esc(objLabel)}</td><td>${esc((c.notes || []).join("; "))}</td></tr>`,
    )
    .join("");
  return `<table class="lot-table scenario-diff-table housing-optimize-table"><thead><tr><th>Rank</th><th>${esc(objLabel)}</th><th>Notes</th></tr></thead><tbody>${rows}</tbody></table>`;
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

  const body = {
    objective,
    search_mode,
    move2_strategy,
    no_dual_ownership,
    original_home,
    move1,
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

export async function runHousingOptimization() {
  const msg = refreshHousingOptValidation();
  if (msg) {
    showMessage(msg, "error");
    return;
  }
  const body = buildHousingOptRequest();
  const target = document.getElementById("housingOptimizeResults");
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
  housingOptAnchorEntryHtml,
  renderHousingOptAnchorsHtml,
  toggleHousingOptAnchorMode,
  addHousingOptAnchor,
  removeHousingOptAnchor,
  loadHousingOptTopCities,
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
