(() => {
  const root = document.querySelector('#workspace');
  function install() {
    root.querySelectorAll('.library-menu:not([data-move-ready])').forEach(menu => {
      menu.dataset.moveReady = 'true';
      const row = menu.closest('.library-row'), group = menu.closest('.library-group').dataset.groupId;
      const trigger = document.createElement('button'); trigger.type = 'button'; trigger.className = 'library-move-trigger'; trigger.textContent = '移动到项目　›'; trigger.setAttribute('aria-expanded', 'false');
      trigger.disabled = row.querySelector('[data-open]').disabled;
      const submenu = document.createElement('div'); submenu.className = 'library-move-submenu'; submenu.hidden = true;
      const targets = researchProjects.filter(p => p.id !== group);
      if (!targets.length) submenu.textContent = '暂无其他项目';
      for (const target of targets) {
        const button = document.createElement('button'); button.type = 'button'; button.textContent = '▱　' + target.name; button.title = target.name;
        button.onclick = async event => {
          event.stopPropagation();
          const label = row.querySelector('[data-rename-kind]');
          const payload = {source_project:group === 'unassigned' ? '' : group, target_project:target.id};
          if (label.dataset.renameKind === 'uploaded') payload.uploaded_index = Number(label.dataset.renameId);
          else payload.interview_id = label.dataset.renameId;
          submenu.querySelectorAll('button').forEach(b => b.disabled = true);
          try { await api('/api/interviews/move', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}); await Promise.all([loadProjects(),loadResearchProjects()]); toast('已移动到“' + target.name + '”'); }
          catch(error) {toast(error.message); submenu.querySelectorAll('button').forEach(b => b.disabled = false);}
        };
        submenu.append(button);
      }
      trigger.onclick = event => {event.stopPropagation(); submenu.hidden = false; trigger.setAttribute('aria-expanded', 'true');};
      trigger.onmouseenter = () => {submenu.hidden = false; trigger.setAttribute('aria-expanded', 'true');};
      menu.prepend(trigger, submenu);
    });
  }
  const style = document.createElement('style'); style.textContent = '.library-menu .library-move-trigger{color:#233e46}.library-move-submenu{position:absolute;right:calc(100% + 6px);top:0;width:240px;max-width:60vw;max-height:280px;overflow:auto;background:white;border:1px solid #d5e2e7;border-radius:12px;box-shadow:0 8px 24px #102b3518;padding:6px}.library-move-submenu button{width:100%;text-align:left!important;color:#233e46!important;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.library-move-submenu button:hover,.library-move-trigger:hover{background:#edf8f6}@media(max-width:700px){.library-move-submenu{position:static;width:100%;max-width:none;box-shadow:none;margin-top:4px}}'; document.head.append(style);
  new MutationObserver(install).observe(document.querySelector('#projectList'), {childList:true,subtree:true}); install();
})();
