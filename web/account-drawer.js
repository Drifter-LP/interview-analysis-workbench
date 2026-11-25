(() => {
 const dlg=document.createElement('dialog');dlg.className='account-drawer';dlg.setAttribute('aria-labelledby','wb-account-title');
 dlg.innerHTML=`<div class="wb-account-wrap">
 <div class="wb-account-heading"><h2 id="wb-account-title">账号与额度</h2><button class="wb-account-close" aria-label="关闭账号与额度"><svg viewBox="0 0 24 24" stroke="currentColor" fill="none" stroke-width="1.6"><path d="m5 5 14 14M19 5 5 19"/></svg></button></div>
 <div class="wb-account-person"><span class="wb-account-avatar"></span><div><strong class="wb-account-name"></strong><span class="wb-account-role"></span></div><div class="wb-account-person-actions"><button class="wb-account-account-toggle" type="button" aria-label="切换账号或退出登录" aria-expanded="false" aria-controls="wb-account-account-menu" aria-haspopup="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 7h16m-4-4 4 4-4 4M20 17H4m4-4-4 4 4 4"/></svg></button><div class="wb-account-account-menu" id="wb-account-account-menu" role="group" aria-label="账号操作" hidden><button type="button" class="wb-account-switch-account">切换账号</button><button type="button" class="wb-account-menu-logout">退出登录</button></div></div></div>
 <div class="wb-account-tabs" role="tablist" aria-label="账号页面"><button role="tab" id="wb-account-mine-tab" aria-controls="wb-account-personal" aria-selected="true">我的账号</button><button role="tab" id="wb-account-members-tab" aria-controls="wb-account-members" aria-selected="false" hidden>成员管理</button></div>
 <div class="wb-account-tab-panels"><section id="wb-account-personal" role="tabpanel" aria-labelledby="wb-account-mine-tab"><div class="wb-account-personal-content">
 <div class="wb-account-quota-head"><h3 class="wb-account-quota-title">今日用量</h3><span class="wb-account-quota-help">
 <button type="button" class="wb-account-quota-help-button" aria-label="用量统计说明" aria-describedby="wb-account-quota-tooltip" aria-controls="wb-account-quota-tooltip" aria-expanded="false"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M9.6 9.5a2.4 2.4 0 0 1 4.8 0c0 1.6-2.4 1.9-2.4 3.7m0 2.8h.01"/></svg></button>
 <span id="wb-account-quota-tooltip" class="wb-account-quota-tooltip" role="tooltip" hidden><span>每发起一次模型 API 请求记 1 次，合计所有模型；一次分析可能调用多次。</span><span class="wb-account-quota-period">按北京时间每天 08:00 划分统计日。Token 仅作统计，不限制额度。</span></span>
 </span></div>
 <div class="wb-account-quota"><div class="wb-account-quota-row"><span class="wb-account-quota-count" role="group" aria-label="今日已用 API 调用次数"><span class="wb-account-number">—</span><span class="wb-account-unit">次</span></span><span class="wb-account-limit"></span></div><div class="wb-account-track"><div class="wb-account-fill"></div></div></div>
 <div class="wb-account-guest-space" hidden><p class="wb-account-note"><strong>临时空间到期：</strong><time class="wb-account-guest-expiry"></time></p><p class="wb-account-note">到期后，未转入账号的资料会被清理。<a href="/account?preserve=1">登录并保留资料</a></p></div>
 <div class="wb-account-model-head"><h3>模型用量</h3><div class="wb-account-scope" role="group" aria-label="用量范围" hidden><button data-scope="self" aria-pressed="true">本人</button><button data-scope="all" aria-pressed="false">全站</button></div><select class="wb-account-days" aria-label="统计时间"><option value="7">近 7 天</option><option value="30">近 30 天</option></select></div>
 <div class="wb-account-models" role="group" aria-label="统计模型"><button data-model="deepseek" aria-pressed="true">DeepSeek Flash</button><button data-model="qwen" aria-pressed="false">千问 Flash</button></div>
 <div class="wb-account-charts" aria-live="polite"><div class="wb-account-chart"><div class="wb-account-chart-label">API 请求次数</div><div class="wb-account-chart-value wb-account-calls">—</div><div class="wb-account-call-plot"></div></div><div class="wb-account-chart"><div class="wb-account-chart-label">Token 用量 · 已确认</div><div class="wb-account-chart-value wb-account-tokens">—</div><div class="wb-account-token-plot"></div></div></div><p class="wb-account-note wb-account-missing"></p>
 </div><section class="wb-account-admin wb-account-invite wb-account-password-panel" aria-labelledby="wb-account-password-title" hidden>
 <button class="wb-account-back wb-account-password-back" type="button"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m14 6-6 6 6 6"/></svg>返回我的账号</button>
 <h3 id="wb-account-password-title">修改密码</h3><p class="wb-account-invite-intro">修改后需要重新登录，其他设备也会退出。请先保存工作台里的修改。</p>
 <form class="wb-account-password-form"><input class="wb-account-password-username" name="username" autocomplete="username" hidden>
 <label>当前密码<input name="current" type="password" autocomplete="current-password" maxlength="128" required></label>
 <label>新密码<input name="next" type="password" autocomplete="new-password" minlength="12" maxlength="128" aria-describedby="wb-account-password-help" required></label>
 <label>确认新密码<input name="confirm" type="password" autocomplete="new-password" minlength="12" maxlength="128" required></label>
 <p class="wb-account-invite-help" id="wb-account-password-help">使用 12–128 个字符，不能与当前密码相同。</p>
 <p class="wb-account-password-error" role="alert"></p><button class="wb-account-primary" type="submit">保存新密码</button></form>
 </section></section><section id="wb-account-members" class="wb-account-admin" role="tabpanel" aria-labelledby="wb-account-members-tab" hidden></section></div>
 <div class="wb-account-message" role="status"></div>
 <footer class="wb-account-footer"><div class="wb-account-footer-inner"><button class="wb-account-logout">退出登录</button><small>只退出账号；不会删除资料或取消已经运行的任务。</small></div></footer></div>`;
 document.body.append(dlg);
 const historyNote=document.createElement('p');historyNote.className='wb-account-note wb-account-history';historyNote.hidden=true;
 dlg.querySelector('.wb-account-missing').after(historyNote);
 const $=s=>dlg.querySelector(s);let me=null,scope='self',model='deepseek',stats=null,seq=0,opener=null,poll=0,tabRequest=0;
 const panelCache=new Map(),panelRequests=new Map();
 const message=(s,copyUrl='')=>{
  const box=$('.wb-account-message');box.textContent=s;
  if(copyUrl){
    const wrap=document.createElement('div');wrap.className='wb-account-copy-row';
    const copyBtn=document.createElement('button');copyBtn.type='button';copyBtn.className='wb-account-copy-btn';copyBtn.textContent='复制链接';
    copyBtn.onclick=async()=>{try{await navigator.clipboard.writeText(copyUrl);copyBtn.textContent='✓ 已复制';setTimeout(()=>{if(copyBtn.isConnected)copyBtn.textContent='复制链接';},2000);}catch{copyBtn.textContent='请手动复制';}};
    wrap.append(copyBtn);box.append(wrap);
  }
};
 const quotaHelp=$('.wb-account-quota-help'),quotaTrigger=$('.wb-account-quota-help-button'),quotaTooltip=$('.wb-account-quota-tooltip');
 let quotaHover=false,quotaFocus=false,quotaPinned=false,quotaDismissed=false;
 function drawQuotaHelp(){
   const open=!quotaDismissed&&(quotaHover||quotaFocus||quotaPinned);
   quotaTooltip.hidden=!open;quotaTrigger.setAttribute('aria-expanded',String(open));
 }
 function hideQuotaHelp(){
   quotaHover=quotaFocus=quotaPinned=false;quotaDismissed=true;drawQuotaHelp();
 }
 quotaTrigger.addEventListener('pointerenter',e=>{if(e.pointerType!=='touch'){quotaHover=true;quotaDismissed=false;drawQuotaHelp();}});
 quotaHelp.addEventListener('pointerleave',()=>{quotaHover=false;drawQuotaHelp();});
 quotaTrigger.addEventListener('focus',()=>{if(quotaTrigger.matches(':focus-visible')){quotaFocus=true;quotaDismissed=false;drawQuotaHelp();}});
 quotaTrigger.addEventListener('blur',()=>{quotaFocus=false;quotaPinned=false;drawQuotaHelp();});
 quotaTrigger.addEventListener('click',()=>{if(quotaPinned){hideQuotaHelp();return;}quotaPinned=true;quotaDismissed=false;drawQuotaHelp();});
 dlg.addEventListener('pointerdown',e=>{if(!quotaHelp.contains(e.target))hideQuotaHelp();});
 dlg.addEventListener('keydown',e=>{if(e.key==='Escape'&&!quotaTooltip.hidden){e.preventDefault();e.stopPropagation();hideQuotaHelp();}});
 const passwordPanel=$('.wb-account-password-panel'),passwordForm=$('.wb-account-password-form'),passwordError=$('.wb-account-password-error');
 let passwordBusy=false;
 const passwordEntry=document.createElement('button');passwordEntry.type='button';passwordEntry.className='wb-account-change-password';passwordEntry.textContent='修改密码';passwordEntry.hidden=true;
 $('.wb-account-menu-logout').before(passwordEntry);
 function showPassword(show){
   hideQuotaHelp();
   passwordPanel.hidden=!show;$('.wb-account-personal-content').hidden=show;
   passwordForm.reset();passwordError.textContent='';message('');
   if(show){$('.wb-account-password-username').value=me.username;passwordForm.elements.current.focus();}
 }
 passwordEntry.onclick=()=>{if(!me||me.role==='guest'||passwordBusy)return;hideAccountMenu();tab(false);showPassword(true);};
 $('.wb-account-password-back').onclick=()=>{if(passwordBusy)return;showPassword(false);accountToggle.focus();};
 passwordForm.onsubmit=async e=>{
   e.preventDefault();if(passwordBusy)return;
   const fields=passwordForm.elements,button=passwordForm.querySelector('[type="submit"]');
   passwordError.textContent='';
   if(fields.next.value!==fields.confirm.value){passwordError.textContent='两次输入的新密码不一致。';fields.confirm.focus();return}
   if(fields.next.value===fields.current.value){passwordError.textContent='新密码不能与当前密码相同。';fields.next.focus();return}
   passwordBusy=true;button.disabled=true;button.textContent='正在保存…';
   try{await api('/auth/change-password',{current_password:fields.current.value,new_password:fields.next.value});passwordForm.reset();location.replace('/account?password=updated');}
   catch(error){if(dlg.open&&!passwordPanel.hidden){passwordError.textContent=error.message;if(error.message.includes('当前密码'))fields.current.focus();}}
   finally{passwordBusy=false;button.disabled=false;button.textContent='保存新密码';}
 };
 async function api(url,body){
   const r=await fetch(url,{method:body?'POST':'GET',headers:{'Content-Type':'application/json',...(body&&me?{'X-CSRF-Token':me.csrf}:{})},...(body?{body:JSON.stringify(body)}:{})});
   const data=await r.json();if(!r.ok){if(r.status===401)location.replace('/account');throw Error(data.detail||'请求失败')}return data;
 }
 const safe=fn=>async e=>{try{await fn(e)}catch(err){message(err.message)}};
 function button(label,fn){const b=document.createElement('button');b.type='button';b.textContent=label;b.onclick=safe(fn);return b}
 const fmt=n=>Number(n).toLocaleString('en-US'),short=n=>n>=1e6?(n/1e6).toFixed(1).replace(/\.0$/,'')+'M':n>=1000?(n/1000).toFixed(1).replace(/\.0$/,'')+'K':String(n);
 function trendPath(coords){
   const steps=coords.slice(1).map(([x,y],i)=>(y-coords[i][1])/(x-coords[i][0]));
   // Use the smaller adjacent slope; plateaus and peaks get a horizontal tangent.
   // This keeps each curve between its actual daily values, including zero runs.
   const tangent=i=>{
     const a=steps[i-1],b=steps[i];
     return a*b>0?Math.sign(a)*Math.min(Math.abs(a),Math.abs(b)):0;
   };
   return coords.reduce((d,[x,y],i)=>{
     if(!i)return `M${x},${y}`;
     const [px,py]=coords[i-1],h=(x-px)/3;
     return `${d} C${px+h},${py+h*tangent(i-1)} ${x-h},${y-h*tangent(i)} ${x},${y}`;
   },'');
 }
 function plot(points,key,bars){
   const W=Math.max(200,$(bars?'.wb-account-token-plot':'.wb-account-call-plot').clientWidth),H=112,L=40,R=W-12,T=10,B=H-24,max=Math.max(1,...points.map(p=>p[key])),m=10**Math.floor(Math.log10(max)),rawCap=Math.ceil(max/m)*m,cap=bars?rawCap:Math.max(2,Math.ceil(rawCap/2)*2);
   const x=i=>L+(R-L)*(i+.5)/points.length,y=v=>B-(B-T)*v/cap;
   let svg=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${bars?'每日已确认 Token 用量':'每日 API 请求次数'}">`;
   for(const n of [0,.5,1])svg+=`<path d="M${L} ${y(cap*n)}H${R}" stroke="#dce5e3"/><text x="${L-6}" y="${y(cap*n)+3}" text-anchor="end" fill="#60797e" font-size="11">${short(cap*n)}</text>`;
   if(bars){const w=Math.max(2,Math.min(12,(R-L)/points.length*.6));points.forEach((p,i)=>{svg+=`<rect x="${x(i)-w/2}" y="${y(p[key])}" width="${w}" height="${B-y(p[key])}" rx="1.5" fill="#83c5ba"><title>${p.day}：${fmt(p[key])} Token</title></rect>`})}
   else{
     const curve=trendPath(points.map((p,i)=>[x(i),y(p[key])]));
     svg+=`<path d="${curve} L${x(points.length-1)},${B} H${x(0)} Z" fill="#d3ebe5"/><path class="wb-account-call-trend" d="${curve}" fill="none" stroke="#008b81" stroke-width="1.7" stroke-linecap="round"/>`;
     points.forEach((p,i)=>svg+=`<circle cx="${x(i)}" cy="${y(p[key])}" r="2" fill="#008b81"><title>${p.day}：${p[key]} 次</title></circle>`);
   }
   for(const i of [0,Math.floor(points.length/2),points.length-1])svg+=`<text x="${x(i)}" y="${H-5}" text-anchor="middle" fill="#60797e" font-size="11">${points[i].day.slice(5).replace('-','/')}</text>`;
   return svg+'</svg>';
 }
 function draw(){
   $('.wb-account-personal-content')?.classList.remove('wb-account-is-loading');
   for(const b of dlg.querySelectorAll('[data-scope]'))b.setAttribute('aria-pressed',String(b.dataset.scope===scope));
   for(const b of dlg.querySelectorAll('[data-model]'))b.setAttribute('aria-pressed',String(b.dataset.model===model));
   if(!stats)return;
   const points=stats.series[model],sum=k=>points.reduce((n,p)=>n+p[k],0);
   $('.wb-account-calls').textContent=fmt(sum('calls'))+' 次';$('.wb-account-tokens').textContent=fmt(sum('tokens'));
   $('.wb-account-call-plot').innerHTML=plot(points,'calls',false);$('.wb-account-token-plot').innerHTML=plot(points,'tokens',true);
   $('.wb-account-missing').textContent=sum('missing')?sum('missing')+' 次请求未返回实际 Token，未计入 Token 图表。':sum('calls')?'Token 仅合计接口返回的实际用量。':'当前时段暂无已记录调用。';
   if(stats.other_calls)$('.wb-account-missing').textContent+=' 另有 '+stats.other_calls+' 次其他模型调用未列入上述两个模型。';
   historyNote.hidden=!stats.historical_calls;
   historyNote.textContent=stats.historical_calls?'本时段含 '+fmt(stats.historical_calls)+' 次经核实历史调用（全部模型），不代表供应商完整账单。':'';
 }
 function requestPanel(key){
   if(panelRequests.has(key))return panelRequests.get(key);
   const pending=api('/auth/account-panel?'+key).then(data=>{
     if(window.workbenchSession&&data.profile.id!==window.workbenchSession.id){panelCache.clear();location.replace('/account');throw Error('当前会话已变化');}
     panelCache.set(key,data);return data;
   }).finally(()=>panelRequests.delete(key));
   panelRequests.set(key,pending);return pending;
 }
 async function usage(){
   const id=++seq,key='scope='+scope+'&days='+$('.wb-account-days').value,cached=panelCache.get(key);
   if(cached){me=cached.profile;profile();stats=cached.model_usage;draw();$('.wb-account-missing').textContent+=' 正在更新…';}
   else{stats=null;$('.wb-account-calls').textContent=$('.wb-account-tokens').textContent='—';$('.wb-account-call-plot').replaceChildren();$('.wb-account-token-plot').replaceChildren();$('.wb-account-missing').textContent='正在读取用量…';historyNote.hidden=true;draw();}
   try{
     const data=await requestPanel(key);
     if(id!==seq||!dlg.open)return;
     me=data.profile;profile();stats=data.model_usage;draw();
   }catch(error){
     if(id!==seq||!dlg.open)return;
     if(cached){draw();$('.wb-account-missing').textContent+=' 更新失败，显示上次结果。';}
     else $('.wb-account-missing').textContent='用量读取失败。';
     $('.wb-account-missing').append(' ',button('重试',usage));
   }
 }
 function profile(){
   $('.wb-account-name').textContent=me.username;$('.wb-account-avatar').textContent=me.username.slice(0,1).toUpperCase();
   const owner=me.role==='admin',guest=me.role==='guest';$('.wb-account-role').textContent=owner?'管理员':guest?'访客 · 临时空间':'普通成员';
   passwordEntry.hidden=guest;
   $('.wb-account-guest-space').hidden=!guest;
   $('.wb-account-quota-title').textContent=guest?'空间累计用量':'今日用量';
   $('.wb-account-quota-count').setAttribute('aria-label',guest?'访客空间累计 API 调用次数':'今日已用 API 调用次数');
   $('.wb-account-quota-period').textContent=guest?'从创建访客空间起累计，不按日重置。Token 仅作统计，不限制额度。':'按北京时间每天 08:00 划分统计日。Token 仅作统计，不限制额度。';
   if(guest){
     $('.wb-account-name').textContent='访客';$('.wb-account-avatar').textContent='访';$('.wb-account-switch-account').textContent='登录并保留资料';
     const expiry=new Date(me.guest.expires*1000), time=$('.wb-account-guest-expiry');
     time.dateTime=expiry.toISOString();time.textContent=new Intl.DateTimeFormat('zh-CN',{month:'long',day:'numeric',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(expiry);
   }
   $('#wb-account-members-tab').hidden=$('.wb-account-scope').hidden=!owner;$('.wb-account-number').textContent=fmt(me.usage.calls);
   $('.wb-account-limit').textContent=owner?'每日额度不限':guest?'空间累计 20 次':'每日 '+me.daily_calls+' 次';
   $('.wb-account-fill').style.width=owner?'0%':Math.min(100,me.usage.calls/me.daily_calls*100)+'%';
   const track=$('.wb-account-track');
   if(owner){track.removeAttribute('role');track.removeAttribute('aria-valuenow');track.removeAttribute('aria-valuemax');track.setAttribute('aria-label','每日额度不限')}
   else {track.setAttribute('role','progressbar');track.setAttribute('aria-label',guest?'空间累计 API 调用次数':'今日已用 API 调用次数');track.setAttribute('aria-valuemin','0');track.setAttribute('aria-valuemax',me.daily_calls);track.setAttribute('aria-valuenow',Math.min(me.usage.calls,me.daily_calls));track.title='已用 '+me.usage.calls+' / '+me.daily_calls+' 次；'+(guest?'不按日重置':'北京时间每天 08:00 重置')}
 }
 function tab(members){
   hideQuotaHelp();
   if(!passwordPanel.hidden)showPassword(false);
   $('#wb-account-personal').hidden=members;$('#wb-account-members').hidden=!members;
   $('#wb-account-mine-tab').setAttribute('aria-selected',String(!members));$('#wb-account-members-tab').setAttribute('aria-selected',String(members));message('');
 }
 async function members(){
   const users=await api('/auth/users'),box=$('#wb-account-members');box.classList.remove('wb-account-invite');box.replaceChildren();
   const head=document.createElement('div');head.className='wb-account-member-head';const h=document.createElement('h3');h.textContent='账号列表';const invite=button('＋ 邀请成员',inviteForm);invite.className='wb-account-primary';head.append(h,invite);box.append(head);
   const table=document.createElement('table');table.className='wb-account-table';table.innerHTML='<thead><tr><th>账号</th><th>状态</th><th>每日调用</th><th>操作</th></tr></thead><tbody></tbody>';
   for(const u of users){const row=table.tBodies[0].insertRow();for(const v of [u.username,u.active?'启用':'停用',u.role==='admin'?'不限':u.daily_calls+' 次'])row.insertCell().textContent=v;row.insertCell().append(button('管理 ›',()=>manage(u)))}box.append(table);
 }
 function subpage(title){
   const box=$('#wb-account-members');box.replaceChildren();box.classList.remove('wb-account-invite');const back=button('返回成员列表',members);back.className='wb-account-back';back.insertAdjacentHTML('afterbegin','<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m14 6-6 6 6 6"/></svg>');box.append(back);const h=document.createElement('h3');h.textContent=title;box.append(h);message('');return box;
 }
 function form(box,label,value,type,attrs,submit,fn){
   const f=document.createElement('form'),l=document.createElement('label'),i=document.createElement('input'),b=document.createElement('button');
   i.type=type;i.value=value;Object.assign(i,attrs);i.required=true;l.textContent=label;l.append(i);b.textContent=submit;b.className='wb-account-primary';f.append(l,b);box.append(f);
   f.onsubmit=safe(async e=>{e.preventDefault();b.disabled=true;try{await fn(i.value)}finally{b.disabled=false}});
   return {f,l,i,b};
 }
 function inviteForm(){
   const box=subpage('邀请成员');box.classList.add('wb-account-invite');
   const intro=document.createElement('p');intro.className='wb-account-invite-intro';intro.textContent='为新成员创建账号，生成专属邀请链接。';box.append(intro);
   const {f,i,b}=form(box,'账号名称','','text',{minLength:3,maxLength:32,placeholder:'输入新成员的账号名称',autocomplete:'off',pattern:'[A-Za-z0-9][A-Za-z0-9_.\\-]{2,31}'},'生成邀请链接',async username=>{const r=await api('/auth/admin/invite',{username});message('邀请链接 48 小时有效，请私下发送：\n'+r.url,r.url)});
   i.setAttribute('aria-describedby','wb-account-invite-help');i.spellcheck=false;i.autocapitalize='none';
   const help=document.createElement('p');help.id='wb-account-invite-help';help.className='wb-account-invite-help';help.textContent='3–32 位英文或数字，支持 . _ -；须以字母或数字开头。';f.insertBefore(help,b);
   b.insertAdjacentHTML('afterbegin','<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m9 15 6-6m-7 9-1 1a4.2 4.2 0 0 1-6-6l4-4a4.2 4.2 0 0 1 6 0m2-3 1-1a4.2 4.2 0 0 1 6 6l-4 4a4.2 4.2 0 0 1-6 0"/></svg>');
   const note=document.createElement('div');note.className='wb-account-invite-note';
   note.innerHTML='<strong>链接生成后，请私下发送给对方。</strong><p>48 小时内有效，仅可使用一次；成员通过链接自行设置密码。</p><p>新账号从空白资料库开始，每日可调用 API 80 次。</p>';box.append(note);
 }
 function manage(u){
   const box=subpage('管理账号：'+u.username);
   if(u.role!=='admin')form(box,'每日 API 调用上限',u.daily_calls,'number',{min:1,max:100},'保存额度',async v=>{await api('/auth/admin/update',{id:u.id,active:!!u.active,daily_calls:Number(v)});u.daily_calls=Number(v);message('已更新额度')});
   const actions=document.createElement('div');actions.className='wb-account-actions';
   if(u.active)actions.append(button('生成密码重设链接',async()=>{if(!confirm('确认已核验 '+u.username+' 的身份？重设链接仅可使用一次，请私下发送。'))return;const r=await api('/auth/admin/reset',{id:u.id,username:u.username});message('密码重设链接 1 小时内有效，仅可用一次。请私下发送：\n'+r.url,r.url)}));
   if(u.role!=='admin')actions.append(button(u.active?'停用账号':'启用账号',async()=>{if(!confirm('确认更改 '+u.username+' 的账号状态？资料不会删除。'))return;await api('/auth/admin/update',{id:u.id,active:!u.active,daily_calls:u.daily_calls});await members()}));
   box.append(actions);
 }
 $('.wb-account-close').onclick=()=>dlg.close();dlg.addEventListener('click',e=>{if(e.target===dlg){const b=dlg.getBoundingClientRect();if(e.clientX<b.left||e.clientY<b.top||e.clientY>b.bottom)dlg.close()}});
 dlg.addEventListener('close',()=>{hideAccountMenu();showPassword(false);seq++;tabRequest++;window.cancelWorkspaceTab?.($('.wb-account-tab-panels'));clearInterval(poll);opener?.focus()});
 async function selectTab(memberTab){
   const request=++tabRequest,target=$('.wb-account-tab-panels'),next=$(memberTab?'#wb-account-members-tab':'#wb-account-mine-tab');
   window.cancelWorkspaceTab?.(target);
   if(next.getAttribute('aria-selected')==='true'){if(!memberTab&&!passwordPanel.hidden&&!passwordBusy)showPassword(false);return;}
   if(passwordBusy)return;
   if(memberTab&&!$('#wb-account-members').childElementCount)await members();
   if(request!==tabRequest||!dlg.open)return;
   const update=()=>{if(request===tabRequest&&dlg.open)tab(memberTab);};
   if(window.slideWorkspaceTab)await window.slideWorkspaceTab(target,update,memberTab?1:-1,$('.wb-account-tabs'),next);else update();
 }
 $('#wb-account-mine-tab').onclick=safe(()=>selectTab(false));
 $('#wb-account-members-tab').onclick=safe(()=>selectTab(true));
 for(const b of dlg.querySelectorAll('[data-scope]'))b.onclick=safe(async()=>{scope=b.dataset.scope;await usage()});
 for(const b of dlg.querySelectorAll('[data-model]'))b.onclick=()=>{model=b.dataset.model;draw()};
 $('.wb-account-days').title='仅统计工作台已记录的调用；按 UTC 日汇总（北京时间 08:00 切日），不补算未记录的历史调用。';
 $('.wb-account-days').onchange=safe(usage);
 let plotWidth=0;
 new ResizeObserver(entries=>{
   const width=entries[0].contentRect.width;
   if(width>0&&Math.abs(width-plotWidth)>1){plotWidth=width;if(dlg.open&&stats&&!$('#wb-account-personal').hidden)draw()}
 }).observe($('.wb-account-charts'));
 const accountActions=$('.wb-account-person-actions'),accountToggle=$('.wb-account-account-toggle'),accountMenu=$('.wb-account-account-menu');
 accountToggle.setAttribute('aria-label','账号操作');
 for(const [selector,path] of [
   ['.wb-account-switch-account','M4 7h16m-4-4 4 4-4 4M20 17H4m4-4-4 4 4 4'],
   ['.wb-account-change-password','M7 10V7a5 5 0 0 1 10 0v3M6 10h12v10H6zM12 14v2'],
   ['.wb-account-menu-logout','M9 4H4v16h5M9 12h12m-4-4 4 4-4 4']
 ]){
   $(selector).insertAdjacentHTML('afterbegin','<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="'+path+'"/></svg>');
 }
 let accountTimer=0,signingOut=false;
 function hideAccountMenu(){clearTimeout(accountTimer);accountMenu.hidden=true;accountToggle.setAttribute('aria-expanded','false')}
 function showAccountMenu(focus=false){clearTimeout(accountTimer);accountMenu.hidden=false;accountToggle.setAttribute('aria-expanded','true');if(focus)accountMenu.querySelector('button').focus()}
 accountActions.onpointerenter=e=>{if(e.pointerType!=='touch')showAccountMenu()};
 accountActions.onpointerleave=()=>{clearTimeout(accountTimer);accountTimer=setTimeout(()=>{if(!accountActions.contains(document.activeElement))hideAccountMenu()},220)};
 accountActions.onfocusin=()=>clearTimeout(accountTimer);
 accountToggle.onclick=()=>showAccountMenu(true);
 accountToggle.onkeydown=e=>{if(e.key==='ArrowDown'){e.preventDefault();e.stopPropagation();showAccountMenu(true)}};
 accountActions.onkeydown=e=>{
   if(e.key==='Escape'&&!accountMenu.hidden){e.preventDefault();e.stopPropagation();hideAccountMenu();accountToggle.focus()}
   if(['ArrowDown','ArrowUp'].includes(e.key)&&accountMenu.contains(document.activeElement)){
     e.preventDefault();const rows=[...accountMenu.children].filter(row=>!row.hidden),i=rows.indexOf(document.activeElement);rows[(i+(e.key==='ArrowDown'?1:-1)+rows.length)%rows.length].focus();
   }
 };
 dlg.addEventListener('cancel',e=>{if(!accountMenu.hidden){e.preventDefault();hideAccountMenu();accountToggle.focus()}else if(!passwordPanel.hidden){e.preventDefault();if(!passwordBusy){showPassword(false);accountToggle.focus();}}});
 dlg.addEventListener('pointerdown',e=>{if(!accountActions.contains(e.target))hideAccountMenu()});
 dlg.addEventListener('focusin',e=>{if(!accountActions.contains(e.target))hideAccountMenu()});
 async function signout(switchAccount){
   if(switchAccount&&me?.role==='guest'){location.assign('/account?preserve=1');return}
   if(signingOut)return;
   if(!confirm(switchAccount?'切换账号需要先退出当前账号，未保存的修改不会自动保存。是否继续？':'退出当前账号？未保存的修改不会自动保存。'))return;
   signingOut=true;hideAccountMenu();
   try{await api('/auth/logout',{});location.replace('/account')}finally{signingOut=false}
 }
 $('.wb-account-switch-account').onclick=safe(()=>signout(true));
 $('.wb-account-menu-logout').onclick=safe(()=>signout(false));
 $('.wb-account-logout').onclick=safe(()=>signout(false));
 window.openAccountDrawer=safe(async()=>{
   if(dlg.open)return;opener=document.activeElement===document.body?document.querySelector('.sidebar-settings'):document.activeElement;scope='self';model='deepseek';stats=null;tab(false);message('');
   $('.wb-account-number').textContent='—';$('.wb-account-name').textContent='正在读取…';$('.wb-account-role').textContent='';$('.wb-account-guest-space').hidden=true;passwordEntry.hidden=true;
   dlg.showModal();$('.wb-account-close').focus();
   const boot=window.workbenchSession;
   if(boot){$('.wb-account-name').textContent=boot.role==='guest'?'访客':boot.username;$('.wb-account-avatar').textContent=boot.role==='guest'?'访':boot.username.slice(0,1).toUpperCase();$('.wb-account-role').textContent=boot.role==='admin'?'管理员':boot.role==='guest'?'访客 · 临时空间':'普通成员';}
   clearInterval(poll);poll=setInterval(()=>{if(dlg.open&&!document.hidden&&!$('#wb-account-personal').hidden&&passwordPanel.hidden)usage()},30000);
   await usage();
 });
 window.attachDrawerMotion?.(dlg);
 if(location.hash==='#account'){history.replaceState(null,'',location.pathname+location.search);window.openAccountDrawer()}
})();
