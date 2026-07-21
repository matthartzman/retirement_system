from .workbook_common import (
    FINAL_SHEET_RENAMES,
    PRICE_CACHE,
    datetime,
    fetch_price,
    price_source,
)
from .workbook_xml_optimizer import optimize_workbook_xml


def post_save_patch(out_path):
    """Apply optional workbook XML optimizations.

    The implementation lives in workbook_xml_optimizer.py; this function only
    preserves the existing call site used by the build orchestrator.
    """
    return optimize_workbook_xml(out_path)


def _chart_dashboard_html(*, years, nw_labels, inc_labels, exp_labels, nw_ser, inc_ser,
                          exp_ser, nw_colors, inc_colors, exp_colors, holdings,
                          cf_ymax, c, today, prices_str):
    """Return a fully self-contained HTML dashboard.

    The old dashboard depended on CDN-hosted Chart.js and Google Fonts.  That
    broke charts in locked-down/offline environments and made the report look
    like it had external workbook/chart links.  This dashboard renders native
    inline SVG from JSON data, so the generated HTML has no external chart or
    font dependency.
    """
    import json

    data_script = "\n".join([
        "const YEARS=" + json.dumps(years) + ";",
        "const NW_D=" + json.dumps([nw_ser[l] for l in nw_labels]) + ";",
        "const INC_D=" + json.dumps([inc_ser[l] for l in inc_labels]) + ";",
        "const EXP_D=" + json.dumps([exp_ser[l] for l in exp_labels]) + ";",
        "const NW_L=" + json.dumps(nw_labels) + ";",
        "const INC_L=" + json.dumps(inc_labels) + ";",
        "const EXP_L=" + json.dumps(exp_labels) + ";",
        "const NW_C=" + json.dumps(nw_colors) + ";",
        "const INC_C=" + json.dumps(inc_colors) + ";",
        "const EXP_C=" + json.dumps(exp_colors) + ";",
        "const HOLD=" + json.dumps(holdings) + ";",
        "const CF_YMAX=" + json.dumps(cf_ymax) + ";",
    ])

    html = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>__COUPLE__ — Retirement Plan Dashboard</title>
<style>
:root{--navy:#1F3864;--blue:#2E75B6;--gold:#C9A84C;--green:#2D6A4F;--teal:#1B7A9E;
      --coral:#C55A11;--red:#9B2335;--smoke:#F4F5F7;--rule:#DDE1E9;--ink:#1A1E2C;
      --muted:#6B7280;--white:#FFFFFF;}
*{box-sizing:border-box;margin:0;padding:0;}
body{font-family:"DM Sans","Aptos","Segoe UI",Arial,sans-serif;background:var(--smoke);color:var(--ink);font-size:14px;line-height:1.6;}
.masthead{background:var(--navy);padding:40px 48px 32px;position:relative;overflow:hidden;}
.masthead::after{content:'';position:absolute;bottom:0;left:0;right:0;height:4px;
  background:linear-gradient(90deg,var(--gold) 0%,var(--blue) 60%,transparent 100%);}
.masthead-inner{max-width:1400px;margin:0 auto;}
.masthead h1{font-family:Georgia,"Times New Roman",serif;font-size:28px;font-weight:700;color:var(--white);margin-bottom:4px;}
.masthead-sub{font-size:13px;color:rgba(255,255,255,.6);font-weight:300;letter-spacing:.04em;text-transform:uppercase;}
.masthead-meta{margin-top:20px;display:flex;gap:16px;flex-wrap:wrap;}
.meta-chip{background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.14);border-radius:6px;padding:8px 16px;}
.meta-chip .label{font-size:10px;text-transform:uppercase;letter-spacing:.1em;color:rgba(255,255,255,.45);display:block;margin-bottom:2px;}
.meta-chip .val{font-size:15px;font-weight:600;color:var(--white);}
.page{max-width:1400px;margin:0 auto;padding:0 24px 64px;}
.section-label{font-family:Georgia,"Times New Roman",serif;font-size:11px;letter-spacing:.16em;text-transform:uppercase;
  color:var(--muted);margin:44px 0 18px;display:flex;align-items:center;gap:12px;}
.section-label::after{content:'';flex:1;height:1px;background:var(--rule);}
.chart-card{background:var(--white);border-radius:12px;border:1px solid var(--rule);
  padding:28px 32px 24px;margin-bottom:40px;box-shadow:0 1px 4px rgba(0,0,0,.04);}
.chart-title{font-family:Georgia,"Times New Roman",serif;font-size:26px;font-weight:700;color:var(--navy);margin-bottom:4px;}
.chart-subtitle{font-size:12px;color:var(--muted);font-weight:300;margin-bottom:20px;}
.chart-body{display:flex;gap:28px;align-items:flex-start;}
.chart-wrap{flex:1 1 0;position:relative;min-width:0;}
.native-chart{width:100%;min-height:340px;}
.native-chart svg{display:block;width:100%;height:auto;overflow:visible;}
.chart-bar rect{shape-rendering:geometricPrecision;}
.chart-axis,.chart-grid{stroke:var(--rule);stroke-width:1;}
.chart-grid{opacity:.8;}
.chart-tick{font-size:10.5px;fill:var(--muted);}
.chart-year{font-size:10px;fill:var(--ink);}
.chart-tooltip{position:fixed;z-index:20;max-width:260px;padding:9px 10px;border-radius:8px;
  background:rgba(26,30,44,.94);color:#fff;font-size:11px;line-height:1.4;pointer-events:none;
  box-shadow:0 8px 20px rgba(0,0,0,.18);display:none;}
.chart-legend{flex:0 0 210px;display:flex;flex-direction:column;gap:5px;padding-top:4px;
  max-height:340px;overflow-y:auto;}
.legend-item{display:flex;align-items:center;gap:8px;font-size:11.5px;color:var(--muted);}
.legend-dot{width:11px;height:11px;border-radius:2px;flex-shrink:0;}
.summary-bar{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
  gap:1px;background:var(--rule);border-radius:10px;overflow:hidden;border:1px solid var(--rule);margin-bottom:24px;}
.sum-cell{background:var(--white);padding:16px 18px;}
.sum-cell .lbl{font-size:10.5px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin-bottom:4px;}
.sum-cell .val{font-family:Georgia,"Times New Roman",serif;font-size:20px;font-weight:700;color:var(--navy);}
.sum-cell .sub{font-size:11px;color:var(--muted);margin-top:2px;}
.holdings-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:20px;}
.acct-card{background:var(--white);border-radius:10px;border:1px solid var(--rule);overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.04);}
.acct-hdr{padding:14px 18px;display:flex;justify-content:space-between;align-items:baseline;}
.acct-name{font-weight:600;font-size:13px;color:var(--white);}
.acct-type{font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:rgba(255,255,255,.65);}
.acct-total{font-size:15px;font-weight:700;color:var(--white);}
.col-hdr{display:grid;grid-template-columns:52px 1fr 72px 72px 60px;
  padding:7px 18px;background:var(--smoke);border-bottom:1px solid var(--rule);}
.col-hdr span{font-size:10px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);font-weight:500;text-align:right;}
.col-hdr span:first-child,.col-hdr span:nth-child(2){text-align:left;}
.pos-row{display:grid;grid-template-columns:52px 1fr 72px 72px 60px;
  padding:9px 18px;border-bottom:1px solid var(--smoke);align-items:center;}
.pos-row:last-child{border-bottom:none;}
.pos-row:hover{background:var(--smoke);}
.pos-sym{font-weight:600;font-size:12px;color:var(--navy);}
.pos-sym.cash{color:var(--muted);font-weight:400;}
.pos-lbl{font-size:11px;color:var(--muted);}
.pos-num{font-size:12px;text-align:right;color:var(--ink);}
.type-pretax{background:#C55A11;}.type-roth{background:#2D6A4F;}
.type-taxable{background:#3D5A80;}.type-hsa{background:#1B7A9E;}.type-cash{background:#595959;}
.footer{text-align:center;padding:24px;font-size:11px;color:var(--muted);
  border-top:1px solid var(--rule);margin-top:32px;}
@media(max-width:900px){.chart-body{display:block}.chart-legend{max-height:none;flex:auto;margin-top:10px}.masthead{padding:28px 24px}.chart-card{padding:20px}.col-hdr,.pos-row{grid-template-columns:52px 1fr 66px 66px 58px}}
@media print{body{background:white}.chart-card,.acct-card{box-shadow:none;break-inside:avoid}.masthead{print-color-adjust:exact;-webkit-print-color-adjust:exact}}
</style>
</head>
<body>
<div class="masthead"><div class="masthead-inner">
  <h1>__COUPLE__ — Retirement Plan Dashboard</h1>
  <p class="masthead-sub">Institutional Retirement, Tax &amp; Estate Plan · __STATE__ · __PLAN_START__–__PLAN_END__</p>
  <div class="masthead-meta">
    <div class="meta-chip"><span class="label">Plan Horizon</span><span class="val">__PLAN_START__–__PLAN_END__</span></div>
    <div class="meta-chip"><span class="label">Net Worth · End __PLAN_START__</span><span class="val">__NW_START__</span></div>
    <div class="meta-chip"><span class="label">Terminal Net Worth</span><span class="val">__NW_END__</span></div>
    <div class="meta-chip"><span class="label">Lifetime Tax</span><span class="val">__LIFETIME_TAX__</span></div>
    <div class="meta-chip"><span class="label">SS Claim Age</span><span class="val">__SS_CLAIM__</span></div>
    <div class="meta-chip"><span class="label">Built</span><span class="val">__TODAY__</span></div>
  </div>
</div></div>

<div class="page">
<p class="section-label">Snapshot · End of __PLAN_START__ (projected)</p>
<div class="summary-bar">
  <div class="sum-cell"><div class="lbl">Pre-Tax (IRA/401k)</div><div class="val">__SNAP_PRETAX__</div><div class="sub">End of __PLAN_START__</div></div>
  <div class="sum-cell"><div class="lbl">Roth Accounts</div><div class="val">__SNAP_ROTH__</div><div class="sub">Tax-free</div></div>
  <div class="sum-cell"><div class="lbl">Trust Accounts</div><div class="val">__SNAP_TRUST__</div><div class="sub">Taxable</div></div>
  <div class="sum-cell"><div class="lbl">Annuities &amp; Pension</div><div class="val">__SNAP_ANN__</div><div class="sub">PV of future income</div></div>
  <div class="sum-cell"><div class="lbl">Other Assets</div><div class="val">__SNAP_OTHER__</div><div class="sub">Home, other, cash</div></div>
  <div class="sum-cell"><div class="lbl">HSA</div><div class="val">__SNAP_HSA__</div><div class="sub">Triple tax-adv</div></div>
</div>

<p class="section-label">Net Worth Trajectory · __PLAN_START__–__PLAN_END__</p>
<div class="chart-card">
  <div class="chart-title">Net Worth by Component</div>
  <div class="chart-subtitle">Stacked by account type · end-of-year balances · offline native SVG</div>
  <div class="chart-body"><div class="chart-wrap"><div id="nwChart" class="native-chart" role="img" aria-label="Net worth by component chart"></div></div>
  <div class="chart-legend" id="nwLegend"></div></div>
</div>

<p class="section-label">Cash Flow — Income &amp; Portfolio Draws · __PLAN_START__–__PLAN_END__</p>
<div class="chart-card">
  <div class="chart-title">Annual Income by Source</div>
  <div class="chart-subtitle">Income streams + portfolio draws · surplus = gap above expense chart bars</div>
  <div class="chart-body"><div class="chart-wrap"><div id="incChart" class="native-chart" role="img" aria-label="Annual income by source chart"></div></div>
  <div class="chart-legend" id="incLegend"></div></div>
</div>

<p class="section-label">Cash Flow — Spending &amp; Taxes · __PLAN_START__–__PLAN_END__</p>
<div class="chart-card">
  <div class="chart-title">Annual Outflows by Category</div>
  <div class="chart-subtitle">Spending + taxes only · surplus is the visual gap between these bars and the income bars above</div>
  <div class="chart-body"><div class="chart-wrap"><div id="expChart" class="native-chart" role="img" aria-label="Annual outflows by category chart"></div></div>
  <div class="chart-legend" id="expLegend"></div></div>
</div>

<p class="section-label">Portfolio Holdings Detail · All Positions · Live Prices __TODAY__</p>
<div class="holdings-grid" id="holdingsGrid"></div>
</div>

<div class="footer">
  Built __TODAY__ · OBBBA (One Big Beautiful Bill Act, signed July 4 2025) · __PRICES__ ·
  For informational purposes only — not financial, tax, or legal advice.
</div>
<div id="chartTooltip" class="chart-tooltip"></div>

<script>
__DATA_SCRIPT__

function fmtK(v){return '$'+Math.round(Number(v||0)/1000).toLocaleString()+'K';}
function fmtD(v){return '$'+Math.round(Number(v||0)).toLocaleString();}
const SVG_NS='http'+'://www.w3.org/2000/svg';
function svgEl(name, attrs){
  const el=document.createElementNS(SVG_NS,name);
  Object.entries(attrs||{}).forEach(([k,v])=>el.setAttribute(k,String(v)));
  return el;
}
function safeText(v){return String(v==null?'':v).replace(/[&<>]/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[ch]));}
function niceMax(v){
  v=Math.max(1, Number(v||0));
  const p=Math.pow(10, Math.floor(Math.log10(v)));
  const n=v/p;
  const step=n<=2?2:n<=5?5:10;
  return step*p;
}
function makeLegend(id,labels,colors){
  const el=document.getElementById(id); if(!el)return; el.innerHTML='';
  labels.forEach((l,i)=>{
    const d=document.createElement('div'); d.className='legend-item';
    const dot=document.createElement('span'); dot.className='legend-dot'; dot.style.background=colors[i]||'#6B7280';
    const txt=document.createElement('span'); txt.textContent=l;
    d.appendChild(dot); d.appendChild(txt); el.appendChild(d);
  });
}
function makeStackedBarSvg(containerId, labels, values, colors, forcedMax){
  const el=document.getElementById(containerId); if(!el)return;
  el.innerHTML='';
  const seriesCount=labels.length, yearCount=YEARS.length;
  const w=980,h=360,ml=74,mr=18,mt=22,mb=62,plotW=w-ml-mr,plotH=h-mt-mb;
  const totals=YEARS.map((_,i)=>values.reduce((sum,series)=>sum+Math.max(0,Number(series[i]||0)),0));
  const maxY=niceMax(forcedMax || Math.max.apply(null, totals.concat([1])));
  const svg=svgEl('svg',{viewBox:'0 0 '+w+' '+h, preserveAspectRatio:'xMidYMid meet', role:'img'});
  const tooltip=document.getElementById('chartTooltip');
  for(let t=0;t<=4;t++){
    const val=maxY*t/4;
    const y=mt+plotH-(val/maxY)*plotH;
    svg.appendChild(svgEl('line',{x1:ml,y1:y,x2:w-mr,y2:y,class:'chart-grid'}));
    const tx=svgEl('text',{x:ml-10,y:y+4,'text-anchor':'end',class:'chart-tick'}); tx.textContent=fmtK(val); svg.appendChild(tx);
  }
  svg.appendChild(svgEl('line',{x1:ml,y1:mt+plotH,x2:w-mr,y2:mt+plotH,class:'chart-axis'}));
  const gap=3;
  const barW=Math.max(3, Math.min(26, (plotW/yearCount)-gap));
  YEARS.forEach((yr,i)=>{
    const x=ml+i*(plotW/Math.max(1,yearCount-1))-barW/2;
    let yBase=mt+plotH;
    labels.forEach((label,s)=>{
      const val=Math.max(0,Number((values[s]||[])[i]||0));
      if(!val)return;
      const bh=(val/maxY)*plotH;
      const rect=svgEl('rect',{x:x,y:yBase-bh,width:barW,height:Math.max(0,bh),fill:colors[s]||'#6B7280',rx:1,ry:1,class:'chart-bar'});
      rect.addEventListener('mousemove',ev=>{
        if(!tooltip)return;
        tooltip.style.display='block';
        tooltip.style.left=(ev.clientX+12)+'px'; tooltip.style.top=(ev.clientY+12)+'px';
        tooltip.innerHTML='<b>'+safeText(yr)+'</b><br>'+safeText(label)+': '+safeText(fmtK(val))+'<br>Total: '+safeText(fmtK(totals[i]));
      });
      rect.addEventListener('mouseleave',()=>{if(tooltip)tooltip.style.display='none';});
      svg.appendChild(rect); yBase-=bh;
    });
    if(i===0 || i===yearCount-1 || i%Math.ceil(yearCount/12)===0){
      const tx=svgEl('text',{x:x+barW/2,y:h-28,'text-anchor':'middle',transform:'rotate(-45 '+(x+barW/2)+' '+(h-28)+')',class:'chart-year'});
      tx.textContent=yr; svg.appendChild(tx);
    }
  });
  el.appendChild(svg);
}
function renderAllCharts(){
  makeStackedBarSvg('nwChart', NW_L, NW_D, NW_C, null);
  makeStackedBarSvg('incChart', INC_L, INC_D, INC_C, CF_YMAX);
  makeStackedBarSvg('expChart', EXP_L, EXP_D, EXP_C, CF_YMAX);
  makeLegend('nwLegend',NW_L,NW_C); makeLegend('incLegend',INC_L,INC_C); makeLegend('expLegend',EXP_L,EXP_C);
}
function renderHoldings(){
  const TYPE_CLS={'Pre-Tax':'type-pretax','Tax-Free':'type-roth','Taxable':'type-taxable','Tax-Adv':'type-hsa','Cash':'type-cash'};
  const accounts={};
  HOLD.forEach(h=>{
    if(!accounts[h.account])accounts[h.account]={positions:[],total:0};
    accounts[h.account].positions.push(h); accounts[h.account].total+=Number(h.value||0);
  });
  const grid=document.getElementById('holdingsGrid'); if(!grid)return; grid.innerHTML='';
  Object.entries(accounts).forEach(([raw,data])=>{
    const m=raw.match(/^(.+?)\\s*·\\s*(.+?)$/); const name=m?m[1].trim():raw; const type=m?m[2].trim():''; const cls=TYPE_CLS[type]||'type-cash';
    const card=document.createElement('div'); card.className='acct-card';
    const rows=data.positions.map(p=>'<div class="pos-row"><span class="pos-sym'+(p.symbol==='CASH'?' cash':'')+'">'+safeText(p.symbol)+'</span><span class="pos-lbl">'+safeText(p.desc)+'</span><span class="pos-num">'+Number(p.shares||0).toLocaleString(undefined,{maximumFractionDigits:3})+'</span><span class="pos-num">'+fmtD(p.price).replace('$','$')+'</span><span class="pos-num">'+fmtD(p.value)+'</span></div>').join('');
    card.innerHTML='<div class="acct-hdr '+cls+'"><div><div class="acct-name">'+safeText(name)+'</div><div class="acct-type">'+safeText(type)+'</div></div><div class="acct-total">'+fmtD(data.total)+'</div></div><div class="col-hdr"><span>Symbol</span><span>Description</span><span>Shares</span><span>Price</span><span>Value</span></div><div>'+rows+'</div>';
    grid.appendChild(card);
  });
}
renderAllCharts(); renderHoldings();
</script>
</body></html>"""
    def _fmt_compact(v):
        try:
            v = float(v or 0)
        except Exception:
            return 'n/a'
        if abs(v) >= 1_000_000:
            return f'${v / 1_000_000:,.2f}M'
        return f'${v / 1_000:,.0f}K'

    def _series_year_value(labels_wanted, index):
        total = 0.0
        for label in labels_wanted:
            series = nw_ser.get(label) or []
            if index < len(series):
                total += float(series[index] or 0)
        return total

    def _esc(s):
        return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    n1 = str(c.get('h_nick') or c.get('h_name') or 'Member 1')
    n2 = str(c.get('w_nick') or c.get('w_name') or '')
    couple = f'{_esc(n1)} &amp; {_esc(n2)}' if n2 else _esc(n1)

    if years:
        nw_start = sum(float((nw_ser.get(l) or [0])[0] or 0) for l in nw_labels)
        nw_end = sum(float((nw_ser.get(l) or [0])[-1] or 0) for l in nw_labels)
        tax_labels = [l for l in exp_labels if 'Tax' in l or l == 'NIIT']
        lifetime_tax = sum(sum(float(v or 0) for v in (exp_ser.get(l) or [])) for l in tax_labels)
    else:
        nw_start = nw_end = lifetime_tax = 0.0

    h_claim = c.get('h_ss_claim_age')
    w_claim = c.get('w_ss_claim_age')
    if h_claim and w_claim and int(h_claim) == int(w_claim):
        ss_claim = f'Age {int(h_claim)}'
    elif h_claim and w_claim:
        ss_claim = f'{n1} {int(h_claim)} / {n2} {int(w_claim)}'
    else:
        ss_claim = f'Age {int(h_claim or w_claim or 70)}'

    y0 = 0  # snapshot cells show end of the first projection year
    snap = {
        '__SNAP_PRETAX__': _fmt_compact(_series_year_value(['Pre-Tax IRA/401k'], y0)),
        '__SNAP_ROTH__': _fmt_compact(_series_year_value(['Roth'], y0)),
        '__SNAP_TRUST__': _fmt_compact(_series_year_value(['Trust'], y0)),
        '__SNAP_ANN__': _fmt_compact(_series_year_value(['Annuities & Pension'], y0)),
        '__SNAP_OTHER__': _fmt_compact(_series_year_value(['Home Equity', 'Other Assets'], y0)),
        '__SNAP_HSA__': _fmt_compact(_series_year_value(['HSA'], y0)),
    }

    replacements = {
        "__PLAN_START__": str(c["plan_start"]),
        "__PLAN_END__": str(c["plan_end"]),
        "__TODAY__": str(today),
        "__PRICES__": str(prices_str),
        "__COUPLE__": couple,
        "__STATE__": str(c.get('state', '')),
        "__NW_START__": _fmt_compact(nw_start) if years else 'n/a',
        "__NW_END__": _fmt_compact(nw_end) if years else 'n/a',
        "__LIFETIME_TAX__": f'~{_fmt_compact(lifetime_tax)}' if years else 'n/a',
        "__SS_CLAIM__": ss_claim,
        **snap,
        "__DATA_SCRIPT__": data_script,
    }
    for key, value in replacements.items():
        html = html.replace(key, value)
    return html


def _find_workbook_charts_sheet(wb):
    """Return the visible workbook charts sheet across legacy and refactored names.

    The workbook refactor renamed the old `8. Charts Dashboard` tab to
    `1E. Charts` — looked up from FINAL_SHEET_RENAMES (workbook_common.py) so
    this fallback can never drift out of sync with the actual rename table.
    The HTML sidecar is generated after the workbook is saved, so it must read
    the final user-facing tab name rather than the legacy build name.  Keep
    the legacy fallback for older workbooks and tests.

    Returns ``None`` when no charts sheet exists.  That is a legitimate state,
    not an error: ``charts_dashboard`` is an optional module, and when its
    toggle is off neither the visible tab nor the hidden ``_Chart Dashboard
    Data`` helper is built.  The caller falls back to deriving the series
    straight from the projection rows, so the HTML dashboard still renders.
    """
    final_charts_name = FINAL_SHEET_RENAMES.get('8. Charts Dashboard', '1E. Charts')
    for name in (final_charts_name, '8. Charts Dashboard', 'Charts'):
        if name in wb.sheetnames:
            return wb[name]
    for ws in wb.worksheets:
        title = str(getattr(ws, 'title', '') or '')
        low = title.lower()
        if 'chart' in low and str(getattr(ws, 'sheet_state', 'visible') or 'visible') == 'visible':
            return ws
    return None


def build_html_dashboard(xlsx_path, html_path, rows, c):
    import math, openpyxl as _oxl

    wb2 = _oxl.load_workbook(xlsx_path, data_only=True)
    ws8 = _find_workbook_charts_sheet(wb2)
    # ── Pull holdings directly from positions/price cache.
    # v5.1 removed the duplicate holdings table from Sheet 3 Balance Sheet,
    # so the dashboard no longer parses holdings from that sheet.
    holdings = []
    desc_map = {'IXUS':'iShares Core MSCI Intl ex-US','ITOT':'iShares Core S&P Total US Mkt',
                'PDBC':'Commodities','AVUV':'Avantis US Small Cap Value',
                'VXUS':'Vanguard Total Intl Stock','VTI':'Vanguard Total Stock Market',
                'VBR':'Vanguard Small-Cap Value','CASH':'Cash (USD)'}
    from ..person_labels import display_account
    from ..core import ACCOUNT_TYPES, _infer_type
    _tax_type_word = {'pre_tax': 'Pre-Tax', 'roth': 'Tax-Free', 'taxable': 'Taxable',
                      'hsa': 'Tax-Adv', 'tax_free': 'Tax-Free', 'cash': 'Cash'}
    for acct, acct_holdings in c.get('positions', {}).items():
        tax = ACCOUNT_TYPES.get(_infer_type(acct), {}).get('tax', 'taxable')
        acct_display = f"{display_account(acct, c)} · {_tax_type_word.get(tax, 'Taxable')}"
        acct_total = sum(fetch_price(sym, '') * shares for sym, shares in acct_holdings.items())
        for sym, shares in acct_holdings.items():
            price = fetch_price(sym, '')
            value = price * shares
            holdings.append({
                'account': acct_display,
                'symbol': sym, 'desc': desc_map.get(sym, ''),
                'shares': round(float(shares), 3),
                'price':  round(float(price or 1), 2),
                'value':  round(float(value or 0), 2),
                'pct_acct': round(float(value / acct_total), 4) if acct_total else 0.0,
                'source': price_source(sym),
            })

    # ── Pull chart series data from the workbook chart-source table ──────────
    # v10 moved the Excel chart helper ranges off the visible "8. Charts
    # Dashboard" page and onto a hidden "_Chart Dashboard Data" sheet.  The
    # standalone HTML dashboard must read that helper sheet; otherwise YEARS=[]
    # and every native SVG chart appears blank.  Keep a row-based fallback so
    # the HTML dashboard still works if an older workbook is supplied.
    chart_data_ws = wb2['_Chart Dashboard Data'] if '_Chart Dashboard Data' in wb2.sheetnames else ws8

    def _cell_text(v):
        return str(v or '').strip()

    def _safe_number(v):
        try:
            if v is None or v == '':
                return 0
            return float(v)
        except Exception:
            return 0

    def _extract_chart_block(ws, *, year_col, first_series_col, total_col=None, max_col=None, start_row=5):
        labels = []
        stop_col = total_col or max_col or ws.max_column
        for col in range(first_series_col, stop_col):
            label = _cell_text(ws.cell(row=4, column=col).value)
            if label and not label.startswith('Σ') and 'Total' not in label:
                labels.append(label)
        yrs = []
        series = {label: [] for label in labels}
        for r in range(start_row, ws.max_row + 1):
            yr = ws.cell(row=r, column=year_col).value
            if not isinstance(yr, int):
                continue
            yrs.append(yr)
            for i, label in enumerate(labels):
                series[label].append(_safe_number(ws.cell(row=r, column=first_series_col + i).value))
        return yrs, labels, series

    # Hidden helper layout from build_sheet8: NW A:I, income K:AA, expenses AC:AM.
    if chart_data_ws is None:
        # charts_dashboard module is off — no helper sheet exists. Leave the
        # series empty so the projection-rows fallback below supplies them.
        years, nw_labels, nw_ser = [], [], {}
        inc_years, inc_labels, inc_ser = [], [], {}
        exp_years, exp_labels, exp_ser = [], [], {}
    else:
        years, nw_labels, nw_ser = _extract_chart_block(chart_data_ws, year_col=1, first_series_col=2, total_col=9)
        inc_years, inc_labels, inc_ser = _extract_chart_block(chart_data_ws, year_col=11, first_series_col=12, total_col=27)
        exp_years, exp_labels, exp_ser = _extract_chart_block(chart_data_ws, year_col=29, first_series_col=30, total_col=39)

    def _series_from_projection_rows():
        _n1 = str(c.get('h_nick') or c.get('h_name') or 'Member 1')
        _n2 = str(c.get('w_nick') or c.get('w_name') or 'Member 2')
        nw_labels_fallback = ['Annuities & Pension','Pre-Tax IRA/401k','Roth','Trust','HSA','Home Equity','Other Assets']
        inc_labels_fallback = ['Earned Income',f'{_n1} SS',f'{_n2} SS','Pension',
                               f'{_n2} Single Ann',f'{_n2} Joint Ann',f'{_n1} Single Ann',f'{_n1} Joint Ann',
                               'Note P+I','RMD','Trust Draw','HSA Draw','Roth Draw','IRA Draw','HELOC Draw']
        exp_labels_fallback = ['Base Spending','Rec Extras','Lump Events','Mortgage + RE Tax','Rent',
                               'HELOC P&I','Federal Tax',f'State Tax ({c["state"][:2]})','NIIT','Payroll Tax']
        yrs_fallback = []
        nw = {l: [] for l in nw_labels_fallback}
        inc = {l: [] for l in inc_labels_fallback}
        exp = {l: [] for l in exp_labels_fallback}
        for row in rows:
            try:
                yr = int(row.get('year'))
            except Exception:
                continue
            yrs_fallback.append(yr)
            nw_values = [
                row.get('ann_nw',0), row.get('pretax_nw',0), row.get('roth_nw',0),
                row.get('trust_nw',0), row.get('hsa_nw',0), row.get('home_equity',0),
                row.get('other_nw',0) - row.get('home_equity',0),
            ]
            inc_values = [
                row.get('earned',0), row.get('h_ss',0), row.get('w_ss',0), row.get('pension',0),
                row.get('wife_single_ann',0), row.get('wife_joint_ann',0), row.get('h_single_ann',0),
                row.get('h_joint_ann',0), row.get('note_princ',0)+row.get('note_int',0),
                row.get('rmd_total',0), max(0,row.get('trust_wd',0)), max(0,row.get('hsa_wd',0)),
                max(0,row.get('roth_wd',0)), max(0,row.get('ira_wd',0)), max(0,row.get('heloc_draw',0)),
            ]
            exp_values = [
                row.get('spend_base_yr',0), row.get('rec_extra',0), row.get('lump',0),
                row.get('mortgage',0), row.get('rent_yr',0),
                row.get('heloc_interest',0)+row.get('heloc_repayment_principal',0),
                row.get('fed_tax',0), row.get('state_tax',0), row.get('niit',0), 0,
            ]
            for label, value in zip(nw_labels_fallback, nw_values):
                nw[label].append(round(_safe_number(value)))
            for label, value in zip(inc_labels_fallback, inc_values):
                inc[label].append(round(_safe_number(value)))
            for label, value in zip(exp_labels_fallback, exp_values):
                exp[label].append(round(_safe_number(value)))
        return yrs_fallback, nw_labels_fallback, inc_labels_fallback, exp_labels_fallback, nw, inc, exp

    if not years:
        years, nw_labels, inc_labels, exp_labels, nw_ser, inc_ser, exp_ser = _series_from_projection_rows()

    cf_ymax = math.ceil(
        max(max(sum(inc_ser[l][i] for l in inc_labels) for i in range(len(years))),
            max(sum(exp_ser[l][i] for l in exp_labels) for i in range(len(years))))
        / 100000) * 100000 if years else 100000
    nw_colors  = ['#2E75B6','#C55A11','#2D6A4F','#5A3E85','#C9A84C','#16A34A','#6B7280']
    inc_colors = ['#1F3864','#2E75B6','#3D9AB8','#C9A84C','#2D6A4F','#40916C',
                   '#C55A11','#E07540','#5A3E85','#9B2335','#7B3F9E','#1B7A9E',
                   '#156041','#B85C00','#8B5E3C']
    exp_colors = ['#1F3864','#2E75B6','#C55A11','#C9A84C','#059669','#9B2335','#C5384E','#E07595','#595959']

    today = str(datetime.date.today())
    prices_str = '  ·  '.join(f'{k} ${v:.2f}' for k, v in PRICE_CACHE.items() if k != 'CASH')

    html = _chart_dashboard_html(
        years=years, nw_labels=nw_labels, inc_labels=inc_labels, exp_labels=exp_labels,
        nw_ser=nw_ser, inc_ser=inc_ser, exp_ser=exp_ser,
        nw_colors=nw_colors, inc_colors=inc_colors, exp_colors=exp_colors,
        holdings=holdings, cf_ymax=cf_ymax, c=c, today=today, prices_str=prices_str,
    )

    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'  HTML dashboard: {len(html):,} chars, {len(holdings)} positions, {len(years)} years, offline SVG charts')


__all__ = ['post_save_patch', 'build_html_dashboard']
