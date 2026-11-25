const {chromium}=require('playwright'),assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 const origin=process.env.ENTRY_QA_ORIGIN||'http://127.0.0.1:9885';
 try{
  const context=await browser.newContext(),page=await context.newPage();page.setDefaultTimeout(40000);
  await page.goto(origin+'/');await page.locator('#submit').waitFor();
  await page.locator('#guestStart').click();await page.locator('#workspace.active').waitFor();
  const first=await (await page.request.get(origin+'/auth/me')).json();assert.equal(first.role,'guest');
  await page.reload();await page.locator('#submit:not([disabled])').waitFor();
  await page.locator('#guestStart').click();await page.locator('#workspace.active').waitFor();
  assert.equal((await (await page.request.get(origin+'/auth/me')).json()).id,first.id);
  await page.goto(origin+'/account');await page.locator('#submit:not([disabled])').waitFor();
  await page.locator('#username').fill('qa_friend');await page.locator('#password').fill('temporary-qa-friend-123');
  const login=page.waitForResponse(r=>r.url().endsWith('/auth/login'));
  page.on('dialog',d=>d.dismiss());await page.locator('#submit').click();assert.equal((await login).status(),200);
  await page.locator('#workspace.active').waitFor();
  const state=await context.storageState(),cookie=state.cookies.find(c=>c.name==='wb_session_8765');
  assert.ok(cookie.httpOnly);assert.ok(cookie.expires-Date.now()/1000>29*86400);
  await context.close();
  const returning=await browser.newContext({storageState:state}),again=await returning.newPage();
  await again.goto(origin+'/');await again.locator('#workspace.active').waitFor();
  assert.equal(await again.locator('#submit').count(),0);
  const me=await (await again.request.get(origin+'/auth/me')).json();
  await again.request.post(origin+'/auth/logout',{headers:{Origin:origin,'X-CSRF-Token':me.csrf},data:{}});
  await again.reload();await again.locator('#submit').waitFor();
  console.log('PASS: first visit login, returning guest login, same guest space, 30-day cookie, browser-context return, logout requires login');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
