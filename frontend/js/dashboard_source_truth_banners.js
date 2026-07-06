(function(){
  'use strict';
  const SOURCE_TRUTH_STEPS={
    plan_data_report:'Authoritative source: saved SQLite local plan. This page is a printable review packet, not an editing surface.',
    all_assumptions:'Authoritative source: saved SQLite local plan rows. CSV/JSON/YAML files are portable adapters and backups.',
    holdings:'Authoritative source: SQLite client_holdings.csv adapter. Broker CSV imports are staged previews until Save Changes.',
    ytd_transactions:'Authoritative source: SQLite YTD transaction table. CSV imports are previewed before they replace or append rows.',
    spending_dashboard:'Authoritative source: SQLite spending taxonomy, budget, and YTD transactions. Spending Analysis is the sync checkpoint before Build.',
    spending_core:'Authoritative source: guided spending categories in SQLite. Detail pages may seed or override category budget lines.',
    system_configuration:'Authoritative source: local SQLite plan plus system_config.csv for runtime settings. Advanced CSV files are maintenance adapters.',
    review:'Authoritative source: saved SQLite plan. Build outputs are snapshots and are advisor-ready only after a current build.',
    build_impact:'Authoritative source: last successful build snapshot. Rebuild after edits before relying on advisor-ready language.',
    detailed_results:'Authoritative source: generated Results Explorer model and workbook artifacts from the last build snapshot.'
  };
  const SPENDING_STEPS=['spending_core','ytd_transactions','spending_dashboard','review'];
  const GLOSSARY={
    PTI:'Post-tax inheritance: estimated amount available to heirs after modeled income, capital-gain, and estate taxes.',
    IRMAA:'Income-Related Monthly Adjustment Amount: Medicare premium surcharge triggered by higher MAGI.',
    MAGI:'Modified Adjusted Gross Income: tax income measure used for Medicare IRMAA and other thresholds.',
    RMD:'Required Minimum Distribution: mandatory tax-deferred account withdrawals after the applicable starting age.',
    QDRO:'Qualified Domestic Relations Order: court order that divides retirement assets in divorce.',
    LTC:'Long-term care: late-life support costs such as facility, in-home, or assisted-care expenses.',
    COLA:'Cost-of-living adjustment: inflation-linked increase such as Social Security COLA.',
    ACA:'Affordable Care Act marketplace coverage, often used for pre-Medicare bridge health insurance.',
    HSA:'Health Savings Account: tax-advantaged healthcare savings account.',
    HELOC:'Home equity line of credit: borrowing capacity secured by home equity.',
    Roth:'After-tax retirement account type that can reduce future taxable distributions.',
    Monte:'Monte Carlo simulation: repeated random return paths used to estimate plan resilience.'
  };
  const MODULE_MANIFEST={
    schema:'dashboard_phase3_module_manifest_v1',
    extracted_modules:['plan_state_build','detailed_results','navigation','spending','holdings','strategy','settings'],
    active_overlay:'roadmap_steps_1_11',
    public_hooks:['renderMain','showStepHelp','setStep','saveAll','runBuild']
  };
  window.RPDashboardRoadmap11=Object.assign({},window.RPDashboardRoadmap11||{}, {manifest:MODULE_MANIFEST, glossary:GLOSSARY});

  function escHtml(value){return String(value==null?'':value).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
  function currentStep(){try{return activeStep||'start';}catch(_e){return 'start';}}
  function byId(id){return document.getElementById(id);}
  function mainPane(){return byId('mainPane');}
  function safeRows(){try{return Array.isArray(rows)?rows:[];}catch(_e){return [];}}
  function visibleStepIds(){try{return visibleSteps().map(function(s){return s.id;});}catch(_e){return [];}}
  function callStep(id){try{setStep(id);}catch(_e){}}

  function sourceTruthHtml(step){
    const text=SOURCE_TRUTH_STEPS[step];
    if(!text)return '';
    return '<div class="source-truth-label" data-roadmap11="source-of-truth"><b>Source of truth:</b> '+escHtml(text)+'</div>';
  }
  function insertAfterPaneHead(html,marker){
    const pane=mainPane(); if(!pane||!html||pane.querySelector('[data-roadmap11="'+marker+'"]'))return;
    const head=pane.querySelector('.pane-head');
    if(head){head.insertAdjacentHTML('afterend',html);}else{pane.insertAdjacentHTML('afterbegin',html);}
  }

  function spendingFlowHtml(step){
    if(!SPENDING_STEPS.includes(step))return '';
    const labels=[['spending_core','Categories'],['ytd_transactions','Transactions'],['spending_dashboard','Spending Analysis'],['review','Sync / Build']];
    let html='<div class="spending-flow-guide" data-roadmap11="spending-flow"><div><b>Recommended spending flow</b><span>Categories → Transactions → Spending Analysis → Sync Actual Rate → Build</span></div><div class="spending-flow-buttons">';
    labels.forEach(function(pair){html+='<button type="button" class="btn '+(pair[0]===step?'primary':'')+'" data-step-id="'+pair[0]+'">'+pair[1]+'</button>';});
    html+='</div></div>';
    return html;
  }

  function reviewCloseoutHtml(step){
    if(step!=='start'&&step!=='review')return '';
    if(document.querySelector('.review-closeout'))return '';
    // Don't show when no plan is loaded — no data to close out
    try{if(!planLoaded)return '';}catch(_e){return '';}
    let reason='';
    try{reason=localStorage.getItem('retirement.first_run.skip_reason.v1')||'';}catch(_e){}
    // Find first incomplete workflow step so button goes to data entry, not straight to R&R
    const WORKFLOW_ITEMS=[
      {steps:['household_people','household_timing'],next:'household_people'},
      {steps:['income_work','income_retirement'],next:'income_work'},
      {steps:['spending_core','retirement_wellness','spending_mortgage_events','spending_travel','spending_travel_extras','ytd_transactions','spending_dashboard'],next:'spending_core'},
      {steps:['holdings','assets_home_cash','insurance_ltc','annuity_death_benefits','assets_special','estate'],next:'holdings'},
      {steps:['planning_levers','roth_conversion','allocation_assets','allocation_policy','withdrawal_strategy','state_residency','heloc_strategy','entity_charitable'],next:'distribution_strategy'},
      {steps:['monte_carlo_options','scenarios','survivor_stress','ltc_stress','divorce_options'],next:'monte_carlo_options'},
    ];
    let firstIncompleteStep='reports_and_review';
    try{
      for(var i=0;i<WORKFLOW_ITEMS.length;i++){
        const st=checklistItemStatus(WORKFLOW_ITEMS[i].steps);
        if(st.cls!=='done'){firstIncompleteStep=WORKFLOW_ITEMS[i].next;break;}
      }
    }catch(_e){}
    const btnLabel=firstIncompleteStep==='reports_and_review'?'Review and Build':'Continue Data Entry';
    return '<div class="first-run-closeout" data-roadmap11="first-run-closeout"><b>First-run closeout</b><span>Required sections should be complete before advisor-ready reports. Optional skips should include a reason.</span><label class="small">Optional skip reason <input id="firstRunSkipReason" value="'+escHtml(reason)+'" placeholder="Example: LTC quote pending" oninput="window.RPDashboardRoadmap11.saveSkipReason(this.value)"></label><button type="button" class="btn primary" data-step-id="'+escHtml(firstIncompleteStep)+'">'+escHtml(btnLabel)+'</button></div>';
  }

  function recommendationsHtml(step){
    const recs=[];
    if(step==='state_residency'){
      recs.push(['Review residency timing','State tax assumptions can change lifetime tax, estate exposure, and Roth conversion headroom.','state_residency']);
      recs.push(['Model a move as a scenario','Use Scenarios for temporary or future state changes instead of overwriting the base plan.','scenarios']);
    }
    if(step==='withdrawal_strategy'){
      recs.push(['Check taxable bridge capacity','Withdrawal order can create or close Roth-conversion windows before RMDs begin.','withdrawal_strategy']);
      recs.push(['Coordinate with IRMAA guardrails','Sequencing, Roth conversions, and Medicare thresholds should be reviewed together.','roth_conversion']);
    }
    if(!recs.length)return '';
    let html='<div class="page-recommendations roadmap11-recommendations" data-roadmap11="expanded-recommendations"><h3>Recommendations to review</h3>';
    recs.forEach(function(r){html+='<div class="recommendation-card"><b>'+escHtml(r[0])+'</b><p>'+escHtml(r[1])+'</p><button type="button" class="btn" data-step-id="'+escHtml(r[2])+'">Open source input</button></div>';});
    html+='</div>';
    return html;
  }

  function planDataPreviewHtml(step){
    if(step!=='plan_data_report')return '';
    return '<div class="plan-data-preview-tools" data-roadmap11="plan-data-preview"><b>Plan Data Summary preview</b><span>Print or save this input packet as PDF before sharing it.</span><button type="button" class="btn primary" onclick="window.print()">Print / Save PDF</button><button type="button" class="btn" onclick="window.RPDashboardRoadmap11.expandPrintableSections()">Expand all sections</button></div>';
  }

  function detailedResultsEnhancements(step){
    if(step!=='detailed_results')return '';
    return '<div class="detail-readability-tools" data-roadmap11="detail-readability"><b>Workbook readability</b><span>Use sheet search, summaries, and quick jumps to inspect important rows before sending reports.</span><input id="roadmap11DetailJumpSearch" class="search" placeholder="Jump to row text…" oninput="window.RPDashboardRoadmap11.filterDetailJump(this.value)"><div id="roadmap11DetailJumps" class="detail-jump-list"></div></div>';
  }

  function addStaleAdvisorNotice(){
    const step=currentStep();
    if(!['review','build_impact','detailed_results'].includes(step))return;
    let stale=false;
    try{stale=!lastBuildOk&&hasUnsavedPlanChanges&&hasUnsavedPlanChanges();}catch(_e){}
    if(!stale)return;
    insertAfterPaneHead('<div class="advisor-ready-disabled" data-roadmap11="stale-advisor"><b>Advisor-ready disabled:</b> plan inputs changed after the last successful build. Save and rebuild before treating reports as final.</div>','stale-advisor');
  }

  function decorateGlossary(root){
    if(!root)return;
    Object.keys(GLOSSARY).forEach(function(term){
      const selector='h1,h2,h3,p,li,span,small,td,th,button,label,summary';
      root.querySelectorAll(selector).forEach(function(el){
        if(el.children.length>3||el.closest('script,style,input,select,textarea'))return;
        const text=el.textContent||'';
        if(text.indexOf(term)>=0 && !el.getAttribute('title'))el.setAttribute('title',GLOSSARY[term]);
      });
    });
  }

  function buildDetailJumpList(){
    const step=currentStep(); if(step!=='detailed_results')return;
    const box=byId('roadmap11DetailJumps'); if(!box)return;
    // Only scan tbody data rows — thead rows are headers and produce garbled text
    const rows=Array.from(document.querySelectorAll('#mainPane table tbody tr')).slice(0,300);
    const picks=[];
    rows.forEach(function(tr,idx){
      const cells=Array.from(tr.querySelectorAll('td'));
      if(!cells.length)return;
      const fullText=(tr.textContent||'').replace(/\s+/g,' ').trim();
      if(!fullText)return;
      const isKeyRow=/terminal|tax|roth|success|probability|net worth|cash flow|risk|warning|retire|social security/i.test(fullText);
      if(!isKeyRow&&idx>=5)return;
      // Label: first 3 non-empty cell values joined with a separator
      const label=cells.slice(0,4).map(td=>(td.textContent||'').trim()).filter(Boolean).slice(0,3).join(' · ');
      if(!label)return;
      if(!tr.id)tr.id='detail-row-jump-'+idx;
      picks.push({id:tr.id,label:label});
    });
    if(!picks.length){box.innerHTML='<span class="small">Open a result sheet to see key-row jumps.</span>';return;}
    box.innerHTML=picks.slice(0,10).map(function(p){return '<a class="detail-jump" href="#'+escHtml(p.id)+'">'+escHtml(p.label)+'</a>';}).join('');
  }

  function filterDetailJump(q){
    q=String(q||'').toLowerCase();
    document.querySelectorAll('#roadmap11DetailJumps .detail-jump').forEach(function(a){
      a.style.display=(!q||a.textContent.toLowerCase().indexOf(q)>=0)?'inline-flex':'none';
    });
  }

  function applyEnhancements(){
    const step=currentStep();
    insertAfterPaneHead(sourceTruthHtml(step),'source-of-truth');
    insertAfterPaneHead(spendingFlowHtml(step),'spending-flow');
    insertAfterPaneHead(reviewCloseoutHtml(step),'first-run-closeout');
    insertAfterPaneHead(recommendationsHtml(step),'expanded-recommendations');
    insertAfterPaneHead(planDataPreviewHtml(step),'plan-data-preview');
    insertAfterPaneHead(detailedResultsEnhancements(step),'detail-readability');
    addStaleAdvisorNotice();
    decorateGlossary(mainPane());
    decorateGlossary(byId('helpPanel'));
    buildDetailJumpList();
  }

  function installShortcuts(){
    if(window.__rpRoadmap11ShortcutsInstalled)return;
    window.__rpRoadmap11ShortcutsInstalled=true;
    document.addEventListener('keydown',function(e){
      const tag=(e.target&&e.target.tagName||'').toLowerCase();
      const typing=['input','textarea','select'].includes(tag);
      if((e.ctrlKey||e.metaKey)&&String(e.key).toLowerCase()==='s'){e.preventDefault();try{saveAll(true);}catch(_e){};return;}
      if((e.ctrlKey||e.metaKey)&&String(e.key).toLowerCase()==='b'){e.preventDefault();try{runBuild(false);}catch(_e){};return;}
      if((e.ctrlKey||e.metaKey)&&String(e.key).toLowerCase()==='k'){e.preventDefault();const s=byId('combinedSearch');if(s){s.focus();s.select();}return;}
      if((e.ctrlKey||e.metaKey)&&e.shiftKey&&String(e.key).toLowerCase()==='r'){e.preventDefault();callStep('review');return;}
      if(typing)return;
      if(e.altKey&&(e.key==='ArrowRight'||e.key==='ArrowLeft')){
        e.preventDefault();const ids=visibleStepIds();const cur=currentStep();const i=Math.max(0,ids.indexOf(cur));const next=ids[Math.max(0,Math.min(ids.length-1,i+(e.key==='ArrowRight'?1:-1)))];if(next)callStep(next);
      }
    });
  }

  function saveSkipReason(value){try{localStorage.setItem('retirement.first_run.skip_reason.v1',String(value||''));}catch(_e){}}
  function expandPrintableSections(){document.querySelectorAll('#mainPane details').forEach(function(d){d.open=true;});}

  try{
    const oldRenderMain=renderMain;
    renderMain=function(){oldRenderMain();applyEnhancements();};
  }catch(_e){}
  try{
    const oldShowStepHelp=showStepHelp;
    showStepHelp=function(id){oldShowStepHelp(id);decorateGlossary(byId('helpPanel'));};
  }catch(_e){}

  window.RPDashboardRoadmap11.saveSkipReason=saveSkipReason;
  window.RPDashboardRoadmap11.expandPrintableSections=expandPrintableSections;
  window.RPDashboardRoadmap11.filterDetailJump=filterDetailJump;
  installShortcuts();
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',applyEnhancements);else setTimeout(applyEnhancements,0);
})();
