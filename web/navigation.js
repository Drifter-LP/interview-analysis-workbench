// Keep existing data and handlers; reorganize only the analysis entry points.
(() => {
  labels.familiarity = '单篇访谈分析';
  labels.focused = '跨访谈分析';
  document.querySelector('.nav-item[data-tab="coding"]')?.remove();
  const originalSingleSwitchTab = switchTab;
  const originalSingleOpenMaterial = openMaterialMemo;
  openMaterialMemo = async function (type, key) {
    const keepCoding = document.querySelector('#coding').classList.contains('active');
    if(keepCoding&&window.aiCodingDemo&&!window.aiCodingDemo.canLeave())return;
    await originalSingleOpenMaterial(type, key, keepCoding ? {targetTab:'coding'} : {});
  };
  switchTab = function (id) {
    originalSingleSwitchTab(id);
    if (id === 'coding') {
      document.querySelector('.nav-item[data-tab="familiarity"]')?.classList.add('active');
      document.querySelector('#pageTitle').textContent = '单篇访谈分析';
      if(!window.aiCodingDemo)renderAnalysis();
    }
  };
  const icon = paths => `<svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths}</svg>`;
  const icons = {
    prepare: '<path d="M6 3h8l4 4v14H6zM14 3v5h4M9 12h6M9 16h6"/>',
    research: '<path d="M5 20V13M12 20V5M19 20V9"/>',
    workspace: '<path d="M3 7h7l2 2h9v11H3zM3 7V4h7l2 3"/>',
    editor: '<path d="m5 19 7-15 7 15M8 13h8M4 22h16"/>',
    projectManage: '<rect x="5" y="5" width="14" height="16" rx="2"/><path d="M9 5V3h6v2M9 11h6M9 15h6"/>',
    familiarity: '<path d="M12 5C8 3 5 3 3 4v16c3-1 6-1 9 1 3-2 6-2 9-1V4c-2-1-5-1-9 1zM12 5v16"/>',
    focused: '<path d="M12 3v9h9M9 4a9 9 0 1 0 11 11M16 3a9 9 0 0 1 5 5"/>',
    coding: '<path d="M3 4h9l9 9-8 8-10-9z"/><circle cx="8" cy="9" r="1"/>',
    matrix: '<circle cx="12" cy="4" r="2"/><circle cx="4" cy="19" r="2"/><circle cx="12" cy="15" r="2"/><circle cx="21" cy="19" r="2"/><path d="m11 6-6 11M12 6v7m1-7 7 11"/>'
  };
  document.querySelectorAll('.nav-parent, .nav-item').forEach(button => {
    const key = button.dataset.group || button.dataset.tab || button.dataset.view;
    const name = button.dataset.group ? button.querySelector('em')?.textContent : labels[key];
    if (icons[key]) button.innerHTML = icon(icons[key]) + `<em>${escapeHtml(name || '')}</em>` + (button.dataset.group ? '<b>⌄</b>' : '');
  });

  const focused = $('#focused'), head = focused.querySelector('.focused-head');
  head.querySelector('h2').textContent = '主题分析';
  const viewActions = document.createElement('div');
  viewActions.className = 'theme-view-actions';
  const compareButton = $('#comparisonModeBtn');
  compareButton.className = 'soft';
  viewActions.append(compareButton);
  $('#themeQuickInput').closest('.focused-input').append(viewActions);
  head.append($('#comparisonTopActions'));
  focused.append($('#comparisonWorkspace'));
  $('#familiarity .familiarity-switch').hidden = true;
  $('#familiarity').classList.add('single-interview-analysis');
  let comparison = false;
  let evidenceContext = null;
  function restoreEvidenceContext() {
    if (!evidenceContext) return;
    if (selectedResearchProject && selectedResearchProject.id !== evidenceContext.projectId) {
      evidenceContext = null;
      return;
    }
    selectedResearchProject = researchProjects.find(project => project.id === evidenceContext.projectId) || evidenceContext.project;
    currentThemeAnalysis = evidenceContext.theme;
    currentComparison = evidenceContext.comparison;
    evidenceContext = null;
  }
  function refreshCrossMode() {
    compareButton.classList.toggle('active', comparison);
    compareButton.textContent = comparison ? '← 返回主题分析' : '材料比较';
    $('#comparisonWorkspace').hidden = !comparison;
    $('#comparisonTopActions').hidden = true;
    $('#themeQuickInput').closest('.focused-input').hidden = false;
    if ($('#comparisonQuickRow')) $('#comparisonQuickRow').hidden = true;
    $('#themePanel').hidden = comparison;
    $('#themeHistorySelect').hidden = false;
    $('#saveThemeBtn').hidden = false;
    $('#compareMaterialsBtn').disabled = false;
    if (comparison && !window.researchNavigation?.renderSharedWorkspace?.()) window.showSharedComparison?.();
  }
  const originalRenderFocused = renderFocusedAnalysis;
  renderFocusedAnalysis = function () { restoreEvidenceContext(); originalRenderFocused(); refreshCrossMode(); };
  const originalEvidence = openComparisonEvidence;
  openComparisonEvidence = async function (projectId, number) {
    // Collect edits before leaving: rendering the result again must not erase drafts.
    collectThemeResult();
    evidenceContext = {
      projectId: selectedResearchProject?.id,
      project: selectedResearchProject,
      theme: currentThemeAnalysis,
      comparison: currentComparison
    };
    window.showMemoTextView?.();
    await originalEvidence(projectId, number);
    window.showMemoTextView?.();
  };
  // Existing generation and evidence handlers still call this entry point.
  switchFamiliarityMode = function (mode) {
    if (mode === 'comparison') {
      comparison = true;
      switchView('analysis', 'focused');
      refreshCrossMode();
    } else {
      $('#memoWorkspace').hidden = false;
      renderMemo();
    }
  };
  compareButton.onclick = () => {
    restoreEvidenceContext();
    comparison = !comparison;
    if (!comparison) { renderThemeHistory(); renderThemeResult(); }
    refreshCrossMode();
  };
  window.themeComparison = {
    get active(){return comparison;},
    set(value){restoreEvidenceContext();comparison=!!value;if(!comparison){renderThemeHistory();renderThemeResult();}refreshCrossMode();}
  };
  $('#themeHistorySelect').addEventListener('change', () => { if (comparison) refreshCrossMode(); });
  refreshCrossMode();
})();
