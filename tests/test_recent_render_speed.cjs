const {chromium}=require('playwright'),assert=require('node:assert/strict');
const {performance}=require('node:perf_hooks');
const before=process.env.RECENT_RENDER_BASE||'http://127.0.0.1:9916';
const after=process.env.RECENT_RENDER_NEW||'http://127.0.0.1:9917';
const pair='访谈者：请回忆第一次参加社区活动的经过。\n受访者：当时我先询问了邻居，再到活动室登记。这是构造的测试资料。\n';
const docs=['原文前言\n'+pair.repeat(750)+'访谈者：结尾甲','原文前言\n'+pair.repeat(750)+'访谈者：结尾乙'];
async function run(browser,origin,optimized){
 const p=await browser.newPage({viewport:{width:1440,height:960}}),errors=[],rows=[];
 p.setDefaultTimeout(65000);p.on('pageerror',e=>errors.push(e.message));
 try{
  assert.ok((await p.request.post(origin+'/auth/login',{headers:{Origin:origin},data:{username:'qa_owner',password:'temporary-qa-login-123'}})).ok());
  const m=await (await p.request.get(origin+'/auth/me')).json(),headers={Origin:origin,'X-CSRF-Token':m.csrf},ids=[];
  for(const [i,text] of docs.entries()){
   const imported=await p.request.post(origin+'/api/transcript-projects',{headers,multipart:{transcript:{name:'长访谈模拟-'+i+'.txt',mimeType:'text/plain',buffer:Buffer.from(text)}}});assert.ok(imported.ok(),'synthetic import '+imported.status());
   const id=(await imported.json()).id;ids.push(id);
   assert.ok((await p.request.put(origin+'/api/projects/'+id+'/transcript',{headers,data:{text}})).ok());
  }
  await p.goto(origin+'/',{waitUntil:'networkidle'});await p.waitForFunction(()=>typeof window.formatTranscriptTurns==='function'&&!!window.researchNavigation);
  await p.evaluate(()=>{
   window.__renderProbe=[];
   const format=window.formatTranscriptTurns;
   window.formatTranscriptTurns=function(text,root){
    const t=performance.now(),result=format(text,root);
    window.__renderProbe.push({id:root?.id||'transcript',chars:text.length,ms:performance.now()-t});
    return result;
   };
  });
  for(let k=0;k<3;k++){
   const i=k%2, id=ids[i];await p.evaluate(()=>window.__renderProbe=[]);
   const started=performance.now();
   await p.locator('.sb-recent-item[data-project-id="'+id+'"]').click();
   await p.waitForFunction(end=>document.querySelector('#analysis.active #familiarity.active #memoSource')?.textContent.endsWith(end),i===0?'结尾甲':'结尾乙');
   const originalMs=performance.now()-started;
   await p.waitForFunction(()=>!document.querySelector('#memoStatus').textContent.includes('正在读取'));
   const snapshot=await p.locator('#memoSource').evaluate(n=>({text:n.textContent,turns:n.querySelectorAll('.transcript-turn').length,fmt:window.__renderProbe}));
   assert.equal(snapshot.text,docs[i]);assert.equal(snapshot.turns,1501);
   const memo=snapshot.fmt.filter(r=>r.id==='memoSource');
   assert.equal(memo.length,optimized?1:2,'background memo should not reformat the source');
   rows.push({originalMs,editorFormatMs:snapshot.fmt.find(r=>r.id==='transcript')?.ms,memoFormatMs:memo[0].ms,memoPaints:memo.length});
   console.log(optimized?'candidate':'baseline', 'sample',k+1,JSON.stringify(rows.at(-1)));
  }
  // The annotation path is deliberately retained. Verify an evidence highlight
  // remains a real mark, and a literal HTML-looking string stays plain text.
  await p.evaluate(()=>{
   const source=document.querySelector('#memoSource');source.dataset.text='访谈者：<b>字面文本</b>\n受访者：这是证据';
   analysisData={...analysisData,familiarity_memo:{evidence:[{number:1,start:source.dataset.text.indexOf('这是证据'),end:source.dataset.text.length,quote:'这是证据'}]}};
   renderMemoSource(1);
  });
  assert.equal(await p.locator('#memoEvidenceHit').filter({hasText:'这是证据'}).textContent(),'这是证据');assert.equal(await p.locator('#memoSource b').count(),0);
  assert.deepEqual(errors,[]);
  return rows;
 }finally{await p.close();}
}
(async()=>{
 const browser=await chromium.launch({channel:'chrome'});
 try{
  const result={before:await run(browser,before,false),after:await run(browser,after,true)};
  for(const [version,rows] of Object.entries(result))console.log(version,rows.map(r=>Object.fromEntries(Object.entries(r).map(([k,v])=>[k,Math.round(v)]))));
  if(process.env.RECENT_RENDER_REPORT)require('node:fs').writeFileSync(process.env.RECENT_RENDER_REPORT,JSON.stringify(result,null,2));
 }finally{await browser.close();}
})().catch(e=>{console.error(e.message);process.exitCode=1});
