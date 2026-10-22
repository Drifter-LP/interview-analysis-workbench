/* Read-only scope resolution: keep persisted project/transcript identities unchanged. */
((root)=>{
 function resolve(projects,sourceId,preferredId='',previousId=''){
  const tid=String(sourceId||'');
  const candidates=tid?projects.filter(p=>[...(p.interview_ids||[]),...(p.interviews||[]).map(x=>x.id),...(p.uploaded_transcripts||[]).map(x=>x.workspace_project_id)].some(id=>id!=null&&String(id)===tid)):[];
  const project=candidates.find(p=>String(p.id)===String(preferredId))||candidates.find(p=>String(p.id)===String(previousId))||candidates[0]||null;
  return {sourceId:tid,project,candidates};
 }
 const api={resolve};if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.aiCodingContext=api;
})(typeof window!=='undefined'?window:globalThis);
