/* Shared, display-only geometry extracted unchanged from the theme network. */
(()=>{
function analyzeTopology(nodes,links){
 const ids=nodes.map(n=>n.id).sort((a,b)=>String(a).localeCompare(String(b))),net=new Map(ids.map(id=>[id,new Set()]));
 for(const e of links)if(e.source!==e.target&&net.has(e.source)&&net.has(e.target)){net.get(e.source).add(e.target);net.get(e.target).add(e.source);}
 const degree=new Map(ids.map(id=>[id,net.get(id).size])),m=[...degree.values()].reduce((a,b)=>a+b,0)/2;
 let groups=ids.map(id=>[id]);
 const quality=parts=>{if(!m)return 0;return parts.reduce((q,g)=>{const members=new Set(g),volume=g.reduce((a,id)=>a+degree.get(id),0),inside=g.reduce((a,id)=>a+[...net.get(id)].filter(v=>members.has(v)).length,0)/2;return q+inside/m-Math.pow(volume/(2*m),2);},0);};
 let score=quality(groups);
 for(;;){let best=null,gain=1e-9;for(let i=0;i<groups.length;i++)for(let j=i+1;j<groups.length;j++){const target=new Set(groups[j]);if(!groups[i].some(id=>[...net.get(id)].some(v=>target.has(v))))continue;const candidate=groups.filter((_,k)=>k!==i&&k!==j).concat([groups[i].concat(groups[j])]),next=quality(candidate);if(next-score>gain){gain=next-score;best=candidate;}}if(!best)break;groups=best;score+=gain;}
 // A display community needs at least three real nodes. Never manufacture a
 // catch-all community from weak structure, pairs or isolated nodes.
 groups=score>=.12?groups.filter(g=>g.length>=3):[];
 groups.sort((a,b)=>b.length-a.length||String(a.slice().sort()[0]).localeCompare(String(b.slice().sort()[0])));
 const membership=new Map();groups.forEach((g,i)=>g.forEach(id=>membership.set(id,i)));
 const sorted=[...degree.values()].sort((a,b)=>a-b),median=sorted[Math.floor(sorted.length/2)]||0,max=Math.max(0,...sorted),threshold=Math.max(3,median+2,Math.ceil(max*.6)),core=new Set(ids.filter(id=>degree.get(id)>=threshold));
 if(max-median<2)core.clear();
 // Brandes centrality on unique, undirected real connections (display role only).
 const centrality=new Map(ids.map(id=>[id,0]));for(const source of ids){const stack=[],queue=[source],dist=new Map(ids.map(id=>[id,-1])),sigma=new Map(ids.map(id=>[id,0])),pred=new Map(ids.map(id=>[id,[]])),delta=new Map(ids.map(id=>[id,0]));dist.set(source,0);sigma.set(source,1);for(let at=0;at<queue.length;at++){const v=queue[at];stack.push(v);for(const w of net.get(v)){if(dist.get(w)<0){dist.set(w,dist.get(v)+1);queue.push(w);}if(dist.get(w)===dist.get(v)+1){sigma.set(w,sigma.get(w)+sigma.get(v));pred.get(w).push(v);}}}while(stack.length){const w=stack.pop();for(const v of pred.get(w))delta.set(v,delta.get(v)+sigma.get(v)/sigma.get(w)*(1+delta.get(w)));if(w!==source)centrality.set(w,centrality.get(w)+delta.get(w)/2);}}
 const mean=ids.reduce((a,id)=>a+centrality.get(id),0)/Math.max(1,ids.length),peak=Math.max(0,...centrality.values()),bridge=new Set();
 if(groups.length>1)for(const id of ids){const k=degree.get(id),counts=new Map();for(const n of net.get(id)){const c=membership.get(n);if(c!==undefined)counts.set(c,(counts.get(c)||0)+1);}const groupedDegree=[...counts.values()].reduce((a,v)=>a+v,0),participation=groupedDegree?1-[...counts.values()].reduce((a,v)=>a+Math.pow(v/groupedDegree,2),0):0;if(k>=3&&counts.size>=2&&participation>=.25&&centrality.get(id)>mean&&centrality.get(id)>=peak*.2)bridge.add(id);}
 return{groups,membership,ungrouped:ids.filter(id=>!membership.has(id)),degree,core,bridge,score};
}

function forceNetworkLayout(nodes,links,aspect=1.4,topology=null){
  if(!nodes.length)return{};
  const ordered=[...nodes].sort((a,b)=>String(a.id).localeCompare(String(b.id))),index=new Map(ordered.map((n,i)=>[n.id,i])),count=ordered.length;
  const ratio=Math.max(.65,Math.min(2.6,aspect||1.4)),area=Math.max(1,count)*65000,width=Math.sqrt(area*ratio),height=Math.sqrt(area/ratio);
  const particles=ordered.map(n=>{let seed=2166136261;for(const c of String(n.id))seed=Math.imul(seed^c.charCodeAt(0),16777619);const random=()=>{seed=(Math.imul(seed,1664525)+1013904223)|0;return(seed>>>0)/4294967296;};return{id:n.id,x:(random()-.5)*width,y:(random()-.5)*height,vx:0,vy:0};});
  const seen=new Set(),pairs=[];for(const e of links){const a=index.get(e.source),b=index.get(e.target);if(a===undefined||b===undefined||a===b)continue;const pair=[Math.min(a,b),Math.max(a,b)],key=pair.join(':');if(!seen.has(key)){seen.add(key);pairs.push(pair);}}pairs.sort((a,b)=>a[0]-b[0]||a[1]-b[1]);
  const degree=Array(count).fill(0);pairs.forEach(([a,b])=>{degree[a]++;degree[b]++;});
  const hub=degree.indexOf(Math.max(...degree));
  // Independent integer mixing avoids correlated starting positions for similar ids.
  particles.forEach((p,i)=>{let seed=Math.imul(i+1,0x9e3779b1);const random=()=>{seed^=seed>>>16;seed=Math.imul(seed,0x7feb352d);seed^=seed>>>15;seed=Math.imul(seed,0x846ca68b);seed^=seed>>>16;return(seed>>>0)/4294967296;};p.x=i===hub?0:(random()-.5)*width;p.y=i===hub?0:(random()-.5)*height;});
  // Graph-distance stress gives the network a loose structure, not fixed slots.
  // Dense neighborhoods stay together; bridges keep separate regions legible.
  const distance=Array.from({length:count},(_,i)=>Array.from({length:count},(_,j)=>i===j?0:Infinity));
  pairs.forEach(([a,b])=>{distance[a][b]=distance[b][a]=1;});
  for(let k=0;k<count;k++)for(let i=0;i<count;i++)for(let j=0;j<count;j++)distance[i][j]=Math.min(distance[i][j],distance[i][k]+distance[k][j]);
  const steps=count>200?260:650;
  for(let step=0;step<steps;step++){
    const forces=particles.map((p,i)=>({x:-p.x*(.002+degree[i]*.0015),y:-p.y*(.002+degree[i]*.0015)})),alpha=Math.max(.08,1-step/steps);
    for(let i=0;i<count;i++)for(let j=i+1;j<count;j++){const hops=distance[i][j];if(!Number.isFinite(hops)||hops<2)continue;const a=particles[i],b=particles[j],dx=b.x-a.x,dy=b.y-a.y,d=Math.max(1,Math.hypot(dx,dy)),desired=320*Math.pow(hops,.95),pull=(d-desired)*.12/(hops*hops);forces[i].x+=dx/d*pull;forces[i].y+=dy/d*pull;forces[j].x-=dx/d*pull;forces[j].y-=dy/d*pull;}
    for(let i=0;i<count;i++)for(let j=i+1;j<count;j++){const a=particles[i],b=particles[j],dx=a.x-b.x,dy=a.y-b.y,d=Math.max(8,Math.hypot(dx,dy)),rep=180000/(d*d);forces[i].x+=dx/d*rep;forces[i].y+=dy/d*rep;forces[j].x-=dx/d*rep;forces[j].y-=dy/d*rep;}
    pairs.forEach(([i,j])=>{const a=particles[i],b=particles[j],dx=b.x-a.x,dy=b.y-a.y,d=Math.max(1,Math.hypot(dx,dy)),same=topology?.membership.has(a.id)&&topology.membership.get(a.id)===topology.membership.get(b.id),pull=(d-(same?230:380))*.038/Math.sqrt(Math.max(1,Math.min(degree[i],degree[j])));forces[i].x+=dx/d*pull;forces[i].y+=dy/d*pull;forces[j].x-=dx/d*pull;forces[j].y-=dy/d*pull;});
    if(topology?.groups.length)for(const group of topology.groups){const members=group.map(id=>particles[index.get(id)]),cx=members.reduce((a,p)=>a+p.x,0)/members.length,cy=members.reduce((a,p)=>a+p.y,0)/members.length;for(const p of members){forces[index.get(p.id)].x+=(cx-p.x)*.025;forces[index.get(p.id)].y+=(cy-p.y)*.025;}}
    particles.forEach((p,i)=>{p.vx=(p.vx+forces[i].x*alpha)*.72;p.vy=(p.vy+forces[i].y*alpha)*.72;const speed=Math.max(1,Math.hypot(p.vx,p.vy)/18);p.x+=p.vx/speed;p.y+=p.vy/speed;});
    // Reserve a rectangle for every node and its two-line title, even while faded.
    for(let pass=0;pass<2;pass++)for(let i=0;i<count;i++)for(let j=i+1;j<count;j++){const a=particles[i],b=particles[j],dx=b.x-a.x,dy=b.y-a.y,ox=290-Math.abs(dx),oy=112-Math.abs(dy);if(ox>0&&oy>0){if(ox<oy){const shift=(ox+.5)/2,s=Math.sign(dx)||1;a.x-=shift*s;b.x+=shift*s;a.vx*=.5;b.vx*=.5;}else{const shift=(oy+.5)/2,s=Math.sign(dy)||1;a.y-=shift*s;b.y+=shift*s;a.vy*=.5;b.vy*=.5;}}}
  }
  // Final collision relaxation has no springs pulling labels back together.
  for(let pass=0;pass<180;pass++){let overlap=false;for(let i=0;i<count;i++)for(let j=i+1;j<count;j++){const a=particles[i],b=particles[j],dx=b.x-a.x,dy=b.y-a.y,ox=290-Math.abs(dx),oy=112-Math.abs(dy);if(ox>0&&oy>0){overlap=true;if(ox<oy){const s=(Math.sign(dx)||1)*(ox+.2)/2;a.x-=s;b.x+=s;}else{const s=(Math.sign(dy)||1)*(oy+.2)/2;a.y-=s;b.y+=s;}}}if(!overlap)break;}
  const xs=particles.map(p=>p.x),ys=particles.map(p=>p.y),spanX=Math.max(...xs)-Math.min(...xs),spanY=Math.max(...ys)-Math.min(...ys),boxRatio=(spanX+334)/(spanY+163);
  const scaleX=boxRatio<ratio?Math.min(2.4,Math.max(1,((spanY+163)*ratio-334)/Math.max(1,spanX))):1,scaleY=boxRatio>ratio?Math.min(2.4,Math.max(1,((spanX+334)/ratio-163)/Math.max(1,spanY))):1;
  return Object.fromEntries(particles.map(p=>[p.id,{x:p.x*scaleX,y:p.y*scaleY}]));
}

function createElasticNetwork(points,links){
  const particles=Object.fromEntries(Object.entries(points).map(([id,p])=>[id,{...p,vx:0,vy:0}])),seen=new Set(),springs=[];
  for(const e of links){const a=particles[e.source],b=particles[e.target],key=[String(e.source),String(e.target)].sort().join('\u0000');if(!a||!b||e.source===e.target||seen.has(key))continue;seen.add(key);springs.push({a:e.source,b:e.target,rest:Math.max(140,Math.hypot(a.x-b.x,a.y-b.y))});}
  return{particles,springs};
}
function stepElasticNetwork(state,pinned,dt=1){
  const list=Object.entries(state.particles),forces=Object.fromEntries(list.map(([id])=>[id,{x:0,y:0}]));
  for(const s of state.springs){const a=state.particles[s.a],b=state.particles[s.b],dx=b.x-a.x,dy=b.y-a.y,d=Math.max(1,Math.hypot(dx,dy)),f=(d-s.rest)*.009;forces[s.a].x+=dx/d*f;forces[s.a].y+=dy/d*f;forces[s.b].x-=dx/d*f;forces[s.b].y-=dy/d*f;}
  for(let i=0;i<list.length;i++)for(let j=i+1;j<list.length;j++){const [aid,a]=list[i],[bid,b]=list[j];let dx=b.x-a.x,dy=b.y-a.y;if(Math.abs(dx)+Math.abs(dy)<.001){dx=1;dy=.5;}const d=Math.max(1,Math.hypot(dx,dy));if(d<170){const f=(170-d)*.012+(d<65?(65-d)*.09:0);forces[aid].x-=dx/d*f;forces[aid].y-=dy/d*f;forces[bid].x+=dx/d*f;forces[bid].y+=dy/d*f;}}
  // Persistent group cohesion competes with real springs; it is only geometry.
  if(state.groups?.length){const centers=[];for(const group of state.groups){if(group.length<3)continue;const members=group.map(id=>state.particles[id]).filter(Boolean);if(!members.length)continue;const cx=members.reduce((a,p)=>a+p.x,0)/members.length,cy=members.reduce((a,p)=>a+p.y,0)/members.length;centers.push({group,x:cx,y:cy,r:110+Math.sqrt(members.length)*45});const pulls=[];for(const id of group){const p=state.particles[id];if(!p)continue;const dx=cx-p.x,dy=cy-p.y,d=Math.max(1,Math.hypot(dx,dy)),weight=state.bridges?.has(id)? .6:1,force=Math.min(3.5,Math.max(0,d-80)*.0085)*weight;pulls.push({id,x:dx/d*force,y:dy/d*force});}const fx=pulls.reduce((a,p)=>a+p.x,0)/members.length,fy=pulls.reduce((a,p)=>a+p.y,0)/members.length;for(const p of pulls){forces[p.id].x+=p.x-fx;forces[p.id].y+=p.y-fy;}}
  for(let i=0;i<centers.length;i++)for(let j=i+1;j<centers.length;j++){const a=centers[i],b=centers[j],dx=b.x-a.x,dy=b.y-a.y,d=Math.max(1,Math.hypot(dx,dy)),f=Math.min(2,Math.max(0,a.r+b.r-d)*.006);for(const id of a.group){forces[id].x-=dx/d*f/a.group.length;forces[id].y-=dy/d*f/a.group.length;}for(const id of b.group){forces[id].x+=dx/d*f/b.group.length;forces[id].y+=dy/d*f/b.group.length;}}}
  let speed=0;for(const [id,p] of list){if(pinned?.id===id){p.x=pinned.x;p.y=pinned.y;p.vx=p.vy=0;continue;}p.vx=(p.vx+forces[id].x*dt)*Math.pow(.82,dt);p.vy=(p.vy+forces[id].y*dt)*Math.pow(.82,dt);const cap=Math.max(1,Math.hypot(p.vx,p.vy)/14);p.vx/=cap;p.vy/=cap;p.x+=p.vx*dt;p.y+=p.vy*dt;speed=Math.max(speed,Math.hypot(p.vx,p.vy));}return speed;
}

function computeGroupRegions(topology,pos,regionState){
 const regions=topology.groups.map((ids,index)=>{if(ids.length<3)return null;const points=ids.map(id=>({id,...pos[id]})).filter(p=>Number.isFinite(p.x));if(!points.length)return null;
 // The densest bounded neighborhood is the body; far dragged nodes stay colored.
 const previous=regionState.get(index);let best=null;
 for(const seed of points){const body=points.filter(p=>Math.hypot(p.x-seed.x,p.y-seed.y)<=460),score=body.length*1000-(previous?Math.hypot(seed.x-previous.x,seed.y-previous.y)*.2:0);if(!best||score>best.score)best={body,score};}
 const body=best.body,x=(Math.min(...body.map(p=>p.x))+Math.max(...body.map(p=>p.x)))/2,y=(Math.min(...body.map(p=>p.y))+Math.max(...body.map(p=>p.y)))/2;
 return{index,x,y,rx:Math.min(340,Math.max(65,(Math.max(...body.map(p=>p.x))-Math.min(...body.map(p=>p.x)))/2+75)),ry:Math.min(270,Math.max(65,(Math.max(...body.map(p=>p.y))-Math.min(...body.map(p=>p.y)))/2+75)),body,count:ids.length};
 }).filter(Boolean);
 // Limit overlap by the directional radii, without feeding regions into physics.
 for(let pass=0;pass<3;pass++)for(let i=0;i<regions.length;i++)for(let j=i+1;j<regions.length;j++){const a=regions[i],b=regions[j],dx=b.x-a.x,dy=b.y-a.y,d=Math.max(1,Math.hypot(dx,dy)),ux=dx/d,uy=dy/d,ra=1/Math.sqrt(ux*ux/(a.rx*a.rx)+uy*uy/(a.ry*a.ry)),rb=1/Math.sqrt(ux*ux/(b.rx*b.rx)+uy*uy/(b.ry*b.ry));if(d<ra+rb+24){const scale=Math.max(.6,(d-24)/(ra+rb));a.rx=Math.max(50,a.rx*scale);a.ry=Math.max(50,a.ry*scale);b.rx=Math.max(50,b.rx*scale);b.ry=Math.max(50,b.ry*scale);}}
 return regions;
}

function localEdgeRoute(a,b,halfWidth=122){const side=Math.sign(b.x-a.x)||1,x1=a.x+side*halfWidth,x2=b.x-side*halfWidth,middle=(x1+x2)/2;return{d:`M${x1} ${a.y} C${middle} ${a.y},${middle} ${b.y},${x2} ${b.y}`,x:middle,y:(a.y+b.y)/2-14};}
window.networkGeometry={analyzeTopology,layout:forceNetworkLayout,createElasticNetwork,stepElasticNetwork,groupRegions:computeGroupRegions,localEdgeRoute};
})();

