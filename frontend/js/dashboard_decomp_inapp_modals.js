// ── In-app confirm/prompt/dialog modals ──
// Extracted verbatim from dashboard_decomp_row_model.js (W4-06, ARC-005): the focus-trapping modal
// primitives (confirm, prompt, static dialogs, save/discard/stay). Bare-global bridge below.
export function showInAppConfirm(message, opts) {
  opts = opts || {};
  return new Promise(function (resolve) {
    const previouslyFocused = document.activeElement;
    const overlay = document.createElement("div");
    overlay.className = "inapp-modal-overlay";
    const variant = opts.variant || "";
    const title = opts.title || "Confirm";
    const confirmLabel = opts.confirmLabel || "Confirm";
    const cancelLabel = opts.cancelLabel || "Cancel";
    const bodyHtml = opts.bodyIsHtml ? message : "<p>" + esc(message) + "</p>";
    overlay.innerHTML =
      '<div class="inapp-modal' +
      (variant ? " modal-" + variant : "") +
      '" role="dialog" aria-modal="true" aria-labelledby="inapp-modal-title-' + _inAppModalIdSeq + '"><b class="inapp-modal-title" id="inapp-modal-title-' + _inAppModalIdSeq++ + '">' +
      esc(title) +
      '</b><div class="inapp-modal-body">' +
      bodyHtml +
      '</div><div class="inapp-modal-actions"><button class="btn inapp-cancel" type="button">' +
      esc(cancelLabel) +
      '</button><button class="btn primary inapp-confirm" type="button">' +
      esc(confirmLabel) +
      "</button></div></div>";
    document.body.appendChild(overlay);
    function close(v) {
      overlay.remove();
      document.removeEventListener("keydown", onKey);
      if (previouslyFocused && typeof previouslyFocused.focus === "function") previouslyFocused.focus();
      resolve(v);
    }
    overlay.querySelector(".inapp-confirm").onclick = function () {
      close(true);
    };
    overlay.querySelector(".inapp-cancel").onclick = function () {
      close(false);
    };
    overlay.onclick = function (e) {
      if (e.target === overlay) close(false);
    };
    function onKey(e) {
      if (e.key === "Escape") {
        close(false);
        return;
      }
      if (e.key === "Tab") _trapTabWithinModal(e, overlay);
    }
    document.addEventListener("keydown", onKey);
    setTimeout(function () {
      const b = overlay.querySelector(".inapp-cancel");
      if (b) b.focus();
    }, 30);
  });
}
let _inAppModalIdSeq = 0;
function _trapTabWithinModal(e, overlay) {
  const focusable = overlay.querySelectorAll(
    'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
  );
  if (!focusable.length) return;
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (e.shiftKey && document.activeElement === first) {
    e.preventDefault();
    last.focus();
  } else if (!e.shiftKey && document.activeElement === last) {
    e.preventDefault();
    first.focus();
  }
}

// UX-004 (system review 2026-09-25, WI-502): the static dialogs declared in
// index.html (#exitModal, #chartModal) carry role=dialog/aria-modal but used
// to be opened/closed by toggling style.display alone -- no focus move, no
// Tab trap, no Escape, no focus restore. These two helpers give them the
// same behaviour showInAppConfirm/showSaveDiscardStayModal already have.
//   opts.display       CSS display value to show with (default "flex")
//   opts.initialFocus  selector (inside modal) for the safe default button
//   opts.onEscape      called on Escape (default: closeStaticDialog(modal))
export function openStaticDialog(modal, opts) {
  if (!modal) return;
  opts = opts || {};
  if (modal.__staticDialog) closeStaticDialog(modal, { restoreFocus: false });
  const opener = document.activeElement;
  function onKey(e) {
    if (e.key === "Escape") {
      e.preventDefault();
      if (typeof opts.onEscape === "function") opts.onEscape();
      else closeStaticDialog(modal);
      return;
    }
    if (e.key === "Tab") _trapTabWithinModal(e, modal);
  }
  modal.__staticDialog = { opener: opener, onKey: onKey };
  modal.style.display = opts.display || "flex";
  document.addEventListener("keydown", onKey);
  const target =
    (opts.initialFocus && modal.querySelector(opts.initialFocus)) ||
    modal.querySelector(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
    );
  if (target && typeof target.focus === "function") target.focus();
}

export function closeStaticDialog(modal, opts) {
  if (!modal) return;
  const state = modal.__staticDialog;
  modal.style.display = "none";
  if (!state) return;
  modal.__staticDialog = null;
  document.removeEventListener("keydown", state.onKey);
  if (
    !(opts && opts.restoreFocus === false) &&
    state.opener &&
    typeof state.opener.focus === "function"
  )
    state.opener.focus();
}

export function showSaveDiscardStayModal(message, opts) {
  opts = opts || {};
  return new Promise(function (resolve) {
    const previouslyFocused = document.activeElement;
    const overlay = document.createElement("div");
    overlay.className = "inapp-modal-overlay";
    const title = opts.title || "Unsaved Changes";
    const bodyHtml = opts.bodyIsHtml ? message : "<p>" + esc(message) + "</p>";
    overlay.innerHTML =
      '<div class="inapp-modal modal-warn" role="dialog" aria-modal="true" aria-labelledby="inapp-modal-title-' + _inAppModalIdSeq + '"><b class="inapp-modal-title" id="inapp-modal-title-' + _inAppModalIdSeq++ + '">' +
      esc(title) +
      '</b><div class="inapp-modal-body">' +
      bodyHtml +
      '</div><div class="inapp-modal-actions"><button class="btn sds-stay" type="button">Stay</button> <button class="btn warn sds-discard" type="button">Discard changes</button> <button class="btn primary sds-save" type="button">Save &amp; leave</button></div></div>';
    document.body.appendChild(overlay);
    function close(v) {
      overlay.remove();
      document.removeEventListener("keydown", onKey);
      if (previouslyFocused && typeof previouslyFocused.focus === "function") previouslyFocused.focus();
      resolve(v);
    }
    overlay.querySelector(".sds-save").onclick = function () {
      close("save");
    };
    overlay.querySelector(".sds-discard").onclick = function () {
      close("discard");
    };
    overlay.querySelector(".sds-stay").onclick = function () {
      close("stay");
    };
    overlay.onclick = function (e) {
      if (e.target === overlay) close("stay");
    };
    function onKey(e) {
      if (e.key === "Escape") {
        close("stay");
        return;
      }
      if (e.key === "Tab") _trapTabWithinModal(e, overlay);
    }
    document.addEventListener("keydown", onKey);
    setTimeout(function () {
      const b = overlay.querySelector(".sds-stay");
      if (b) b.focus();
    }, 30);
  });
}

// UX-010 / WI-020: same dialog pattern as showInAppConfirm (role=dialog, aria-modal, labelled,
// Tab trap, Escape, focus restored). opts.choices = [string | {value,label}] turns the free-text
// box into a <select> for enumerated values (state, trust type); the result is then always one of them.
export function showInAppPrompt(message, defaultValue, opts) {
  defaultValue = defaultValue || "";
  opts = opts || {};
  return new Promise(function (resolve) {
    const previouslyFocused = document.activeElement;
    const overlay = document.createElement("div");
    overlay.className = "inapp-modal-overlay";
    const title = opts.title || message;
    const placeholder = opts.placeholder || "";
    const seq = _inAppModalIdSeq++;
    const titleId = "inapp-modal-title-" + seq;
    const labelId = "inapp-modal-label-" + seq;
    const inputId = "inapp-modal-input-" + seq;
    const showLabel = !!message && message !== title;
    const labelledBy = titleId + (showLabel ? " " + labelId : "");
    const choices = Array.isArray(opts.choices) ? opts.choices : null;
    const control = choices
      ? '<select class="inapp-modal-input compact-input" id="' +
        inputId +
        '" aria-labelledby="' +
        labelledBy +
        '">' +
        choices
          .map(function (c) {
            const v = typeof c === "object" ? c.value : c;
            const l = typeof c === "object" ? c.label || c.value : c;
            return (
              '<option value="' + esc(v) + '"' + (String(v) === String(defaultValue) ? " selected" : "") + ">" + esc(l) + "</option>"
            );
          })
          .join("") +
        "</select>"
      : '<input class="inapp-modal-input compact-input" id="' +
        inputId +
        '" type="text" aria-labelledby="' +
        labelledBy +
        '" value="' +
        esc(defaultValue) +
        '" placeholder="' +
        esc(placeholder) +
        '">';
    overlay.innerHTML =
      '<div class="inapp-modal" role="dialog" aria-modal="true" aria-labelledby="' +
      titleId +
      '"><b class="inapp-modal-title" id="' +
      titleId +
      '">' +
      esc(title) +
      '</b><div class="inapp-modal-body">' +
      (showLabel ? '<label class="inapp-modal-label" id="' + labelId + '" for="' + inputId + '">' + esc(message) + "</label>" : "") +
      control +
      '</div><div class="inapp-modal-actions"><button class="btn inapp-cancel" type="button">Cancel</button><button class="btn primary inapp-confirm" type="button">OK</button></div></div>';
    document.body.appendChild(overlay);
    const input = overlay.querySelector(".inapp-modal-input");
    function close(v) {
      overlay.remove();
      document.removeEventListener("keydown", onKey);
      if (previouslyFocused && typeof previouslyFocused.focus === "function") previouslyFocused.focus();
      resolve(v);
    }
    function accept() {
      close(String(input.value || "").trim() || null);
    }
    overlay.querySelector(".inapp-confirm").onclick = accept;
    overlay.querySelector(".inapp-cancel").onclick = function () {
      close(null);
    };
    overlay.onclick = function (e) {
      if (e.target === overlay) close(null);
    };
    function onKey(e) {
      if (e.key === "Escape") close(null);
      else if (e.key === "Enter" && document.activeElement === input) {
        if (e.preventDefault) e.preventDefault();
        accept();
      } else if (e.key === "Tab") _trapTabWithinModal(e, overlay);
    }
    document.addEventListener("keydown", onKey);
    setTimeout(function () {
      if (input && input.focus) input.focus();
      if (!choices && input && input.select) input.select();
    }, 30);
  });
}
Object.assign(window, {
  closeStaticDialog, openStaticDialog, showInAppConfirm, showInAppPrompt, showSaveDiscardStayModal,
});
