const {chromium}=require('playwright'),assert=require('node:assert/strict'),path=require('node:path');
(async()=>{
 const b=await chromium.launch({channel:'chrome',headless:true});
 try{
  const p=await b.newPage({viewport:{width:1440,height:960}}),errors=[];
  p.on('pageerror',e=>errors.push(e.message));
  const base=process.env.GUIDE_QA_ORIGIN||'http://127.0.0.1:9896';
  assert.ok((await p.request.post(base+'/auth/login',{headers:{Origin:base},data:{username:'qa_owner',password:'temporary-qa-login-123'}})).ok());
  await p.goto(base+'/');await p.waitForFunction(()=>window.emptyCoachmarkGuide&&typeof switchView==='function');
  await p.evaluate(()=>switchView('editor'));await p.locator('#cmTourRoot').waitFor();
  assert.equal(await p.locator('#cmStepPill').innerText(),'1 / 2');
  await p.locator('#cmPrimaryBtn').click();assert.equal(await p.locator('#cmStepPill').innerText(),'2 / 2');
  await p.locator('#cmSecondaryBtn').click();assert.equal(await p.locator('#cmStepPill').innerText(),'1 / 2');
  await p.locator('#cmCloseBtn').click();await p.locator('#cmTourRoot').waitFor({state:'hidden'});
  await p.locator('#cmReopenPill').click();await p.locator('#cmTourRoot').waitFor();
  await p.locator('#cmPrimaryBtn').focus();await p.waitForTimeout(1300);
  assert.equal(await p.evaluate(()=>document.activeElement.id),'cmPrimaryBtn');
  await p.evaluate(()=>document.querySelector('#transcriptDialog').showModal());
  await p.waitForTimeout(250);assert.equal(await p.locator('#cmTourRoot').isVisible(),false,'modal must suppress guide');
  await p.evaluate(()=>document.querySelector('#transcriptDialog').close());
  await p.waitForTimeout(250);
  await p.setViewportSize({width:390,height:844});await p.waitForTimeout(400);
  const rect=await p.locator('.cm-tour-card').boundingBox();
  assert.ok(rect&&rect.x>=0&&rect.x+rect.width<=390,JSON.stringify(rect));
  await p.setViewportSize({width:1440,height:960});await p.evaluate(()=>switchView('analysis','familiarity'));
  await p.waitForTimeout(450);assert.equal(await p.locator('#cmTourRoot').isVisible(),true);
  await p.screenshot({path:path.resolve(__dirname,'../outputs/empty-guide-desktop.png')});
  await p.evaluate(()=>switchView('workspace'));await p.waitForTimeout(250);
  assert.equal(await p.locator('#cmTourRoot').isVisible(),false);
  assert.deepEqual(errors,[]);console.log('PASS: steps, close/reopen, focus, modal suppression, mobile bounds, scene switch, no page errors');
 }finally{await b.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
