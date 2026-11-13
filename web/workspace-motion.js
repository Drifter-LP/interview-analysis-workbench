/* Animate live content only, never cloned editors or data refreshes. */
(() => {
 const transitions=new WeakMap(),entrances=new WeakMap(),indicators=new WeakMap();
 const reduced=()=>matchMedia('(prefers-reduced-motion: reduce)').matches;
 const easing='cubic-bezier(.2,.7,.3,1)';let updating=0,frame=0;
 function indicator(container,previous,next){
  indicators.get(container)?.();
  if(!previous||!next||previous===next||reduced())return;
  const a=previous.getBoundingClientRect(),b=next.getBoundingClientRect(),c=container.getBoundingClientRect();
  const position=container.style.position,border=next.style.borderBottomColor,line=document.createElement('span');
  if(getComputedStyle(container).position==='static')container.style.position='relative';
  next.style.borderBottomColor='transparent';line.className='workspace-sliding-underline';
  Object.assign(line.style,{position:'absolute',pointerEvents:'none',height:'3px',background:getComputedStyle(next).color,left:(b.left-c.left+container.scrollLeft)+'px',top:(b.bottom-c.top-3+container.scrollTop)+'px',width:b.width+'px',transformOrigin:'left center',zIndex:'2'});
  container.append(line);container.dataset.underlineMotion='running';
  const animation=line.animate([{transform:`translateX(${a.left-b.left}px) scaleX(${a.width/b.width})`},{transform:'none'}],{duration:200,easing});
  const clean=()=>{animation.cancel();line.remove();next.style.borderBottomColor=border;container.style.position=position;container.dataset.underlineMotion='finished';indicators.delete(container);};
  indicators.set(container,clean);animation.finished.then(clean,()=>{});
 }
 window.cancelWorkspaceTab=target=>transitions.get(target)?.cancel();
 window.slideWorkspaceTab=async function(target,update,direction=1,tabs=null,next=null){
  if(!target){update();return;}
  transitions.get(target)?.cancel();entrances.get(target)?.cancel();
  const previous=tabs?.querySelector('[aria-selected="true"],button.active');
  const state={animation:null,cancelled:false,cancel(){this.cancelled=true;this.animation?.cancel();}};
  transitions.set(target,state);
  const run=async frames=>{state.animation=target.animate(frames,{duration:100,easing});try{await state.animation.finished;}catch{}};
  try{
   if(!reduced()&&target.animate){target.dataset.tabMotion='out';await run([{opacity:1,transform:'translateX(0)'},{opacity:0,transform:`translateX(${-16*direction}px)`}]);}
   if(state.cancelled)return;
   updating++;try{update();}finally{updating--;}
   if(tabs&&next)indicator(tabs,previous,next);
   if(!reduced()&&target.animate){target.dataset.tabMotion='in';await run([{opacity:0,transform:`translateX(${16*direction}px)`},{opacity:1,transform:'translateX(0)'}]);}
  }finally{
   if(transitions.get(target)===state){target.dataset.tabMotion='idle';transitions.delete(target);}
  }
 };
 window.animateWorkspaceTransition=function(target,direction=1){
  if(!target?.animate||reduced()||updating||transitions.has(target))return;
  entrances.get(target)?.cancel();
  entrances.set(target,target.animate([{opacity:.35,transform:`translateX(${10*direction}px)`},{opacity:1,transform:'translateX(0)'}],{duration:150,easing}));
 };
 for(const name of ['switchView','switchTab']){
  const original=window[name];if(typeof original!=='function')continue;
  window[name]=function(...args){
   if(!updating)window.cancelWorkspaceTab(document.querySelector('#analysis'));
   const before=document.querySelector('.view.active')?.id+':'+document.querySelector('.tab-panel.active')?.id;
   const result=original.apply(this,args);
   const after=document.querySelector('.view.active')?.id+':'+document.querySelector('.tab-panel.active')?.id;
   if(before!==after&&!updating){cancelAnimationFrame(frame);frame=requestAnimationFrame(()=>{const view=document.querySelector('.view.active');window.animateWorkspaceTransition(view?.querySelector('.tab-panel.active')||view);});}
   return result;
  };
 }
 const labels=['访谈纪要','纪要结构','访谈编码','主题研究','词语探索','编码分布','分析结果','发现核查'];
 document.addEventListener('click',event=>{
  const button=event.target.closest('.workspace-tab-slot button,.workspace-header .research-view-segments button');
  if(!button||!labels.includes(button.textContent.trim())||!button.onclick||button.disabled)return;
  const target=document.querySelector('#analysis'),tabs=button.parentElement;
  if(button.classList.contains('active')&&!transitions.has(target))return;
  const previous=tabs.querySelector('button.active');
  const direction=previous&&button.getBoundingClientRect().left<previous.getBoundingClientRect().left?-1:1;
  event.preventDefault();event.stopImmediatePropagation();
  window.slideWorkspaceTab(target,()=>button.onclick.call(button,event),direction,tabs,button);
 },true);
})();
