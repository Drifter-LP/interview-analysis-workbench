const {chromium}=require('playwright'),assert=require('node:assert/strict'),path=require('node:path');
(async()=>{
 const origin=process.env.SIDEBAR_QA_ORIGIN||'http://127.0.0.1:9896';
 const b=await chromium.launch({channel:'chrome',headless:true});
 try{
  for(const role of ['admin','member','guest']){
   const p=await b.newPage({viewport:{width:1440,height:960}});p.setDefaultTimeout(45000);
   const errors=[];p.on('pageerror',e=>errors.push(e.message));
   const auth=await p.request.post(origin+(role==='guest'?'/auth/guest':'/auth/login'),{
    headers:{Origin:origin},data:role==='guest'?{}:{username:role==='admin'?'qa_owner':'qa_friend',password:role==='admin'?'temporary-qa-login-123':'temporary-qa-friend-123'}});
   assert.ok(auth.ok());await p.goto(origin+(role==='guest'?'/?guest=1':'/'));await p.locator('#sbQuotaCard').waitFor();
   await p.waitForFunction(()=>/次/.test(document.querySelector('#sbQuotaNums').textContent));
   const before=await p.locator('#sbQuotaCard').boundingBox();
   await p.locator('#sbQuotaCard').focus();await p.locator('#sbQuotaTooltip').waitFor();
   assert.ok((await p.locator('#sbQuotaTooltip').innerText()).includes('已用：'));
   assert.ok((await p.locator('#sbQuotaTooltip').innerText()).includes(role==='admin'?'不限':role==='guest'?'不按日重置':'每天08:00重置'));
   await p.keyboard.press('Escape');assert.equal(await p.locator('#sbQuotaTooltip').isVisible(),false);
   await p.locator('body').click({position:{x:1100,y:600}});
   await p.locator('#sbQuotaCard').hover();await p.locator('#sbQuotaTooltip').waitFor();
   await p.locator('#sbQuotaTooltip').hover();await p.waitForTimeout(200);assert.ok(await p.locator('#sbQuotaTooltip').isVisible());
   assert.deepEqual(await p.locator('#sbQuotaCard').boundingBox(),before,'hover must not resize or move card');
   if(role==='admin')await p.screenshot({path:path.resolve(__dirname,'../outputs/quota-interaction-verified.png')});
   await p.keyboard.press('Escape');
   if(role==='admin'){
    assert.equal(await p.locator('.sb-quota-track').isVisible(),true);
    assert.ok((await p.locator('#sbQuotaNums').innerText()).includes('/ ∞'));
    const me=await (await p.request.get(origin+'/auth/me')).json(),ids=[];
    for(const name of ['第一份虚构访谈：出行与费用','第二份虚构访谈：这是一份很长很长的标题以检查溢出']){
     const r=await p.request.post(origin+'/api/transcript-projects',{headers:{Origin:origin,'X-CSRF-Token':me.csrf},multipart:{transcript:{name:name+'.txt',mimeType:'text/plain',buffer:Buffer.from('访谈者：平时怎样出行？\n受访者：我乘地铁，但没有因为费用拒绝出行。')}}});
     assert.ok(r.ok(),await r.text());ids.push((await r.json()).id);
    }
    const revised=await p.request.put(origin+'/api/projects/'+ids[0]+'/transcript',{headers:{Origin:origin,'X-CSRF-Token':me.csrf},data:{text:'访谈者：平时怎样出行？\n受访者：我乘地铁。'}});assert.ok(revised.ok());
    await p.evaluate(async()=>{await loadProjects();window.updateSidebarWidgets()});
    assert.equal(await p.locator('.sb-nav-badge').count(),0);
    assert.equal(await p.locator('.sb-recent-tag').count(),0);
    for(const label of await p.locator('.sb-recent-name').allTextContents())assert.ok(Array.from(label.replace(/…$/,'')).length<=5);
    const align=await p.evaluate(()=>{const a=document.querySelector('[data-view="workspace"] em').getBoundingClientRect(),b=document.querySelector('.sb-recent-name').getBoundingClientRect();return Math.abs(a.left-b.left)});assert.ok(align<1,'child label alignment '+align);
    await p.locator('.sb-recent-item').first().waitFor();
    await p.locator('.sb-recent-item').first().focus();
    await p.evaluate(()=>window.__sidebarFocus=document.activeElement);
    await p.waitForTimeout(2800);
    assert.ok(await p.evaluate(()=>window.__sidebarFocus===document.activeElement&&window.__sidebarFocus.isConnected),'unchanged list must preserve focus');
    await p.locator(`.sb-recent-item[data-project-id="${ids[0]}"]`).click();
    await p.waitForFunction(id=>selected===id,ids[0]);
    await p.waitForFunction(()=>document.querySelector('#familiarity').classList.contains('active'));
    assert.ok(await p.locator(`.sb-recent-item[data-project-id="${ids[0]}"]`).getAttribute('aria-current'));
    await p.evaluate(()=>switchView('analysis','familiarity'));
    await p.route('**/api/projects/'+ids[1]+'**',async route=>{await new Promise(r=>setTimeout(r,500));await route.continue()});
    await p.locator(`.sb-recent-item[data-project-id="${ids[1]}"]`).click();
    await p.locator(`.sb-recent-item[data-project-id="${ids[0]}"]`).click();
    await p.waitForTimeout(1000);
    assert.equal(await p.evaluate(()=>selected),ids[0]);
    assert.ok(await p.locator('#familiarity').evaluate(el=>el.classList.contains('active')));
    await p.unrouteAll({behavior:'wait'});
    await p.locator('#sbQuotaCard').focus();await p.keyboard.press('Enter');await p.getByRole('heading',{name:'账号与额度',exact:true}).waitFor();
    assert.equal(await p.locator('#sbQuotaTooltip').isVisible(),false);
    await p.getByRole('button',{name:'关闭账号与额度',exact:true}).click();
    await p.waitForFunction(()=>!document.querySelector('.account-drawer').open);
    await p.setViewportSize({width:1440,height:720});
    const geometry=await p.locator('.sidebar').evaluate(side=>({width:side.clientWidth,scroll:side.scrollWidth,settings:side.querySelector('.sidebar-settings').getBoundingClientRect().bottom,height:innerHeight}));
    assert.ok(geometry.scroll<=geometry.width+2,JSON.stringify(geometry));
    assert.ok(geometry.settings<=geometry.height,JSON.stringify(geometry));
    await p.setViewportSize({width:1440,height:960});
    await p.screenshot({path:path.resolve(__dirname,'../outputs/sidebar-enrichment-admin.png')});
    const footer=await p.locator('.site-icp-footer').boundingBox();assert.ok(footer.x>1100&&footer.y>900);
    await p.locator('#sbRecentBox .nav-parent').click();assert.equal(await p.locator('#sbRecentList').isVisible(),false);
    await p.locator('#sbRecentBox .nav-parent').click();assert.equal(await p.locator('#sbRecentList').isVisible(),true);
    await p.locator(`.sb-recent-item[data-project-id="${ids[1]}"]`).click();await p.waitForFunction(id=>selected===id&&document.querySelector('#editor').classList.contains('active'),ids[1]);
    await p.locator('#sideToggle').click();assert.equal(await p.locator('#sbRecentList').isVisible(),false);assert.equal(await p.locator('#sbQuotaCard').isVisible(),false);
    await p.setViewportSize({width:390,height:844});assert.equal(await p.locator('#sbQuotaCard').isVisible(),false);
   }else if(role==='member'){
    assert.ok((await p.locator('#sbQuotaNums').innerText()).includes('/ 80'));
    await p.route('**/auth/me',route=>route.fulfill({status:503,contentType:'application/json',body:'{"detail":"synthetic failure"}'}));
    await p.evaluate(()=>window.refreshSidebarQuota());assert.equal(await p.locator('#sbQuotaNums').innerText(),'暂不可用');
    await p.unroute('**/auth/me');await p.evaluate(()=>window.refreshSidebarQuota());assert.ok((await p.locator('#sbQuotaNums').innerText()).includes('/ 80'));
   }else{
    assert.equal(await p.locator('#sbQuotaRole').innerText(),'试用额度');
    assert.ok((await p.locator('#sbQuotaCard').getAttribute('aria-label')).includes('不按日重置'));
    assert.equal(await p.locator('.nav-item[data-tab="focused"] .sb-nav-badge').count(),0);
    await p.screenshot({path:path.resolve(__dirname,'../outputs/sidebar-enrichment-guest.png')});
   }
   assert.deepEqual(errors,[]);console.log('PASS sidebar enrichment:',role);await p.close();
  }
 }finally{await b.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
