/* Library-only presentation. Research membership remains the source of truth. */
(()=>{
 const expanded=new Set(),allRows=new Set();let initialized=false;
 const root=$('#workspace'), overview=root.querySelector('.overview-grid');
 overview.innerHTML='<span>全部访谈 <strong id="projectCount">0</strong></span><span>｜</span><span>待校订 <strong id="reviewCount">0</strong></span><span class="library-activity"><i></i><span id="activeState">当前无处理任务</span></span>';
 root.querySelector('.section-head').innerHTML='<h2>访谈资料</h2><div class="library-tools"><input id="librarySearch" placeholder="搜索访谈或项目" aria-label="搜索访谈或项目"><select id="libraryStatus" aria-label="访谈状态"><option value="">全部状态</option><option value="completed">已完成</option><option value="review">待校订</option><option value="processing">处理中</option><option value="failed">失败</option></select><select id="librarySort" aria-label="访谈排序"><option value="opened">最近打开</option><option value="created">最近导入</option><option value="name">名称排序</option></select></div>';
 const dialog=document.createElement('dialog');dialog.className='library-delete-dialog';dialog.innerHTML='<h3>删除访谈？</h3><p class="library-delete-name"></p><p>将从资料列表、项目及后续分析材料中移除。包含该访谈的分析记录一并归档，原文件保留在本机恢复归档中。</p><div class="dialog-actions"><button type="button" class="ghost" data-cancel>取消</button><button type="button" class="danger" data-confirm>删除访谈</button></div>';document.body.append(dialog);
 function confirmDelete(name){dialog.querySelector('.library-delete-name').textContent=name;dialog.showModal();return new Promise(resolve=>{const finish=v=>{dialog.close();dialog.oncancel=null;resolve(v)};dialog.querySelector('[data-cancel]').onclick=()=>finish(false);dialog.querySelector('[data-confirm]').onclick=()=>finish(true);dialog.oncancel=e=>{e.preventDefault();finish(false)}})}
 function groups(){const assigned=new Set(),byId=new Map(projects.map(p=>[p.id,p]));const result=researchProjects.map(p=>{const rows=[],seen=new Set();for(const id of p.interview_ids||[]){const w=byId.get(id);if(w){rows.push({...w,key:id,owner:p.id,type:'workspace'});seen.add(id);assigned.add(id)}}(p.uploaded_transcripts||[]).forEach((u,index)=>{const id=u.workspace_project_id; if(id)assigned.add(id);if(id&&seen.has(id))return;const w=byId.get(id);rows.push({...u,...(w||{}),name:w?.name||u.name,key:id||`${p.id}:${index}`,id:id||'',owner:p.id,index,type:id&&w?'workspace':'uploaded',status:w?.status||'completed'});if(id)seen.add(id)});return {...p,rows}});const rows=projects.filter(p=>!assigned.has(p.id)).map(p=>({...p,key:p.id,type:'workspace'}));if(rows.length)result.push({id:'unassigned',name:'未归入项目的访谈',rows});return result}
 function sortRows(a,b){const mode=$('#librarySort').value;if(mode==='name')return a.name.localeCompare(b.name,'zh-CN');return (b[mode==='created'?'created_at':'last_opened_at']||0)-(a[mode==='created'?'created_at':'last_opened_at']||0)}
function render(){const data=groups().map(g=>({...g,rows:g.rows.filter(r=>!pendingDeletes.has(r.key))})),q=$('#librarySearch').value.trim().toLowerCase(),status=$('#libraryStatus').value;const unique=new Map(data.flatMap(g=>g.rows).map(r=>[r.key,r]));$('#projectCount').textContent=unique.size;$('#reviewCount').textContent=[...unique.values()].filter(p=>p.status==='completed'&&!p.edited_at).length;if(!initialized&&researchProjects.length){expanded.add(data[0].id);initialized=true}data.sort((a,b)=>$('#librarySort').value==='name'?a.name.localeCompare(b.name,'zh-CN'):(b.last_opened_at||0)-(a.last_opened_at||0));const box=$('#projectList');const markup=data.map(g=>{const rows=g.rows.filter(r=>(!q||g.name.toLowerCase().includes(q)||r.name.toLowerCase().includes(q))&&(!status||(status==='review'?r.status==='completed'&&!r.edited_at:status==='processing'?['queued','running'].includes(r.status):r.status===status))).sort(sortRows);if((q||status)&&!rows.length)return '';const open=expanded.has(g.id)||!!q||!!status,visible=(allRows.has(g.id)||q||status)?rows:rows.slice(0,4);return `<section class="library-group ${open?'open':''}" data-group-id="${escapeHtml(g.id)}"><button class="library-group-head" aria-expanded="${open}"><span class="library-folder" aria-hidden="true">▱</span><span class="library-group-title"><strong>${escapeHtml(g.name)}</strong><small>${g.rows.length} 份访谈稿</small>${g.last_opened_at?`<small class="library-last">最近打开：${dateText(g.last_opened_at)}</small>`:''}</span><span class="library-chevron">${open?'⌄':'›'}</span></button>${open?`<div class="library-table"><div class="library-columns"><span>访谈名称</span><span>最近打开</span><span>状态</span><span>操作</span></div>${visible.map(r=>`<div class="library-row" data-row-key="${escapeHtml(r.key)}"><div class="library-row-name"><span aria-hidden="true">▤</span><strong data-rename-kind="${r.type==='uploaded'?'uploaded':'interview'}" data-rename-id="${escapeHtml(r.type==='uploaded'?r.index:r.id)}" data-rename-owner="${escapeHtml(r.owner||'')}" title="${escapeHtml(r.name)}">${escapeHtml(r.name)}</strong></div><time>${r.last_opened_at?dateText(r.last_opened_at):'尚未打开'}</time><span class="library-row-status ${escapeHtml(r.status)}">${escapeHtml(statusText(r.status))}</span><div class="library-row-actions"><button data-open ${['queued','running'].includes(r.status)?'disabled':''}>打开</button><button class="library-dots" data-more aria-label="更多操作：${escapeHtml(r.name)}" aria-expanded="false">⋯</button><div class="library-menu" hidden><button data-delete ${['queued','running'].includes(r.status)?'disabled':''}>删除访谈</button></div></div></div>`).join('')}${rows.length>4&&!q&&!status?`<button class="library-more-rows" data-all>${allRows.has(g.id)?'收起':'查看全部 '+rows.length+' 份访谈稿'} ›</button>`:''}${!rows.length?'<p class="empty">暂无访谈稿</p>':''}</div>`:''}</section>`}).join('')||'<div class="empty">没有匹配的访谈或项目。</div>';patchLibrary(box,markup);
box.querySelectorAll('.library-group').forEach(el=>{const id=el.dataset.groupId;el.querySelector('.library-group-head').onclick=async()=>{if(expanded.has(id)){expanded.delete(id);allRows.delete(id)}else{expanded.add(id);allRows.add(id)}render();if(id!=='unassigned'){try{await api(`/api/research-projects/${encodeURIComponent(id)}/opened`,{method:'POST'});const p=researchProjects.find(p=>p.id===id);if(p)p.last_opened_at=Date.now()/1000}catch(e){toast(e.message)}}};el.querySelector('[data-all]')?.addEventListener('click',()=>{if(allRows.has(id)){allRows.delete(id);expanded.delete(id)}else{allRows.add(id);expanded.add(id)}render()});el.querySelectorAll('[data-row-key]').forEach(row=>{const r=data.find(g=>g.id===id).rows.find(r=>r.key===row.dataset.rowKey);row.onclick=event=>{if(event.target.closest('button,.library-menu,input'))return;const button=row.querySelector('[data-open]');if(!button.disabled)button.click()};row.tabIndex=0;row.setAttribute('aria-label','打开访谈稿：'+r.name);row.onkeydown=event=>{if(event.target===row&&(event.key==='Enter'||event.key===' ')){event.preventDefault();const button=row.querySelector('[data-open]');if(!button.disabled)button.click()}};row.querySelector('[data-open]').onclick=async()=>{try{let key=r.id;if(r.type==='uploaded')key=(await api(`/api/research-projects/${encodeURIComponent(r.owner)}/uploaded/${r.index}/prepare`,{method:'POST'})).project_id;await openProject(key);await api(`/api/projects/${encodeURIComponent(key)}/opened`,{method:'POST'});await Promise.all([loadProjects(),loadResearchProjects()])}catch(e){toast(e.message)}};row.querySelector('[data-more]').onclick=()=>{const menu=row.querySelector('.library-menu'),show=menu.hidden;closeMenus();menu.hidden=!show;row.querySelector('[data-more]').setAttribute('aria-expanded',String(show))};row.querySelector('[data-delete]').onclick=()=>deleteFromLibrary(r)})});
 }
 window.renderInterviewLibrary=render;
 const pendingDeletes=new Set();let deletionBusy=false;
 async function deleteFromLibrary(r){
  if(deletionBusy){toast('上一份访谈正在删除，请稍候');return}
  closeMenus();if(!await confirmDelete(r.name))return;
  if(deletionBusy)return;
  deletionBusy=true;pendingDeletes.add(r.key);render();
  let committed=false;
  try{
   await api(r.type==='uploaded'?`/api/research-projects/${encodeURIComponent(r.owner)}/materials/uploaded/${r.index}`:`/api/projects/${encodeURIComponent(r.id)}`,{method:'DELETE'});
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
  const [latestProjects,latestResearch]=await Promise.all([api('/api/projects'),api('/api/research-projects')]);
  projects=latestProjects;researchProjects=latestResearch;
  if(selectedResearchProject)selectedResearchProject=researchProjects.find(p=>p.id===selectedResearchProject.id)||null;
  if(!selected){
   pendingAccepted.clear();renderTranscript('');setCodingText('');$('#memoSource').dataset.text='';
   for(const id of ['saveBtn','optimizeBtn','goAnalysisBtn'])$('#'+id).disabled=true;
  }
  render();renderEditorProjects();renderMemoSwitcher();renderComparisonHistory();
  document.dispatchEvent(new CustomEvent('interview-library-updated',{detail:{deletedId:deletedRow.id}}));
  requestAnimationFrame(()=>positions.forEach(([node,top])=>{node.scrollTop=top}));
  toast('访谈已删除');
 }
 function closeMenus(){root.querySelectorAll('.library-menu').forEach(m=>m.hidden=true);root.querySelectorAll('[data-more]').forEach(b=>b.setAttribute('aria-expanded','false'))}
 document.addEventListener('click',e=>{if(!e.target.closest('.library-row-actions'))closeMenus()});document.addEventListener('keydown',e=>{if(e.key==='Escape')closeMenus()});
 loadProjects=async()=>{projects=await api('/api/projects');render()};const oldResearch=loadResearchProjects;loadResearchProjects=async()=>{await oldResearch();render()};const oldStatus=loadStatus;loadStatus=async()=>{await oldStatus();$('#activeState').textContent=$('#activeState').textContent==='空闲'?'当前无处理任务':'正在处理任务'};
 ['librarySearch','libraryStatus','librarySort'].forEach(id=>$('#'+id).addEventListener(id==='librarySearch'?'input':'change',render));render();Promise.all([loadProjects(),loadResearchProjects(),loadStatus()]).catch(e=>toast(e.message));
})();
