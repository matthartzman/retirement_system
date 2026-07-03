/* Retirement Planner app store extraction seam.
   Small browser-local state container used while the monolithic dashboard is
   being split into feature modules. It intentionally mirrors existing global
   state instead of owning projections or saved plan data. */
(function(global){
  'use strict';
  const state = {
    rows: [],
    dirtyCount: 0,
    holdingsChanged: false,
    liabilitiesChanged: false,
    spendingChanged: false,
    planLoaded: false,
    planSource: '',
    activeStep: '',
    lastBuildOk: false,
    runtime: null,
    updatedAt: ''
  };
  const listeners = new Set();
  function clone(value){
    if(value === undefined || value === null) return value;
    try{ return JSON.parse(JSON.stringify(value)); }catch(_e){ return value; }
  }
  function emit(){
    state.updatedAt = new Date().toISOString();
    listeners.forEach(function(fn){ try{ fn(snapshot()); }catch(_e){} });
  }
  function set(patch){ Object.assign(state, patch || {}); emit(); return snapshot(); }
  function snapshot(){ return Object.assign({}, state, {rows: Array.isArray(state.rows) ? state.rows.slice() : []}); }
  function setRows(rows){ return set({rows:Array.isArray(rows)?rows.slice():[]}); }
  function markDirty(count){ return set({dirtyCount:Math.max(0, Number(count) || 0)}); }
  function resetPlanFlags(){ return set({dirtyCount:0, holdingsChanged:false, liabilitiesChanged:false, spendingChanged:false}); }
  function subscribe(fn){ if(typeof fn==='function') listeners.add(fn); return function(){ listeners.delete(fn); }; }
  global.RetirementAppStore = { set:set, setRows:setRows, markDirty:markDirty, resetPlanFlags:resetPlanFlags, snapshot:snapshot, subscribe:subscribe, clone:clone };
})(window);
