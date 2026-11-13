// Desktop rail: use the actual navigation buttons as destinations, not a second route list.
(() => {
  const shell=document.querySelector('#shell'), sidebar=shell.querySelector('.sidebar');
  const toggle=sidebar.querySelector('#sideToggle'), desktop=matchMedia('(min-width:851px)');
  const groups=[...sidebar.querySelectorAll('.nav-group')];
  const compact=()=>desktop.matches && shell.classList.contains('collapsed');
  let host=null,panel=null,timer=0;
  const cancel=()=>clearTimeout(timer);
  function close(){
    cancel(); if(!panel)return;
    window.guestFeatureHint?.closeWithin(panel);
    host.setAttribute('aria-expanded','false');host.removeAttribute('aria-controls');
    panel.remove();panel=null;host=null;
  }
  function leave(){cancel();timer=setTimeout(close,240)}
  function position(){
    if(!panel)return;
    const a=host.getBoundingClientRect(),s=sidebar.getBoundingClientRect(),p=panel.firstChild;
    const bridge=Math.max(0,s.right-a.right)+4;
    panel.style.left=a.right+'px';panel.style.paddingLeft=bridge+'px';
    p.style.width=Math.min(204,innerWidth-a.right-bridge-8)+'px';
    panel.style.top=Math.max(6,Math.min(a.top,innerHeight-p.offsetHeight-6))+'px';
  }
  function open(button,focus=false){
    if(!compact())return;
    cancel();
    if(host!==button){
      close(); host=button;
      panel=document.createElement('div');panel.id='sidebar-rail-panel';panel.className='rail-panel';
      const menu=document.createElement('div');menu.className='settings-popover rail-menu';menu.dataset.settingsView='';
      menu.setAttribute('role','group');menu.setAttribute('aria-label',button.querySelector('em').textContent);
      const items=document.createElement('div');items.className='settings-menu';menu.append(items);
      for(const dest of button.closest('.nav-group').querySelectorAll('.nav-children .nav-item:not([hidden])')){
        if(window.WORKBENCH_GUEST&&['matrix','projectManage'].includes(dest.dataset.tab))continue;
        const row=document.createElement('button');row.type='button';row.className='settings-menu-item';
        const svg=dest.querySelector('svg')?.cloneNode(true);
        if(svg){svg.setAttribute('class','settings-menu-icon');row.append(svg)}
        const label=document.createElement('span'),strong=document.createElement('strong');
        strong.textContent=dest.querySelector('em')?.textContent||dest.textContent;label.append(strong);row.append(label);
        const locked=window.WORKBENCH_GUEST&&dest.dataset.tab==='focused';
        if(!locked)row.insertAdjacentHTML('beforeend','<svg class="settings-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="m9 6 6 6-6 6"/></svg>');
        if(dest.classList.contains('active'))row.setAttribute('aria-current','page');
        if(locked)window.guestFeatureHint?.bind(row,'cross',{hold:cancel,release:leave});
        else row.onclick=()=>{close();button.focus();dest.click()};
        items.append(row);
      }
      panel.append(menu);document.body.append(panel);
      button.setAttribute('aria-expanded','true');button.setAttribute('aria-controls',panel.id);
      panel.onpointerenter=cancel;panel.onpointerleave=leave;panel.onfocusin=cancel;
      panel.onkeydown=e=>{
        const rows=[...items.children],index=rows.indexOf(document.activeElement);
        if(['ArrowUp','ArrowDown'].includes(e.key)){e.preventDefault();rows[(index+(e.key==='ArrowDown'?1:-1)+rows.length)%rows.length]?.focus()}
        if(e.key==='Tab'&&((e.shiftKey&&index===0)||(!e.shiftKey&&index===rows.length-1))){
          const parents=groups.map(g=>g.querySelector('.nav-parent')),next=e.shiftKey?button:parents[parents.indexOf(button)+1]||sidebar.querySelector('.sidebar-settings');
          e.preventDefault();close();next.focus();
        }
      };
      position();
    }
    if(focus)panel.querySelector('button')?.focus();
  }
  function sync(){
    close();const name=compact()?'展开侧栏':'收起侧栏';
    toggle.title=name;toggle.setAttribute('aria-label',name);toggle.setAttribute('aria-expanded',String(!compact()));
    groups.forEach(g=>{
      const b=g.querySelector('.nav-parent'),label=b.querySelector('em');
      if(!label.id)label.id='rail-name-'+b.dataset.group;
      b.setAttribute('aria-labelledby',label.id);
      if(compact())b.setAttribute('aria-expanded','false');else b.removeAttribute('aria-expanded');
    });
  }
  toggle.innerHTML='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><rect x="2.5" y="4" width="19" height="16" rx="2"/><path d="M9 4v16"/></svg>';
  toggle.onclick=()=>{shell.classList.toggle('collapsed');sync()};
  for(const g of groups){
    const b=g.querySelector('.nav-parent');
    b.addEventListener('pointerenter',e=>{if(e.pointerType!=='touch')open(b)});
    b.addEventListener('pointerleave',()=>{if(host===b)leave()});
    b.addEventListener('click',e=>{if(!compact())return;e.stopImmediatePropagation();open(b,true)},true);
    b.addEventListener('keydown',e=>{if(compact()&&['ArrowRight','ArrowDown'].includes(e.key)){e.preventDefault();open(b,true)}});
  }
  document.addEventListener('keydown',e=>{if(e.key==='Escape'&&host){const b=host;close();b.focus();e.preventDefault()}});
  function outside(e){if(panel&&!panel.contains(e.target)&&!host.contains(e.target)&&!e.target.closest?.('.guest-feature-tip'))close()}
  document.addEventListener('pointerdown',outside,true);document.addEventListener('focusin',outside);
  window.addEventListener('resize',position);window.addEventListener('scroll',position,true);
  desktop.addEventListener('change',()=>{if(!desktop.matches)shell.classList.remove('collapsed');sync()});
  sync();
})();
