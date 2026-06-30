(function(){
  function decimalTrim(text){
    return String(text).replace(/\.0+$/,'').replace(/(\.\d*?)0+$/,'$1');
  }

  function numberFromDisplay(value){
    const raw=String(value??'').trim();
    if(!raw)return null;
    const neg=/^\(.*\)$/.test(raw)||/^\s*-/.test(raw);
    const cleaned=raw.replace(/[,$%\s]/g,'').replace(/[()]/g,'');
    const n=Number(cleaned);
    if(!Number.isFinite(n))return null;
    return neg?-Math.abs(n):n;
  }

  function formatNumberValue(value,maxDecimals=2,minDecimals=0){
    const n=numberFromDisplay(value);
    if(n===null)return String(value??'');
    const opts={useGrouping:false,minimumFractionDigits:minDecimals,maximumFractionDigits:maxDecimals};
    return n.toLocaleString(undefined,opts);
  }

  function currencyDisplay(value){
    const n=numberFromDisplay(value);
    if(n===null)return String(value??'');
    const opts={minimumFractionDigits:Number.isInteger(n)?0:2,maximumFractionDigits:2};
    return (n<0?'-':'')+'$'+Math.abs(n).toLocaleString(undefined,opts);
  }

  function percentDisplay(value,decimals=0){
    const n=numberFromDisplay(value);
    if(n===null)return String(value??'');
    const d=Math.max(0,Math.min(6,Number(decimals)||0));
    return n.toLocaleString(undefined,{minimumFractionDigits:d,maximumFractionDigits:d})+'%';
  }

  window.RPDashboardUtils={
    decimalTrim,
    numberFromDisplay,
    formatNumberValue,
    currencyDisplay,
    percentDisplay,
  };
})();
