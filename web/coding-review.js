// Coding review presentation; source text and existing workspace data remain authoritative.
(()=>{
 const panel=$('#coding'),grid=$('#codingGrid'),source=$('#codingText'),side=grid.querySelector('.coding-side');
 const style=document.createElement('link');style.rel='stylesheet';style.href='/assets/coding-review.css?v=20261009-1';document.head.append(style);
 const rawSet=setCodingText;let raw=source.textContent||'',mode='pending',hit=null,busy=false;
 setCodingText=function(text){raw=String(text||'');hit=null;rawSet(text);};
 codingTextValue=()=>raw;
 $('#toggleCodingTextBtn').hidden=true;grid.classList.remove('text-collapsed');
 const left=document.createElement('section');left.className='review-source';source.before(left);left.append(source);
 const top=document.createElement('header');top.innerHTML='<h3>访谈原文</h3><input id="reviewSearch" placeholder="搜索原文" aria-label="搜索原文"><span id="reviewSourceCount"></span>';left.prepend(top);
 const foot=document.createElement('footer');foot.textContent='选中一段原文，可创建或关联编码。';left.append(foot);
 side.innerHTML='<header class="review-tabs"><button data-mode="pending">AI建议 <b></b></button><button data-mode="accepted">已接受 <b></b></button><button data-mode="library">编码库 <b></b></button></header><div class="review-hint">逐条核对原文后接受，可修改名称与归属。</div><div id="suggestionList"></div><div id="codeList" hidden></div><footer><span>编码与原文绑定；未确认建议不进入编码表。</span><button id="reviewManual" class="soft">＋ 手动添加编码</button></footer>';
 const toolbar=document.createElement('div');toolbar.className='review-toolbar';toolbar.innerHTML='<span id="reviewProject"></span><button id="reviewSettings" class="soft">编码设置</button><span class="review-note">AI建议需人工确认</span>';grid.before(toolbar);
 const dialog=document.createElement('dialog');dialog.className='review-dialog';dialog.innerHTML='<form method="dialog"><h3>编码设置</h3><label>本篇编码关注问题<textarea id="reviewQuestion" rows="3"></textarea></label><p>用于现有 AI 编码请求，不改变其他页面的研究问题。</p><div><button value="cancel" class="soft">取消</button><button value="save" class="primary">保存设置</button></div></form>';document.body.append(dialog);
 const edit=document.createElement('dialog');edit.className='review-dialog';edit.innerHTML='<form method="dialog"><h3>修改编码</h3><label>名称<input name="name" required maxlength="100"></label><label>归属<input name="theme" placeholder="可选：已有范畴或主题"></label><label>说明<textarea name="definition" rows="3"></textarea></label><div><button value="cancel" class="soft" formnovalidate>取消</button><button value="save" class="primary">保存</button></div></form>';document.body.append(edit);let editTarget=null;
 function ensure(){if(!analysisData)return false;analysisData.codes??=[];analysisData.excerpts??=[];analysisData.ai_suggestions??=[];return true;}
 function position(item){const quote=String(item.quote||'');if(!quote)return -1;const start=Number(item.start);return Number.isInteger(start)&&start>=0&&raw.slice(start,start+quote.length)===quote?start:raw.indexOf(quote);}
 function paragraph(start){return start<0?'原文未匹配':'第 '+(raw.slice(0,start).split(/\n\s*\n/).length)+' 段';}
 function paint(){
  // Build only source text/marks here: textContent stays byte-for-byte identical to raw.
  const ranges=[];for(const e of analysisData?.excerpts||[]){const start=position(e);if(start>=0)ranges.push({start,end:start+e.quote.length,type:'coded'});}
  if(hit)ranges.push({...hit,type:'active'});
  const stops=[...new Set([0,raw.length,...ranges.flatMap(r=>[r.start,r.end])])].sort((a,b)=>a-b);let html='';
  for(let i=0;i<stops.length-1;i++){const a=stops[i],b=stops[i+1],active=ranges.some(r=>r.type==='active'&&r.start<=a&&r.end>=b),coded=ranges.some(r=>r.type==='coded'&&r.start<=a&&r.end>=b);const text=escapeHtml(raw.slice(a,b));html+=active||coded?`<mark class="${active?'review-hit':'review-coded'}">${text}</mark>`:text;}
  source.innerHTML=html||'<span class="review-empty">请选择访谈稿</span>';
 }
 function locate(item){hideCodingPopover();const start=position(item);if(start<0){toast('未在当前原文中匹配到证据，请先核对');return;}hit={start,end:start+item.quote.length};paint();source.querySelector('.review-hit')?.scrollIntoView({behavior:'smooth',block:'center'});}
 function counts(){const pending=(analysisData?.ai_suggestions||[]).filter(s=>!['已接受','已忽略'].includes(s.status));const accepted=analysisData?.excerpts||[];return {pending,accepted};}
 function refresh(){renderCodes();renderSuggestions();paint();}
 renderCodes=function(){
  const codes=analysisData?.codes||[],box=$('#codeList');box.innerHTML=codes.length?codes.map(c=>`<article class="review-card"><h3>${escapeHtml(c.name)}</h3><small>${escapeHtml(c.theme||'未设置归属')} · ${(analysisData.excerpts||[]).filter(e=>e.code_id===c.id).length} 段原文</small><p>${escapeHtml(c.definition||'暂无说明')}</p><button class="soft" data-edit-code="${escapeHtml(c.id)}">修改</button></article>`).join(''):'<div class="empty">尚无已确认编码</div>';
  box.querySelectorAll('[data-edit-code]').forEach(b=>b.onclick=()=>openEdit('code',b.dataset.editCode));
  const filter=$('#evidenceFilter'),old=filter.value;filter.innerHTML='<option value="">全部编码</option>'+codes.map(c=>`<option value="${escapeHtml(c.id)}">${escapeHtml(c.name)}</option>`).join('');filter.value=old;
  $('#codingPopoverSelect').innerHTML='<option value="">选择已有编码</option>'+codes.map(c=>`<option value="${escapeHtml(c.id)}">${escapeHtml(c.name)}</option>`).join('');
 };
 renderSuggestions=function(){
  const {pending,accepted}=counts(),codes=analysisData?.codes||[];
  side.querySelectorAll('[data-mode]').forEach(b=>{b.classList.toggle('active',b.dataset.mode===mode);b.setAttribute('aria-pressed',String(b.dataset.mode===mode));b.querySelector('b').textContent=({pending:pending.length,accepted:accepted.length,library:codes.length})[b.dataset.mode];});
  $('#reviewSourceCount').textContent='已确认 '+accepted.length+' 段编码';$('#reviewProject').textContent='项目：'+(selectedResearchProject?.name||'未选择研究项目');$('#reviewManual').disabled=!selected;$('#reviewSettings').disabled=!selected;
  const box=$('#suggestionList');box.hidden=mode==='library';$('#codeList').hidden=mode!=='library';
  const rows=mode==='accepted'?accepted:pending,map=Object.fromEntries(codes.map(c=>[c.id,c]));
  box.innerHTML=rows.length?rows.map(s=>{const code=map[s.code_id],start=position(s),isPending=mode==='pending';return `<article class="review-card"><div class="review-meta"><span>${isPending?'待确认':'已确认'}</span><small>${paragraph(start)}</small></div><h3>${escapeHtml(isPending?s.code:code?.name||'未命名编码')}</h3><small>原文片段</small><blockquote>${escapeHtml(s.quote)}</blockquote>${isPending?`<label>建议归属<input data-theme="${escapeHtml(s.id)}" value="${escapeHtml(s.theme||'')}" placeholder="可选：范畴 / 主题"></label><small>AI建议理由</small><p>${escapeHtml(s.reason||'未提供理由')}</p>`:''}<div class="review-card-actions">${isPending?`<button class="primary" data-accept="${escapeHtml(s.id)}" ${start<0?'disabled':''}>✓ 接受</button><button class="soft" data-edit="${escapeHtml(s.id)}">修改</button><button class="soft" data-ignore="${escapeHtml(s.id)}">× 忽略</button>`:''}<button class="ghost" data-locate="${escapeHtml(s.id)}" ${start<0?'disabled':''}>定位原文</button></div>${start<0?'<small class="review-warning">证据未匹配到当前原文，不能接受。</small>':''}</article>`}).join(''):`<div class="empty">${selected?(mode==='accepted'?'尚无已确认编码':'暂无待审核建议，可点击顶部 AI编码生成。'):'请先选择访谈稿'}</div>`;
  box.querySelectorAll('[data-locate]').forEach(b=>b.onclick=()=>locate(rows.find(s=>s.id===b.dataset.locate)));
  box.querySelectorAll('[data-edit]').forEach(b=>b.onclick=()=>openEdit('suggestion',b.dataset.edit));
  box.querySelectorAll('[data-accept]').forEach(b=>b.onclick=()=>mutate(async()=>{const s=analysisData.ai_suggestions.find(s=>s.id===b.dataset.accept);s.theme=box.querySelector(`[data-theme="${CSS.escape(s.id)}"]`).value.trim();await acceptSuggestion(s.id);}));
  box.querySelectorAll('[data-ignore]').forEach(b=>b.onclick=()=>mutate(async()=>{analysisData.ai_suggestions.find(s=>s.id===b.dataset.ignore).status='已忽略';await saveAnalysis(false);refresh();}));
  paint();
 };
 async function mutate(action){if(busy||!ensure())return;busy=true;const snapshot=structuredClone(analysisData),id=selected;try{await action();}catch(e){if(selected===id)analysisData=snapshot;toast('保存失败：'+e.message);refresh();}finally{busy=false;}}
acceptSuggestion=async function(id){const s=analysisData.ai_suggestions.find(x=>x.id===id);if(!s||s.status==='已接受')return;const start=position(s);if(start<0)throw new Error('证据未匹配原文');const code=addCode(s.code,s.definition||s.reason||'','AI');if(s.theme)code.theme=s.theme;analysisData.excerpts.push({id:uid(),code_id:code.id,quote:s.quote,context:raw.slice(Math.max(0,start-100),Math.min(raw.length,start+s.quote.length+100)),speaker:s.speaker||'',source:'AI建议',status:'人工已确认',unit_id:s.unit_id,unit_kind:s.unit_kind,transcript_hash:s.transcript_hash,prompt_version:s.prompt_version,project_id:s.project_id,source_start:s.source_start,source_end:s.source_end,start,end:start+s.quote.length});s.status='已接受';await saveAnalysis(false);refresh();toast('编码已接受并保存');};
 function openEdit(kind,id){editTarget={kind,id,project:selected};const c=kind==='code'?analysisData.codes.find(c=>c.id===id):analysisData.ai_suggestions.find(c=>c.id===id);edit.querySelector('[name=name]').value=c.name||c.code||'';edit.querySelector('[name=theme]').value=c.theme||'';edit.querySelector('[name=definition]').value=c.definition||c.reason||'';edit.showModal();}
edit.addEventListener('close',()=>{if(edit.returnValue!=='save'||editTarget?.project!==selected)return;const target=editTarget;mutate(async()=>{const c=target.kind==='code'?analysisData.codes.find(c=>c.id===target.id):analysisData.ai_suggestions.find(c=>c.id===target.id);const name=edit.querySelector('[name=name]').value.trim();if(!name)return;const duplicate=target.kind==='code'&&analysisData.codes.some(x=>x.id!==c.id&&x.name===name);if(duplicate)throw new Error('同名编码已存在，请使用已有编码');c[target.kind==='code'?'name':'code']=name;c.theme=edit.querySelector('[name=theme]').value.trim();c[target.kind==='code'?'definition':'reason']=edit.querySelector('[name=definition]').value.trim();if(target.kind==='suggestion')c.definition=c.reason;await saveAnalysis(false);refresh();});});
 side.querySelectorAll('[data-mode]').forEach(b=>b.onclick=()=>{mode=b.dataset.mode;refresh();});
 $('#reviewSearch').oninput=e=>{const term=e.target.value.trim();const start=term?raw.indexOf(term):-1;hit=start>=0?{start,end:start+term.length}:null;paint();if(hit)source.querySelector('.review-hit')?.scrollIntoView({block:'center'});};
 $('#reviewManual').onclick=()=>{source.focus();toast('请先在左侧选中一段原文，再创建或关联编码');};
 const originalApply=applyPopoverCode;$('#codingPopoverApply').onclick=()=>mutate(async()=>{await originalApply();paint();});
 // Do not dismiss the selection when moving the pointer into the coding controls.
 $('#codingPopover').onmouseleave=null;
 $('#reviewSettings').onclick=()=>{dialog.querySelector('textarea').value=analysisData?.coding_question||selectedResearchProject?.research_question||'';dialog.showModal();};
 dialog.addEventListener('close',()=>{if(dialog.returnValue==='save')mutate(async()=>{analysisData.coding_question=dialog.querySelector('textarea').value.trim();await saveAnalysis(false);toast('编码设置已保存');});});
 // Same endpoint, with an explicit per-interview question; no additional model calls.
$('#aiCodeBtn').onclick=async()=>{if(!selected||busy)return;const project=selected,question=analysisData.coding_question||selectedResearchProject?.research_question||analysisData.metadata?.research_question||'',button=$('#aiCodeBtn');setAiLoading(button,true);$('#codingStatus').textContent='正在生成…';try{await saveAnalysis(false);if(selected!==project)return;const result=await api(`/api/projects/${project}/coding-suggestions`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({research_question:question})});if(selected!==project){toast('访谈稿已切换，本次建议未写入其他访谈');return;}const known=new Set(analysisData.ai_suggestions.map(s=>JSON.stringify([s.quote,s.code,s.unit_id||'',s.start??null])));for(const s of result.suggestions||[]){const key=JSON.stringify([s.quote,s.code,s.unit_id||'',s.start??null]);if(!known.has(key)){s.id??=uid();analysisData.ai_suggestions.push(s);known.add(key);}}await saveAnalysis(false);mode='pending';refresh();$('#codingStatus').textContent=result.rejected_bindings?`已生成建议 · ${result.rejected_bindings} 条引文未通过匹配`:'已生成建议';}catch(e){toast(e.message);$('#codingStatus').textContent='生成失败';}finally{setAiLoading(button,false);}};
 // Keep source offsets correct even when a selection crosses existing highlight marks.
 showCodingPopover=function(event){
  clearCodingMark();const selection=window.getSelection();if(!selection||selection.rangeCount===0||selection.isCollapsed)return hideCodingPopover();
  const range=selection.getRangeAt(0);if(!source.contains(range.commonAncestorContainer))return hideCodingPopover();
  const before=range.cloneRange();before.selectNodeContents(source);before.setEnd(range.startContainer,range.startOffset);
  const quote=range.toString();if(!quote.trim())return hideCodingPopover();const start=before.toString().length;
  codingSelection={start,end:start+quote.length,quote};
  const rect=range.getBoundingClientRect(),pop=$('#codingPopover');pop.style.left=Math.max(12,Math.min(rect.left,window.innerWidth-470))+'px';pop.style.top=Math.max(12,Math.min(rect.bottom+8,window.innerHeight-100))+'px';pop.hidden=false;
  $('#codingPopoverSelect').value=selectedCodeId||'';$('#codingPopoverInput').value='';
 };
 source.onmouseup=showCodingPopover;source.onkeyup=e=>{if(e.shiftKey)showCodingPopover(e);};
 const baseSave=saveAnalysis;
 saveAnalysis=async function(show=true){if(!selected)return baseSave(show);const id=selected;$('#codingStatus').textContent='保存中…';try{const result=await baseSave(show);if(selected===id)$('#codingStatus').textContent='已保存';return result;}catch(error){if(selected===id)$('#codingStatus').textContent='保存失败';throw error;}};
 $('#saveAnalysisBtn').onclick=()=>mutate(()=>saveAnalysis());
 // Generate export from real stored coding data, not the preview contents.
 const exportButton=document.createElement('button');exportButton.className='soft';exportButton.textContent='导出编码';toolbar.append(exportButton);
 exportButton.onclick=()=>{if(!selected||!analysisData)return;const payload={interview_id:selected,interview_name:selectedProject?.name||'',codes:analysisData.codes,excerpts:analysisData.excerpts,ai_suggestions:analysisData.ai_suggestions};const blob=new Blob([JSON.stringify(payload,null,2)],{type:'application/json;charset=utf-8'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=(selectedProject?.name||'访谈')+'-编码.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
 const priorRender=renderSuggestions;renderSuggestions=function(){priorRender();exportButton.disabled=!selected;};
 refresh();
})();
