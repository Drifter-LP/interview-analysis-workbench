const {chromium}=require('playwright'),assert=require('node:assert/strict');
const origin=process.env.ACCOUNT_UI_ORIGIN||'http://127.0.0.1:9928';
(async()=>{
 const b=await chromium.launch({channel:'chrome'});
 try{
  for(const guest of [true,false]){
   const p=await b.newPage({viewport:{width:390,height:800}}),errors=[];
   p.on('pageerror',e=>errors.push(e.message));
   const login=await p.request.post(origin+'/auth/'+(guest?'guest':'login'),{headers:{Origin:origin},data:guest?{}:{username:'qa_owner',password:'temporary-qa-login-123'}});
   assert.ok(login.ok());
   await p.route('**/auth/changelog',r=>r.fulfill({json:{items:[]}}));
   await p.goto(origin+(guest?'/?guest=1':'/'),{waitUntil:'domcontentloaded'});
   if(guest){
    const cross=p.locator('.nav-item.guest-feature-locked[data-tab=focused]'),tip=p.locator('#guestFeatureTip');
    await cross.waitFor({state:'attached'});
    if(!await cross.isVisible())await p.locator('.nav-parent[data-group=research]').click();
    await cross.waitFor();await cross.focus();await p.keyboard.press('Enter');
    const link=tip.getByRole('link');await link.waitFor();
    assert.ok(await link.evaluate(x=>x===document.activeElement));
    assert.equal(await link.getAttribute('href'),'/account?preserve=1');
    const bounds=await tip.boundingBox();assert.ok(bounds.x>=0&&bounds.x+bounds.width<=390);
    await p.keyboard.press('Escape');
    assert.equal((await p.request.get(origin+'/auth/users')).status(),403);
   }
   await p.waitForFunction(()=>window.openAccountDrawer);await p.evaluate(()=>window.openAccountDrawer());
   if(guest){
    await p.locator('.wb-account-guest-login-btn').waitFor();
    assert.equal(await p.locator('.wb-account-logout').isVisible(),false);
   }else{
    await p.locator('.wb-account-avatar').click();
    await p.locator('[data-preset="preset:ocean"]').click();
    await p.locator('.wb-account-toast').filter({hasText:'头像配色已更新'}).waitFor();
    assert.equal((await (await p.request.get(origin+'/auth/me')).json()).avatar,'preset:ocean');
   }
   assert.deepEqual(errors,[]);
  }
  console.log('PASS: guest login link, guest permissions, mobile bounds and avatar feedback');
 }finally{await b.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
