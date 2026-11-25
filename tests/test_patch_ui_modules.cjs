const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
 const origin=process.env.PATCH_QA_ORIGIN||'http://127.0.0.1:9891';
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:900}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(()=>Object.defineProperty(navigator,'clipboard',{value:{writeText:async value=>{window.__copiedLink=value}}}));
  const login=await page.request.post(origin+'/auth/login',{headers:{Origin:origin},data:{username:'qa_owner',password:'temporary-qa-login-123'}});assert.ok(login.ok());
  await page.goto(origin+'/');await page.waitForFunction(()=>typeof window.loadDemoSample==='function');
  const meta=await page.evaluate(()=>window.loadDemoSample('familiarity'));
  const title=page.locator('.viewpoint-title').first();await title.waitFor();
  const longTitle='跨城决策中的预算安全与同伴支持如何影响行动选择'.repeat(6);
  await title.fill(longTitle);
  const geometry=await title.evaluate(el=>({height:el.getBoundingClientRect().height,scroll:el.scrollHeight,client:el.clientHeight}));
  assert.ok(geometry.height>50&&geometry.scroll<=geometry.client+2,JSON.stringify(geometry));
  const saved=page.waitForResponse(r=>r.url().includes('/analysis-workspace')&&r.request().method()==='PUT');
  await page.locator('#saveMemoBtn').click();assert.equal((await saved).status(),200);
  const analysis=await (await page.request.get(origin+'/api/projects/'+meta.id+'/analysis-workspace')).json();
  assert.equal(analysis.familiarity_memo.viewpoints[0].title,longTitle);
  await page.locator('[data-evidence-number]').first().click();
  assert.ok(await page.locator('#memoSource mark').count()>0);
  await page.screenshot({path:require('node:path').resolve(__dirname,'../outputs/patch-memo-title-verified.png')});
  await page.evaluate(()=>window.openAccountDrawer());
  await page.getByRole('tab',{name:'成员管理'}).click();
  await page.getByRole('button',{name:'＋ 邀请成员',exact:true}).click();
  await page.locator('.wb-account-invite input[type=text]').fill('qa_patch_'+Date.now());
  await page.getByRole('button',{name:'生成邀请链接',exact:true}).click();
  await page.getByRole('button',{name:'复制链接',exact:true}).click();
  await page.waitForFunction(()=>typeof window.__copiedLink==='string');
  assert.ok(await page.evaluate(()=>window.__copiedLink.startsWith(location.origin+'/account#invite=')));
  await page.locator('.wb-account-close').click();
  assert.deepEqual(errors,[]);
  console.log('PASS: long memo title wraps and saves, evidence highlight opens, admin invitation link copies; synthetic data only, no model calls');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
