// Extracted from dashboard.js by tools/js_codemod/extract_module.mjs.

export function captureMainPaneFocus(mainPane) {
  const prevActive = document.activeElement;
  const focusKey =
    prevActive &&
    prevActive.getAttribute &&
    mainPane &&
    mainPane.contains(prevActive)
      ? prevActive.getAttribute("data-focus-key")
      : null;
  if (!focusKey) return null;
  let focusValue, focusSelStart, focusSelEnd;
  let hasSel = false;
  focusValue = "value" in prevActive ? prevActive.value : undefined;
  try {
    if (typeof prevActive.selectionStart === "number") {
      focusSelStart = prevActive.selectionStart;
      focusSelEnd = prevActive.selectionEnd;
      hasSel = true;
    }
  } catch (e) {
    // Some input types (e.g. type=number) throw reading selectionStart --
    // treat that as "no selection to restore", not an error.
  }
  return { focusKey, focusValue, focusSelStart, focusSelEnd, hasSel };
}

export function restoreMainPaneFocus(state) {
  if (!state) return;
  const revived = document.querySelector(
    `[data-focus-key="${CSS.escape(state.focusKey)}"]`,
  );
  if (!revived) return;
  revived.focus({ preventScroll: true });
  // Restore a caret/selection only when the value round-tripped identical --
  // otherwise a stale selection range would clobber a fresh server-provided
  // value with a leftover caret position.
  if ("value" in revived && revived.value === state.focusValue) {
    if (state.hasSel) {
      try {
        revived.setSelectionRange(state.focusSelStart, state.focusSelEnd);
      } catch (e) {
        if (typeof revived.select === "function") {
          try {
            revived.select();
          } catch (e2) {}
        }
      }
    } else if (typeof revived.select === "function") {
      try {
        revived.select();
      } catch (e2) {}
    }
  }
}

// Every export above is also re-attached to window: dashboard.js calls these
// as bare globals, and this file's own rendered HTML uses inline
// onclick="..." handlers, which always resolve through window regardless of
// module scoping. New code should prefer `import` from this module; this
// bridge exists only for callers that cannot move to import in the same pass.
Object.assign(window, {
  captureMainPaneFocus,
  restoreMainPaneFocus,
});
