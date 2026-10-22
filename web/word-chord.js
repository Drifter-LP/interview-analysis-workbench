/* Undirected chord view. No backend writes or statistical recomputation. */
(function(scope){
 'use strict';
 const TAU=Math.PI*2;
 const pairKey=(a,b)=>JSON.stringify([a,b].sort());
 function prepareGraph(nodes,edges){
  const ids=new Set();for(const n of nodes){if(ids.has(n.id))throw Error('词语编号重复');ids.add(n.id);}
  const unique=new Map(),warnings=[];
  for(const e of edges){
   if(!ids.has(e.source)||!ids.has(e.target)||!Number.isFinite(e.count)||e.count<=0||e.source===e.target)throw Error('共现词对或权重无效，请核对已有结果');
   const key=pairKey(e.source,e.target),old=unique.get(key);
   if(old){
    const refs=x=>JSON.stringify((x.evidence||[]).map(r=>JSON.stringify([r.interview_id,r.block_id])).sort());
    if(old.count!==e.count||old.interviews!==e.interviews||refs(old)!==refs(e))throw Error('重复词对的统计不一致，未自动相加');
    warnings.push('重复词对只展示一次');continue;
   }
   unique.set(key,e);
  }
  const ordered=nodes.slice().sort((a,b)=>(Number.isFinite(a.group)?a.group:999)-(Number.isFinite(b.group)?b.group:999)||String(a.label||a.id).localeCompare(String(b.label||b.id),'zh-CN')||String(a.id).localeCompare(String(b.id)));
  return{nodes:ordered,edges:[...unique.values()],warnings};
 }
 function chordLayout(nodes,edges){
  const n=nodes.length,index=new Map(nodes.map((node,i)=>[node.id,i])),matrix=Array.from({length:n},()=>Array(n).fill(0));
  for(const e of edges){const i=index.get(e.source),j=index.get(e.target);if(i===undefined||j===undefined||i===j)throw Error('和弦矩阵引用无效');if(matrix[i][j])throw Error('矩阵词对重复');matrix[i][j]=matrix[j][i]=e.count;}
  const weights=matrix.map(row=>row.reduce((a,b)=>a+b,0)),total=weights.reduce((a,b)=>a+b,0),gap=n?Math.min(.035,TAU/n*.16):0;
  const zeros=weights.filter(w=>!w).length,zeroAngle=total?Math.min(.025,(TAU-gap*n)/Math.max(1,n)*.3):n?(TAU-gap*n)/n:0;
  const scale=total?(TAU-gap*n-zeroAngle*zeros)/total:0,groups=[],slots=Array.from({length:n},()=>new Map());let angle=gap/2;
  for(let i=0;i<n;i++){
   const start=angle,end=start+(weights[i]?weights[i]*scale:zeroAngle);
   groups.push({id:nodes[i].id,index:i,start,end,value:weights[i],placeholder:!weights[i]});
   // Stable circular neighbor order prevents sort changes on hover/focus.
   let cursor=start;for(let j=0;j<n;j++)if(matrix[i][j]){const next=cursor+matrix[i][j]*scale;slots[i].set(j,{start:cursor,end:next});cursor=next;}
   angle=end+gap;
  }
  const ribbons=edges.map(edge=>{const i=index.get(edge.source),j=index.get(edge.target);return{edge,a:slots[i].get(j),b:slots[j].get(i),key:pairKey(edge.source,edge.target),value:edge.count};});
  return{groups,ribbons,matrix,weights,matrixSum:total,pairWeight:edges.reduce((s,e)=>s+e.count,0),scale};
 }
 const polar=(angle,r)=>[Math.sin(angle)*r,-Math.cos(angle)*r];
 const point=p=>p.map(x=>Number(x.toFixed(5))).join(' ');
 function arcPath(start,end,inner=252,outer=274){
  return 'M'+point(polar(start,outer))+' A'+outer+' '+outer+' 0 '+Number(end-start>Math.PI)+' 1 '+point(polar(end,outer))+' L'+point(polar(end,inner))+' A'+inner+' '+inner+' 0 '+Number(end-start>Math.PI)+' 0 '+point(polar(start,inner))+' Z';
 }
 function ribbonPath(a,b,r=250){
  return 'M'+point(polar(a.start,r))+' A'+r+' '+r+' 0 '+Number(a.end-a.start>Math.PI)+' 1 '+point(polar(a.end,r))+' Q0 0 '+point(polar(b.start,r))+' A'+r+' '+r+' 0 '+Number(b.end-b.start>Math.PI)+' 1 '+point(polar(b.end,r))+' Q0 0 '+point(polar(a.start,r))+' Z';
 }
 function labelLayout(groups,nodes){
  const lookup=new Map(nodes.map(n=>[n.id,n])),sides={left:[],right:[]};
  for(const g of groups){const angle=(g.start+g.end)/2,anchor=polar(angle,280),side=anchor[0]<0?'left':'right',chars=Array.from(String(lookup.get(g.id)?.label||g.id)),lines=[];for(let i=0;i<chars.length;i+=14)lines.push(chars.slice(i,i+14).join(''));sides[side].push({id:g.id,anchor,desired:anchor[1],side,lines,height:Math.max(22,lines.length*17+5)});}
  const height=Math.max(760,...Object.values(sides).map(labels=>labels.reduce((s,l)=>s+l.height,0)+120));
  for(const labels of Object.values(sides)){
   labels.sort((a,b)=>a.desired-b.desired);let cursor=-height/2+55;
   for(const label of labels){label.y=Math.max(label.desired,cursor+label.height/2);cursor=label.y+label.height/2;}
   cursor=height/2-55;for(const label of labels.slice().reverse()){label.y=Math.min(label.y,cursor-label.height/2);cursor=label.y-label.height/2;}
  }
  return{labels:[...sides.left,...sides.right],box:{x:-560,y:-height/2,w:1120,h:height}};
 }
 const helpers={prepareGraph,chordLayout,arcPath,ribbonPath,labelLayout,pairKey};
 if(typeof module!=='undefined')module.exports=helpers;
 if(!scope?.document)return;
 scope.wordChordGeometry=helpers;
 scope.renderWordNetwork=function({root,heading,draft,showSource}){
  const ns='http://www.w3.org/2000/svg',graph=prepareGraph(draft.graph?.nodes||[],draft.graph?.edges||[]),nodes=graph.nodes,edges=graph.edges;
  const lookup=new Map(nodes.map(n=>[n.id,n])),rank=new Map(nodes.map((n,i)=>[n.id,i])),colors=['#48a89c','#87acc9','#d4b477','#ad9bc3','#9ab582','#c58f97','#6eaab7','#b9ad78','#869bc2','#86bcb0'];
  const color=id=>colors[rank.get(id)%colors.length],name=id=>lookup.get(id)?.label||id;
  const el=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n;};
  const shape=(tag,attrs={},text)=>{const n=document.createElementNS(ns,tag);for(const[k,v]of Object.entries(attrs))n.setAttribute(k,v);if(text!==undefined)n.textContent=text;return n;};
  const button=text=>{const b=el('button','',text);b.type='button';return b;};
  let visible=[],visibleNodes=[],focus=null,selectedEdge=null,local=false,hover=null,explorer=null,chart=null,base=null,camera=null,drag=null,suppress=false,disposed=false,resizeFrame=0;
  const page=el('section','wn-workspace wc-chord-workspace'),bar=el('div','wn-toolbar'),searchWrap=el('div','wn-search'),search=el('input'),results=el('div','wn-results');
  search.type='search';search.placeholder='搜索词语';search.setAttribute('aria-label','搜索共现词语');results.hidden=true;searchWrap.append(search,results);
  const views=el('div','wn-views'),allButton=button('全部词对'),focusButton=button('聚焦词语');views.append(allButton,focusButton);
  const thresholdLabel=el('label','wn-threshold','至少'),threshold=el('input');threshold.type='number';threshold.min='1';threshold.step='1';threshold.value='5';threshold.setAttribute('aria-label','最少共现块数');thresholdLabel.append(threshold,el('span','','块共现'));
  const counts=el('span','wn-counts'),fit=button('分析设置'),exportButton=button('导出图片');bar.append(searchWrap,views,thresholdLabel,counts,fit,exportButton);heading.classList.add('wn-heading');heading.append(bar);root.append(page);
  const layout=el('div','wn-layout'),stage=el('div','wn-stage'),svg=shape('svg',{class:'wn-canvas wc-chord-canvas',role:'group','aria-label':'词语共现和弦图：无方向关联',preserveAspectRatio:'xMidYMid meet'}),aside=el('aside','wn-details'),head=el('header'),title=el('strong','','词语共现和弦图'),content=el('div','wn-detail-content');
  head.append(title);aside.append(head,content);stage.append(svg);layout.append(stage,aside);page.append(layout);
  const zoom=el('div','wn-zoom'),minus=button('−'),plus=button('+'),percent=el('output','','100%');minus.setAttribute('aria-label','缩小共现图');plus.setAttribute('aria-label','放大共现图');zoom.append(minus,percent,plus);stage.append(zoom);
  const note=el('p','wn-note','无方向共现，无箭头；每个词在圆周出现一次，每个词对只画一次。带宽为共同出现的话题块数；外圈弧长为当前显示关系的共现权重合计，不是词语独立出现次数。灰色占位弧表示当前没有连带。');page.append(note);
  const elements={nodes:[],labels:[],ribbons:[]},controller=new AbortController();
  function countText(){if(local&&focus){const linked=visible.filter(e=>e.source===focus||e.target===focus),words=new Set(linked.flatMap(e=>[e.source,e.target]));words.add(focus);return words.size+' / '+nodes.length+' 个词 · '+linked.length+' / '+visible.length+' 条共现';}return nodes.length+' 个词 · '+visible.length+' 条共现';}
  function applyCamera(){svg.setAttribute('viewBox',camera.x+' '+camera.y+' '+camera.w+' '+camera.h);percent.textContent=Math.round(base.w/camera.w*100)+'%';}
  function fitCamera(){if(!chart)return;const box={...chart.box},r=svg.getBoundingClientRect();if(r.width&&r.height){const ratio=r.width/r.height;if(box.w/box.h<ratio){const w=box.h*ratio;box.x-=(w-box.w)/2;box.w=w;}else{const h=box.w/ratio;box.y-=(h-box.h)/2;box.h=h;}}base=box;camera={...box};applyCamera();}
  function nodeInfo(id){const node=lookup.get(id),weight=chart?.weights.get(id)||0;return name(id)+'：自身出现于 '+(node?.count||0)+' 个话题块 · '+(node?.interviews||0)+' 篇访谈；当前显示关系的共现权重合计 '+weight+'（同一块可能在不同词对中重复贡献，不能当作独立块数）。';}
  function edgeInfo(edge){return name(edge.source)+' — '+name(edge.target)+'：共同出现于'+edge.count+'个话题块';}
  function highlight(){
   const edge=hover?.edge||(!hover?selectedEdge:null),id=hover?.id||(!hover&&!edge?focus:null),near=new Set();
   if(edge){near.add(edge.source);near.add(edge.target);}else if(id){near.add(id);for(const e of visible)if(e.source===id||e.target===id){near.add(e.source);near.add(e.target);}}
   for(const item of elements.nodes){const active=!near.size||near.has(item.id);item.node.setAttribute('opacity',active?'1':'.22');item.node.setAttribute('stroke',item.id===id?'#007b74':'white');item.node.setAttribute('stroke-width',item.id===id?'2.5':'1');item.node.setAttribute('aria-pressed',String(item.id===focus));}
   for(const item of elements.labels){item.node.setAttribute('opacity',!near.size||near.has(item.id)?'1':'.28');item.node.querySelector('text').setAttribute('font-weight',item.id===id?'700':'400');}
   for(const item of elements.ribbons){const active=edge?item.edge===edge:!id||item.edge.source===id||item.edge.target===id;item.node.setAttribute('fill-opacity',active?(edge?'.85':'.50'):'.055');item.node.setAttribute('stroke-opacity',active?'.28':'.035');}
   allButton.setAttribute('aria-pressed',String(!local));focusButton.setAttribute('aria-pressed',String(local));
  }
  function activate(node,action,info){
   node.addEventListener('click',()=>{if(!suppress)action();});node.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();action();}});
   const enter=()=>{hover=info;highlight();};const leave=()=>{hover=null;highlight();};
   node.addEventListener('pointerenter',enter);node.addEventListener('pointerleave',leave);node.addEventListener('focus',enter);node.addEventListener('blur',leave);
  }
  function details(){
   content.replaceChildren();
   if(selectedEdge){
    const edge=selectedEdge;title.textContent=name(edge.source)+' — '+name(edge.target);const back=button('← 返回词语');back.onclick=()=>{selectedEdge=null;hover=null;highlight();details();explorer?.refresh();};
    content.append(back,el('p','wn-evidence-count',edge.count+' 个话题块 · '+edge.interviews+' 篇访谈'),el('p','wn-muted','共同出现，不表示方向、因果或观点一致。'));
    const rows=scope.wordExplorerData?.refsFor(edge,draft.interviews||[])||(edge.evidence||[]).map(ref=>{const t=draft.interviews?.find(t=>t.id===ref.interview_id);return{t,b:t?.blocks.find(b=>b.id===ref.block_id)};});let shown=0;
    for(const {t,b}of rows){if(!t||!b)continue;const card=el('section','wn-evidence'),jump=button('查看完整原文 →');jump.className='wn-source';jump.onclick=()=>showSource(t,b);card.append(el('strong','',t.name),el('p','',Array.from(t.text).slice(b.start,b.end).join('')),jump);content.append(card);shown++;}
    if(shown!==edge.count)content.append(el('p','wn-muted','当前可回查 '+shown+' 个话题块；若与已有统计不符，请核对历史结果版本。'));
   }else if(focus){
    title.textContent=name(focus);content.append(el('p','wn-muted',nodeInfo(focus)));
    const linked=visible.filter(e=>e.source===focus||e.target===focus).sort((a,b)=>b.count-a.count);
    for(const e of linked){const b=button(name(e.source===focus?e.target:e.source)+' · '+e.count+' 块');b.className='wn-relation';b.onclick=()=>selectEdge(e);content.append(b);}
    if(!linked.length)content.append(el('p','wn-muted','当前阈值下没有直接共现关系，可降低阈值。'));
   }else{title.textContent='词语共现和弦图';content.append(el('p','wn-muted','点击圆周词语突出其直接关联；再次点击可退出聚焦。点击内部连带查看对应话题块和完整访谈原文。'),el('p','wn-muted','外圈长度：所连接词对的共现权重合计。词语自身出现次数在悬停信息中单独列出。'));}
  }
  function draw(){
   const scene=local&&focus?visible.filter(e=>e.source===focus||e.target===focus):visible,neighbors=new Set(scene.flatMap(e=>[e.source,e.target]));
   if(local&&focus)neighbors.add(focus);
   const sceneNodes=local&&focus?nodes.filter(n=>neighbors.has(n.id)):nodes;
   const data=chordLayout(sceneNodes,scene),labels=labelLayout(data.groups,sceneNodes);chart={...data,box:labels.box,weights:new Map(data.groups.map(g=>[g.id,g.value]))};
   svg.replaceChildren();elements.nodes=[];elements.labels=[];elements.ribbons=[];hover=null;
   svg.dataset.pairCount=scene.length;svg.dataset.nodeCount=sceneNodes.length;svg.dataset.matrixSum=data.matrixSum;svg.dataset.pairWeight=data.pairWeight;
   const defs=shape('defs'),bands=shape('g',{class:'wc-chord-bands'}),ring=shape('g',{class:'wc-chord-ring'}),textLayer=shape('g',{class:'wc-chord-labels'});svg.append(defs,bands,ring,textLayer);
   const prefix='chord-'+Math.random().toString(36).slice(2);
   data.ribbons.forEach((r,i)=>{
    const gradient=shape('linearGradient',{id:prefix+'-'+i,gradientUnits:'userSpaceOnUse',x1:polar((r.a.start+r.a.end)/2,250)[0],y1:polar((r.a.start+r.a.end)/2,250)[1],x2:polar((r.b.start+r.b.end)/2,250)[0],y2:polar((r.b.start+r.b.end)/2,250)[1]});
    gradient.append(shape('stop',{offset:'0%', 'stop-color':color(r.edge.source)}),shape('stop',{offset:'100%','stop-color':color(r.edge.target)}));defs.append(gradient);
    const path=shape('path',{d:ribbonPath(r.a,r.b),class:'wc-chord-ribbon',fill:'url(#'+prefix+'-'+i+')',stroke:'#396c69','stroke-width':.55,tabindex:0,role:'button','aria-label':'查看共现：'+name(r.edge.source)+'与'+name(r.edge.target)+'，'+r.edge.count+'块','data-a':r.edge.source,'data-b':r.edge.target,'data-count':r.edge.count});
    path.append(shape('title',{},edgeInfo(r.edge)));activate(path,()=>selectEdge(r.edge),{edge:r.edge});bands.append(path);elements.ribbons.push({edge:r.edge,node:path});
   });
   for(const g of data.groups){
    const path=shape('path',{d:arcPath(g.start,g.end),class:'wc-chord-node',fill:g.placeholder?'#dce7e6':color(g.id),tabindex:0,role:'button','aria-label':'查看词语：'+name(g.id),'data-word':g.id,'data-weight':g.value,'data-own-count':lookup.get(g.id)?.count||0});
    activate(path,()=>selectNode(g.id),{id:g.id});ring.append(path);elements.nodes.push({id:g.id,node:path});
   }
   for(const label of labels.labels){
    const left=label.side==='left',x=left?-325:325,g=shape('g',{class:'wc-chord-label',tabindex:0,role:'button','aria-label':'聚焦词语：'+name(label.id),'data-word':label.id});
    const leader=shape('path',{d:'M'+point(label.anchor)+' L'+(left?-302:302)+' '+label.y+' L'+(left?x+7:x-7)+' '+label.y,fill:'none',stroke:'#b4c9c6','stroke-width':.8,'pointer-events':'none'});
    const y=label.y-(label.lines.length-1)*8.5,text=shape('text',{x,y:y+5,'text-anchor':left?'end':'start','font-size':15,'font-family':'Microsoft YaHei, sans-serif',fill:'#24434c'});
    label.lines.forEach((line,i)=>text.append(shape('tspan',{x,dy:i?17:0},line)));
    const width=Math.max(...label.lines.map(line=>Array.from(line).length))*15+10;
    g.append(shape('rect',{x:left?x-width:x-4,y:label.y-label.height/2,width:width+4,height:label.height,fill:'transparent','pointer-events':'all'}),leader,text);
    activate(g,()=>selectNode(label.id),{id:label.id});textLayer.append(g);elements.labels.push({id:label.id,node:g});
   }
   if(!scene.length){const empty=shape('text',{x:0,y:0,'text-anchor':'middle',fill:'#71888e','font-size':16},nodes.length?'当前阈值下没有共现词对':'没有可显示的词语');svg.append(empty);if(nodes.length)svg.append(shape('text',{x:0,y:28,'text-anchor':'middle',fill:'#71888e','font-size':13},'可降低阈值；外圈保留所选词语'));}
   counts.textContent=countText();highlight();fitCamera();
  }
  function selectNode(id){if(!lookup.has(id))return;const wasLocal=local,toggled=focus===id&&!selectedEdge;focus=toggled?null:id;selectedEdge=null;hover=null;if(toggled)local=false;if(wasLocal)draw();else highlight();details();explorer?.refresh();}
  function selectEdge(edge){selectedEdge=edge;focus=focus&&[edge.source,edge.target].includes(focus)?focus:edge.source;hover=null;if(local)draw();else highlight();details();explorer?.refresh();}
  function update(){threshold.value=Math.max(1,Math.floor(Number(threshold.value)||1));visible=edges.filter(e=>e.count>=Number(threshold.value));visibleNodes=nodes;selectedEdge=null;draw();details();explorer?.refresh();}
  threshold.onchange=update;threshold.oninput=()=>{if(Number(threshold.value)>0)update();};
  allButton.onclick=()=>{const wasLocal=local;local=false;focus=null;selectedEdge=null;hover=null;if(wasLocal)draw();else highlight();details();explorer?.refresh();};
  focusButton.onclick=()=>{if(!focus)focus=nodes.slice().sort((a,b)=>b.count-a.count)[0]?.id||null;if(!focus)return;local=true;selectedEdge=null;draw();details();explorer?.refresh();};fit.onclick=()=>window.wordCooccurrence?.setStep(3);
  function zoomBy(factor){const w=Math.max(base.w*.15,Math.min(base.w*4,camera.w*factor)),ratio=w/camera.w;camera={x:camera.x+(camera.w-w)/2,y:camera.y+(camera.h-camera.h*ratio)/2,w,h:camera.h*ratio};applyCamera();}
  minus.onclick=()=>zoomBy(1.25);plus.onclick=()=>zoomBy(.8);
  svg.addEventListener('wheel',e=>{e.preventDefault();zoomBy(Math.exp(Math.max(-.25,Math.min(.25,e.deltaY*.001))));},{passive:false});
  svg.addEventListener('pointerdown',e=>{if(e.button!==0||e.target.closest('.wc-chord-node,.wc-chord-ribbon,.wc-chord-label'))return;drag={x:e.clientX,y:e.clientY,camera:{...camera},moved:false};svg.setPointerCapture(e.pointerId);});
  svg.addEventListener('pointermove',e=>{if(!drag)return;const dx=e.clientX-drag.x,dy=e.clientY-drag.y;if(Math.hypot(dx,dy)>4)drag.moved=true;if(!drag.moved)return;suppress=true;const r=svg.getBoundingClientRect(),scale=Math.min(r.width/drag.camera.w,r.height/drag.camera.h);camera={...drag.camera,x:drag.camera.x-dx/scale,y:drag.camera.y-dy/scale};applyCamera();});
  const end=()=>{drag=null;setTimeout(()=>suppress=false,0);};svg.addEventListener('pointerup',end);svg.addEventListener('pointercancel',end);svg.addEventListener('lostpointercapture',end);
  search.oninput=()=>{results.replaceChildren();const q=search.value.trim().toLowerCase();results.hidden=!q;if(!q)return;for(const n of nodes.filter(n=>String(n.label||n.id).toLowerCase().includes(q))){const b=button(n.label||n.id);b.onclick=()=>{if(focus===n.id&&!selectedEdge){highlight();details();}else selectNode(n.id);search.value='';results.hidden=true;};results.append(b);}if(!results.childElementCount)results.append(el('p','wn-muted','没有匹配的词语。'));};
  search.onkeydown=e=>{if(e.key==='Escape')results.hidden=true;if(e.key==='Enter'){e.preventDefault();results.querySelector('button')?.click();}};
  document.addEventListener('pointerdown',e=>{if(!searchWrap.contains(e.target))results.hidden=true;},{signal:controller.signal});
  exportButton.onclick=()=>{
   if(!chart)return;exportButton.disabled=true;
   const clone=svg.cloneNode(true),box={...chart.box};box.y-=24;box.h+=82;clone.setAttribute('xmlns',ns);clone.setAttribute('viewBox',[box.x,box.y,box.w,box.h].join(' '));clone.setAttribute('width','1800');clone.setAttribute('height',String(Math.round(1800*box.h/box.w)));
   clone.querySelectorAll('[tabindex]').forEach(n=>n.removeAttribute('tabindex'));
   clone.append(shape('text',{x:0,y:box.y+22,'text-anchor':'middle',fill:'#24434c','font-size':18,'font-family':'Microsoft YaHei, sans-serif'},'词语共现和弦图 · 至少 '+threshold.value+' 块共现'));
   clone.append(shape('text',{x:0,y:box.y+box.h-18,'text-anchor':'middle',fill:'#71888e','font-size':12},'无方向关系；带宽为共现块数；外圈为共现权重合计，不是词语自身出现次数。'));
   const url=URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(clone)],{type:'image/svg+xml;charset=utf-8'})),image=new Image();
   const fail=()=>{URL.revokeObjectURL(url);exportButton.disabled=false;if(typeof toast==='function')toast('图片导出失败，请重试');};
   image.onload=()=>{try{const ratio=Math.min(1800/box.w,12000/box.h),canvas=document.createElement('canvas');canvas.width=Math.max(1,Math.round(box.w*ratio));canvas.height=Math.max(1,Math.round(box.h*ratio));const c=canvas.getContext('2d');c.fillStyle='white';c.fillRect(0,0,canvas.width,canvas.height);c.drawImage(image,0,0,canvas.width,canvas.height);canvas.toBlob(blob=>{exportButton.disabled=false;if(!blob){fail();return;}const a=el('a'),download=URL.createObjectURL(blob);a.href=download;a.download='词语共现和弦图.png';a.click();setTimeout(()=>URL.revokeObjectURL(download),1000);},'image/png');URL.revokeObjectURL(url);}catch{fail();}};
   image.onerror=fail;image.src=url;
  };
  let lastSize='';const sizing=new ResizeObserver(()=>{if(disposed||layout.hidden)return;const r=svg.getBoundingClientRect(),size=Math.round(r.width)+':'+Math.round(r.height);if(!r.width||!r.height||size===lastSize)return;lastSize=size;cancelAnimationFrame(resizeFrame);resizeFrame=requestAnimationFrame(()=>{if(!disposed)fitCamera();});});sizing.observe(svg);
  update();
  if(scope.mountWordExplorer){explorer=scope.mountWordExplorer({initialView:'network',page,heading,bar,layout,networkViews:views,fit,exportButton,getState:()=>({nodes,visible,visibleNodes,focus,selectedEdge,networkCountText:countText()}),selectNode,selectEdge,showSource,draft,stopMotion:()=>{}});explorer.start();}
  return()=>{disposed=true;controller.abort();sizing.disconnect();cancelAnimationFrame(resizeFrame);explorer?.dispose();bar.remove();page.remove();};
 };
})(typeof window!=='undefined'?window:null);

