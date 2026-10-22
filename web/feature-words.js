/* Feature selection UI. Stopword edits stay local until explicitly applied. */
window.renderFeatureWords = function({root,heading,draft,apply,recommend,showSource,notify,setPending=()=>{}}) {
 const el=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n;};
 const button=(text,cls='')=>{const n=el('button',cls,text);n.type='button';return n;};
 const page=el('div','fw-page');root.append(page);
 const settings=el('div','fw-settings'),scope=el('label','','统计范围');
 const mode=el('select');mode.setAttribute('aria-label','统计文本范围');mode.title='仅受访者回答：只统计明确标注的受访者回答；整块原文包含提问。';mode.append(new Option('仅受访者回答','answers'),new Option('整块原文（包含提问）','all'));mode.value=draft.token_mode||'answers';scope.append(mode);
 const initial=new Set(draft.stopwords||[]);let stops=new Set(initial),saving=false,focusWord='';
 const stopButton=button(`停用词 · ${initial.size} 个`,'fw-stop-trigger');stopButton.setAttribute('aria-expanded','false');
 const rerun=button('重新分词');settings.append(scope,stopButton,rerun);if(heading){heading.classList.add('fw-heading');heading.append(settings);}else page.append(settings);
 const grid=el('div','fw-grid'),main=el('section','fw-candidates'),side=el('aside','fw-selected');grid.append(main,side);page.append(grid);
 const toolbar=el('div','fw-toolbar'),title=el('h3','',`候选词 · ${(draft.candidates||[]).length}`),search=el('input'),sort=el('select'),clear=button('清空选择');
 search.type='search';search.placeholder='搜索候选词';search.setAttribute('aria-label','搜索候选词');sort.setAttribute('aria-label','候选词排序');sort.append(new Option('按词频排序','frequency'),new Option('按名称排序','name'));const ai=button('✧ AI推荐','fw-ai'),toolbarActions=el('div','fw-toolbar-actions');toolbarActions.append(search,sort,ai,clear);toolbar.append(title,toolbarActions);main.append(toolbar);
 const recommendationBox=el('section','fw-recommendation');recommendationBox.hidden=true;main.append(recommendationBox);
 const objective=el('input');objective.placeholder='研究关注点（可选，例如：医保政策如何影响诊疗）';objective.maxLength=1000;objective.setAttribute('aria-label','AI推荐研究关注点');
 const run=button('开始推荐','primary'),dismiss=button('收起'),actions=el('div','fw-recommend-actions'),recommendations=el('div','fw-recommend-results');run.title='使用 DeepSeek Flash；仅发送项目名称、候选词及块频和填写的关注点，不发送访谈原文或录音。';actions.append(run,dismiss);recommendationBox.append(objective,actions,recommendations);
 let recommending=false;
 ai.onclick=()=>{recommendationBox.hidden=!recommendationBox.hidden;};dismiss.onclick=()=>{recommendationBox.hidden=true;};
 run.onclick=async()=>{
  if(recommending||saving)return;if(changed()||mode.value!==(draft.token_mode||'answers')){notify('请先应用统计范围或保存停用词，再推荐');return;}
  recommending=true;run.disabled=true;run.textContent='AI推荐中…';recommendations.replaceChildren();rerun.disabled=true;stopButton.disabled=true;mode.disabled=true;
  try{
   const data=await recommend({revision:draft.revision,objective:objective.value.trim()});if(!page.isConnected)return;
   const picks=[];recommendations.append(el('p','fw-note',`AI推荐 ${data.recommendations.length} 个词，仅供参考；勾选后加入，不覆盖已有选择。`));
   for(const row of data.recommendations){const label=el('label','fw-recommend-row'),check=el('input'),detail=el('span');check.type='checkbox';check.checked=true;check.dataset.recommendedWord=row.word;detail.append(el('strong','',row.word),el('small','',row.reason));label.append(check,detail);recommendations.append(label);picks.push(check);}
   const accept=button('加入勾选推荐词','primary');accept.onclick=()=>{let n=0;for(const check of picks)if(check.checked&&valid.has(check.dataset.recommendedWord)&&!chosen.has(check.dataset.recommendedWord)){chosen.add(check.dataset.recommendedWord);n++;}draw();notify(`已新增 ${n} 个推荐词，原有选择已保留`);};recommendations.append(accept);
  }catch(e){notify(e.message);recommendations.append(el('p','fw-note','推荐失败，已选词未改变。可重试或继续手动选择。'));}
  finally{recommending=false;if(page.isConnected){run.disabled=false;run.textContent='重新推荐';rerun.disabled=stopButton.disabled=mode.disabled=false;}}
 };
 const list=el('div','fw-word-list');main.append(list);const empty=el('p','fw-note','没有匹配的候选词');main.append(empty);
 const valid=new Set((draft.candidates||[]).map(x=>x.word)),chosen=new Set((draft.selected_words||[]).filter(w=>valid.has(w)));draft.selected_words=[...chosen];
 const summary=el('p','fw-note');page.append(summary);
 function preview(word){
  side.querySelector('.fw-preview')?.remove();if(!word)return;
  const box=el('section','fw-preview');box.append(el('h3','','原文示例'));
  const hits=[];for(const t of draft.interviews||[])for(const b of t.blocks||[])if(b.include&&(b.tokens||[]).includes(word))hits.push({t,b});
  box.append(el('p','fw-note',`${word} · 命中 ${hits.length} 个文本块`));
  if(hits.length){const {t,b}=hits[0],quote=el('p','fw-quote');quote.textContent=Array.from(t.text).slice(b.start,b.end).join('');box.append(quote);const link=button('查看原文 →','fw-link');link.onclick=()=>showSource(t,b);box.append(link);}else box.append(el('p','fw-note','重新分词后可查看对应原文。'));
  side.append(box);
 }
 function sync(){
  draft.selected_words=[...chosen];side.replaceChildren(el('h3','',`已选特征词 · ${chosen.size}`),el('p','fw-note','将用于生成共现网络'));
  const tags=el('div','fw-selected-tags');for(const word of chosen){const tag=button(word+' ×');tag.setAttribute('aria-label','取消选择 '+word);tag.onclick=()=>{chosen.delete(word);draw();};tags.append(tag);}side.append(tags);
  if(!chosen.size)side.append(el('p','fw-note','点击左侧词语进行选择。'));
  summary.textContent=`已选 ${chosen.size} 个特征词`;preview(focusWord||[...chosen][0]);
 }
 function draw(){
  list.replaceChildren();const q=search.value.trim().toLowerCase(),rows=(draft.candidates||[]).filter(x=>x.word.toLowerCase().includes(q)).slice();
  rows.sort(sort.value==='name'?(a,b)=>a.word.localeCompare(b.word,'zh-CN'):(a,b)=>b.blocks-a.blocks);
  for(const x of rows){const label=el('label','fw-word'),input=el('input');input.type='checkbox';input.dataset.word=x.word;input.checked=chosen.has(x.word);label.classList.toggle('selected',input.checked);label.append(input,el('span','',x.word),el('small','',String(x.blocks)));input.onchange=()=>{input.checked?chosen.add(x.word):chosen.delete(x.word);focusWord=x.word;label.classList.toggle('selected',input.checked);sync();};list.append(label);}
  empty.hidden=!!rows.length;sync();
 }
 search.oninput=draw;sort.onchange=draw;clear.onclick=()=>{chosen.clear();draw();};draw();
 const pop=el('section','fw-popover');pop.setAttribute('popover','manual');pop.setAttribute('role','dialog');pop.setAttribute('aria-label','停用词管理');page.append(pop);
 const head=el('header'),popTitle=el('h3'),close=button('×','fw-close');close.setAttribute('aria-label','关闭停用词管理');head.append(popTitle,close);
 const find=el('input');find.type='search';find.placeholder='搜索停用词';find.setAttribute('aria-label','搜索停用词');
 const addRow=el('div','fw-add-row'),entry=el('input'),add=button('+ 添加');entry.placeholder='输入新词';entry.setAttribute('aria-label','添加停用词');addRow.append(entry,add);
 const helper=el('p','fw-note','支持粘贴多个词，空格或换行分隔；自动去重'),chips=el('div','fw-stop-list'),changes=el('div','fw-changes'),diff=el('span'),reset=button('撤销修改','fw-link');changes.append(diff,reset);
 const footer=el('footer'),cancel=button('取消'),save=button('保存并重新分词','primary');footer.append(cancel,save);
 pop.append(head,find,addRow,helper,chips,changes,el('p','fw-note','保存前不会改变当前分词结果。'),footer);
 const changed=()=>stops.size!==initial.size||[...stops].some(w=>!initial.has(w));
 const pending=()=>setPending(changed()||mode.value!==(draft.token_mode||'answers'));
 mode.onchange=()=>{pending();notify('统计范围尚未应用，请点击“重新分词”');};
 function drawStops(){
  popTitle.textContent=`停用词管理 · ${stops.size} 个`;chips.replaceChildren();const q=find.value.trim().toLowerCase();
  for(const w of stops){if(!w.toLowerCase().includes(q))continue;const tag=el('span','fw-stop-tag');if(!initial.has(w))tag.classList.add('added');const remove=button('×');remove.setAttribute('aria-label','删除停用词 '+w);remove.disabled=saving;remove.onclick=()=>{stops.delete(w);drawStops();};tag.append(el('span','',w),remove);chips.append(tag);}
  if(!chips.childElementCount)chips.append(el('p','fw-note','没有匹配的停用词'));
  const added=[...stops].filter(w=>!initial.has(w)).length,deleted=[...initial].filter(w=>!stops.has(w)).length;
  diff.textContent=changed()?`待保存：新增 ${added} 个 · 删除 ${deleted} 个`:'未修改';reset.disabled=!changed()||saving;save.disabled=!changed()||saving;pending();
 }
 function addWords(){const words=entry.value.split(/\s+/u).filter(Boolean);if(!words.length)return;let count=0;for(const w of words)if(!stops.has(w)){stops.add(w);count++;}entry.value='';drawStops();if(!count)notify('这些词已在停用词中，未重复添加');}
 add.onclick=addWords;entry.onkeydown=e=>{if(e.key==='Enter'&&!e.isComposing){e.preventDefault();addWords();}};find.oninput=drawStops;reset.onclick=()=>{stops=new Set(initial);drawStops();};
 const controller=new AbortController();
 function position(){const r=stopButton.getBoundingClientRect(),width=Math.min(540,innerWidth-24);pop.style.width=width+'px';pop.style.left=Math.max(12,Math.min(r.left,innerWidth-width-12))+'px';pop.style.top=Math.max(12,Math.min(r.bottom+10,innerHeight-pop.offsetHeight-12))+'px';}
 function hide(discard=false){if(saving)return;if(changed()&&!discard){notify('停用词尚未保存，请保存或点击“取消”放弃修改');return;}if(pop.matches(':popover-open'))pop.hidePopover();stopButton.setAttribute('aria-expanded','false');stopButton.focus();}
 stopButton.onclick=()=>{if(pop.matches(':popover-open')){hide();return;}stops=new Set(initial);find.value=entry.value='';drawStops();pop.showPopover();position();stopButton.setAttribute('aria-expanded','true');find.focus();};
 close.onclick=()=>hide();cancel.onclick=()=>{stops=new Set(initial);drawStops();hide(true);};
 document.addEventListener('pointerdown',e=>{if(pop.matches(':popover-open')&&!pop.contains(e.target)&&!stopButton.contains(e.target))hide();},{signal:controller.signal});
 document.addEventListener('keydown',e=>{if(e.key==='Escape'&&pop.matches(':popover-open')){e.preventDefault();hide();}},{signal:controller.signal});
 window.addEventListener('resize',()=>{if(pop.matches(':popover-open'))position();},{signal:controller.signal});
 async function submit(newStops){
  if(saving)return;saving=true;save.disabled=cancel.disabled=close.disabled=add.disabled=entry.disabled=find.disabled=rerun.disabled=mode.disabled=stopButton.disabled=true;main.inert=side.inert=true;chips.querySelectorAll('button').forEach(b=>b.disabled=true);setPending(true);
  try{await apply({mode:mode.value,stopwords:[...newStops],keep:[...chosen]});}
  catch(error){notify(error.message);}
  finally{saving=false;if(page.isConnected){save.disabled=cancel.disabled=close.disabled=add.disabled=entry.disabled=find.disabled=rerun.disabled=mode.disabled=stopButton.disabled=false;main.inert=side.inert=false;drawStops();}}
 }
 save.onclick=()=>submit(stops);rerun.onclick=()=>{if(changed()){notify('请先保存或取消停用词修改');return;}submit(initial);};
 return ()=>{controller.abort();pop.remove();settings.remove();};
};
