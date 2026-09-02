/* navigation.js: feature-owned navigation behavior for the retirement dashboard. */
(function(){
  'use strict';
  // #204/#205: autosave-on-navigate is now the default persistence model for every
  // data-entry step. Steps deliberately excluded (read-only/build-gated reports,
  // scenario/stress-test previews that don't touch the saved plan, and
  // plan-independent/admin pages) stay on the explicit-save + 3-way guard below.
  const AUTOSAVE_STEPS=['household_people','income_work','income_retirement','lifestyle_spending','spending_core','spending_setup','retirement_wellness','spending_mortgage_events','ytd_transactions','holdings','assets_home_cash','annuity_death_benefits','assets_special','estate','distribution_strategy','state_residency','special_strategies','economic_tax_assumptions','optional_functions','all_assumptions'];
  const PLAN_INDEPENDENT_STEPS=['start','system_configuration','workbook_formatting','detailed_results','planning_workbench','reports_and_review'];
  // #301: Reports & Review is primarily the Impact page now -- Downloads and
  // Plan Data Review no longer have their own tabs (folded into Impact as
  // action buttons / collapsible sections), so jump-links to those step ids
  // land on Impact too rather than a tab that no longer exists.
  const REPORTS_REDIRECTS={
    detailed_results:'Results',
    build_impact:'Impact',
    review:'Impact',
    plan_data_report:'Impact'
  };
  const STEP_REDIRECTS={
    spending_travel:'lifestyle_spending',
    spending_travel_extras:'lifestyle_spending',
    ss_timing:'income_retirement',
    timing_tax:'state_residency',
    heloc_strategy:'special_strategies',
    entity_charitable:'special_strategies',
    withdrawal_strategy:'distribution_strategy',
    allocation_policy:'distribution_strategy',
    investment_strategy:'distribution_strategy'
  };

  function noop(){}
  function safeCall(fn){try{return typeof fn==='function'?fn():undefined}catch(_e){return undefined}}

  // #296: an in-app Back/Forward history, independent of browser history (this
  // app is a single page with no URL routing). Tracks the resolved step id --
  // the same value ctx.setActiveStep() receives -- so Back/Forward retraces
  // exactly the pages the user actually saw, not raw pre-redirect step ids.
  let historyStack=[];
  let historyIndex=-1;
  function pushHistory(id){
    if(historyIndex>=0&&historyStack[historyIndex]===id)return;
    historyStack=historyStack.slice(0,historyIndex+1);
    historyStack.push(id);
    historyIndex=historyStack.length-1;
  }
  function canGoBack(){return historyIndex>0;}
  function canGoForward(){return historyIndex<historyStack.length-1;}
  function updateHistoryNavButtons(){
    const back=document.getElementById('navBackBtn');
    if(back)back.disabled=!canGoBack();
    const fwd=document.getElementById('navForwardBtn');
    if(fwd)fwd.disabled=!canGoForward();
  }
  function goBackInHistory(ctx){
    if(!canGoBack())return;
    historyIndex--;
    setStep(ctx,historyStack[historyIndex],{skipHistory:true});
  }
  function goForwardInHistory(ctx){
    if(!canGoForward())return;
    historyIndex++;
    setStep(ctx,historyStack[historyIndex],{skipHistory:true});
  }

  function setStep(ctx,id,opts){
    ctx=ctx||{};
    opts=opts||{};
    const planLoaded=!!safeCall(ctx.getPlanLoaded);
    if(REPORTS_REDIRECTS[id]){
      safeCall(()=>ctx.setReportsTab(REPORTS_REDIRECTS[id]));
      id='reports_and_review';
    }else if(STEP_REDIRECTS[id]){
      id=STEP_REDIRECTS[id];
    }
    if(!planLoaded&&!PLAN_INDEPENDENT_STEPS.includes(id)){
      safeCall(()=>ctx.setActiveStep('start'));
      if(!opts.skipHistory)pushHistory('start');
      updateHistoryNavButtons();
      safeCall(ctx.renderMain);
      setTimeout(()=>{try{window.scrollTo({top:0,behavior:'smooth'});}catch(_e){}},0);
      return;
    }
    safeCall(()=>ctx.setActiveStep(id));
    if(!opts.skipHistory)pushHistory(id);
    updateHistoryNavButtons();
    updateSaveModeBadge(id,planLoaded);
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
    const scrollAndFocus=()=>setTimeout(()=>{
      try{window.scrollTo({top:0,behavior:'smooth'});}catch(_e){}
      const entries=safeCall(ctx.focusableEntries)||[];
      const first=entries.find(el=>el&&el.closest&&el.closest('#mainPane'));
      if(first&&first.focus)first.focus();
    },0);
    if(id==='all_assumptions'){
      // #222: showing the overlay then immediately running the expensive
      // synchronous renderMain() on the same tick never gave the browser a
      // chance to paint the overlay first -- the page just froze for several
      // seconds with no visible progress bar. Yield one tick so it paints.
      safeCall(()=>setBuildOverlay(true,'Loading all assumptions','Aggregating all plan fields across sections. This takes a moment.','waiting'));
      setTimeout(()=>{
        safeCall(ctx.renderMain);
        setTimeout(()=>safeCall(hideBuildOverlay),50);
        scrollAndFocus();
      },20);
      return;
    }
    safeCall(ctx.renderMain);
    scrollAndFocus();
  }

  // #204: saveWorkingCopy() is the same universal save the header "Save Changes"
  // button uses (plain field edits, holdings, liabilities, travel/liquidity/forced
  // conversions, YTD, category rules, tax budget, budget lines). Autosave-on-navigate
  // reuses it so every data-entry step persists the same way, instead of a bespoke
  // per-page save function that only some pages could go through.
  function saveCurrentStep(ctx,fromStep){
    return ctx.saveWorkingCopy?ctx.saveWorkingCopy():Promise.resolve(true);
  }

  function exposeGlobals(ctx){
    window.setStep=function(id){return ctx.setStep(id)};
    window.navigateHistoryBack=function(){goBackInHistory(ctx)};
    window.navigateHistoryForward=function(){goForwardInHistory(ctx)};
    window.showStepHelp=ctx.showStepHelp||noop;
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
    pushHistory(safeCall(ctx.getActiveStep)||'start');
    updateHistoryNavButtons();
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
        Promise.resolve(saveCurrentStep(ctx,fromStep)).then(function(result){
          if(result===false){
            safeCall(()=>ctx.showMessage('Fix the highlighted error before leaving this step.','error'));
            return;
          }
          safeCall(()=>ctx.showMessage('Auto-saved.','success'));
          ctx.setStep(targetStep);
        }).catch(function(err){
          safeCall(()=>ctx.showMessage('Auto-save failed — correct the error before leaving this step. ('+((err&&err.message)||String(err))+')','error'));
        });
      }else if(safeCall(ctx.hasUnsavedPlanChanges)){
        // #205: pages kept on the explicit-save model (e.g. system settings) still
        // get a real 3-way Save/Discard/Stay choice instead of a binary confirm.
        const decide=ctx.confirmSaveDiscardStay||function(m){return Promise.resolve(window.confirm(m)?'discard':'stay')};
        decide('You have unsaved changes on this page. Save them before leaving, discard them, or stay?',{title:'Unsaved Changes'}).then(function(choice){
          if(choice==='save'){
            Promise.resolve(safeCall(ctx.saveAll)?ctx.saveAll(true):true).then(function(ok){
              if(ok!==false)ctx.setStep(targetStep);
            });
          }else if(choice==='discard'){
            ctx.setStep(targetStep);
          }
        });
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
  // #223: Page-scope search re-renders the whole main pane (Field Finder's
  // "all_assumptions" page alone groups/sorts/labels 600+ rows) -- doing that
  // synchronously on every keystroke is what made typing feel laggy. Debounce
  // the expensive render; the native input itself never blocked on its own.
  let _combinedSearchTimer=null;
  function setCombinedSearch(ctx,q){
    clearTimeout(_combinedSearchTimer);
    const scope=(safeCall(ctx.getSearchScope)||'page');
    _combinedSearchTimer=setTimeout(()=>{
      if(scope==='nav'){
        safeCall(()=>ctx.setNavSearchText(q));safeCall(ctx.renderSteps);
      }else{
        safeCall(()=>ctx.setSearchText(q));safeCall(ctx.renderMain);
      }
    },150);
    updateSearchToggle(ctx);
  }
  // Which persistence model the CURRENT step uses, shown before the user acts.
  //
  // Autosave-on-navigate covers 20 of ~30 steps and reports itself only AFTER
  // the fact, via an "Auto-saved." toast once you have already clicked away.
  // Every other step instead raises a blocking Save/Discard/Stay prompt. The
  // header renders the same Save button and the same "Unsaved changes" pill in
  // both cases, so nothing distinguished them until it was too late to matter.
  // The risk is confusion and misplaced trust rather than data loss -- both
  // models do persist -- which is why this is a small always-visible label
  // rather than a change to the save architecture itself.
  function updateSaveModeBadge(stepId,planLoaded){
    const el=document.getElementById('saveModeBadge');
    if(!el)return;
    if(!planLoaded||PLAN_INDEPENDENT_STEPS.includes(stepId)){
      el.classList.add('hidden');
      el.textContent='';
      el.removeAttribute('title');
      return;
    }
    const auto=AUTOSAVE_STEPS.includes(stepId);
    el.textContent=auto?'Saves automatically':'Save required';
    el.title=auto
      ?'Your edits on this page are saved when you move to another page.'
      :'Use Save Changes to keep your edits on this page. You will be asked before leaving with unsaved changes.';
    el.classList.toggle('auto',auto);
    el.classList.toggle('manual',!auto);
    el.classList.remove('hidden');
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
    focusableEntries,
    updateSaveModeBadge
  };
})();
