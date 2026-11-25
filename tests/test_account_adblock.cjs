const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
 const origin=process.env.ACCOUNT_QA_ORIGIN||'http://127.0.0.1:9892';
 const b=await chromium.launch({channel:'chrome',headless:true});
 const legacyAdRules='.ad-wrap,.ad-heading,.ad-tabs,.ad-message,.ad-footer,[class^="ad-"],[class*=" ad-"]{display:none!important}';
 try{
  for(const role of ['admin','member','guest']){
   const page=await b.newPage({viewport:{width:1200,height:900}});
   const errors=[];page.on('pageerror',e=>errors.push(e.message));
   const auth=role==='guest'?'/auth/guest':'/auth/login';
   const data=role==='guest'?{}:{username:role==='admin'?'qa_owner':'qa_friend',password:role==='admin'?'temporary-qa-login-123':'temporary-qa-friend-123'};
   assert.ok((await page.request.post(origin+auth,{headers:{Origin:origin},data})).ok());
   await page.goto(origin+(role==='guest'?'/?guest=1':'/'));
   await page.waitForFunction(()=>typeof window.openAccountDrawer==='function');
   await page.addStyleTag({content:legacyAdRules});
   let fail=role==='member';
   await page.route('**/auth/account-panel?*',async route=>{
    if(fail){fail=false;return route.fulfill({status:503,contentType:'application/json',body:'{"detail":"synthetic temporary failure"}'})}
    return route.continue();
   });
   await page.evaluate(()=>window.openAccountDrawer());
   const panel=page.locator('.account-drawer');
   await panel.getByRole('heading',{name:'账号与额度',exact:true}).waitFor();
   assert.ok(await panel.locator('.wb-account-wrap').isVisible());
   if(role==='member'){
    await panel.getByRole('button',{name:'重试',exact:true}).click();
   }
   await page.waitForFunction(()=>/^\d/.test(document.querySelector('.wb-account-number').textContent));
   assert.ok(await panel.locator('.wb-account-call-plot svg').isVisible());
   assert.equal(await panel.locator('[class^="ad-"],[class*=" ad-"]').count(),0);
   await panel.getByRole('button',{name:'千问 Flash',exact:true}).click();
   assert.ok(await panel.locator('.wb-account-token-plot svg').isVisible());
   for(let i=0;i<2;i++){
    await panel.getByRole('button',{name:'关闭账号与额度',exact:true}).click();
    await page.waitForFunction(()=>!document.querySelector('.account-drawer').open);
    await page.evaluate(()=>window.openAccountDrawer());
    await panel.locator('.wb-account-number').waitFor();
    assert.ok(await panel.locator('.wb-account-wrap').isVisible());
   }
   assert.deepEqual(errors,[]);
   console.log('PASS account ad-filter regression:',role);
   await page.close();
  }
 }finally{await b.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
