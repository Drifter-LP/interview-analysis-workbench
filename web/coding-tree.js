/* Presentation of existing analysis only: no model calls or data mutations. */
(() => {
 const ns='http://www.w3.org/2000/svg',make=(tag,attrs={},text)=>{const n=document.createElementNS(ns,tag);for(const [k,v] of Object.entries(attrs))n.setAttribute(k,v);if(text!==undefined)n.textContent=text;return n;};
 function build(analysis){
  const nodes=new Map(),roots=[];
  const add=(id,label,level,data,parent)=>{const n={id,label:label||'未命名',level,data,parent,children:[]};nodes.set(id,n);if(parent)parent.children.push(n);else roots.push(n);return n;};
  for(const [di,d] of (analysis?.dimensions||[]).entries()){
   const dim=d.is_flat_findings?null:add(`d${di}`,d.name,0,d);
   for(const [fi,f] of (d.findings||[]).entries()){
    const finding=add(`d${di}/f${fi}`,f.title,1,f,dim);
    for(const [ti,t] of (f.facts||[]).entries()){
     const fact=add(`${finding.id}/t${ti}`,t.text,2,t,finding);
     const seen=new Set();for(const [si,s] of (t.sources||[]).entries()){
      const key=JSON.stringify([s.project_id,s.number,s.start,s.end,s.quote]);if(seen.has(key))continue;seen.add(key);
      add(`${fact.id}/s${si}`,`${s.material_name||t.material_name||s.project_id||'访谈稿'} · 原文 ${s.number??si+1}`,3,s,fact);
     }
     if(!fact.children.length)for(const number of (t.evidence||[]))add(`${fact.id}/e${number}`,`${t.material_name||t.project_id||'访谈稿'} · 索引 ${number}`,3,{project_id:t.project_id,number},fact);
    }
   }
  }return {nodes,roots};
 }
 window.buildCodingTree=build;
 const css=document.createElement('link');css.rel='stylesheet';css.href='/assets/coding-tree.css?v=20261006-4';document.head.append(css);
 const page=document.querySelector('#focused'),tabs=document.querySelector('.network-tabs'),tab=document.createElement('button');tab.type='button';tab.textContent='主题发现树';tabs.append(tab);
 const root=document.createElement('section');root.className='coding-tree-workspace';root.hidden=true;
 root.innerHTML='<div class="coding-tree-layout"><div class="coding-tree-main"><div class="coding-tree-headings"><span>分析维度</span><span>整合发现</span><span>事实条目</span><span>原文证据</span></div><div class="coding-tree-scroll"><svg aria-label="可展开主题发现树" role="group"></svg><p class="coding-tree-empty" hidden></p></div><p class="coding-tree-note">点击＋／−展开层级 · 点击条目查看原文</p></div><aside class="coding-tree-detail" aria-live="polite"></aside></div>';
 page.append(root);
 let active=false,model=build(null),expanded=new Set(),selected=null ,record=null;
 const svg=root.querySelector('svg'),detail=root.querySelector('aside'),empty=root.querySelector('.coding-tree-empty');
 const textWrap=(text,width)=>{const canvas=document.createElement('canvas'),ctx=canvas.getContext('2d');ctx.font='14px sans-serif';const lines=[];let line='';for(const ch of String(text)){if(line&&ctx.measureText(line+ch).width>width){lines.push(line);line='';}line+=ch;}if(line)lines.push(line);return lines.length?lines:[''];};
 function evidenceFor(n){if(n.level===3)return [n.data];if(n.level===2)return n.children.map(c=>c.data);return n.children.flatMap(evidenceFor);}
 function showDetail(){
  detail.replaceChildren();const n=model.nodes.get(selected);if(!n){const p=document.createElement('p');p.className='coding-tree-muted';p.textContent='选择条目，查看说明与原文证据。';detail.append(p);return;}
  const heading=document.createElement('h3'),badge=document.createElement('span');heading.textContent=n.label;badge.className='coding-tree-type';badge.textContent=['分析维度','整合发现','事实条目','原文证据'][n.level];detail.append(heading,badge);
  const description=n.data.definition||n.data.summary||(n.level===2?n.data.text:'');if(description){const p=document.createElement('p');p.textContent=description;detail.append(p);}
  const boundary=n.data.boundary_review_info;if(boundary){const box=document.createElement('details'),summary=document.createElement('summary'),reason=document.createElement('p');summary.textContent='合并边界复核：'+(boundary.decision==='split'?'由原发现拆分':'保留原发现');reason.textContent=boundary.reason;box.append(summary,reason);if(boundary.decision==='split'){const original=document.createElement('p');original.textContent='复核前：'+(boundary.original_finding?.title||'')+'\n'+(boundary.original_finding?.summary||'');box.append(original);}const caution=document.createElement('p');caution.className='coding-tree-muted';caution.textContent='模型的边界判断，不代表已完成原文支持性核查。';box.append(caution);detail.append(box);}
  const notes=[...(n.data.reference_notes||[]),...(n.data.differences?['差异与例外：'+n.data.differences]:[]),...(n.data.unclassified_reason?['暂无分类：'+n.data.unclassified_reason]:[])];for(const note of notes){const p=document.createElement('p');p.className='coding-tree-muted';p.textContent=note;detail.append(p);}if(n.data.reference_notes?.length){const p=document.createElement('p');p.className='coding-tree-muted';p.textContent='引用关系由程序计算，不代表语义重复。';detail.append(p);}
  const unique=new Map();for(const s of evidenceFor(n))unique.set(JSON.stringify([s.project_id,s.number,s.start,s.end,s.quote]),s);
  const title=document.createElement('h4');title.textContent='原文证据 ';const count=document.createElement('span');count.className='coding-tree-count';count.textContent=unique.size;title.append(count);detail.append(title);
  for(const s of unique.values()){
   const block=document.createElement('section'),source=document.createElement('p'),quote=document.createElement('blockquote'),button=document.createElement('button');source.className='coding-tree-source';source.textContent=`${s.material_name||s.project_id||'访谈稿'} · ${s.source_type==='transcript'?'原文':'索引'} ${s.number??''}`;
   quote.textContent=s.quote||'此历史条目未保存原文快照，请打开原文索引核查。';button.type='button';button.className='coding-tree-context';button.textContent='查看上下文 →';button.onclick=()=>openThemeEvidence(s.project_id,Number(s.number),s);block.append(source,quote,button);detail.append(block);
  }if(!unique.size){const p=document.createElement('p');p.textContent='此条目未保存可用原文索引。';detail.append(p);}
 }
 function draw(){
  svg.replaceChildren();
  const visible=[],links=[];let cursor=12;
  const visit=n=>{const lines=textWrap(n.label,168),h=Math.max(54,lines.length*21+22);const open=expanded.has(n.id);const children=open?n.children:[];const start=cursor;let y;
   if(children.length){const positions=children.map(visit).filter(Boolean);y=positions.length?(positions[0].y+positions.at(-1).y)/2:cursor+h/2;cursor=Math.max(cursor,start+h+20);for(const c of positions)links.push({parent:n,child:c});}
   else{y=cursor+h/2;cursor+=h+24;}
   n.x=24+(n.level-(record?.dimension_stage_skipped?1:0))*252;n.y=y;n.h=h;n.lines=lines;n.open=open;visible.push(n);return n;
  };
  const headings=root.querySelector('.coding-tree-headings');headings.innerHTML=record?.dimension_stage_skipped?'<span>整合发现</span><span>事实条目</span><span>原文证据</span>':'<span>分析维度</span><span>整合发现</span><span>事实条目</span><span>原文证据</span>';
  model.roots.forEach(n=>{visit(n);cursor+=24;});const height=Math.max(400,cursor),width=Math.max(record?.dimension_stage_skipped?780:1032,...visible.map(n=>n.x+224));svg.setAttribute('viewBox',`0 0 ${width} ${height}`);svg.setAttribute('width',width);svg.setAttribute('height',height);
  for(const {parent:p,child:c} of links){const x=p.x+216,m=x+18;svg.append(make('path',{d:`M ${x} ${p.y} H ${m} V ${c.y} H ${c.x}`,fill:'none',stroke:'#37bfb8','stroke-width':1.3}));}
  for(const n of visible){const g=make('g',{transform:`translate(${n.x},${n.y-n.h/2})`,role:'button',tabindex:0,'aria-label':n.label,'data-node':n.id});g.append(make('rect',{width:216,height:n.h,rx:16,fill:selected===n.id?'#e0f5f3':n.level===0?'#edf9f7':'#fff',stroke:selected===n.id?'#69c8c3':'#dce7eb'}));
   const t=make('text',{x:36,y:(n.h-n.lines.length*21)/2+16,fill:'#173742','font-size':14,'font-family':'sans-serif','font-weight':n.level<2?600:400});n.lines.forEach((line,i)=>t.append(make('tspan',{x:36,dy:i?21:0},line)));g.append(t);
   if(n.children.length){g.setAttribute('aria-expanded',String(n.open));const toggle=make('g',{role:'button',tabindex:0,'aria-label':`${n.open?'收起':'展开'}${n.label}`});toggle.append(make('rect',{x:10,y:n.h/2-10,width:20,height:20,rx:5,fill:'#f6fbfb',stroke:'#dce7eb'}),make('text',{x:20,y:n.h/2+5,'text-anchor':'middle',fill:'#258f89','font-size':16},n.open?'−':'+'));const flip=e=>{e.stopPropagation();expanded.has(n.id)?expanded.delete(n.id):expanded.add(n.id);draw();};toggle.onclick=flip;toggle.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();flip(e);}};g.append(toggle);g.append(make('title',{},`${n.label} · ${n.children.length} 个下级条目`));}
   const choose=()=>{selected=n.id;draw();showDetail();};g.onclick=choose;g.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();choose();}};svg.append(g);
  }empty.hidden=visible.length>0;empty.textContent=currentThemeAnalysis?'这条历史结果没有维度层级，无法展示主题发现树。':'请先打开一条主题分析结果。';
 }
 function refresh(){if(!active)return;if(record!==currentThemeAnalysis){record=currentThemeAnalysis;model=build(record);expanded=new Set(model.roots.map(n=>n.id));selected=model.roots[0]?.id||null;}draw();showDetail();window.workspaceHeader?.refresh();}
 function hideBase(){for(const el of [document.querySelector('#themeQuickInput')?.closest('.focused-input'),document.querySelector('#themePanel'),document.querySelector('#comparisonWorkspace'),document.querySelector('#comparisonQuickRow')])if(el){el.hidden=true;el.style.display='none';}}
 window.codingTree={get active(){return active;},leave(){active=false;root.hidden=true;tab.classList.remove('active');page.classList.remove('coding-tree-active');for(const id of ['comparisonWorkspace','comparisonQuickRow']){const e=document.getElementById(id);if(e)e.style.display='';}},refresh};
 tab.onclick=()=>{tabs.children[0].click();active=true;page.classList.add('coding-tree-active');root.hidden=false;[...tabs.children].forEach(b=>b.classList.toggle('active',b===tab));hideBase();refresh();};
 const original=renderFocusedAnalysis;renderFocusedAnalysis=function(){original();if(active){hideBase();refresh();}};
})();
