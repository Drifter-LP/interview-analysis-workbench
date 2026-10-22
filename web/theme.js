let currentThemeAnalysis = null;
let themeRetryGeneration=0;
async function restoreThemeRetryNotice(){
 const generation=++themeRetryGeneration,projectId=selectedResearchProject?.id;
 if(!projectId||themePickerBusy)return;
 try{const data=await api(`/api/research-projects/${encodeURIComponent(projectId)}/theme-run-status`);
  if(generation!==themeRetryGeneration||projectId!==selectedResearchProject?.id||themePickerBusy||!data.retry||currentThemeAnalysis?.run_id===data.retry.runId)return;
  installThemeIntegrationRetry(data.retry);
 }catch{/* Recovery lookup must not interrupt normal result browsing. */}
}
const themePickerCss=document.createElement('link');themePickerCss.rel='stylesheet';themePickerCss.href='/assets/theme-picker.css?v=20261006-compact';document.head.append(themePickerCss);
let themePickerOriginal=null,themePickerBusy=false,themePickerQuestion='';
const themePickerDrafts=new Map();
const themePicker=$('#themeDialog');themePicker.classList.add('theme-picker-dialog');
const themePickerProjects=document.createElement('div');themePickerProjects.className='theme-project-choices';themePickerProjects.hidden=true;themePicker.querySelector('.theme-label').before(themePickerProjects);
const themePickerStep=document.createElement('p');themePickerStep.className='theme-picker-step';themePicker.querySelector('.dialog-head').after(themePickerStep);
const themePickerBack=document.createElement('button');themePickerBack.type='button';themePickerBack.className='theme-picker-back';themePickerBack.textContent='← 返回项目';themePickerBack.hidden=true;themePickerStep.before(themePickerBack);
const themePickerCount=document.createElement('span');themePickerCount.className='theme-picker-count';themePicker.querySelector('.dialog-actions').prepend(themePickerCount);
function saveThemePickerDraft(){if(selectedResearchProject&&!themePickerProjects.hidden)return;if(selectedResearchProject)themePickerDrafts.set(selectedResearchProject.id,[...document.querySelectorAll('#themeMaterialList input[data-type]:checked')].map(n=>`${n.dataset.type}:${n.dataset.key}`));}
function showThemePickerProjects(){
 themePickerProjects.hidden=false;themePickerBack.hidden=true;themePicker.querySelector('.theme-label').hidden=true;$('#themeMaterialList').hidden=true;$('#startThemeBtn').hidden=true;themePickerCount.hidden=true;themePickerStep.textContent='1 / 2 · 先选择研究项目';
 themePickerProjects.replaceChildren();
 for(const project of researchProjects){const count=(project.interviews||[]).length+(project.uploaded_transcripts||[]).length;const b=document.createElement('button');b.type='button';b.className='theme-project-row';b.innerHTML=`<span class="theme-project-name">${escapeHtml(project.name)}</span><span class="theme-project-size">${count} 篇</span><span class="theme-project-arrow" aria-hidden="true">›</span>`;b.title=project.name;b.onclick=()=>{if(!count){toast('这个项目尚无访谈稿');return;}selectedResearchProject=project;openThemeMaterialDialog();};themePickerProjects.append(b);}
 if(!researchProjects.length)themePickerProjects.textContent='暂无研究项目，请先在项目管理中创建项目。';
}
themePickerBack.onclick=()=>{if(themePickerBusy)return;themePickerQuestion=$('#themeInput').value;saveThemePickerDraft();showThemePickerProjects();};
themePicker.addEventListener('cancel',event=>{if(themePickerBusy)event.preventDefault();});
themePicker.addEventListener('close',()=>{if(themePickerOriginal){selectedResearchProject=themePickerOriginal.project;currentThemeAnalysis=themePickerOriginal.analysis;themePickerOriginal=null;}themePickerDrafts.clear();});

function openThemeEvidence(projectId, number, sourceOverride=null) {
  const source=sourceOverride||(currentThemeAnalysis?.dimensions||[]).flatMap(d=>(d.findings||[]).flatMap(f=>(f.facts||[]).flatMap(fact=>fact.sources||[]))).find(s=>s.project_id===projectId&&Number(s.number)===number);
  if(!source||source.source_type!=='transcript')return openComparisonEvidence(projectId,number);
  const dialog=document.createElement('dialog');dialog.style.cssText='width:min(800px,90vw);max-height:85vh;overflow:auto;padding:24px;border:1px solid #dce7e8;border-radius:10px';
  const heading=document.createElement('h3'),note=document.createElement('p'),text=document.createElement('pre'),close=document.createElement('button');
  heading.textContent=`${source.material_name||projectId} · 原文 ${number}`;note.textContent=`分析时的原文证据，字符位置 ${source.start}—${source.end}（不是纪要编号）`;
  text.textContent=source.context_quote||source.quote;text.style.cssText='white-space:pre-wrap;line-height:1.9;font:inherit';close.textContent='关闭';close.type='button';close.onclick=()=>dialog.close();dialog.append(heading,note,text,close);dialog.addEventListener('close',()=>dialog.remove());document.body.append(dialog);dialog.showModal();
}

function renderFocusedAnalysis() {
  const picker = $('#themeProjectSelect');
  picker.innerHTML = '<option value="">选择项目</option>' + researchProjects.map(project =>
    `<option value="${escapeHtml(project.id)}">${escapeHtml(project.name)}</option>`
  ).join('');
  picker.value = selectedResearchProject?.id || '';
  if (currentThemeAnalysis && currentThemeAnalysis._researchProjectId !== selectedResearchProject?.id) currentThemeAnalysis = null;
  renderThemeHistory();
  renderThemeResult();
  restoreThemeRetryNotice();
}

function renderThemeHistory() {
  const picker = $('#themeHistorySelect');
  const records = researchProjects.filter(project=>!selectedResearchProject||project.id===selectedResearchProject.id).flatMap(project => (project.theme_analyses || []).map((item, index) => ({item, index, projectId: project.id})));
  records.sort((a, b) => Number(b.item.saved_at || b.item.created_at || 0) - Number(a.item.saved_at || a.item.created_at || 0) || b.index - a.index);
  const options = '<option value="">分析记录</option>' + records.map(({item, index, projectId}) =>
    `<option value="${escapeHtml(JSON.stringify([projectId, index]))}">${escapeHtml(item.name || item.theme || '主题分析')}</option>`
  ).join('');
  if(picker.dataset.historyOptions!==options){picker.innerHTML=options;picker.dataset.historyOptions=options;}
  picker.disabled = !records.length;
  const project = researchProjects.find(item => item.id === currentThemeAnalysis?._researchProjectId);
  const index = (project?.theme_analyses || []).findIndex(item => item.id && item.id === currentThemeAnalysis?.id);
  picker.value = index >= 0 ? JSON.stringify([project.id, index]) : '';
}

function themeInclusionSummary(analysis, tooltipId = 'themeInclusionReasons') {
  return ''; // Material count lives in the compact result toolbar; no relevance gate.
}

function renderThemeResult() {
  const panel = $('#themePanel');
  const analysis = currentThemeAnalysis;
  $('#saveThemeBtn').disabled = !analysis || !!analysis._saved || !selectedResearchProject;
  if (!analysis) {
    panel.innerHTML = '';
    return;
  }
  $('#themeQuickInput').value = analysis.theme || '';
  if (analysis.graph_type === 'cooccurrence') {
    panel.innerHTML = `<div class="memo-empty"><h3>五篇访谈主题共现分析</h3><p>研究问题：${escapeHtml(analysis.theme)}</p><p>本记录为问答块共现图，请切换到“主题关系图”查看。纳入 ${analysis.materials?.length || 0} 篇访谈；连线表示同块讨论，不表示因果。</p></div>`;
    return;
  }
  if (Array.isArray(analysis.dimensions)) {
    const dimensions = analysis.dimensions.map((dimension, dimensionIndex) => {
      const findings = (dimension.findings || []).map((item, findingIndex) => {
        const facts = item.facts || [];
        const findingNotes = [...(item.reference_notes || []), ...(item.unclassified_reason ? ['暂无分类：' + item.unclassified_reason] : [])];
        const boundary = item.boundary_review_info;
        const boundaryMarkup = boundary ? `<details class="theme-boundary-review"><summary>合并边界复核：${boundary.decision === 'split' ? '由原发现拆分' : '保留原发现'}</summary><p>${escapeHtml(boundary.reason)}</p>${boundary.decision === 'split' ? `<p>复核前：${escapeHtml(boundary.original_finding?.title || '')}</p><p>${escapeHtml(boundary.original_finding?.summary || '')}</p>` : ''}${boundary.unused_statement_ids?.length ? `<p>未沿用引用：${escapeHtml(boundary.unused_statement_ids.join('、'))}。${escapeHtml(boundary.unused_reason)}</p>` : ''}<p>模型的边界判断，不代表已完成原文支持性核查。</p></details>` : '';
const findingCell = `<td class="theme-finding-cell" rowspan="${Math.max(1, facts.length)}"><h3 contenteditable="true" data-field="title">${escapeHtml(item.title || '')}</h3><p contenteditable="true" data-field="summary">${escapeHtml(item.summary || '')}</p>${item.differences ? `<p class="coding-tree-muted">差异与例外：${escapeHtml(item.differences)}</p>` : ''}${findingNotes.map(note => `<p class="coding-tree-muted">${escapeHtml(note)}</p>`).join('')}${item.reference_notes?.length ? '<p class="coding-tree-muted">引用关系由程序计算，不代表语义重复。</p>' : ''}${boundaryMarkup}</td>`;
        const rows = facts.map((fact, factIndex) => {
          let sourceCell = '';
          if (factIndex === 0 || !fact.project_id || facts[factIndex - 1].project_id !== fact.project_id) {
            let count = 1;
            while (fact.project_id && facts[factIndex + count]?.project_id === fact.project_id) count++;
            sourceCell = `<td class="theme-source-cell" rowspan="${count}"><span data-rename-kind="interview" data-rename-id="${escapeHtml(fact.project_id || '')}" title="双击重命名">${escapeHtml(fact.material_name || '')}</span></td>`;
          }
          return `<tr data-fact="${factIndex}">${factIndex === 0 ? findingCell : ''}${sourceCell}<td><span contenteditable="true" data-field="text">${escapeHtml(fact.text || '')}</span> <span class="memo-indexes">${comparisonEvidenceButtons(fact)}</span></td></tr>`;
        }).join('');
        return `<tbody data-finding="${findingIndex}">${rows || `<tr>${findingCell}<td>—</td><td>暂无事实</td></tr>`}</tbody>`;
      }).join('');
      return `<section class="theme-section theme-dimension" data-dimension="${dimensionIndex}">${dimension.is_flat_findings ? '' : `<div class="theme-dimension-heading"><span class="theme-dimension-number">${String(dimensionIndex + 1).padStart(2, '0')}</span><h2 contenteditable="true" data-field="dimension-name">${escapeHtml(dimension.name || '')}</h2></div>`}${dimension.definition ? `<details class="theme-definition"><summary aria-label="展开维度定义" title="维度定义">⌄</summary><p contenteditable="true" data-field="dimension-definition">${escapeHtml(dimension.definition)}</p></details>` : ''}<table class="theme-table"><colgroup><col style="width:25%"><col style="width:20%"><col style="width:55%"></colgroup><thead><tr><th scope="col">发现</th><th scope="col">材料来源</th><th scope="col">事实与依据</th></tr></thead>${findings || '<tbody><tr><td colspan="3">暂无发现</td></tr></tbody>'}</table></section>`;
    }).join('');
    const dimensionNote = analysis.dimension_selection?.acceptable === false ? '<p class="theme-integration-warning">模型未找到充分合理的维度方案；以下为候选结构，需人工检查。</p>' : '';
    panel.innerHTML = `${dimensionNote}${themeInclusionSummary(analysis)}${dimensions || `<div class="memo-empty">${escapeHtml(analysis.notice || '没有符合主题的材料')}</div>`}`;
    if(analysis.run_id&&analysis.source_mode==='original_transcript'&&(analysis.failed_batches||[]).some(item=>item.label==='synthesis'&&/截断|失败|未完成/.test(item.error||'')))installThemeIntegrationRetry({runId:analysis.run_id,theme:analysis.theme,projectId:analysis._researchProjectId||selectedResearchProject?.id,ids:(analysis.materials||[]).map(m=>m.project_id)});
    panel.querySelectorAll('.comparison-evidence').forEach(button => button.onclick = () => openThemeEvidence(button.dataset.projectId, Number(button.dataset.evidenceNumber)));
    panel.querySelectorAll('[contenteditable]').forEach(node => node.oninput = () => {
      analysis._saved = false;
      $('#saveThemeBtn').disabled = false;
    });
    return;
  }
  const section = (key, label) => `<section class="theme-section"><h2>${label}</h2>${(analysis[key] || []).length ? analysis[key].map((item, index) =>
    `<article class="comparison-item theme-item" data-kind="${key}" data-index="${index}"><div class="viewpoint-heading"><span class="viewpoint-number">${String(index + 1).padStart(2, '0')}</span><h3 contenteditable="true" data-field="title">${escapeHtml(item.title || '')}</h3></div><p contenteditable="true" data-field="summary">${escapeHtml(item.summary || '')}</p>${(item.perspectives || []).map((view, viewIndex) =>
      `<div class="comparison-perspective" data-view="${viewIndex}"><b>${escapeHtml(view.material_name || '')}</b><span contenteditable="true" data-field="text">${escapeHtml(view.text || '')}</span><span class="memo-indexes">${comparisonEvidenceButtons(view)}</span></div>`
    ).join('')}</article>`
  ).join('') : '<div class="memo-empty">暂无</div>'}</section>`;
  panel.innerHTML = `${themeInclusionSummary(analysis)}${section('findings', '主要发现')}${section('exceptions', '不同看法与例外')}<section class="theme-section"><h2>尚待了解</h2>${(analysis.gaps || []).map((gap, index) => `<p class="theme-gap" data-gap="${index}" contenteditable="true">${escapeHtml(gap)}</p>`).join('') || '<div class="memo-empty">暂无</div>'}</section>`;
  panel.querySelectorAll('.comparison-evidence').forEach(button => button.onclick = () => openComparisonEvidence(button.dataset.projectId, Number(button.dataset.evidenceNumber)));
  panel.querySelectorAll('[contenteditable]').forEach(node => node.oninput = () => {
    analysis._saved = false;
    $('#saveThemeBtn').disabled = false;
  });
}

function collectThemeResult() {
  const analysis = currentThemeAnalysis;
  if (!analysis) return;
  if (Array.isArray(analysis.dimensions)) {
    $('#themePanel').querySelectorAll('[data-dimension]').forEach(section => {
      const dimension = analysis.dimensions[Number(section.dataset.dimension)];
      const dimensionName = section.querySelector('[data-field="dimension-name"]');
      if (dimensionName) dimension.name = dimensionName.textContent.trim();
        const definition = section.querySelector('[data-field="dimension-definition"]');
        if (definition) dimension.definition = definition.textContent.trim();
      section.querySelectorAll('[data-finding]').forEach(card => {
        const item = dimension.findings[Number(card.dataset.finding)];
        item.title = card.querySelector('[data-field="title"]').textContent.trim();
        item.summary = card.querySelector('[data-field="summary"]').textContent.trim();
        card.querySelectorAll('[data-fact]').forEach(row => {
          item.facts[Number(row.dataset.fact)].text = row.querySelector('[data-field="text"]').textContent.trim();
        });
      });
    });
    return;
  }
  $('#themePanel').querySelectorAll('.theme-item').forEach(card => {
    const item = analysis[card.dataset.kind][Number(card.dataset.index)];
    item.title = card.querySelector('[data-field="title"]').textContent.trim();
    item.summary = card.querySelector('[data-field="summary"]').textContent.trim();
    card.querySelectorAll('[data-view]').forEach(row => {
      item.perspectives[Number(row.dataset.view)].text = row.querySelector('[data-field="text"]').textContent.trim();
    });
  });
  $('#themePanel').querySelectorAll('[data-gap]').forEach(row => {
    analysis.gaps[Number(row.dataset.gap)] = row.textContent.trim();
  });
}

function updateThemeSelection() {
  const choices = [...document.querySelectorAll('#themeMaterialList input[data-type]')];
  const selected = choices.filter(choice => choice.checked).length;
  themePickerCount.textContent=`已选 ${selected} 篇`;
  const all = $('#themeSelectAll');
  if (all) {
    all.checked = choices.length > 0 && selected === choices.length;
    all.indeterminate = selected > 0 && selected < choices.length;
  }
  $('#startThemeBtn').disabled = !$('#themeInput').value.trim() || selected === 0;
}

function openThemeDialog() {
  if(themePicker.open)return;themePickerOriginal={project:selectedResearchProject,analysis:currentThemeAnalysis};themePickerQuestion=$('#themeQuickInput').value.trim()||currentThemeAnalysis?.theme||'';themePickerDrafts.clear();themePicker.querySelector('h2').textContent='选择访谈稿';showThemePickerProjects();themePicker.showModal();
}

function openThemeMaterialDialog() {
  if (!selectedResearchProject) { toast('请先打开研究项目'); return; }
  const rows = memoMaterials();
  if (!rows.length) { toast('请先向项目添加访谈稿'); return; }
  const previous = currentThemeAnalysis?._researchProjectId === selectedResearchProject.id ? currentThemeAnalysis : null;
  const previousIds = new Set((previous?.materials || []).map(item => item.project_id));
  const draft=themePickerDrafts.get(selectedResearchProject.id);
  themePickerProjects.hidden=true;themePickerBack.hidden=false;themePicker.querySelector('.theme-label').hidden=false;$('#themeMaterialList').hidden=false;$('#startThemeBtn').hidden=false;themePickerCount.hidden=false;themePickerStep.textContent=`2 / 2 · ${selectedResearchProject.name}`;themePickerStep.title=selectedResearchProject.name;
  $('#themeInput').value = themePickerQuestion;
  $('#themeMaterialList').innerHTML = '<label class="comparison-choice"><input type="checkbox" id="themeSelectAll"><span>全选</span></label>' + rows.map(row =>
    `<label class="comparison-choice" title="${escapeHtml(row.name)}"><input type="checkbox" data-type="${row.type}" data-key="${escapeHtml(row.key)}" data-project-id="${escapeHtml(row.projectId)}" ${(draft?draft.includes(`${row.type}:${row.key}`):previousIds.has(row.projectId)) ? 'checked' : ''}><span>${escapeHtml(row.name)}</span></label>`
  ).join('');
  updateThemeSelection();
  if(!themePicker.open)themePicker.showModal();
  $('#themeInput').focus();
}

async function generateThemeAnalysis() {
  const theme = $('#themeInput').value.trim();
  const choices = [...document.querySelectorAll('#themeMaterialList input[data-type]:checked')];
  if (!theme || !choices.length) return;
  const button = $('#startThemeBtn');
  themePickerBusy=true;themePickerBack.disabled=true;$('#closeThemeDialog').disabled=true;$('#cancelThemeDialog').disabled=true;
  setAiLoading(button, true);
  const progress=document.createElement('p');progress.className='theme-run-progress';progress.setAttribute('role','status');progress.setAttribute('aria-live','polite');progress.style.cssText='font-size:13px;color:var(--muted,#70878e);margin:8px 0';button.closest('.dialog-actions').before(progress);
  let requestIds=[];
  try {
    const ids = [];
    for (const choice of choices) {
      let projectId = choice.dataset.projectId;
      if (!projectId && choice.dataset.type === 'uploaded') {
        const prepared = await api(`/api/research-projects/${selectedResearchProject.id}/uploaded/${choice.dataset.key}/prepare`, {method: 'POST'});
        projectId = prepared.project_id;
        selectedResearchProject.uploaded_transcripts[Number(choice.dataset.key)].workspace_project_id = projectId;
      }
      if (projectId) ids.push(projectId);
    }
    requestIds=ids;
    const result = await runThemeWithProgress({research_project_id: selectedResearchProject.id, project_ids: ids, theme},data=>{progress.textContent=data.message||'正在分析…';});
    currentThemeAnalysis = {...result.analysis, _saved: false, _researchProjectId: selectedResearchProject.id};
    themePickerOriginal=null;
    $('#themeDialog').close();
    switchView('analysis', 'focused');
    toast('主题分析已生成');
  } catch (error) { toast(error.message);const match=error.message.match(/运行编号：([0-9]{8}-[0-9]{6}-[0-9a-f]{6})/);if(match&&(error.message.includes('可仅重试整合')||error.message.includes('可继续未完成分析'))){themePickerOriginal=null;$('#themeDialog').close();switchView('analysis','focused');installThemeIntegrationRetry({runId:match[1],theme,projectId:selectedResearchProject.id,ids:requestIds,recovery:error.message.includes('可继续未完成分析')});} }
  finally { progress.remove();themePickerBusy=false;themePickerBack.disabled=false;$('#closeThemeDialog').disabled=false;$('#cancelThemeDialog').disabled=false;setAiLoading(button, false); }
}

function installThemeIntegrationRetry(context){
 const panel=$('#themePanel');panel.querySelector('.theme-integration-warning')?.remove();const notice=document.createElement('div');notice.className='theme-integration-warning';notice.style.cssText='padding:12px 16px;margin:12px 0;border:1px solid #ecdca5;border-radius:8px;background:#fffaf0;font-size:13px';
 const retryLabel=context.recovery?'继续未完成分析':'仅重试整合';const text=document.createElement('p');text.textContent=context.recovery?'本次提取未完成；已保留成功批次。继续时复用输入一致的检查点，仅处理未完成部分；以下旧结果不是本次新结果。':'跨访谈整合未完成；已保留原文提取结果。以下旧结果不是完整聚合结果。';const button=document.createElement('button');button.type='button';button.className='soft';button.textContent=retryLabel;notice.append(text,button);panel.prepend(notice);
const progress=document.createElement('p');progress.setAttribute('role','status');progress.setAttribute('aria-live','polite');progress.style.cssText='font-size:13px;margin:8px 0 0';notice.append(progress);
button.onclick=async()=>{button.disabled=true;button.textContent=context.recovery?'正在继续…':'正在整合…';try{const result=await runThemeWithProgress({research_project_id:context.projectId,project_ids:context.ids,theme:context.theme,resume_run_id:context.runId},data=>{progress.textContent=data.message||'正在分析…';});selectedResearchProject=researchProjects.find(p=>p.id===context.projectId)||selectedResearchProject;currentThemeAnalysis={...result.analysis,_saved:false,_researchProjectId:context.projectId};renderFocusedAnalysis();toast('主题分析已完成，尚未保存');}catch(error){toast(error.message);progress.textContent='尚未完成，成功批次已保留，可继续。';const match=error.message.match(/运行编号：([0-9]{8}-[0-9]{6}-[0-9a-f]{6})/);if(match)context.runId=match[1];}finally{button.disabled=false;button.textContent=retryLabel;}};
}

async function saveThemeAnalysis() {
  if (!currentThemeAnalysis || !selectedResearchProject) return;
  collectThemeResult();
  const name = await askComparisonName(currentThemeAnalysis.name || currentThemeAnalysis.theme, '保存主题分析', '分析名称');
  if (!name) return;
  const button = $('#saveThemeBtn');
  button.disabled = true;
  try {
    const analysis = {...currentThemeAnalysis, name};
    delete analysis._saved;
    delete analysis._researchProjectId;
    const result = await api(`/api/research-projects/${selectedResearchProject.id}/theme-analyses`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({analysis})});
    selectedResearchProject.theme_analyses = selectedResearchProject.theme_analyses || [];
    selectedResearchProject.theme_analyses.push(result.analysis);
    currentThemeAnalysis = {...result.analysis, _saved: true, _researchProjectId: selectedResearchProject.id};
    renderThemeHistory();
    renderThemeResult();
    toast('主题分析已保存');
  } catch (error) { button.disabled = false; toast(error.message); }
}

$('#themeQuickStart').onclick = openThemeDialog;
$('#themeProjectSelect').hidden=true;
$('#themeQuickInput').onkeydown = event => { if (event.key === 'Enter') openThemeDialog(); };
$('#themeProjectSelect').onchange = event => {
  selectedResearchProject = researchProjects.find(project => project.id === event.target.value) || null;
  currentThemeAnalysis = null;
  renderFocusedAnalysis();
};
$('#closeThemeDialog').onclick = $('#cancelThemeDialog').onclick = () => {if(!themePickerBusy)$('#themeDialog').close();};
$('#themeInput').oninput = updateThemeSelection;
$('#themeMaterialList').onchange = event => {
  if (event.target.id === 'themeSelectAll') {
    document.querySelectorAll('#themeMaterialList input[data-type]').forEach(choice => { choice.checked = event.target.checked; });
  }
  updateThemeSelection();
};
$('#startThemeBtn').onclick = generateThemeAnalysis;
$('#saveThemeBtn').onclick = saveThemeAnalysis;
let themeHistoryRequest=0;
$('#themeHistorySelect').onchange = async event => {
  if (event.target.value === '') return;
  let selection;
  try { selection = JSON.parse(event.target.value); } catch { return; }
  if (!Array.isArray(selection) || selection.length !== 2) return;
  const [projectId, index] = selection;
  const project = researchProjects.find(item => item.id === projectId);
  let record = project?.theme_analyses?.[index];
  if (!record) return;
  const token=++themeHistoryRequest;
  if(record._summary){
    try{const loaded=await api(`/api/research-projects/${encodeURIComponent(projectId)}/theme-analysis-records/${index}`);if(token!==themeHistoryRequest||event.target.value!==JSON.stringify([projectId,index])||selectedResearchProject?.id!==projectId)return;if(record.id&&loaded.id!==record.id)throw Error('分析记录已变化，请刷新列表');project.theme_analyses[index]=record=loaded;}
    catch(error){if(token===themeHistoryRequest)toast('读取分析结果失败：'+error.message);return;}
  }
  selectedResearchProject = project;
  currentThemeAnalysis = {...record, _saved: true, _researchProjectId: project.id};
  renderFocusedAnalysis();
};

const renameScript = document.createElement('script');
renameScript.src = '/assets/rename.js?v=20261012-cascade-2';
document.body.append(renameScript);

const structureScript = document.createElement('script');
structureScript.src = '/assets/structure.js?v=20261005-unified-top-2';
document.body.append(structureScript);

const navigationScript = document.createElement('script');
navigationScript.async = false;
navigationScript.src = '/assets/navigation.js?v=20261021-coding-fast-21';
document.body.append(navigationScript);

const comparisonStyle = document.createElement('link');
comparisonStyle.rel = 'stylesheet';
comparisonStyle.href = '/assets/comparison.css?v=20261004-3';
document.head.append(comparisonStyle);
const comparisonScript = document.createElement('script');
comparisonScript.async = false;
comparisonScript.src = '/assets/comparison.js?v=20261015-statement-1';
document.body.append(comparisonScript);

const sharedComparisonScript = document.createElement('script');
sharedComparisonScript.async = false;
sharedComparisonScript.src = '/assets/shared-comparison.js?v=20261015-statement-1';
const findingReviewScript=document.createElement('script');findingReviewScript.src='/assets/finding-review.js?v=20261019-ds-independent-1';document.body.append(findingReviewScript);
sharedComparisonScript.addEventListener('load', () => {
  const networkScript = document.createElement('script');
  networkScript.src = '/assets/network-view.js?v=20261013-focus-curves-4';
networkScript.addEventListener('load',()=>{const script=document.createElement('script');script.src='/assets/coding-tree.js?v=20261018-boundary-review';script.addEventListener('load',()=>{const navigation=document.createElement('script');navigation.src='/assets/research-navigation.js?v=20261020-cleanpicker-6';document.body.append(navigation);});document.body.append(script);});
  document.body.append(networkScript);
});
document.body.append(sharedComparisonScript);
