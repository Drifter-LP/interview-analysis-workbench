/* Independent evidence-grounded network view. No model calls during navigation. */
(() => {
  const style = document.createElement('link'); style.rel='stylesheet'; style.href='/assets/network.css?v=20261004-7'; document.head.append(style);
  const head = document.querySelector('#focused .focused-head');
  const tabs = document.createElement('div'); tabs.className='network-tabs';
  tabs.innerHTML='<button type="button" class="active">主题分析</button><button type="button">主题关系图</button>';
  head.querySelector('h2').replaceWith(tabs);
  const workspace=document.createElement('section'); workspace.className='network-workspace';workspace.hidden=true;
  workspace.innerHTML='<div class="network-toolbar"><p>基于当前主题分析，独立整理发现之间的联系</p><button class="soft" data-action="generate">生成关系图</button><button class="soft" data-action="global">全局网络</button><button class="soft" data-action="reset">返回默认中心</button><button class="soft" data-action="export">导出图片</button></div><div class="network-layout"><svg class="network-canvas" viewBox="0 0 1000 650" role="img" aria-label="主题关系网络"></svg><aside class="network-details"></aside></div><p class="network-note">仅显示材料支持的联系；默认中心按连接数选择，不代表主题重要性。点击节点展开局部联系，点击连线查看原文依据。</p>';
  document.querySelector('#focused').append(workspace);
  // Remove the obsolete global-view action; node focus is always retained.
  workspace.querySelector('[data-action="global"]').remove();
  workspace.querySelector('[data-action="reset"]').remove();
  const svg=workspace.querySelector('svg'), detailsAside=workspace.querySelector('aside');
  const details=document.createElement('div');details.className='network-detail-content';
  const detailHead=document.createElement('div');detailHead.className='network-detail-head';
  const detailTitle=document.createElement('span');detailTitle.textContent='';detailHead.append(detailTitle);
  const backButton=document.createElement('button');backButton.type='button';backButton.className='network-back';backButton.textContent='←';backButton.title='返回节点说明';backButton.setAttribute('aria-label','返回节点说明');backButton.hidden=true;detailHead.prepend(backButton);
  backButton.onclick=()=>{edgeId=null;draw();showDetails();};
  detailsAside.append(detailHead,details);
  svg.setAttribute('preserveAspectRatio','xMidYMin meet');
  detailsAside.id='networkDetails';
  const collapseButton=document.createElement('button');
  collapseButton.type='button';collapseButton.className='network-collapse';
  collapseButton.textContent='›';collapseButton.title='收起说明';collapseButton.setAttribute('aria-label','收起说明');collapseButton.setAttribute('aria-expanded','true');
  collapseButton.setAttribute('aria-controls',detailsAside.id);detailHead.append(collapseButton);
  const expandButton=document.createElement('button');expandButton.type='button';expandButton.className='network-expand';
  expandButton.textContent='‹';expandButton.title='展开说明';expandButton.setAttribute('aria-label','展开说明');expandButton.setAttribute('aria-controls',detailsAside.id);expandButton.hidden=true;
  workspace.querySelector('.network-layout').append(expandButton);
  function setDetailsCollapsed(collapsed){
    workspace.querySelector('.network-layout').classList.toggle('details-collapsed',collapsed);
    detailsAside.hidden=collapsed;expandButton.hidden=!collapsed;
    collapseButton.setAttribute('aria-expanded',String(!collapsed));
    expandButton.setAttribute('aria-expanded',String(!collapsed));
  }
  collapseButton.onclick=()=>setDetailsCollapsed(true);expandButton.onclick=()=>setDetailsCollapsed(false);
  const action=name=>workspace.querySelector(`[data-action="${name}"]`);
  let active=false, graph=null, focus=null, edgeId=null, defaultFocus=null, positions={}, frame=0, requestToken=0, pending=false, loadedAnalysis=null;
  const ns='http://www.w3.org/2000/svg';
  const el=(tag,attrs={})=>{const node=document.createElementNS(ns,tag);Object.entries(attrs).forEach(([k,v])=>node.setAttribute(k,v));return node;};
  const degree=id=>graph.edges.filter(e=>e.source===id||e.target===id).length;
  const neighbors=id=>new Set(graph.edges.filter(e=>e.source===id||e.target===id).map(e=>e.source===id?e.target:e.source));
  // Display-only abbreviation. Full findings and evidence remain unchanged.
  function compactLabel(value,limit=12){
    let text=String(value||'').trim();
    const original=text;
    text=text.replace(/^[A-Za-z][A-Za-z0-9/-]*(?:改革|付费|支付)?(?:下)?/,'').replace(/^导致/,'');
    text=text.split(/[，,；;。]/)[0].trim()||original;
    const chars=Array.from(text);return chars.length>limit?chars.slice(0,limit).join('')+'…':text;
  }
  function setControls(){action('generate').disabled=pending||!currentThemeAnalysis;action('generate').textContent=pending?'正在整理联系…':graph?'已生成并保存':'生成关系图'; if(graph)action('generate').disabled=true;action('export').disabled=!graph;}
  function hideBase(value){
    const input=document.querySelector('#themeQuickInput').closest('.focused-input');
    input.hidden=value; input.style.display=value?'none':'';
    const panel=document.querySelector('#themePanel');panel.hidden=value;panel.style.display=value?'none':'';
    if(value){const comparison=document.querySelector('#comparisonWorkspace');comparison.hidden=true;
      const oldInput=document.querySelector('#comparisonQuickRow');if(oldInput)oldInput.hidden=true;}
  }
  function switchMode(value){
    if(value)collectThemeResult();active=value;tabs.children[0].classList.toggle('active',!value);tabs.children[1].classList.toggle('active',value);
    workspace.hidden=!value;
    hideBase(value);
    if(value){document.querySelector('#comparisonWorkspace').hidden=true;load();}
    else renderFocusedAnalysis();
  }
  tabs.children[0].onclick=()=>switchMode(false);tabs.children[1].onclick=()=>switchMode(true);
  const originalRender=renderFocusedAnalysis;
  renderFocusedAnalysis=function(){originalRender();if(active){workspace.hidden=false;hideBase(true);load();}};
  document.querySelector('#themeHistorySelect').addEventListener('change',()=>{if(active)load();});
  function requestBody(){return {research_project_id:selectedResearchProject?.id,analysis:currentThemeAnalysis};}
  async function load(){
    const analysis=currentThemeAnalysis;if(loadedAnalysis===analysis&&graph){setControls();return;}
    const token=++requestToken;graph=null;focus=null;edgeId=null;cancelAnimationFrame(frame);positions={};loadedAnalysis=analysis;svg.replaceChildren();setControls();
    if(!analysis||!selectedResearchProject){details.innerHTML='<p>请先在主题分析中打开一条分析结果，再进入主题关系图。</p>';return;}
    details.innerHTML='<p>正在读取已保存的关系图…</p>';
    try{const result=await api('/api/theme-networks/load',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(requestBody())});if(token!==requestToken)return;
      if(result.graph)useGraph(result.graph);else details.innerHTML='<h3>尚未生成关系图</h3><p>点击“生成关系图”整理有原文支持的联系。首次生成调用一次 DeepSeek；结果自动保存，后续浏览不再调用。</p>';
    }catch(error){if(token===requestToken){details.textContent=error.message;toast(error.message);}}finally{if(token===requestToken)setControls();}
  }
  action('generate').onclick=async()=>{
    if(pending||!currentThemeAnalysis)return;const analysis=currentThemeAnalysis, projectId=selectedResearchProject?.id, token=++requestToken;pending=true;setControls();details.innerHTML='<p>正在依据事实与原文整理联系，请稍候…</p>';
    try{const result=await api('/api/theme-networks',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(requestBody())});if(token===requestToken&&analysis===currentThemeAnalysis&&projectId===selectedResearchProject?.id){useGraph(result.graph);toast('关系图已生成并保存');}}
    catch(error){if(token===requestToken){details.textContent=error.message;toast(error.message);}}
    finally{pending=false;setControls();}
  };
  function useGraph(value){graph=value;defaultFocus=[...graph.nodes].sort((a,b)=>degree(b.id)-degree(a.id))[0]?.id;focus=defaultFocus;edgeId=null;move(false);setControls();}
  function layout(){
    const result={},count=graph.nodes.length;
    if(!focus){graph.nodes.forEach((n,i)=>{const angle=i*2*Math.PI/count-Math.PI/2;result[n.id]={x:500+Math.cos(angle)*330,y:265+Math.sin(angle)*190};});return result;}
    const adjacent=neighbors(focus),near=graph.nodes.filter(n=>adjacent.has(n.id)),far=graph.nodes.filter(n=>n.id!==focus&&!adjacent.has(n.id));
    result[focus]={x:280,y:265};
    // Local reading layout, not causal stages: equal peers on a spacious right arc.
    near.forEach((n,i)=>result[n.id]={x:670+(i%2)*55,y:45+(i+1)*440/(near.length+1)});
    far.forEach((n,i)=>{const angle=(i+1)*Math.PI*2/(far.length+1);result[n.id]={x:500+Math.cos(angle)*330,y:265+Math.sin(angle)*220};});return result;
  }
  function move(animate=true){
    cancelAnimationFrame(frame);const target=layout(),start={};graph.nodes.forEach(n=>start[n.id]=positions[n.id]||target[n.id]);
    const duration=animate&&!matchMedia('(prefers-reduced-motion: reduce)').matches?550:0,began=performance.now();
    const tick=now=>{const t=duration?Math.min(1,(now-began)/duration):1,ease=1-Math.pow(1-t,3);graph.nodes.forEach(n=>positions[n.id]={x:start[n.id].x+(target[n.id].x-start[n.id].x)*ease,y:start[n.id].y+(target[n.id].y-start[n.id].y)*ease});draw();if(t<1)frame=requestAnimationFrame(tick);};frame=requestAnimationFrame(tick);showDetails();
  }
  function selectNode(id){focus=id;edgeId=null;move();}
  function selectEdge(id){
    const edge=graph?.edges.find(item=>item.id===id);
    if(!edge||!focus||(edge.source!==focus&&edge.target!==focus))return;
    edgeId=id;setDetailsCollapsed(false);draw();showDetails();
  }
  function draw(){
    svg.replaceChildren();const defs=el('defs'),marker=el('marker',{id:'networkArrow',viewBox:'0 0 10 10',refX:9,refY:5,markerWidth:5,markerHeight:5,orient:'auto-start-reverse'});marker.append(el('path',{d:'M 0 0 L 10 5 L 0 10 z',fill:'#64baae'}));defs.append(marker);svg.append(defs);
    const adjacent=focus?neighbors(focus):new Set(graph.nodes.map(n=>n.id));
    graph.edges.forEach(edge=>{
      const a=positions[edge.source],b=positions[edge.target],near=!focus||edge.source===focus||edge.target===focus,selected=edge.id===edgeId;
      const dx=b.x-a.x,dy=b.y-a.y,len=Math.hypot(dx,dy)||1,bx=b.x-dx/len*12,by=b.y-dy/len*12;
      const d=`M ${a.x} ${a.y} Q ${(a.x+b.x)/2} ${(a.y+b.y)/2-18} ${bx} ${by}`;
      const path=el('path',{d,class:`network-edge${near?' near':''}${selected?' selected':''}`});if(edge.directed&&near)path.setAttribute('marker-end','url(#networkArrow)');svg.append(path);
      if(near&&focus){
        const hit=el('path',{d,class:'network-edge-hit',tabindex:0,role:'button','aria-label':edge.label});const select=()=>selectEdge(edge.id);hit.addEventListener('click',select);hit.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();select();}});svg.append(hit);
      }
      if(focus&&near){const text=el('text',{x:(a.x+b.x)/2,y:(a.y+b.y)/2-14,'text-anchor':'middle',class:'network-label'});text.textContent=compactLabel(edge.label,8);svg.append(text);}
    });
    graph.nodes.forEach(node=>{const p=positions[node.id],selected=node.id===focus,near=selected||adjacent.has(node.id);const group=el('g',{transform:`translate(${p.x} ${p.y})`,class:`network-node${near?' near':''}${selected?' focus':''}`,tabindex:0,role:'button','aria-label':`聚焦：${node.label}`});
      const title=el('title');title.textContent=node.label;group.append(title);
      if(selected)group.append(el('circle',{r:20,class:'network-halo'}));group.append(el('circle',{r:selected?12:near?8:6}));
      if(focus&&!near)group.classList.add('distant');
      const beside=focus&&near&&!selected;
      const text=el('text',{x:beside?14:0,y:beside?5:28,'text-anchor':beside?'start':'middle',class:'network-node-label'});
      text.textContent=compactLabel(node.label,selected?14:12);group.append(text);
      group.addEventListener('click',()=>selectNode(node.id));group.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();selectNode(node.id);}});svg.append(group);
    });
  }
  function showDetails(){
    const edge=graph.edges.find(e=>e.id===edgeId);
    backButton.hidden=!edge;detailTitle.classList.remove('network-node-heading');
    if(edge){detailTitle.textContent='原文依据';details.innerHTML=`${(edge.sources||[]).map((s,i)=>`<article class="network-quote"><div class="network-quote-source">${escapeHtml(s.material_name)}</div><blockquote>${escapeHtml(s.quote)} <button type="button" class="network-index" data-source="${i}" title="查看原文" aria-label="查看原文 ${escapeHtml(String(s.number))}">${escapeHtml(String(s.number))}</button></blockquote></article>`).join('')||'<p class="network-muted">暂无原文依据</p>'}`;
      details.querySelectorAll('[data-source]').forEach(b=>b.onclick=()=>{const s=edge.sources[Number(b.dataset.source)];openComparisonEvidence(s.project_id,Number(s.number));});return;}
    detailTitle.textContent='';
    const node=graph.nodes.find(n=>n.id===focus);if(!node){details.innerHTML='<p>点击节点查看联系。</p>';return;}
    const related=graph.edges.filter(e=>e.source===focus||e.target===focus);
    details.innerHTML=`<h3 class="network-node-heading">${escapeHtml(compactLabel(node.label,18))}</h3><p class="network-node-full">${escapeHtml(node.label)}</p><div class="network-relation-count">${related.length} 条直接联系</div><div class="network-relation-list">${related.map(e=>{const other=graph.nodes.find(n=>n.id===(e.source===focus?e.target:e.source));return `<button class="network-relation-row" type="button" data-edge="${e.id}"><span>${escapeHtml(e.label)}</span><small>${escapeHtml(compactLabel(other?.label||'',16))}</small><i aria-hidden="true">›</i></button>`;}).join('')||'<p class="network-muted">没有可确认的直接联系</p>'}</div>`;
    detailTitle.textContent=compactLabel(node.label,18);detailTitle.classList.add('network-node-heading');details.querySelector('.network-node-heading').remove();
    details.querySelectorAll('[data-edge]').forEach(b=>b.onclick=()=>selectEdge(b.dataset.edge));
  }
  action('export').onclick=()=>{
    const clone=svg.cloneNode(true);clone.setAttribute('xmlns',ns);clone.setAttribute('width','1600');clone.setAttribute('height','1040');
    clone.querySelectorAll('*').forEach((n,i)=>{const original=svg.querySelectorAll('*')[i],s=getComputedStyle(original);['fill','stroke','stroke-width','font-size','font-family','font-weight','paint-order'].forEach(k=>n.style.setProperty(k,s.getPropertyValue(k)));});
    const blob=new Blob([new XMLSerializer().serializeToString(clone)],{type:'image/svg+xml'}),url=URL.createObjectURL(blob),image=new Image();image.onload=()=>{const canvas=document.createElement('canvas');canvas.width=1600;canvas.height=1040;const context=canvas.getContext('2d');context.fillStyle='#f6f9f8';context.fillRect(0,0,1600,1040);context.drawImage(image,0,0);URL.revokeObjectURL(url);canvas.toBlob(b=>{if(!b){toast('导出失败');return;}const a=document.createElement('a'),u=URL.createObjectURL(b);a.href=u;a.download='主题关系图.png';a.click();setTimeout(()=>URL.revokeObjectURL(u),1000);},'image/png');};image.onerror=()=>{URL.revokeObjectURL(url);toast('导出失败，请重试');};image.src=url;
  };
  setControls();
})();
