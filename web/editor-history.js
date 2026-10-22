/* In-memory, per-document edit history. Saving is still explicit. */
(() => {
  const editor = document.querySelector('#transcript');
  if (!editor) return;
  const bar = document.createElement('span');
  bar.className = 'editor-history';
  bar.innerHTML = '<button type="button" class="soft" id="undoTranscriptBtn" title="撤销（Ctrl+Z）" aria-label="撤销修订" disabled><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 4 3 9l5 5M3 9h10a7 7 0 0 1 0 14"/></svg></button><button type="button" class="soft" id="redoTranscriptBtn" title="重做（Ctrl+Y / Ctrl+Shift+Z）" aria-label="重做修订" disabled><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m16 4 5 5-5 5M21 9H11a7 7 0 0 0 0 14"/></svg></button>';
  document.querySelector('.editor-ai-split').before(bar);
  const style = document.createElement('style');
  style.textContent = '.editor-history{display:inline-flex;gap:4px;align-items:center}.editor-history button{width:36px;height:36px;min-width:36px;padding:7px!important;border-radius:8px!important}.editor-history svg{width:21px;height:21px;fill:none;stroke:currentColor;stroke-width:1.6;stroke-linecap:round;stroke-linejoin:round}.editor-history button:disabled{opacity:.35;cursor:default}.editor-history button:not(:disabled):hover{background:#e7f4f2;color:#008f89}';
  document.head.append(style);
  const undo = bar.querySelector('#undoTranscriptBtn'), redo = bar.querySelector('#redoTranscriptBtn');
  let owner = null, states = [], index = -1, restoring = false, opening = 0, composing = false;
  let lastTime = 0, lastType = '', before = null;
  const snapshot = () => ({html: editor.innerHTML, accepted: [...pendingAccepted]});
  const sync = () => {
    undo.disabled = !selected || opening > 0 || index <= 0;
    redo.disabled = !selected || opening > 0 || index >= states.length - 1;
  };
  function reset() {
    owner = selected; states = [snapshot()]; index = 0; lastTime = 0; lastType = ''; sync();
  }
  function record(type = '') {
    if (restoring || opening) return;
    if (owner !== selected || index < 0) { reset(); return; }
    const state = snapshot();
    if (states[index].html === state.html) return;
    const now = Date.now();
    const group = index > 0 && index === states.length - 1 && now-lastTime < 650 &&
      type === lastType && ['insertText','deleteContentBackward','deleteContentForward'].includes(type);
    states = states.slice(0, index + 1);
    if (group) states[index] = state;
    else { states.push(state); index++; }
    if (states.length > 100) { states.shift(); index--; }
    lastTime = now; lastType = type; sync();
  }
  function restore(delta) {
    if (composing || opening || owner !== selected) return;
    const next = index + delta;
    if (next < 0 || next >= states.length) return;
    restoring = true;
    index = next; editor.innerHTML = states[index].html;
    pendingAccepted.clear(); states[index].accepted.forEach(id => pendingAccepted.add(id));
    editor.querySelectorAll('[data-accept-change]').forEach(button => {
      button.onclick = () => acceptTranscriptChange(button);
    });
    updateAcceptAllButton();
    editor.focus();
    const range = document.createRange(); range.selectNodeContents(editor); range.collapse(false);
    const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range);
    editor.dispatchEvent(new Event('input', {bubbles:true}));
    restoring = false; lastTime = 0; lastType = ''; sync();
  }
  undo.onmousedown = redo.onmousedown = event => event.preventDefault();
  undo.onclick = () => restore(-1); redo.onclick = () => restore(1);
  editor.addEventListener('beforeinput', event => {
    if (event.inputType === 'historyUndo' || event.inputType === 'historyRedo') {
      event.preventDefault(); restore(event.inputType === 'historyUndo' ? -1 : 1);
    } else before = event.inputType;
  });
  editor.addEventListener('input', event => { if (!composing) record(event.inputType || before || ''); });
  editor.addEventListener('compositionstart', () => { composing = true; lastTime = 0; });
  editor.addEventListener('compositionend', () => { composing = false; record('composition'); });
  editor.addEventListener('keydown', event => {
    if (event.isComposing || composing || !(event.ctrlKey || event.metaKey) || event.altKey) return;
    const key = event.key.toLowerCase();
    if (key === 'z' || key === 'y') { event.preventDefault(); restore(key === 'y' || event.shiftKey ? 1 : -1); }
  });
  const render = renderTranscript;
  renderTranscript = function(...args) {
    const result = render(...args);
    if (opening || owner !== selected || index < 0) reset(); else record('replace');
    return result;
  };
  const open = openProject;
  openProject = async function(...args) {
    opening++; sync();
    try { return await open(...args); }
    finally { opening--; reset(); }
  };
  reset();
})();
