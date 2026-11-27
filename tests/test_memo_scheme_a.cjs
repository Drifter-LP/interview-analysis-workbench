const assert=require('node:assert/strict');
const {chromium}=require('playwright');
const base=process.env.MEMO_UI_ORIGIN||'http://127.0.0.1:9924';
(async()=>{
 const browser=await chromium.launch({channel:'chrome'});
 try{
  const p=await browser.newPage({viewport:{width:1440,height:900}}),errors=[];
  p.on('pageerror',e=>errors.push(e.message));
  assert.ok((await p.request.post(base+'/auth/login',{headers:{Origin:base},data:{username:'qa_owner',password:'temporary-qa-login-123'}})).ok());
  const me=await (await p.request.get(base+'/auth/me')).json();
  await p.addInitScript(id=>localStorage.setItem('wb_seen_changelog_id:'+id,'seed-20261126'),me.id);
  await p.goto(base+'/',{waitUntil:'domcontentloaded'});
  await p.evaluate(()=>{
   switchView('analysis','familiarity');
   interviewAnalysisRead=null;
   analysisData={familiarity_memo:{participant_identity:'测试受访者',interview_date:'2026-11-27',interview_topic:'社区服务参与',summary:'测试摘要',viewpoints:[{title:'这是测试观点的长标题，用来检验较窄的内容区仍能完整显示和编辑。'.repeat(3),summary:'观点摘要',points:[{text:'测试细节'}]}]}};
   renderMemo({keepSource:true});
  });
  const identity=p.getByLabel('受访者',{exact:true}),topic=p.getByLabel('主题',{exact:true}),title=p.getByRole('textbox',{name:'观点标题'}),details=p.locator('.memo-detail summary');
  await identity.waitFor();assert.equal(await identity.inputValue(),'测试受访者');
  assert.equal(await topic.inputValue(),'社区服务参与');
  assert.equal(await p.locator('.viewpoint-index').textContent(),'01');assert.match(await details.textContent(),/1 项/);
  assert.ok((await title.boundingBox()).height>32);
  await details.focus();await p.keyboard.press('Enter');assert.equal(await title.isVisible(),false);
  await p.keyboard.press('Enter');await title.waitFor();await title.fill('修改后的观点');
  await identity.fill('修改后的受访者');assert.equal(await identity.inputValue(),'修改后的受访者');
  assert.ok(await p.locator('#saveMemoBtn').isEnabled());
  await p.setViewportSize({width:390,height:800});
  const bounds=await p.locator('.memo-meta').boundingBox();assert.ok(bounds.width>0&&bounds.x+bounds.width<=391);
  const date=await p.getByLabel('日期',{exact:true}).boundingBox();assert.ok(date.y>(await identity.boundingBox()).y);
  await p.evaluate(()=>{analysisData={};renderMemo({keepSource:true});});
  assert.ok(await p.locator('#saveMemoBtn').isDisabled());assert.match(await p.locator('#memoPanel').innerText(),/生成纪要/);
  assert.deepEqual(errors,[]);
  console.log('PASS: memo metadata, long title, edit controls, keyboard disclosure, narrow layout, empty state');
 }finally{await browser.close();}
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
