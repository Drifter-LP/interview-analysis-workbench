/* Task navigation over existing analysis records. No migration or AI generation. */
(() => {
 const $ = s => document.querySelector(s);
 const make = (tag,cls,text) => {const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n;};
 const button = (text,fn) => {const n=make('button','',text);n.type='button';n.onclick=fn;return n;};
 const textIfChanged=(node,text)=>{if(node.textContent!==text)node.textContent=text;};
 const hiddenIfChanged=(node,hidden)=>{if(node.hidden!==hidden)node.hidden=hidden;};
 const attrIfChanged=(node,name,value)=>{if(node.getAttribute(name)!==value)node.setAttribute(name,value);};
 const page=$('#focused'),legacy=$('.network-tabs');
 const oldTheme=legacy.children[0],oldGraph=legacy.children[1],oldTree=[...legacy.children].find(b=>b.textContent==='主题发现树');
 let task='theme',presentation='text',comparing=false,reviewMode=false,rendering=false,codeToken=0;
 const themeRecords=new Map();
 const rememberTheme=()=>{if(currentThemeAnalysis?._researchProjectId)themeRecords.set(currentThemeAnalysis._researchProjectId,currentThemeAnalysis);};
 const previousFocusedRender=renderFocusedAnalysis;
 renderFocusedAnalysis=function(){rememberTheme();if(currentThemeAnalysis?._researchProjectId!==selectedResearchProject?.id)currentThemeAnalysis=themeRecords.get(selectedResearchProject?.id)||null;previousFocusedRender();};
 $('#themePanel').addEventListener('input',()=>{if(currentThemeAnalysis){currentThemeAnalysis._saved=false;rememberTheme();window.workspaceHeader?.refresh();}});
 const tasks=make('div','research-task-tabs');tasks.setAttribute('role','group');tasks.setAttribute('aria-label','跨访谈研究任务');
 const themeViews=make('div','research-view-controls'),wordSettings=button('分析设置',()=>{const step=window.wordCooccurrence.step;window.wordCooccurrence.setStep(step===4?3:4);});
 const themeButtons=new Map(),taskButtons=new Map();
 const themeSegments=make('div','research-view-segments');themeViews.append(themeSegments);
 const resultPicker=make('div','research-result-picker');
 const resultTrigger=button('',()=>{resultMenu.hidden=!resultMenu.hidden;resultTrigger.setAttribute('aria-expanded',String(!resultMenu.hidden));});resultTrigger.className='research-result-trigger';resultTrigger.setAttribute('aria-label','主题结果展示方式');resultTrigger.setAttribute('aria-haspopup','menu');resultTrigger.setAttribute('aria-expanded','false');
 const resultMenu=make('div','research-result-menu');resultMenu.hidden=true;resultMenu.setAttribute('role','menu');resultMenu.setAttribute('aria-label','主题结果展示选项');
 const resultLabel=make('span','research-result-label'),resultArrow=make('span','research-result-arrow');resultArrow.setAttribute('aria-hidden','true');resultTrigger.append(resultLabel,resultArrow);
 const resultItems=new Map();
 for(const [value,name] of [['text','文字结果'],['tree','发现树']]){const item=button(name,()=>{resultMenu.hidden=true;resultTrigger.setAttribute('aria-expanded','false');choosePresentation(value);resultTrigger.focus();});item.setAttribute('role','menuitemradio');resultItems.set(value,item);resultMenu.append(item);}
 resultPicker.append(resultTrigger,resultMenu);
 function updateResultPicker(){textIfChanged(resultLabel,presentation==='tree'?'发现树':'文字结果');for(const [value,item]of resultItems)attrIfChanged(item,'aria-checked',String(value===presentation));}
 document.addEventListener('click',event=>{if(!resultPicker.contains(event.target)&&!resultMenu.hidden){resultMenu.hidden=true;attrIfChanged(resultTrigger,'aria-expanded','false');}});
 resultPicker.addEventListener('keydown',event=>{if(event.key==='Escape'){event.preventDefault();resultMenu.hidden=true;resultTrigger.setAttribute('aria-expanded','false');resultTrigger.focus();}else if(event.key==='ArrowDown'||event.key==='ArrowUp'){event.preventDefault();resultMenu.hidden=false;resultTrigger.setAttribute('aria-expanded','true');const items=[...resultItems.values()],index=items.indexOf(document.activeElement),next=event.key==='ArrowDown'?(index+1)%items.length:(index-1+items.length)%items.length;items[next].focus();}});
 oldGraph.disabled=true;oldGraph.hidden=true;
 const projectPicker=make('select','research-project-picker');projectPicker.setAttribute('aria-label','选择分析项目');
 const scope=button('',()=>selectedResearchProject&&openResearchProject(selectedResearchProject.id));scope.className='research-material-scope';scope.setAttribute('aria-label','管理项目访谈');
 const search=button('查找原文',()=>window.openSourceSearch?.({materials:searchMaterials()}));search.className='research-source-search';
 const newAnalysis=button('新建分析',()=>openThemeDialog());newAnalysis.className='research-source-search';
 const scopeText=make('div','research-record-scope');
 window.createEvidenceDrawer=function(titleText){
  const drawer=make('dialog','wc-source-drawer'),head=make('header'),title=make('strong','',titleText),close=button('×',()=>drawer.close()),note=make('p','wc-source-note'),body=make('div','wc-source-body');close.setAttribute('aria-label','关闭原文');head.append(title,close);drawer.append(head,note,body);document.body.append(drawer);drawer.onclose=()=>drawer.remove();drawer.showModal();return{drawer,note,body};
 };
 const previousEvidence=openThemeEvidence;
 openThemeEvidence=async function(projectId,number,sourceOverride=null){
  const source=sourceOverride||(currentThemeAnalysis?.dimensions||[]).flatMap(d=>(d.findings||[]).flatMap(f=>(f.facts||[]).flatMap(fact=>fact.sources||[]))).find(s=>s.project_id===projectId&&Number(s.number)===number);
  if(!source||source.source_type!=='transcript')return previousEvidence(projectId,number,sourceOverride);
  const {drawer,note,body}=window.createEvidenceDrawer(`${source.material_name||projectId} · 原文上下文`);
  note.textContent='正在读取整篇原文…';body.textContent='';
  try{
   const data=await api(`/api/projects/${encodeURIComponent(projectId)}/transcript`);
   if(!drawer.isConnected)return;
   const text=data.text,quote=source.quote||'';
   if(typeof text!=='string')throw new Error('原文内容为空');
   let start=-1,end=-1;
   if(Number.isInteger(source.start)&&Number.isInteger(source.end)&&source.start>=0&&source.end>source.start){
    const chars=Array.from(text),candidate=chars.slice(source.start,source.end).join('');
    if(quote&&candidate===quote){start=chars.slice(0,source.start).join('').length;end=start+quote.length;}
   }
   if(start<0&&quote){const found=text.indexOf(quote);if(found>=0&&text.indexOf(quote,found+1)<0){start=found;end=found+quote.length;}}
   if(start<0){body.textContent=text;note.textContent='整篇原文 · 未能唯一定位引用，原文可能已修改；未自动标注。';return;}
   const highlight=make('mark','research-evidence-highlight',text.slice(start,end));
   body.replaceChildren(document.createTextNode(text.slice(0,start)),highlight,document.createTextNode(text.slice(end)));
   note.textContent=`整篇原文 · 青绿色为引用片段 · 位于全文约 ${Math.round(start/Math.max(1,text.length)*100)}% 处 · 只读`;
   requestAnimationFrame(()=>{if(drawer.isConnected)body.scrollTop=Math.max(0,highlight.offsetTop-body.offsetTop-body.clientHeight*.3);});
  }catch(error){if(!drawer.isConnected)return;note.textContent='整篇原文读取失败，以下仅为分析时保存的引用片段。';body.textContent=source.quote||'';}
 };
 const codePanel=$('#matrix');codePanel.classList.remove('tab-panel');codePanel.classList.add('research-code-workspace');codePanel.hidden=true;page.append(codePanel);
 codePanel.querySelector('.analysis-actions span').textContent='统计当前项目中人工确认的编码片段';
 const codeNotice=make('p','research-code-notice');codePanel.querySelector('.table-wrap').before(codeNotice);
 const memberIds=p=>[...new Set([...(p?.interview_ids||[]),...(p?.uploaded_transcripts||[]).map(x=>x.workspace_project_id)].filter(Boolean))];
 const projectMaterials=p=>[...(p?.interviews||[]).map(x=>({id:x.id,name:x.name})),...(p?.uploaded_transcripts||[]).filter(x=>x.workspace_project_id).map(x=>({id:x.workspace_project_id,name:x.name}))];
 function searchMaterials(){
  if(task==='words')return window.wordCooccurrence.materials.map(x=>({id:x.id,name:x.name}));
  if(task==='theme'&&currentThemeAnalysis)return(currentThemeAnalysis.materials||[]).map(x=>({id:x.project_id,name:x.name})).filter(x=>x.id);
  return projectMaterials(selectedResearchProject);
 }
 function chooseTask(next){
  if(rendering)return;rendering=true;
  try{
   collectThemeResult();
   if(!selectedResearchProject)selectedResearchProject=researchProjects[0]||null;
   window.wordCooccurrence?.leave();
   oldTheme.click();window.themeComparison?.set(false);comparing=false;
   task=next;codePanel.hidden=next!=='codes';
   if(next==='words')window.wordCooccurrence?.activate();
   else if(next==='codes'){
    window.codingTree?.leave();$('.network-workspace').hidden=true;page.classList.remove('network-active');
    $('#themePanel').hidden=true;$('#themePanel').style.display='none';$('#comparisonWorkspace').hidden=true;
    $('#themeQuickInput').closest('.focused-input').hidden=true;$('#themeQuickInput').closest('.focused-input').style.display='none';
    refreshCodes();
   }else choosePresentation(presentation);
  }finally{rendering=false;window.workspaceHeader?.refresh();window.animateWorkspaceTransition?.(page);}
 }
 function choosePresentation(next){
  if(task!=='theme')return;
  if(!['text','tree','comparison','review'].includes(next))next='text';
  collectThemeResult();reviewMode=next==='review';comparing=next==='comparison'||reviewMode;
  oldTheme.click();window.themeComparison?.set(comparing);
  if(!comparing){presentation=next;if(next==='tree')oldTree.click();}
  window.workspaceHeader?.refresh();
 }
 for(const [key,name]of [['theme','主题研究'],['words','词语探索'],['codes','编码分布']]){const b=button(name,()=>chooseTask(key));taskButtons.set(key,b);tasks.append(b);}
 for(const [key,name]of [['text','分析结果'],['review','发现核查']]){const b=button(name,()=>choosePresentation(key==='text'?presentation:key));themeButtons.set(key,b);themeSegments.append(b);}themeViews.append(resultPicker);
 projectPicker.onchange=()=>{
  collectThemeResult();rememberTheme();selectedResearchProject=researchProjects.find(p=>p.id===projectPicker.value)||null;currentThemeAnalysis=themeRecords.get(selectedResearchProject?.id)||null;
  renderFocusedAnalysis();chooseTask(task);
 };
 async function refreshCodes(){
  const project=selectedResearchProject,token=++codeToken,ids=memberIds(project),table=$('#matrixTable');
  table.replaceChildren();codeNotice.textContent=project?'正在读取编码…':'请选择研究项目';if(!project)return;
  const data=await Promise.allSettled(ids.map(id=>api(`/api/projects/${encodeURIComponent(id)}/analysis-workspace`).then(a=>({id,a}))));
  if(token!==codeToken||project.id!==selectedResearchProject?.id)return;
  const rows=[],codes=new Set();let failed=0;
  for(const result of data){if(result.status!=='fulfilled'){failed++;continue;}const {id,a}=result.value,map=new Map((a.codes||[]).map(c=>[c.id,c.name])),counts={};for(const excerpt of a.excerpts||[]){const name=map.get(excerpt.code_id);if(name){counts[name]=(counts[name]||0)+1;codes.add(name);}}rows.push({name:projects.find(p=>p.id===id)?.name||projectMaterials(project).find(p=>p.id===id)?.name||id,metadata:a.metadata||{},counts});}
  const names=[...codes].sort((a,b)=>a.localeCompare(b,'zh-CN'));
  codeNotice.textContent=`${project.name} · ${rows.length} 篇访谈 · ${names.length} 个编码${failed?' · '+failed+' 篇读取失败':''}`;
  if(!names.length){table.innerHTML='<tbody><tr><td>当前项目尚无已确认的编码。请在单篇访谈的“访谈编码”中确认编码后查看。</td></tr></tbody>';return;}
  table.innerHTML=`<thead><tr>${['访谈','受访者','角色',...names].map(n=>'<th>'+escapeHtml(n)+'</th>').join('')}</tr></thead><tbody>${rows.map(r=>'<tr><td>'+escapeHtml(r.name)+'</td><td>'+escapeHtml(r.metadata.participant_id||'')+'</td><td>'+escapeHtml(r.metadata.participant_role||'')+'</td>'+names.map(n=>'<td>'+(r.counts[n]||0)+'</td>').join('')+'</tr>').join('')}</tbody>`;
 }
 $('#refreshMatrixBtn').onclick=refreshCodes;
 // The former project page is retained as a dialog, preserving its existing actions.
 const manager=make('dialog','research-members-dialog'),managerClose=button('关闭',()=>manager.close());managerClose.className='research-manager-close';managerClose.setAttribute('aria-label','关闭项目访谈管理');manager.append(managerClose,$('#projectManage'));document.body.append(manager);
 manager.addEventListener('click',event=>{if(event.target.closest('[data-open-memo],[data-start-analysis]'))manager.close();},{capture:true});
 const openManager=openResearchProject;
 openResearchProject=function(id){openManager(id,false);if(!manager.open)manager.showModal();};
 showResearchList=function(){if(manager.open)manager.close();renderResearchProjects();window.renderInterviewLibrary?.();window.workspaceHeader?.refresh();};
 const originalSwitch=switchTab;
 switchTab=function(id){if(id==='projectManage'){switchView('workspace');return;}if(id==='matrix'){originalSwitch('focused');chooseTask('codes');return;}originalSwitch(id);if(id==='focused'&&!rendering)chooseTask(task);};
 const navGroup=$('.nav-parent[data-group="research"]');navGroup.querySelector('em').textContent='研究分析';
 $('.nav-item[data-tab="projectManage"]')?.remove();$('.nav-item[data-tab="matrix"]')?.remove();
 function libraryMenus(){for(const menu of document.querySelectorAll('.library-project-menu')){if(menu.querySelector('[data-manage-project]'))continue;const id=menu.closest('[data-group-id]').dataset.groupId,b=button('管理访谈',e=>{e.stopPropagation();menu.hidden=true;openResearchProject(id);});b.dataset.manageProject=id;menu.prepend(b);}}
 function configure(config,id){
  if(!['workspace','editor'].includes(id))config.module='研究分析';
  if(['familiarity','coding','sourceSearch'].includes(id)){config.page='单篇访谈分析';return;}
  if(id!=='focused')return;
  config.page='跨访谈分析';config.tabs=[tasks];
  const focusedNav=$('.nav-item[data-tab="focused"]');if(focusedNav&&!focusedNav.classList.contains('active'))focusedNav.classList.add('active');
  for(const [key,b]of taskButtons)b.classList.toggle('active',key===task);
  const active=reviewMode&&comparing?'review':comparing?'comparison':'text';updateResultPicker();hiddenIfChanged(resultPicker,comparing);
  for(const [key,b]of themeButtons){b.classList.toggle('active',key===active);attrIfChanged(b,'aria-pressed',String(key===active));}
  if(task==='words'){
   const wordProject=researchProjects.find(p=>p.id===window.wordCooccurrence?.projectId);if(wordProject)selectedResearchProject=wordProject;
   textIfChanged(wordSettings,window.wordCooccurrence?.step===4?'分析设置':'查看已有结果');hiddenIfChanged(wordSettings,window.wordCooccurrence?.step!==4&&!(window.wordCooccurrence?.step===3&&window.wordCooccurrence?.hasResult));
   if(window.wordCooccurrence?.loading||window.wordCooccurrence?.step===4)hiddenIfChanged(wordSettings,true);
   const words=window.wordCooccurrence;
   config.status=[];config.actions=[words.saveResult];config.toolsLeft=[words.controls[2],words.controls[3]];config.toolsRight=[wordSettings];scopeText.hidden=true;
  }else{
   const options=researchProjects.map(p=>`<option value="${escapeHtml(p.id)}">${escapeHtml(p.name)}</option>`).join('');if(projectPicker.dataset.options!==options){projectPicker.innerHTML='<option value="">请选择项目</option>'+options;projectPicker.dataset.options=options;}
   const projectValue=selectedResearchProject?.id||'';if(projectPicker.value!==projectValue)projectPicker.value=projectValue;
   textIfChanged(scope,'项目 · '+memberIds(selectedResearchProject).length+' 篇访谈');if(scope.disabled!==!selectedResearchProject)scope.disabled=!selectedResearchProject;
   config.selector=task==='codes'?[projectPicker]:[projectPicker,$('#themeHistorySelect')];
   const quick=$('#themeQuickInput').closest('.focused-input');if(!quick.classList.contains('research-inline-question'))quick.classList.add('research-inline-question');
   const showQuick=task==='theme'&&!currentThemeAnalysis&&!comparing&&presentation==='text';hiddenIfChanged(quick,!showQuick);const quickDisplay=showQuick?'flex':'none';if(quick.style.display!==quickDisplay)quick.style.display=quickDisplay;
   config.toolsLeft=task==='theme'?[themeViews,...(showQuick?[quick]:[]),...(currentThemeAnalysis?[scopeText]:[])]:[];hiddenIfChanged(newAnalysis,!currentThemeAnalysis&&!comparing&&presentation==='text');config.toolsRight=[search,newAnalysis];
   if(task==='codes'){config.status=[];config.actions=[search];config.toolsLeft=[];config.toolsRight=[];scopeText.hidden=true;$('#themePanel').hidden=true;$('#themePanel').style.display='none';$('#comparisonWorkspace').hidden=true;quick.hidden=true;quick.style.display='none';}
   else{
    const analysis=currentThemeAnalysis;hiddenIfChanged(scopeText,!analysis);
    if(analysis){const names=(analysis.materials||[]).map(x=>x.name||x.project_id),signature=JSON.stringify([analysis.theme||analysis.name||'',names]);if(scopeText.dataset.signature!==signature){const question=make('span','research-scope-question',`研究问题：${analysis.theme||analysis.name||''}`),count=make('span','research-scope-count',`纳入 ${names.length} 篇访谈稿`);question.title=question.textContent;count.title=names.join('、');scopeText.replaceChildren(question,count);scopeText.dataset.signature=signature;}const quick=$('#themeQuickInput').closest('.focused-input');hiddenIfChanged(quick,true);if(quick.style.display!=='none')quick.style.display='none';}
   }
  }
 }
 window.researchNavigation={configure,get task(){return task;},searchMaterials,chooseTask,
  renderSharedWorkspace(){
   if(task!=='theme'||!reviewMode||!comparing)return false;
   window.findingReview?.open();return true;
  }
 };
// Navigation styles are render-blocking in index.html to avoid default-layout flashes.
 const observer=new MutationObserver(libraryMenus);observer.observe($('#projectList'),{subtree:true,childList:true});libraryMenus();
 window.workspaceHeader?.refresh();
})();
