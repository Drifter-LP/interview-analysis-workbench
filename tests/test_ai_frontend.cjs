const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(require('node:path').join(__dirname,'../web/app.js'),'utf8');
function setup(name){
 let resolve;let calls=0;
 const ctx={selected:'A',analysisData:{page:'A',familiarity_memo:{summary:'old'}},
 api:()=>{calls++;return new Promise(r=>resolve=r)},$:()=>({textContent:''}),
 setAiLoading:()=>{},renderMemo:()=>{},toast:()=>{},collectMemo:()=>{}};
 vm.createContext(ctx);
 vm.runInContext("const memoRequests=new Map();\n"+source.split(/\r?\n/).find(l=>l.startsWith('async function '+name+'(')),ctx);
 return {ctx,finish:v=>resolve(v),calls:()=>calls};
}
(async()=>{
 for(const name of ['generateMemo','generateMemoSummary']){
  const {ctx,finish}=setup(name);const pending=ctx[name]();
  ctx.selected='B';ctx.analysisData={page:'B',familiarity_memo:{summary:'B'}};
  finish({memo:{source:'A'},summary:'A',_version:'A'});
  await pending;assert.equal(ctx.analysisData.familiarity_memo.summary,'B');
  assert.equal(ctx.analysisData.familiarity_memo.source,undefined);
 }
 const x=setup('generateMemo'),first=x.ctx.generateMemo();await x.ctx.generateMemo();
 assert.equal(x.calls(),1);x.finish({memo:{summary:'A'},_version:'v1'});await first;
 assert.equal(x.ctx.analysisData._version,'v1');
 console.log('PASS: memo/summary stale-response guards and duplicate submission');
})().catch(e=>{console.error(e);process.exitCode=1});
