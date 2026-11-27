const assert=require('node:assert/strict');
const {chromium}=require('playwright');
const base=process.env.MEMO_UI_ORIGIN||'http://127.0.0.1:9925';
(async()=>{
 const browser=await chromium.launch({channel:'chrome'});
 try{
  const p=await browser.newPage({viewport:{width:1440,height:900}});
  assert.ok((await p.request.post(base+'/auth/login',{headers:{Origin:base},data:{username:'qa_owner',password:'temporary-qa-login-123'}})).ok());
  const me=await (await p.request.get(base+'/auth/me')).json();
  const headers={Origin:base,'X-CSRF-Token':me.csrf};
  await p.addInitScript(id=>localStorage.setItem('wb_seen_changelog_id:'+id,'seed-20261126'),me.id);
  const names=['社区出行访谈甲','社区出行访谈乙'];
  for(const name of names){
   const r=await p.request.post(base+'/api/transcript-projects',{headers,multipart:{transcript:{name:name+'.txt',mimeType:'text/plain',buffer:Buffer.from('受访者：'+name+'测试原文。')}}});
   assert.ok(r.ok(),String(r.status()));
  }
  await p.goto(base+'/',{waitUntil:'domcontentloaded'});
  await p.waitForFunction(()=>projects.filter(x=>x.name.startsWith('社区出行访谈')).length===2);
  await p.evaluate(()=>switchView('analysis','familiarity'));
  const toggle=p.locator('.workspace-header .single-interview-picker > button');
  const group=p.getByRole('button',{name:/未归入项目的访谈/});
  for(const name of names){
   await toggle.click();await group.click();
   const item=p.locator('.single-interview-picker .memo-cascade-sub button').filter({hasText:name});
   const full=await item.textContent();assert.ok(full.startsWith(name));
   await item.click();
   await p.waitForFunction(full=>document.querySelector('.workspace-header .single-interview-picker > button')?.title===full,full);
   assert.equal(await toggle.textContent(),'社区出行访… ▾');
   assert.equal(await toggle.getAttribute('aria-label'),'选择访谈稿：'+full);
   await p.waitForFunction(name=>document.querySelector('#memoSource').textContent.includes(name+'测试原文'),name);
  }
  await p.evaluate(()=>switchView('analysis','coding'));
  assert.equal(await toggle.textContent(),'社区出行访… ▾');
  assert.ok((await toggle.boundingBox()).width<=113);
  console.log('PASS: full menu names, matching five-character prefixes, real transcript switching, coding tab');
 }finally{await browser.close();}
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
