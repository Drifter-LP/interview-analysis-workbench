/* Organization is a separate, explicitly reviewed workflow. No automatic code edits. */
(() => {
 const el=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n;};
 const button=(text,fn)=>{const b=el('button','',text);b.type='button';b.onclick=fn;return b;};
 const closeButton=()=>{const b=button('×',()=>dialog.close());b.className='aco-close';b.title='关闭整理';b.setAttribute('aria-label','关闭整理');return b;};
 function displayReason(text,snapshot=[]){
  text=String(text||'');
  const identifiers=[];
  for(const c of snapshot){identifiers.push({id:c.id,label:c.name});for(const [i,r] of (c.references||[]).entries())if(r.id)identifiers.push({id:r.id,label:'第'+(i+1)+'处原文引用'});}
  // Replace only known unambiguous identifiers; never remove arbitrary numbers from evidence.
  text=text.replace(/(?<![a-z0-9])([a-f0-9]{6,64})(?:\.{3}|…)?(?![a-z0-9])/gi,(raw,id)=>{const found=identifiers.filter(x=>String(x.id).toLowerCase().startsWith(id.toLowerCase()));return found.length&&new Set(found.map(x=>x.label)).size===1?found[0].label:raw;});
  text=text.replace(/\s*\r?\n\s*/g,' ').trim();
  if(typeof Intl.Segmenter!=='function')return text;
  const sentences=[...new Intl.Segmenter('zh-CN',{granularity:'sentence'}).segment(text)].map(x=>x.segment);
  // Move an existing explicit comparison forward, without synthesizing a new research judgment.
  const index=sentences.findIndex(x=>/^\s*(两者|二者|这些编码|上述编码|这两个编码)/u.test(x));
  if(index>0)sentences.unshift(sentences.splice(index,1)[0]);
  return sentences.join('');
 }
 function reasonBlock(text,snapshot){return el('p','aco-ai-reason',displayReason(text,snapshot));}
 function methodHelp(owner){
  const wrap=el('div','aco-method'),label=el('span','','编码整理方法'),toggle=button('i',()=>{pinned=!pinned;show(pinned);}),panel=el('div','aco-method-panel');
  const events=new AbortController();let pinned=false,hideTimer;
  panel.id='aco-method-'+Math.random().toString(36).slice(2);panel.hidden=true;panel.setAttribute('role','tooltip');
  toggle.className='aco-method-toggle';toggle.setAttribute('aria-label','编码整理方法说明');toggle.setAttribute('aria-expanded','false');toggle.setAttribute('aria-controls',panel.id);toggle.setAttribute('aria-describedby',panel.id);
  panel.append(el('p','','每个编码最多选取5段原文引用，并尽量分别选取处于访谈前、中、后位置的内容片段。超过4000字的单段引用不会发送给AI。AI只根据本次收到的引用提出建议，并非检查全部引文。'),el('p','','编码较多时，会分组检查，并让不同组之间的编码相互比较，减少遗漏跨组重复或边界问题的风险。AI只提供整理建议，不会自动合并或修改编码。'));
  function show(open){clearTimeout(hideTimer);panel.hidden=!open;toggle.setAttribute('aria-expanded',String(open));if(open){const r=toggle.getBoundingClientRect(),width=Math.min(520,innerWidth-40);panel.style.width=width+'px';panel.style.left=Math.max(20,Math.min(r.left,innerWidth-width-20))+'px';panel.style.top=Math.max(20,Math.min(r.bottom+8,innerHeight-panel.getBoundingClientRect().height-20))+'px';}}
  wrap.append(label,toggle,panel);
  wrap.onmouseenter=()=>show(true);wrap.onmouseleave=()=>{if(!pinned)hideTimer=setTimeout(()=>show(false),180);};
  toggle.onfocus=()=>show(true);wrap.onfocusout=e=>{if(!pinned&&!wrap.contains(e.relatedTarget))show(false);};
  document.addEventListener('pointerdown',e=>{if(!wrap.contains(e.target)){pinned=false;show(false);}},{signal:events.signal});
  owner.addEventListener('keydown',e=>{if(e.key==='Escape'&&!panel.hidden){e.preventDefault();e.stopPropagation();pinned=false;show(false);}},{signal:events.signal});
  window.addEventListener('resize',()=>{pinned=false;show(false);},{signal:events.signal});
  owner.addEventListener('close',()=>{clearTimeout(hideTimer);events.abort();},{once:true});return wrap;
 }
 const types={duplicate:'疑似重复',boundary:'边界冲突',granularity:'粒度差异'},actions={consider_merge:'考虑合并',keep_independent:'保留独立',check_definition:'检查定义',manual_review:'人工判断'};
 const states={pending:'待处理',kept:'已保留独立',skipped:'暂时跳过',merged:'已合并',undone:'已撤销'};
 const suggestionReviewed=s=>!s.stale&&['merged','kept'].includes(s.status);
 const codeStates={pending:'待审核',accepted:'已接受',modified:'已修改',rejected:'已拒绝'};
 const dialog=el('dialog','aco-dialog');dialog.setAttribute('aria-label','整理编码');document.body.append(dialog);
 let context=null,runs=[],runId='',suggestionId='',timer=null,generation=0,submitting=false;
 async function request(path,method='GET',body){const r=await fetch(path,{method,headers:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});const d=await r.json();if(!r.ok)throw Error(d.detail||'操作失败');return d;}
 const base=()=>context.endpoint+'/organize';
 const run=()=>runs.find(r=>r.id===runId)||runs.at(-1);
 function error(e){const box=dialog.querySelector('.aco-error');if(box)box.textContent=e.message||String(e);}
 dialog.addEventListener('close',()=>{clearTimeout(timer);generation++;});
 async function load(){const version=++generation,owner=base();try{const d=await request(owner);if(version!==generation||owner!==base())return;runs=d.runs;if(!runs.some(r=>r.id===runId))runId=runs.at(-1)?.id||'';render();clearTimeout(timer);if(runs.some(r=>r.status==='running')&&dialog.open)timer=setTimeout(load,1500);}catch(e){error(e);}}
 async function start(resume=false){
  if(submitting)return;submitting=true;
  try{
   if(resume){await request(base()+'/run','POST',{resume_run_id:run().id});await load();return;}
   const plan=await request(base()+'/plan');
   const confirm=el('dialog','aco-confirm');confirm.setAttribute('aria-label','确认开始整理');
   confirm.append(el('h3','','整理当前访谈的编码'),methodHelp(confirm),el('p','',`共 ${plan.code_count} 个未删除、未拒绝编码，计划 ${plan.task_count} 批检查。`));
   const omitted=plan.sampling.filter(s=>s.sent_count<s.valid_count||s.unresolved_count);
   if(omitted.length)confirm.append(el('p','ac-note',`${omitted.length} 个编码存在未送入的引用；整理结果中可对照完整引用。`));
   const row=el('div','aco-actions'),cancel=button('取消',()=>confirm.close()),go=button('开始整理',async()=>{
    go.disabled=true;try{const result=await request(base()+'/run','POST',{confirm_task_count:plan.task_count});runId=result.run_id;suggestionId='';confirm.close();await load();}catch(e){message.textContent=e.message;go.disabled=false;}
   }),message=el('p','aco-error');cancel.autofocus=true;go.disabled=!plan.code_count;row.append(cancel,go);confirm.append(message,row);confirm.onclose=()=>confirm.remove();document.body.append(confirm);confirm.showModal();
  }catch(e){error(e);}finally{submitting=false;}
 }
 async function decision(s,action,extra={}){
  if(submitting)return;submitting=true;const owner=context.endpoint;
  try{const d=await request(base()+'/'+run().id+'/suggestions/'+s.id,'POST',{action,...extra});if(owner!==context.endpoint)return;context.updated(d.coding);runs=d.organization.runs;render();}
  catch(e){error(e);throw e;}finally{submitting=false;}
 }
 function mergeDialog(s){
  const snapshot=run().snapshot,codes=s.code_ids.map(id=>snapshot.find(c=>c.id===id));
  const confirm=el('dialog','aco-confirm');confirm.setAttribute('aria-label','确认合并编码');
  confirm.append(el('h3','','确认合并编码'),el('p','ac-note','仅合并选中的编码及关联，原文不变；原编码及状态保留在合并记录中。'));
  const keep=el('select'),nameSource=el('select'),definitionSource=el('select'),name=el('input'),definition=el('textarea');
  keep.setAttribute('aria-label','保留编码ID');nameSource.setAttribute('aria-label','名称来源');definitionSource.setAttribute('aria-label','定义来源');name.setAttribute('aria-label','合并后名称');definition.setAttribute('aria-label','合并后定义');
  for(const c of codes){keep.append(new Option(c.name+' · '+c.id,c.id));nameSource.append(new Option('使用：'+c.name,c.id));definitionSource.append(new Option('使用：'+c.name,c.id));}
  if(s.candidate_name)nameSource.append(new Option('AI候选名称（需人工确认）','candidate'));
  if(s.candidate_definition)definitionSource.append(new Option('AI候选定义（需人工确认）','candidate'));
  name.value=codes[0].name;definition.value=codes[0].definition;
  nameSource.onchange=()=>name.value=nameSource.value==='candidate'?s.candidate_name:codes.find(c=>c.id===nameSource.value).name;
  definitionSource.onchange=()=>definition.value=definitionSource.value==='candidate'?s.candidate_definition:codes.find(c=>c.id===definitionSource.value).definition;
  for(const [label,node] of [['保留的编码ID',keep],['名称来源',nameSource],['最终编码名称（可修改）',name],['定义来源',definitionSource],['最终编码定义（可修改）',definition]])confirm.append(el('label','',label),node);
  confirm.append(el('p','aco-warning',codes.some(c=>c.status==='pending')?'包含待审核编码：合并结果仍为待审核，不会把所有引用当作已接受。':'全部编码已审核：合并后标为已修改，原有状态仍完整保留。'),el('p','ac-note','只有精确相同的原文位置才去重；重叠但不相同的引用分别保留。撤销仅在合并后编码未被再编辑时执行，避免覆盖新修改。'));
  const message=el('p','aco-error'),row=el('div','aco-actions'),go=button('确认合并并保存',async()=>{
   if(!name.value.trim()||!definition.value.trim()){message.textContent='名称和定义不能为空';return;}
   go.disabled=true;try{await decision(s,'merge',{confirmed:true,keep_id:keep.value,name:name.value,definition:definition.value});confirm.close();}catch(e){message.textContent=e.message;go.disabled=false;}
  });row.append(button('取消',()=>confirm.close()),go);confirm.append(message,row);confirm.onclose=()=>confirm.remove();document.body.append(confirm);confirm.showModal();
 }
 function render(){
  const previousScroll=dialog.querySelector('.aco-detail')?.scrollTop||0;dialog.replaceChildren();const r=run();
  const head=el('header','aco-head');head.append(el('h2','','整理编码'),closeButton());dialog.append(head);
  const toolbar=el('div','aco-toolbar'),picker=el('select');picker.setAttribute('aria-label','整理运行记录');
  runs.slice().reverse().forEach((item,i)=>picker.append(new Option(`整理记录 ${runs.length-i} · ${new Date(item.created_at*1000).toLocaleString('zh-CN')}`,item.id)));picker.value=r?.id||'';picker.onchange=()=>{runId=picker.value;suggestionId='';render();};
  if(!runs.length){picker.append(new Option('暂无整理记录',''));picker.disabled=true;}
  toolbar.append(picker,button(runs.length?'重新整理':'开始整理',()=>start(false)));if(r&&['failed','partial'].includes(r.status))toolbar.append(button('继续未完成检查',()=>start(true)));dialog.append(toolbar);
  const message=el('p','aco-error');message.setAttribute('role','alert');dialog.append(message);
  if(!r){dialog.append(el('p','aco-empty','尚无整理记录。点击“开始整理”，AI将对名称、定义和代表性原文进行比较。'));return;}
  const done=r.tasks.filter(t=>t.status==='completed').length,summary=el('p','aco-summary');summary.textContent=`${r.status==='running'?'正在检查':r.status==='completed'?'检查完成':'检查部分完成或失败'} · ${done}/${r.tasks.length} 批 · ${r.suggestions.length} 条建议`;dialog.append(summary);
  if(r.error)message.textContent=r.error;
  for(const task of r.tasks)if(task.status==='failed')message.textContent+=' '+(task.attempts.at(-1)?.error||'检查失败');
  if(r.collection_changed)dialog.append(el('p','aco-warning','编码集合已变化（包括已确认的合并）。未处理的相关旧建议可能失效；如需检查当前完整集合，请重新整理。'));
  const body=el('div','aco-layout'),list=el('aside','aco-suggestions'),detail=el('section','aco-detail');body.append(list,detail);dialog.append(body);
  if(!r.suggestions.length)detail.append(el('p','aco-empty',r.status==='completed'?'未发现明显问题。此结果仅基于本次送入的编码及代表性引文，不代表已证明所有编码一致。':r.status==='running'?'AI正在检查，请稍候；关闭后可重新打开查看进度。':'未获得有效建议，可继续未完成检查；已有编码未被改变。'));
  if(!r.suggestions.some(s=>s.id===suggestionId))suggestionId=r.suggestions[0]?.id||'';
  for(const s of r.suggestions){const b=button('',()=>{suggestionId=s.id;render();});b.className='aco-suggestion'+(s.id===suggestionId?' active':'');const reviewed=suggestionReviewed(s),head=el('div','aco-suggestion-head'),badge=el('span','aco-review-badge '+(reviewed?'aco-reviewed':'aco-pending-review'),reviewed?'已审核':'待审核');badge.title=s.stale?'建议已失效，请重新整理':s.status==='undone'?'合并已撤销，可重新整理后判断':reviewed?'此整理建议已由研究者处理':'此整理建议尚未完成审核';head.append(el('strong','',types[s.problem_type]),badge);b.append(head,el('span','',s.code_ids.map(id=>r.snapshot.find(c=>c.id===id)?.name||id).join(' / ')),el('small','',states[s.status]+(s.stale?' · 已失效':'')));list.append(b);}
  const s=r.suggestions.find(s=>s.id===suggestionId);
  if(s){
   detail.append(el('h3','',`${types[s.problem_type]} · AI建议：${actions[s.action]}`),reasonBlock(s.reason,r.snapshot));
   if(s.stale)detail.append(el('p','aco-warning','相关编码已修改、删除或合并：旧建议不可执行，请重新整理。'));
   const compare=el('div','aco-compare');
   for(const id of s.code_ids){const c=r.snapshot.find(c=>c.id===id),card=el('article','aco-code-card');card.append(el('small','ac-note','已保存编码 · 整理时快照'),el('h4','',c.name),el('p','',c.definition),el('p','ac-note',`${codeStates[c.status]} · ${c.references.length} 处引用 · ID ${c.id}`));
    const sample=r.sampling.find(x=>x.id===id);if(sample)card.append(el('p','ac-note',`AI送入 ${sample.sent_count}/${c.references.length} 处引用；按原文顺序等距取样。`));
    const refs=el('details','aco-all-refs');refs.open=true;refs.append(el('summary','',`原文引用（${c.references.length}）`));
    for(const ref of c.references){const quote=button(ref.quote||'引用无效',()=>{dialog.close();context.locate(c,ref);});quote.className='aco-quote';quote.disabled=ref.validation!=='valid'||s.stale;quote.title=quote.disabled?'此引用未定位或建议失效':'在访谈全文中定位';refs.append(quote);if(s.supporting_reference_ids.includes(ref.id))refs.append(el('small','ac-note','AI判断依据'));}
    const edit=button('返回编辑此编码',()=>{dialog.close();context.editCode(c.id);});edit.disabled=s.stale||['merged','undone'].includes(s.status);card.append(refs,edit);compare.append(card);
   }
   detail.append(compare);
   const controls=el('div','aco-actions'),unresolved=['pending','skipped'].includes(s.status),merge=button('合并编码',()=>mergeDialog(s)),keep=button('保留独立',()=>decision(s,'keep').catch(()=>{})),skip=button('暂时跳过',()=>decision(s,'skip').catch(()=>{}));
   merge.disabled=s.stale||!unresolved||s.code_ids.length<2;keep.disabled=skip.disabled=s.stale||!unresolved;controls.append(merge,keep,skip);detail.append(controls);
  }
  const history=el('details','aco-operations');history.open=true;history.append(el('summary','','合并记录与撤销'));
  for(const op of r.operations||[]){const row=el('div','aco-operation');row.append(el('span','',op.before_codes.map(c=>c.name).join(' + ')+' · '+(op.status==='applied'?'已合并':'已撤销')));
   if(op.status==='applied')row.append(button('查看合并后编码',()=>{dialog.close();context.editCode(op.survivor_id);}),button('撤销合并',async()=>{try{const d=await request(base()+'/'+r.id+'/operations/'+op.id+'/undo','POST');context.updated(d.coding);runs=d.organization.runs;render();}catch(e){error(e);}}));history.append(row);}
  detail.append(history);detail.scrollTop=previousScroll;
 }
 window.aiCodingOrganizer={async open(options){context=options;runId='';suggestionId='';const head=el('header','aco-head');head.append(el('h2','','整理编码'),closeButton());dialog.replaceChildren(head,el('p','','正在读取整理记录…'),el('p','aco-error'));if(!dialog.open)dialog.showModal();await load();}};
})();
