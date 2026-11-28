const {chromium}=require('playwright'), assert=require('node:assert/strict'),path=require('node:path');
const origin=process.env.WORD_SCOPE_QA_ORIGIN||'http://127.0.0.1:9919';
(async()=>{
 const b=await chromium.launch({channel:'chrome'}),p=await b.newPage({viewport:{width:1440,height:900}}), errors=[], reads=[];
 try{
  p.setDefaultTimeout(45000);p.on('pageerror',e=>errors.push(e.message));
  assert.ok((await p.request.post(origin+'/auth/login',{headers:{Origin:origin},data:{username:'qa_owner',password:'temporary-qa-login-123'}})).ok());
  await p.route('**/auth/changelog',r=>r.fulfill({json:{items:[]}}));
  const projects=[{id:'scope-a',name:'社区服务研究',interviews:[],interview_ids:[]},{id:'scope-b',name:'社区活动参与研究',interviews:[],interview_ids:[]}];
  const fixtures=id=>['甲','乙'].map((letter,i)=>{const first='受访者：这是隔离测试原文 '+id+letter,part=Array.from(first).length,text=first+'。另一个话题。';return {id:id+'-'+i,name:'社区服务访谈稿'+letter+'完整版',text,issues:[{start:0,end:2,action:'keep',reason:'确认第一块的边界'},{start:part+1,end:part+3,action:'merge_previous',reason:'核对前一块是否属于同一话题'}],blocks:[{id:id+'-block-'+i+'a',start:0,end:part,include:true,kind:'content'},{id:id+'-block-'+i+'b',start:part,end:Array.from(text).length,include:true,kind:'content'}]};});
  let fail=false,allWords=false,running=false,recommendAttempts=0;const wordRequests=[];
  await p.route(/\/api\/research-projects\/scope-[ab]\/word-cooccurrence/,async r=>{
   const [,id,action='']=new URL(r.request().url()).pathname.match(/research-projects\/(scope-[ab])\/word-cooccurrence(.*)/);reads.push([id,action]);
   if(fail&&id==='scope-b'){fail=false;return r.fulfill({status:503,json:{detail:'模拟读取失败'}});}
   if(running&&id==='scope-b'&&!action)return r.fulfill({json:{status:'running',step:1,revision:3,interviews:fixtures(id)}});
   const candidates=[{word:'社区',blocks:2},{word:'服务',blocks:1}];
   if(id==='scope-a'&&action==='/recommend'){
    recommendAttempts++;
    return recommendAttempts===1?r.fulfill({json:{recommendations:[{word:'服务',reason:'用于比较服务经验'}],skipped_count:2}}):
     r.fulfill({status:502,json:{detail:'AI 输出被截断，无法读取推荐。请重试或手动选词。'}});
   }
   if(id==='scope-b'&&action==='/words'){
    const body=r.request().postDataJSON();wordRequests.push(body);
    if(body.mode==='answers'){
     await p.locator('.fw-loading-state').waitFor();
     return r.fulfill({status:422,json:{detail:'没有可统计词语'}});
    }
    allWords=true;return r.fulfill({json:candidates});
   }
   return r.fulfill({json:action==='/history'?[{id:'saved-one',name:'服务可及性',saved_at:1764050000}]:{status:'completed',step:allWords&&id==='scope-b'?3:2,confirmed:true,revision:allWords&&id==='scope-b'?2:1,history_id:action? 'saved-one':null,interviews:fixtures(id),candidates:id==='scope-a'||allWords?candidates:undefined,token_mode:allWords&&id==='scope-b'?'all':'answers'}});
  });
  await p.goto(origin+'/',{waitUntil:'domcontentloaded'});await p.waitForFunction(()=>!!window.researchNavigation);
  await p.evaluate(list=>{researchProjects=list;selectedResearchProject=list[0];switchView('analysis','focused');},projects);
  await p.getByRole('button',{name:'词语探索',exact:true}).click();
  const trigger=p.getByRole('button',{name:'项目与分析记录',exact:true}),menu=p.locator('#wcScopeMenu'),save=p.locator('.wc-save-result'),local=p.locator('.wc-interviews button.active');
  await local.waitFor();await trigger.waitFor();
  assert.equal(await p.locator('.wc-list').getByRole('button',{name:/^(全部访谈|有待复核)$/}).count(),0);
  assert.equal(await p.locator('.wc-interviews button').count(),2);
  assert.ok(await p.getByRole('switch',{name:'仅待复核',exact:true}).isVisible());
  assert.equal(await p.locator('.workspace-selector-slot select:visible').count(),0);
  assert.ok(await save.isHidden());assert.equal(await p.getByLabel('当前核对访谈').count(),0);
  assert.equal(await local.locator('span').textContent(),'社区服务访谈稿甲完整…');
  assert.equal(await p.locator('.wc-middle-clean-title').textContent(),'社区服务访…');
  const before=reads.length;
  await p.getByRole('button',{name:'社区服务访谈稿乙完整版',exact:true}).click();assert.match(await p.locator('.wc-original').first().innerText(),/scope-a乙/);assert.equal(reads.length,before);
  const suggested=p.locator('.wc-suggest-meta strong'),activeBlock=p.locator('.wc-current-review .wc-block-number');
  assert.match(await suggested.textContent(),/第 01 块/);assert.equal(await activeBlock.textContent(),'01');
  await p.getByRole('button',{name:'下一项',exact:true}).click();
  assert.match(await suggested.textContent(),/第 02 块/);assert.equal(await activeBlock.textContent(),'02');
  await p.getByRole('button',{name:'查看相邻块',exact:true}).click();assert.equal(await p.locator('.wc-neighbor-highlight').count(),2);
  await p.getByRole('button',{name:'上一项',exact:true}).click();
  assert.equal(await activeBlock.textContent(),'01');
  await trigger.focus();await p.keyboard.press('ArrowDown');assert.ok(await menu.isVisible());
  await p.keyboard.press('Escape');assert.equal(await menu.isVisible(),false);assert.ok(await trigger.evaluate(n=>n===document.activeElement));
  if(await p.getByLabel('关闭操作指引',{exact:true}).isVisible())await p.getByLabel('关闭操作指引',{exact:true}).click();
  assert.ok(await p.getByRole('button',{name:'保存进度',exact:true}).isVisible());
  const reviewHeader=p.locator('#wordCooccurrence > .wc-heading');
  const spacing=await reviewHeader.evaluate(row=>{
   const bar=row.getBoundingClientRect(),tabs=document.querySelector('.workspace-header').getBoundingClientRect();
   const action=row.querySelector('.wc-heading-actions').getBoundingClientRect(),title=row.querySelector('h2').getBoundingClientRect();
   return {above:action.top-tabs.bottom,below:bar.bottom-action.bottom-parseFloat(getComputedStyle(row).borderBottomWidth),titleOffset:(title.top+title.bottom-action.top-action.bottom)/2};
  });
  await reviewHeader.screenshot({path:path.resolve(__dirname,'../outputs/chunk-review-heading-verified.png')});
  assert.ok(Math.abs(spacing.above-spacing.below)<=1&&Math.abs(spacing.titleOffset)<=1,JSON.stringify(spacing));
  await p.screenshot({path:path.resolve(__dirname,'../outputs/cross-scope-verified.png')});
  await trigger.click();await p.screenshot({path:path.resolve(__dirname,'../outputs/cross-scope-menu-verified.png')});
  await menu.getByRole('button',{name:/服务可及性/}).click();await p.waitForFunction(()=>document.querySelector('.wc-scope-trigger').textContent.includes('服务可及性'));assert.ok(await save.isDisabled());
  await trigger.click();await menu.getByRole('button',{name:'当前草稿',exact:true}).click();await p.waitForFunction(()=>document.querySelector('.wc-scope-trigger').textContent.includes('当前草稿'));
  assert.equal(await p.locator('.workspace-tab-slot .wc-stepper .wc-stepper-item').count(),4);
  const requestsBeforeDraftReturn=reads.length;
  await p.getByRole('button',{name:'+ 新建探索',exact:true}).click();
  await p.locator('.wc-selection-page').waitFor();
  await p.getByRole('button',{name:'返回当前草稿',exact:true}).click();
  await local.waitFor();
  assert.equal(reads.length,requestsBeforeDraftReturn);
  await p.locator('.wc-stepper [data-step="3"]').click();
  const generate=p.getByRole('button',{name:/确认特征词并生成/});
  assert.ok(await generate.isDisabled());
  await p.locator('.fw-word input[data-word="社区"]').check();assert.ok(await generate.isDisabled());
  await p.locator('.wc-stepper [data-step="2"]').click();await local.waitFor();
  assert.ok(await p.getByRole('button',{name:/确认切块并继续/}).isEnabled());
  await p.locator('.wc-stepper [data-step="3"]').click();
  await p.getByRole('button',{name:'AI 推荐',exact:true}).click();
  await p.getByRole('button',{name:'开始推荐',exact:true}).click();
  await p.getByText(/已跳过 2 条/).waitFor();
  assert.ok(await p.locator('.fw-word input[data-word="社区"]').isChecked());
  assert.ok(!await p.locator('.fw-word input[data-word="服务"]').isChecked());
  await p.getByRole('button',{name:'加入勾选推荐词'}).click();assert.ok(await generate.isEnabled());
  await p.getByRole('button',{name:'重新推荐',exact:true}).click();
  await p.getByRole('alert').filter({hasText:'输出被截断'}).waitFor();
  assert.equal(await p.locator('.fw-word input:checked').count(),2);assert.equal(recommendAttempts,2);
  await p.locator('.wc-stepper [data-step="2"]').click();await local.waitFor();
  await p.locator('.wc-card summary').filter({hasText:'纳入统计'}).first().click();
  await p.getByRole('button',{name:'排除统计',exact:true}).click();
  await trigger.click();p.once('dialog',dialog=>dialog.dismiss());await menu.getByRole('button',{name:'社区活动参与研究',exact:true}).click();
  assert.match(await trigger.textContent(),/社区服务研究/);
  assert.equal(await p.locator('.wc-excluded-badge').count(),1);
  fail=true;await trigger.click();p.once('dialog',dialog=>dialog.accept());await menu.getByRole('button',{name:'社区活动参与研究',exact:true}).click();
  await p.locator('#toast').filter({hasText:'模拟读取失败'}).waitFor();assert.match(await trigger.textContent(),/社区服务研究/);
  await trigger.click();p.once('dialog',dialog=>dialog.accept());await menu.getByRole('button',{name:'社区活动参与研究',exact:true}).click();await p.waitForFunction(()=>document.querySelector('.wc-scope-trigger').textContent.includes('社区活动参与研究'));
  const autoAttempt=p.waitForResponse(r=>r.url().endsWith('/words')&&r.status()===422);
  await p.locator('.wc-stepper [data-step="3"]').click();
  const whole=p.getByRole('button',{name:/切换为.*整块原文.*并提取词语/});
  await autoAttempt;
  await whole.waitFor();assert.ok(await generate.isDisabled());
  await p.locator('.wc-stepper [data-step="2"]').click();await local.waitFor();
  await p.locator('.wc-stepper [data-step="3"]').click();await whole.click();
  await p.locator('.fw-word input[data-word="社区"]').waitFor();
  assert.deepEqual(wordRequests.map(x=>[x.mode,x.revision]),[['answers',1],['all',1]]);
  await p.setViewportSize({width:390,height:800});await trigger.click();const m=await menu.boundingBox();assert.ok(m.x>=0&&m.x+m.width<=391,JSON.stringify(m));
  const mobileColumns=locator=>locator.evaluate(el=>getComputedStyle(el).gridTemplateColumns.trim().split(/\s+/).length);
  assert.equal(await mobileColumns(p.locator('.fw-grid')),1);
  await trigger.click();running=true;await p.evaluate(()=>window.wordCooccurrence.activate());
  await p.locator('.wc-running-center').getByRole('heading',{name:/正在准备话题块/}).waitFor();
  assert.equal(await mobileColumns(p.locator('.wc-selection-grid')),1);
  assert.equal(await p.getByRole('button',{name:'返回重选',exact:true}).count(),0);
  await p.screenshot({path:path.resolve(__dirname,'../outputs/word-running-mobile.png')});
  assert.deepEqual(errors,[]);console.log('PASS: compact scope, five characters, local switch, history, unsaved guard, failure recovery and mobile bounds');
 }finally{await b.close();}
})().catch(e=>{console.error(e.stack);process.exitCode=1});
