/* Independent review workspace. Never replaces a finding automatically. */
(()=>{
 const panel=document.querySelector('#comparisonPanel'),cache=new Map(),pending=new Set(),loaded=new Set(),loadErrors=new Map();let selected=0,filter='all',busy=false,token=0;
 const names={counter:'反例',condition:'限定条件',uncertain:'待判断'};
 function entries(){return(currentThemeAnalysis?.dimensions||[]).flatMap((d,di)=>(d.findings||[]).map((f,fi)=>({f,di,fi})));}
 function key(a,e){return `${a.id}:${e.di}:${e.fi}`;}
 function current(){const a=currentThemeAnalysis,e=entries()[selected];return {a,e,k:e&&key(a,e)};}
 function url(a){return `/api/research-projects/${encodeURIComponent(selectedResearchProject.id)}/theme-analyses/${a.id}/finding-review`;}
 function context(source){
  return openThemeEvidence(source.project_id,Number(source.number),source);
 }
 function loadSaved(a,e,k){
  if(cache.has(k)||pending.has(k)||loaded.has(k)||loadErrors.has(k)||!(a.finding_review_index||[]).some(r=>r.dimension_index===e.di&&r.finding_index===e.fi))return;
  pending.add(k);
  api(url(a)+`/saved?dimension_index=${e.di}&finding_index=${e.fi}`).then(result=>{
   loaded.add(k);if(result.review)cache.set(k,result.review);
  }).catch(error=>loadErrors.set(k,error.message)).finally(()=>{
   pending.delete(k);if(current().k===k&&current().a===a)render(true);
  });
 }
 function render(preserveList=false){
  const {a,e,k}=current(),all=entries();if(!e){panel.textContent='请先打开已保存的主题研究结果';return;}
  const review=cache.get(k)||[...(a.finding_reviews||[])].reverse().find(r=>r.dimension_index===e.di&&r.finding_index===e.fi);
  if(review&&!cache.has(k))cache.set(k,review);
  // Legacy support judgments remain readable without requesting new support output.
  const displayNames=(review?.items||[]).some(i=>i.category==='support')?{support:'支持材料（历史）',...names}:names;
  loadSaved(a,e,k);
  const loading=pending.has(k),loadError=loadErrors.get(k);
  const items=(review?.items||[]).map((item,index)=>({item,index})).filter(({item})=>filter==='all'||item.category===filter);
  const emptyMessage=busy?'正在分批核查；失败批次会自动重试，成功批次保留。':loading?'正在读取这条发现已保存的核查记录…':loadError?'已保存核查记录读取失败，档案未删除。':!review?'选择发现后点击“查找相关材料”开始核查。':review.status==='incomplete'?'本次核查尚未完成；点击“继续核查”恢复未完成批次。':filter!=='all'?`本次核查暂无${displayNames[filter]}，可切换其他分类查看。`:'本次核查未找到相关材料；不代表整篇访谈未讨论此发现。';
  if(!preserveList||!panel.querySelector('.fr-list')){
  panel.innerHTML=`<div class="fr-toolbar"><strong>待核查发现</strong><select class="fr-picker" aria-label="待核查发现" ${busy?'disabled':''}>${all.map((row,i)=>`<option value="${i}" ${i===selected?'selected':''}>${escapeHtml(row.f.title)}</option>`).join('')}</select><button class="soft fr-run" ${busy?'disabled':''}>${busy?'正在核查…':review?'重新核查':'查找相关材料'}</button><span class="fr-inline-note"><button type="button" class="fr-info" aria-label="核查范围说明" title="${escapeHtml(review?.notice||'仅核查当前主题已保存的表述，未检索全部原文。AI分类与修订均需人工判断。')}">i</button>AI建议，需人工确认</span><button class="soft fr-save" ${!review||busy?'disabled':''}>保存核查</button><button class="soft fr-fresh" hidden>重新开始</button><span role="status" class="fr-status"></span></div><div class="fr-grid"><nav class="fr-list" aria-label="选择待核查发现">${all.map((row,i)=>`<button data-fr-select="${i}" class="${i===selected?'active':''}" ${busy?'disabled':''}>${escapeHtml(row.f.title)}</button>`).join('')}</nav><section class="fr-evidence"></section></div>`;
  }
  panel.querySelector('.fr-evidence').innerHTML=`<div class="fr-filters">${[['all','全部'],...Object.entries(displayNames)].map(([id,name])=>`<button data-fr-filter="${id}" class="${filter===id?'active':''}">${name}</button>`).join('')}</div><div class="fr-items">${items.map(({item,index})=>`<article><header><strong>${escapeHtml(item.statement.sources[0]?.material_name||item.statement.project_id)}</strong><select aria-label="证据${index+1}分类" data-fr-category="${index}">${Object.entries(displayNames).map(([v,n])=>`<option value="${v}" ${item.category===v?'selected':''}>${n}</option>`).join('')}</select></header><p>${escapeHtml(item.statement.summary)}</p><blockquote>${escapeHtml(item.statement.sources.map(s=>s.quote).join('\n'))}</blockquote><small>归类依据：${escapeHtml(item.reason)}</small><footer>${item.statement.sources.map((s,j)=>`<button data-fr-source="${index}:${j}">原文 ${s.number} ↗</button>`).join('')}</footer></article>`).join('')||`<p class="fr-empty">${escapeHtml(emptyMessage)}</p>`}</div>`;
  const picker=panel.querySelector('.fr-picker');picker.value=String(selected);picker.disabled=busy;
  all.forEach((row,i)=>{if(picker.options[i])picker.options[i].textContent=row.f.title;});
  panel.querySelector('.fr-run').textContent=busy?'正在核查…':loadError?'重新读取记录':review?.status==='incomplete'?'继续核查':review?'重新核查':'查找相关材料';
  panel.querySelector('.fr-run').disabled=busy||loading;panel.querySelector('.fr-save').disabled=!review||busy||loading;
  const fresh=panel.querySelector('.fr-fresh');if(fresh){fresh.hidden=review?.status!=='incomplete';fresh.disabled=busy||loading;fresh.onclick=()=>panel.querySelector('.fr-run').onclick(true);}
  panel.querySelector('.fr-info').title=review?.notice||'仅核查当前主题已保存的表述，未检索全部原文。AI分类与修订均需人工判断。';
  panel.querySelector('.fr-status').textContent=loading?'正在读取已保存核查…':loadError?'读取失败，可点击重新读取记录。':review?.status==='incomplete'?`未完成：已核查 ${review.completed_statement_count}/${review.input_statement_count} 条，已完成批次保留。`:'';
  panel.querySelectorAll('[data-fr-select]').forEach(b=>{b.classList.toggle('active',Number(b.dataset.frSelect)===selected);b.disabled=busy;const title=all[Number(b.dataset.frSelect)].f.title;if(!b.isContentEditable&&b.textContent!==title)b.textContent=title;});
  panel.querySelectorAll('[data-fr-select]').forEach(b=>b.onclick=()=>{if(b.isContentEditable||Number(b.dataset.frSelect)===selected)return;token++;selected=Number(b.dataset.frSelect);filter='all';render(true);});
  panel.querySelector('.fr-picker').onchange=event=>{token++;selected=Number(event.target.value);filter='all';render(true);};
  panel.querySelectorAll('[data-fr-filter]').forEach(b=>b.onclick=()=>{filter=b.dataset.frFilter;render(true);});
  panel.querySelectorAll('[data-fr-select]').forEach(b=>{
   b.title='双击编辑；Enter保存，Esc取消';
   b.ondblclick=()=>{
    const index=Number(b.dataset.frSelect),row=all[index],before=row.f.title;
    b.contentEditable='true';b.setAttribute('role','textbox');b.setAttribute('aria-label','编辑发现标题');b.focus();
    const range=document.createRange();range.selectNodeContents(b);const selection=window.getSelection();selection.removeAllRanges();selection.addRange(range);
    let finished=false;
    const finish=async(cancel=false)=>{if(finished)return;finished=true;const title=b.textContent.trim();b.contentEditable='false';b.removeAttribute('role');b.removeAttribute('aria-label');b.onblur=null;b.onkeydown=null;
     if(cancel||title===before){render(true);return;}
     if(!title){toast('发现文字不能为空');render(true);return;}
     try{const response=await api(`/api/research-projects/${encodeURIComponent(selectedResearchProject.id)}/theme-analyses/${a.id}/finding-title`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({dimension_index:row.di,finding_index:row.fi,title,previous_title:before})});row.f.title=response.title;const stored=selectedResearchProject.theme_analyses?.find(r=>r.id===a.id);if(stored)stored.dimensions[row.di].findings[row.fi].title=response.title;toast('发现已保存；原文证据保持不变');}catch(error){toast('保存失败：'+error.message);}render(true);
    };
    b.onblur=()=>finish();b.onkeydown=event=>{if(event.isComposing)return;if(event.key==='Escape'){event.preventDefault();finish(true);}if(event.key==='Enter'){event.preventDefault();finish();}};
   };
  });
  panel.querySelectorAll('[data-fr-category]').forEach(s=>s.onchange=()=>{review.items[Number(s.dataset.frCategory)].category=s.value;review.items[Number(s.dataset.frCategory)].confirmed=false;});
  panel.querySelectorAll('[data-fr-source]').forEach(b=>b.onclick=()=>{const [i,j]=b.dataset.frSource.split(':').map(Number);context(review.items[i].statement.sources[j]);});
  panel.querySelector('.fr-run').onclick=async(forceNew=false)=>{if(loadError){loadErrors.delete(k);loaded.delete(k);render(true);return;}if(busy||loading)return;if(!a.id){toast('请先保存主题研究');return;}busy=true;render(true);try{const result=await api(url(a),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({dimension_index:e.di,finding_index:e.fi,resume_call_id:forceNew!==true&&review?.status==='incomplete'?review.call_id:null})});cache.set(k,result.review);}catch(error){toast('核查未完成：'+error.message);}finally{busy=false;if(current().k===k)render(true);}};
  panel.querySelector('.fr-save').onclick=async()=>{const button=panel.querySelector('.fr-save');button.disabled=true;try{const result=await api(url(a)+'/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({dimension_index:e.di,finding_index:e.fi,review})});cache.set(k,result.review);a.finding_review_index=a.finding_review_index||[];if(result.index)a.finding_review_index.push(result.index);panel.querySelector('.fr-status').textContent=review.status==='incomplete'?'未完成核查记录已保存，可稍后继续':'核查记录已保存，原发现未改动';}catch(error){toast(error.message);}finally{button.disabled=false;}};
 }
 let openedAnalysis=null;
 window.findingReview={open:()=>{if(openedAnalysis!==currentThemeAnalysis){selected=0;filter='all';openedAnalysis=currentThemeAnalysis;}render();}};
 const style=document.createElement('link');style.rel='stylesheet';style.href='/assets/finding-review.css?v=20261015-fill-height-7';document.head.append(style);
})();
