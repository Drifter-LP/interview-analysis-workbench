(() => {
  const sidebar=document.querySelector('.sidebar');
  const logo=document.createElementNS('http://www.w3.org/2000/svg','svg');
  logo.setAttribute('viewBox','0 0 48 48');logo.setAttribute('class','sidebar-logo');logo.setAttribute('aria-hidden','true');
  logo.innerHTML='<path d="M13 32 25 14 37 32" fill="none" stroke="currentColor" stroke-width="5" opacity=".55"/><g fill="currentColor"><circle cx="25" cy="12" r="7"/><circle cx="11" cy="32" r="7"/><circle cx="37" cy="32" r="7"/></g>';
  sidebar.querySelector('.side-top').prepend(logo);
  const card=sidebar.querySelector('.system-card');
  const state=document.querySelector('#systemState');
  const syncState=()=>{const text=state.textContent;const ready=document.querySelector('#readyDot').classList.contains('ready');state.textContent=ready?'本地服务已就绪':text.includes('检查')?'正在检查本地服务':'本地模型尚未就绪';};
  const observer=new MutationObserver(()=>{observer.disconnect();syncState();observer.observe(state,{childList:true});});observer.observe(state,{childList:true});syncState();
  const settings=document.createElement('button');settings.type='button';settings.className='sidebar-settings';settings.setAttribute('aria-label','设置');
  settings.innerHTML='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" aria-hidden="true"><path d="m9 3 1-1h4l1 3 3 1 3-1 2 4-2 2v3l2 2-2 4-3-1-3 1-1 3h-4l-1-3-3-1-3 1-2-4 2-2v-3l-2-2 2-4 3 1z"/><circle cx="12" cy="12" r="3"/></svg><span>设置</span>';
  settings.onclick=()=>{const dialog=document.createElement('dialog');dialog.className='sidebar-settings-dialog';const head=document.createElement('div');head.className='dialog-head';const title=document.createElement('h2');title.textContent='设置';const close=document.createElement('button');close.type='button';close.className='icon-btn';close.setAttribute('aria-label','关闭设置');close.textContent='×';close.onclick=()=>dialog.close();head.append(title,close);dialog.append(head);for(const [label,id] of [['本地服务','systemState'],['计算设备与转录模型','gpuState'],['分析服务','aiState']]){const heading=document.createElement('h3');heading.textContent=label;const value=document.createElement('p');value.textContent=document.getElementById(id).textContent;dialog.append(heading,value);}dialog.addEventListener('close',()=>dialog.remove(),{once:true});document.body.append(dialog);dialog.showModal();};card.append(settings);
})();
