/* Use geometric chevrons, not font glyphs with platform-dependent baselines. */
(()=>{
 const selector='button, summary';
 function normalize(root){
  const controls=[];
  if(root.nodeType===1&&root.matches(selector))controls.push(root);
  if(root.querySelectorAll)controls.push(...root.querySelectorAll(selector));
  for(const control of controls){
   const walker=document.createTreeWalker(control,NodeFilter.SHOW_TEXT);const nodes=[];let node;
   while(node=walker.nextNode())if(!node.parentElement.closest('.ui-chevron,svg'))nodes.push(node);
   for(const text of nodes){
    const match=text.textContent.match(/^(.*?)([⌄▾▿▼▴▵▲⌃])(\s*)$/u);
    if(!match)continue;
    text.textContent=match[1];
    const icon=document.createElement('span');icon.className='ui-chevron';icon.setAttribute('aria-hidden','true');icon.append(document.createTextNode(match[2]+match[3]));
    if(match[1].trim())icon.classList.add('ui-chevron-after-text');
    const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 12 12');
    const path=document.createElementNS('http://www.w3.org/2000/svg','path');path.setAttribute('d','M2 4 L6 8 L10 4');svg.append(path);icon.append(svg);
    if(/[▴▵▲⌃]/u.test(match[2]))icon.classList.add('ui-chevron-up');
    text.after(icon);
   }
  }
 }
 normalize(document);
 let pending=false;
 new MutationObserver(()=>{if(pending)return;pending=true;requestAnimationFrame(()=>{pending=false;normalize(document);});}).observe(document.body,{subtree:true,childList:true,characterData:true});
})();
