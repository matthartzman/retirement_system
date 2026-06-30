/* Retirement Planner API client extraction seam.
   Dependency-free wrapper around fetch so dashboard modules can move away from
   scattered request/response parsing without a bundler. */
(function(global){
  'use strict';
  function defaultBase(){ return global.__retirementApiBase || ''; }
  function setBase(base){ global.__retirementApiBase = String(base || '').replace(/\/$/, ''); }
  function url(path){
    const p = String(path || '');
    if(/^https?:\/\//i.test(p)) return p;
    const base = defaultBase();
    return base + (p.charAt(0)==='/' ? p : '/' + p);
  }
  function normalizeHeaders(headers, method){
    const out = Object.assign({}, headers || {});
    const hasContentType = Object.keys(out).some(function(k){ return k.toLowerCase()==='content-type'; });
    if(!hasContentType) out['Content-Type'] = 'application/json';
    const token = global.__retirementCsrfToken || '';
    if(token && String(method || 'GET').toUpperCase() !== 'GET') out['X-CSRF-Token'] = token;
    return out;
  }
  async function request(path, opts){
    opts = Object.assign({}, opts || {});
    const timeoutMs = Number(opts.timeoutMs) || 0;
    delete opts.timeoutMs;
    opts.headers = normalizeHeaders(opts.headers, opts.method || 'GET');
    let timer = null;
    if(timeoutMs > 0){
      const controller = new AbortController();
      opts.signal = controller.signal;
      timer = setTimeout(function(){ controller.abort(); }, timeoutMs);
    }
    try{
      const res = await fetch(url(path), opts);
      const text = await res.text();
      let data = text;
      try{ data = JSON.parse(text); }catch(_e){}
      if(!res.ok) throw new Error((data && data.error) || text || res.statusText);
      return data;
    }catch(e){
      if(e && e.name === 'AbortError') throw new Error('Request timed out after '+Math.round(timeoutMs/1000)+' seconds.');
      throw e;
    }finally{
      if(timer) clearTimeout(timer);
    }
  }
  async function text(path, opts){
    const res = await fetch(url(path), Object.assign({cache:'no-store'}, opts || {}));
    if(!res.ok) throw new Error(await res.text());
    return await res.text();
  }
  async function ping(base, timeoutMs){
    const controller = new AbortController();
    const timer = setTimeout(function(){ controller.abort(); }, Number(timeoutMs) || 2500);
    try{ return await fetch(String(base || '').replace(/\/$/, '') + '/api/ping', {cache:'no-store', signal:controller.signal}); }
    finally{ clearTimeout(timer); }
  }
  global.RetirementApiClient = { setBase:setBase, url:url, request:request, text:text, ping:ping };
})(window);
