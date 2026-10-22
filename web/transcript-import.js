/* Batch library import reuses the single-file API, preserving per-file results. */
(()=>{
 const dialog=document.querySelector('#transcriptDialog'),form=document.querySelector('#transcriptForm');
 if(!dialog||!form)return;
 const input=form.querySelector('#transcriptInput'),name=form.querySelector('[name="name"]');
 const nameField=form.querySelector('#transcriptNameField'),label=form.querySelector('#transcriptFileLabel');
 const hint=form.querySelector('#transcriptImportHint'),status=form.querySelector('#transcriptImportStatus');
 const results=form.querySelector('#transcriptImportResults'),submit=form.querySelector('#submitTranscript');
 const close=form.querySelector('#closeTranscriptDialog'),cancel=form.querySelector('#cancelTranscriptDialog');
 let tasks=[],busy=false,batch=false;
 const stem=file=>file.name.replace(/\.(txt|docx)$/i,'');
 function render(){
  label.textContent=tasks.length>1?`已选择 ${tasks.length} 份访谈稿`:tasks[0]?.file.name||'选择 TXT 或 Word 访谈稿';
  nameField.hidden=batch;name.disabled=busy||batch;
  hint.textContent=batch?'每份访谈按各自文件名命名，不会合并':'可按 Shift 连选或 Ctrl 多选，每份文件单独导入';
  results.hidden=!tasks.length;results.replaceChildren();
  for(const task of tasks){
   const li=document.createElement('li'),text=document.createElement('span'),state=document.createElement('span');
   text.className='import-file-name';text.textContent=task.file.name;
   if(task.error){const error=document.createElement('small');error.className='import-error';error.textContent=task.error;text.append(error)}
   state.className='import-file-state'+(task.state==='success'?' import-success':task.state==='failed'?' import-failed':'');
   state.textContent=({pending:'待导入',running:'导入中…',success:'已导入',failed:'失败'})[task.state];
   li.append(text,state);results.append(li);
  }
 }
 function setBusy(value){
  busy=value;form.setAttribute('aria-busy',String(value));
  input.disabled=value;submit.disabled=value;close.disabled=value;cancel.disabled=value;name.disabled=value||batch;
 }
 function reset(){tasks=[];batch=false;form.reset();status.hidden=true;status.textContent='';submit.textContent='导入';render()}
 input.onchange=()=>{
  if(busy)return;
  tasks=Array.from(input.files||[],file=>({file,name:null,state:'pending',error:''}));batch=tasks.length>1;
  status.hidden=true;submit.textContent='导入';render();
 };
 dialog.addEventListener('cancel',event=>{if(busy)event.preventDefault()});
 dialog.addEventListener('close',()=>{if(!busy)reset()});
 form.onsubmit=async event=>{
  event.preventDefault();if(busy)return;
  const pending=tasks.filter(task=>task.state!=='success');
  if(!pending.length){status.hidden=false;status.textContent='请先选择 TXT 或 DOCX 访谈稿';return}
  for(const task of pending)if(task.name===null||!batch)task.name=batch?stem(task.file):name.value.trim()||stem(task.file);
  setBusy(true);status.hidden=false;
  try{
   for(let i=0;i<pending.length;i++){
    const task=pending[i];task.state='running';task.error='';render();
    submit.textContent=`导入中 ${i+1}/${pending.length}`;status.textContent=`正在导入 ${i+1}/${pending.length}：${task.file.name}`;
    try{
     if(!/\.(txt|docx)$/i.test(task.file.name))throw new Error('仅支持 TXT 或 DOCX 文件');
     const data=new FormData();data.append('name',task.name);data.append('transcript',task.file,task.file.name);
     task.project=await api('/api/transcript-projects',{method:'POST',body:data});task.state='success';
    }catch(error){task.state='failed';task.error=error.message||'导入失败，请检查列表后重试'}
    render();
   }
   const successes=tasks.filter(task=>task.state==='success'),failures=tasks.filter(task=>task.state==='failed');
   let refreshed=true;
   try{await loadProjects()}catch(error){refreshed=false}
   if(failures.length){
    status.textContent=`已导入 ${successes.length} 份，失败 ${failures.length} 份。重试仅处理失败项。`+(refreshed?'':'列表刷新失败，请稍后刷新页面。');
    submit.textContent='重试失败项';
   }else{
    const single=!batch&&successes.length===1?successes[0].project:null;
    const count=successes.length;setBusy(false);dialog.close();
    toast(refreshed?`已导入 ${count} 份访谈稿`:`已导入 ${count} 份，列表刷新失败，请刷新页面`);
    try{if(single)await openProject(single.id);else switchView('workspace')}catch(error){toast('访谈稿已导入，打开页面失败，请从访谈资料中查看')}
   }
  }finally{setBusy(false);if(submit.textContent.startsWith('导入中'))submit.textContent='导入'}
 };
 render();
})();
