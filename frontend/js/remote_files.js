/* Remote mode file flows (multi-user Phase 5): browser download/upload in place of desktop file dialogs.
   Plan files: GET /api/plan/download, POST /api/plan/upload. Monarch CSVs: POST /api/monarch/upload (dry run,
   then confirmed import; account names shown exactly as the API masks them). Reached only when
   RetirementRemote.enabled. SEAM: a future "Connect Monarch" button belongs in monarchUploadCardHtml(). */
(function (global) {
  'use strict';
  const doc = global.document;
  const MAX_PLAN_BYTES = 47 * 1024 * 1024;   // 64 MiB JSON body cap, base64 adds a third
  const MAX_MONARCH_BYTES = 12 * 1024 * 1024; // the API refuses 16 MiB of file; base64 must fit its body cap
  const msg = (t, kind) => (global.showMessage || console.log)(t, kind);
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const client = () => global.RetirementApiClient;
  let pending = { transactions: null, balances: null }, shown = { transactions: '', balances: '' };

  function readBase64(file) {
    return new Promise(function (resolve, reject) {
      const fr = new global.FileReader();
      fr.onload = () => resolve(String(fr.result).split(',', 2)[1] || '');
      fr.onerror = () => reject(new Error('Could not read the file.'));
      fr.readAsDataURL(file);
    });
  }
  function pickFile(accept) {
    return new Promise(function (resolve) {
      const inp = doc.createElement('input');
      inp.type = 'file';
      inp.accept = accept;
      inp.onchange = () => resolve(inp.files && inp.files[0] ? inp.files[0] : null);
      inp.click();
    });
  }
  function tooBig(file, limit) {
    if (file.size <= limit) return false;
    msg('That file is ' + Math.round(file.size / 1048576) + ' MB; the limit is ' + Math.floor(limit / 1048576) + ' MB.', 'error');
    return true;
  }

  async function downloadPlan() {
    try {
      if (global.hasUnsavedPlanChanges && global.hasUnsavedPlanChanges() && !(await global.saveWorkingCopy())) {
        return msg('Could not save current changes first. Plan file not downloaded.', 'error');
      }
      const res = await global.fetch('/api/plan/download', { cache: 'no-store' });
      if (!res.ok) throw new Error(((await res.json().catch(() => ({}))) || {}).error || 'Download failed.');
      const cd = res.headers.get('Content-Disposition') || '';
      const name = (/filename="?([^";]+)"?/.exec(cd) || [])[1] || 'myplan.rpx';
      const url = global.URL.createObjectURL(await res.blob());
      const a = doc.createElement('a');
      a.href = url;
      a.download = name;
      doc.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => global.URL.revokeObjectURL(url), 10000);
      msg('Plan file downloaded: ' + name);
    } catch (e) { msg('Download failed: ' + e.message, 'error'); }
  }

  // mode "open": a new plan from the file, made active. mode "restore": replaces the active plan's contents.
  async function uploadPlan(mode) {
    const restore = mode === 'restore';
    if (global.hasUnsavedPlanChanges && global.hasUnsavedPlanChanges()) {
      const choice = await global.showSaveDiscardStayModal('You have unsaved changes. Save them, discard them, or stay here?', { title: 'Upload plan file' });
      if (choice === 'stay') return;
      if (choice === 'save' && !(await global.saveAll(true))) return;
    }
    const ok = await global.showInAppConfirm(restore
      ? 'This replaces the contents of your current plan with the chosen file. A backup of the current plan is kept.'
      : 'This opens the chosen plan file as a new plan and makes it the active plan. Your current plan is not changed.',
    { title: restore ? 'Restore plan from file' : 'Upload plan file', confirmLabel: restore ? 'Choose file' : 'Choose file', variant: 'warn' });
    if (!ok) return;
    const file = await pickFile('.rpx,application/octet-stream');
    if (!file || tooBig(file, MAX_PLAN_BYTES)) return;
    try {
      const out = await client().request('/api/plan/upload', { method: 'POST',
        body: JSON.stringify({ filename: file.name, mode: restore ? 'restore' : 'open', content_base64: await readBase64(file) }) });
      if (!out || out.success === false) throw new Error((out && out.error) || 'Upload failed.');
      msg(restore ? 'Plan restored from ' + file.name : 'Plan loaded from ' + file.name);
      await global.loadAll({ source: 'Loaded from file', preferLocal: false });
      if (global.refreshPlanSwitcher) global.refreshPlanSwitcher();
      global.renderMain();
    } catch (e) { msg('Upload failed: ' + e.message, 'error'); }
  }

  // ---- Monarch CSV upload: dry run, show the masked result, then confirm ----
  function resultHtml(kind, r) {
    if (!r) return '';
    const names = (r.account_names || []).map(esc).join(', ');
    const range = (r.date_range || []).join(' to ');
    const count = r.rows_read != null ? r.rows_read : r.rows;
    return '<p class="small" data-kind="state" role="status"><b>' + (r.dry_run ? 'Preview (nothing imported yet)' : 'Imported') + ':</b> ' + esc(count) + ' rows, ' +
      esc(r.accounts) + ' accounts' + (range ? ', ' + esc(range) : '') + '.' +
      (r.added != null && !r.dry_run ? ' Added ' + esc(r.added) + ', updated ' + esc(r.updated) + ', skipped ' + esc(r.skipped) + '.' : '') +
      (names ? '<br>Accounts: ' + names : '') + '</p>' +
      (r.dry_run ? '<button class="btn primary" type="button" onclick="event.stopPropagation();confirmMonarchUpload(\'' + kind + '\')">Import ' + esc(count) + ' rows</button>' : '');
  }
  function monarchUploadCardHtml() {
    const box = (kind, label, help) => '<div data-monarch-upload="' + kind + '"><b>' + label + '</b><p class="small" data-kind="state">' + help + '</p>' +
      '<button class="btn" type="button" onclick="event.stopPropagation();chooseMonarchUpload(\'' + kind + '\')">Choose ' + label.toLowerCase() + ' file</button>' +
      '<div id="monarchUpload_' + kind + '">' + shown[kind] + '</div></div>';
    return '<div class="feature-card monarch-upload-card" tabindex="0"><h3>Monarch import</h3><p class="small" data-kind="state">Each file is checked first; nothing imports until you confirm.</p>' +
      box('transactions', 'Transactions', 'Monarch: Transactions, Download CSV.') +
      box('balances', 'Balances', 'Monarch: balance history export.') +
      '<!-- SEAM: Connect Monarch button goes here once the connector exists. --></div>';
  }
  function show(kind, html) {
    shown[kind] = html;
    const el = doc.getElementById('monarchUpload_' + kind);
    if (el) el.innerHTML = html;
  }
  async function send(kind, dry) {
    const p = pending[kind];
    return client().request('/api/monarch/upload', { method: 'POST',
      body: JSON.stringify({ kind: kind, filename: p.name, content_base64: p.b64, dry_run: dry }) });
  }
  async function chooseMonarchUpload(kind) {
    const file = await pickFile('.csv,text/csv');
    if (!file || tooBig(file, MAX_MONARCH_BYTES)) return;
    try {
      pending[kind] = { name: file.name, b64: await readBase64(file) };
      show(kind, '<p class="small" data-kind="state">Checking ' + esc(file.name) + '...</p>');
      show(kind, resultHtml(kind, await send(kind, true)));
    } catch (e) {
      pending[kind] = null;
      show(kind, '<p class="small" role="alert" data-kind="warn">' + esc(e.message) + '</p>');
    }
  }
  async function confirmMonarchUpload(kind) {
    if (!pending[kind]) return;
    try {
      show(kind, '<p class="small" data-kind="state">Importing...</p>');
      const out = await send(kind, false);
      pending[kind] = null;
      show(kind, resultHtml(kind, out));
      msg('Monarch ' + kind + ' imported.', 'success');
      if (global.markBuildStale) global.markBuildStale();
    } catch (e) { show(kind, '<p class="small" role="alert" data-kind="warn">' + esc(e.message) + '</p>'); }
  }

  const R = global.RetirementRemote || (global.RetirementRemote = {});
  Object.assign(R, { downloadPlan, uploadPlan, monarchUploadCardHtml });
  Object.assign(global, { chooseMonarchUpload, confirmMonarchUpload });
})(window);
