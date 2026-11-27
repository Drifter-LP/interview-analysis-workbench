const {chromium}=require('playwright'),assert=require('node:assert/strict');
const origin=process.env.DISPLAY_NAME_QA_ORIGIN||'http://127.0.0.1:9923';

(async()=>{
 const browser=await chromium.launch({channel:'chrome'});
 try{
  const context=await browser.newContext({reducedMotion:'reduce'}),p=await context.newPage(),errors=[];
  p.on('pageerror',e=>errors.push(e.message));
  const login=()=>p.request.post(origin+'/auth/login',{headers:{Origin:origin},data:{username:'qa_owner',password:'temporary-qa-login-123'}});
  const read=async()=>{const r=await p.request.get(origin+'/auth/me');assert.ok(r.ok());return r.json();};
  assert.ok((await login()).ok());const initial=await read();
  await p.addInitScript(id=>localStorage.setItem('wb_seen_changelog_id:'+id,'seed-20261126'),initial.id);
  const open=async()=>{await p.goto(origin+'/',{waitUntil:'domcontentloaded'});await p.waitForFunction(()=>window.openAccountDrawer);await p.evaluate(()=>window.openAccountDrawer());};
  await open();await p.locator('.wb-account-edit-name').click();
  const input=p.getByRole('textbox',{name:'显示名称',exact:true}),save=p.locator('.wb-account-name-save');
  await input.fill('奶龙大龙');
  await p.route(origin+'/auth/profile',r=>r.fulfill({status:503,json:{detail:'模拟暂不可保存'}}),{times:1});
  await save.click();await p.getByText('模拟暂不可保存',{exact:true}).last().waitFor();
  assert.equal(await input.inputValue(),'奶龙大龙');
  const saving=p.waitForResponse(r=>r.url()===origin+'/auth/profile'&&r.request().method()==='POST');
  await save.click();assert.ok((await saving).ok());
  await p.waitForFunction(()=>document.querySelector('.wb-account-name').textContent==='奶龙大龙');
  const updated=await read();
  assert.equal(updated.display_name,'奶龙大龙');assert.equal(updated.username,initial.username);
  assert.equal(updated.id,initial.id);assert.equal(updated.owns_existing_data,initial.owns_existing_data);
  await open();assert.equal(await p.locator('.wb-account-name').textContent(),'奶龙大龙');
  await context.clearCookies();assert.ok((await login()).ok());await open();
  assert.equal(await p.locator('.wb-account-name').textContent(),'奶龙大龙');
  assert.deepEqual(errors,[]);
  console.log('PASS: Chinese display name, failed save and retry, refresh, login and unchanged ownership');
 }finally{await browser.close();}
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
