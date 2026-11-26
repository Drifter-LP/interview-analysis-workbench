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

  // Recent interviews share the same first/second-level navigation primitives.
  const recentBox=document.createElement('section');
  recentBox.className='nav-group open sb-recent-box';recentBox.id='sbRecentBox';
  recentBox.innerHTML='<button type="button" class="nav-parent" aria-expanded="true" aria-controls="sbRecentList"><svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg><em>最近访谈</em><b>⌄</b></button><div class="nav-children sb-recent-list" id="sbRecentList"></div>';
  sidebar.querySelector('nav').append(recentBox);
  const recentToggle=recentBox.querySelector('.nav-parent'),recentList=recentBox.querySelector('#sbRecentList');
  recentToggle.onclick=()=>{const open=recentBox.classList.toggle('open');recentToggle.setAttribute('aria-expanded',String(open));recentList.hidden=!open;};
  const quotaCard=document.createElement('button');
  quotaCard.type='button';quotaCard.className='sb-quota-card';quotaCard.id='sbQuotaCard';
  quotaCard.innerHTML='<div class="sb-quota-top"><span class="sb-quota-role" id="sbQuotaRole">今日额度</span><span class="sb-quota-nums" id="sbQuotaNums">—</span></div><div class="sb-quota-track" aria-hidden="true"><div class="sb-quota-fill" id="sbQuotaFill" style="width:0%"></div></div>';
  sidebar.insertBefore(quotaCard,settings);
  const arrow=document.createElement('span');arrow.className='sb-quota-arrow';arrow.setAttribute('aria-hidden','true');arrow.textContent='›';quotaCard.append(arrow);
  const quotaTip=document.createElement('div');quotaTip.id='sbQuotaTooltip';quotaTip.className='sb-quota-tooltip';quotaTip.setAttribute('role','tooltip');quotaTip.hidden=true;document.body.append(quotaTip);
  let quotaExplanation='正在读取额度…',tipTimer=0,tipDismissed=false;
  function hideQuotaTip(){clearTimeout(tipTimer);quotaTip.hidden=true;quotaCard.removeAttribute('aria-describedby');}
  function positionQuotaTip(){
    if(quotaTip.hidden)return;
    const a=quotaCard.getBoundingClientRect();if(!a.width||!a.height){hideQuotaTip();return;}
    quotaTip.style.left=Math.max(8,Math.min(a.right+10,innerWidth-quotaTip.offsetWidth-8))+'px';
    quotaTip.style.top=Math.max(8,Math.min(a.top,innerHeight-quotaTip.offsetHeight-8))+'px';
  }
  function showQuotaTip(){clearTimeout(tipTimer);if(tipDismissed)return;quotaTip.textContent=quotaExplanation;quotaTip.hidden=false;quotaCard.setAttribute('aria-describedby',quotaTip.id);positionQuotaTip();}
  function leaveQuotaTip(){clearTimeout(tipTimer);tipTimer=setTimeout(()=>{if(!quotaCard.matches(':hover')&&!quotaTip.matches(':hover')&&document.activeElement!==quotaCard)hideQuotaTip();},150);}
  quotaCard.addEventListener('pointerenter',event=>{if(event.pointerType!=='touch'){tipDismissed=false;showQuotaTip();}});
  quotaCard.addEventListener('pointerleave',leaveQuotaTip);
  quotaCard.addEventListener('focus',()=>{tipDismissed=false;showQuotaTip();});quotaCard.addEventListener('blur',leaveQuotaTip);
  quotaTip.addEventListener('pointerenter',()=>clearTimeout(tipTimer));quotaTip.addEventListener('pointerleave',leaveQuotaTip);
  document.addEventListener('keydown',event=>{if(event.key==='Escape'&&!quotaTip.hidden){tipDismissed=true;hideQuotaTip();event.stopPropagation();}},true);
  window.addEventListener('resize',hideQuotaTip);document.addEventListener('scroll',positionQuotaTip,true);
  quotaCard.onclick=()=>{tipDismissed=true;hideQuotaTip();if((window.workbenchSession||accountsEnabled)&&window.openAccountDrawer)window.openAccountDrawer();else settings.click();};
  function explainQuota(text){quotaExplanation=text;quotaCard.removeAttribute('title');if(!quotaTip.hidden){quotaTip.textContent=text;positionQuotaTip();}}
  let recentSignature='',recentOpenSerial=0,quotaPending=false;
  function updateSidebarWidgets(){
    if(document.hidden)return;
    const rows=typeof projects!=='undefined'&&Array.isArray(projects)?projects:[];
    const currentId=typeof selected!=='undefined'?selected:null;
    const sorted=rows.filter(p=>!p.hidden_in_library&&p.status==='completed').sort((a,b)=>(b.last_opened_at||b.created_at||0)-(a.last_opened_at||a.created_at||0)).slice(0,4);
    const libraryStatus=document.querySelector('#projectList>[role="status"]')?.textContent||'';
    const waiting=!sorted.length&&/正在读取访谈资料|访谈资料读取失败/.test(libraryStatus);
    const signature=JSON.stringify([currentId,waiting?libraryStatus:'',sorted.map(p=>[p.id,p.name,p.edited_at,p.last_opened_at])]);
    if(signature===recentSignature)return;recentSignature=signature;
    if(waiting||!sorted.length){
      const status=document.createElement('div');status.className='sb-recent-empty';status.setAttribute('role','status');
      status.textContent=waiting?(libraryStatus.includes('失败')?'资料读取失败，请在资料页重试':'正在读取最近访谈…'):'暂无最近访谈';
      recentList.replaceChildren(status);return;
    }
    recentList.replaceChildren(...sorted.map(item=>{
      const revised=!!item.edited_at,fullName=String(item.name||'未命名访谈'),chars=Array.from(fullName);
      const btn=document.createElement('button');btn.type='button';btn.className='nav-item sb-recent-item';btn.dataset.projectId=String(item.id);
      if(String(currentId)===String(item.id))btn.setAttribute('aria-current','page');
      const status=revised?'已修订，打开单篇访谈分析':'未修订，打开文字校订';
      btn.title=fullName+'（'+status+'）';btn.setAttribute('aria-label',fullName+'，'+status);
      btn.innerHTML='<svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M6 3h8l4 4v14H6zM14 3v5h4M9 12h6M9 16h6"/></svg>';
      const name=document.createElement('em');name.className='sb-recent-name';name.textContent=chars.length>5?chars.slice(0,5).join('')+'…':fullName;
      const dot=document.createElement('span');dot.className='sb-recent-dot'+(revised?'':' is-review');dot.setAttribute('aria-hidden','true');btn.append(name,dot);
      btn.onclick=async()=>{
        const serial=++recentOpenSerial,isCurrent=()=>serial===recentOpenSerial;
        try{
          const options=revised?{targetTab:'familiarity',isCurrent}:{transcriptFirst:true,isCurrent};
          if(!await openProject(item.id,null,options)||!isCurrent())return;
          if(revised)switchView('analysis','familiarity');
          item.last_opened_at=Date.now()/1000;updateSidebarWidgets();
          api('/api/projects/'+encodeURIComponent(item.id)+'/opened',{method:'POST'}).then(result=>{item.last_opened_at=result.last_opened_at;updateSidebarWidgets();}).catch(error=>toast('最近打开记录未更新：'+error.message));
        }catch(error){if(isCurrent())toast(error.message);}
      };return btn;
    }));
  }
  async function refreshSidebarQuota(){
    if(quotaPending||document.hidden)return;
    const label=quotaCard.querySelector('#sbQuotaRole'),nums=quotaCard.querySelector('#sbQuotaNums'),fill=quotaCard.querySelector('#sbQuotaFill'),track=fill.parentElement;
    if(!window.workbenchSession&&!accountsEnabled){label.textContent='本地工作台';nums.textContent='设置';track.hidden=true;explainQuota('点击打开本地工作台设置');return;}
    try{
      quotaPending=true;const r=await fetch('/auth/me');if(!r.ok)throw Error();
      const me=await r.json(),admin=me.role==='admin',guest=me.role==='guest',used=Number(me.usage?.calls),limit=Number(me.daily_calls);
      if(!Number.isFinite(used)||(!admin&&!(limit>0)))throw Error();
      label.textContent=guest?'试用额度':'今日额度';nums.textContent=used+' / '+(admin?'∞':limit)+' 次';
      track.hidden=false;fill.style.width=(admin?100:Math.min(100,used/limit*100))+'%';
      const hint=admin?'管理员每日额度不限':guest?'访客空间累计额度，不按日重置':'北京时间每天08:00重置';
      explainQuota('已用：'+used+' 次\n剩余：'+(admin?'不限':Math.max(0,limit-used)+' 次')+'\n'+hint+'\n点击查看账号与额度详情');
      quotaCard.setAttribute('aria-label',label.textContent+'：'+nums.textContent+'。'+hint+'。点击查看账号与额度');
    }catch{nums.textContent='暂不可用';track.hidden=true;explainQuota('额度读取失败，点击查看详情或重试');quotaCard.setAttribute('aria-label','额度暂不可用，点击查看详情或重试');}
    finally{quotaPending=false;}
  }
  window.updateSidebarWidgets=updateSidebarWidgets;window.refreshSidebarQuota=refreshSidebarQuota;
  document.addEventListener('interview-library-updated',updateSidebarWidgets);
  document.addEventListener('click',()=>requestAnimationFrame(updateSidebarWidgets));
  setTimeout(()=>{updateSidebarWidgets();refreshSidebarQuota();},250);
  setInterval(()=>{updateSidebarWidgets();},2500);
  setInterval(refreshSidebarQuota,60000);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden){updateSidebarWidgets();refreshSidebarQuota();}});
})();
