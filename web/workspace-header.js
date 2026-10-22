// Shared presentation adapter. Existing controls retain their identity and handlers.
(() => {
 const main=document.querySelector('main'),find=s=>document.querySelector(s);
 class WorkspaceHeader {
  constructor(){
   this.element=document.createElement('header');this.element.className='workspace-header';
   this.element.innerHTML='<div class="workspace-header-row"><div class="workspace-breadcrumb"><span></span><i>/</i><strong></strong></div><div class="workspace-header-right"><div class="workspace-selector-slot"></div><div class="workspace-status-slot"></div><div class="workspace-action-slot"></div></div></div><div class="workspace-tab-slot" hidden></div>';
   const tools=document.createElement('div');tools.className='editor-tool-row';tools.hidden=true;tools.innerHTML='<div class="editor-tool-left"></div><div class="editor-tool-right"></div>';this.element.append(tools);this.tools=tools;
   this.slots={selector:this.element.querySelector('.workspace-selector-slot'),status:this.element.querySelector('.workspace-status-slot'),actions:this.element.querySelector('.workspace-action-slot'),tabs:this.element.querySelector('.workspace-tab-slot'),toolsLeft:tools.firstElementChild,toolsRight:tools.lastElementChild};
   this.mounted=new Map();this.parking=document.createElement('div');this.parking.hidden=true;main.append(this.parking);main.prepend(this.element);
   this.resize=new ResizeObserver(()=>main.style.setProperty('--workspace-header-height',this.element.getBoundingClientRect().height+'px'));this.resize.observe(this.element);
  }
  render({module,page,selector=[],status=[],actions=[],tabs=[],toolsLeft=[],toolsRight=[]}){
   const moduleEl=this.element.querySelector('.workspace-breadcrumb span'),pageEl=this.element.querySelector('.workspace-breadcrumb strong');
   if(moduleEl.textContent!==module)moduleEl.textContent=module;
   if(pageEl.textContent!==page)pageEl.textContent=page;
   const groups={selector,status,actions,tabs,toolsLeft,toolsRight},wanted=new Set(Object.values(groups).flat().filter(Boolean));
   const hideTools=!(toolsLeft.length||toolsRight.length);if(this.tools.hidden!==hideTools)this.tools.hidden=hideTools;
   for(const [node,anchor] of this.mounted)if(!wanted.has(node)){if([...wanted].some(parent=>parent.contains(node)))anchor.remove();else anchor.replaceWith(node);this.mounted.delete(node);}
   for(const [slot,nodes] of Object.entries(groups)){
    let previous=null;
    for(const node of nodes.filter(Boolean)){
     if(!this.mounted.has(node)){if(!node.isConnected)this.parking.append(node);const anchor=document.createComment('header-control');node.before(anchor);this.mounted.set(node,anchor);}
     const container=this.slots[slot],next=previous?previous.nextSibling:container.firstChild;
     if(node.parentNode!==container||next!==node)container.insertBefore(node,next);
     previous=node;
    }
   }
   const hideTabs=!tabs.filter(Boolean).length;if(this.slots.tabs.hidden!==hideTabs)this.slots.tabs.hidden=hideTabs;
   for(const picker of this.slots.selector.querySelectorAll('select')){
    const full=picker.selectedOptions[0]?.textContent||'';if(picker.title!==full)picker.title=full;
   }
  }
 }
 main.classList.add('workspace-main');
 const legacy=find('main > .topbar');legacy.classList.add('workspace-legacy-topbar');
 const header=new WorkspaceHeader();
 const editorPicker=document.createElement('select');editorPicker.id='editorInterviewSelect';editorPicker.setAttribute('aria-label','选择校订访谈稿');
 const editorCascade=document.createElement('div');editorCascade.className='memo-selector-control editor-cascade-control';editorCascade.style.position='relative';
 const editorCascadeButton=document.createElement('button');editorCascadeButton.type='button';editorCascadeButton.setAttribute('aria-label','选择校订访谈稿');editorCascadeButton.setAttribute('aria-haspopup','true');editorCascadeButton.setAttribute('aria-expanded','false');
 const editorCascadeMenu=document.createElement('div');editorCascadeMenu.className='comparison-history-list memo-cascade-menu';editorCascadeMenu.hidden=true;editorPicker.hidden=true;editorCascade.append(editorPicker,editorCascadeButton,editorCascadeMenu);header.parking.append(editorCascade);
 function editorGroups(){
  editorCascadeMenu.replaceChildren();editorCascadeMenu.hidden=false;editorCascadeButton.setAttribute('aria-expanded','true');
  const assigned=new Set(researchProjects.flatMap(p=>[...(p.interviews||[]).map(x=>String(x.id)),...(p.uploaded_transcripts||[]).filter(x=>x.workspace_project_id).map(x=>String(x.workspace_project_id))]));
  const groups=researchProjects.map(project=>({project,name:project.name,rows:[...(project.interviews||[]).map(x=>({name:x.name,id:String(x.id)})),...(project.uploaded_transcripts||[]).map((x,index)=>({name:x.name,id:x.workspace_project_id?String(x.workspace_project_id):null,index}))]}));
  const ungrouped=projects.filter(p=>p.status==='completed'&&!assigned.has(String(p.id))).map(p=>({name:p.name,id:String(p.id)}));if(ungrouped.length)groups.push({project:null,name:'未归入项目的访谈',rows:ungrouped});
  for(const group of groups){
   const row=document.createElement('div');row.className='memo-cascade-group';const button=document.createElement('button');button.type='button';button.className='memo-cascade-parent';button.setAttribute('aria-haspopup','true');button.setAttribute('aria-expanded','false');
   const name=document.createElement('span');name.textContent=group.name;const count=document.createElement('small');count.textContent=group.rows.length+' 份';const arrow=document.createElement('span');arrow.textContent='›';button.append(name,count,arrow);
   const sub=document.createElement('div');sub.className='memo-cascade-sub';sub.hidden=true;
   const expand=()=>{for(const other of editorCascadeMenu.querySelectorAll('.memo-cascade-sub'))other.hidden=true;for(const other of editorCascadeMenu.querySelectorAll('.memo-cascade-parent'))other.setAttribute('aria-expanded','false');sub.hidden=false;button.setAttribute('aria-expanded','true');sub.classList.remove('open-left');sub.classList.toggle('open-left',sub.getBoundingClientRect().right>window.innerWidth-12);};button.onclick=expand;row.onmouseenter=expand;
   button.onkeydown=e=>{if(e.key==='ArrowRight'){e.preventDefault();expand();sub.querySelector('button')?.focus();}};
   for(const material of group.rows){const item=document.createElement('button');item.type='button';item.textContent=material.name;item.title=material.name;item.classList.toggle('active',material.id===String(selected));
    item.onclick=async()=>{if(editorLoading)return;if(editorDirty.get(String(selected))&&!confirm('当前校订有未保存修改，切换将放弃这些修改。继续吗？'))return;editorCascadeMenu.hidden=true;editorCascadeButton.setAttribute('aria-expanded','false');editorLoading=true;sync();try{let id=material.id;if(!id){const result=await api(`/api/research-projects/${group.project.id}/uploaded/${material.index}/prepare`,{method:'POST'});id=result.project_id;await loadProjects();await loadResearchProjects();}await openProject(id);selectedResearchProject=group.project;editorDirty.delete(String(selected));editorSaved.delete(String(selected));}catch(error){toast(error.message);}finally{editorLoading=false;sync();}};
    item.onkeydown=e=>{if(e.key==='ArrowLeft'){e.preventDefault();sub.hidden=true;button.setAttribute('aria-expanded','false');button.focus();}};sub.append(item);}
   if(!group.rows.length){const empty=document.createElement('p');empty.textContent='暂无访谈稿';sub.append(empty);}row.append(button,sub);editorCascadeMenu.append(row);
  }
  if(!groups.length)editorCascadeMenu.textContent='暂无访谈稿';
 }
 editorCascadeButton.onclick=()=>{if(editorLoading)return;if(editorCascadeMenu.hidden)editorGroups();else{editorCascadeMenu.hidden=true;editorCascadeButton.setAttribute('aria-expanded','false');}};
 document.addEventListener('click',e=>{if(!editorCascade.contains(e.target)){editorCascadeMenu.hidden=true;editorCascadeButton.setAttribute('aria-expanded','false');}});
 editorCascade.addEventListener('keydown',e=>{if(e.key==='Escape'){editorCascadeMenu.hidden=true;editorCascadeButton.setAttribute('aria-expanded','false');editorCascadeButton.focus();}});
 const editorStatus=document.createElement('span');editorStatus.id='editorSaveStatus';editorStatus.setAttribute('role','status');
 const editorFind=document.createElement('button');editorFind.type='button';editorFind.id='editorFindButton';editorFind.innerHTML='<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/></svg><span>查找</span>';
 header.parking.append(editorFind);
 const themeStatus=document.createElement('span');themeStatus.setAttribute('role','status');
 const memoTextTab=document.createElement('button');memoTextTab.type='button';memoTextTab.textContent='访谈纪要';memoTextTab.onclick=()=>{switchView('analysis','familiarity');window.showMemoTextView?.();};
 const codingTab=document.createElement('button');codingTab.type='button';codingTab.textContent='访谈编码';codingTab.onclick=()=>{collectMemo();switchView('analysis','coding');};
 const sourceSearchTab=document.createElement('button');sourceSearchTab.type='button';sourceSearchTab.textContent='查找主题原文';sourceSearchTab.onclick=()=>{collectMemo();window.openSourceSearch?.();};
 // Keep dynamically loaded structure/network extensions discoverable after mounting.
 let structureButton=null,networkTabs=null,networkActions=null,memoSelector=null,editorOptions='',editorLoading=false;
 function writeStatus(node,text){if(node.textContent!==text)node.textContent=text;}
 function sync(){
  const syncStarted=performance.now();
  observer.disconnect();
  try{
   networkTabs=networkTabs||find('.network-tabs');networkActions=networkActions||find('.network-head-actions');
   structureButton=structureButton||find('#memoStructureModeBtn');
   memoSelector=memoSelector||find('#memoWorkspace .memo-actions button[aria-haspopup]')?.parentElement;
   const activeView=find('main > .view.active'),panel=activeView?.id==='analysis'?find('#analysis > .tab-panel.active'):null;
   const id=panel?.id||activeView?.id||'workspace';
   const config={module:['workspace','editor'].includes(id)?'访谈整理':'研究项目',page:({workspace:'全部访谈',editor:'文字校订',projectManage:'项目管理',familiarity:'单篇访谈分析',focused:'跨访谈分析',coding:'访谈编码',matrix:'比较分析',projectData:'项目资料'})[id]||'访谈分析'};
   if(id==='workspace'){
    config.actions=[find('#importTranscriptBtn'),find('#newProjectBtn')];
    config.actions.forEach(n=>n.hidden=false);
    if(find('#currentProject').textContent==='全部项目')find('#currentProject').textContent='全部访谈';
   }else if(id==='editor'){
    const rows=projects.filter(p=>p.status==='completed'),signature=JSON.stringify(rows.map(p=>[p.id,p.name]));
    if(signature!==editorOptions){
     editorOptions=signature;editorPicker.replaceChildren(new Option('请选择访谈稿',''),...rows.map(p=>new Option(p.name,String(p.id))));
    }
    editorPicker.value=selected?String(selected):'';
    editorPicker.disabled=editorLoading;
    editorCascadeButton.disabled=editorLoading;
    const editorLabel=(editorLoading?'正在读取…':selectedProject?.name||'请选择访谈稿')+' ▾';if(editorCascadeButton.textContent!==editorLabel)editorCascadeButton.textContent=editorLabel;
    if(editorLoading)for(const id of ['saveBtn','optimizeBtn','goAnalysisBtn'])find('#'+id).disabled=true;
    writeStatus(editorStatus,editorLoading?'正在读取…':selected?(editorDirty.get(String(selected))?'未保存':editorSaved.get(String(selected))||find('#editorHint').textContent):'');
    config.selector=[editorCascade];config.status=[editorStatus];
    config.actions=[find('#saveBtn')];
    config.toolsLeft=[find('.editor-history'),find('#editorFindControl')||editorFind].filter(Boolean);
    config.toolsRight=[find('.editor-ai-split'),find('#goAnalysisBtn'),find('.audio-menu')||find('#audioFollowToggle')].filter(Boolean);
   }else if(id==='projectManage'){
    config.actions=[find('#researchBackBtn'),find('#deleteResearchBtn'),find('#createResearchBtn')];
   }else if(id==='familiarity'||id==='coding'||id==='sourceSearch'){
    config.page='单篇访谈分析';
    const picker=find('#memoInterviewSelect');picker.hidden=!!memoSelector;
    if(memoSelector){memoSelector.classList.add('memo-selector-control');const toggle=memoSelector.querySelector('button');toggle.title=picker.selectedOptions[0]?.textContent||'请选择访谈稿';toggle.setAttribute('aria-label','选择访谈稿');}
    config.selector=id==='sourceSearch'?[find('#sourceSearchInterview')]:[memoSelector||picker];config.status=id==='sourceSearch'?[]:id==='coding'?[find('#codingStatus')]:[find('#memoStatus')];
    config.actions=id==='sourceSearch'?[]:id==='coding'?[find('#saveAnalysisBtn'),find('#aiCodeBtn')]:[find('#saveMemoBtn'),find('#generateMemoBtn')];
    if(id==='coding'){
     find('#saveAnalysisBtn').disabled=!selected;
     find('#aiCodeBtn').disabled=!selected||find('#aiCodeBtn').classList.contains('is-loading');
    }
    if(structureButton&&!structureButton.dataset.singleAnalysis){
     structureButton.dataset.singleAnalysis='true';
     structureButton.onclick=()=>{collectMemo();switchView('analysis','familiarity');window.showMemoStructureView?.();};
    }
    config.tabs=[memoTextTab,structureButton,codingTab].filter(Boolean);
    sourceSearchTab.classList.add('workspace-tab-action');
    config.tabs.push(sourceSearchTab);writeStatus(sourceSearchTab,'查找原文');
    if(structureButton)writeStatus(structureButton,'纪要结构');
    sourceSearchTab.classList.toggle('active',id==='sourceSearch');
    if(id==='sourceSearch')find('.nav-item[data-tab="familiarity"]')?.classList.add('active');
    codingTab.classList.toggle('active',id==='coding');
    if(structureButton){
     const showing=!find('#memoStructure')?.hidden;
     memoTextTab.classList.toggle('active',id==='familiarity'&&!showing);memoTextTab.setAttribute('aria-pressed',String(id==='familiarity'&&!showing));
     structureButton.classList.toggle('active',id==='familiarity'&&showing);
    }
   }else if(id==='focused'){
    config.selector=[find('#themeHistorySelect')];config.tabs=networkTabs?[networkTabs]:[];
    const network=find('#focused').classList.contains('network-active');
    if(window.codingTree?.active){writeStatus(themeStatus,currentThemeAnalysis?(currentThemeAnalysis._saved?'已保存':'未保存'):'');config.status=[themeStatus];config.actions=[find('#saveThemeBtn')];}
    else if(network&&networkActions){config.status=[find('.network-status')];config.actions=[networkActions];}
    else{
     writeStatus(themeStatus,currentThemeAnalysis?(currentThemeAnalysis._saved?'已保存':'未保存'):'');
     config.status=[themeStatus];config.actions=[find('#saveThemeBtn')];
    }
   }
   if(id==='focused'&&window.wordCooccurrence?.active){const [picker,status,save,next]=window.wordCooccurrence.controls;config.selector=[picker,window.wordCooccurrence.historyPicker];config.status=[status];config.actions=[save,next,window.wordCooccurrence.saveResult];}
   header.element.classList.toggle('cross-header',id==='focused');
   window.researchNavigation?.configure(config,id);
   if(id==='coding')window.aiCodingDemo?.configure(config);
   header.render(config);
   // Promote at most one existing action, without creating a new saving/generation path.
   const primaryId=({workspace:'newProjectBtn',editor:'saveBtn',projectManage:'createResearchBtn',familiarity:'generateMemoBtn',focused:find('#focused').classList.contains('network-active')?'':'saveThemeBtn',coding:'aiCodeBtn'})[id];
   for(const button of header.slots.actions.querySelectorAll('button'))button.classList.toggle('workspace-primary',button.id===primaryId||button.dataset.action==='export');
   for(const b of header.slots.tabs.querySelectorAll('button')){const pressed=String(b.classList.contains('active'));if(b.getAttribute('aria-pressed')!==pressed)b.setAttribute('aria-pressed',pressed);}
  }finally{header.element.dataset.syncCount=String(Number(header.element.dataset.syncCount||0)+1);header.element.dataset.lastSyncMs=(performance.now()-syncStarted).toFixed(2);observer.observe(main,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:['class','hidden','disabled','aria-pressed']});}
 }
 const editorDirty=new Map(),editorSaved=new Map();
 editorPicker.onchange=async()=>{if(!editorPicker.value||editorLoading)return;const id=editorPicker.value;editorLoading=true;sync();try{await openProject(id);editorDirty.delete(String(selected));editorSaved.delete(String(selected));}catch(error){toast(error.message);}finally{editorLoading=false;sync();}};
 const originalSave=saveTranscript;
 find('#saveBtn').onclick=async()=>{
  if(!selected)return;const id=String(selected);writeStatus(editorStatus,'保存中…');
  try{await originalSave();editorDirty.delete(id);editorSaved.set(id,'已保存');sync();}
  catch(error){writeStatus(editorStatus,'保存失败');toast(error.message);}
 };
 find('#transcript').addEventListener('input',()=>{if(selected)editorDirty.set(String(selected),true);schedule();});
 const originalMemoSave=find('#saveMemoBtn').onclick;
 find('#saveMemoBtn').onclick=async()=>{
  if(!analysisData?.familiarity_memo)return;
  writeStatus(find('#memoStatus'),'保存中…');
  try{await originalMemoSave();writeStatus(find('#memoStatus'),'已保存');schedule();}
  catch(error){writeStatus(find('#memoStatus'),'保存失败');toast(error.message);}
 };
 find('#memoPanel').addEventListener('input',()=>{if(analysisData?.familiarity_memo)writeStatus(find('#memoStatus'),'未保存');schedule();});
 let scheduled=false;
 function schedule(){if(scheduled)return;scheduled=true;requestAnimationFrame(()=>{scheduled=false;sync();});}
 const observer=new MutationObserver(schedule);
 document.addEventListener('input',schedule);document.addEventListener('change',schedule);document.addEventListener('click',event=>{if(!event.target.closest('select'))schedule();});
 sync();
 window.workspaceHeader={refresh:schedule,component:header};
})();
