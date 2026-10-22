/* One topic analysis record, with an on-demand comparison view. */
(() => {
  let pending = null;
  const panel = $('#comparisonPanel');
  const legacyRecords = () => selectedResearchProject?.material_comparisons || [];

  function legacyAccess() {
    const records = legacyRecords();
    if (!records.length) return;
    const section = document.createElement('details');
    section.className = 'shared-legacy-records';
    section.innerHTML = `<summary>旧材料比较记录（${records.length}）</summary><div>${records.map((record, index) => `<button type="button" data-old-comparison="${index}">${escapeHtml(record.name || comparisonRecordLabel(record, index))}</button>`).join('')}</div>`;
    panel.append(section);
    section.querySelectorAll('[data-old-comparison]').forEach(button => button.onclick = () => {
      const record = records[Number(button.dataset.oldComparison)];
      if (!record) return;
      currentComparison = {...record, _saved: true, _researchProjectId: selectedResearchProject.id};
      renderComparison();
      const back = document.createElement('button');
      back.type = 'button';
      back.className = 'soft shared-return';
      back.textContent = '返回当前主题比较';
      back.onclick = () => window.showSharedComparison();
      panel.prepend(back);
    });
  }

  function showComparison(analysis) {
    currentComparison = {...analysis.comparison, relevance: analysis.relevance, _saved: true, _researchProjectId: selectedResearchProject.id};
    renderComparison();
    if (!analysis._comparisonPendingSave) {
      const upgrade = document.createElement('button');
      upgrade.type = 'button';
      upgrade.className = 'soft shared-save-retry';
      upgrade.textContent = '重新生成比较';
      upgrade.onclick = () => {
        analysis._previousComparison = analysis.comparison;
        analysis.comparison = null;
        window.showSharedComparison(true);
      };
      panel.prepend(upgrade);
    }
    if (analysis._comparisonPendingSave) {
      const retry = document.createElement('button');
      retry.type = 'button';
      retry.className = 'soft shared-save-retry';
      retry.textContent = '保存本次比较结果';
      retry.onclick = () => persistComparison(analysis, selectedResearchProject);
      panel.prepend(retry);
    }
    legacyAccess();
    if(analysis.comparison?.source_mode==='theme_statements'){
      const note=document.createElement('p');note.className='comparison-muted';note.textContent=analysis.comparison.notice;panel.prepend(note);
      panel.querySelectorAll('.comparison-evidence').forEach(button=>button.onclick=()=>{
        const pid=button.dataset.projectId,number=Number(button.dataset.evidenceNumber);
        const source=(analysis.comparison.aspects||[]).flatMap(a=>[...(a.answers||[]),...(a.differences||[]).flatMap(d=>d.variants||[])]).flatMap(a=>a.sources||[]).find(s=>s.project_id===pid&&Number(s.number)===number);
        if(source)openThemeEvidence(pid,number,source);else toast('未找到该引用的原文绑定');
      });
    }
  }

  async function persistComparison(analysis, project) {
    if (!analysis.comparison || !project) return;
    try {
      let saved;
      if (analysis.id) {
        const result = await api(`/api/research-projects/${project.id}/theme-analyses/${analysis.id}/comparison`, {
          method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify({comparison:analysis.comparison})
        });
        saved = result.analysis;
        const index = (project.theme_analyses || []).findIndex(record => record.id === analysis.id);
        if (index >= 0) project.theme_analyses[index] = saved;
      } else {
        collectThemeResult();
        const clean = {...analysis, name:analysis.name || analysis.theme.slice(0, 80)};
        delete clean._saved; delete clean._researchProjectId; delete clean._comparisonPendingSave;
        const result = await api(`/api/research-projects/${project.id}/theme-analyses`, {
          method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({analysis:clean})
        });
        saved = result.analysis;
        project.theme_analyses = project.theme_analyses || [];
        project.theme_analyses.push(saved);
        Object.assign(analysis, {id:saved.id, name:saved.name, saved_at:saved.saved_at, _saved:true});
      }
      analysis._comparisonPendingSave = false;
      if (currentThemeAnalysis === analysis && selectedResearchProject?.id === project.id) {
        renderThemeHistory();
        showComparison(analysis);
      }
    } catch (error) {
      analysis._comparisonPendingSave = true;
      if (currentThemeAnalysis === analysis && selectedResearchProject?.id === project.id) showComparison(analysis);
      toast(`比较已生成，但保存失败：${error.message}`);
    }
  }

  window.showSharedComparison = function (generate = false) {
    const analysis = currentThemeAnalysis, project = selectedResearchProject;
    if (!project || !analysis) {
      panel.innerHTML = '<div class="memo-empty">请先在“主题分析”中生成或打开一条分析结果</div>';
      legacyAccess();
      return;
    }
    if (analysis.comparison) { showComparison(analysis); return; }
    const ids = [...new Set((analysis.materials || []).map(item => item.project_id).filter(Boolean))];
    if (ids.length < 2) {
      panel.innerHTML = '<div class="memo-empty">当前主题分析只包含一份访谈稿，至少需要两份才能比较</div>';
      legacyAccess();
      return;
    }
    if (!generate) {
      panel.innerHTML = '<div class="memo-empty">当前主题尚无访谈比较结果。<button type="button" class="soft shared-generate">生成访谈比较</button></div>';
      panel.querySelector('.shared-generate').onclick = () => window.showSharedComparison(true);
      legacyAccess();
      return;
    }
    if (pending?.analysis === analysis) return;
    if(!analysis.id){toast('请先保存当前主题研究结果，再生成访谈比较');return;}
    panel.innerHTML = '<div class="memo-empty">正在按当前主题整理各访谈的共性与差异…</div>';
    pending = {analysis, projectId:project.id};
    api('/api/material-comparisons', {method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({theme:analysis.theme, project_ids:ids, research_project_id:project.id,
        theme_analysis_id:analysis.id,dimensions:(analysis.dimensions || []).map(item => item.name).filter(Boolean)})})
      .then(async result => {
        analysis.comparison = result.comparison;
        analysis._comparisonPendingSave = true;
        if (currentThemeAnalysis === analysis && selectedResearchProject?.id === project.id) showComparison(analysis);
        await persistComparison(analysis, project);
      })
      .catch(error => {
        if (analysis._previousComparison && !analysis.comparison) analysis.comparison = analysis._previousComparison;
        if (currentThemeAnalysis !== analysis || selectedResearchProject?.id !== project.id) return;
        panel.innerHTML = '<div class="memo-empty">材料比较未完成。<button type="button" class="soft shared-retry">重新比较</button></div>';
        panel.querySelector('.shared-retry').onclick = () => window.showSharedComparison(true);
        legacyAccess();
        toast(error.message);
      })
      .finally(() => { if (pending?.analysis === analysis) pending = null; });
  };
})();
