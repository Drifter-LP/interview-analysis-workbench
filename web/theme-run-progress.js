/* Theme run polling is read-only, scoped to a unique request, and stopped on exit. */
(function(root){
 async function runThemeWithProgress(payload,onProgress,apiCall=api){
  const token=crypto.randomUUID(),body={...payload,request_token:token};
  let stopped=false,timer=null;
  const emit=data=>{if(!stopped&&onProgress)onProgress(data);};
  async function poll(){
   try{const data=await apiCall(`/api/research-projects/${encodeURIComponent(body.research_project_id)}/theme-run-status?request_token=${encodeURIComponent(token)}`);
    if(data.progress)emit(data.progress);
   }catch{/* A progress read failure must not interrupt or repeat the analysis POST. */}
   finally{if(!stopped)timer=setTimeout(poll,1200);}
  }
  emit({message:'正在准备分析…',recovering:false});
  timer=setTimeout(poll,500);
  try{return await apiCall('/api/theme-analyses',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});}
  finally{stopped=true;if(timer!==null)clearTimeout(timer);}
 }
 root.runThemeWithProgress=runThemeWithProgress;
})(globalThis);
