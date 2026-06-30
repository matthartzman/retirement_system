const fs=require('fs'), vm=require('vm');
const code=fs.readFileSync('frontend/js/dashboard.js','utf8');
function makeEl(){return {classList:{toggle:()=>{},add:()=>{},remove:()=>{}},style:{},textContent:'',innerHTML:'',disabled:false,setAttribute:()=>{},getAttribute:()=>null,closest:()=>null,focus:()=>{},select:()=>{}}}
const elems={};
const ctx={console, window:{localStorage:{getItem:()=>null,setItem:()=>{}}, sessionStorage:{getItem:()=>null,setItem:()=>{}}, addEventListener:()=>{}, scrollTo:()=>{}}, document:{getElementById:(id)=>elems[id]||(elems[id]=makeEl()), querySelector:()=>null, querySelectorAll:()=>[], addEventListener:()=>{}}, setTimeout:()=>{}, clearTimeout:()=>{}, setInterval:()=>{}, clearInterval:()=>{}, fetch:()=>Promise.resolve({ok:false,status:503,text:()=>Promise.resolve('offline')})};
vm.createContext(ctx);
const rows = [
 {row_index:1, section:'Other Assets', subsection:'Home', label:'value_as_of_plan_start', value:'1000000', units:'USD', schema:{type:'dollars'}},
 {row_index:2, section:'Other Assets', subsection:'Home', label:'home_basis', value:'1000000', units:'USD', schema:{type:'dollars'}},
 {row_index:3, section:'Other Assets', subsection:'Home', label:'home_sale_year', value:'0', units:'year', schema:{type:'year'}},
 {row_index:4, section:'Scenarios', subsection:'Sell Home', label:'home_sale_year', value:'2040', units:'year', schema:{type:'year'}},
 {row_index:5, section:'Scenarios', subsection:'Sell Home', label:'home_sale_price', value:'790000', units:'USD', schema:{type:'dollars'}},
 {row_index:6, section:'Scenarios', subsection:'Sell Home', label:'home_basis', value:'790000', units:'USD', schema:{type:'dollars'}},
 {row_index:7, section:'Scenarios', subsection:'Sell Home', label:'monthly_rent_post_sale', value:'5000', units:'USD', schema:{type:'dollars'}},
 {row_index:8, section:'Scenarios', subsection:'Economy', label:'high_inflation_pct', value:'8', units:'%', schema:{type:'percent'}},
];
vm.runInContext(code + `
(()=>{
rows=${JSON.stringify(rows)}; planLoaded=true; activeStep='scenarios'; serverOnline=false;
renderMain();
const html=document.getElementById('mainPane').innerHTML;
if (html.includes('$790,000') || html.includes('Home Sale Price')) throw new Error('Scenario UI still shows retired scenario sale-price duplicate: '+html);
if (!html.includes('$1,000,000')) throw new Error('Scenario UI did not show canonical Home Value/Basis');
if (html.includes('retired value ignored')) throw new Error('Retired scenario duplicate rows should not be shown even as inactive values');
const section={title:'Sell Home Scenario Detail'};
const priceRow={cells:[{value:'Projected Sale Price',display:'Projected Sale Price',kind:'text'},{value:1512589.72,display:'1512589.72',kind:'number'}]};
const basisRow={cells:[{value:'Cost Basis (purchase + improvements)',display:'Cost Basis (purchase + improvements)',kind:'text'},{value:1000000,display:'1000000',kind:'number'}]};
const price=detailCellDisplay(section,priceRow,1,[]);
const basis=detailCellDisplay(section,basisRow,1,[]);
if (!price.startsWith('$') || !basis.startsWith('$')) throw new Error('Scenario detail money cells are not formatted as currency: '+price+' / '+basis);
console.log('PASS scenario UI and detailed-result formatting checks', price, basis);

})();`, ctx);
