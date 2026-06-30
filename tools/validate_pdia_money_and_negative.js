const fs=require('fs'), vm=require('vm');
const code=fs.readFileSync('frontend/js/dashboard.js','utf8');
function makeEl(){return {classList:{toggle:()=>{},add:()=>{},remove:()=>{}},style:{},textContent:'',innerHTML:'',disabled:false,setAttribute:()=>{},getAttribute:()=>null,closest:()=>null,focus:()=>{},select:()=>{}}}
const elems={};
const ctx={console, window:{localStorage:{getItem:()=>null,setItem:()=>{}}, sessionStorage:{getItem:()=>null,setItem:()=>{}}, addEventListener:()=>{}, scrollTo:()=>{}}, document:{getElementById:(id)=>elems[id]||(elems[id]=makeEl()), querySelector:()=>null, querySelectorAll:()=>[], addEventListener:()=>{}}, setTimeout:()=>{}, clearTimeout:()=>{}, setInterval:()=>{}, clearInterval:()=>{}, fetch:()=>Promise.resolve({ok:false,status:503,text:()=>Promise.resolve('offline')})};
vm.createContext(ctx);
vm.runInContext(code + `
(()=>{
 const section={title:'WHAT-IF SCENARIO ANALYSIS'};
 const headers=[{display:'Scenario'},{display:'Assumption Change'},{display:'Ending NW'},{display:'Lifetime Tax'},{display:'Plan Survives?'},{display:'Delta vs Base'}];
 const pdia={cells:[{display:'PDIA Div 4.5%',value:'PDIA Div 4.5%'},{display:'All annuity dividends at 4.5%',value:'All annuity dividends at 4.5%'},{display:'2152780',value:2152780,kind:'number'},{display:'92780',value:92780,kind:'number'},{display:'YES',value:'YES'},{display:'-125000',value:-125000,kind:'number'}]};
 const vals=[2,3,5].map(i=>detailCellDisplay(section,pdia,i,headers));
 if(vals[0] !== '$2,153K' || vals[1] !== '$93K' || vals[2] !== '-$125K') throw new Error('PDIA scenario numbers not rendered as dollars: '+vals.join(' / '));
 const html=renderDetailedResultTable({title:'WHAT-IF SCENARIO ANALYSIS',rows:[{cells:headers},pdia]},'');
 if(!html.includes('detail-cell-currency')) throw new Error('PDIA scenario table did not classify money columns');
 if(!html.includes('negative-money')) throw new Error('Negative dollar table cell is not red-classed');
 const impact=impactCardHtml('Terminal net worth',-250000,1000000,750000,fmtMoney,'');
 if(!impact.includes('negative-money') || !impact.includes('-$250,000')) throw new Error('Impact negative dollars not red-classed: '+impact);
 console.log('PASS PDIA scenario dollar formatting and negative-money styling', vals.join(' / '));
})();`, ctx);
