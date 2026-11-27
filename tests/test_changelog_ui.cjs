const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const origin = process.env.CHANGELOG_QA_ORIGIN || 'http://127.0.0.1:9921';

async function login(context, username, password) {
  const response = await context.request.post(origin+'/auth/login', {headers:{Origin:origin},data:{username,password}});
  assert.ok(response.ok());
  return (await (await context.request.get(origin+'/auth/me')).json()).csrf;
}

(async()=>{
  const browser=await chromium.launch({channel:'chrome'});
  try {
    const admin=await browser.newContext({reducedMotion:'reduce'});
    const member=await browser.newContext({reducedMotion:'reduce',viewport:{width:390,height:800}});
    const url=origin+'/auth/admin/changelog';
    const data={date:'2099-01-31',content:'隔离测试：未来通知'};
    assert.equal((await admin.request.get(origin+'/auth/changelog')).status(),401);
    const adminCsrf=await login(admin,'qa_owner','temporary-qa-login-123');
    const memberCsrf=await login(member,'qa_friend','temporary-qa-friend-123');
    assert.equal((await member.request.post(url,{headers:{Origin:origin,'X-CSRF-Token':memberCsrf},data})).status(),403);
    assert.equal((await admin.request.post(url,{headers:{Origin:origin},data})).status(),403);
    assert.equal((await admin.request.post(url,{headers:{Origin:origin,'X-CSRF-Token':adminCsrf},data:{...data,date:'2026-02-30'}})).status(),400);
    const p=await admin.newPage(), errors=[];
    p.on('pageerror',error=>errors.push(error.message));
    await p.goto(origin+'/',{waitUntil:'domcontentloaded'});
    const bell=p.getByRole('button',{name:'更新通知',exact:true});
    const notice=p.getByRole('dialog',{name:'更新通知',exact:true});
    await notice.getByRole('button',{name:'知道了'}).click();
    await bell.click();await notice.getByRole('button',{name:/拟定新通知/}).click();
    const compose=p.getByRole('dialog',{name:'拟定更新通知'});
    await compose.locator('input[type=date]').fill(data.date);
    await compose.locator('textarea').fill(data.content);
    const submit=compose.getByRole('button',{name:'保存并发布'});
    await p.route(url,route=>route.fulfill({status:404,json:{detail:'模拟发布失败'}}),{times:1});
    await submit.click();await compose.getByRole('alert').filter({hasText:'模拟发布失败'}).waitFor();
    assert.equal(await compose.locator('textarea').inputValue(),data.content);
    const saving=p.waitForResponse(r=>r.url()===url&&r.request().method()==='POST');
    await submit.click();const saved=await saving;assert.ok(saved.ok());
    const pending=(await saved.json()).items.find(item=>item.content===data.content);
    assert.ok(pending?.id);
    assert.equal((await admin.request.post(url,{headers:{Origin:origin,'X-CSRF-Token':adminCsrf},data:{...data,id:'seed-20261126'}})).status(),400);
    await notice.getByText(data.content,{exact:true}).waitFor();
    await notice.getByText(/待发布/).waitFor();
    await notice.getByRole('button',{name:/历史通知/}).click();
    assert.equal(await notice.locator('#wbClHistoryBox').getByText(/待发布/).count(),0);
    await notice.getByRole('button',{name:'修改',exact:true}).click();
    const editDialog=p.getByRole('dialog',{name:'修改更新通知'});
    assert.equal(await editDialog.locator('textarea').inputValue(),data.content);
    const updatedContent='隔离测试：修改后的未来通知';
    await editDialog.locator('textarea').fill(updatedContent);
    const updating=p.waitForResponse(r=>r.url()===url&&r.request().method()==='POST');
    await editDialog.getByRole('button',{name:'保存并发布'}).click();const updated=await updating;assert.ok(updated.ok());
    assert.equal((await updated.json()).items.find(item=>item.content===updatedContent).id,pending.id);
    await notice.getByText(updatedContent,{exact:true}).waitFor();
    data.content=updatedContent;
    await p.keyboard.press('Escape');assert.equal(await bell.evaluate(e=>e===document.activeElement),true);
    await p.evaluate(()=>localStorage.removeItem('wb_seen_changelog_id:'+window.workbenchSession.id));
    await p.reload({waitUntil:'domcontentloaded'});
    await notice.getByText(/访谈编码新增/).first().waitFor();
    assert.equal(await notice.getByRole('button',{name:'修改',exact:true}).count(),0);
    await notice.getByRole('button',{name:'知道了'}).click();
    const m=await member.newPage();m.on('pageerror',error=>errors.push(error.message));
    await m.goto(origin+'/',{waitUntil:'domcontentloaded'});
    const memberNotice=m.getByRole('dialog',{name:'更新通知',exact:true});
    await memberNotice.getByRole('button',{name:'知道了'}).click();
    await m.reload({waitUntil:'domcontentloaded'});
    const memberBell=m.getByRole('button',{name:'更新通知',exact:true});
    await memberBell.click();
    assert.equal(await memberNotice.getByRole('button',{name:/拟定新通知/}).count(),0);
    assert.ok(!(await (await member.request.get(origin+'/auth/changelog')).text()).includes(data.content));
    const bounds=await memberNotice.boundingBox();assert.ok(bounds.x>=0&&bounds.x+bounds.width<=390);
    assert.deepEqual(errors,[]);
    console.log('PASS: changelog role, CSRF, invalid date, failed save & retry, schedule visibility, mobile and keyboard');
  }finally{await browser.close();}
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
