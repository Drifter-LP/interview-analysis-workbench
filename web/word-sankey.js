/* Display-only Sankey-style layout for undirected co-occurrence pairs. */
(function(scope){
 'use strict';
 function layoutPairs(edges, labels=new Map()){
  const order=(a,b)=>String(labels.get(a)||a).localeCompare(String(labels.get(b)||b),'zh-CN')||String(a).localeCompare(String(b));
  const pairs=edges.map(edge=>{const [left,right]=order(edge.source,edge.target)<0?[edge.source,edge.target]:[edge.target,edge.source];return{edge,left,right,value:edge.count};});
  let left=[...new Set(pairs.map(p=>p.left))].sort(order),right=[...new Set(pairs.map(p=>p.right))].sort(order);
  function reorder(ids,other,side){
   const ranks=new Map(other.map((id,i)=>[id,i]));
   return ids.slice().sort((a,b)=>{
    const center=id=>{let n=0,d=0;for(const p of pairs)if(p[side]===id){n+=ranks.get(p[side==='left'?'right':'left'])*p.value;d+=p.value;}return n/Math.max(1,d);};
    return center(a)-center(b)||order(a,b);
   });
  }
  for(let i=0;i<6;i++){left=reorder(left,right,'left');right=reorder(right,left,'right');}
  const h=Math.max(700,Math.max(left.length,right.length)*36+120),total=pairs.reduce((s,p)=>s+p.value,0);
  const scale=(h-120-Math.max(0,Math.max(left.length,right.length)-1)*22)/Math.max(1,total),nodes=[];
  for(const [side,ids,x]of [['left',left,260],['right',right,840]]){
   const sizes=ids.map(id=>Math.max(8,pairs.filter(p=>p[side]===id).reduce((s,p)=>s+p.value,0)*scale));
   let y=(h-sizes.reduce((a,b)=>a+b,0)-Math.max(0,ids.length-1)*22)/2;
   ids.forEach((id,i)=>{nodes.push({id,side,x,y,h:sizes[i]});y+=sizes[i]+22;});
  }
  const lookup=new Map(nodes.map(n=>[n.side+':'+n.id,n])),offsets=new Map(nodes.map(n=>[n.side+':'+n.id,0]));
  pairs.sort((a,b)=>left.indexOf(a.left)-left.indexOf(b.left)||right.indexOf(a.right)-right.indexOf(b.right));
  // Stack each end independently in the opposite column's order.
  for(const side of ['left','right']){
   const opposite=side==='left'?'right':'left',rank=side==='left'?right:left;
   for(const p of pairs.slice().sort((a,b)=>rank.indexOf(a[opposite])-rank.indexOf(b[opposite]))){
    const key=side+':'+p[side],node=lookup.get(key),width=p.value*scale;
    p[side+'Y']=node.y+offsets.get(key)+width/2;offsets.set(key,offsets.get(key)+width);p.width=width;
   }
  }
  return{nodes,pairs,width:1100,height:h};
 }
 if(typeof module!=='undefined')module.exports={layoutPairs};
 if(!scope?.document)return;
 scope.renderWordNetwork=function({root,heading,draft,showSource}){
  const ns='http://www.w3.org/2000/svg',nodes=draft.graph?.nodes||[],ids=new Set(nodes.map(n=>n.id));
  const edges=(draft.graph?.edges||[]).filter(e=>ids.has(e.source)&&ids.has(e.target)&&e.source!==e.target&&Number.isFinite(e.count)&&e.count>0);
  const labels=new Map(nodes.map(n=>[n.id,n.label||n.id])),colors=['#58b6ac','#87aed0','#d7b271','#af9bc9','#9fb979'];
  const el=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n;};
  const svgEl=(tag,attrs,text)=>{const n=document.createElementNS(ns,tag);for(const[k,v]of Object.entries(attrs||{}))n.setAttribute(k,v);if(text!==undefined)n.textContent=text;return n;};
  const btn=text=>{const b=el('button','',text);b.type='button';return b;};
  let visible=[],visibleNodes=[],focus=null,selectedEdge=null,local=false,explorer=null,camera,base,drag=null,suppress=false;
  const page=el('section','wn-workspace ws-workspace'),bar=el('div','wn-toolbar'),searchWrap=el('div','wn-search'),search=el('input'),results=el('div','wn-results');search.type='search';search.placeholder='搜索词语';search.setAttribute('aria-label','搜索共现词语');results.hidden=true;searchWrap.append(search,results);
  const views=el('div','wn-views'),globalButton=btn('全部词对'),localButton=btn('聚焦词语');views.append(globalButton,localButton);
  const thresholdLabel=el('label','wn-threshold','至少'),threshold=el('input');threshold.type='number';threshold.min='1';threshold.step='1';threshold.value='5';threshold.setAttribute('aria-label','最少共现块数');thresholdLabel.append(threshold,el('span','','块共现'));
  const counts=el('span','wn-counts'),fit=btn('适应画布'),exportButton=btn('导出图片');bar.append(searchWrap,views,thresholdLabel,counts,fit,exportButton);heading.classList.add('wn-heading');heading.append(bar);root.append(page);
  const layout=el('div','wn-layout'),stage=el('div','wn-stage'),svg=svgEl('svg',{class:'wn-canvas',role:'group','aria-label':'词语共现桑基图：无方向词对'}),aside=el('aside','wn-details'),head=el('header'),title=el('strong','','词语共现'),content=el('div','wn-detail-content');head.append(title);aside.append(head,content);stage.append(svg);layout.append(stage,aside);page.append(layout);
  const zoom=el('div','wn-zoom'),minus=btn('−'),plus=btn('+'),percent=el('output','','100%');minus.setAttribute('aria-label','缩小共现图');plus.setAttribute('aria-label','放大共现图');zoom.append(minus,percent,plus);stage.append(zoom);
  page.append(el('p','wn-note','无方向共现：左右仅为排版，同一词可能出现在两侧；每个词对只画一次。带宽表示共现块数，不代表流向、因果或观点一致。节点高度为所连接词对的共现次数合计，不是独立文本块数。点击连带查看原文；拖动画布移动，滚轮缩放。'));
  const nodeColor=id=>colors[Math.max(0,nodes.find(n=>n.id===id)?.group||0)%colors.length];
  function activate(n,fn){n.addEventListener('click',()=>{if(!suppress)fn();});n.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();fn();}});}
  function applyCamera(){svg.setAttribute('viewBox',`${camera.x} ${camera.y} ${camera.w} ${camera.h}`);percent.textContent=Math.round(base.w/camera.w*100)+'%';}
  function selectNode(id){focus=id;selectedEdge=null;draw();details();explorer?.refresh();}
  function selectEdge(edge){selectedEdge=edge;focus=focus&&[edge.source,edge.target].includes(focus)?focus:edge.source;draw();details();explorer?.refresh();}
  function details(){
   content.replaceChildren();
   if(selectedEdge){
    const e=selectedEdge;title.textContent=(labels.get(e.source)||e.source)+' — '+(labels.get(e.target)||e.target);
    const back=btn('← 返回词语');back.onclick=()=>{selectedEdge=null;draw();details();explorer?.refresh();};
    content.append(back,el('p','wn-evidence-count',e.count+' 个文本块 · '+e.interviews+' 篇访谈'),el('p','wn-muted','共同出现，不表示因果或观点一致。'));
    let valid=0;
    for(const ref of e.evidence||[]){
     const t=draft.interviews?.find(t=>t.id===ref.interview_id),b=t?.blocks.find(b=>b.id===ref.block_id);if(!t||!b)continue;
     const card=el('section','wn-evidence'),jump=btn('查看完整原文 →');jump.className='wn-source';jump.onclick=()=>showSource(t,b);
     card.append(el('strong','',t.name),el('p','',t.text.slice(b.start,b.end)),jump);content.append(card);valid++;
    }
    if(!valid)content.append(el('p','wn-muted','原文引用暂不可用，请核对当前草稿版本。'));
   }else if(focus){
    const n=nodes.find(n=>n.id===focus);title.textContent=labels.get(focus)||focus;
    content.append(el('p','wn-muted',`出现于 ${n?.count||0} 个文本块 · ${n?.interviews||0} 篇访谈`));
    for(const e of visible.filter(e=>[e.source,e.target].includes(focus)).sort((a,b)=>b.count-a.count)){
     const other=e.source===focus?e.target:e.source,b=btn((labels.get(other)||other)+' · '+e.count+' 块');b.className='wn-relation';b.onclick=()=>selectEdge(e);content.append(b);
    }
   }else{title.textContent='共现桑基图';content.append(el('p','wn-muted','点击词语查看关联，点击带状连线查看原文。左右列不是阶段或层级，带宽表示同一文本块中共同出现的次数。'));}
  }
  function draw(reset=false){
   const scene=local&&focus?visible.filter(e=>[e.source,e.target].includes(focus)):visible;
   const chart=layoutPairs(scene,labels);svg.replaceChildren();
   if(reset||!base){base={x:0,y:0,w:chart.width,h:chart.height};camera={...base};}
   globalButton.setAttribute('aria-pressed',String(!local));localButton.setAttribute('aria-pressed',String(local));
   const banner=svgEl('text',{x:550,y:24,'text-anchor':'middle',fill:'#6e858c','font-size':13},'词语共现 · 无方向关系');svg.append(banner);
   if(!scene.length)svg.append(svgEl('text',{x:550,y:300,'text-anchor':'middle',fill:'#74888e'},'当前阈值下没有共现词对，请降低阈值。'));
   for(const p of chart.pairs){
    const related=!focus||[p.edge.source,p.edge.target].includes(focus),selected=selectedEdge===p.edge;
    const group=svgEl('g',{class:'ws-link',tabindex:0,role:'button','aria-label':`查看共现：${labels.get(p.left)}与${labels.get(p.right)}，${p.value}块`});
    const d=`M274 ${p.leftY} C480 ${p.leftY},620 ${p.rightY},826 ${p.rightY}`;
    group.append(svgEl('path',{d,fill:'none',stroke:nodeColor(p.left),'stroke-width':p.width,opacity:selected?'.85':related?'.46':'.10'}),svgEl('path',{d,fill:'none',stroke:'transparent','stroke-width':Math.max(12,p.width),'pointer-events':'stroke'}),svgEl('title',{},`${labels.get(p.left)} — ${labels.get(p.right)}：${p.value} 块 · ${p.edge.interviews} 篇访谈`));
    activate(group,()=>selectEdge(p.edge));svg.append(group);
   }
   for(const n of chart.nodes){
    const selected=n.id===focus,g=svgEl('g',{class:'ws-node',tabindex:0,role:'button','aria-label':'查看词语：'+labels.get(n.id)}),left=n.side==='left',label=labels.get(n.id)||n.id;
    g.append(svgEl('rect',{x:left?0:826,y:n.y+n.h/2-Math.max(20,n.h)/2,width:274,height:Math.max(20,n.h),fill:'transparent','pointer-events':'all'}),svgEl('rect',{x:n.x-14,y:n.y,width:28,height:n.h,rx:4,fill:selected?'#008f89':nodeColor(n.id)}),svgEl('text',{x:left?n.x-24:n.x+24,y:n.y+n.h/2+5,'text-anchor':left?'end':'start','font-size':15,fill:selected?'#008f89':'#24434c','font-weight':selected?'700':'400'},label));
    activate(g,()=>selectNode(n.id));svg.append(g);
   }
   counts.textContent=visibleNodes.length+' 个词 · '+visible.length+' 条共现';applyCamera();
  }
  function update(){
   const n=Math.max(1,Math.floor(Number(threshold.value)||1));threshold.value=n;visible=edges.filter(e=>e.count>=n);
   const endpoints=new Set(visible.flatMap(e=>[e.source,e.target]));visibleNodes=nodes.filter(n=>endpoints.has(n.id));
   if(focus&&!endpoints.has(focus))focus=null;selectedEdge=null;draw(true);details();explorer?.refresh();
  }
  threshold.onchange=update;threshold.oninput=()=>{if(Number(threshold.value)>0)update();};
  globalButton.onclick=()=>{local=false;draw(true);};localButton.onclick=()=>{focus=focus||visibleNodes.slice().sort((a,b)=>b.count-a.count)[0]?.id||null;local=true;draw(true);details();explorer?.refresh();};fit.onclick=()=>draw(true);
  function zoomBy(factor){const w=Math.max(base.w*.12,Math.min(base.w*5,camera.w*factor)),ratio=w/camera.w;camera={x:camera.x+(camera.w-w)/2,y:camera.y+(camera.h-camera.h*ratio)/2,w,h:camera.h*ratio};applyCamera();}
  minus.onclick=()=>zoomBy(1.25);plus.onclick=()=>zoomBy(.8);
  svg.addEventListener('wheel',e=>{e.preventDefault();zoomBy(Math.exp(Math.max(-.25,Math.min(.25,e.deltaY*.001))));},{passive:false});
  svg.addEventListener('pointerdown',e=>{if(e.button!==0||e.target.closest('.ws-link,.ws-node'))return;drag={x:e.clientX,y:e.clientY,camera:{...camera},moved:false};svg.setPointerCapture(e.pointerId);});
  svg.addEventListener('pointermove',e=>{if(!drag)return;const dx=e.clientX-drag.x,dy=e.clientY-drag.y;if(Math.hypot(dx,dy)>4)drag.moved=true;if(!drag.moved)return;suppress=true;const r=svg.getBoundingClientRect(),scale=Math.min(r.width/drag.camera.w,r.height/drag.camera.h);camera={...drag.camera,x:drag.camera.x-dx/scale,y:drag.camera.y-dy/scale};applyCamera();});
  const end=()=>{drag=null;setTimeout(()=>suppress=false,0);};svg.addEventListener('pointerup',end);svg.addEventListener('pointercancel',end);svg.addEventListener('lostpointercapture',end);
  search.oninput=()=>{results.replaceChildren();const q=search.value.trim().toLowerCase();results.hidden=!q;if(!q)return;
   for(const n of visibleNodes.filter(n=>(n.label||n.id).toLowerCase().includes(q))){const b=btn(n.label||n.id);b.onclick=()=>{selectNode(n.id);search.value='';results.hidden=true;};results.append(b);}
   if(!results.childElementCount)results.append(el('p','wn-muted','当前阈值下没有匹配词语。'));
  };
  search.onkeydown=e=>{if(e.key==='Escape')results.hidden=true;if(e.key==='Enter'){e.preventDefault();results.querySelector('button')?.click();}};
  exportButton.onclick=()=>{
   const clone=svg.cloneNode(true);clone.setAttribute('xmlns',ns);clone.setAttribute('viewBox',`0 0 ${base.w} ${base.h}`);clone.setAttribute('width','1600');clone.setAttribute('height',String(Math.round(1600*base.h/base.w)));
   clone.append(svgEl('text',{x:550,y:base.h-12,'text-anchor':'middle',fill:'#71888e','font-size':12},'无方向共现；左右仅排版，带宽为共现块数，不表示因果。'));
   const url=URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(clone)],{type:'image/svg+xml;charset=utf-8'})),image=new Image();
   image.onload=()=>{const canvas=document.createElement('canvas');canvas.width=1600;canvas.height=Math.min(16000,Math.round(1600*base.h/base.w));const c=canvas.getContext('2d');c.fillStyle='white';c.fillRect(0,0,canvas.width,canvas.height);c.drawImage(image,0,0,canvas.width,canvas.height);canvas.toBlob(blob=>{if(blob){const a=el('a'),u=URL.createObjectURL(blob);a.href=u;a.download='词语共现桑基图.png';a.click();setTimeout(()=>URL.revokeObjectURL(u),1000);}},'image/png');URL.revokeObjectURL(url);};
   image.onerror=()=>{URL.revokeObjectURL(url);if(typeof toast==='function')toast('图片导出失败，请重试');};image.src=url;
  };
  update();
  if(scope.mountWordExplorer){explorer=scope.mountWordExplorer({initialView:'network',page,heading,bar,layout,networkViews:views,fit,exportButton,getState:()=>({nodes,visible,visibleNodes,focus,selectedEdge}),selectNode,selectEdge,showSource,draft,stopMotion:()=>{}});explorer.start();}
  return()=>{explorer?.dispose();bar.remove();page.remove();};
 };
})(typeof window!=='undefined'?window:null);

