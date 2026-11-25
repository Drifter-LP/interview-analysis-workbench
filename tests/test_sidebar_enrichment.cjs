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
   if(role==='admin'){
    assert.equal(await p.locator('.sb-quota-track').isVisible(),false);
    const me=await (await p.request.get(origin+'/auth/me')).json(),ids=[];
    for(const name of ['第一份虚构访谈：出行与费用','第二份虚构访谈：这是一份很长很长的标题以检查溢出']){
     const r=await p.request.post(origin+'/api/transcript-projects',{headers:{Origin:origin,'X-CSRF-Token':me.csrf},multipart:{transcript:{name:name+'.txt',mimeType:'text/plain',buffer:Buffer.from('访谈者：平时怎样出行？\n受访者：我乘地铁，但没有因为费用拒绝出行。')}}});
     assert.ok(r.ok(),await r.text());ids.push((await r.json()).id);
    }
    await p.evaluate(async()=>{await loadProjects();window.updateSidebarWidgets()});
    await p.locator('.sb-recent-item').first().waitFor();
    await p.locator('.sb-recent-item').first().focus();
    await p.evaluate(()=>window.__sidebarFocus=document.activeElement);
    await p.waitForTimeout(2800);
    assert.ok(await p.evaluate(()=>window.__sidebarFocus===document.activeElement&&window.__sidebarFocus.isConnected),'unchanged list must preserve focus');
    await p.locator(`.sb-recent-item[data-project-id="${ids[0]}"]`).click();
    await p.waitForFunction(id=>selected===id,ids[0]);
    assert.ok(await p.locator(`.sb-recent-item[data-project-id="${ids[0]}"]`).getAttribute('aria-current'));
    await p.evaluate(()=>switchView('analysis','familiarity'));
    await p.route('**/api/projects/'+ids[1]+'**',async route=>{await new Promise(r=>setTimeout(r,500));await route.continue()});
    await p.locator(`.sb-recent-item[data-project-id="${ids[1]}"]`).click();
    await p.locator(`.sb-recent-item[data-project-id="${ids[0]}"]`).click();
    await p.waitForTimeout(1000);
    assert.equal(await p.evaluate(()=>selected),ids[0]);
    assert.ok(await p.locator('#familiarity').evaluate(el=>el.classList.contains('active')));
    await p.unrouteAll({behavior:'wait'});
    await p.locator('#sbQuotaCard').click();await p.getByRole('heading',{name:'账号与额度',exact:true}).waitFor();
    await p.getByRole('button',{name:'关闭账号与额度',exact:true}).click();
    await p.waitForFunction(()=>!document.querySelector('.account-drawer').open);
    await p.setViewportSize({width:1440,height:720});
    const geometry=await p.locator('.sidebar').evaluate(side=>({width:side.clientWidth,scroll:side.scrollWidth,settings:side.querySelector('.sidebar-settings').getBoundingClientRect().bottom,height:innerHeight}));
    assert.ok(geometry.scroll<=geometry.width+2,JSON.stringify(geometry));
    assert.ok(geometry.settings<=geometry.height,JSON.stringify(geometry));
    await p.setViewportSize({width:1440,height:960});
    await p.screenshot({path:path.resolve(__dirname,'../outputs/sidebar-enrichment-admin.png')});
    await p.locator('#sideToggle').click();assert.equal(await p.locator('#sbRecentBox').isVisible(),false);assert.equal(await p.locator('#sbQuotaCard').isVisible(),false);
    await p.setViewportSize({width:390,height:844});assert.equal(await p.locator('#sbQuotaCard').isVisible(),false);
   }else if(role==='member'){
    assert.ok((await p.locator('#sbQuotaNums').innerText()).includes('/ 80'));
    await p.route('**/auth/me',route=>route.fulfill({status:503,contentType:'application/json',body:'{"detail":"synthetic failure"}'}));
    await p.evaluate(()=>window.refreshSidebarQuota());assert.equal(await p.locator('#sbQuotaNums').innerText(),'暂不可用');
    await p.unroute('**/auth/me');await p.evaluate(()=>window.refreshSidebarQuota());assert.ok((await p.locator('#sbQuotaNums').innerText()).includes('/ 80'));
   }else{
    assert.ok((await p.locator('#sbQuotaNums').innerText()).startsWith('累计 '));
    assert.ok((await p.locator('#sbQuotaSub').innerText()).includes('不按日重置'));
    assert.equal(await p.locator('.nav-item[data-tab="focused"] .sb-nav-badge').count(),0);
    await p.screenshot({path:path.resolve(__dirname,'../outputs/sidebar-enrichment-guest.png')});
   }
   assert.deepEqual(errors,[]);console.log('PASS sidebar enrichment:',role);await p.close();
  }
 }finally{await b.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
