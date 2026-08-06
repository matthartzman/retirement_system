// #260: every "state" Plan Data input is a pull-down of the 50 states plus
// DC, never free text. Extracted from dashboard.js (shares its classic-script
// global scope, same as the other dashboard_decomp_*.js siblings) so the
// state-list data doesn't grow the monolith past its line-count ratchet.
//
// Mirrors src/us_states.py -- keep in sync. DC is appended as its own
// explicit entry, distinct from the 50 states, not folded silently in.
const US_STATES_AND_DC = [
  ["Alabama", "AL"], ["Alaska", "AK"], ["Arizona", "AZ"], ["Arkansas", "AR"],
  ["California", "CA"], ["Colorado", "CO"], ["Connecticut", "CT"], ["Delaware", "DE"],
  ["Florida", "FL"], ["Georgia", "GA"], ["Hawaii", "HI"], ["Idaho", "ID"],
  ["Illinois", "IL"], ["Indiana", "IN"], ["Iowa", "IA"], ["Kansas", "KS"],
  ["Kentucky", "KY"], ["Louisiana", "LA"], ["Maine", "ME"], ["Maryland", "MD"],
  ["Massachusetts", "MA"], ["Michigan", "MI"], ["Minnesota", "MN"], ["Mississippi", "MS"],
  ["Missouri", "MO"], ["Montana", "MT"], ["Nebraska", "NE"], ["Nevada", "NV"],
  ["New Hampshire", "NH"], ["New Jersey", "NJ"], ["New Mexico", "NM"], ["New York", "NY"],
  ["North Carolina", "NC"], ["North Dakota", "ND"], ["Ohio", "OH"], ["Oklahoma", "OK"],
  ["Oregon", "OR"], ["Pennsylvania", "PA"], ["Rhode Island", "RI"], ["South Carolina", "SC"],
  ["South Dakota", "SD"], ["Tennessee", "TN"], ["Texas", "TX"], ["Utah", "UT"],
  ["Vermont", "VT"], ["Virginia", "VA"], ["Washington", "WA"], ["West Virginia", "WV"],
  ["Wisconsin", "WI"], ["Wyoming", "WY"],
  ["District of Columbia", "DC"],
];
export function _stateNameChoiceOptions() {
  return US_STATES_AND_DC.map(([name]) => ({ value: name, label: name }));
}
export function _stateAbbrChoiceOptions() {
  return US_STATES_AND_DC.map(([name, abbr]) => ({
    value: abbr,
    label: `${name} (${abbr})`,
  }));
}
// These labels force fieldHtml() into the choice/<select> branch even though
// schema.csv doesn't tag them type=choice.
window.STATE_INPUT_LABELS = new Set(["state", "residence_state", "target_state"]);

// Wave 6.4 ("leaves inward" ES-module migration, 'settings' leaf):
// STATE_INPUT_LABELS is read directly by dashboard.js's fieldHtml() (a
// data constant, not a function call), so it's an explicit window property
// rather than module-private; US_STATES_AND_DC is read only by the two
// functions below, so it can stay module-private.
Object.assign(window, {
  _stateNameChoiceOptions,
  _stateAbbrChoiceOptions,
});
