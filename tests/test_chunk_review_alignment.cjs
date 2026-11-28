const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const origin=process.env.WORD_SCOPE_QA_ORIGIN||'http://127.0.0.1:9919';

(async()=>{
 const browser=await chromium.launch({channel:process.env.QA_BROWSER_CHANNEL||'chrome'});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:900}}),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  const login=await page.request.post(origin+'/auth/login',{headers:{Origin:origin},data:{username:'qa_owner',password:'temporary-qa-login-123'}});
  assert.ok(login.ok());
  const project={id:'chunk-qa',name:'社区服务研究',interviews:[],interview_ids:[]};
  const paragraph='受访者：参加社区服务以后，邻居们开始互相通知活动时间，志愿者也会帮第一次到场的人登记。';
  let offset=0;
  const pieces=Array.from({length:12},(_,i)=>`提问人：请谈谈第 ${i+1} 个活动。\n${paragraph.repeat(i===5||i===9?12:5)}\n`);
  const blocks=pieces.map((part,i)=>{const start=offset;offset+=Array.from(part).length;return {id:'fixture-'+i,start,end:offset,kind:'content',include:true};});
  const issues=[5,9].map(i=>({start:blocks[i].start,action:'keep',reason:'长段落中可能存在话题转换，请对照原文核查。',resolved:false}));
  const fixture={id:'synthetic',name:'社区服务与志愿者组织访谈完整版',text:pieces.join(''),blocks,issues};
  let saved;
  await page.route('**/auth/changelog',route=>route.fulfill({json:{items:[]}}));
  await page.route('**/api/research-projects/chunk-qa/word-cooccurrence**',route=>{
   if(route.request().method()==='PUT'){saved=route.request().postDataJSON();return route.fulfill({json:{revision:2,step:2}});}
   const response=route.request().url().endsWith('/history')?[]:{status:'completed',step:2,revision:1,interviews:[fixture]};
   return route.fulfill({json:response});
  });
  await page.goto(origin+'/',{waitUntil:'domcontentloaded'});
  await page.waitForFunction(()=>!!window.researchNavigation);
  await page.evaluate(item=>{researchProjects=[item];selectedResearchProject=item;switchView('analysis','focused');},project);
  await page.getByRole('button',{name:'词语探索',exact:true}).click();
  const review=page.locator('.wc-layout');
  await review.waitFor();
  const help=page.getByLabel('关闭操作指引',{exact:true});
  if(await help.isVisible())await help.click();
  const locate=async n=>{
   await page.waitForFunction(expected=>{
    const rail=document.querySelector('.wc-cards'),active=rail?.querySelector('.wc-current-review');
    const head=active?.querySelector('.wc-card-head')?.getBoundingClientRect(),view=rail?.getBoundingClientRect();
    return active?.querySelector('.wc-block-number')?.textContent===expected&&head?.top>=view.top&&head?.bottom<=view.bottom;
   },n);
   assert.match(await page.locator('.wc-suggest-meta strong').textContent(),new RegExp('第 '+n+' 块'));
  };
  await locate('06');
  const dims=await review.evaluate(el=>{
   const headers=[...el.querySelectorAll('.wc-list>h3,.wc-middle>header,.wc-side-heading')].map(node=>node.getBoundingClientRect());
   const panels=[...el.querySelectorAll('.wc-list,.wc-middle,.wc-issues')];
   const footer=el.querySelector('.wc-issue-footer').getBoundingClientRect();
   return {headerDelta:Math.max(...headers.map(x=>x.bottom))-Math.min(...headers.map(x=>x.bottom)),widths:panels.map(x=>x.clientWidth),
    white:panels.every(x=>getComputedStyle(x).backgroundColor==='rgb(255, 255, 255)'),footerGap:panels[2].getBoundingClientRect().bottom-footer.bottom};
  });
  assert.ok(dims.headerDelta<=1&&dims.white&&dims.footerGap<=2&&dims.widths[1]>Math.max(dims.widths[0],dims.widths[2]),JSON.stringify(dims));
  if(process.env.CHUNK_QA_PNG)await review.screenshot({path:process.env.CHUNK_QA_PNG});
  await page.getByRole('button',{name:'下一项',exact:true}).click();
  await locate('10');
  const scroller=page.locator('.wc-cards');
  await scroller.evaluate(el=>{el.scrollTop=0;});
  assert.equal(await scroller.evaluate(el=>el.scrollTop),0);
  assert.match(await page.locator('.wc-suggest-meta strong').textContent(),/第 10 块/);
  await page.getByRole('button',{name:'上一项',exact:true}).click();
  await locate('06');
  await page.getByRole('button',{name:'查看相邻块',exact:true}).click();
  assert.equal(await page.locator('.wc-neighbor-highlight').count(),3);
  await page.getByRole('button',{name:'保持当前分块',exact:true}).click();
  assert.equal(await page.locator('.wc-side-heading .wc-pending-count').textContent(),'已核对');
  const saveResponse=page.waitForResponse(response=>response.url().endsWith('/chunk-qa/word-cooccurrence')&&response.request().method()==='PUT');
  await page.getByRole('button',{name:'保存进度',exact:true}).click();
  assert.ok((await saveResponse).ok());
  assert.deepEqual(saved.interviews[0].resolved,[0]);
  assert.deepEqual(saved.interviews[0].blocks,blocks);
  await page.getByRole('button',{name:/下一个复核块/}).click();
  await locate('10');
  await page.getByRole('button',{name:'收起复核栏'}).click();
  assert.ok(await page.locator('.wc-issues').isHidden());
  await page.locator('.wc-interview-title-group button.wc-pending-count').click();
  await locate('10');
  await page.getByRole('button',{name:'保持当前分块',exact:true}).click();
  const sidebar=page.locator('.nav-parent[data-group="research"]');
  const single=page.locator('.nav-item[data-tab="familiarity"]');
  if(!await single.isVisible())await sidebar.click();
  await single.click();
  await page.locator('#familiarity.active').waitFor();
  assert.ok(await page.locator('#focused').isHidden(),'跨访谈面板必须在进入单篇访谈时隐藏');
  await page.getByRole('button',{name:'访谈编码',exact:true}).click();
  await page.locator('#coding.active').waitFor();
  assert.ok(await page.locator('#coding').isVisible());
  assert.ok(await page.locator('#wordCooccurrence').isHidden());
  await page.locator('.nav-item[data-tab="focused"]').click();
  await review.waitFor();
  assert.equal(await page.locator('.wc-interview-title-group .wc-pending-count').textContent(),'已核对','返回词语探索时须保留未保存的复核修改');
  const heading=await review.evaluate(layout=>{
   const title=layout.previousElementSibling,style=getComputedStyle(title);
   return [parseFloat(style.borderBottomWidth),parseFloat(style.paddingTop),parseFloat(style.paddingBottom)];
  });
  assert.deepEqual(heading,[0,8,8]);
  await page.setViewportSize({width:640,height:900});
  await page.waitForFunction(()=>document.querySelector('.wc-layout')?.classList.contains('wc-pane-compact'));
  assert.ok(await review.evaluate(el=>el.scrollWidth<=el.clientWidth+1));
  assert.deepEqual(errors,[]);
  console.log('PASS: chunk review layout, initial and explicit navigation, manual scrolling, adjacent blocks, save payload, side panel and compact layout');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
