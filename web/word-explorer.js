/* Read-only views over the saved graph and its exact evidence references. */
(function(scope){
 'use strict';
 const pairKey=(a,b)=>JSON.stringify([a,b].sort());
 function refsFor(edge,interviews){
  const lookup=new Map(interviews.map(t=>[t.id,t])),seen=new Set(),rows=[];
  for(const ref of edge?.evidence||[]){const key=JSON.stringify([ref.interview_id,ref.block_id]);if(seen.has(key))continue;seen.add(key);const t=lookup.get(ref.interview_id),b=t?.blocks?.find(b=>b.id===ref.block_id);rows.push({ref,t,b});}return rows;
 }
 function association(edge,nodes){const lookup=new Map(nodes.map(n=>[n.id,n])),a=lookup.get(edge.source)?.count||0,b=lookup.get(edge.target)?.count||0,union=a+b-edge.count;return union>0?edge.count/union:0;}
 function distribution(edge,interviews){const counts=new Map();for(const {ref}of refsFor(edge,interviews))counts.set(ref.interview_id,(counts.get(ref.interview_id)||0)+1);return interviews.map(t=>({id:t.id,name:t.name,count:counts.get(t.id)||0}));}
 function combinedScore(edge,nodes,total){return total>0?association(edge,nodes)*edge.interviews/total:0;}
 const data={pairKey,refsFor,association,distribution,combinedScore};
 if(typeof module!=='undefined')module.exports=data;
 if(!scope?.document)return;
 scope.wordExplorerData=data;
 scope.mountWordExplorer=function({page,heading,bar,layout,networkViews,fit,exportButton,getState,selectNode,selectEdge,showSource,draft,stopMotion,initialView='rank'}){
  const el=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n;},btn=(text,cls)=>{const b=el('button',cls,text);b.type='button';return b;};
  let mode='rank',sort='count',interview='',matrixLimit=50,zerosOpen=false,lastLeft=null;
  const sourceChars=new WeakMap();
  function sourceText(t,b){let chars=sourceChars.get(t);if(!chars){chars=Array.from(t.text);sourceChars.set(t,chars);}return chars.slice(b.start,b.end).join('');}
  const root=page.parentElement;root.classList.add('we-compact');
  const graphCounts=bar.querySelector('.wn-counts');
  const tabs=el('div','we-tabs'),modes=[['network','关系总览'],['rank','关联排行'],['matrix','共现矩阵']],tabButtons=new Map();tabs.setAttribute('role','group');tabs.setAttribute('aria-label','词语共现分析视图');
  for(const [id,label]of modes){const b=btn(label);b.onclick=()=>setMode(id);tabs.append(b);tabButtons.set(id,b);}bar.prepend(tabs);
  const sortSelect=el('select','we-sort');sortSelect.setAttribute('aria-label','关联排序');for(const [value,label]of [['count','按共现块数排序'],['coverage','按覆盖访谈排序'],['association','按相对关联度排序']])sortSelect.append(new Option(label,value));sortSelect.onchange=()=>{sort=sortSelect.value;refresh();};
  const rankSort=el('select','we-rank-sort');rankSort.setAttribute('aria-label','当前词语关联排序');for(const [value,label]of [['count','共现块数'],['coverage','覆盖访谈'],['association','相对关联度'],['combined','综合分数']])rankSort.append(new Option('排序：'+label,value));rankSort.title='综合分数 = Jaccard × 词对覆盖访谈数 ÷ 纳入访谈总数。仅为辅助排序，不代表显著性或可信度。';rankSort.onchange=()=>{sort=rankSort.value;if(sort!=='combined')sortSelect.value=sort;refresh();};
  const help=btn('?','we-help');help.setAttribute('aria-label','共现分析说明');help.title='每个文本块内同一词只计一次；统计范围沿用生成图时的设置。相对关联度 = 共同出现块数 ÷ 至少含其中一个词的块数（Jaccard）。少量样本可能产生高关联度，请结合共现块数、访谈覆盖和原文判断。共现不表示因果或观点一致。';bar.insertBefore(sortSelect,fit);bar.insertBefore(help,fit);
  const pane=el('div','we-layout'),left=el('section','we-main'),right=el('aside','we-evidence-panel');pane.append(left,right);page.insertBefore(pane,layout);
  const download=btn('导出数据','we-download');bar.append(download);download.onclick=exportCsv;
  function linked(state){return state.visible.filter(e=>e.source===state.focus||e.target===state.focus).slice().sort((a,b)=>value(b)-value(a)||b.count-a.count||pairKey(a.source,a.target).localeCompare(pairKey(b.source,b.target)));}
  function value(edge){const state=getState();return sort==='combined'?combinedScore(edge,state.nodes,draft.interviews.length):sort==='association'?association(edge,state.nodes):sort==='coverage'?edge.interviews:edge.count;}
  function sizePanels(){if(!pane.hidden){const height=Math.max(340,window.innerHeight-pane.getBoundingClientRect().top-18);page.style.setProperty('--we-panel-height',height+'px');}}
  const sizing=new ResizeObserver(sizePanels);sizing.observe(heading);window.addEventListener('resize',sizePanels);
  function setMode(next){const changed=mode!==next;mode=next;if(next!=='network'){stopMotion();const state=getState();if(!state.focus&&state.visibleNodes.length){const first=state.visibleNodes.slice().sort((a,b)=>b.count-a.count)[0];selectNode(first.id);}}refresh();if(changed)window.animateWorkspaceTransition?.(next==='network'?layout:pane);}
  function refresh(){
   const state=getState();for(const [id,b]of tabButtons)b.setAttribute('aria-pressed',String(id===mode));const network=mode==='network';layout.hidden=!network;pane.hidden=network;networkViews.hidden=!network;fit.hidden=exportButton.hidden=!network;sortSelect.hidden=download.hidden=network;page.classList.toggle('we-active',!network);page.querySelector('.wn-note').hidden=!network;
   graphCounts.hidden=!network;if(network){lastLeft=null;if(state.networkCountText)graphCounts.textContent=state.networkCountText;return;}
   const stamp=[mode,sort,state.focus,matrixLimit,zerosOpen];
   if(lastLeft&&lastLeft.visible===state.visible&&lastLeft.nodes===state.nodes&&stamp.every((v,i)=>v===lastLeft.stamp[i])){
    const key=state.selectedEdge?pairKey(state.selectedEdge.source,state.selectedEdge.target):'';
    for(const row of left.querySelectorAll('[data-pair-key]'))row.classList.toggle('selected',row.dataset.pairKey===key);
    const scroll=left.scrollTop;left.querySelector('.we-distribution')?.remove();renderDistribution(state);left.scrollTop=scroll;
    updateEvidence(state);return;
   }
   lastLeft={visible:state.visible,nodes:state.nodes,stamp};
   graphCounts.textContent=`${state.visibleNodes.length} 个词 · ${state.visible.length} 条共现`;left.replaceChildren();right.replaceChildren();if(!state.visible.length){lastLeft=null;left.append(el('p','we-empty','当前阈值下没有共现关系，请降低“至少共现”的设置。'));return;}
   const title=el('header','we-section-head'),chip=el('span','we-focus-chip','当前词语：'+(state.nodes.find(n=>n.id===state.focus)?.label||state.focus||'未选择'));chip.title='通过上方搜索切换当前词语';title.append(chip,el('span','we-summary',graphCounts.textContent));left.append(title);
   if(mode==='rank'){sortSelect.hidden=true;rankSort.value=sort;chip.after(rankSort);renderRank(state);}else {if(sort==='combined'){sort='count';sortSelect.value='count';}renderMatrix(state);}
   updateEvidence(state);
  }
  function updateEvidence(state){right.replaceChildren();renderEvidence(state);const evidenceCount=right.querySelector('.we-meta'),evidenceControls=right.querySelector('.we-evidence-controls');if(evidenceCount&&evidenceControls)evidenceControls.append(evidenceCount);sizePanels();}
  function renderRank(state){
   const rows=linked(state),table=el('table','we-ranking'),thead=el('thead'),tr=el('tr');for(const label of ['关联词','共现块数','覆盖访谈','相对关联度']){const th=el('th','',label);if(label==='相对关联度'){const tip=btn('?','we-association-help');tip.setAttribute('aria-label','相对关联度说明');tip.title='相对关联度即 Jaccard 系数：同时包含两个词的话题块数 ÷ 至少包含其中一个词的话题块数。取值为0—1，越高表示两词出现范围的重叠比例越大，不代表因果或语义相似。少量材料也可能得到高值，请结合共现块数和访谈覆盖判断。';th.append(tip);}tr.append(th);}thead.append(tr);table.append(thead);const body=el('tbody'),max=Math.max(1,...rows.map(e=>e.count));
   for(const edge of rows){const name=edge.source===state.focus?edge.target:edge.source,row=el('tr');row.classList.toggle('selected',state.selectedEdge===edge);const word=el('td'),choose=btn(name,'we-word');choose.setAttribute('aria-label','查看关联：'+name);choose.onclick=()=>{interview='';selectEdge(edge);};word.append(choose);const amount=el('td','we-amount'),number=el('span','',String(edge.count)),track=el('span','we-track'),fill=el('i');fill.style.width=(edge.count/max*100)+'%';track.append(fill);amount.append(number,track);row.append(word,amount,el('td','',`${edge.interviews} / ${draft.interviews.length} 篇`),el('td','',association(edge,state.nodes).toFixed(3)));body.append(row);}table.append(body);left.append(table);if(!rows.length)left.append(el('p','we-empty','当前词语没有达到阈值的关联词。'));
   for(const row of body.children){const edge=rows[row.sectionRowIndex];row.dataset.pairKey=pairKey(edge.source,edge.target);row.classList.add('we-clickable-row');row.tabIndex=0;row.setAttribute('aria-label',`查看原文证据：${edge.source}与${edge.target}，${edge.count}块`);const open=()=>{interview='';selectEdge(edge);};row.onclick=e=>{if(!e.target.closest('button'))open();};row.onkeydown=e=>{if(e.target===row&&(e.key==='Enter'||e.key===' ')){e.preventDefault();open();}};}
   renderDistribution(state);
  }
  function renderDistribution(state){
   const edge=state.selectedEdge,section=el('section','we-distribution');section.append(el('h4','',edge?`${edge.source} × ${edge.target} · 访谈分布`:'访谈分布'));if(!edge){section.append(el('p','we-empty','点击上方关联词，查看共现在哪些访谈中出现。'));left.append(section);return;}
   const rows=distribution(edge,draft.interviews).sort((a,b)=>b.count-a.count),max=Math.max(1,...rows.map(r=>r.count)),zeroRows=rows.filter(t=>!t.count),zeroList=el('div','we-zero-list');zeroList.hidden=!zerosOpen;for(const t of rows){const row=btn('','we-interview-row');row.setAttribute('aria-label',`筛选访谈：${t.name}，${t.count}块`);row.classList.toggle('selected',interview===t.id);const name=el('span','we-interview-name',t.name),track=el('span','we-track'),fill=el('i');name.title=t.name;fill.style.width=(t.count/max*100)+'%';track.append(fill);row.append(name,track,el('span','we-interview-count',`${t.count} 块`));row.onclick=()=>{interview=interview===t.id?'':t.id;refresh();};(t.count?section:zeroList).append(row);}if(zeroRows.length){const toggle=btn(`另 ${zeroRows.length} 篇无共现 · ${zerosOpen?'收起':'查看'}`,'we-zero-toggle');toggle.setAttribute('aria-expanded',String(zerosOpen));toggle.onclick=()=>{zerosOpen=!zerosOpen;refresh();};section.append(toggle,zeroList);}left.append(section);
  }
  function renderMatrix(state){
   const controls=el('div','we-matrix-controls'),limit=el('select');limit.setAttribute('aria-label','矩阵词数');for(const n of [20,50,0])limit.append(new Option(n?'前 '+n+' 个词':'全部词语',String(n)));limit.value=String(matrixLimit);limit.onchange=()=>{matrixLimit=Number(limit.value);refresh();};
   let words=state.visibleNodes.slice().sort((a,b)=>b.count-a.count||a.label.localeCompare(b.label));if(matrixLimit)words=words.slice(0,matrixLimit);if(state.focus&&!words.some(n=>n.id===state.focus)){const n=state.nodes.find(n=>n.id===state.focus);if(n){words.pop();words.unshift(n);}}
   controls.append(limit,el('span','',`${words.length} / ${state.visibleNodes.length} 个词`));left.querySelector('.we-focus-chip').after(controls);
   const scroll=el('div','we-matrix-scroll'),table=el('table','we-matrix'),head=el('tr');head.append(el('th','we-corner','词语'));for(const n of words){const th=el('th'),b=btn(n.label);b.title=n.label;b.onclick=()=>{interview='';selectNode(n.id);};th.append(b);head.append(th);}const thead=el('thead');thead.append(head);table.append(thead);
   const lookup=new Map(state.visible.map(e=>[pairKey(e.source,e.target),e])),max=Math.max(.00001,...state.visible.map(value)),body=el('tbody');
   for(const a of words){const row=el('tr'),th=el('th'),word=btn(a.label);word.onclick=()=>{interview='';selectNode(a.id);};th.append(word);row.append(th);for(const b of words){const td=el('td');if(a.id===b.id){td.className='we-diagonal';td.textContent='—';}else{const edge=lookup.get(pairKey(a.id,b.id));if(edge){const cell=btn(sort==='association'?association(edge,state.nodes).toFixed(2):String(sort==='coverage'?edge.interviews:edge.count),'we-cell');cell.style.background=`rgba(0,158,150,${.07+.65*value(edge)/max})`;if(value(edge)/max>.6)cell.style.color='#fff';cell.dataset.pairKey=pairKey(edge.source,edge.target);cell.classList.toggle('selected',state.selectedEdge===edge);cell.setAttribute('aria-label',`查看共现：${a.label}与${b.label}，${edge.count}块，${edge.interviews}篇`);cell.title=`${edge.count} 块 · ${edge.interviews} 篇 · 相对关联度 ${association(edge,state.nodes).toFixed(3)}`;cell.onclick=()=>{interview='';selectEdge(edge);};td.append(cell);}else{td.className='we-no-edge';td.textContent='·';td.title='无共现或低于当前阈值';}}row.append(td);}body.append(row);}table.append(body);scroll.append(table);left.append(scroll);renderDistribution(state);
  }
  function renderEvidence(state){
   const edge=state.selectedEdge,head=el('header','we-section-head');right.append(head);if(!edge){head.append(el('h3','','原文证据'));right.append(el('p','we-empty','点击关联词或矩阵格子查看对应文本块。'));return;}
   head.append(el('h3','we-pair',`${edge.source} × ${edge.target}`),el('span','we-summary',`${edge.count} 块 · ${edge.interviews} 篇`));const filterRow=el('div','we-evidence-controls'),filter=el('select','we-evidence-filter');filter.setAttribute('aria-label','原文访谈筛选');filter.append(new Option('全部访谈',''));for(const t of draft.interviews)filter.append(new Option(t.name,t.id));filter.value=interview;filter.onchange=()=>{interview=filter.value;refresh();};filterRow.append(filter);right.append(filterRow);
   const rows=refsFor(edge,draft.interviews).filter(r=>!interview||r.ref.interview_id===interview),list=el('div','we-evidence-list');let valid=0;
   for(const {t,b}of rows){if(!t||!b)continue;valid++;const card=el('section','we-quote'),blockIndex=t.blocks.indexOf(b)+1;card.append(el('strong','',`${t.name} · 文本块 ${blockIndex}`));const quote=el('p'),source=sourceText(t,b),terms=[edge.source,edge.target].filter(Boolean).sort((a,b)=>b.length-a.length);let i=0,plain='';while(i<source.length){const term=terms.find(w=>source.startsWith(w,i));if(term){if(plain){quote.append(document.createTextNode(plain));plain='';}quote.append(el('mark','',term));i+=term.length;}else plain+=source[i++];}if(plain)quote.append(document.createTextNode(plain));const jump=btn('定位到原文 →','we-source');jump.onclick=()=>showSource(t,b);card.append(quote,jump);list.append(card);}if(!rows.length)list.append(el('p','we-empty','这篇访谈中没有该词对的共现文本块。'));else if(valid!==rows.length)list.append(el('p','we-empty','部分原文引用暂不可用，请核对草稿版本。'));right.append(el('p','we-meta',`当前显示 ${valid} 个文本块`),list);
  }
  function exportCsv(){const state=getState(),rows=mode==='rank'?linked(state):state.visible,lines=[['词语一','词语二','共现块数','覆盖访谈数','纳入访谈数','相对关联度_Jaccard'],...rows.map(e=>[e.source,e.target,e.count,e.interviews,draft.interviews.length,association(e,state.nodes).toFixed(6)])];const csv='\ufeff'+lines.map(row=>row.map(v=>'"'+String(v).replaceAll('"','""')+'"').join(',')).join('\r\n'),url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'})),a=el('a');a.href=url;a.download='词语共现关联数据.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  return {refresh,start(){setMode(initialView);const state=getState(),first=linked(state)[0];if(initialView==='rank'&&first&&!state.selectedEdge)selectEdge(first);},dispose(){sizing.disconnect();window.removeEventListener('resize',sizePanels);root.classList.remove('we-compact');tabs.remove();pane.remove();sortSelect.remove();help.remove();download.remove();}};
 };
})(typeof window!=='undefined'?window:null);
