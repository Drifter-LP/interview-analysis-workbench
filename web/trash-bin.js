/* Installed inside Settings; restoration never invokes a model. */
window.installInterviewTrash=function(dialog){
 const section=document.createElement('section');section.className='interview-trash';
 section.innerHTML='<p class="trash-note">删除的访谈保留7天，期间可恢复</p><div class="trash-items" role="status">正在读取…</div>';
 dialog.append(section);
 const box=section.querySelector('.trash-items');
 async function refresh(){
  try{
   const result=await api('/api/trash/interviews');
   box.replaceChildren();
   if(!result.items.length){box.textContent='回收站为空';return;}
   for(const item of result.items){
    const row=document.createElement('div');row.className='trash-row';
    const text=document.createElement('div'),name=document.createElement('strong'),detail=document.createElement('small');
    name.textContent=item.name;
    const hours=item.expires_at?Math.max(0,Math.ceil((item.expires_at*1000-Date.now())/3600000)):null;
    detail.textContent=new Date(item.deleted_at*1000).toLocaleString('zh-CN')+' 删除 · '+(hours===null?'旧归档，暂不自动清理':hours>=24?'剩余约'+Math.ceil(hours/24)+'天':'剩余约'+hours+'小时');
    text.append(name,detail);
    const restore=document.createElement('button');restore.type='button';restore.className='trash-restore';restore.title='恢复访谈';restore.setAttribute('aria-label','恢复访谈：'+item.name);
    restore.innerHTML='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 10a9 9 0 1 1 2.7 8.4M3 4v6h6"/></svg>';
    restore.onclick=async()=>{restore.disabled=true;try{
     const result=await api('/api/trash/interviews/'+encodeURIComponent(item.id)+'/restore',{method:'POST'});
     toast(result.message||'访谈已恢复');await refresh();await Promise.all([loadProjects(),loadResearchProjects()]);
    }catch(e){restore.disabled=false;toast(e.message);}};
    row.append(text,restore);box.append(row);
   }
  }catch(e){box.textContent='回收站读取失败：'+e.message;}
 }
 refresh();
};
const trashStyle=document.createElement('style');
trashStyle.textContent='.sidebar-settings-dialog{max-height:85vh;overflow:auto}.interview-trash{border-top:1px solid #dce8e5;margin-top:20px;padding-top:4px}.trash-note{font-size:13px!important;line-height:1.7;color:#637c7c}.trash-items{font-size:14px;color:#6b8183;max-height:340px;overflow:auto}.trash-row{display:flex;align-items:center;gap:12px;padding:12px 0;border-bottom:1px solid #edf2f0}.trash-row>div{flex:1;min-width:0}.trash-row strong{display:block;overflow-wrap:anywhere;font-size:14px;font-weight:500;color:#26474b}.trash-row small{display:block;font-size:12px;line-height:1.6;margin-top:4px}.trash-restore{flex:none;border:0!important;background:transparent!important;padding:5px 7px!important;color:#008780;font-size:13px;cursor:pointer}.trash-restore:hover{background:#eaf5f2!important}.trash-restore:disabled{opacity:.45}';
document.head.append(trashStyle);
trashStyle.textContent+=' .sidebar>.sidebar-settings{margin-top:12px}.shell.collapsed .sidebar-settings span{display:none}@media(max-width:850px){.sidebar>.sidebar-settings{align-self:flex-end;margin-top:4px;padding:5px 10px}}';
trashStyle.textContent+=`.sidebar-settings-dialog{width:min(580px,calc(100vw - 32px));border:1px solid #dce8e5;border-radius:18px;padding:24px}.settings-heading{display:flex;align-items:center;gap:9px}.settings-heading h2{margin:0;font-size:21px}.settings-back{display:grid;place-items:center;width:30px;height:32px;border:0;border-radius:7px;background:none;color:#5e7b7d;cursor:pointer;padding:4px}.settings-back[hidden]{display:none}.settings-back svg{width:22px;height:22px}.settings-back:hover{background:#edf5f2}.settings-menu{display:grid;gap:10px;margin-top:6px}.settings-menu-item{display:flex;align-items:center;gap:14px;width:100%;padding:18px 16px;text-align:left;border:1px solid #e1eae7;border-radius:12px;background:#fbfdfc;color:#294b4e;cursor:pointer}.settings-menu-item:hover{background:#edf7f4;border-color:#bcd9d1}.settings-menu-item>span{flex:1}.settings-menu-item strong{display:block;font-size:16px;font-weight:600}.settings-menu-item small{display:block;font-size:13px;line-height:1.6;color:#718586;margin-top:4px}.settings-menu-icon{width:25px;height:25px;flex:none;color:#11847e}.settings-chevron{width:19px;height:19px;color:#819994}.settings-config-row{padding:12px 0;border-bottom:1px solid #edf2f0}.settings-config-row h3{margin:0!important}.settings-config-row p{margin:6px 0 0;font-size:14px}.settings-content .interview-trash{border:0;padding:0;margin:0}.trash-row .trash-restore{display:grid;place-items:center;width:36px;height:36px;padding:8px!important;border-radius:9px}.trash-restore svg{display:block;width:20px;height:20px}.trash-restore:focus-visible,.settings-back:focus-visible,.settings-menu-item:focus-visible{outline:2px solid #168b84;outline-offset:2px}`;
trashStyle.textContent+=`.settings-popover{position:fixed;inset:auto;margin:0;z-index:1000;padding:14px;border-radius:16px;background:#fff;color:#294b4e;box-shadow:0 12px 40px #163c3a24,0 2px 8px #163c3a0a;overflow:auto;overscroll-behavior:contain}.settings-popover::backdrop{background:transparent;pointer-events:none}.settings-popover .dialog-head{margin-bottom:10px;gap:12px}.settings-popover .settings-heading h2{font-size:16px}.settings-popover .icon-btn{font-size:20px;color:#819493}.settings-popover .settings-menu{gap:2px;margin:0}.settings-popover .settings-menu-item{padding:12px 8px;border:0;border-radius:9px;background:transparent;gap:11px}.settings-popover .settings-menu-item:hover{background:#edf7f4}.settings-popover .settings-menu-item strong{font-size:15px;font-weight:500}.settings-popover .settings-menu-item small{font-size:12px}.settings-popover .settings-menu-icon{width:21px;height:21px}.settings-popover .trash-note{margin:0 0 8px;font-size:12px!important}.settings-popover .trash-row{padding:10px 0}.settings-popover .trash-items{max-height:min(340px,50vh)}`;
trashStyle.textContent+='@media(max-width:850px){.sidebar>.sidebar-settings{width:auto;align-self:flex-start}}';
trashStyle.textContent+='.settings-popover[data-settings-view=""]{padding:7px;border-radius:12px}.settings-popover[data-settings-view=""]>.dialog-head{display:none}.settings-popover[data-settings-view=""] .settings-menu{gap:2px}.settings-popover[data-settings-view=""] .settings-menu-item{min-height:40px;padding:9px 10px;gap:10px}.settings-popover[data-settings-view=""] .settings-menu-icon{width:19px;height:19px}.settings-popover[data-settings-view=""] .settings-chevron{width:16px;height:16px}';
trashStyle.textContent+=`
.settings-popover{padding:12px;border-radius:12px}
.settings-popover .dialog-head{margin:0 0 6px;gap:8px;min-height:28px}
.settings-popover .settings-heading{gap:5px}
.settings-popover .settings-back{width:26px;height:28px;padding:3px}
.settings-popover .settings-back svg{width:19px;height:19px}
.settings-popover .settings-config-row{padding:8px 0}
.settings-popover .settings-config-row:first-child{padding-top:4px}
.settings-popover .settings-config-row:last-child{padding-bottom:2px;border-bottom:0}
.settings-popover .settings-config-row h3{font-size:14px;line-height:1.4}
.settings-popover .settings-config-row p{margin-top:3px;font-size:13px;line-height:1.45;overflow-wrap:anywhere}
.settings-popover .trash-note{margin:0 0 6px;line-height:1.5;font-size:13px!important}
.settings-popover .trash-row{padding:7px 0;gap:8px}
.settings-popover .trash-row strong{line-height:1.4}
.settings-popover .trash-row small{margin-top:2px;line-height:1.4;font-size:13px}
.settings-popover .trash-row .trash-restore{width:32px;height:32px;padding:6px!important}
.settings-popover .trash-restore svg{width:19px;height:19px}
.settings-popover[data-settings-view=""]{padding:6px}
.settings-popover[data-settings-view=""] .settings-menu{gap:0}
.settings-popover[data-settings-view=""] .settings-menu-item{min-height:36px;padding:6px 8px;gap:9px}
`;
