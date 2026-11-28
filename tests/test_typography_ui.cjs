const assert=require('node:assert/strict'),path=require('node:path');
const {chromium}=require('playwright');
const base=process.env.TYPOGRAPHY_QA_ORIGIN||'http://127.0.0.1:9935';
(async()=>{
 const browser=await chromium.launch({channel:'chrome'});
 try{
  const p=await browser.newPage({viewport:{width:1440,height:900},reducedMotion:'reduce'}),errors=[];
  p.on('pageerror',error=>errors.push(error.message));
  assert.ok((await p.request.post(base+'/auth/login',{headers:{Origin:base},data:{username:'qa_owner',password:'temporary-qa-login-123'}})).ok());
  await p.route('**/auth/changelog',r=>r.fulfill({json:{items:[]}}));
  await p.goto(base+'/',{waitUntil:'domcontentloaded'});
  const sizes=await p.evaluate(()=>{const s=getComputedStyle(document.documentElement);return ['xs','sm','base','md','lg','xl','2xl'].map(t=>s.getPropertyValue('--text-'+t).trim());});
  assert.deepEqual(sizes,['12px','13px','14px','15px','16px','18px','24px']);
  assert.equal(await p.locator('body').evaluate(e=>getComputedStyle(e).fontSize),'14px');
  await p.evaluate(()=>switchView('analysis','familiarity'));
  const header=p.locator('.workspace-breadcrumb');await header.waitFor();
  assert.equal(await header.evaluate(e=>getComputedStyle(e).fontSize),'16px');
  await p.screenshot({path:path.resolve(__dirname,'../outputs/type-scale-desktop.png')});
  await p.setViewportSize({width:390,height:800});
  await p.evaluate(()=>window.openAccountDrawer());
  const drawer=p.locator('.account-drawer[open]');await drawer.waitFor();
  const rect=await drawer.boundingBox();assert.ok(rect.x>=-1&&rect.x+rect.width<=391);
  await drawer.locator('#wb-account-members-tab').click();
  const row=drawer.locator('.wb-account-table tbody tr').first();await row.waitFor();
  assert.equal(await row.locator('td').first().evaluate(el=>getComputedStyle(el).fontSize),'13px');
  const overflow=await row.evaluate(e=>{const container=e.closest('.wb-account-table-scroll')||e.closest('table').parentElement;return {width:container.clientWidth,scrollWidth:container.scrollWidth,overflow:getComputedStyle(container).overflowX};});
  assert.ok(overflow.width>0&&(overflow.scrollWidth<=overflow.width+1||['auto','scroll'].includes(overflow.overflow)),JSON.stringify(overflow));
  await p.screenshot({path:path.resolve(__dirname,'../outputs/type-scale-mobile.png')});
  assert.deepEqual(errors,[]);
  console.log('PASS: shared type scale, header, mobile account panel and member table');
 }finally{await browser.close();}
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
