// A visual view of the existing memo, not a separate AI analysis.
(() => {
  let showing = false;
  const button = document.createElement('button');
  button.type = 'button'; button.className = 'soft'; button.textContent = '结构图';button.id='memoStructureModeBtn';
  button.setAttribute('aria-pressed', 'false');
  $('#saveMemoBtn').before(button);
  const diagram = document.createElement('div');
  diagram.id = 'memoStructure'; diagram.hidden = true;
  $('#memoWorkspace').append(diagram);
  const grid = $('#memoWorkspace .memo-grid');

  function draw() {
    const memo = analysisData?.familiarity_memo;
    if (!memo) {
      diagram.innerHTML = '<div class="memo-empty">请先生成访谈纪要</div>';
      return;
    }
    const views = memo.viewpoints || [];
    diagram.innerHTML = `<div class="memo-structure-tree"><section class="structure-root"><h3><span data-rename-kind="interview" data-rename-id="${escapeHtml(selectedProject?.id || '')}">${escapeHtml(selectedProject?.name || '访谈稿')}</span></h3>${memo.interview_topic ? `<p class="structure-topic">${escapeHtml(memo.interview_topic)}</p>` : ''}${memo.summary ? `<p>${escapeHtml(memo.summary)}</p>` : ''}</section><div class="structure-branches">${views.map((view, index) => `<section class="structure-branch"><div class="structure-view"><h3><span class="structure-number">${String(index + 1).padStart(2, '0')}</span>${escapeHtml(view.title || '核心观点')}</h3>${view.summary ? `<p>${escapeHtml(view.summary)} <span class="memo-indexes">${memoEvidenceButtons(view.evidence || [])}</span></p>` : ''}</div><ul class="structure-facts">${(view.points || []).map(point => `<li>${escapeHtml(point.text || '')} <span class="memo-indexes">${memoEvidenceButtons(point.evidence || [])}</span></li>`).join('') || '<li class="structure-empty">暂无具体展开</li>'}</ul></section>`).join('') || '<div class="memo-empty">纪要尚无核心观点</div>'}</div></div>`;
    diagram.querySelectorAll('[data-evidence-number]').forEach(index => index.onclick = () => {
      setShowing(false);
      renderMemoSource(Number(index.dataset.evidenceNumber));
    });
  }
  function setShowing(value) {
    showing = value;
    grid.hidden = value; diagram.hidden = !value;
    button.textContent = '结构图';
    button.setAttribute('aria-pressed', String(value));
    if (value) draw();
  }
  window.showMemoTextView = () => setShowing(false);
  window.showMemoStructureView = () => { collectMemo();setShowing(true); };
  button.onclick = () => {
    // Keep manual memo edits in memory; the existing Save button still persists them.
    collectMemo();
    setShowing(true);
  };
  const originalRenderMemo = renderMemo;
  renderMemo = function () {
    originalRenderMemo();
    if (showing) draw();
  };
})();
