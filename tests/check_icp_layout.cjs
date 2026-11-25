const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:900}});
 const origin=process.env.WB_QA_ORIGIN||'http://127.0.0.1:9887';
 const out=require('node:path').resolve(__dirname,'../outputs/icp-layout-verified');
 fs.mkdirSync(out,{recursive:true});
 async function check(state){
  const link=page.locator('.site-icp-footer a');await link.waitFor();
  assert.equal(await link.count(),1);
  assert.equal(await link.textContent(),'沪ICP备2026063450号');
  assert.equal(await link.getAttribute('href'),'https://beian.miit.gov.cn/');
  const g=await link.evaluate(a=>{
   const f=a.parentElement,s=document.querySelector('.shell>.sidebar'),r=a.getBoundingClientRect();
   return {x:r.x,y:r.y,right:r.right,bottom:r.bottom,w:innerWidth,h:innerHeight,
    sidebar:s?{x:s.getBoundingClientRect().x,right:s.getBoundingClientRect().right,padding:parseFloat(getComputedStyle(s).paddingLeft)}:null,
    align:getComputedStyle(f).textAlign,bg:getComputedStyle(f).backgroundColor,
    bodyPadding:getComputedStyle(document.body).paddingBottom};
  });
  assert.ok(g.x>=0&&g.right<=g.w&&g.y>=0&&g.bottom<=g.h,JSON.stringify(g));
  assert.equal(g.bg,'rgba(0, 0, 0, 0)');assert.equal(g.bodyPadding,'0px');
  if(state==='expanded'){assert.equal(g.align,'left');assert.ok(Math.abs(g.x-g.sidebar.x-g.sidebar.padding)<1);}
  else assert.ok(g.w-g.right<=25);
  await link.focus();assert.ok(await link.evaluate(a=>document.activeElement===a));
  await page.screenshot({path:out+'/'+state+'.png'});
  console.log(state,JSON.stringify(g));
 }
 try{
  await page.goto(origin+'/account');await check('login');
  const r=await page.request.post(origin+'/auth/login',{headers:{Origin:origin},data:{username:'qa_owner',password:'temporary-qa-login-123'}});assert.ok(r.ok());
  await page.goto(origin+'/');await page.locator('#sideToggle').waitFor();
  await check('expanded');
  await page.locator('#sideToggle').click();
  await page.waitForFunction(()=>document.querySelector('.sidebar').getBoundingClientRect().width<80);
  await check('collapsed');
  await page.locator('#sideToggle').click();
  await page.waitForFunction(()=>document.querySelector('.sidebar').getBoundingClientRect().width>200);
  await check('expanded');
  await page.setViewportSize({width:390,height:844});await check('mobile');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
