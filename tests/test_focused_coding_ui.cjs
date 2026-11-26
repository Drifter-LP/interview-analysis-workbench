const {chromium}=require('playwright'),assert=require('node:assert/strict'),path=require('node:path');
(async()=>{
 const origin=process.env.FOCUS_QA_ORIGIN||'http://127.0.0.1:9902';
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:960}}),errors=[],calls=[];
  page.on('pageerror',e=>errors.push(e.message));
  assert.ok((await page.request.post(origin+'/auth/login',{headers:{Origin:origin},data:{username:'qa_owner',password:'temporary-qa-login-123'}})).ok());
  const text='受访者：我会比较交通费用，再决定是否参加活动。',hash='synthetic-source';
  const state={current_hash:hash,sources:{[hash]:{text}},revision:1,runs:[],deleted_codes:[],codes:[]};
  for(const mode of ['explore','focused'])state.codes.push({id:mode,name:mode==='explore'?'探索建议':'聚焦建议',definition:'比较交通费用以决定参与',reason:'原文支持',coding_mode:mode,focus_question:mode==='focused'?'如何决定参加活动？':'',focus_label:'出行成本',source_hash:hash,source_id:'t',origin:'ai',status:'pending',revision:0,references:[{id:'r',start:7,end:13,quote:text.slice(7,13),validation:'valid'}]});
  await page.route('**/api/research-projects/p/ai-coding/t**',async route=>{
   if(route.request().method()==='POST'&&route.request().url().endsWith('/run')){calls.push(route.request().postDataJSON());return route.fulfill({json:{run_id:'synthetic'}});}
   return route.fulfill({json:state});
  });
  await page.goto(origin+'/');await page.waitForFunction(()=>!!window.aiCodingDemo);
  await page.evaluate(async()=>{
   window.singleInterviewCodingContext={get:()=>({sourceId:'t',researchProjectId:'p'}),projects:()=>[{id:'p',name:'隔离测试项目',interview_ids:['t']}],setScope(){}};
   switchView('analysis','coding');await window.aiCodingDemo.activateCurrent();
  });
  await page.locator('.ac-code').first().waitFor();
  await page.locator('.ac-code').first().click();
  await page.getByLabel('编码名称',{exact:true}).fill('尚未保存的修改');
  page.once('dialog',d=>d.dismiss());
  await page.getByRole('button',{name:'🎯 问题聚焦',exact:true}).click();
  assert.equal(await page.getByLabel('编码名称',{exact:true}).inputValue(),'尚未保存的修改');
  assert.equal(await page.getByLabel('聚焦编码研究问题').isVisible(),false);
  page.once('dialog',d=>d.accept());
  await page.getByRole('button',{name:'🎯 问题聚焦',exact:true}).click();
  assert.equal(await page.locator('.ac-code').count(),1);
  await page.getByLabel('聚焦编码研究问题').fill('如何决定参加活动？');
  await page.getByLabel('添加关注维度标签').fill('出行成本');await page.getByLabel('添加关注维度标签').press('Enter');
  page.on('dialog',d=>d.accept());
  await page.getByRole('button',{name:'🎯 按焦点AI编码',exact:true}).click();
  await page.waitForTimeout(200);assert.equal(calls.length,1);assert.equal(calls[0].mode,'focused');assert.deepEqual(calls[0].focus_dimensions,['出行成本']);
  await page.reload();await page.waitForFunction(()=>!!window.aiCodingDemo);
  await page.evaluate(async()=>{window.singleInterviewCodingContext={get:()=>({sourceId:'t',researchProjectId:'p'}),projects:()=>[{id:'p',name:'隔离测试项目',interview_ids:['t']}],setScope(){}};switchView('analysis','coding');await window.aiCodingDemo.activateCurrent();});
  await page.getByLabel('聚焦编码研究问题').waitFor();assert.equal(await page.getByLabel('聚焦编码研究问题').inputValue(),'如何决定参加活动？');
  if(await page.getByLabel('关闭操作指引',{exact:true}).isVisible())await page.getByLabel('关闭操作指引',{exact:true}).click();
  await page.screenshot({path:path.resolve(__dirname,'../outputs/focused-coding-verified.png')});
  for(const width of [720,390]){await page.setViewportSize({width,height:900});await page.waitForTimeout(100);assert.ok(await page.getByLabel('聚焦编码研究问题').isVisible());}
  assert.deepEqual(errors,[]);
  const guest=await browser.newPage();
  assert.ok((await guest.request.post(origin+'/auth/guest',{headers:{Origin:origin},data:{}})).ok());
  await guest.goto(origin+'/?guest=1');await guest.waitForFunction(()=>!!window.aiCodingDemo);await guest.evaluate(()=>switchView('analysis','coding'));
  assert.ok(await guest.getByRole('button',{name:'开始AI编码',exact:true}).isDisabled());
  console.log(JSON.stringify({passed:true,checks:['focused-filter','focus-payload','draft-reload','desktop-mobile','guest-disabled','no-pageerrors']}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
