(() => {
  const sidebar=document.querySelector('.sidebar');
  const logo=document.createElementNS('http://www.w3.org/2000/svg','svg');
  logo.setAttribute('viewBox','0 0 48 48');logo.setAttribute('class','sidebar-logo');logo.setAttribute('aria-hidden','true');
  logo.innerHTML='<path d="M13 32 25 14 37 32" fill="none" stroke="currentColor" stroke-width="5" opacity=".55"/><g fill="currentColor"><circle cx="25" cy="12" r="7"/><circle cx="11" cy="32" r="7"/><circle cx="37" cy="32" r="7"/></g>';
  if(!sidebar.querySelector('.sidebar-logo'))sidebar.querySelector('.side-top').prepend(logo);
  const card=sidebar.querySelector('.system-card');
  const state=document.querySelector('#systemState');
  const syncState=()=>{const text=state.textContent;const ready=document.querySelector('#readyDot').classList.contains('ready');state.textContent=ready?'本地服务已就绪':text.includes('检查')?'正在检查本地服务':'本地模型尚未就绪';};
  const observer=new MutationObserver(()=>{observer.disconnect();syncState();observer.observe(state,{childList:true});});observer.observe(state,{childList:true});syncState();
  const settings=sidebar.querySelector('.sidebar-settings')||document.createElement('button');settings.type='button';settings.className='sidebar-settings';settings.setAttribute('aria-label','设置');
  settings.innerHTML='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" aria-hidden="true"><path d="m9 3 1-1h4l1 3 3 1 3-1 2 4-2 2v3l2 2-2 4-3-1-3 1-1 3h-4l-1-3-3-1-3 1-2-4 2-2v-3l-2-2 2-4 3 1z"/><circle cx="12" cy="12" r="3"/></svg><span>设置</span>';
  let openSettings=null;
  let accountsEnabled=!!document.querySelector('script[data-workbench-accounts]');
  // Compatibility with an already-running gateway which injected a separate
  // sidebar link. Consolidate it without restarting active analysis workers.
  function consolidateAccountEntry(){
    const entry=sidebar.querySelector('a[href="/account"]');
    accountsEnabled=accountsEnabled||!!entry;
    entry?.remove();
  }
  if(document.readyState!=='complete')document.addEventListener('DOMContentLoaded',consolidateAccountEntry,{once:true});
  else consolidateAccountEntry();
  settings.setAttribute('aria-haspopup','dialog');settings.setAttribute('aria-expanded','false');
  settings.onclick=()=>{
    consolidateAccountEntry();
    if(openSettings){openSettings();return;}
    const dialog=document.createElement('div');dialog.className='sidebar-settings-dialog settings-popover';
    dialog.setAttribute('popover','auto');dialog.setAttribute('role','dialog');dialog.setAttribute('aria-label','设置');
    let removed=false,frame=0;
    function closePanel(){
      if(removed)return;removed=true;cancelAnimationFrame(frame);
      resizeObserver.disconnect();window.removeEventListener('resize',schedulePosition);document.removeEventListener('scroll',schedulePosition,true);
      document.removeEventListener('pointerdown',outside,true);document.removeEventListener('keydown',escape,true);
      if(dialog.matches(':popover-open'))dialog.hidePopover();dialog.remove();openSettings=null;settings.setAttribute('aria-expanded','false');
    }
    function outside(event){if(!dialog.contains(event.target)&&!settings.contains(event.target))closePanel();}
    function escape(event){if(event.key==='Escape'){event.preventDefault();closePanel();settings.focus();}}
    function position(){
      if(removed)return;
      const anchor=settings.getBoundingClientRect(),vw=document.documentElement.clientWidth,vh=window.innerHeight,gap=8,pad=12;
      if(anchor.bottom<0||anchor.top>vh){closePanel();return;}
      const preferredWidth=current==='config'?340:current==='trash'?360:184;
      const width=Math.min(preferredWidth,vw-pad*2);
      dialog.style.width=width+'px';dialog.style.maxHeight=Math.max(100,vh-pad*2)+'px';
      const height=dialog.getBoundingClientRect().height;
      let x,y;
      x=anchor.left;
      y=anchor.top>=height+gap+pad?anchor.top-height-gap:anchor.bottom+gap;
      dialog.style.left=Math.max(pad,Math.min(x,vw-width-pad))+'px';
      dialog.style.top=Math.max(pad,Math.min(y,vh-height-pad))+'px';
    }
    function schedulePosition(){cancelAnimationFrame(frame);frame=requestAnimationFrame(position);}
    const resizeObserver=new ResizeObserver(schedulePosition);
    const head=document.createElement('div');head.className='dialog-head';
    const left=document.createElement('div');left.className='settings-heading';
    const back=document.createElement('button');back.type='button';back.className='settings-back';back.title='返回设置';back.setAttribute('aria-label','返回设置');
    back.innerHTML='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m14 6-6 6 6 6"/></svg>';
    const title=document.createElement('h2');left.append(back,title);
    const close=document.createElement('button');close.type='button';close.className='icon-btn';close.setAttribute('aria-label','关闭设置');close.textContent='×';close.onclick=()=>{closePanel();settings.focus();};
    head.append(left,close);const body=document.createElement('div');body.className='settings-content';dialog.append(head,body);
    let current='';
    function show(view){
      current=view;dialog.dataset.settingsView=view;head.hidden=!view;back.hidden=!view;title.textContent=view==='config'?'配置':view==='trash'?'回收站':'设置';body.replaceChildren();schedulePosition();
      if(view==='config'){
        for(const [label,id] of [['本地服务','systemState'],['计算设备与转录模型','gpuState'],['分析服务','aiState']]){
          const group=document.createElement('div');group.className='settings-config-row';
          const heading=document.createElement('h3');heading.textContent=label;
          const value=document.createElement('p');value.textContent=document.getElementById(id).textContent;group.append(heading,value);body.append(group);
        }
      }else if(view==='trash')window.installInterviewTrash?.(body);
      else{
        const menu=document.createElement('div');menu.className='settings-menu';
        for(const [key,label,path] of [
          ['config','配置','M4 7h16M4 17h16M8 4v6M16 14v6'],
          ['trash','回收站','M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13M10 10v7M14 10v7'],
          ...(accountsEnabled?[['account','账号与额度','M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0M4 21v-2a8 8 0 0 1 16 0v2']]:[])
        ]){
          const button=document.createElement('button');button.type='button';button.className='settings-menu-item';button.setAttribute('aria-label',label);
          button.innerHTML='<svg class="settings-menu-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="'+path+'"/></svg><span><strong>'+label+'</strong></span><svg class="settings-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m9 6 6 6-6 6"/></svg>';
          button.onclick=()=>{if(key==='account'){closePanel();if(window.openAccountDrawer)window.openAccountDrawer();else window.location.assign('/account');return;}show(key);back.focus();};menu.append(button);
        }
        body.append(menu);
      }
    }
    back.onclick=()=>{const previous=current;show('');body.querySelector('[aria-label="'+(previous==='config'?'配置':'回收站')+'"]').focus();};
    dialog.addEventListener('toggle',event=>{if(event.newState==='closed')closePanel();});
    show('');document.body.append(dialog);openSettings=closePanel;settings.setAttribute('aria-expanded','true');
    if(typeof dialog.showPopover==='function')dialog.showPopover();
    else dialog.removeAttribute('popover');
    position();resizeObserver.observe(dialog);window.addEventListener('resize',schedulePosition);document.addEventListener('scroll',schedulePosition,true);
    document.addEventListener('pointerdown',outside,true);document.addEventListener('keydown',escape,true);
    body.querySelector('button')?.focus();
  };sidebar.append(settings);
})();
