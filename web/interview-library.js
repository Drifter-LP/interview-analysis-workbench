/* Library-only presentation. Research membership remains the source of truth. */
(()=>{
 const expanded=new Set(),allRows=new Set();let initialized=false;
 const root=$('#workspace'), overview=root.querySelector('.overview-grid');
 overview.innerHTML='<span>全部访谈 <strong id="projectCount">0</strong></span><span>｜</span><span>待校订 <strong id="reviewCount">0</strong></span><span class="library-activity"><i></i><span id="activeState">当前无处理任务</span></span>';
root.querySelector('.section-head').innerHTML='<h2>访谈资料</h2><div class="library-tools"><input id="librarySearch" placeholder="搜索访谈或项目" aria-label="搜索访谈或项目"><select id="libraryStatus" aria-label="访谈状态"><option value="">全部状态</option><option value="completed">已完成</option><option value="review">待校订</option><option value="processing">处理中</option><option value="interrupted">已中断</option><option value="failed">失败</option></select><select id="librarySort" aria-label="访谈排序"><option value="opened">最近打开</option><option value="created">最近导入</option><option value="name">名称排序</option></select></div>';
 const dialog=document.createElement('dialog');dialog.className='library-delete-dialog';dialog.innerHTML='<h3>删除访谈？</h3><p class="library-delete-name"></p><p>将从资料列表、项目及后续分析材料中移除。包含该访谈的分析记录一并归档，移入「设置 → 回收站」，7天内可恢复，到期永久删除。</p><div class="dialog-actions"><button type="button" class="ghost" data-cancel>取消</button><button type="button" class="danger" data-confirm>删除访谈</button></div>';document.body.append(dialog);
 function confirmDelete(name){dialog.querySelector('.library-delete-name').textContent=name;dialog.showModal();return new Promise(resolve=>{const finish=v=>{dialog.close();dialog.oncancel=null;resolve(v)};dialog.querySelector('[data-cancel]').onclick=()=>finish(false);dialog.querySelector('[data-confirm]').onclick=()=>finish(true);dialog.oncancel=e=>{e.preventDefault();finish(false)}})}
 function groups(){const assigned=new Set(),byId=new Map(projects.map(p=>[p.id,p]));const result=researchProjects.map(p=>{const rows=[],seen=new Set();for(const id of p.interview_ids||[]){const w=byId.get(id);if(w){rows.push({...w,key:id,owner:p.id,type:'workspace'});seen.add(id);assigned.add(id)}}(p.uploaded_transcripts||[]).forEach((u,index)=>{const id=u.workspace_project_id; if(id)assigned.add(id);if(id&&seen.has(id))return;const w=byId.get(id);rows.push({...u,...(w||{}),name:w?.name||u.name,key:id||`${p.id}:${index}`,id:id||'',owner:p.id,index,type:id&&w?'workspace':'uploaded',status:w?.status||'completed'});if(id)seen.add(id)});return {...p,rows}});const rows=projects.filter(p=>!assigned.has(p.id)).map(p=>({...p,key:p.id,type:'workspace'}));if(rows.length)result.push({id:'unassigned',name:'未归入项目的访谈',rows});return result}
 function sortRows(a,b){const mode=$('#librarySort').value;if(mode==='name')return a.name.localeCompare(b.name,'zh-CN');return (b[mode==='created'?'created_at':'last_opened_at']||0)-(a[mode==='created'?'created_at':'last_opened_at']||0)}
function render(){const data=groups().map(g=>({...g,rows:g.rows.filter(r=>!pendingDeletes.has(r.key))})),q=$('#librarySearch').value.trim().toLowerCase(),status=$('#libraryStatus').value;const unique=new Map(data.flatMap(g=>g.rows).map(r=>[r.key,r]));$('#projectCount').textContent=unique.size;$('#reviewCount').textContent=[...unique.values()].filter(p=>p.status==='completed'&&!p.edited_at).length;if(!initialized&&researchProjects.length){expanded.add(data[0].id);initialized=true}data.sort((a,b)=>$('#librarySort').value==='name'?a.name.localeCompare(b.name,'zh-CN'):(b.last_opened_at||0)-(a.last_opened_at||0));const box=$('#projectList');const markup=data.map(g=>{const rows=g.rows.filter(r=>(!q||g.name.toLowerCase().includes(q)||r.name.toLowerCase().includes(q))&&(!status||(status==='review'?r.status==='completed'&&!r.edited_at:status==='processing'?['queued','running'].includes(r.status):r.status===status))).sort(sortRows);if((q||status)&&!rows.length)return '';const open=expanded.has(g.id)||!!q||!!status,visible=(allRows.has(g.id)||q||status)?rows:rows.slice(0,4);return `<section class="library-group ${open?'open':''}" data-group-id="${escapeHtml(g.id)}"><button class="library-group-head" aria-expanded="${open}"><span class="library-folder" aria-hidden="true">▱</span><span class="library-group-title"><strong>${escapeHtml(g.name)}</strong><small>${g.rows.length} 份访谈稿</small>${g.last_opened_at?`<small class="library-last">最近打开：${dateText(g.last_opened_at)}</small>`:''}</span><span class="library-chevron">${open?'⌄':'›'}</span></button>${open?`<div class="library-table"><div class="library-columns"><span>访谈名称</span><span>最近打开</span><span>状态</span><span>操作</span></div>${visible.map(r=>`<div class="library-row" data-row-key="${escapeHtml(r.key)}"><div class="library-row-name"><span aria-hidden="true">▤</span><strong data-rename-kind="${r.type==='uploaded'?'uploaded':'interview'}" data-rename-id="${escapeHtml(r.type==='uploaded'?r.index:r.id)}" data-rename-owner="${escapeHtml(r.owner||'')}" title="${escapeHtml(r.name)}">${escapeHtml(r.name)}</strong></div><time>${r.last_opened_at?dateText(r.last_opened_at):'尚未打开'}</time><span class="library-row-status ${escapeHtml(r.status)}">${escapeHtml(statusText(r.status))}</span><div class="library-row-actions"><button data-open ${r.status!=='completed'||openingRow?.key===r.key?'disabled':''} ${r.resume_available?'hidden':''}>${openingRow?.key===r.key?'打开中…':'打开'}</button>${r.resume_available?`<button data-resume ${resuming.has(r.id)?'disabled':''}>${resuming.has(r.id)?'校验中…':'继续转录'}</button>`:''}<button class="library-dots" data-more aria-label="更多操作：${escapeHtml(r.name)}" aria-expanded="false">⋯</button><div class="library-menu" hidden><button data-delete ${['queued','running'].includes(r.status)?'disabled':''}>删除访谈</button></div></div></div>`).join('')}${rows.length>4&&!q&&!status?`<button class="library-more-rows" data-all>${allRows.has(g.id)?'收起':'查看全部 '+rows.length+' 份访谈稿'} ›</button>`:''}${!rows.length?'<p class="empty">暂无访谈稿</p>':''}</div>`:''}</section>`}).join('')||'<div class="empty">没有匹配的访谈或项目。</div>';patchLibrary(box,markup);
box.querySelectorAll('.library-group').forEach(el=>{const id=el.dataset.groupId;el.querySelector('.library-group-head').onclick=async()=>{if(expanded.has(id)){expanded.delete(id);allRows.delete(id)}else{expanded.add(id);allRows.add(id)}render();if(id!=='unassigned'){try{await api(`/api/research-projects/${encodeURIComponent(id)}/opened`,{method:'POST'});const p=researchProjects.find(p=>p.id===id);if(p)p.last_opened_at=Date.now()/1000}catch(e){toast(e.message)}}};el.querySelector('[data-all]')?.addEventListener('click',()=>{if(allRows.has(id)){allRows.delete(id);expanded.delete(id)}else{allRows.add(id);expanded.add(id)}render()});el.querySelectorAll('[data-row-key]').forEach(row=>{const r=data.find(g=>g.id===id).rows.find(r=>r.key===row.dataset.rowKey);row.onclick=event=>{if(event.target.closest('button,.library-menu,input'))return;const button=row.querySelector('[data-open]');if(!button.disabled)button.click()};row.tabIndex=0;row.setAttribute('aria-label','打开访谈稿：'+r.name);row.onkeydown=event=>{if(event.target===row&&(event.key==='Enter'||event.key===' ')){event.preventDefault();const button=row.querySelector('[data-open]');if(!button.disabled)button.click()}};row.querySelector('[data-open]').onclick=()=>openFromLibrary(r);row.querySelector('[data-more]').onclick=()=>{const menu=row.querySelector('.library-menu'),show=menu.hidden;closeMenus();menu.hidden=!show;row.querySelector('[data-more]').setAttribute('aria-expanded',String(show))};row.querySelector('[data-resume]')?.addEventListener('click',event=>{event.stopPropagation();resumeFromLibrary(r,event.currentTarget)});row.querySelector('[data-delete]').onclick=()=>deleteFromLibrary(r)})});
 }
 window.renderInterviewLibrary=render;
 const pendingDeletes=new Set(),resuming=new Set();let deletionBusy=false;
 let openingRow=null;
 async function openFromLibrary(row){
  if(openingRow?.key===row.key)return;
  const opening={key:row.key};
  openingRow=opening;render();
  const isCurrent=()=>openingRow===opening&&root.classList.contains('active');
  try{
   const prepared=row.type==='uploaded';
   const key=prepared?(await api(`/api/research-projects/${encodeURIComponent(row.owner)}/uploaded/${row.index}/prepare`,{method:'POST'})).project_id:row.id;
   if(!isCurrent())return;
   if(!await openProject(key,null,{fromLibrary:true,isCurrent}))return;
   // Persist recent history without blocking the editor or re-fetching the library.
   api(`/api/projects/${encodeURIComponent(key)}/opened`,{method:'POST'}).then(({last_opened_at})=>{
    if(prepared)return Promise.all([loadProjects(),loadResearchProjects()]);
    const entry=projects.find(item=>item.id===key);
    if(entry&&last_opened_at>(entry.last_opened_at||0)){entry.last_opened_at=last_opened_at;render()}
   }).catch(error=>toast('最近打开记录未更新：'+error.message));
  }catch(error){if(isCurrent())toast(error.message)}
  finally{if(openingRow===opening){openingRow=null;render()}}
 }
 async function resumeFromLibrary(row,button){
  if(resuming.has(row.id))return;
  resuming.add(row.id);button.disabled=true;button.textContent='校验中…';
  const element=button.closest('.library-row');element?.querySelector('.library-resume-error')?.remove();
  try{
   const result=await api(`/api/projects/${encodeURIComponent(row.id)}/resume-transcription`,{method:'POST'});
   toast(result.next_chunk?`校验通过，从第${result.next_chunk}段继续转录`:'校验通过，正在保存最终结果');
   await loadProjects();await loadStatus();startPolling();
  }catch(error){
   toast(error.message);
   if(element?.isConnected){const message=document.createElement('div');message.className='library-resume-error';message.setAttribute('role','alert');message.textContent=error.message;element.append(message);}
  }finally{resuming.delete(row.id);if(button.isConnected){button.disabled=false;button.textContent='继续转录';}}
 }
 async function deleteFromLibrary(r){
  if(deletionBusy){toast('上一份访谈正在删除，请稍候');return}
  closeMenus();if(!await confirmDelete(r.name))return;
  if(deletionBusy)return;
  deletionBusy=true;pendingDeletes.add(r.key);render();
  let committed=false;
  try{
   const interviewId=r.type==='uploaded'?(await api(`/api/research-projects/${encodeURIComponent(r.owner)}/uploaded/${r.index}/prepare`,{method:'POST'})).project_id:r.id;
   await api(`/api/projects/${encodeURIComponent(interviewId)}`,{method:'DELETE'});
   committed=true;
   // Update local membership before fetching, so a failed refresh cannot resurrect a deleted item.
   if(r.type==='uploaded')researchProjects.find(p=>p.id===r.owner)?.uploaded_transcripts.splice(r.index,1);
   else{
    projects=projects.filter(p=>p.id!==r.id);
    researchProjects.forEach(p=>{p.interview_ids=(p.interview_ids||[]).filter(i=>i!==r.id);p.uploaded_transcripts=(p.uploaded_transcripts||[]).filter(u=>u.workspace_project_id!==r.id)});
   }
   if(selected===r.id){selected=null;selectedProject=null;analysisData=null;currentMemoMaterial=null;switchView('workspace')}
   await refreshAfterDelete(r);
  }catch(e){toast(committed?'访谈已删除，但列表同步失败，请稍后重试':'删除失败，已恢复访谈：'+e.message)}
  finally{pendingDeletes.delete(r.key);deletionBusy=false;render()}
 }
 function patchLibrary(box,markup){
  if(!libraryReady){
   $('#projectCount').textContent=$('#reviewCount').textContent='—';
   markup=libraryFailed?'<div class="empty" role="status">访谈资料读取失败。 <button type="button" class="soft" data-retry-library>重试</button></div>':'<div class="empty" role="status">正在读取访谈资料…</div>';
  }
  if(libraryReady && !projects.length && !researchProjects.length && !$('#librarySearch').value.trim() && !$('#libraryStatus').value && document.querySelector('script[data-workbench-accounts]')){
   markup='<div class="empty">这是你的独立资料库，导入第一份访谈即可开始分析。 <button type="button" class="soft" data-first-import>导入访谈</button></div>';
  }
  const template=document.createElement('template');template.innerHTML=markup;
  function key(node){return node.nodeType===1?(node.dataset.groupId||node.dataset.rowKey||''):''}
  function reconcile(parent,desired){
   const existing=[...parent.childNodes],used=new Set();
   [...desired.childNodes].forEach((fresh,index)=>{
    const id=key(fresh);
    let old=id?existing.find(n=>!used.has(n)&&key(n)===id):existing[index];
    if(old&&(used.has(old)||key(old)!==id||old.nodeType!==fresh.nodeType||old.nodeName!==fresh.nodeName))old=null;
    const node=old||fresh.cloneNode(true);used.add(node);
    if(old){
     if(node.nodeType===3){if(node.textContent!==fresh.textContent)node.textContent=fresh.textContent}
     else if(node.nodeType===1){
      for(const attr of [...node.attributes])if(!fresh.hasAttribute(attr.name))node.removeAttribute(attr.name);
      for(const attr of [...fresh.attributes])if(node.getAttribute(attr.name)!==attr.value)node.setAttribute(attr.name,attr.value);
      reconcile(node,fresh);
     }
    }
    const at=parent.childNodes[index];if(at!==node)parent.insertBefore(node,at||null);
   });
   for(const node of existing)if(!used.has(node)&&node.parentNode===parent)node.remove();
  }
  reconcile(box,template.content);
 }
 async function refreshAfterDelete(deletedRow){
  const scrollers=[document.scrollingElement,...document.querySelectorAll('main,#workspace')].filter(Boolean);
  const positions=scrollers.map(node=>[node,node.scrollTop]);
  const [latestProjects,latestResearch]=await Promise.all([api('/api/projects'),api('/api/research-projects?summaries=true')]);
  projects=latestProjects;researchProjects=latestResearch;
  if(selectedResearchProject)selectedResearchProject=researchProjects.find(p=>p.id===selectedResearchProject.id)||null;
  if(!selected){
   pendingAccepted.clear();renderTranscript('');setCodingText('');$('#memoSource').dataset.text='';
   for(const id of ['saveBtn','optimizeBtn','goAnalysisBtn'])$('#'+id).disabled=true;
  }
  render();renderEditorProjects();renderMemoSwitcher();renderComparisonHistory();
  document.dispatchEvent(new CustomEvent('interview-library-updated',{detail:{deletedId:deletedRow.id}}));
  requestAnimationFrame(()=>positions.forEach(([node,top])=>{node.scrollTop=top}));
  toast('已移入回收站，7天内可在设置中恢复');
 }
 function closeMenus(){root.querySelectorAll('.library-menu').forEach(m=>m.hidden=true);root.querySelectorAll('[data-more]').forEach(b=>b.setAttribute('aria-expanded','false'))}
 document.addEventListener('click',e=>{if(!e.target.closest('.library-row-actions'))closeMenus()});document.addEventListener('keydown',e=>{if(e.key==='Escape')closeMenus()});
 loadProjects=async initial=>{projects=initial??await api('/api/projects');render()};const oldResearch=loadResearchProjects;loadResearchProjects=async initial=>{await oldResearch(initial);render()};const oldStatus=loadStatus;loadStatus=async initial=>{await oldStatus(initial);const state=$('#activeState');const busy=state.textContent!=='空闲';state.textContent=busy?'正在处理任务':'当前无处理任务';state.closest('.library-activity').classList.toggle('is-busy',busy)};
 let libraryReady=false,libraryFailed=false;
 async function loadInitialLibrary(initial){
  libraryFailed=false;render();
  try{const boot=await initial;loadStatus(boot?.status).catch(e=>toast(e.message));await Promise.all([loadProjects(boot?.projects),loadResearchProjects(boot?.research)]);libraryReady=true;render();if(projects.some(p=>['queued','running'].includes(p.status)))startPolling();}
  catch(e){libraryFailed=true;render();toast(e.message);}
 }
 $('#projectList').addEventListener('click',e=>{if(e.target.closest('[data-first-import]'))$('#importTranscriptBtn').click();if(e.target.closest('[data-retry-library]'))loadInitialLibrary()});
 ['librarySearch','libraryStatus','librarySort'].forEach(id=>$('#'+id).addEventListener(id==='librarySearch'?'input':'change',render));loadInitialLibrary(window.workbenchInitialLibrary);
})();
