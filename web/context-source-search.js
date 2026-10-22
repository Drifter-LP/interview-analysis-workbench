/* Shared source search: exact text locally, semantic retrieval explicitly. */
(() => {
 const dialog=document.createElement('dialog');dialog.className='research-source-dialog';dialog.id='sourceSearch';
 dialog.innerHTML='<header><strong>查找原文</strong><button type="button" aria-label="关闭原文检索">×</button></header><form class="research-source-controls"><select aria-label="原文检索范围"></select><div class="research-search-modes" role="group" aria-label="查找方式"><button type="button" data-mode="literal" aria-pressed="true">文字匹配</button><button type="button" data-mode="semantic" aria-pressed="false">语义查找</button></div><input aria-label="原文检索问题" placeholder="输入要匹配的文字" maxlength="300"><button type="submit">查找</button></form><div class="research-source-status"><span role="status"></span><div><button type="button" data-previous disabled>上一处 ↑</button><button type="button" data-next disabled>下一处 ↓</button></div></div><div class="research-source-grid"><section class="research-source-results" aria-label="匹配结果"></section><article class="research-source-original"><header><strong>原文上下文</strong><span></span></header><div class="research-source-context">选择检索结果，查看原文上下文。</div></article></div>';
 document.body.append(dialog);
 const picker=dialog.querySelector('select'),input=dialog.querySelector('input'),form=dialog.querySelector('form'),button=form.querySelector('[type="submit"]'),results=dialog.querySelector('.research-source-results'),context=dialog.querySelector('.research-source-context'),contextLabel=dialog.querySelector('.research-source-original header span'),status=dialog.querySelector('[role="status"]'),previous=dialog.querySelector('[data-previous]'),next=dialog.querySelector('[data-next]');
 let materials=[],generation=0,controller=null,busy=false,mode='literal',hits=[],active=-1,rendered=0;
 const label=()=>mode==='literal'?'文字匹配':'语义查找';
 function resetButton(){busy=false;form.setAttribute('aria-busy','false');button.textContent='查找';button.disabled=!materials.length;}
 function cancelSearch(){generation++;controller?.abort();resetButton();}
 function resetResults(message){hits=[];active=-1;rendered=0;results.textContent=message;status.textContent=label()+' · 已保存的访谈稿';contextLabel.textContent='';context.textContent='选择检索结果，查看原文上下文。';previous.disabled=next.disabled=true;}
 function setMode(value){mode=value;for(const item of dialog.querySelectorAll('[data-mode]'))item.setAttribute('aria-pressed',String(item.dataset.mode===mode));input.placeholder=mode==='literal'?'输入要匹配的文字':'输入想查找的内容或主题';}
 dialog.querySelector('[aria-label="关闭原文检索"]').onclick=()=>dialog.close();dialog.onclose=cancelSearch;
 for(const toggle of dialog.querySelectorAll('[data-mode]'))toggle.onclick=()=>{if(mode===toggle.dataset.mode)return;cancelSearch();setMode(toggle.dataset.mode);resetResults('输入内容后点击查找。');input.focus();};
 window.openSourceSearch=function(options={}){
  cancelSearch();setMode('literal');
  const cross=document.querySelector('#focused')?.classList.contains('active');
  const rows=options.materials||(cross?window.researchNavigation?.searchMaterials():selected?[{id:selected,name:selectedProject?.name||selected}]:[]);
  materials=[...new Map((rows||[]).filter(x=>x.id).map(x=>[String(x.id),{...x,id:String(x.id)}])).values()];
  picker.replaceChildren();if(materials.length>1)picker.append(new Option('本次材料 · '+materials.length+' 篇','all'));for(const m of materials)picker.append(new Option(m.name||m.id,m.id));
  resetResults(materials.length?'输入内容后查找已保存的访谈原文。':'当前范围没有可检索的访谈稿。');resetButton();if(!dialog.open)dialog.showModal();input.focus();
 };
 picker.onchange=()=>{cancelSearch();resetResults('输入内容后查找当前范围的原文。');};
 input.oninput=()=>{cancelSearch();resetResults('输入内容后点击查找。');};
 function literalResults(text,query){
  // Python offsets count Unicode characters; indexOf counts UTF-16 units.
  const offsets=new Uint32Array(text.length+1);let unit=0,point=0;
  for(const char of text){offsets[unit]=point;if(char.length===2)offsets[unit+1]=point;unit+=char.length;point++;}offsets[unit]=point;
  const chars=Array.from(text),matches=[];let position=0,index;
  while((index=text.indexOf(query,position))!==-1){const start=offsets[index],end=offsets[index+query.length],snippetStart=Math.max(0,start-60),snippetEnd=Math.min(chars.length,end+100);matches.push({start,end,text:chars.slice(snippetStart,snippetEnd).join(''),snippetStart});position=index+query.length;}
  return{source_text:text,results:matches};
 }
 function selectHit(index){
  if(index<0||index>=hits.length)return;active=index;while(rendered<=index)renderMore();
  results.querySelectorAll('[data-hit]').forEach(card=>{const selected=Number(card.dataset.hit)===index;card.classList.toggle('selected',selected);card.querySelector('button').setAttribute('aria-pressed',String(selected));});
  const hit=hits[index],chars=hit.data.chars||(hit.data.chars=Array.from(hit.data.source_text||'')),mark=document.createElement('mark');mark.textContent=chars.slice(hit.item.start,hit.item.end).join('');
  context.replaceChildren(document.createTextNode(chars.slice(0,hit.item.start).join('')),mark,document.createTextNode(chars.slice(hit.item.end).join('')));
  contextLabel.textContent=(hit.material.name||hit.material.id)+' · '+(index+1)+' / '+hits.length;previous.disabled=index===0;next.disabled=index===hits.length-1;
  mark.scrollIntoView({block:'center'});results.querySelector('[data-hit="'+index+'"]')?.scrollIntoView({block:'nearest'});
 }
 function renderMore(){
  results.querySelector('[data-more]')?.remove();const limit=Math.min(hits.length,rendered+100);
  for(;rendered<limit;rendered++){
   const index=rendered,hit=hits[index],card=document.createElement('article'),title=document.createElement('strong'),quote=document.createElement('blockquote'),jump=document.createElement('button');card.dataset.hit=String(index);
   title.textContent=(hit.material.name||hit.material.id)+' · '+label();
   if(mode==='literal'){const chars=Array.from(hit.item.text),start=hit.item.start-hit.item.snippetStart,end=hit.item.end-hit.item.snippetStart,mark=document.createElement('mark');mark.textContent=chars.slice(start,end).join('');quote.append(document.createTextNode(chars.slice(0,start).join('')),mark,document.createTextNode(chars.slice(end).join('')));}else quote.textContent=hit.item.text;
   jump.type='button';jump.textContent='查看原文上下文 →';jump.setAttribute('aria-pressed','false');jump.onclick=()=>selectHit(index);card.append(title,quote,jump);results.append(card);
  }
  if(rendered<hits.length){const more=document.createElement('button');more.type='button';more.dataset.more='';more.textContent='显示更多（'+rendered+' / '+hits.length+'）';more.onclick=renderMore;results.append(more);}
 }
 previous.onclick=()=>selectHit(active-1);next.onclick=()=>selectHit(active+1);
 async function fetchSearch(url,options,signal){
  const local=new AbortController();let timeout=false;
  const abort=()=>local.abort();if(signal.aborted)abort();else signal.addEventListener('abort',abort,{once:true});
  const timer=setTimeout(()=>{timeout=true;local.abort();},105000);
  try{
   const response=await fetch(url,{...options,signal:local.signal});
   let data;try{data=await response.json();}catch(error){throw Error('本地检索服务返回格式错误，请检查服务是否已启动。');}
   if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:'查找失败（'+response.status+'），请稍后重试。');
   return data;
  }catch(error){if(timeout)throw Error('本批检索超过等待时间，请稍后重试；未返回不完整结果。');throw error;}
  finally{clearTimeout(timer);signal.removeEventListener('abort',abort);}
 }
 async function semanticSearch(material,query,signal,onProgress){
  let source=null,index=0,total=1,finished=false;const matches=[];
  while(index<total){
   const body={query,batch_index:index};if(source)body.source_hash=source.source_hash;
   const data=await fetchSearch('/api/projects/'+encodeURIComponent(material.id)+'/source-search',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)},signal);
   if(typeof data.source_text!=='string'||!Array.isArray(data.results))throw Error('语义检索结果格式不完整，请重试。');
   if(source&&(data.source_hash!==source.source_hash||data.source_text!==source.source_text))throw Error('查找期间访谈稿已更新，请重新查找。');
   source=source||data;total=data.batch_count??1;
   if(!Number.isInteger(total)||total<0||total>50000)throw Error('检索批次信息无效，请重试。');
   if(data.batch_index!==undefined&&data.batch_index!==null&&data.batch_index!==index)throw Error('检索批次不一致，请重新查找。');
   matches.push(...data.results);index++;onProgress(index,total);
   if(data.complete||total===0||data.batch_count===undefined){finished=true;break;}
  }
  if(!source||!finished)throw Error('语义检索未完成全部批次；未返回不完整结果。');
  return{...source,results:matches};
 }
 form.onsubmit=async event=>{
  event.preventDefault();if(busy){cancelSearch();status.textContent='已取消本次查找。';return;}
  const query=input.value.trim();if(!query){resetResults('请先输入想查找的文字或主题。');return input.focus();}
  const targets=picker.value==='all'?materials:materials.filter(x=>x.id===picker.value);if(!targets.length){resetResults('请选择一份可检索的访谈稿。');return;}
  cancelSearch();controller=new AbortController();const activeController=controller,signal=controller.signal,token=++generation,searchMode=mode;
  resetResults('正在查找…');busy=true;form.setAttribute('aria-busy','true');button.textContent='取消查找';button.disabled=false;status.textContent=searchMode==='literal'?'正在匹配 '+targets.length+' 篇已保存稿…':'正在语义查找 '+targets.length+' 篇访谈，可能需要一些时间…';
  try{
   const replies=new Array(targets.length);let cursor=0,completed=0;
   const progress=(material,done,total)=>{if(token===generation)status.textContent='正在语义查找 · 已处理 '+completed+' / '+targets.length+' 篇 · '+(material.name||material.id)+' '+done+' / '+total+' 批';};
   await Promise.all(Array.from({length:Math.min(searchMode==='literal'?4:2,targets.length)},async()=>{while(cursor<targets.length&&!signal.aborted){const index=cursor++,material=targets[index];try{
    const data=searchMode==='literal'?await fetchSearch('/api/projects/'+encodeURIComponent(material.id)+'/transcript',{},signal):await semanticSearch(material,query,signal,(done,total)=>progress(material,done,total));
    if(searchMode==='literal'&&typeof data.text!=='string')throw Error('未获取到已保存的访谈稿。');
    replies[index]={material,data:searchMode==='literal'?literalResults(data.text,query):data};
   }catch(error){replies[index]={material,error};}finally{completed++;if(token===generation&&searchMode==='semantic')status.textContent='正在语义查找 · 已处理 '+completed+' / '+targets.length+' 篇';}}}));
   if(token!==generation)return;results.replaceChildren();const failures=[];
   for(let i=0;i<targets.length;i++){const reply=replies[i];if(!reply||reply.error){failures.push((targets[i].name||targets[i].id)+'：'+(reply?.error?.message||'查找未完成。'));continue;}for(const item of reply.data.results||[])hits.push({material:reply.material,data:reply.data,item});}
   status.textContent=failures.length===targets.length?(searchMode==='literal'?'文字查找未完成':'语义查找未完成')+' · '+failures.length+' 篇检索失败':(searchMode==='literal'?'文字命中':'语义相关')+' · '+hits.length+(searchMode==='literal'?' 处匹配':' 段原文')+' · '+(targets.length-failures.length)+' / '+targets.length+' 篇已完成'+(failures.length?' · '+failures.length+' 篇失败':'');
   if(hits.length){renderMore();selectHit(0);}else{const empty=document.createElement('p');empty.textContent=failures.length?'检索未完成，请查看下方原因。':searchMode==='literal'?'没有找到这段连续文字，可切换语义查找。':'没有找到相关原文，请调整问题后重试。';results.append(empty);}
   for(const message of failures){const error=document.createElement('p');error.textContent=message;error.setAttribute('role','alert');results.append(error);}
  }catch(error){if(token===generation){status.textContent='查找未完成。';results.textContent=error.message;}}
  finally{if(token===generation)resetButton();}
 };
})();
