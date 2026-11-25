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

  // --- Sidebar Enrichment: Badges, Recent Interviews Switcher & Quota Mini-Card ---
  const navEl=sidebar.querySelector('nav');
  const recentBox=document.createElement('section');
  recentBox.className='sb-recent-box';recentBox.id='sbRecentBox';recentBox.setAttribute('aria-label','最近打开的访谈');
  recentBox.innerHTML='<div class="sb-recent-head"><span>最近访谈</span><small id="sbRecentCount"></small></div><div class="sb-recent-list" id="sbRecentList"></div>';
  if(navEl)navEl.after(recentBox);

  const quotaCard=document.createElement('button');
  quotaCard.type='button';quotaCard.className='sb-quota-card';quotaCard.id='sbQuotaCard';
  quotaCard.setAttribute('aria-label','查看账号与今日调用额度');
  quotaCard.innerHTML='<div class="sb-quota-top"><span class="sb-quota-role" id="sbQuotaRole">工作台状态</span><span class="sb-quota-nums" id="sbQuotaNums">—</span></div><div class="sb-quota-track" aria-hidden="true"><div class="sb-quota-fill" id="sbQuotaFill" style="width:0%"></div></div><small class="sb-quota-sub" id="sbQuotaSub">点击查看账号与额度详情</small>';
  sidebar.insertBefore(quotaCard,settings);
  quotaCard.onclick=()=>{
    if((window.workbenchSession||accountsEnabled)&&window.openAccountDrawer)window.openAccountDrawer();
    else settings.click();
  };
  let recentSignature='',recentOpenSerial=0,quotaPending=false;

  function ensureBadge(selector){
    const item=sidebar.querySelector(selector);
    if(!item)return null;
    let badge=item.querySelector('.sb-nav-badge');
    if(!badge){
      badge=document.createElement('span');
      badge.className='sb-nav-badge';
      badge.hidden=true;
      item.append(badge);
    }
    return badge;
  }

  function updateSidebarWidgets(){
    if(document.hidden)return;
    const allProjects=Array.isArray(window.projects)?window.projects:(typeof projects!=='undefined'&&Array.isArray(projects)?projects:[]);
    const allResearch=Array.isArray(window.researchProjects)?window.researchProjects:(typeof researchProjects!=='undefined'&&Array.isArray(researchProjects)?researchProjects:[]);
    const currentId=typeof selected!=='undefined'?selected:null;
    const currentAnalysis=typeof analysisData!=='undefined'?analysisData:null;

    const visible=allProjects.filter(p=>!p.hidden_in_library);
    const completed=visible.filter(p=>p.status==='completed');
    const pendingReview=completed.filter(p=>!p.edited_at);

    // 1. Update Navigation Badges
    const bWorkspace=ensureBadge('.nav-item[data-view="workspace"]');
    if(bWorkspace){
      bWorkspace.hidden=!visible.length;
      bWorkspace.textContent=String(visible.length);
    }
    const bEditor=ensureBadge('.nav-item[data-view="editor"]');
    if(bEditor){
      if(pendingReview.length){
        bEditor.hidden=false;
        bEditor.classList.add('is-warn');
        bEditor.textContent=pendingReview.length+' 待校';
      }else{
        bEditor.hidden=true;
        bEditor.classList.remove('is-warn');
      }
    }
    const bSingle=ensureBadge('.nav-item[data-tab="familiarity"]');
    if(bSingle){
      const codeCount=(currentAnalysis?.codes||[]).length;
      if(codeCount>0){
        bSingle.hidden=false;
        bSingle.textContent=codeCount+' 编码';
      }else if(completed.length>0){
        bSingle.hidden=false;
        bSingle.textContent=completed.length+' 篇';
      }else{
        bSingle.hidden=true;
      }
    }
    if(!window.WORKBENCH_GUEST){
      const bCross=ensureBadge('.nav-item[data-tab="focused"]');
      if(bCross){
        if(allResearch.length>0){
          bCross.hidden=false;
          bCross.textContent=allResearch.length+' 项目';
        }else{
          bCross.hidden=true;
        }
      }
    }

    // 2. Update Recent Interviews Quick List
    const recentList=document.getElementById('sbRecentList');
    const recentCount=document.getElementById('sbRecentCount');
    if(recentList&&recentCount){
      const sorted=[...completed].sort((a,b)=>(b.last_opened_at||b.created_at||0)-(a.last_opened_at||a.created_at||0));
      const libraryStatus=document.querySelector('#projectList>[role="status"]')?.textContent||'';
      const waiting=!sorted.length&&/正在读取访谈资料|访谈资料读取失败/.test(libraryStatus);
      const signature=JSON.stringify([currentId,completed.length,waiting?libraryStatus:'',sorted.slice(0,4).map(p=>[p.id,p.name,p.edited_at,p.last_opened_at])]);
      if(signature===recentSignature)return;
      recentSignature=signature;
      recentCount.textContent=completed.length?completed.length+' 篇':'';
      if(waiting){
        const status=document.createElement('div');status.className='sb-recent-empty';status.setAttribute('role','status');
        status.textContent=libraryStatus.includes('失败')?'访谈资料暂不可用，请在资料页重试':'正在读取最近访谈…';recentList.replaceChildren(status);
      }else if(!sorted.length){
        recentList.innerHTML='<div class="sb-recent-empty"><span>暂无已导入的访谈稿</span><br><button type="button" data-sb-demo>＋ 载入示例访谈</button></div>';
        const demoBtn=recentList.querySelector('[data-sb-demo]');
        if(demoBtn)demoBtn.onclick=()=>{
          if(typeof window.loadDemoSample==='function')window.loadDemoSample('editor',demoBtn);
          else document.getElementById('importTranscriptBtn')?.click();
        };
      }else{
        const topItems=sorted.slice(0,4);
        recentList.replaceChildren(...topItems.map(item=>{
          const btn=document.createElement('button');
          btn.type='button';
          btn.dataset.projectId=String(item.id);
          const isCurrent=currentId&&String(item.id)===String(currentId);
          btn.className='sb-recent-item'+(isCurrent?' is-current':'');
          if(isCurrent)btn.setAttribute('aria-current','true');
          btn.title=item.name+(item.edited_at?'（已校订）':'（待校订）');
          const dot=document.createElement('span');
          dot.className='sb-recent-dot'+(!item.edited_at?' is-review':'');
          const name=document.createElement('span');
          name.className='sb-recent-name';
          name.textContent=item.name;
          const tag=document.createElement('span');
          tag.className='sb-recent-tag';
          tag.textContent=isCurrent?'当前':(!item.edited_at?'待校':'');
          btn.append(dot,name,tag);
          btn.onclick=async()=>{
            if(typeof openProject!=='function')return;
            const serial=++recentOpenSerial,isCurrent=()=>serial===recentOpenSerial;
            try{
            const inAnalysis=document.getElementById('analysis')?.classList.contains('active');
            const inCoding=inAnalysis&&document.getElementById('coding')?.classList.contains('active');
            const inMemo=inAnalysis&&document.getElementById('familiarity')?.classList.contains('active');
            if(inCoding){
              if(!await openProject(item.id,null,{targetTab:'coding',isCurrent})||!isCurrent())return;
              if(typeof switchView==='function')switchView('analysis','coding');
            }else if(inMemo){
              if(!await openProject(item.id,null,{targetTab:'familiarity',isCurrent})||!isCurrent())return;
              if(typeof switchView==='function')switchView('analysis','familiarity');
            }else{
              if(!await openProject(item.id,null,{transcriptFirst:true,isCurrent})||!isCurrent())return;
            }
            item.last_opened_at=Date.now()/1000;
            updateSidebarWidgets();
            api('/api/projects/'+encodeURIComponent(item.id)+'/opened',{method:'POST'}).then(result=>{
              item.last_opened_at=result.last_opened_at;updateSidebarWidgets();
            }).catch(error=>toast('最近打开记录未更新：'+error.message));
            }catch(error){if(isCurrent())toast(error.message);}
          };
          return btn;
        }));
      }
    }
  }

  async function refreshSidebarQuota(){
    if(quotaPending||document.hidden)return;
    const roleEl=document.getElementById('sbQuotaRole');
    const numsEl=document.getElementById('sbQuotaNums');
    const fillEl=document.getElementById('sbQuotaFill');
    const track=fillEl?.parentElement;
    const subEl=document.getElementById('sbQuotaSub');
    if(!roleEl||!numsEl||!fillEl||!subEl)return;
    const boot=window.workbenchSession;
    if(!boot&&!accountsEnabled){
      const allProjects=typeof projects!=='undefined'&&Array.isArray(projects)?projects:[];
      const done=allProjects.filter(p=>p.status==='completed').length;
      roleEl.textContent='本地工作台';
      numsEl.textContent=done+' 篇就绪';
      track.hidden=true;
      subEl.textContent='点击打开工作台设置与回收站';
      quotaCard.setAttribute('aria-label','打开本地工作台设置');
      return;
    }
    if(boot){
      const isGuest=boot.role==='guest',isAdmin=boot.role==='admin';
      roleEl.textContent=isGuest?'访客试用空间':isAdmin?(boot.username+' · 管理员'):boot.username;
    }
    try{
      quotaPending=true;
      const r=await fetch('/auth/me');
      if(!r.ok)throw new Error('额度读取失败');
      const me=await r.json();
      if(!me||!me.usage||!Number.isFinite(Number(me.usage.calls)))throw new Error('额度数据无效');
      const isGuest=me.role==='guest',isAdmin=me.role==='admin';
      const used=Number(me.usage.calls),limit=Number(me.daily_calls);
      if(!isAdmin&&!(Number.isFinite(limit)&&limit>0))throw new Error('额度上限无效');
      roleEl.textContent=isGuest?'访客试用空间':isAdmin?(me.username+' · 管理员'):me.username;
      numsEl.textContent=isAdmin?('今日 '+used+' 次'):((isGuest?'累计 ':'')+used+' / '+limit+' 次');
      track.hidden=isAdmin;
      const pct=isAdmin?0:Math.min(100,Math.round(used/limit*100));
      fillEl.style.width=pct+'%';
      subEl.textContent=isGuest?'空间累计 20 次 · 不按日重置':isAdmin?'每日额度不限 · 点击管理成员与统计':'北京时间 08:00 重置 · 点击查看详情';
    }catch{
      numsEl.textContent='暂不可用';track.hidden=true;subEl.textContent='额度读取失败 · 点击查看详情或重试';
    }finally{quotaPending=false;}
  }

  window.updateSidebarWidgets=updateSidebarWidgets;
  window.refreshSidebarQuota=refreshSidebarQuota;
  document.addEventListener('interview-library-updated',updateSidebarWidgets);
  document.addEventListener('click',()=>requestAnimationFrame(updateSidebarWidgets));
  setTimeout(()=>{updateSidebarWidgets();refreshSidebarQuota();},250);
  setInterval(updateSidebarWidgets,2500);
  setInterval(()=>{if(!document.hidden)refreshSidebarQuota();},60000);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden){updateSidebarWidgets();refreshSidebarQuota();}});

})();
