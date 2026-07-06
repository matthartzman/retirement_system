/* navigation.js: feature-owned navigation behavior for the retirement dashboard. */
(function(){
  'use strict';
  const AUTOSAVE_STEPS=['ytd_transactions','spending_core','spending_setup','spending_travel','spending_travel_extras','spending_mortgage_events','retirement_wellness'];
  const PLAN_INDEPENDENT_STEPS=['start','system_configuration','detailed_results','planning_workbench','reports_and_review'];
  const REPORTS_REDIRECTS={
    detailed_results:'Results',
    build_impact:'Impact',
    review:'Downloads',
    plan_data_report:'Plan Data Review',
    spending_dashboard:'Results'
  };
  const STEP_REDIRECTS={
    spending_travel:'lifestyle_spending',
    spending_travel_extras:'lifestyle_spending',
    ss_timing:'timing_tax',
    state_residency:'timing_tax',
    heloc_strategy:'special_strategies',
    entity_charitable:'special_strategies',
    roth_conversion:'distribution_strategy',
    withdrawal_strategy:'distribution_strategy',
    allocation_assets:'distribution_strategy',
    allocation_policy:'distribution_strategy',
    investment_strategy:'distribution_strategy'
  };

  function noop(){}
  function safeCall(fn){try{return typeof fn==='function'?fn():undefined}catch(_e){return undefined}}
  function setStep(ctx,id){
    ctx=ctx||{};
    const planLoaded=!!safeCall(ctx.getPlanLoaded);
    if(REPORTS_REDIRECTS[id]){
      safeCall(()=>ctx.setReportsTab(REPORTS_REDIRECTS[id]));
      id='reports_and_review';
    }else if(STEP_REDIRECTS[id]){
      id=STEP_REDIRECTS[id];
    }
    if(!planLoaded&&!PLAN_INDEPENDENT_STEPS.includes(id)){
      safeCall(()=>ctx.setActiveStep('start'));
      safeCall(ctx.renderMain);
      setTimeout(()=>{try{window.scrollTo({top:0,behavior:'smooth'});}catch(_e){}},0);
      return;
    }
    safeCall(()=>ctx.setActiveStep(id));
    safeCall(()=>ctx.setSearchText(''));
    const srch=document.getElementById('combinedSearch');
    if(srch)srch.value='';
    safeCall(()=>ctx.setNavSearchText(''));
    if(id==='build_impact'&&safeCall(ctx.getLastBuildCompare)&&!safeCall(ctx.getLastBuildOk)){
      safeCall(()=>ctx.showMessage('Plan inputs changed since last build — results may be stale.','warn',{persistent:true,action:{label:'Download & Rebuild',fn:"downloadWithBuild('/api/xlsx','Workbook')"}}));
    }
    if(id==='detailed_results'){
      safeCall(()=>ctx.loadDetailedResults(false));
      if(safeCall(ctx.getDetailedResultsData)&&!safeCall(ctx.getLastBuildOk)){
        safeCall(()=>ctx.showMessage('Plan inputs changed since last build — results may be stale.','warn',{persistent:true,action:{label:'Rebuild now',fn:'runBuild(false)'}}));
      }
    }
    safeCall(ctx.renderMain);
    setTimeout(()=>{
      try{window.scrollTo({top:0,behavior:'smooth'});}catch(_e){}
      const entries=safeCall(ctx.focusableEntries)||[];
      const first=entries.find(el=>el&&el.closest&&el.closest('#mainPane'));
      if(first&&first.focus)first.focus();
    },0);
  }

  function saveCurrentStep(ctx,fromStep){
    if(fromStep==='ytd_transactions')return ctx.saveYtdPending();
    return Promise.all([
      safeCall(ctx.getCatMapChanged)?ctx.saveCategoryMap():Promise.resolve(),
      safeCall(ctx.getRulesChanged)?ctx.saveMappingRulesData():Promise.resolve(),
      safeCall(ctx.getTaxBudgetChanged)?ctx.saveTaxonomyBudgetData():Promise.resolve(),
      safeCall(ctx.getBudgetLinesChanged)?ctx.saveBudgetLines():Promise.resolve()
    ]);
  }

  function exposeGlobals(ctx){
    window.setStep=function(id){return ctx.setStep(id)};
    window.toggleAdvanced=ctx.toggleAdvanced||noop;
    window.showStepHelp=ctx.showStepHelp||noop;
    window.setLanguageMode=ctx.setLanguageMode||noop;
    window.jumpRecommendationSource=ctx.jumpRecommendationSource||noop;
    window.planningCaseCreate=ctx.planningCaseCreate||noop;
    window.planningCaseDelete=ctx.planningCaseDelete||noop;
    window.planningCaseArchive=ctx.planningCaseArchive||noop;
    window.planningCaseAdopt=ctx.planningCaseAdopt||noop;
    window.setPlanningCaseActive=ctx.setPlanningCaseActive||noop;
    window.setDetailedResultSheet=ctx.setDetailedResultSheet||noop;
    window.setDetailedResultsNavOpen=ctx.setDetailedResultsNavOpen||noop;
    window.loadDetailedResults=ctx.loadDetailedResults||noop;
    window.loadDetailedResultSheet=ctx.loadDetailedResultSheet||noop;
    window.toggleDetailColumnGroup=ctx.toggleDetailColumnGroup||noop;
    window.setAllDetailColumnGroups=ctx.setAllDetailColumnGroups||noop;
    window.setDetailColGroupOpen=function(key,open){
      if(ctx.setDetailColGroupOpen)return ctx.setDetailColGroupOpen(key,open);
    };
  }

  function wireStepNavigation(ctx){
    ctx=ctx||{};
    if(window.__retirementStepNavWired){exposeGlobals(ctx);return;}
    window.__retirementStepNavWired=true;
    document.addEventListener('click',function(e){
      const detail=e.target&&e.target.closest?e.target.closest('[data-detail-sheet]'):null;
      if(detail&&!detail.disabled){
        e.preventDefault();
        safeCall(()=>ctx.setDetailedResultSheet(detail.getAttribute('data-detail-sheet')));
        return;
      }
      const target=e.target&&e.target.closest?e.target.closest('[data-step-id]'):null;
      if(!target||target.disabled)return;
      e.preventDefault();
      const fromStep=safeCall(ctx.getActiveStep)||'';
      const targetStep=target.getAttribute('data-step-id');
      if(AUTOSAVE_STEPS.includes(fromStep)){
        saveCurrentStep(ctx,fromStep).then(function(){
          safeCall(()=>ctx.showMessage('Auto-saved.','success'));
          ctx.setStep(targetStep);
        }).catch(function(err){
          safeCall(()=>ctx.showMessage('Auto-save failed — correct the error before leaving this step. ('+((err&&err.message)||String(err))+')','error'));
        });
      }else if(safeCall(ctx.hasUnsavedPlanChanges)){
        const doConfirm=ctx.confirm||function(m){return Promise.resolve(window.confirm(m))};
        doConfirm('You have unsaved changes. Leave this step?',{title:'Unsaved Changes',confirmLabel:'Leave Step',cancelLabel:'Stay'}).then(function(ok){if(ok)ctx.setStep(targetStep)});
      }else{
        ctx.setStep(targetStep);
      }
    });
    exposeGlobals(ctx);
  }

  function renderNav(ctx){
    ctx=ctx||{};
    const visible=(safeCall(ctx.visibleSteps)||[]);
    const active=safeCall(ctx.getActiveStep)||'';
    const idx=visible.findIndex(s=>s.id===active);
    const prev=visible[Math.max(0,idx-1)]||visible[0]||{id:'start'};
    const next=visible[Math.min(visible.length-1,idx+1)]||visible[visible.length-1]||{id:'review'};
    return `<div class="nav-actions"><button class="btn" type="button" ${idx<=0?'disabled':''} data-step-id="${prev.id}">&larr; Previous</button><div><button class="btn" type="button" onclick="showStepHelp(activeStep)">Step Help</button> <button class="btn primary" type="button" ${idx>=visible.length-1?'disabled':''} data-step-id="${next.id}">Next →</button></div></div>`;
  }

  function updateSearchToggle(ctx){
    ctx=ctx||{};
    const scope=safeCall(ctx.getSearchScope)||'page';
    const el=document.getElementById('combinedSearch');
    if(el){
      el.value=scope==='nav'?(safeCall(ctx.getNavSearchText)||''):(safeCall(ctx.getSearchText)||'');
      el.placeholder=scope==='nav'?'Search navigation...':'Search this page...';
    }
    document.querySelectorAll('[data-search-scope]').forEach(b=>b.classList.toggle('primary',b.dataset.searchScope===scope));
  }

  function setNavSearch(ctx,q){safeCall(()=>ctx.setNavSearchText(q));safeCall(ctx.renderSteps);}
  function setSearchScope(ctx,scope){
    const nextScope=scope==='page'?'page':'nav';
    safeCall(()=>ctx.setSearchScope(nextScope));
    updateSearchToggle(ctx);
    if(nextScope==='page')safeCall(ctx.renderMain);else safeCall(ctx.renderSteps);
  }
  function setCombinedSearch(ctx,q){
    if((safeCall(ctx.getSearchScope)||'page')==='nav'){
      safeCall(()=>ctx.setNavSearchText(q));safeCall(ctx.renderSteps);
    }else{
      safeCall(()=>ctx.setSearchText(q));safeCall(ctx.renderMain);
    }
    updateSearchToggle(ctx);
  }
  function focusableEntries(){
    return Array.from(document.querySelectorAll('.field input,.field select,.lot-table input,.lot-table select,.matrix-table input,.pane-actions button:not(:disabled),.nav-actions button:not(:disabled),header button:not(:disabled)')).filter(el=>!el.classList.contains('helpbtn')&&!el.disabled&&el.offsetParent!==null);
  }

  window.RetirementNavigation={
    AUTOSAVE_STEPS,
    PLAN_INDEPENDENT_STEPS,
    setStep,
    wireStepNavigation,
    renderNav,
    setNavSearch,
    updateSearchToggle,
    setSearchScope,
    setCombinedSearch,
    focusableEntries
  };
})();
