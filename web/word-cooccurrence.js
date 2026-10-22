/* Independent review gate. Text is immutable; only offsets are edited. */
(() => {
 const css=document.createElement('link');css.rel='stylesheet';css.href='/assets/word-cooccurrence.css?v=20261010-resize-3';document.head.append(css);
 const selectionCss=document.createElement('link');selectionCss.rel='stylesheet';selectionCss.href='/assets/cooccurrence-selection.css?v=20261010-5';document.head.append(selectionCss);
 const reviewCss=document.createElement('link');reviewCss.rel='stylesheet';reviewCss.href='/assets/cooccurrence-review.css?v=33';document.head.append(reviewCss);
 const root=document.createElement('section');root.id='wordCooccurrence';root.hidden=true;document.querySelector('#focused').append(root);
 const picker=document.createElement('select'),status=document.createElement('span'),save=document.createElement('button'),next=document.createElement('button');
 picker.setAttribute('aria-label','选择共现分析项目');save.textContent='保存进度';next.id='wcNext';next.textContent='确认切块并继续 →';next.className='primary';
 let draft=null,pid='',tid='',dirty=false,issueIndex=0,onlyIssues=false,active=false,poll=null,busy=false,loading=false;
 const historyPicker=document.createElement('select'),saveResult=document.createElement('button');historyPicker.setAttribute('aria-label','词语探索历史结果');historyPicker.title='分析记录：未选择历史结果时显示当前草稿';historyPicker.append(new Option('分析记录',''));saveResult.textContent='保存结果';saveResult.className='wc-save-result';
 save.hidden=next.hidden=saveResult.hidden=true;
 async function loadHistory(){const rows=await request('/history');historyPicker.replaceChildren(new Option('分析记录',''),...rows.map(r=>new Option(r.name+' · '+new Date(r.saved_at*1000).toLocaleString(),r.id)));historyPicker.value=draft?.history_id||'';}
 historyPicker.onchange=async()=>{if(busy)return;busy=true;try{if(dirty&&!confirm('当前改动尚未保存，放弃并切换？')){historyPicker.value=draft?.history_id||'';return;}dirty=false;clearTimeout(poll);draft=await request(historyPicker.value?'/history/'+historyPicker.value:'');render();}catch(e){toast(e.message);}finally{busy=false;}};
 saveResult.onclick=async()=>{if(busy||!draft?.graph||draft.history_id)return;const name=prompt('为这份结果命名','词语共现结果');if(!name?.trim())return;busy=true;saveResult.disabled=true;try{await request('/history','POST',{name:name.trim(),revision:draft.revision});await loadHistory();toast('结果已保存到历史记录，当前草稿仍保留');}catch(e){toast(e.message);}finally{busy=false;saveResult.disabled=!!draft?.history_id;}};
 const esc=escapeHtml;
 document.addEventListener('pointerdown',event=>{
  root.querySelectorAll('.wc-stat-menu[open]').forEach(menu=>{if(!menu.contains(event.target))menu.open=false;});
 });
 let closeInlineSplit=()=>{};
 let reviewBlock=null,reviewInterview=null,reviewOpen=false;
 function refreshReviewPane(){const area=root.querySelector('.wc-cards'),top=area?.scrollTop||0,edge=area?.getBoundingClientRect().top;const anchor=area&&[...area.querySelectorAll('.wc-card')].find(c=>c.getBoundingClientRect().bottom>edge),id=anchor?.id,offset=anchor?anchor.getBoundingClientRect().top-edge:0;render();const nextArea=root.querySelector('.wc-cards'),nextAnchor=id&&document.getElementById(id);if(nextArea){nextArea.scrollTop=top;if(nextAnchor)nextArea.scrollTop+=nextAnchor.getBoundingClientRect().top-nextArea.getBoundingClientRect().top-offset;}}
 function highlightExactIssues(area,t,b){
  const ranges=t.issues.filter(x=>!x.resolved&&Number.isInteger(x.start)&&Number.isInteger(x.end)&&x.start>=b.start&&x.end<=b.end&&x.end>x.start&&(!x.quote||text(t,x)===x.quote));
  if(!ranges.length)return;
  const walker=document.createTreeWalker(area,NodeFilter.SHOW_TEXT),nodes=[];let n;
  while((n=walker.nextNode()))if(!n.parentElement.closest('.wc-cut-marker'))nodes.push(n);
  let pos=b.start;
  for(const node of nodes){const chars=Array.from(node.textContent),fragment=document.createDocumentFragment();let plain='';
   for(let i=0;i<chars.length;){const issue=ranges.find(x=>x.start<=pos+i&&pos+i<x.end);if(!issue){plain+=chars[i++];continue;}if(plain){fragment.append(document.createTextNode(plain));plain='';}const mark=document.createElement('mark');mark.className='wc-pending-text';let value='';while(i<chars.length&&pos+i<issue.end)value+=chars[i++];mark.textContent=value;mark.title='点击查看核对原因';mark.onclick=e=>{e.stopPropagation();reviewBlock=b.id;reviewOpen=true;issueIndex=t.issues.filter(x=>!x.resolved&&b.start<=x.start&&x.start<b.end).indexOf(issue);refreshReviewPane();};fragment.append(mark);}
   if(plain)fragment.append(document.createTextNode(plain));pos+=chars.length;node.replaceWith(fragment);
  }
 }
 function enableInlineSplit(area,t,b){
  area.onclick=e=>{
   closeInlineSplit();
   let node,offset;
   if(document.caretPositionFromPoint){const p=document.caretPositionFromPoint(e.clientX,e.clientY);node=p?.offsetNode;offset=p?.offset;}
   else if(document.caretRangeFromPoint){const p=document.caretRangeFromPoint(e.clientX,e.clientY);node=p?.startContainer;offset=p?.startOffset;}
   if(!node||node.nodeType!==Node.TEXT_NODE||!area.contains(node)||node.parentElement.closest('.wc-cut-marker'))return;
   // Caret hit-testing can snap blank space to the closest text endpoint.
   // Require the pointer to hit a visible, non-whitespace character rectangle.
   const value=node.textContent;let hitText=false;
   for(const candidate of [offset-1,offset]){
    if(candidate<0||candidate>=value.length)continue;
    let start=candidate,end=candidate+1;
    if(/[\uDC00-\uDFFF]/.test(value[start])&&start>0)start--;
    if(/[\uD800-\uDBFF]/.test(value[end-1])&&end<value.length)end++;
    if(!value.slice(start,end).trim())continue;
    const glyph=document.createRange();glyph.setStart(node,start);glyph.setEnd(node,end);
    if([...glyph.getClientRects()].some(r=>r.width>0&&r.height>0&&e.clientX>=r.left&&e.clientX<=r.right&&e.clientY>=r.top&&e.clientY<=r.bottom)){hitText=true;break;}
   }
   if(!hitText)return;
   const walker=document.createTreeWalker(area,NodeFilter.SHOW_TEXT);let total=0,current;
   while((current=walker.nextNode())){if(current.parentElement.closest('.wc-cut-marker'))continue;if(current===node){total+=Array.from(current.textContent.slice(0,offset)).length;break;}total+=Array.from(current.textContent).length;}
   const cut=b.start+total;if(cut<=b.start||cut>=b.end){toast('请选择块内位置，不能在开头或结尾拆分');return;}
   const range=document.createRange();range.setStart(node,offset);range.collapse(true);let rect=range.getBoundingClientRect();
   if(!rect.height)rect={left:e.clientX,top:e.clientY,bottom:e.clientY+20,height:20};
   const caret=document.createElement('div');caret.className='wc-inline-caret';caret.style.cssText=`left:${rect.left}px;top:${rect.top}px;height:${rect.height}px`;
   const popup=document.createElement('div');popup.className='wc-inline-split';popup.innerHTML='<button data-cut>✂ 在此拆分</button><button data-cancel aria-label="取消拆分">×</button>';
   document.body.append(caret,popup);popup.style.left=Math.max(8,Math.min(rect.left,innerWidth-popup.offsetWidth-8))+'px';popup.style.top=(rect.top>=60?rect.top-popup.offsetHeight-10:rect.bottom+8)+'px';
   const controller=new AbortController();
   closeInlineSplit=()=>{caret.remove();popup.remove();controller.abort();closeInlineSplit=()=>{};};
   popup.querySelector('[data-cut]').onclick=()=>{closeInlineSplit();split(t,b,[cut]);mark();};popup.querySelector('[data-cancel]').onclick=()=>closeInlineSplit();
   document.addEventListener('pointerdown',event=>{if(!popup.contains(event.target)&&!area.contains(event.target))closeInlineSplit();},{signal:controller.signal});
   document.addEventListener('keydown',event=>{if(event.key==='Escape')closeInlineSplit();},{signal:controller.signal});
   document.addEventListener('scroll',()=>closeInlineSplit(),{capture:true,signal:controller.signal});window.addEventListener('resize',()=>closeInlineSplit(),{signal:controller.signal});
  };
 }
 let panePrefs={left:240,right:290,collapsed:false};
 try{Object.assign(panePrefs,JSON.parse(localStorage.getItem('wc-pane-widths')||'{}'));}catch{}
 function setupPanes(layout){
  const list=layout.querySelector('.wc-list'),middle=layout.querySelector('.wc-middle'),right=layout.querySelector('.wc-issues');
  const store=()=>{try{localStorage.setItem('wc-pane-widths',JSON.stringify(panePrefs));}catch{}};
  const toggle=document.createElement('button');toggle.className='wc-collapse';toggle.type='button';
  const rail=document.createElement('div');rail.className='wc-collapsed-rail';
  const expand=document.createElement('button');expand.type='button';expand.innerHTML='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 3h8l4 4v14H6z"/><path d="M14 3v5h4M9 12h6M9 16h6"/></svg><svg viewBox="0 0 16 16" aria-hidden="true"><path d="m6 4 4 4-4 4"/></svg>';expand.title='展开访谈列表';expand.setAttribute('aria-label','展开访谈列表');
  const count=document.createElement('span');count.textContent=draft.interviews.length;rail.append(expand,count);
  list.prepend(toggle);layout.prepend(rail);
  function apply(){
   const width=layout.clientWidth;
   const compact=width<780;
   layout.classList.toggle('wc-pane-compact',compact);
   layout.classList.toggle('wc-pane-collapsed',panePrefs.collapsed);
   const available=Math.max(0,width-16);
   let left=panePrefs.collapsed?44:Math.min(Math.max(Number(panePrefs.left)||240,180),Math.max(180,available-560));
   let rw=Math.min(Math.max(Number(panePrefs.right)||290,240),Math.max(240,available-left-320));
   layout.classList.toggle('wc-review-closed',!reviewOpen);
   layout.style.gridTemplateColumns=compact?'minmax(0,1fr)':reviewOpen?`${left}px 8px minmax(320px,1fr) 8px ${rw}px`:`${left}px 8px minmax(320px,1fr)`;
   toggle.textContent='‹';toggle.title='收起访谈列表';toggle.setAttribute('aria-label','收起访谈列表');
   const leftHeader=middle.querySelector('header'),rightHeader=right.querySelector('.wc-side-heading');if(leftHeader&&rightHeader)rightHeader.style.height=leftHeader.getBoundingClientRect().height+'px';
  }
  toggle.onclick=()=>{panePrefs.collapsed=true;store();apply();};expand.onclick=()=>{panePrefs.collapsed=false;store();apply();};
  function divider(side,before){
   const handle=document.createElement('div');handle.className='wc-divider wc-divider-'+side;handle.tabIndex=0;handle.setAttribute('role','separator');handle.setAttribute('aria-orientation','vertical');handle.setAttribute('aria-label',side==='left'?'调整访谈列表宽度':'调整复核栏宽度');handle.title='拖动调整宽度，双击恢复默认';layout.insertBefore(handle,before);
   handle.ondblclick=()=>{panePrefs.left=240;panePrefs.right=290;store();apply();};
   handle.onkeydown=e=>{if(!['ArrowLeft','ArrowRight'].includes(e.key))return;e.preventDefault();if(side==='left'&&panePrefs.collapsed)return;panePrefs[side]+=(e.key==='ArrowRight'?1:-1)*(side==='right'?-20:20);store();apply();};
   handle.onpointerdown=e=>{
    if(e.button!==0||layout.classList.contains('wc-pane-compact')||(side==='left'&&panePrefs.collapsed))return;
    e.preventDefault();handle.setPointerCapture(e.pointerId);const start=e.clientX,initial=side==='left'?list.getBoundingClientRect().width:right.getBoundingClientRect().width;
    handle.classList.add('dragging');
    handle.onpointermove=event=>{panePrefs[side]=initial+(event.clientX-start)*(side==='right'?-1:1);apply();panePrefs[side]=side==='left'?list.getBoundingClientRect().width:right.getBoundingClientRect().width;};
    const finish=()=>{handle.onpointermove=null;handle.classList.remove('dragging');store();};handle.onpointerup=finish;handle.onpointercancel=finish;
   };
  }
  divider('left',middle);divider('right',right);
  apply();const observer=new ResizeObserver(()=>{if(!layout.isConnected){observer.disconnect();return;}apply();});observer.observe(layout);observer.observe(middle.querySelector('header'));
 }
 const request=async(path,method='GET',body)=>{const r=await fetch(`/api/research-projects/${encodeURIComponent(pid)}/word-cooccurrence${path}`,{method,headers:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});const d=await r.json();if(!r.ok)throw Error(d.detail||'请求失败');return d;};
 const guard=fn=>async(...args)=>{if(busy)return;busy=true;save.disabled=next.disabled=true;try{await fn(...args);}catch(e){toast(e.message);}finally{busy=false;save.disabled=next.disabled=false;}};
 function text(t,b){return Array.from(t.text).slice(b.start,b.end).join('');}
 function selected(){return draft?.interviews.find(t=>t.id===tid)||draft?.interviews[0];}
 function mark(anchorId=null){
  const scroller=root.querySelector('.wc-cards');
  const anchor=anchorId?document.getElementById('wc-'+anchorId):scroller?[...scroller.querySelectorAll('.wc-card')].find(c=>c.getBoundingClientRect().bottom>scroller.getBoundingClientRect().top):null;
  const saved=scroller?{top:scroller.scrollTop,id:anchor?.id,offset:anchor?anchor.getBoundingClientRect().top-scroller.getBoundingClientRect().top:null}:null;
  const sideScroll=[...root.querySelectorAll('.wc-interviews,.wc-issues')].map(e=>[e.classList.contains('wc-issues')?'.wc-issues':'.wc-interviews',e.scrollTop]);
  dirty=true;draft.step=2;draft.confirmed=false;delete draft.graph;status.textContent='未保存';render();
  const nextScroller=root.querySelector('.wc-cards');
  if(saved&&nextScroller){nextScroller.scrollTop=saved.top;const nextAnchor=saved.id?document.getElementById(saved.id):null;if(nextAnchor&&saved.offset!==null)nextScroller.scrollTop+=nextAnchor.getBoundingClientRect().top-nextScroller.getBoundingClientRect().top-saved.offset;}
  for(const [selector,top] of sideScroll){const e=root.querySelector(selector);if(e)e.scrollTop=top;}
 }
 function payload(confirm=false){return {revision:draft.revision,confirm,interviews:draft.interviews.map(t=>({id:t.id,blocks:t.blocks,resolved:t.issues.flatMap((x,i)=>x.resolved?[i]:[])}))};}
 async function persist(confirm=false){const r=await request('','PUT',payload(confirm));draft.revision=r.revision;draft.step=r.step;dirty=false;status.textContent='草稿已保存';if(confirm)await reload();}
 async function reload(){loading=true;save.hidden=next.hidden=saveResult.hidden=true;status.textContent='正在加载…';historyPicker.disabled=true;window.workspaceHeader?.refresh();try{draft=await request('');await loadHistory();tid=draft?.interviews.some(t=>t.id===tid)?tid:draft?.interviews[0]?.id||'';}finally{loading=false;historyPicker.disabled=false;render();window.workspaceHeader?.refresh();}clearTimeout(poll);if(draft?.status==='running')poll=setTimeout(()=>reload().catch(e=>toast(e.message)),3000);}
 save.onclick=guard(()=>persist());next.onclick=guard(async()=>{if(draft?.step===2)await persist(true);else if(draft?.step===3){const words=draft.selected_words||[];await request('/graph','POST',{words});await reload();}});
picker.onchange=guard(async()=>{if(dirty&&!confirm('当前改动尚未保存，放弃这些改动并切换项目？')){picker.value=pid;return;}pid=picker.value;dirty=false;issueIndex=0;if(pid)await reload();else{draft=null;render();}});
window.wordCooccurrence={get loading(){return loading;},historyPicker,saveResult,get active(){return active;},get projectId(){return pid;},get step(){return draft?.step;},get hasResult(){return !!draft?.graph;},get materials(){return draft?.interviews||[];},controls:[picker,status,save,next],activate:()=>tab?.click(),leave:()=>{active=false;root.hidden=true;document.querySelector('#focused').classList.remove('word-co-active');},setStep:step=>{if(draft?.history_id){toast('历史结果只读，请先切换到当前草稿');return;}if(!draft||![2,3,4].includes(step))return;if(step===3&&!draft.confirmed)return;if(step===4&&!draft.graph)return;draft.step=step;render();window.workspaceHeader?.refresh();}};
function activate(){active=true;root.hidden=false;document.querySelector('#focused').classList.add('word-co-active');document.querySelectorAll('.network-tabs button').forEach(b=>b.classList.toggle('active',b===tab));picker.replaceChildren(new Option('请选择研究项目',''),...researchProjects.map(p=>new Option(p.name,p.id)));pid=dirty?pid:(selectedResearchProject?.id||pid||researchProjects[0]?.id||'');picker.value=pid;window.workspaceHeader?.refresh();if(pid&&!dirty)guard(reload)();else render();}
 let tab;
 const installer=new MutationObserver(()=>{const tabs=document.querySelector('.network-tabs');if(!tabs)return;if(tab){if(tabs.lastElementChild!==tab)tabs.append(tab);return;}tab=document.createElement('button');tab.type='button';tab.textContent='词语共现图';tab.onclick=activate;tabs.append(tab);tabs.addEventListener('click',e=>{if(e.target.closest('button')!==tab){active=false;root.hidden=true;document.querySelector('#focused').classList.remove('word-co-active');window.workspaceHeader?.refresh();}});});installer.observe(document.body,{subtree:true,childList:true});
 function dialog(title,content){const d=document.createElement('dialog');d.className='wc-dialog';const h=document.createElement('h3');h.textContent=title;const close=document.createElement('button');close.textContent='关闭';close.onclick=()=>d.close();d.append(h,content,close);document.body.append(d);d.onclose=()=>d.remove();d.showModal();return d;}
 async function showSourceDrawer(t,b){
  closeInlineSplit();
  const shared=window.createEvidenceDrawer?.(t.name+' · 完整原文');
  const drawer=shared?.drawer||document.createElement('dialog');drawer.className='wc-source-drawer';
  const note=shared?.note||document.createElement('p'),body=shared?.body||document.createElement('div');note.className='wc-source-note';body.className='wc-source-body';note.textContent='正在核对原文版本…';
  if(!shared){const head=document.createElement('header'),title=document.createElement('strong'),close=document.createElement('button');title.textContent=t.name+' · 完整原文';close.textContent='×';close.setAttribute('aria-label','关闭原文');close.onclick=()=>drawer.close();head.append(title,close);drawer.append(head,note,body);document.body.append(drawer);drawer.onclose=()=>drawer.remove();drawer.showModal();}
  drawer.addEventListener('click',e=>{if(e.target===drawer){const r=drawer.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)drawer.close();}});
  let current;
  try{const response=await fetch(`/api/projects/${encodeURIComponent(t.id)}/transcript`);if(!response.ok)throw Error();const data=await response.json();current=data.text??data.transcript??data.content;if(typeof current!=='string')throw Error();}
  catch{note.textContent='无法核对最新版本，以下显示切块时保存的原文；浅绿仅定位该版本。';}
  if(!drawer.isConnected)return;
  if(current!==undefined&&current!==t.text){note.textContent='原文已更新，以下显示最新原文；旧块位置可能变化，已停止高亮。';body.textContent=current;return;}
  if(current!==undefined)note.textContent='原文只读 · 浅绿色为当前块，已核对版本一致';
  const chars=Array.from(t.text),highlight=document.createElement('mark');highlight.textContent=chars.slice(b.start,b.end).join('');body.append(document.createTextNode(chars.slice(0,b.start).join('')),highlight,document.createTextNode(chars.slice(b.end).join('')));
  requestAnimationFrame(()=>{body.scrollTop=highlight.offsetTop-body.offsetTop-60;});
 }
 function split(t,b,cuts){const points=[b.start,...cuts,b.end];if(!cuts.length||cuts.some(c=>!(b.start<c&&c<b.end)))return;const at=t.blocks.indexOf(b);t.blocks.splice(at,1,...points.slice(0,-1).map((a,i)=>({...b,id:crypto.randomUUID(),start:a,end:points[i+1]})));}
 function merge(t,i){
  if(i<0||i+1>=t.blocks.length)return false;
  const first=t.blocks[i],second=t.blocks[i+1];
  if(first.include!==second.include&&!confirm('两块纳入状态不同，合并后沿用前一块状态？'))return false;
  for(const hint of t.issues){
   const ranges=hint.merge_target_ranges;
   if(hint.resolved||!Array.isArray(ranges)||ranges.length!==2)continue;
   if(ranges.every(([start,end])=>first.start<=start&&end<=second.end)&&ranges.some(([start,end])=>start<first.end&&end<=first.end)&&ranges.some(([start,end])=>start>=second.start&&end<=second.end))hint.resolved=true;
  }
  if(reviewBlock===second.id)reviewBlock=first.id;
  const anchorId=first.id;first.end=second.end;t.blocks.splice(i+1,1);issueIndex=0;mark(anchorId);return true;
 }
 function manual(t,b){const c=document.createElement('div');c.innerHTML='<p>点击一句的开头，在该位置拆分；原文不会改变。</p>';const re=/[。！？!?；;\n]+/g;let m,a=0;const starts=[0];while((m=re.exec(text(t,b))))starts.push(m.index+m[0].length);starts.push(text(t,b).length);for(let i=0;i+1<starts.length;i++){const button=document.createElement('button');button.className='wc-sentence';button.textContent=text(t,b).slice(starts[i],starts[i+1]);button.disabled=i===0;button.onclick=()=>{split(t,b,[b.start+starts[i]]);d.close();mark();};c.append(button);}const d=dialog('手动拆分',c);}
 let disposeWords=()=>{};
 function render(){
  disposeWords();disposeWords=()=>{};
  closeInlineSplit();
  root.replaceChildren();save.hidden=next.hidden=!draft||draft.status==='running'||draft.status==='failed';save.hidden=save.hidden||draft?.step!==2;next.hidden=next.hidden||draft?.step===4;next.textContent=draft?.step===3?'确认特征词并生成 →':'确认切块并继续 →';
  saveResult.hidden=!draft?.graph;saveResult.disabled=!!draft?.history_id;status.textContent=draft?.history_id?'历史结果 · 只读':dirty?'未保存':draft?.stale?'原文已更新':draft?.status==='running'?draft.progress||'AI正在切块…':draft?'草稿已保存':'';
  if(!pid){root.textContent='请先选择研究项目。';return;}
  if(!draft||draft.status==='failed'){renderStart();return;}
  if(draft.status==='running'){root.innerHTML='<div class="wc-empty">正在准备话题块：优先复用索引，缺少索引时新建。可切换到其它页面，任务继续运行。</div>';return;}
  if(draft.stale){root.innerHTML=`<p class="wc-warning">${esc(draft.stale)}</p>`;renderStart();return;}
  const heading=document.createElement('div');heading.className='wc-heading';heading.innerHTML=`<h2>${draft.step===2?'切块复核':draft.step===3?'特征词确认':'词语共现图'}</h2><select aria-label="流程步骤"><option value="2">第 2/4 步 · 切块复核</option>${draft.confirmed?'<option value="3">第 3/4 步 · 特征词确认</option>':''}${draft.graph?'<option value="4">第 4/4 步 · 共现图</option>':''}</select><span>调整讨论边界，保留访谈原文。</span>`;root.append(heading);heading.querySelector('select').value=draft.step;heading.querySelector('select').onchange=e=>{draft.step=Number(e.target.value);render();};
  if(draft.step===3){
   heading.querySelector('span').remove();
   const help=document.createElement('span');help.className='wc-count-help fw-heading-help';
   const helpButton=document.createElement('button');helpButton.type='button';helpButton.textContent='?';helpButton.setAttribute('aria-label','特征词确认说明');
   const tip=document.createElement('span');tip.className='wc-count-tooltip';tip.id='fw-heading-tooltip';tip.setAttribute('role','tooltip');tip.textContent='选择有研究意义的词，作为共现分析的节点。每个文本块中的同一词只计一次；统计范围以当前设置为准。';helpButton.setAttribute('aria-describedby',tip.id);help.append(helpButton,tip);heading.querySelector('h2').append(help);
   helpButton.onclick=()=>help.classList.toggle('open');helpButton.onkeydown=e=>{if(e.key==='Escape')help.classList.remove('open');};
   disposeWords=window.renderFeatureWords({root,heading,draft,notify:toast,showSource:showSourceDrawer,recommend:body=>request('/recommend','POST',body),setPending:value=>{next.disabled=value||busy;},apply:async({mode,stopwords,keep})=>{
    if(busy)throw Error('正在处理，请稍后再试');busy=true;next.disabled=true;
    try{await request('/words','POST',{mode,stopwords});draft=await request('');const available=new Set(draft.candidates.map(x=>x.word));const removed=keep.filter(w=>!available.has(w)),notApplied=stopwords.filter(w=>!draft.stopwords.includes(w));draft.selected_words=keep.filter(w=>available.has(w));render();toast('重新分词完成'+(removed.length?'；不再出现的已选词已移除：'+removed.join('、'):'，已保留仍出现的已选词')+(notApplied.length?'；受保护词未加入停用词：'+notApplied.join('、'):''));}
    finally{busy=false;next.disabled=false;}
   }});return;
  }if(draft.step===4){heading.querySelector('select').remove();heading.querySelector('span').remove();disposeWords=window.renderWordNetwork({root,heading,draft,showSource:showSourceDrawer});return;}
  const t=selected();if(reviewInterview!==t.id){reviewInterview=t.id;reviewBlock=null;reviewOpen=false;}
  const scope=reviewBlock?t.blocks.find(b=>b.id===reviewBlock):null;
  if(reviewBlock&&!scope){reviewBlock=null;reviewOpen=false;}
  const issues=t.issues.filter(x=>!x.resolved&&(!scope||(scope.start<=x.start&&x.start<scope.end)));issueIndex=Math.min(issueIndex,Math.max(0,issues.length-1));const issue=issues[issueIndex]||(scope?t.issues.findLast(x=>x.resolved&&scope.start<=x.start&&x.start<scope.end):null);
  const layout=document.createElement('div');layout.className='wc-layout';layout.innerHTML=`<aside class="wc-list"><h3>访谈稿 · ${draft.interviews.length}</h3><select aria-label="筛选访谈"><option value="all">全部访谈</option><option value="pending">仅待复核</option></select><div class="wc-interviews"></div></aside><div class="wc-middle"><header><h3>${esc(t.name)}</h3><button data-filter>${onlyIssues?'查看全部块':'仅待复核'}</button></header><div class="wc-cards"></div></div><aside class="wc-issues"><h3>待核对问题 <span>${issues.length}</span></h3><div class="wc-issue-content"></div><details open><summary>复核规则</summary><p>只调整边界，原文保持不变。排除仅影响统计，不删除材料。超过500字是提醒，不是强制切分。</p></details><details><summary>超短回答如何处理</summary><p>有含义的确认或否定保留；按相邻语境合并。纯填充语可排除统计。</p></details></aside>`;root.append(layout);
  function list(pending=false){const list=layout.querySelector('.wc-interviews');list.replaceChildren();for(const x of draft.interviews){const n=x.issues.filter(y=>!y.resolved).length;if(pending&&!n)continue;const b=document.createElement('button');b.className=x.id===t.id?'active':'';b.innerHTML=`<span>${esc(x.name)}</span><small class="wc-total-blocks">共${x.blocks.length}块</small>`;b.onclick=()=>{tid=x.id;issueIndex=0;render();};list.append(b);}}list();layout.querySelector('.wc-list select').onchange=e=>list(e.target.value==='pending');layout.querySelector('[data-filter]').onclick=()=>{onlyIssues=!onlyIssues;render();};
  heading.classList.add('wc-side-heading');
  layout.querySelector('.wc-issues').prepend(heading);
  const hideReview=document.createElement('button');hideReview.className='wc-hide-review';hideReview.textContent='×';hideReview.setAttribute('aria-label','收起复核栏');hideReview.onclick=()=>{reviewOpen=false;refreshReviewPane();};heading.append(hideReview);
  layout.querySelector('[data-filter]').setAttribute('aria-pressed',String(onlyIssues));
  setupPanes(layout);
  const oldFilter=layout.querySelector('[data-filter]'),filter=document.createElement('label');filter.className='wc-review-toggle';
  const titleGroup=document.createElement('div');titleGroup.className='wc-interview-title-group';
  const interviewTitle=layout.querySelector('.wc-middle>header h3');interviewTitle.before(titleGroup);titleGroup.append(interviewTitle);
  const pendingTotal=t.issues.filter(x=>!x.resolved).length;
  const hadReviewHints=t.issues.length>0;
  const pendingCount=document.createElement('span');pendingCount.className='wc-pending-count';pendingCount.textContent=pendingTotal?`待核对${pendingTotal}项`:hadReviewHints?'已核对':'无待核对';pendingCount.classList.toggle('wc-reviewed',pendingTotal===0&&hadReviewHints);pendingCount.classList.toggle('wc-no-review',!hadReviewHints);
  const help=document.createElement('span');help.className='wc-count-help';
  const helpButton=document.createElement('button');helpButton.type='button';helpButton.textContent='?';helpButton.setAttribute('aria-label','待核对数量说明');helpButton.setAttribute('aria-expanded','false');
  const explanation=document.createElement('span');explanation.className='wc-count-tooltip';explanation.id='wc-count-explanation';explanation.setAttribute('role','tooltip');explanation.textContent=pendingTotal?'尚未处理的复核提示数量，一块可能有多条提示':'当前没有未处理的切块复核提示，不代表整篇原文已验证。';helpButton.setAttribute('aria-describedby',explanation.id);
  helpButton.onclick=()=>{const open=help.classList.toggle('open');helpButton.setAttribute('aria-expanded',String(open));};help.onkeydown=e=>{if(e.key==='Escape'){help.classList.remove('open');helpButton.setAttribute('aria-expanded','false');}};
  help.append(helpButton,explanation);titleGroup.append(pendingCount,help);
  filter.innerHTML='<span>仅待复核</span><input type="checkbox" role="switch" aria-label="仅待复核"><i aria-hidden="true"></i>';
  filter.querySelector('input').checked=onlyIssues;filter.querySelector('input').onchange=e=>{onlyIssues=e.target.checked;render();};oldFilter.replaceWith(filter);
  heading.querySelector('select')?.remove();
  heading.querySelector('span')?.remove();
  heading.querySelectorAll('option').forEach(o=>{o.textContent=o.textContent.split(' · ')[0];});
  const cards=layout.querySelector('.wc-cards');t.blocks.forEach((b,i)=>{const own=t.issues.filter(x=>b.start<=x.start&&x.start<b.end&&!x.resolved);if(onlyIssues&&!own.length)return;const c=document.createElement('article');c.className='wc-card';c.id='wc-'+b.id;c.innerHTML=`<div class="wc-card-head"><span>块 ${i+1} · 字符 ${b.start}—${b.end}</span><select aria-label="是否纳入统计"><option value="yes">纳入统计</option><option value="no">排除统计</option></select></div><p class="wc-kind">${b.kind==='content'?'正文块':b.kind==='background'?'背景／资料块':'接话块'} · ${text(t,b).replace(/\s/g,'').length} 字</p><div class="wc-original"></div><footer><button data-split>✂ 手动拆分</button><button data-source>▤ 查看原文</button><span>${own.length?'待核对 '+own.length:''}</span></footer>`;const original=c.querySelector('.wc-original');const cuts=own.flatMap(x=>x.cuts||[]).filter(p=>b.start<p&&p<b.end).sort((a,z)=>a-z);let from=b.start;for(const cut of [...new Set(cuts)]){original.append(document.createTextNode(text(t,{start:from,end:cut})));const marker=document.createElement('div');marker.className='wc-cut-marker';marker.textContent='建议拆分位置';original.append(marker);from=cut;}original.append(document.createTextNode(text(t,{start:from,end:b.end})));c.querySelector('select').value=b.include?'yes':'no';c.querySelector('select').onchange=e=>{b.include=e.target.value==='yes';mark();};c.querySelector('[data-split]').onclick=()=>manual(t,b);c.querySelector('[data-source]').onclick=()=>{const pre=document.createElement('pre');pre.textContent=t.text;const d=dialog(t.name+' · 完整原文',pre);d.scrollTop=0;};cards.append(c);if(i+1<t.blocks.length&&!onlyIssues){const m=document.createElement('button');m.className='wc-merge';m.textContent='⌁ 合并相邻块';m.onclick=()=>merge(t,i);cards.append(m);}});
  cards.querySelectorAll('.wc-card').forEach(card=>{
   const meta=card.querySelector('.wc-card-head>span'),kind=card.querySelector('.wc-kind');
   const parts=kind.textContent.split(' · '),labels={content:'正文',background:'背景',interaction:'接话'};
   const number=meta.textContent.split(' · ')[0].replace('块 ','');
   meta.replaceChildren();const numberBadge=document.createElement('span');numberBadge.className='wc-block-number';numberBadge.textContent=number.padStart(2,'0');
   const description=document.createElement('span');description.textContent=(labels[parts[0]]||parts[0])+' · '+parts[1];meta.append(numberBadge,description);kind.remove();
   const block=t.blocks.find(x=>'wc-'+x.id===card.id),original=card.querySelector('.wc-original');
   highlightExactIssues(original,t,block);
   const pending=t.issues.filter(x=>!x.resolved&&block.start<=x.start&&x.start<block.end).length;
   if(pending){const badge=document.createElement('button');badge.type='button';badge.className='wc-block-pending';badge.textContent=`待核对${pending}项`;badge.onclick=()=>{reviewBlock=block.id;reviewOpen=true;issueIndex=0;refreshReviewPane();};meta.append(badge);}
   card.querySelectorAll('footer>span:not(.wc-readonly)').forEach(el=>el.remove());
   if(!block.include){
    card.classList.add('wc-excluded-collapsed');
    const toggle=document.createElement('button');toggle.type='button';toggle.className='wc-excluded-toggle';toggle.textContent='展开原文 ▾';toggle.setAttribute('aria-expanded','false');
    toggle.textContent='展开 ▾';
    toggle.onclick=()=>{const collapsed=card.classList.toggle('wc-excluded-collapsed');toggle.textContent=collapsed?'展开 ▾':'收起 ▴';toggle.setAttribute('aria-expanded',String(!collapsed));};
    const head=card.querySelector('.wc-card-head'),badge=document.createElement('small');badge.className='wc-excluded-badge';badge.textContent='已排除';head.after(badge);head.insertBefore(toggle,head.querySelector('select'));
   }
   enableInlineSplit(original,t,block);original.title='点击原文位置，在此拆分';
   card.querySelector('[data-source]').onclick=()=>showSourceDrawer(t,block);
   const native=card.querySelector('.wc-card-head>select'),menu=document.createElement('details');menu.className='wc-stat-menu';menu.dataset.state=block.include?'yes':'no';
   const summary=document.createElement('summary');summary.textContent=block.include?'纳入统计':'排除统计';
   const choices=document.createElement('div');choices.className='wc-stat-choices';
   for(const [value,label] of [['yes','纳入统计'],['no','排除统计']]){
    const button=document.createElement('button');button.type='button';button.textContent=label;button.dataset.value=value;button.classList.toggle('selected',native.value===value);
    button.onclick=()=>{menu.open=false;if(native.value!==value){native.value=value;native.dispatchEvent(new Event('change'));}};choices.append(button);
   }
   menu.append(summary,choices);native.hidden=true;native.after(menu);
   menu.ontoggle=()=>{if(menu.open)cards.querySelectorAll('.wc-stat-menu').forEach(other=>{if(other!==menu)other.open=false;});};
   menu.onkeydown=e=>{if(e.key==='Escape')menu.open=false;};
   card.querySelector('[data-split]').onclick=()=>{closeInlineSplit();original.classList.add('wc-split-ready');toast('请点击原文中要拆分的位置');};
   card.querySelector('[data-split]').hidden=true;
   const readonly=document.createElement('span');readonly.className='wc-readonly';readonly.textContent='原文只读';card.querySelector('footer').append(readonly);
  });
  cards.querySelectorAll('.wc-merge').forEach(button=>{
   const before=button.previousElementSibling,after=button.nextElementSibling;
   const a=t.blocks.findIndex(x=>'wc-'+x.id===before?.id),b=t.blocks.findIndex(x=>'wc-'+x.id===after?.id);
   button.dataset.tooltip=`合并块${a+1}与块${b+1}`;
   button.removeAttribute('title');button.setAttribute('aria-label',button.dataset.tooltip);
   button.innerHTML='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m10 14 4-4M8 16l-1 1a4 4 0 0 1-6-6l4-4a4 4 0 0 1 6 0M16 8l1-1a4 4 0 0 1 6 6l-4 4a4 4 0 0 1-6 0"/></svg><span>合并</span>';
   const band=document.createElement('div');band.className='wc-merge-band';button.before(band);band.append(button);
  });
  const panel=layout.querySelector('.wc-issue-content');if(!issue){panel.innerHTML='<p>没有待核对建议。仍可人工检查并调整边界。</p>';return;}
  const sourceBlock=t.blocks.find(b=>b.start<=issue.start&&issue.start<b.end);
  const blockIndex=t.blocks.indexOf(sourceBlock);
  if(blockIndex>=0){const issueHeading=layout.querySelector('.wc-issues>h3');issueHeading.replaceChildren(document.createTextNode(`块 ${blockIndex+1} `));const countBadge=document.createElement('span');countBadge.className='wc-issue-count-pill';countBadge.textContent=issues.length?`待核对${issues.length}项`:'已核对';countBadge.classList.toggle('wc-reviewed',!issues.length);issueHeading.append(countBadge);}
  const sourceChars=Array.from(t.text),sentenceStarts=[0];
  for(const match of t.text.matchAll(/[。！？!?；;\n]+/g)){const offset=Array.from(t.text.slice(0,match.index+match[0].length)).length;if(offset<sourceChars.length)sentenceStarts.push(offset);}
  const blockLabel=sid=>{const start=sentenceStarts[Number(sid.slice(1))-1],index=t.blocks.findIndex(b=>b.start<=start&&start<b.end);return index>=0?`块 ${index+1}`:'当前片段';};
  const reason=String(issue.reason||'').replace(/(S\d{5})\s*[-—–]\s*(S\d{5})/g,(_,a,b)=>{const first=blockLabel(a),last=blockLabel(b);return first===last?first:`${first}至${last}`;}).replace(/S\d{5}/g,blockLabel);
  let direction='结合左侧原文检查话题是否连续；同一话题可合并，出现独立话题可在转折处拆分。';
  let applyLabel='采用建议';
  if(issue.action==='merge_previous'){direction=blockIndex>0?`如果确认是上一块同一话题的延续或收尾，可合并块 ${blockIndex} 与块 ${blockIndex+1}；如果是独立话题，保持分开。`:'当前没有前一块，请结合原文检查边界。';applyLabel='合并到前一块';}
  else if(issue.action==='merge_next'){direction=blockIndex+1<t.blocks.length?`如果确认与下一块属于同一话题，可合并块 ${blockIndex+1} 与块 ${blockIndex+2}；如果话题不同，保持分开。`:'当前没有后一块，请结合原文检查边界。';applyLabel='与后一块合并';}
  else if(issue.action==='split'){direction='如果建议位置前后是两个独立话题，可在该处拆分；如果是同一案例的连续追问或补充，保持完整。';applyLabel='按建议拆分';}
  panel.innerHTML=`<p class="wc-reason-text">${esc(reason)}</p><p class="wc-review-direction">${esc(direction)}</p>${issue.action!=='keep'?`<button class="primary" data-apply>${esc(applyLabel)}</button>`:''}`;
  if(sourceBlock){
   const previous=issue.action==='merge_previous'||/前文|前一|上一|前块/.test(reason),following=issue.action==='merge_next'||/后续|后文|后一|下一|后块/.test(reason);
   const neighbors=(previous&&!following?[t.blocks[blockIndex-1]]:following&&!previous?[t.blocks[blockIndex+1]]:[t.blocks[blockIndex-1],t.blocks[blockIndex+1]]).filter(Boolean);
   if(neighbors.length){const view=document.createElement('button');view.className='wc-view-neighbor';view.textContent='查看相邻块';view.onclick=()=>{
    onlyIssues=false;refreshReviewPane();
    const pair=[sourceBlock,...neighbors].sort((a,b)=>a.start-b.start);
    for(const block of pair){const card=document.getElementById('wc-'+block.id);if(card?.classList.contains('wc-excluded-collapsed'))card.querySelector('.wc-excluded-toggle')?.click();card?.classList.add('wc-neighbor-highlight');}
    document.getElementById('wc-'+pair[0].id)?.scrollIntoView({behavior:'smooth',block:'start'});
   };const apply=panel.querySelector('[data-apply]');if(apply)apply.before(view);else panel.append(view);}
  }
  const keep=document.createElement('button');keep.type='button';keep.dataset.dismiss='';keep.textContent=issue.resolved?'已核对':['merge_previous','merge_next'].includes(issue.action)?'保持分开':issue.action==='split'?'保持此块完整':'保持当前分块';keep.disabled=!!issue.resolved;keep.classList.toggle('wc-reviewed',!!issue.resolved);keep.onclick=()=>{issue.resolved=true;mark();};panel.append(keep);
  if(issue.resolved)panel.querySelector('[data-apply]')?.remove();
  if(issue.resolved){
   const pendingBlocks=t.blocks.filter(b=>t.issues.some(x=>!x.resolved&&b.start<=x.start&&x.start<b.end));
   const nextBlock=pendingBlocks.find(b=>b.start>sourceBlock.start)||pendingBlocks[0];
   if(nextBlock){const go=document.createElement('button');go.type='button';go.className='wc-next-review';go.textContent=`→ 下一个复核块 · 块 ${t.blocks.indexOf(nextBlock)+1}`;go.onclick=()=>{reviewBlock=nextBlock.id;reviewOpen=true;issueIndex=0;refreshReviewPane();const card=document.getElementById('wc-'+nextBlock.id);if(card?.classList.contains('wc-excluded-collapsed'))card.querySelector('.wc-excluded-toggle')?.click();card?.scrollIntoView({behavior:'smooth',block:'start'});};panel.append(go);}
   else{const done=document.createElement('p');done.className='wc-review-done';done.textContent='本篇复核已完成';panel.append(done);}
  }
  panel.querySelector('[data-apply]')?.addEventListener('click',()=>{const i=t.blocks.findIndex(b=>b.start<=issue.start&&issue.start<b.end),b=t.blocks[i];if(issue.action==='split')split(t,b,issue.cuts||[]);else if(issue.action==='merge_previous'){if(i===0){toast('没有相邻前块');return;}if(!merge(t,i-1))return;}else if(issue.action==='merge_next'){if(i+1===t.blocks.length){toast('没有相邻后块');return;}if(!merge(t,i))return;}else if(issue.action==='filler')b.include=false;issue.resolved=true;mark();});
 }
 function renderStart(){
  const project=researchProjects.find(x=>x.id===pid),rows=[];
  for(const x of project?.interviews||[])rows.push({name:x.name,id:x.id});
  for(const [index,x] of (project?.uploaded_transcripts||[]).entries()){
   if((project.interviews||[]).some(t=>t.id===x.workspace_project_id))continue;
   rows.push({name:x.name,upload:index,previewId:x.workspace_project_id});
  }
  const fileIcon='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 2h8l5 5v15H6zM14 2v6h5"/></svg>';
  const page=document.createElement('div');page.className='wc-selection-page';
page.innerHTML=`<div class="wc-selection-title"><h2>选择访谈稿</h2><select aria-label="流程步骤"><option>第 1/4 步</option></select></div><p class="wc-selection-intro">选择用于分析的访谈稿，优先复用已有索引切块，缺少索引时新建；确认后进入分词与统计。</p>${draft?.error?`<p class="wc-warning">${esc(draft.error)}</p>`:''}<div class="wc-selection-grid"><section class="wc-material-card"><div class="wc-material-search"><label><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10" cy="10" r="6"/><path d="m15 15 5 5"/></svg><input type="search" placeholder="搜索访谈稿" aria-label="搜索访谈稿"></label><span>共 ${rows.length} 份</span></div><div class="wc-select-all"><label><input type="checkbox" data-all checked>全选</label><span data-count></span></div><div class="wc-material-rows"></div><p class="wc-material-empty" hidden>没有匹配的访谈稿</p><footer><span data-summary></span><button type="button" class="primary" data-start>准备话题块 <span aria-hidden="true">→</span></button></footer></section><aside class="wc-followup"><h3>后续流程</h3><ol><li><span class="wc-step-number">1</span><div><strong>按话题切块</strong><p>复用话题索引，缺少时新建。</p></div></li><li><span class="wc-step-number">2</span><div><strong>复核讨论边界</strong><p>检查并调整切分位置。</p></div></li><li><span class="wc-step-number">3</span><div><strong>确认特征词</strong><p>复核后再生成共现网络。</p></div></li></ol><details class="wc-processing-settings"><summary><span aria-hidden="true">⚙</span> 处理设置</summary><div>最多同时处理2篇访谈。已有索引不重复切块；正文默认纳入统计，资料头默认排除。长块仅提示人工检查，支持拆分、合并。</div></details><p class="wc-model-label">切块：优先复用千问话题索引</p></aside></div><p class="wc-selection-note">开始前可随时调整材料选择。</p>`;
  root.append(page);
  const list=page.querySelector('.wc-material-rows'),all=page.querySelector('[data-all]'),start=page.querySelector('[data-start]');
  for(const row of rows){
   const item=document.createElement('div');item.className='wc-material-row selected';item.dataset.name=row.name;
   item.innerHTML=`<label><input type="checkbox" ${row.id?`data-id="${esc(row.id)}"`:`data-upload="${row.upload}"`} checked>${fileIcon}<span>${esc(row.name)}</span></label><button type="button" class="wc-preview" aria-label="预览${esc(row.name)}">预览 <span aria-hidden="true">›</span></button>`;
   item.querySelector('input').onchange=update;
   item.querySelector('button').onclick=guard(async()=>{
    const id=row.id||row.previewId;
    if(!id){toast('该上传稿尚未准备原文，请从项目资料中打开预览');return;}
    const shared=window.createEvidenceDrawer(row.name+' · 原文预览');
    shared.note.textContent='正在读取整篇原文…';
    try{
     const response=await fetch(`/api/projects/${encodeURIComponent(id)}/transcript`);
     const data=await response.json();if(!response.ok)throw Error(data.detail||'原文加载失败');
     if(!shared.drawer.isConnected)return;
     if(typeof data.text!=='string')throw Error('原文内容为空');
     shared.body.textContent=data.text;shared.note.textContent='整篇原文 · 只读';
    }catch(error){if(shared.drawer.isConnected){shared.note.textContent='原文加载失败';shared.body.textContent='请关闭后重新预览；已勾选的访谈稿保持不变。';}throw error;}
   });
   list.append(item);
  }
  function update(){
   const inputs=[...list.querySelectorAll('input')],n=inputs.filter(x=>x.checked).length;
   page.querySelector('[data-count]').textContent=`已选 ${n} 份`;
   page.querySelector('[data-summary]').textContent=`✓ 已选择 ${n} 份访谈稿`;
   all.checked=inputs.length>0&&n===inputs.length;all.indeterminate=n>0&&n<inputs.length;
   start.disabled=n===0;
   for(const input of inputs)input.closest('.wc-material-row').classList.toggle('selected',input.checked);
  }
  all.onchange=()=>{list.querySelectorAll('input').forEach(input=>input.checked=all.checked);update();};
  page.querySelector('input[type=search]').oninput=event=>{
   const term=event.target.value.trim().toLowerCase();let visible=0;
   for(const item of list.children){item.hidden=!item.dataset.name.toLowerCase().includes(term);if(!item.hidden)visible++;}
   page.querySelector('.wc-material-empty').hidden=visible>0;
  };
  start.onclick=guard(async()=>{
   if(draft&&!confirm('重新切块会替换当前草稿（后台保留备份），继续？'))return;
   start.disabled=true;start.textContent='正在准备…';
   try{await request('/start','POST',{ids:[...list.querySelectorAll('[data-id]:checked')].map(x=>x.dataset.id),uploads:[...list.querySelectorAll('[data-upload]:checked')].map(x=>Number(x.dataset.upload)),replace:!!draft});await reload();}
   finally{start.textContent='准备话题块 →';start.disabled=false;}
  });
  update();
 }
function renderWords(){const c=document.createElement('div');c.className='wc-words';c.innerHTML='<p>分词后剔除停用词。每块每词只计一次；请勾选有研究意义的特征词，不自动将全部词变为节点。</p><label>统计文本范围<select aria-label="统计文本范围"><option value="answers">仅明确标注的受访者回答</option><option value="all">整块原文（包含提问）</option></select></label><label>停用词（空格或换行分隔）<textarea></textarea></label><button>应用停用词并分词</button><div class="wc-word-list"></div>';root.append(c);c.querySelector('select').value=draft.token_mode||'answers';c.querySelector('textarea').value=(draft.stopwords||['呃','啊','呀','呢','嗯','你','我','是','他','就','也','那','这','说','到','在','吧','我们','一个','什么','咋','娃','人家','然后','比方说','就是','比方','都是','都']).join(' ');c.querySelector('button').onclick=guard(async()=>{await request('/words','POST',{mode:c.querySelector('select').value,stopwords:c.querySelector('textarea').value.split(/\s+/).filter(Boolean)});await reload();});for(const x of draft.candidates||[]){const l=document.createElement('label');l.innerHTML=`<input type="checkbox" data-word="${esc(x.word)}" ${(draft.selected_words||[]).includes(x.word)?'checked':''}>${esc(x.word)} <small>${x.blocks}块</small>`;c.querySelector('.wc-word-list').append(l);}}
function renderGraph(){const c=document.createElement('div');c.className='wc-graph';c.innerHTML='<label>至少 <input type="number" min="1" value="5"> 块支持</label><p>线宽表示共现块数，不表示因果。点击连线查看支持原文。</p><svg viewBox="0 0 1100 700"></svg><aside></aside>';root.append(c);const ns='http://www.w3.org/2000/svg';function draw(){const svg=c.querySelector('svg');svg.replaceChildren();const es=draft.graph.edges.filter(e=>e.count>=Number(c.querySelector('input').value)),ids=new Set(es.flatMap(e=>[e.source,e.target])),nodes=draft.graph.nodes.filter(n=>ids.has(n.id));const positions=new Map(nodes.map(n=>[n.id,{x:n.x,y:n.y}]));const make=(tag,attrs,txt)=>{const e=document.createElementNS(ns,tag);for(const [k,v]of Object.entries(attrs))e.setAttribute(k,v);if(txt)e.textContent=txt;svg.append(e);return e;};for(const e of es){const a=positions.get(e.source),b=positions.get(e.target);const l=make('line',{x1:a.x,y1:a.y,x2:b.x,y2:b.y,stroke:'#75b9b6','stroke-width':1+4*(e.count/Math.max(...es.map(x=>x.count))),tabindex:0});l.onclick=()=>{const aside=c.querySelector('aside');aside.replaceChildren();const h=document.createElement('h3');h.textContent=`${e.source} — ${e.target} · ${e.count}块 / ${e.interviews}篇`;aside.append(h);for(const ref of e.evidence){const t=draft.interviews.find(x=>x.id===ref.interview_id),b=t.blocks.find(x=>x.id===ref.block_id);const p=document.createElement('p');p.textContent=t.name+'\n'+text(t,b);aside.append(p);}};make('text',{x:(a.x+b.x)/2,y:(a.y+b.y)/2,fill:'#49716f','font-size':12},String(e.count));}for(const n of nodes){const p=positions.get(n.id);make('circle',{cx:p.x,cy:p.y,r:11,fill:['#e8c553','#73b8b2','#92ace0','#be99c9','#86b596'][Math.max(0,n.group)%5]});make('text',{x:p.x+15,y:p.y+5,fill:'#142f37','font-size':15},n.label);}if(!nodes.length)make('text',{x:350,y:320},'当前阈值下没有连线，请降低阈值。');}c.querySelector('input').onchange=draw;draw();}
})();
