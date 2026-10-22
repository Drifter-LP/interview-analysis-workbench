/* Theme-led comparison, with backward-compatible saved records. */
(() => {
  const dialog = $('#comparisonDialog');
  const label = document.createElement('label');
  label.className = 'comparison-theme-label';
  label.innerHTML = '比较主题<input id="comparisonThemeInput" maxlength="300" placeholder="例如：DIP改革对患者就医的影响" autocomplete="off">';
  const row = document.createElement('div');
  row.id = 'comparisonQuickRow';
  row.className = 'focused-input';
  row.hidden = true;
  $('#focused .focused-head').after(row);
  row.append(label);
  row.append($('#compareMaterialsBtn'));
  $('#compareMaterialsBtn').className = 'primary';
  $('#compareMaterialsBtn').textContent = '选择访谈稿';
  $('#comparisonHistoryToggle').textContent = '历史结果 ▾';
  const historyToggle = $('#comparisonHistoryToggle');
  const tidyHistoryLabel = () => {
    const clean = historyToggle.textContent.replace(/\s*▾\s*$/, '');
    if (clean !== historyToggle.textContent) historyToggle.textContent = clean;
  };
  new MutationObserver(tidyHistoryLabel).observe(historyToggle, {childList:true, characterData:true, subtree:true});
  tidyHistoryLabel();
  dialog.querySelector('h2').textContent = '选择比较访谈稿';
  const input = $('#comparisonThemeInput');
  input.placeholder = '输入想比较的问题或主题';
  input.setAttribute('aria-label', '比较主题');
  row.replaceChild(input, label);
  const selectAllRow = document.createElement('label');
  selectAllRow.className = 'comparison-select-all';
  selectAllRow.innerHTML = '<input type="checkbox" id="comparisonSelectAll"> 全选';
  $('#comparisonMaterialList').before(selectAllRow);
  const selectAll = $('#comparisonSelectAll');
  selectAll.onchange = () => {
    dialog.querySelectorAll('#comparisonMaterialList input[type="checkbox"]').forEach(choice => { choice.checked = selectAll.checked; });
    updateComparisonCount();
  };
  const originalOpen = openComparisonDialog;
  openComparisonDialog = function () {
    if (!selectedResearchProject) { $('#themeProjectSelect').focus(); toast('请先选择研究项目'); return; }
    originalOpen();
    selectAll.checked = false;
    selectAll.indeterminate = false;
    updateComparisonCount();
  };
  updateComparisonCount = function () {
    const choices = [...dialog.querySelectorAll('#comparisonMaterialList input[type="checkbox"]')];
    const count = choices.filter(choice => choice.checked).length;
    selectAll.checked = choices.length > 0 && count === choices.length;
    selectAll.indeterminate = count > 0 && count < choices.length;
    $('#comparisonCount').textContent = `已选择 ${count} 份${input.value.trim() ? '' : ' · 请先在页面填写比较主题'}`;
    $('#startComparisonBtn').disabled = count < 2 || !input.value.trim();
  };
  input.oninput = updateComparisonCount;
  $('#comparisonMaterialList').onchange = updateComparisonCount;
  $('#compareMaterialsBtn').onclick = openComparisonDialog;
  if ($('#emptyComparisonBtn')) $('#emptyComparisonBtn').onclick = openComparisonDialog;
  generateComparison = async function () {
    const choices = [...dialog.querySelectorAll('#comparisonMaterialList input:checked')];
    const theme = input.value.trim(), project = selectedResearchProject;
    const button = $('#startComparisonBtn');
    if (choices.length < 2 || !theme || !project) return;
    setAiLoading(button, true);
    try {
      const ids = [];
      for (const choice of choices) {
        let id = choice.dataset.projectId;
        if (!id && choice.dataset.type === 'uploaded') {
          const prepared = await api(`/api/research-projects/${project.id}/uploaded/${choice.dataset.key}/prepare`, {method:'POST'});
          id = prepared.project_id;
        }
        if (id) ids.push(id);
      }
      const result = await api('/api/material-comparisons', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({theme, project_ids:ids, research_project_id:project.id})});
      currentComparison = {...result.comparison, _saved:false, _researchProjectId:project.id};
      dialog.close();
      switchFamiliarityMode('comparison');
      renderComparison();
      toast('主题比较已生成，可保存本次结果');
    } catch (e) { toast(e.message); }
    finally { setAiLoading(button, false); updateComparisonCount(); }
  };
  $('#startComparisonBtn').onclick = generateComparison;
  const legacyRender = renderComparison;
  renderComparison = function () {
    if (!Array.isArray(currentComparison?.aspects)) return legacyRender();
    const c = currentComparison, materials = c.materials || [], panel = $('#comparisonPanel');
    input.value = c.theme || '';
    $('#saveComparisonBtn').disabled = !!c._saved || !selectedResearchProject;
    if (c.schema_version >= 2) {
      const dimensionOrder = (currentThemeAnalysis?.dimensions || []).map(item => item.name).filter(Boolean);
      const grouped = new Map();
      c.aspects.forEach(aspect => {
        const name = aspect.dimension || '比较发现';
        if (!grouped.has(name)) grouped.set(name, []);
        grouped.get(name).push(aspect);
      });
      const names = [...grouped.keys()].sort((left, right) => {
        const a = dimensionOrder.indexOf(left), b = dimensionOrder.indexOf(right);
        return (a < 0 ? 999 : a) - (b < 0 ? 999 : b);
      });
      const renderAspect = aspect => {
        const common = (aspect.common || []).filter(item => Array.isArray(item.project_ids) && item.project_ids.length >= 2);
        const supported = new Set(common.flatMap(item => item.project_ids));
        const evidence = (aspect.answers || []).filter(answer => supported.has(answer.project_id));
        const differences = (aspect.differences || []).filter(item => Array.isArray(item.variants) && item.variants.length >= 2);
        const commonText = common.length ? common.map(item => `<p>${escapeHtml(item.text)}</p>`).join('') : `<p class="comparison-muted">仅单篇提及，未形成跨访谈共性</p>`;
        const coverage = common.length ? `<div class="comparison-coverage">${supported.size} / ${materials.length} 篇提及 <span class="memo-indexes">${evidence.map(comparisonEvidenceButtons).join('')}</span></div>` : '';
        const diffText = differences.length ? differences.map(item => `<div class="comparison-diff-group"><div class="comparison-diff-question">比较问题　${escapeHtml(item.question || aspect.question || '')}</div>${item.variants.map(variant => `<div class="comparison-diff-line"><b data-rename-kind="interview" data-rename-id="${escapeHtml(variant.project_id)}">${escapeHtml(variant.material_name || materials.find(m => m.project_id === variant.project_id)?.name || '')}</b><span>${escapeHtml(variant.text)} <span class="memo-indexes">${comparisonEvidenceButtons(variant)}</span></span></div>`).join('')}</div>`).join('') : '<p class="comparison-no-diff">未发现针对同一事实的明确差异</p>';
        return `<div class="comparison-view-row"><div class="comparison-view-cell"><h4>${escapeHtml(aspect.name)}</h4>${commonText}${coverage}</div><div class="comparison-view-cell">${diffText}</div></div>`;
      };
      panel.innerHTML = `${themeInclusionSummary(c, 'comparisonInclusionReasons')}${names.map((name, index) => {
        const aspects = grouped.get(name);
        const shared = aspects.filter(aspect => (aspect.common || []).some(item => (item.project_ids || []).length >= 2));
        const single = aspects.filter(aspect => !shared.includes(aspect));
        return `<section class="comparison-dimension"><h3><span>${String(index + 1).padStart(2, '0')}</span>${escapeHtml(name)}</h3><div class="comparison-view-head"><span>共同发现</span><span>访谈间差异</span></div>${shared.map(renderAspect).join('')}${single.length ? `<details class="comparison-single"><summary>仅单篇提及　${single.length} 项发现</summary>${single.map(renderAspect).join('')}</details>` : ''}</section>`;
      }).join('') || '<div class="memo-empty">所选材料中没有找到有依据的主题回答。</div>'}`;
      panel.querySelectorAll('.comparison-evidence').forEach(button => button.onclick = () => openComparisonEvidence(button.dataset.projectId, Number(button.dataset.evidenceNumber)));
      return;
    }
    const summaries = (items, fallback) => items?.length ? items.map(i => `<p>${escapeHtml(i.text)}</p>`).join('') : `<p class="comparison-muted">${fallback}</p>`;
    panel.innerHTML = `<h2 class="comparison-question">${escapeHtml(c.theme)}</h2>${c.aspects.length ? `<div class="answer-matrix-scroll"><table class="answer-matrix"><thead><tr><th>比较方面</th>${materials.map(m => `<th><span data-rename-kind="interview" data-rename-id="${escapeHtml(m.project_id)}">${escapeHtml(m.name)}</span></th>`).join('')}</tr></thead>${c.aspects.map(a => `<tbody><tr><th><strong>${escapeHtml(a.name)}</strong><small>${escapeHtml(a.question)}</small></th>${materials.map(m => {
      const answer = (a.answers || []).find(v => v.project_id === m.project_id);
      if (!answer || answer.status === 'not_discussed') return '<td class="comparison-muted">未明确讨论</td>';
      if (answer.status === 'not_found') return '<td class="comparison-muted">未找到相关表述</td>';
      return `<td>${answer.status === 'uncertain' ? '<small class="comparison-muted">与主题的联系尚不明确</small>' : ''}<p>${escapeHtml(answer.text)}</p><span class="memo-indexes">${comparisonEvidenceButtons(answer)}</span></td>`;
    }).join('')}</tr><tr class="comparison-synthesis"><td colspan="${materials.length + 1}"><div><b>共性</b>${summaries(a.common, '暂无有依据的共性')}</div><div><b>差异</b>${summaries(a.differences, '暂无有依据的差异')}</div></td></tr></tbody>`).join('')}</table></div>` : '<div class="memo-empty">所选材料中没有找到有依据的主题回答，可调整主题或更换材料。</div>'}`;
    panel.insertAdjacentHTML('afterbegin', themeInclusionSummary(c, 'comparisonInclusionReasons'));
    panel.querySelectorAll('.comparison-evidence').forEach(b => b.onclick = () => openComparisonEvidence(b.dataset.projectId, Number(b.dataset.evidenceNumber)));
  };
  if (currentComparison) renderComparison();
})();
