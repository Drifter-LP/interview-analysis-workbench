/* Display-only network workspace. Counts and source bindings remain untouched. */
window.renderWordNetwork=function({root,heading,draft,showSource}){
 const graph=draft.graph||{nodes:[],edges:[]},ns='http://www.w3.org/2000/svg';
 const html=(tag,cls,txt)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(txt!==undefined)n.textContent=txt;return n;};
 const shape=(tag,attrs={},txt)=>{const n=document.createElementNS(ns,tag);for(const [k,v]of Object.entries(attrs))n.setAttribute(k,v);if(txt!==undefined)n.textContent=txt;return n;};
 const button=(txt,cls='')=>{const b=html('button',cls,txt);b.type='button';return b;};
 const palette=[['#eedb79','#88700f','#f8f1cf'],['#e6b383','#a66b37','#f2e3d5'],['#8cbddd','#437da7','#deebf4'],['#b8a9d5','#78679d','#ebe5f3'],['#b9cb85','#718640','#e8efd8'],['#dcaaaa','#a16969','#f1e2e2']];
 const geometry=window.networkGeometry;
 let topology={groups:[],membership:new Map(),degree:new Map(),core:new Set(),bridge:new Set()},regionState=new Map(),regionTargets=[],regionComputed=0;
 const color=n=>topology.membership.has(n.id)?palette[topology.membership.get(n.id)%palette.length]:['#b9c5ce','#617788','#edf1f4'];
 const nodes=graph.nodes||[],ids=new Set(nodes.map(n=>n.id));
 let edges=(graph.edges||[]).filter(e=>ids.has(e.source)&&ids.has(e.target)&&e.source!==e.target),visible=[],visibleNodes=[],focus=null,selectedEdge=null,view='global',positions={},camera={x:0,y:0,w:1100,h:700},base={...camera},drag=null;
 const page=html('section','wn-workspace');root.append(page);
 const bar=html('div','wn-toolbar'),searchWrap=html('div','wn-search'),search=html('input'),results=html('div','wn-results');search.type='search';search.placeholder='搜索词语';search.setAttribute('aria-label','搜索共现词语');results.hidden=true;searchWrap.append(search,results);
 const views=html('div','wn-views'),global=button('全局总览'),local=button('局部聚焦');views.append(global,local);views.setAttribute('role','group');views.setAttribute('aria-label','共现图视图');
 const thresholdLabel=html('label','wn-threshold','至少'),threshold=html('input');threshold.type='number';threshold.min='1';threshold.step='1';threshold.value='5';threshold.setAttribute('aria-label','最少共现块数');thresholdLabel.append(threshold,html('span','','块共现'));
 const counts=html('span','wn-counts'),fit=button('适应画布'),exportButton=button('导出图片');bar.append(searchWrap,views,thresholdLabel,counts,fit,exportButton);if(heading){heading.classList.add('wn-heading');heading.append(bar);}else page.append(bar);
 const layout=html('div','wn-layout'),stage=html('div','wn-stage'),svg=shape('svg',{class:'wn-canvas',role:'group','aria-label':'词语共现网络',preserveAspectRatio:'xMidYMid meet'}),empty=html('div','wn-empty','当前阈值下没有共现连线，请降低阈值。'),aside=html('aside','wn-details');stage.append(svg,empty);layout.append(stage,aside);page.append(layout);
 const detailHead=html('header'),detailTitle=html('strong','','词语共现'),collapse=button('›');collapse.setAttribute('aria-label','收起共现说明');detailHead.append(detailTitle,collapse);const content=html('div','wn-detail-content');aside.append(detailHead,content);
 const expand=button('‹','wn-expand');expand.setAttribute('aria-label','展开共现说明');expand.hidden=true;stage.append(expand);
 const zoom=html('div','wn-zoom'),minus=button('−'),plus=button('+'),percentage=html('output','','100%');minus.setAttribute('aria-label','缩小共现图');plus.setAttribute('aria-label','放大共现图');zoom.append(minus,percentage,plus);stage.append(zoom);
 const legend=html('div','wn-legend');stage.prepend(legend);
 page.append(html('p','wn-note','拖动画布移动 · 滚轮缩放 · 点击词语聚焦，点击连线查看原文。仅显示达到阈值的连线及其端点；线宽表示共现块数，不表示因果。'));
 const controller=new AbortController();let disposed=false,explorer=null;
 const adjacent=id=>new Set(visible.filter(e=>e.source===id||e.target===id).map(e=>e.source===id?e.target:e.source));
 function bounds(points){const ps=Object.values(points);if(!ps.length)return{x:0,y:0,w:1100,h:700};const xs=ps.map(p=>p.x),ys=ps.map(p=>p.y);return{x:Math.min(...xs)-140,y:Math.min(...ys)-110,w:Math.max(440,Math.max(...xs)-Math.min(...xs)+280),h:Math.max(340,Math.max(...ys)-Math.min(...ys)+220)};}
 let stageRatio=1.4;
 function currentRatio(){const r=svg.getBoundingClientRect();if(r.width>0&&r.height>0)stageRatio=r.width/r.height;return stageRatio;}
 function forceLayout(){return geometry.layout(visibleNodes,visible,currentRatio(),topology);}
 let globalPositions={},elastic=null,elasticFrame=0,elasticLast=0,elasticStart=0,quietFrames=0,centerMotion=null,releasedPin=null,savedGlobalCamera=null,savedGlobalBase=null,suppressClick=false;
 function applyCamera(){svg.setAttribute('viewBox',`${camera.x} ${camera.y} ${camera.w} ${camera.h}`);percentage.textContent=Math.round(base.w/camera.w*100)+'%';}
 function fitCamera(){stopElastic();base=bounds(positions);const ratio=currentRatio();if(base.w/base.h<ratio){const w=base.h*ratio;base.x-=(w-base.w)/2;base.w=w;}else{const h=base.w/ratio;base.y-=(h-base.h)/2;base.h=h;}camera={...base};draw();}
 function activate(element,fn){element.addEventListener('click',e=>{if(!suppressClick)fn(e);});element.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();fn(e);}});}
 function stopElastic(){cancelAnimationFrame(elasticFrame);elasticFrame=0;elasticLast=0;centerMotion=null;releasedPin=null;}
 function ensureElastic(){if(!elastic){elastic=geometry.createElasticNetwork(globalPositions,visible);elastic.groups=topology.groups;elastic.bridges=topology.bridge;for(const spring of elastic.springs)if(topology.membership.has(spring.a)&&topology.membership.get(spring.a)===topology.membership.get(spring.b))spring.rest=Math.min(spring.rest,230);}return elastic;}
 function updateMotionDrawing(){
  svg.querySelectorAll('.wn-node').forEach(g=>{const p=positions[g.dataset.word];if(p)g.setAttribute('transform',`translate(${p.x} ${p.y})`);});
  svg.querySelectorAll('.wn-edge').forEach(g=>{const route=edgeRoute({source:g.dataset.source,target:g.dataset.target});if(!route)return;g.querySelectorAll('path').forEach(path=>path.setAttribute('d',route.d));const badge=g.querySelector('.wn-edge-badge'),label=g.querySelector('.wn-edge-count');if(badge){const w=Number(badge.getAttribute('width')),h=Number(badge.getAttribute('height'));badge.setAttribute('x',route.x-w/2);badge.setAttribute('y',route.y-h/2);}if(label){label.setAttribute('x',route.x);label.setAttribute('y',route.y+Number(label.dataset.offset));}});
  placeLabels();updateRegions();
 }
 function startElastic(){ensureElastic();quietFrames=0;elasticStart=performance.now();if(elasticFrame)return;elasticLast=0;elasticFrame=requestAnimationFrame(elasticTick);}
 function elasticTick(now){
  elasticFrame=0;if(disposed||view!=='global'||!elastic)return;const dt=elasticLast?Math.min(1.5,(now-elasticLast)/16.667):1;elasticLast=now;let pinned=null;
  if(centerMotion){const m=centerMotion,t=Math.min(1,(now-m.began)/650),ease=(1-Math.cos(Math.PI*t))/2;pinned={id:m.id,x:m.from.x+(m.to.x-m.from.x)*ease,y:m.from.y+(m.to.y-m.from.y)*ease};}
  if(drag?.id&&drag.moved)pinned={id:drag.id,...drag.at};else if(releasedPin)pinned=releasedPin;
  const speed=geometry.stepElasticNetwork(elastic,pinned,dt);const r=svg.getBoundingClientRect(),unit=Math.max(camera.w/Math.max(1,r.width),camera.h/Math.max(1,r.height));const particles=Object.values(elastic.particles);for(let i=0;i<particles.length;i++)for(let j=i+1;j<particles.length;j++){const a=particles[i],b=particles[j],dx=b.x-a.x,dy=b.y-a.y,d=Math.hypot(dx,dy)||1,min=76*unit;if(d<min){const shift=Math.min(4*unit,(min-d)*.12),ux=dx/d,uy=dy/d;if(a!==elastic.particles[pinned?.id]){a.x-=ux*shift;a.y-=uy*shift;}if(b!==elastic.particles[pinned?.id]){b.x+=ux*shift;b.y+=uy*shift;}}}for(const [id,p]of Object.entries(elastic.particles)){globalPositions[id]={x:p.x,y:p.y};positions[id]=globalPositions[id];}updateMotionDrawing();
  const moving=centerMotion&&now-centerMotion.began<650;if(!drag&&!moving&&speed<.08)quietFrames++;else quietFrames=0;
  if(drag||moving||(quietFrames<20&&now-elasticStart<6500))elasticFrame=requestAnimationFrame(elasticTick);else{elasticLast=0;for(const p of Object.values(elastic.particles))p.vx=p.vy=0;draw();}
 }
 function centerOnNode(id){if(view!=='global'||layout.hidden||!positions[id])return;ensureElastic();const to={x:camera.x+camera.w/2,y:camera.y+camera.h/2},from={...positions[id]};if(Math.hypot(from.x-to.x,from.y-to.y)<.5)return;releasedPin=null;centerMotion={id,from,to,began:performance.now()};startElastic();}
 function selectNode(id){stopElastic();focus=id;selectedEdge=null;if(view==='local')localPositions();draw();showDetails();}
 function selectEdge(e){selectedEdge=e;focus=focus&&[e.source,e.target].includes(focus)?focus:e.source;if(view==='local')localPositions();draw();showDetails();}
 function localPositions(){stopElastic();const weights=new Map(visible.filter(e=>e.source===focus||e.target===focus).map(e=>[e.source===focus?e.target:e.source,e.count])),near=visibleNodes.filter(n=>weights.has(n.id)).sort((a,b)=>weights.get(b.id)-weights.get(a.id)||a.label.localeCompare(b.label)),height=Math.max(660,Math.ceil(near.length/2)*96+100),p={[focus]:{x:550,y:height/2}};near.forEach((n,i)=>{const side=i%2,row=Math.floor(i/2),num=side?Math.floor(near.length/2):Math.ceil(near.length/2);p[n.id]={x:side?930:170,y:(row+1)*height/(num+1)};});positions=p;base={x:0,y:0,w:1100,h:height};camera={...base};}
 function setView(v){if(v===view)return;stopElastic();selectedEdge=null;if(v==='local'){savedGlobalCamera={...camera};savedGlobalBase={...base};view=v;focus=focus||visibleNodes.slice().sort((a,b)=>adjacent(b.id).size-adjacent(a.id).size)[0]?.id;if(focus)localPositions();}else{view=v;positions=globalPositions;camera=savedGlobalCamera?{...savedGlobalCamera}:{...camera};base=savedGlobalBase?{...savedGlobalBase}:bounds(globalPositions);}draw();showDetails();}
 function updateRegions(){
  if(view!=='global')return;const now=performance.now();if(now-regionComputed>65||!regionTargets.length){regionTargets=geometry.groupRegions(topology,positions,regionState);regionComputed=now;}
  const r=svg.getBoundingClientRect(),unit=Math.max(1,base.w/Math.max(1,r.width),base.h/Math.max(1,r.height)),labels=[];
  for(const target of regionTargets){let state=regionState.get(target.index);if(!state){state={...target};regionState.set(target.index,state);}for(const key of ['x','y','rx','ry'])state[key]+=(target[key]-state[key])*.22;
   const g=svg.querySelector(`[data-region="${target.index}"]`);if(!g)continue;const ellipse=g.querySelector('ellipse');for(const [key,value]of Object.entries({cx:state.x,cy:state.y,rx:state.rx,ry:state.ry}))ellipse.setAttribute(key,value);
   if(target.body.length===2){const [a,b]=target.body,angle=Math.atan2(b.y-a.y,b.x-a.x)*180/Math.PI;ellipse.setAttribute('rx',Math.min(300,Math.hypot(b.x-a.x,b.y-a.y)/2+60));ellipse.setAttribute('ry',55);ellipse.setAttribute('transform',`rotate(${angle} ${state.x} ${state.y})`);}else ellipse.removeAttribute('transform');
   const label=svg.querySelector(`[data-region-label="${target.index}"]`);if(!label)continue;const text=`词群 ${target.index+1} · ${target.count} 个词`;label.textContent=text;const width=Array.from(text).length*12*unit;let x=state.x-state.rx,y=state.y-state.ry-10*unit;
   for(let pass=0;pass<6;pass++){const collision=Object.values(positions).some(p=>Math.abs(p.y-y)<36*unit&&p.x>x-50*unit&&p.x<x+width+40*unit)||labels.some(old=>Math.abs(old.y-y)<24*unit&&x<old.x+old.w&&x+width>old.x);if(!collision)break;y-=24*unit;}
   x=Math.max(camera.x+10*unit,Math.min(x,camera.x+camera.w-width-10*unit));y=Math.max(camera.y+18*unit,Math.min(y,camera.y+camera.h-48*unit));labels.push({x,y,w:width});state.labelX=state.labelX===undefined?x:state.labelX+(x-state.labelX)*.22;state.labelY=state.labelY===undefined?y:state.labelY+(y-state.labelY)*.22;label.setAttribute('x',state.labelX);label.setAttribute('y',state.labelY);label.style.fontSize=12*unit+'px';
  }
 }
 function placeLabels(){
  if(view!=='global')return;const r=svg.getBoundingClientRect(),u=Math.max(1,base.w/Math.max(1,r.width),base.h/Math.max(1,r.height)),boxes=[];
  const crosses=(a,b,box)=>{for(let t=0;t<=1;t+=.05){const x=a.x+(b.x-a.x)*t,y=a.y+(b.y-a.y)*t;if(x>box.x&&x<box.x+box.w&&y>box.y&&y<box.y+box.h)return true;}return false;};
  const groups=[...svg.querySelectorAll('.wn-node')].filter(g=>!g.classList.contains('distant')).sort((a,b)=>Number(b.dataset.word===focus)-Number(a.dataset.word===focus));
  for(const g of groups){const p=positions[g.dataset.word],bg=g.querySelector('.wn-label-bg'),text=g.querySelector('.wn-node-label');if(!bg||!p)continue;const w=(Array.from(text.textContent).length*13+10)*u,h=24*u,options=[{x:18*u,y:-h/2},{x:-w-18*u,y:-h/2},{x:-w/2,y:-h-18*u},{x:-w/2,y:18*u},{x:16*u,y:-h-10*u},{x:-w-16*u,y:-h-10*u},{x:16*u,y:10*u},{x:-w-16*u,y:10*u}];let best=null,score=Infinity;
   for(const [i,o]of options.entries()){const box={x:p.x+o.x,y:p.y+o.y,w,h};let s=i*2;for(const old of boxes)if(box.x<old.x+old.w+5*u&&box.x+w+5*u>old.x&&box.y<old.y+old.h+4*u&&box.y+h+4*u>old.y)s+=10000;for(const [id,q]of Object.entries(positions))if(id!==g.dataset.word&&q.x>box.x-13*u&&q.x<box.x+w+13*u&&q.y>box.y-13*u&&q.y<box.y+h+13*u)s+=10000;for(const e of visible)if(crosses(positions[e.source],positions[e.target],box))s+=500;if(box.x<camera.x+8*u||box.x+w>camera.x+camera.w-8*u||box.y<camera.y+10*u||box.y+h>camera.y+camera.h-50*u)s+=20000;if(s<score){score=s;best=o;}}
   boxes.push({x:p.x+best.x,y:p.y+best.y,w,h});bg.setAttribute('x',best.x);bg.setAttribute('y',best.y);bg.setAttribute('width',w);bg.setAttribute('height',h);text.setAttribute('x',best.x+w/2);text.setAttribute('y',best.y+17*u);
  }
 }
 function edgeRoute(e){const a=positions[e.source],b=positions[e.target];if(!a||!b)return null;if(view==='local')return geometry.localEdgeRoute(a,b);return{d:`M${a.x} ${a.y} L${b.x} ${b.y}`,x:(a.x+b.x)/2,y:(a.y+b.y)/2};}
 function draw(){
  if(layout.hidden)return;
  svg.replaceChildren();global.setAttribute('aria-pressed',String(view==='global'));local.setAttribute('aria-pressed',String(view==='local'));const near=adjacent(focus),groups=new Map(),rect=svg.getBoundingClientRect(),unit=Math.max(1,base.w/Math.max(1,rect.width),base.h/Math.max(1,rect.height));
  if(view==='global')topology.groups.forEach((ids,i)=>groups.set(i,visibleNodes.filter(n=>ids.includes(n.id))));
  legend.replaceChildren();
  for(const [group,members]of groups){if(!members.length)continue;const c=palette[group%palette.length],key=html('span','',`词群 ${group+1}`),dot=html('i');dot.style.background=c[0];key.prepend(dot);legend.append(key);}
  legend.hidden=view!=='global';
  const max=Math.max(1,...visible.map(e=>e.count));
  const sceneEdges=view==='local'?visible.filter(e=>e.source===focus||e.target===focus):visible;
  for(const e of sceneEdges){const a=positions[e.source],b=positions[e.target];if(!a||!b)continue;const selected=selectedEdge===e,close=!focus||e.source===focus||e.target===focus,group=shape('g',{class:'wn-edge'+(selected?' selected':'')+(close?' near':' distant'),'data-source':e.source,'data-target':e.target,role:'button',tabindex:0,'aria-label':`${e.source}与${e.target}：${e.count}块共现`}),route=edgeRoute(e);
   group.append(shape('path',{d:route.d,class:'wn-edge-line','stroke-width':.7+1.3*e.count/max,'vector-effect':'non-scaling-stroke'}),shape('path',{d:route.d,class:'wn-edge-hit','vector-effect':'non-scaling-stroke'}));const title=shape('title',{},`${e.source} — ${e.target}\n${e.count}块 / ${e.interviews}篇`);group.append(title);
   group.style.setProperty('--wn-edge-color',close?'#7ba5a1':'#bac8cb');
   if(selected||view==='local'){const x=route.x,y=route.y;group.append(shape('rect',{x:x-14*unit,y:y-10*unit,width:28*unit,height:20*unit,rx:6*unit,class:'wn-edge-badge'}),shape('text',{x,y:y+4*unit,'text-anchor':'middle',class:'wn-edge-count','data-offset':4*unit,style:`font-size:${11*unit}px`},String(e.count)));}
   activate(group,()=>selectEdge(e));svg.append(group);
  }
  const labelBoxes=[];
  const shown=visibleNodes.filter(n=>positions[n.id]).sort((a,b)=>Number(b.id===focus)-Number(a.id===focus));
  for(const n of shown){const p=positions[n.id],selected=n.id===focus,related=!focus||selected||near.has(n.id),c=color(n),g=shape('g',{transform:`translate(${p.x} ${p.y})`,class:'wn-node'+(selected?' focus':'')+(related?' near':' distant'),role:'button',tabindex:0,'data-word':n.id,'aria-label':'选择词语：'+n.label});g.style.setProperty('--wn-color',c[0]);g.style.setProperty('--wn-dark',c[1]);
   const structural=[];if(topology.core.has(n.id))structural.push(`结构核心：直接连接 ${topology.degree.get(n.id)} 个词语，不代表研究重要性`);if(topology.bridge.has(n.id))structural.push('桥梁词语：连接不同词群，并承担较多路径连接');const title=shape('title',{},`${n.label}\n出现于${n.count}块 / ${n.interviews}篇\n${structural.join('；')}`);g.append(title);g.dataset.core=String(topology.core.has(n.id));g.dataset.bridge=String(topology.bridge.has(n.id));
   const width=Math.max(54,Math.min(260,Array.from(n.label).length*13+20))*unit;
   if(view==='local'){g.append(shape('rect',{x:-122,y:-32,width:244,height:64,rx:selected?30:9,class:'wn-card'}),shape('text',{x:0,y:5*unit,'text-anchor':'middle',class:'wn-node-label',style:`font-size:${13*unit}px`},n.label));}
   else{
    const radius=(selected?9:7)*unit;g.append(shape('circle',{r:20*unit,class:'wn-node-hit'}));g.append(shape('circle',{r:radius,class:'wn-ball','vector-effect':'non-scaling-stroke'}));
    const options=[{x:16*unit,y:-14*unit},{x:-width-16*unit,y:-14*unit},{x:-width/2,y:18*unit},{x:-width/2,y:-46*unit}];let label=options[0],best=Infinity;
    for(const [i,o]of options.entries()){const box={x:p.x+o.x,y:p.y+o.y,w:width,h:28*unit};let score=i*10;for(const old of labelBoxes){const ox=Math.min(box.x+box.w,old.x+old.w)-Math.max(box.x,old.x),oy=Math.min(box.y+box.h,old.y+old.h)-Math.max(box.y,old.y);if(ox>0&&oy>0)score+=1000+ox*oy;}for(const other of shown){const q=positions[other.id];if(other.id!==n.id&&q.x>box.x-12*unit&&q.x<box.x+box.w+12*unit&&q.y>box.y-12*unit&&q.y<box.y+box.h+12*unit)score+=2000;}if(score<best){best=score;label=o;}}
    labelBoxes.push({x:p.x+label.x,y:p.y+label.y,w:width,h:28*unit});g.append(shape('rect',{x:label.x,y:label.y,width,height:28*unit,rx:7*unit,class:'wn-label-bg'}),shape('text',{x:label.x+width/2,y:label.y+18*unit,'text-anchor':'middle',class:'wn-node-label',style:`font-size:${13*unit}px`},n.label));
   }
   if(view==='global'&&!related){for(const label of g.querySelectorAll('.wn-label-bg,.wn-node-label')){label.setAttribute('visibility','hidden');label.setAttribute('display','none');}}
   activate(g,()=>selectNode(n.id));g.addEventListener('dblclick',()=>{focus=n.id;setView('local');});svg.append(g);
  }
  counts.textContent=`${shown.length} 个词 · ${sceneEdges.length} 条共现`;empty.hidden=sceneEdges.length>0;applyCamera();placeLabels();updateRegions();
 }
 function showDetails(){
  explorer?.refresh();
  content.replaceChildren();
  if(selectedEdge){const e=selectedEdge;detailTitle.textContent=e.source+' — '+e.target;const back=button('← 返回词语','wn-back');back.onclick=()=>{selectedEdge=null;draw();showDetails();};content.append(back,html('p','wn-evidence-count',`${e.count} 个文本块 · ${e.interviews} 篇访谈`),html('p','wn-muted','共同出现，不表示因果或观点一致。'));
   let displayed=0;for(const ref of e.evidence||[]){const t=(draft.interviews||[]).find(t=>t.id===ref.interview_id),b=t?.blocks.find(b=>b.id===ref.block_id);if(!t||!b)continue;const card=html('section','wn-evidence'),name=html('strong','',t.name),quote=html('p');quote.textContent=Array.from(t.text).slice(b.start,b.end).join('');const source=button('查看完整原文 →','wn-source');source.onclick=()=>showSource(t,b);card.append(name,quote,source);content.append(card);displayed++;}if(!displayed)content.append(html('p','wn-muted','原文引用暂不可用，请核对当前草稿版本。'));return;
  }
  if(focus){const n=nodes.find(n=>n.id===focus);detailTitle.textContent=n?.label||focus;content.append(html('p','wn-muted',`出现于 ${n?.count||0} 个文本块 · ${n?.interviews||0} 篇访谈`));const focusButton=button('聚焦此词语 →','wn-focus-button');focusButton.onclick=()=>setView('local');content.append(focusButton);if(topology.core.has(focus))content.append(html('p','wn-structure-note',`结构核心：直接连接 ${topology.degree.get(focus)} 个词语，不代表研究重要性。`));if(topology.bridge.has(focus))content.append(html('p','wn-structure-note','桥梁词语：连接不同词群，并承担较多路径连接。'));const linked=visible.filter(e=>e.source===focus||e.target===focus).sort((a,b)=>b.count-a.count);content.append(html('h4','',`直接共现 · ${linked.length}`));for(const e of linked){const label=e.source===focus?e.target:e.source,b=button(label+' · '+e.count+' 块','wn-relation');b.onclick=()=>selectEdge(e);content.append(b);}if(!linked.length)content.append(html('p','wn-muted','当前阈值下没有直接共现连线。'));return;
  }
  detailTitle.textContent='词语共现';content.append(html('h3','','查看词语之间的共同出现'),html('p','wn-muted','点击词语查看直接共现；点击连线查看对应文本块。'),html('p','wn-muted','颜色沿用共现网络的结构分组，词群不是AI生成的研究主题。节点大小和位置不代表研究重要性。'));
 }
 function update(){stopElastic();drag=null;const value=Math.max(1,Math.floor(Number(threshold.value)||1));threshold.value=value;visible=edges.filter(e=>e.count>=value);const endpoints=new Set(visible.flatMap(e=>[e.source,e.target]));visibleNodes=nodes.filter(n=>endpoints.has(n.id));topology=geometry.analyzeTopology(visibleNodes,visible);if(!focus||!endpoints.has(focus))focus=visibleNodes.slice().sort((a,b)=>topology.degree.get(b.id)-topology.degree.get(a.id))[0]?.id||null;selectedEdge=null;elastic=null;regionState=new Map();regionTargets=[];regionComputed=0;globalPositions=forceLayout();positions=globalPositions;fitCamera();savedGlobalCamera={...camera};savedGlobalBase={...base};if(view==='local'&&focus)localPositions();draw();showDetails();}
 global.onclick=()=>setView('global');local.onclick=()=>setView('local');threshold.onchange=update;threshold.oninput=()=>{if(Number.isInteger(Number(threshold.value))&&Number(threshold.value)>0)update();};fit.onclick=fitCamera;
 function setCollapsed(value){layout.classList.toggle('wn-collapsed',value);aside.hidden=value;expand.hidden=!value;}collapse.onclick=()=>setCollapsed(true);expand.onclick=()=>setCollapsed(false);
 function zoomBy(factor,center=null){stopElastic();drag=null;const p=center||{x:camera.x+camera.w/2,y:camera.y+camera.h/2},width=Math.max(base.w*.12,Math.min(base.w*5,camera.w*factor)),scale=width/camera.w;camera={x:p.x+(camera.x-p.x)*scale,y:p.y+(camera.y-p.y)*scale,w:width,h:camera.h*scale};applyCamera();}
 minus.onclick=()=>zoomBy(1.25);plus.onclick=()=>zoomBy(.8);
 function point(event){const rect=svg.getBoundingClientRect(),scale=Math.min(rect.width/camera.w,rect.height/camera.h),left=rect.left+(rect.width-camera.w*scale)/2,top=rect.top+(rect.height-camera.h*scale)/2;return{x:camera.x+(event.clientX-left)/scale,y:camera.y+(event.clientY-top)/scale};}
 svg.addEventListener('wheel',e=>{e.preventDefault();zoomBy(Math.exp(Math.max(-.25,Math.min(.25,e.deltaY*.001))),point(e));},{passive:false});
 svg.addEventListener('pointerdown',e=>{
  if(e.button!==0||e.target.closest('.wn-edge'))return;const node=e.target.closest('.wn-node');if(node&&view==='local')return;stopElastic();const p=point(e),id=node?.dataset.word;if(id)ensureElastic();drag={id,p,clientX:e.clientX,clientY:e.clientY,camera:{...camera},moved:false,pointer:e.pointerId,offset:id?{x:positions[id].x-p.x,y:positions[id].y-p.y}:{x:0,y:0},at:id?{...positions[id]}:null};svg.setPointerCapture(e.pointerId);if(id)e.preventDefault();
 });
 svg.addEventListener('pointermove',e=>{
  if(!drag||drag.pointer!==e.pointerId)return;if(!drag.moved&&Math.hypot(e.clientX-drag.clientX,e.clientY-drag.clientY)<4)return;drag.moved=true;suppressClick=true;const p=point(e);
  if(drag.id){drag.at={x:p.x+drag.offset.x,y:p.y+drag.offset.y};const particle=elastic.particles[drag.id];particle.x=drag.at.x;particle.y=drag.at.y;particle.vx=particle.vy=0;positions[drag.id]=globalPositions[drag.id]={...drag.at};updateMotionDrawing();startElastic();}
  else{const r=svg.getBoundingClientRect(),scale=Math.min(r.width/drag.camera.w,r.height/drag.camera.h);camera={...drag.camera,x:drag.camera.x-(e.clientX-drag.clientX)/scale,y:drag.camera.y-(e.clientY-drag.clientY)/scale};applyCamera();}
 });
 function endDrag(e){const completed=drag;drag=null;if(!completed)return;if(completed.id&&completed.moved){centerMotion=null;releasedPin={id:completed.id,...completed.at};startElastic();}else if(completed.id&&e.type==='pointerup')selectNode(completed.id);suppressClick=true;setTimeout(()=>suppressClick=false,0);}
 svg.addEventListener('pointerup',endDrag);svg.addEventListener('pointercancel',endDrag);svg.addEventListener('lostpointercapture',e=>{if(drag)endDrag(e);});
 search.oninput=()=>{results.replaceChildren();const q=search.value.trim().toLowerCase();results.hidden=!q;if(!q)return;for(const n of visibleNodes.filter(n=>n.label.toLowerCase().includes(q))){const b=button(n.label);b.onclick=()=>{selectNode(n.id);search.value='';results.hidden=true;};results.append(b);}if(!results.childElementCount)results.append(html('p','wn-muted','当前阈值下没有匹配的词语，可降低阈值'));};
 document.addEventListener('pointerdown',e=>{if(!searchWrap.contains(e.target))results.hidden=true;},{signal:controller.signal});search.onkeydown=e=>{if(e.key==='Escape')results.hidden=true;if(e.key==='Enter'){e.preventDefault();results.querySelector('button')?.click();}};
 exportButton.onclick=()=>{
  const clone=svg.cloneNode(true),raw=svg.getBBox(),box=raw.width?{x:raw.x-35,y:raw.y-35,w:raw.width+70,h:raw.height+70}:bounds(positions);clone.setAttribute('viewBox',`${box.x} ${box.y} ${box.w} ${box.h}`);clone.setAttribute('width','1600');clone.setAttribute('height','1000');const styles=shape('style',{},'.wn-node-label{font:16px Microsoft YaHei,sans-serif;fill:#193740}.wn-ball{fill:var(--wn-color);stroke:white;stroke-width:2}.wn-bridge-ring{fill:none;stroke:var(--wn-dark);stroke-width:1.4}.wn-group-caption{font-family:Microsoft YaHei,sans-serif}.wn-label-bg{fill:white;stroke:#dae5e6}.wn-edge-line{stroke:var(--wn-edge-color,#81ada9)}.wn-edge-hit,.wn-node-hit{stroke:none;fill:none}.wn-halo{fill:#def4ef}.wn-card{fill:white;stroke:#83b8b0}.wn-edge-count{font:12px sans-serif;fill:#356861}.wn-edge-badge{fill:white}.wn-edge-line{opacity:.68}.wn-edge.distant .wn-edge-line{opacity:.16}.wn-edge.selected .wn-edge-line{stroke:#008f86;opacity:1}.wn-node.distant{opacity:.38}.wn-node.focus .wn-label-bg{fill:#eaf7f2;stroke:#7ebfb1}.wn-node.focus .wn-node-label{font-weight:600;fill:#008e82}.wn-node.focus .wn-card{fill:#009e96;stroke:#009e96}.wn-node.focus:has(.wn-card) .wn-node-label{fill:white}');clone.prepend(styles);const url=URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(clone)],{type:'image/svg+xml;charset=utf-8'})),image=new Image();
  URL.revokeObjectURL(url);const originals=svg.querySelectorAll('*'),copies=clone.querySelectorAll('*:not(style)');originals.forEach((original,i)=>{const copy=copies[i];if(!copy)return;const computed=getComputedStyle(original);for(const property of ['fill','stroke','stroke-width','opacity','fill-opacity','stroke-opacity','font-family','font-size','font-weight','paint-order','stroke-linejoin'])copy.style.setProperty(property,computed.getPropertyValue(property));});const styledUrl=URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(clone)],{type:'image/svg+xml;charset=utf-8'}));
  image.onload=()=>{const canvas=document.createElement('canvas');canvas.width=1600;canvas.height=1000;const ctx=canvas.getContext('2d');ctx.fillStyle='#fbfdfd';ctx.fillRect(0,0,1600,1000);ctx.drawImage(image,0,0,1600,1000);canvas.toBlob(blob=>{if(blob){const a=document.createElement('a'),download=URL.createObjectURL(blob);a.href=download;a.download='词语共现图.png';a.click();setTimeout(()=>URL.revokeObjectURL(download),1000);}},'image/png');URL.revokeObjectURL(styledUrl);};image.onerror=()=>URL.revokeObjectURL(styledUrl);image.src=styledUrl;
 };
 let lastCanvasSize='';
 const observer=new ResizeObserver(()=>{if(disposed||layout.hidden)return;const r=svg.getBoundingClientRect();if(!r.width||!r.height)return;const size=`${Math.round(r.width)}:${Math.round(r.height)}`;if(size!==lastCanvasSize){lastCanvasSize=size;fitCamera();}else draw();});observer.observe(svg);update();
 if(window.mountWordExplorer){explorer=window.mountWordExplorer({page,heading,bar,layout,networkViews:views,fit,exportButton,getState:()=>({nodes,visible,visibleNodes,focus,selectedEdge}),selectNode,selectEdge,showSource,draft,stopMotion:stopElastic});explorer.start();}
 return()=>{disposed=true;stopElastic();controller.abort();observer.disconnect();explorer?.dispose();bar.remove();page.remove();};
};
