/* Entrance-only motion: no delayed navigation, screenshots, or layout animation. */
(() => {
 const animations=new WeakMap();let frame=0;
 window.animateWorkspaceTransition=function(target,direction=1){
  if(!target||!target.animate||matchMedia('(prefers-reduced-motion: reduce)').matches)return;
  animations.get(target)?.cancel();
  const animation=target.animate([{opacity:.35,transform:`translateX(${10*direction}px)`},{opacity:1,transform:'translateX(0)'}],{duration:150,easing:'cubic-bezier(.2,.7,.3,1)'});
  animations.set(target,animation);
 };
 for(const name of ['switchView','switchTab']){
  const original=window[name];if(typeof original!=='function')continue;
  window[name]=function(...args){
   const previous=document.querySelector('.view.active')?.id+':'+document.querySelector('.tab-panel.active')?.id;
   const result=original.apply(this,args);
   const current=document.querySelector('.view.active')?.id+':'+document.querySelector('.tab-panel.active')?.id;
   if(current!==previous){cancelAnimationFrame(frame);frame=requestAnimationFrame(()=>{const view=document.querySelector('.view.active');window.animateWorkspaceTransition(view?.querySelector('.tab-panel.active')||view);});}
   return result;
  };
 }
 let tabFrame=0,underline=null,restoreBorder=null;
 document.addEventListener('click',event=>{
  const button=event.target.closest('.workspace-tab-slot button');
  if(!button||!['访谈纪要','纪要结构','访谈编码','主题研究','词语探索','编码分布'].includes(button.textContent.trim())||button.classList.contains('active'))return;
  if(matchMedia('(prefers-reduced-motion: reduce)').matches)return;
  const slot=button.closest('.workspace-tab-slot'),previous=slot.querySelector('button.active');
  if(!previous)return;
  const before=previous.getBoundingClientRect(),direction=button.getBoundingClientRect().left>=before.left?1:-1;
  cancelAnimationFrame(tabFrame);underline?.remove();restoreBorder?.();
  tabFrame=requestAnimationFrame(()=>{tabFrame=requestAnimationFrame(()=>{
   if(!button.isConnected||!button.classList.contains('active'))return;
   const after=button.getBoundingClientRect(),line=document.createElement('span'),border=button.style.borderBottomColor;
   underline=line;restoreBorder=()=>{button.style.borderBottomColor=border;restoreBorder=null;};
   button.style.borderBottomColor='transparent';
   Object.assign(line.style,{position:'fixed',pointerEvents:'none',zIndex:'25',height:'2px',background:'#009e96',left:after.left+'px',top:(after.bottom-2)+'px',width:after.width+'px',transformOrigin:'left center'});
   document.body.append(line);
   line.className='workspace-sliding-underline';
   slot.dataset.underlineFrom=String(before.left);slot.dataset.underlineTo=String(after.left);slot.dataset.underlineMotion='running';
   const animation=line.animate([{transform:`translateX(${before.left-after.left}px) scaleX(${before.width/after.width})`},{transform:'translateX(0) scaleX(1)'}],{duration:240,easing:'cubic-bezier(.2,.7,.3,1)'});
   animation.onfinish=()=>{line.remove();if(underline===line){underline=null;restoreBorder?.();slot.dataset.underlineMotion='finished';}};
   const view=document.querySelector('.view.active'),panel=view?.querySelector('.tab-panel.active'),structure=document.querySelector('#memoStructure');
   window.animateWorkspaceTransition(panel?.id==='familiarity'&&structure&&!structure.hidden?structure:panel||view,direction);
  });});
 },true);
})();
