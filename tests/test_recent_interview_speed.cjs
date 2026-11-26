const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const {performance}=require('node:perf_hooks');
const url=process.env.RECENT_QA_ORIGIN||'http://127.0.0.1:9912';
const delay=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
  const page=await browser.newPage(),errors=[],calls=[];
  page.on('pageerror',e=>errors.push(e.message));
  const auth=await page.request.post(url+'/auth/login',{headers:{Origin:url},data:{username:'qa_owner',password:'temporary-qa-login-123'}});assert.ok(auth.ok());
  const ids=['recent-qa-a','recent-qa-b','recent-qa-editor'];
  const fixture=Object.fromEntries(ids.map((id,i)=>[id,{id,name:'虚构访谈 '+i,status:'completed',source_type:'transcript',created_at:200-i,edited_at:i<2?1:null}]));
  const transcript=id=>({text:'受访者：测试原文 '+id,edited:!!fixture[id].edited_at,annotations:[]});
  let slow='',failMemo=false,failText=false,memoGate=null,releaseMemo;
  await page.route(/\/api\/projects\/recent-qa-/,async route=>{
   const [,id,action='']=new URL(route.request().url()).pathname.match(/projects\/(recent-qa-[^/]+)(?:\/(.*))?$/);
   calls.push({id,action});
   let status=200,json;
   if(action==='opened')json={last_opened_at:Date.now()/1000};
   else if(action==='analysis-workspace'){await (memoGate||delay(650));if(failMemo){failMemo=false;status=502;json={detail:'模拟纪要读取失败'};}else json={metadata:{},familiarity_memo:{topic:'',interview_topic:'模拟纪要 '+id,viewpoints:[],evidence:[]}};}
   else{await delay(slow===id?550:150);if(action==='open-transcript'&&failText){failText=false;status=503;json={detail:'模拟原文读取失败'};}else json=action==='open-transcript'?{project:fixture[id],transcript:transcript(id)}:action==='transcript'?transcript(id):fixture[id];}
   // An aborted read is no longer a browser response.
   await route.fulfill({status,json}).catch(()=>{});
  });
  await page.goto(url+'/',{waitUntil:'networkidle',timeout:90000});
  await page.waitForFunction(()=>!!window.updateSidebarWidgets&&!!window.researchNavigation);
  await page.evaluate(rows=>{projects=rows;window.updateSidebarWidgets();},Object.values(fixture));
  const link=id=>page.locator('.sb-recent-item[data-project-id="'+id+'"]');
  const text=id=>page.locator('#memoSource').filter({hasText:'测试原文 '+id});
  const a=ids[0],b=ids[1];
  const startOld=performance.now();
  await page.evaluate(async id=>{await openProject(id,null,{targetTab:'familiarity'});switchView('analysis','familiarity');},a);
  await text(a).waitFor();
  const oldMs=performance.now()-startOld;
  memoGate=new Promise(resolve=>{releaseMemo=resolve;});
  const startNew=performance.now();await link(b).click();await text(b).waitFor();
  const newMs=performance.now()-startNew;
  assert.match(await page.locator('#memoStatus').textContent(),/正在读取/);
  assert.ok(await page.locator('#generateMemoBtn').isDisabled());
  releaseMemo();memoGate=null;
  await page.waitForFunction(id=>document.querySelector('#memoTopic')?.value==='模拟纪要 '+id,b);
  assert.equal(calls.filter(c=>c.id===b&&c.action==='open-transcript').length,1);
  assert.equal(calls.filter(c=>c.id===b&&(c.action===''||c.action==='transcript')).length,0);
  slow=a;
  await link(a).click();await link(b).click();await delay(750);
  assert.ok(await text(b).isVisible());assert.ok(await link(b).getAttribute('aria-current'));
  slow='';failText=true;
  await link(a).click();await page.locator('#toast').filter({hasText:'模拟原文读取失败'}).waitFor();
  assert.ok(await text(b).isVisible());assert.equal(await link(a).getAttribute('aria-busy'),null);
  failMemo=true;
  await link(a).focus();await page.keyboard.press('Enter');await text(a).waitFor();
  await page.locator('#memoPanel').getByRole('button',{name:'重试',exact:true}).click();
  await page.waitForFunction(id=>document.querySelector('#memoTopic')?.value==='模拟纪要 '+id,a);
  const beforePicker=calls.length;
  memoGate=new Promise(resolve=>{releaseMemo=resolve;});
  await page.evaluate(id=>openMaterialMemo('workspace',id),b);
  await text(b).waitFor();
  assert.match(await page.locator('#memoStatus').textContent(),/正在读取/);
  assert.ok(calls.slice(beforePicker).some(x=>x.id===b&&x.action==='open-transcript'));
  assert.ok(!calls.slice(beforePicker).some(x=>x.id===b&&(x.action===''||x.action==='transcript')));
  releaseMemo();memoGate=null;
  await page.waitForFunction(id=>document.querySelector('#memoTopic')?.value==='模拟纪要 '+id,b);
  await link(ids[2]).click();
  await page.locator('#editor.active').waitFor();
  assert.equal(await page.evaluate(()=>transcriptText()),transcript(ids[2]).text);
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({oldMs:Math.round(oldMs),newMs:Math.round(newMs),checks:['原文优先','后台纪要','快速切换','请求失败保留原文','键盘重试','未修订跳转']}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
