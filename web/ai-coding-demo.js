/* Source offsets are Unicode code points, matching Python, not UTF-16 indices. */
(() => {
 const el=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n;},btn=(text,fn)=>{const b=el('button','',text);b.type='button';b.onclick=fn;return b;};
 const icons={more:'M5 12h.01M12 12h.01M19 12h.01',trash:'M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7',unlink:'M10 13a5 5 0 0 1-1-7l3-3a5 5 0 0 1 7 7l-1 1M14 11a5 5 0 0 1 1 7l-3 3a5 5 0 0 1-7-7l1-1M3 3l18 18',undo:'M4 10h9a6 6 0 0 1 0 12M4 10l5-5M4 10l5 5',save:'M5 3h12l4 4v14H3V3h2M7 3v6h10V3M7 21v-8h10v8',range:'M4 4h6M4 4v6M20 20h-6M20 20v-6M8 16l8-8M14 5l5 5',locate:'M12 3v3M12 18v3M3 12h3M18 12h3M19 12a7 7 0 1 1-14 0 7 7 0 0 1 14 0',help:'M9 9a3 3 0 0 1 6 0c0 2-3 2-3 4M12 17h.01M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0'};
 function iconButton(name,kind,fn){const b=btn('',fn);b.className='ac-icon-button';b.title=name;b.setAttribute('aria-label',name);const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('aria-hidden','true');const path=document.createElementNS(svg.namespaceURI,'path');path.setAttribute('d',icons[kind]);svg.append(path);b.append(svg);return b;}
 const host=document.querySelector('#coding'),legacy=el('div','ac-legacy-coding');legacy.hidden=true;legacy.append(...host.childNodes);const page=el('section','ac-page');page.id='aiCodingDemo';host.append(legacy,page);
 const project=el('select'),status=el('span'),start=btn('开始AI编码',()=>run(false)),resume=btn('继续未完成批次',()=>run(true)),refresh=btn('刷新',()=>load());
 project.setAttribute('aria-label','AI编码研究项目');resume.hidden=true;
 const progress=el('div','ac-progress');
 const grid=el('div','ac-grid'),left=el('aside','ac-list'),middle=el('section','ac-middle'),reviewCard=el('aside','ac-review'),reviewHeader=el('div','ac-review-head'),right=el('div','ac-review-body'),reviewFooter=el('div','ac-review-fixed-footer');reviewFooter.hidden=true;reviewHeader.append(el('h3','','编码审核'));reviewCard.append(reviewHeader,right,reviewFooter);
 const listHead=el('h3','','编码建议'),filter=el('select'),list=el('div','ac-list-items');filter.setAttribute('aria-label','筛选审核状态');for(const [v,t] of [['all','全部'],['pending','待审核'],['accepted','已接受'],['modified','已修改'],['rejected','已拒绝'],['deleted','已删除（可恢复）']])filter.append(new Option(t,v));const listHeader=el('div','ac-list-head'),organizeButton=btn('整理编码',openOrganizer);organizeButton.className='ac-organize-button';organizeButton.disabled=true;const acceptAll=btn('接受全部AI编码',acceptAllCodes);acceptAll.className='ac-bulk-accept';acceptAll.disabled=true;listHeader.append(listHead,organizeButton);left.append(listHeader,filter,acceptAll,list);
 const sourceTitle=el('h3','','访谈原文'),sourceInfo=el('p','ac-note'),source=el('div','ac-source'),selectionInfo=el('span','ac-note','选中文字后可编码'),manual=btn('新建编码',()=>{closeSelectionMenu();newManual();}),attach=btn('加入当前编码',()=>{closeSelectionMenu();if(current()?.references[referenceIndex]?.validation!=='valid')confirmSelectionReference();else attachSelection();});
 const selectionMenu=el('div','ac-selection-popover');
 selectionMenu.setAttribute('role','menu');selectionMenu.setAttribute('aria-label','原文选区编码操作');manual.setAttribute('role','menuitem');attach.setAttribute('role','menuitem');selectionMenu.hidden=true;selectionMenu.append(selectionInfo,manual,attach);document.body.append(selectionMenu);
 function closeSelectionMenu(){selectionMenu.hidden=true;}
 selectionMenu.addEventListener('mousedown',e=>e.preventDefault());
 document.addEventListener('click',e=>{if(!selectionMenu.contains(e.target)&&!source.contains(e.target))closeSelectionMenu();});
 document.addEventListener('keydown',e=>{if(e.key==='Escape'){closeSelectionMenu();closeCodeMenus();}});
 document.addEventListener('click',e=>{if(!e.target.closest('.ac-more-box'))closeCodeMenus();});
 function closeCodeMenus(){for(const m of reviewCard.querySelectorAll('.ac-more-menu'))m.hidden=true;for(const b of reviewCard.querySelectorAll('.ac-more-box>button'))b.setAttribute('aria-expanded','false');}
 selectionMenu.addEventListener('keydown',e=>{if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();const buttons=[manual,attach].filter(b=>!b.disabled),i=buttons.indexOf(document.activeElement);buttons[(i+(e.key==='ArrowDown'?1:buttons.length-1))%buttons.length].focus();}});
 document.addEventListener('scroll',closeSelectionMenu,true);window.addEventListener('resize',closeSelectionMenu);
 source.tabIndex=0;source.setAttribute('aria-label','AI编码完整原文');middle.append(sourceTitle,source);grid.append(left,middle,reviewCard);page.append(grid);
 let state=null,pid='',tid='',selected='',editing=null,dirty=false,range=null,shownHash='',token=0,timer=null,busy=false,referenceIndex=0,peers=[],scopeChoices=[],activation=0,previousFilter='all';
 const statusLabels={pending:'待审核',accepted:'已接受',modified:'已修改',rejected:'已拒绝'};
 const endpoint=()=>`/api/research-projects/${encodeURIComponent(pid)}/ai-coding/${encodeURIComponent(tid)}`;
 async function request(path,method='GET',body){const r=await fetch(path,{method,headers:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});const d=await r.json();if(!r.ok)throw Error(d.detail||'请求失败');return d;}
 function warn(e){toast(e.message||String(e));}
 function checkDirty(){return !dirty||confirm('当前编码修改尚未保存，放弃这些修改？');}
 function updateReviewStatus(){const note=reviewCard.querySelector('.ac-save-state'),save=reviewCard.querySelector('[aria-label="保存修改"]');if(note){note.textContent=dirty?'修改未保存':current()?.status==='pending'?'AI建议已自动保存':'已保存';note.classList.toggle('ac-unsaved',dirty);}if(save)save.disabled=!dirty||busy;}
 function markDirty(){const saved=state?.codes.find(c=>c.id===editing?.id);dirty=!saved||editing.name!==saved.name||editing.definition!==saved.definition||JSON.stringify(editing.references)!==JSON.stringify(saved.references);updateReviewStatus();}
function resetContext(message){organizeButton.disabled=true;acceptAll.disabled=true;clearTimeout(timer);++token;state=null;selected='';editing=null;dirty=false;range=null;referenceIndex=0;closeSelectionMenu();list.replaceChildren();source.replaceChildren();sourceInfo.textContent='';right.replaceChildren();reviewFooter.replaceChildren();reviewFooter.hidden=true;reviewHeader.replaceChildren(el('h3','','编码审核'));progress.textContent=message;status.textContent=message;start.disabled=true;resume.hidden=true;}
 async function activateCurrent(){
  const context=window.singleInterviewCodingContext.get(),sourceId=String(context.sourceId||'');
  if(state&&sourceId===tid&&(!context.researchProjectId||context.researchProjectId===pid)){render();return;}
  if(!checkDirty())return;
  const serial=++activation,previousPid=pid;resetContext(sourceId?'正在读取当前访谈的编码…':'请先选择一篇访谈');pid='';tid=sourceId;scopeChoices=[];
  window.workspaceHeader?.refresh();if(!sourceId)return;
  try{
   peers=window.singleInterviewCodingContext.projects?.()||[];
   if(!window.aiCodingContext.resolve(peers,sourceId,context.researchProjectId,previousPid).project)peers=await request('/api/research-projects?summaries=true');
   if(serial!==activation)return;
   const scope=window.aiCodingContext.resolve(peers,sourceId,context.researchProjectId,previousPid);scopeChoices=scope.candidates;
   project.replaceChildren(...scopeChoices.map(p=>new Option(p.name,p.id)));
   if(!scope.project){resetContext('该访谈尚未归入研究项目，请先在访谈资料中将它加入项目。');return;}
   pid=String(scope.project.id);project.value=pid;window.singleInterviewCodingContext.setScope?.(pid);
   await load();
  }catch(e){if(serial===activation){resetContext('编码读取失败：'+e.message);warn(e);}}
  finally{if(serial===activation)window.workspaceHeader?.refresh();}
 }
 function acceptCandidate(c){const chars=Array.from(state?.sources[state.current_hash]?.text||'');return c.origin==='ai'&&c.status==='pending'&&!c.deleted_at&&c.source_hash===state.current_hash&&c.references.length>0&&c.references.every(r=>r.validation==='valid'&&Number.isInteger(r.start)&&Number.isInteger(r.end)&&r.start>=0&&r.end>r.start&&r.end<=chars.length&&chars.slice(r.start,r.end).join('')===r.quote);}
 async function acceptAllCodes(){
  if(busy||!state)return;if(dirty)return toast('请先保存当前修改，再批量接受。');
  const count=state.codes.filter(acceptCandidate).length;if(!count)return;
  if(!confirm(`接受当前访谈中 ${count} 个可精确定位的待审核AI编码？\n需处理、历史原文版本、已拒绝及人工修改的编码不变。\n原文定位准确不代表编码含义正确，请确认你已审阅。`))return;
  const owner=endpoint(),version=token;busy=true;acceptAll.disabled=true;
  try{const d=await request(owner+'/accept-all','POST',{confirmed:true,revision:state.revision});if(owner!==endpoint()||version!==token)return;state=d.coding;editing=null;dirty=false;busy=false;render();toast(`已接受 ${d.accepted_count} 个AI编码，结果已保存。`);}catch(e){warn(e);}finally{busy=false;if(state)renderList();}
 }
 function activate(){if(!checkDirty())return;switchView('analysis','coding');}
 async function load(){if(!pid||!tid)return;const version=++token;clearTimeout(timer);try{const d=await request(endpoint());if(version!==token)return;state=d;if(!dirty)editing=null;render();if(d.runs.some(r=>r.status==='running'))timer=setTimeout(()=>load(),1800);}catch(e){if(version===token){warn(e);status.textContent='读取失败';window.workspaceHeader?.refresh();}}}
 project.onchange=async()=>{if(!checkDirty()){project.value=pid;return;}const next=project.value;resetContext('正在读取此项目下的编码…');pid=next;window.singleInterviewCodingContext.setScope?.(pid);await load();};
 filter.onchange=()=>{if(!checkDirty()){filter.value=previousFilter;return;}previousFilter=filter.value;selected='';editing=null;dirty=false;range=null;render();};
 async function run(continuing){if(busy||!state||!checkDirty())return;const last=state.runs.at(-1);if(!continuing&&state.codes.length&&!confirm('重新编码将新增一轮待审核建议，已有编码和人工判断全部保留。继续？'))return;busy=true;start.disabled=resume.disabled=true;try{await request(endpoint()+'/run','POST',continuing?{resume_run_id:last?.id}:{});editing=null;dirty=false;await load();}catch(e){warn(e);}finally{busy=false;start.disabled=resume.disabled=false;}}
 function choose(id){if(!checkDirty())return;selected=id;editing=null;dirty=false;referenceIndex=0;range=null;render();scrollToRef();}
 function nextCode(){const codes=state?.codes||[],index=codes.findIndex(c=>c.id===selected);return index<0?null:codes.slice(index+1).find(c=>filter.value==='all'||c.status===filter.value)||null;}
 function advanceCode(){if(busy)return;const next=nextCode();if(next)choose(next.id);else toast('当前列表已无下一处编码。');}
 function current(){return editing||[...(state?.codes||[]),...(state?.deleted_codes||[])].find(c=>c.id===selected);}
 function scrollToRef(){const c=current(),ref=c?.references[referenceIndex];let mark;if(ref?.validation==='valid')mark=[...source.querySelectorAll('mark')].find(m=>Number(m.dataset.start)<=ref.start&&Number(m.dataset.end)>ref.start);else mark=source.querySelector('[data-assist="match"]')||source.querySelector('[data-assist="block"]');mark?.scrollIntoView({block:'center',behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'});}
 function render(){closeSelectionMenu();if(!state)return;const run=state.runs.at(-1),running=run?.status==='running',pending=state.codes.filter(c=>c.status==='pending').length,unresolved=state.codes.flatMap(c=>c.references).filter(r=>r.validation!=='valid').length;
  const indexStage=run?.index_preparation;status.textContent=running?(indexStage&&indexStage.status!=='completed'?'正在准备话题索引…':'正在编码'):indexStage?.status==='failed'?'话题索引准备失败，可继续':run&&run.status!=='completed'?'编码部分完成或失败':pending?'编码完成 · 存在待审核建议':state.codes.length?'编码及审核已完成':'尚未开始编码';
  status.title=run?.error||(indexStage?.status==='completed'?(indexStage.reused?'已复用共享话题索引':'已建立并保存共享话题索引'):'');
  start.disabled=!!running;resume.hidden=!run||!['failed','partial'].includes(run.status);resume.disabled=!!running;project.disabled=false;
  progress.textContent=run?`本轮 ${run.batches.filter(b=>b.status==='completed').length}/${run.batches.length} 批完成 · ${state.codes.length} 个编码 · ${pending} 个待审核 · ${unresolved} 处引用需处理${run.error?' · '+run.error:''}`:'请选择访谈后开始；也可直接选中原文手动编码。';
  for(const b of run?.batches||[]){if(b.status==='failed'){const info=el('span','ac-error',' 批次失败：'+(b.attempts.at(-1)?.error||'可继续'));progress.append(info);}}
  renderList();renderSource();renderReview();window.workspaceHeader?.refresh();
 }
 function renderList(){organizeButton.disabled=!state||!state.codes.some(c=>c.status!=='rejected');acceptAll.disabled=busy||!state||state.runs.some(r=>r.status==='running')||!state.codes.some(acceptCandidate);list.replaceChildren();for(const c of (filter.value==='deleted'?state?.deleted_codes:state?.codes)||[]){if(filter.value!=='deleted'&&filter.value!=='all'&&c.status!==filter.value)continue;const b=btn('',()=>choose(c.id));b.className='ac-code'+(selected===c.id?' active':'');b.append(el('strong','',c.name),el('small','',`${c.references.length} 处引用 · ${c.deleted_at?'已删除':statusLabels[c.status]}${c.references.some(r=>r.validation!=='valid')?' · 需处理':''}`));list.append(b);}if(!list.childElementCount)list.append(el('p','ac-note','暂无编码。'));}
 function renderSource(){const c=current();shownHash=c?.source_hash||state.current_hash;const text=state.sources[shownHash]?.text||'',chars=Array.from(text),bindings=[];sourceInfo.textContent=`${shownHash===state.current_hash?'当前原文':'历史原文快照（原文已更新）'} · 版本 ${shownHash.slice(0,12)} · 字符范围从0开始、末位不包含`;
  for(const code of state.codes){if(code.source_hash!==shownHash||code.status==='rejected')continue;for(const ref of code.references)if(ref.validation==='valid')bindings.push({start:ref.start,end:ref.end,id:code.id,name:code.name});}
  if(editing&&!editing.deleted_at){for(let i=bindings.length-1;i>=0;i--)if(bindings[i].id===editing.id)bindings.splice(i,1);for(const ref of editing.references)if(ref.validation==='valid')bindings.push({...ref,id:editing.id,name:editing.name});}
  const hint=window.aiCodingLocator.locateUnresolved(c?.references[referenceIndex],c,state);if(hint){bindings.push({start:hint.start,end:hint.end,assist:'block'});for(const span of hint.fragments)bindings.push({...span,assist:'match'});sourceInfo.textContent+=' · 黄色仅为待确认引用的查找辅助';}
  const events=new Map();for(const b of bindings){if(!events.has(b.start))events.set(b.start,{add:[],remove:[]});if(!events.has(b.end))events.set(b.end,{add:[],remove:[]});events.get(b.start).add.push(b);events.get(b.end).remove.push(b);}const points=[...new Set([0,chars.length,...events.keys()])].sort((a,b)=>a-b),active=new Set(),frag=document.createDocumentFragment();
  for(let i=0;i<points.length-1;i++){const pos=points[i],ev=events.get(pos);for(const b of ev?.remove||[])active.delete(b);for(const b of ev?.add||[])active.add(b);const content=chars.slice(pos,points[i+1]).join('');if(!active.size){frag.append(document.createTextNode(content));continue;}const mark=el('mark','',content),ids=[...new Set([...active].map(x=>x.id).filter(Boolean))];mark.dataset.start=pos;mark.dataset.end=points[i+1];mark.dataset.codeIds=JSON.stringify(ids);const assists=[...active].filter(x=>x.assist);if(assists.length){mark.dataset.assist=assists.some(x=>x.assist==='match')?'match':'block';mark.classList.add('ac-assist-'+mark.dataset.assist);}mark.title=assists.length?'辅助定位，尚未确认引用':[...new Set([...active].map(x=>x.name))].join(' / ');if(ids.includes(selected))mark.classList.add('selected');if(ids.length>1)mark.classList.add('overlap');mark.onclick=()=>{if(window.getSelection()?.toString()||!ids.length)return;if(ids.length===1)choose(ids[0]);else{reviewFooter.hidden=true;reviewHeader.replaceChildren(el('h3','','编码审核'));right.replaceChildren(el('h3','','该片段对应多个编码'));for(const id of ids){const code=state.codes.find(c=>c.id===id);right.append(btn(code?.name||'新编码',()=>choose(id)));}}};frag.append(mark);}
  const scroll=source.scrollTop;source.replaceChildren(frag);source.scrollTop=scroll;
 }
const captureSelection=()=>{const s=window.getSelection();if(selectionMenu.contains(document.activeElement))return;if(!state||!s||s.isCollapsed||!source.contains(s.anchorNode)||!source.contains(s.focusNode)){closeSelectionMenu();return;}const r=s.getRangeAt(0),prefix=r.cloneRange();prefix.selectNodeContents(source);prefix.setEnd(r.startContainer,r.startOffset);const a=Array.from(prefix.toString()).length,q=r.toString(),b=a+Array.from(q).length;const expected=Array.from(state.sources[shownHash].text).slice(a,b).join('');if(q!==expected){range=null;closeSelectionMenu();return;}range={start:a,end:b,quote:q,validation:'valid',source_hash:shownHash};attach.disabled=busy||!current()||!!current().deleted_at||current().source_hash!==shownHash;attach.textContent=current()?.references[referenceIndex]?.validation!=='valid'?'用选区确认此引用':'加入当前编码';selectionInfo.textContent=`已选 ${b-a} 字`;const bounds=source.getBoundingClientRect(),rects=[...r.getClientRects()].filter(x=>x.bottom>bounds.top&&x.top<bounds.bottom&&x.width);if(!rects.length){closeSelectionMenu();return;}const rect=rects.at(-1);selectionMenu.hidden=false;const box=selectionMenu.getBoundingClientRect(),gap=8,left=Math.max(gap,Math.min(rect.left,innerWidth-box.width-gap)),below=rect.bottom+gap,top=below+box.height<=Math.min(innerHeight-gap,bounds.bottom)?below:Math.max(gap,Math.min(rect.top-box.height-gap,innerHeight-box.height-gap));selectionMenu.style.left=`${left}px`;selectionMenu.style.top=`${top}px`;};
 source.onmouseup=captureSelection;source.onkeyup=e=>{if(e.key!=='Escape')captureSelection();};
 document.addEventListener('selectionchange',captureSelection);
 function newManual(){if(!range)return toast('请先在中间原文中选择片段');if(!checkDirty())return;selected='';editing={name:'',definition:'',source_hash:range.source_hash,source_id:tid,status:'modified',references:[{...range}],reason:'研究者手动编码'};dirty=true;referenceIndex=0;renderReview();}
 function attachSelection(){const c=current();if(c?.deleted_at)return toast('请先恢复该编码');if(!c||!range)return toast('请先选择编码和原文片段');if(c.source_hash!==range.source_hash)return toast('不能混用不同原文版本');editing=JSON.parse(JSON.stringify(c));editing.references.push({...range});dirty=true;referenceIndex=editing.references.length-1;renderReview();renderSource();}

 async function confirmSelectionReference(){
  const c=current(),ref=c?.references[referenceIndex],selection=range&&{...range};
  if(busy||!c||!selection||c.deleted_at)return;
  if(!c.id||!ref?.id)return toast('请先保存当前编码。');
  if(dirty)return toast('当前有未保存修改，请先保存，再用选区确认引用；不会覆盖你的修改。');
  if(ref.validation==='valid')return toast('此引用已定位，请刷新后查看。');
  if(c.source_hash!==selection.source_hash)return toast('原文版本不一致，请重新选择。');
  const owner=endpoint(),ownerToken=token;
  busy=true;attach.disabled=true;
  try{
   const d=await request(owner+'/codes/'+encodeURIComponent(c.id)+'/actions','POST',{action:'confirm_reference',revision:c.revision,reference_id:ref.id,source_hash:selection.source_hash,start:selection.start,end:selection.end,quote:selection.quote});
   if(owner!==endpoint()||ownerToken!==token)return;
   state=d;editing=null;dirty=false;range=null;busy=false;render();
   toast('此处引用已确认并保存；编码审核状态未改变。');
  }catch(e){warn(e);}finally{busy=false;updateReviewStatus();}
 }
 function renderReview(){
  right.replaceChildren();reviewFooter.replaceChildren();reviewFooter.hidden=true;
  reviewHeader.replaceChildren(el('h3','','编码审核'));const c=current();
  if(!c){right.append(el('p','ac-note','点击左侧编码或原文高亮查看建议。'));return;}
  if(c.deleted_at){right.append(el('h4','',c.name),el('p','ac-note','编码及引用已保留，可恢复；访谈原文未改变。'),btn('恢复编码',()=>codeAction('restore')));return;}
  const draft=editing||JSON.parse(JSON.stringify(c));editing=draft;
  const titleGroup=el('div','ac-review-title-group'),badge=el('span','ac-status-badge ac-status-'+draft.status,statusLabels[draft.status]);
  titleGroup.append(el('h3','','编码审核'),badge);
  function menuControl(label,items){
   const box=el('div','ac-more-box'),menu=el('div','ac-more-menu'),toggle=iconButton(label,'more',()=>{
    const opening=menu.hidden;closeCodeMenus();menu.hidden=!opening;toggle.setAttribute('aria-expanded',String(opening));
   });
   toggle.setAttribute('aria-haspopup','menu');toggle.setAttribute('aria-expanded','false');
   menu.hidden=true;menu.setAttribute('role','menu');menu.setAttribute('aria-label',label+'菜单');
   for(const item of items){item.setAttribute('role','menuitem');const original=item.onclick;item.onclick=e=>{closeCodeMenus();original?.(e);};menu.append(item);}
   box.append(toggle,menu);return box;
  }
  const deleteCode=btn('',()=>codeAction('delete'));deleteCode.className='ac-delete-code';
  deleteCode.append(el('span','','删除整个编码'),el('small','','移除该编码及全部引用'));
  deleteCode.prepend(iconButton('删除','trash',()=>{}).firstChild);deleteCode.disabled=!draft.id;
  reviewHeader.replaceChildren(titleGroup,menuControl('编码更多操作',[deleteCode]));
  const name=el('input'),definition=el('textarea');
  name.value=draft.name;definition.value=draft.definition;name.setAttribute('aria-label','编码名称');definition.setAttribute('aria-label','编码说明');
  name.oninput=()=>{draft.name=name.value;markDirty();};definition.oninput=()=>{draft.definition=definition.value;markDirty();};
  const nameGroup=el('section','ac-field-group'),definitionGroup=el('section','ac-field-group');
  nameGroup.append(el('label','','编码名称'),name);definitionGroup.append(el('label','','编码说明'),definition);
  const reason=el('details','ac-reason'),reasonSummary=el('summary','','AI建议理由');
  reason.append(reasonSummary,el('p','ac-note',draft.reason));right.append(nameGroup);
  referenceIndex=Math.max(0,Math.min(referenceIndex,draft.references.length-1));const ref=draft.references[referenceIndex];
  const refs=el('select','ac-reference-picker');refs.setAttribute('aria-label','当前编码引用');
  draft.references.forEach((r,i)=>refs.append(new Option(`${i+1} / ${draft.references.length}${r.validation==='valid'?'':' · 需处理'}`,i)));
  refs.value=referenceIndex;
  const changeReference=index=>{if(index<0||index>=draft.references.length)return;referenceIndex=index;closeSelectionMenu();renderSource();renderReview();scrollToRef();};
  refs.onchange=()=>changeReference(Number(refs.value));
  const prev=btn('‹',()=>changeReference(referenceIndex-1)),next=btn('›',()=>changeReference(referenceIndex+1));
  prev.className=next.className='ac-reference-step';prev.title='上一处引用';next.title='下一处引用';
  prev.setAttribute('aria-label','上一处引用');next.setAttribute('aria-label','下一处引用');prev.disabled=referenceIndex===0;next.disabled=referenceIndex===draft.references.length-1;
  const rangeButton=iconButton('用当前原文选区调整此引用','range',()=>{
   if(!range)return toast('请先在中间选择原文');if(range.source_hash!==draft.source_hash)return toast('原文版本不一致');
   draft.references[referenceIndex]={...ref,...range};delete draft.references[referenceIndex].error;markDirty();renderReview();renderSource();
  });rangeButton.append(el('span','','调整引用范围'));
  const removeRef=iconButton('移除此处引用','unlink',removeReference);removeRef.append(el('span','','移除此处引用'));removeRef.disabled=busy;
  const items=[rangeButton,removeRef];
  if(draft.removed_references?.length){const undo=iconButton('恢复最近移除的引用','undo',()=>codeAction('restore_reference'));undo.append(el('span','','恢复最近移除的引用'));items.push(undo);}
  const evidenceCard=el('section','ac-evidence-card');evidenceCard.setAttribute('aria-label','原文片段与引用');
  const refBar=el('div','ac-reference-bar');refBar.append(el('span','ac-reference-label','原文片段'),refs,prev,next,menuControl('引用更多操作',items));
  const quote=el('blockquote','ac-evidence-quote',typeof ref.quote==='string'?ref.quote:'引用无效');quote.tabIndex=0;quote.setAttribute('role','button');quote.setAttribute('aria-label','点击引文定位原文');quote.title='点击定位原文';
  quote.onclick=()=>{if(!window.getSelection()?.toString())scrollToRef();};quote.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();scrollToRef();}};
  evidenceCard.append(refBar,quote);right.append(evidenceCard);
  if(ref.validation!=='valid'){
   evidenceCard.append(el('p','ac-error',ref.error||'引用需人工选择范围确认。'));
   const hint=window.aiCodingLocator.locateUnresolved(ref,draft,state);
   if(hint)evidenceCard.append(el('p','ac-note','黄色为辅助查找，尚未确认。选中准确原文后，点击“用选区确认此引用”。'));
   else evidenceCard.append(el('p','ac-error','未找到对应输入块，请人工查找；不会猜测位置。'));
  }
  right.append(definitionGroup,reason);
  const actions=el('div','ac-actions ac-review-toolbar'),accept=btn('✓ 接受',()=>persist('accepted')),reject=btn('× 拒绝',()=>persist('rejected')),saveEdit=iconButton('保存修改','save',()=>persist('modified'));
  accept.setAttribute('aria-label','接受建议');reject.setAttribute('aria-label','拒绝建议');accept.title='接受并保存审核状态';reject.title='拒绝并保存审核状态';
  if(c.status==='accepted'){accept.textContent='下一处编码';accept.setAttribute('aria-label','下一处编码');accept.title=nextCode()?'查看当前列表的下一处编码':'当前列表已无下一处编码';accept.classList.add('ac-next-code');accept.onclick=advanceCode;}
  actions.append(accept,reject,saveEdit);
  const foot=el('div','ac-review-footer'),saveNote=el('span','ac-note ac-save-state'),rules='AI建议含待审核结果均已自动保存。接受或拒绝会立即保存；修改名称、说明或引用后请保存。保存修改视为人工审核，待审核和已拒绝建议不作为正式编码。';
  foot.append(saveNote,iconButton('保存与审核说明','help',()=>toast(rules)));foot.lastChild.title=rules;
  reviewFooter.hidden=false;reviewFooter.append(foot,actions);updateReviewStatus();
 }

 function removeReference(){
  const c=current();if(!c||busy)return;
  if(c.references.length<=1)return toast('这是最后一处引用；如不再需要，请从“⋯”删除整个编码。');
  const ref=c.references[referenceIndex];
  if(!c.id||!ref.id){c.references.splice(referenceIndex,1);referenceIndex=Math.min(referenceIndex,c.references.length-1);markDirty();renderReview();renderSource();return;}
  codeAction('remove_reference',ref.id);
 }
 async function codeAction(action,referenceId){
  const c=current();if(!c?.id||busy)return;
  if(!checkDirty())return;
  if(action==='delete'&&!confirm('删除整个编码“'+c.name+'”及其全部引用关联？\n不会删除访谈原文，可在“已删除（可恢复）”中恢复。'))return;
  const saved=[...state.codes,...(state.deleted_codes||[])].find(x=>x.id===c.id);
  if(!saved)return;
  busy=true;
  try{
   const owner=endpoint(),d=await request(owner+'/codes/'+encodeURIComponent(c.id)+'/actions','POST',{action,revision:saved.revision,reference_id:referenceId});
   if(owner!==endpoint())return;
   state=d;editing=null;dirty=false;range=null;
   if(action==='delete'){selected='';referenceIndex=0;}
   if(action==='restore'){filter.value=previousFilter='all';selected=c.id;}
   if(action==='remove_reference')referenceIndex=Math.min(referenceIndex,d.codes.find(x=>x.id===c.id).references.length-1);
   busy=false;render();toast(action==='delete'?'已删除，可从左侧筛选中恢复':action==='restore'?'编码已恢复':action==='remove_reference'?'引用关联已移除并保存':'引用已恢复');
  }catch(e){warn(e);}finally{busy=false;updateReviewStatus();}
 }
 async function persist(statusValue){if(busy||!editing)return;busy=true;try{const owner=endpoint(),payload={...editing,status:statusValue};const d=await request(owner+'/codes','POST',payload);if(owner!==endpoint())return;state=d;selected=d.codes.find(c=>c.id===payload.id)?.id||d.codes.at(-1)?.id||'';editing=null;dirty=false;busy=false;render();toast('编码已保存');}catch(e){warn(e);}finally{busy=false;updateReviewStatus();}}

 function openOrganizer(){
  if(!state)return;
  if(dirty)return toast('请先保存当前编码修改，再整理编码。');
  const owner=endpoint();
  window.aiCodingOrganizer.open({
   endpoint:owner,
   updated(d){if(owner!==endpoint())return;state=d;editing=null;dirty=false;range=null;if(!state.codes.some(c=>c.id===selected))selected='';referenceIndex=0;render();},
   editCode(id){if(owner!==endpoint())return;choose(id);},
   locate(code,ref){
    if(owner!==endpoint())return;
    const live=state.codes.find(c=>c.id===code.id)||state.codes.find(c=>c.references.some(r=>(r.merge_origins||[]).some(o=>o.code_id===code.id&&o.reference_id===ref.id))),index=live?.references.findIndex(r=>(r.id===ref.id||(r.merge_origins||[]).some(o=>o.code_id===code.id&&o.reference_id===ref.id))&&r.quote===ref.quote&&r.start===ref.start&&r.end===ref.end);
    if(!live||index<0||live.source_hash!==code.source_hash)return toast('编码或引用已变化，请刷新整理建议后定位。');
    if(!checkDirty())return;selected=live.id;editing=null;dirty=false;range=null;referenceIndex=index;render();scrollToRef();
   }
  });
 }
 window.aiCodingDemo={activate,activateCurrent,prepareSwitch(){++activation;resetContext('正在读取当前访谈的编码…');},canLeave:checkDirty,configure(config){config.module='研究分析';config.page='单篇访谈分析';config.selector=[...(config.selector||[]),...(scopeChoices.length>1?[project]:[])];config.status=[status];config.actions=[start,resume,refresh];config.toolsLeft=[];config.toolsRight=[];}};

 window.addEventListener('beforeunload',e=>{if(dirty){e.preventDefault();e.returnValue='';}});
})();
