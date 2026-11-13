/* Presentation/accessibility adapter; existing destination/action handlers stay intact. */
(() => {
 const definitions=[
   ['.library-project-menu','.library-project-dots','.library-project-actions',false],
   ['.library-menu','.library-dots','.library-row-actions',false],
   ['.library-move-submenu','.library-move-trigger','.library-menu',true],
   ['.research-result-menu','.research-result-trigger','.research-result-picker',false]
 ];
 const icons={
   manage:'M4 5h16v15H4zM8 5V3h8v2M8 10h8M8 15h8',
   remove:'M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13M10 10v7M14 10v7',
   move:'M3 7h7l2 2h9v11H3zM3 7V4h7l2 3M9 14h8m-3-3 3 3-3 3',
   folder:'M3 7h7l2 2h9v11H3zM3 7V4h7l2 3',
   text:'M5 4h14v16H5zM8 8h8M8 12h8M8 16h5',
   tree:'M12 3v7M5 15v-5h14v5M3 15h4v5H3zM10 15h4v5h-4zM17 15h4v5h-4z'
 };
 let serial=0,queued=false;
 const pairs=()=>definitions.flatMap(([selector,trigger,wrap,nested])=>[...document.querySelectorAll(selector)].map(menu=>({menu,trigger:menu.closest(wrap)?.querySelector(trigger),nested}))).filter(p=>p.trigger);
 const visible=p=>!p.menu.hidden&&p.menu.isConnected&&p.trigger.getClientRects().length>0;
 const rows=p=>[...p.menu.children].filter(n=>n.tagName==='BUTTON'&&!n.hidden&&!n.disabled);
 function close(p,focus=false){
   if(p.menu.matches(':popover-open'))p.menu.hidePopover();
   p.menu.hidden=true;p.trigger.setAttribute('aria-expanded','false');
   for(const child of pairs().filter(x=>p.menu.contains(x.trigger))) {if(child.menu.matches(':popover-open'))child.menu.hidePopover();child.menu.hidden=true;child.trigger.setAttribute('aria-expanded','false')}
   if(focus&&p.trigger.isConnected)p.trigger.focus();
 }
 function position(p){
   if(!visible(p))return;
   if(typeof p.menu.showPopover==='function'&&!p.menu.matches(':popover-open'))p.menu.showPopover();
   const r=p.trigger.getBoundingClientRect(),m=p.menu.getBoundingClientRect(),pad=12,gap=4;
   let x=p.nested?(r.left-m.width-gap>=pad?r.left-m.width-gap:r.right+gap):r.right-m.width;
   let y=p.nested?r.top:(r.bottom+gap+m.height<=innerHeight-pad?r.bottom+gap:r.top-m.height-gap);
   p.menu.style.setProperty('--wb-menu-x',Math.max(pad,Math.min(x,innerWidth-m.width-pad))+'px');
   p.menu.style.setProperty('--wb-menu-y',Math.max(pad,Math.min(y,innerHeight-m.height-pad))+'px');
 }
 function open(p,focus=false){
   for(const other of pairs())if(other.menu!==p.menu&&!other.menu.contains(p.trigger)&&!p.menu.contains(other.trigger))close(other);
   p.menu.hidden=false;p.trigger.setAttribute('aria-expanded','true');position(p);if(focus)rows(p)[0]?.focus();
 }
 function decorate(p){
   if(!p.menu.id)p.menu.id='wb-short-menu-'+(++serial);
   p.menu.classList.add('wb-menu-fixed');p.trigger.setAttribute('aria-controls',p.menu.id);p.trigger.setAttribute('aria-haspopup','menu');
   if(typeof p.menu.showPopover==='function'&&!p.menu.hasAttribute('popover'))p.menu.setAttribute('popover','manual');
   if(!p.menu.hidden&&!p.trigger.getClientRects().length)close(p);
   if((p.menu.hidden||!p.trigger.getClientRects().length)&&p.menu.matches(':popover-open'))p.menu.hidePopover();
   p.trigger.setAttribute('aria-expanded',String(!p.menu.hidden));
   if(!p.menu.hasAttribute('role'))p.menu.setAttribute('role','menu');
   for(const row of [...p.menu.children].filter(n=>n.tagName==='BUTTON')){
     if(!row.hasAttribute('role'))row.setAttribute('role','menuitem');
     if(row.dataset.wbDecorated)continue;
     row.dataset.wbDecorated='true';
     const label=row.textContent.replace(/^▱\s*/,'').replace(/\s*›$/,'').trim();
     const kind=row.matches('[data-manage-project]')?'manage':row.matches('[data-delete]')||label==='删除项目'?'remove':row.matches('.library-move-trigger')?'move':p.nested?'folder':label==='发现树'?'tree':'text';
     const icon=document.createElementNS('http://www.w3.org/2000/svg','svg');icon.setAttribute('viewBox','0 0 24 24');icon.setAttribute('class','wb-menu-icon');icon.setAttribute('aria-hidden','true');
     const path=document.createElementNS(icon.namespaceURI,'path');path.setAttribute('d',icons[kind]);icon.append(path);
     const span=document.createElement('span');span.className='wb-menu-label';span.textContent=label;
     row.replaceChildren(icon,span);
     if(row.matches('.library-move-trigger'))row.insertAdjacentHTML('beforeend','<svg class="wb-menu-next" viewBox="0 0 24 24" aria-hidden="true"><path d="m9 6 6 6-6 6"/></svg>');
   }
   position(p);
 }
 function scan(){queued=false;for(const p of pairs())decorate(p)}
 function schedule(){if(!queued){queued=true;queueMicrotask(scan)}}
 new MutationObserver(schedule).observe(document.body,{subtree:true,childList:true,attributes:true,attributeFilter:['hidden']});
 document.addEventListener('pointerdown',e=>{for(const p of pairs())if(visible(p)&&!p.menu.contains(e.target)&&!p.trigger.contains(e.target))close(p)},true);
 document.addEventListener('click',e=>{
   const all=pairs(),trigger=all.find(p=>p.trigger.contains(e.target));
   if(trigger){if(!trigger.menu.hidden)open(trigger);return}
   const own=all.filter(p=>p.menu.contains(e.target)).at(-1);
   if(!own||!e.target.closest('button')||e.target.closest('button').disabled)return;
   // After the original click callback: close short menus without touching
   // a newly opened editing/confirmation dialog or changing its focus.
   queueMicrotask(()=>{
     const top=all.find(p=>!p.nested&&p.menu.contains(own.trigger))||own;
     close(top);
     if(document.activeElement===document.body&&top.trigger.isConnected)top.trigger.focus();
   });
 });
 document.addEventListener('keydown',e=>{
   const all=pairs(),focused=document.activeElement;
   const active=all.filter(p=>visible(p)&&p.menu.contains(focused)).at(-1);
   const trigger=all.find(p=>p.trigger===focused);
   if(trigger&&['ArrowDown','ArrowRight'].includes(e.key)){e.preventDefault();e.stopImmediatePropagation();open(trigger,true);return}
   if(e.key==='Escape'){
     const p=active||all.filter(visible).at(-1);
     if(p){e.preventDefault();e.stopImmediatePropagation();close(p,true)}return;
   }
   if(!active)return;
   const items=rows(active),index=items.indexOf(focused);
   if(['ArrowDown','ArrowUp','Home','End'].includes(e.key)){
     e.preventDefault();e.stopImmediatePropagation();
     const next=e.key==='Home'?0:e.key==='End'?items.length-1:(index+(e.key==='ArrowDown'?1:-1)+items.length)%items.length;items[next]?.focus();
   }else if(e.key==='ArrowLeft'&&active.nested){e.preventDefault();e.stopImmediatePropagation();close(active,true)}
   else if(e.key==='Tab')close(active);
 },true);
 document.addEventListener('focusin',e=>{for(const p of pairs())if(visible(p)&&!p.menu.contains(e.target)&&!p.trigger.contains(e.target))close(p)});
 window.addEventListener('resize',()=>pairs().filter(visible).forEach(position));
 document.addEventListener('scroll',()=>pairs().filter(visible).forEach(position),true);
 scan();
})();
