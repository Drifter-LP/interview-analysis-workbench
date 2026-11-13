/* Guest identity is server-authoritative; this banner is only presentation. */
(()=>{
 if(!window.WORKBENCH_GUEST)return;
 const descriptions={cross:['登录后可使用跨访谈分析','主题研究、发现核查、词语探索等'],project:['登录后可新建研究项目','']};
 const lock='<svg class="guest-lock-icon" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3M12 14v3"/></svg>';
 const tip=document.createElement('div'), heading=document.createElement('strong'), detail=document.createElement('span');
 tip.id='guestFeatureTip';tip.className='guest-feature-tip';tip.setAttribute('role','tooltip');tip.hidden=true;
 tip.append(heading,detail);document.body.append(tip);
 let current=null, timer=0;
 function close(){clearTimeout(timer);current?.element.removeAttribute('aria-describedby');current=null;tip.hidden=true;}
 function position(){
  if(!current)return;
  const row=current.element.getBoundingClientRect();
  if(!row.width||!row.height){close();return;}
  const box=tip.getBoundingClientRect(), margin=12, right=row.right+25;
  const side=current.key==='cross'&&right+box.width<=innerWidth-margin;
  const below=row.bottom+9+box.height<=innerHeight-margin;
  const clamp=(v,max)=>Math.max(margin,Math.min(v,max-margin));
  const left=side?right:clamp(row.left,innerWidth-box.width);
  const top=clamp(side?row.top+(row.height-box.height)/2:below?row.bottom+9:row.top-box.height-9,innerHeight-box.height);
  tip.dataset.side=side?'right':below?'below':'above';
  tip.style.left=left+'px';tip.style.top=top+'px';
  tip.style.setProperty('--guest-tip-arrow',Math.max(12,Math.min(box.width-20,row.left+row.width/2-left-4))+'px');
 }
 function show(item){
  if(current!==item){close();current=item;const [title,note]=descriptions[item.key];heading.textContent=title;detail.textContent=note;detail.hidden=!note;}
  clearTimeout(timer);tip.hidden=false;item.element.setAttribute('aria-describedby',tip.id);position();
 }
 function leave(){clearTimeout(timer);timer=setTimeout(()=>{
  if(current&&document.activeElement!==current.element&&!current.element.matches(':hover')&&!tip.matches(':hover'))close();
 },170);}
 function bind(element,key,options={}){
  if(!element||element.classList.contains('guest-feature-locked'))return;
  const item={element,key,...options};
  element.classList.add('guest-feature-locked');element.setAttribute('aria-disabled','true');element.insertAdjacentHTML('beforeend',lock);
  element.addEventListener('pointerenter',event=>{if(event.pointerType!=='touch')show(item);});
  element.addEventListener('pointerleave',leave);
  element.addEventListener('focus',()=>show(item));
  element.addEventListener('blur',()=>{if(current===item)leave();});
  element.addEventListener('click',event=>{event.preventDefault();event.stopImmediatePropagation();show(item);},true);
 }
 tip.addEventListener('pointerenter',()=>{clearTimeout(timer);current?.hold?.();});
 tip.addEventListener('pointerleave',()=>{current?.release?.();leave();});
 document.addEventListener('keydown',event=>{if(event.key==='Escape'&&current){close();event.stopImmediatePropagation();event.preventDefault();}},true);
 document.addEventListener('pointerdown',event=>{if(current&&!current.element.contains(event.target)&&!tip.contains(event.target))close();},true);
 window.addEventListener('resize',position);window.addEventListener('scroll',position,true);
 window.guestFeatureHint={bind,closeWithin:parent=>{if(current&&parent.contains(current.element))close();}};
 bind(document.querySelector('.nav-item[data-tab="focused"]'),'cross');
 bind(document.querySelector('#libraryCreateResearch'),'project');

 (window.workbenchSession?Promise.resolve(window.workbenchSession):fetch('/auth/me').then(r=>r.ok?r.json():null)).then(me=>{
  if(me?.role!=='guest')return;
  // Keep expiry enforcement without a persistent countdown or DOM updates.
  const remaining=me.guest.expires*1000-Date.now();
  if(Number.isFinite(remaining))setTimeout(()=>location.replace('/account'),Math.max(0,remaining));
 }).catch(()=>{});
})();
