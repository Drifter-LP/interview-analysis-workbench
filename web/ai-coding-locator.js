/* Assistance only: never repairs or rewrites a stored reference. */
(function(scope){
 function locateUnresolved(ref,code,state){
  if(!ref||ref.validation==='valid'||!code)return null;
  const run=state.runs.find(r=>r.id===code.run_id&&r.source_hash===code.source_hash);
  const unit=run?.units?.flat().find(u=>u.unit_id===ref.unit_id),text=state.sources[code.source_hash]?.text;
  if(!unit||typeof text!=='string'||Array.from(text).slice(unit.start,unit.end).join('')!==unit.text)return null;
  const fragments=[];
  for(const part of [...new Set(String(ref.quote||'').split(/\.{3,}|…+/).map(s=>s.trim()).filter(s=>Array.from(s).length>=4))]){
   let cursor=0;
   while(true){const at=unit.text.indexOf(part,cursor);if(at<0)break;const start=unit.start+Array.from(unit.text.slice(0,at)).length;fragments.push({start,end:start+Array.from(part).length});cursor=at+1;}
  }
  return {start:unit.start,end:unit.end,unit_id:unit.unit_id,fragments};
 }
 if(typeof module!=='undefined')module.exports={locateUnresolved};
 if(scope)scope.aiCodingLocator={locateUnresolved};
})(typeof window!=='undefined'?window:null);
