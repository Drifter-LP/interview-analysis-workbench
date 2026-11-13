// Shared enter/leave lifecycle. Native close occurs only after the exit finishes.
(() => {
 window.attachDrawerMotion=function(drawer){
   if(drawer.dataset.drawerAnimated)return drawer;
   drawer.dataset.drawerAnimated='true';
   const show=drawer.showModal.bind(drawer),close=drawer.close.bind(drawer);
   let animation=null,closing=false,opener=null,generation=0;
   const reduced=()=>matchMedia('(prefers-reduced-motion: reduce)').matches;
   const restore=()=>{if(opener?.isConnected&&opener!==document.body)opener.focus({preventScroll:true})};
   drawer.showModal=function(){
     if(drawer.open)return;
     opener=document.activeElement;closing=false;const version=++generation;
     drawer.dataset.drawerMotion=reduced()?'open':'opening';show();
     if(reduced())return;
     animation=drawer.animate([{transform:'translateX(100%)'},{transform:'translateX(0)'}],{duration:220,easing:'cubic-bezier(.2,.75,.25,1)',fill:'both'});
     animation.finished.then(()=>{if(version!==generation)return;animation.cancel();animation=null;drawer.dataset.drawerMotion='open'}).catch(()=>{});
   };
   drawer.close=function(value){
     if(!drawer.open||closing)return;
     closing=true;const version=++generation,current=getComputedStyle(drawer).transform;
     animation?.cancel();drawer.dataset.drawerMotion='closing';
     const finish=()=>{
       if(version!==generation)return;
       close(value);animation?.cancel();animation=null;closing=false;drawer.dataset.drawerMotion='closed';restore();
     };
     if(reduced()){finish();return}
     animation=drawer.animate([{transform:current==='none'?'translateX(0)':current},{transform:'translateX(100%)'}],{duration:180,easing:'cubic-bezier(.4,0,.8,.3)',fill:'both'});
     animation.finished.then(finish).catch(()=>{});
   };
   // Attach after a drawer's own cancel handler, so unsaved state or an open
   // nested menu can consume Esc without closing the whole drawer.
   drawer.addEventListener('cancel',e=>{if(e.defaultPrevented)return;e.preventDefault();drawer.close()});
   drawer.addEventListener('click',e=>{
     if(e.target!==drawer)return;
     const r=drawer.getBoundingClientRect();
     if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)drawer.close();
   });
   return drawer;
 };
 window.createEvidenceDrawer=function(titleText){
   const drawer=document.createElement('dialog');drawer.className='wc-source-drawer';drawer.setAttribute('aria-label',titleText);
   const head=document.createElement('header'),title=document.createElement('strong'),button=document.createElement('button'),note=document.createElement('p'),body=document.createElement('div');
   title.textContent=titleText;button.type='button';button.textContent='×';button.setAttribute('aria-label','关闭原文');button.onclick=()=>drawer.close();
   head.append(title,button);note.className='wc-source-note';body.className='wc-source-body';
   body.setAttribute('role','region');body.setAttribute('aria-label','只读原文');
   drawer.append(head,note,body);document.body.append(drawer);drawer.addEventListener('close',()=>drawer.remove());
   window.attachDrawerMotion(drawer);drawer.showModal();return{drawer,note,body};
 };
})();
