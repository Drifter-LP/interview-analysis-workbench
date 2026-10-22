// Shared inline display-name editing. IDs and manuscript text remain unchanged.
(() => {
  let active = null, clickTimer = null, replay = false;
  const attr = (node, kind, id, owner = '') => {
    if (!node || node.querySelector('input') || node === active?.node) return;
    node.dataset.renameKind = kind;
    node.dataset.renameId = id;
    node.dataset.renameOwner = owner;
    node.title = '双击重命名';
  };
  function mark() {
    projects.forEach(project => [researchProjects, selectedResearchProject, currentComparison, currentThemeAnalysis].forEach(value => refreshReferences(value, project.id, project.name)));
    document.querySelectorAll('#projectList .project').forEach(card => attr(card.querySelector('strong'), 'interview', card.dataset.id));
    document.querySelectorAll('#researchProjectList .research-card').forEach(card => attr(card.querySelector('h3'), 'research', card.dataset.researchId));
    if (selectedResearchProject && !$('#researchBackBtn').hidden) attr($('#researchHeading'), 'research', selectedResearchProject.id);
    else delete $('#researchHeading').dataset.renameKind;
    document.querySelectorAll('.material-card').forEach(card => {
      const kind = card.dataset.materialType === 'uploaded' ? 'uploaded' : 'interview';
      attr(card.querySelector('.material-main > span'), kind, card.dataset.materialKey, selectedResearchProject?.id || '');
    });
    document.querySelectorAll('#researchInterviewList label, #themeMaterialList label, #comparisonMaterialList label').forEach(label => {
      const input = label.querySelector('input');
      if (!input || input.id === 'themeSelectAll') return;
      attr(label.querySelector('span'), input.dataset.type === 'uploaded' ? 'uploaded' : 'interview', input.dataset.type ? input.dataset.key : input.value, selectedResearchProject?.id || '');
    });
    if (selectedProject) {
      attr($('#editorTitle'), 'interview', selectedProject.id);
      const title = $('#memoTitle');
      if (!title.querySelector('[data-rename-kind]')) {
        title.textContent = '';
        const name = document.createElement('span');
        name.textContent = selectedProject.name;
        attr(name, 'interview', selectedProject.id);
        title.append(name, ' · 访谈纪要');
      }
    }
    document.querySelectorAll('.comparison-perspective').forEach(row => {
      const id = row.querySelector('[data-project-id]')?.dataset.projectId;
      if (id) attr(row.querySelector('b'), 'interview', id);
    });
    document.querySelectorAll('.theme-relevance').forEach(row => {
      const item = currentThemeAnalysis?.relevance?.find(item => item.name === row.querySelector('b')?.textContent);
      if (item) attr(row.querySelector('b'), 'interview', item.project_id);
    });
    document.querySelectorAll('#matrixTable tbody tr').forEach(row => {
      const node = row.querySelector('td');
      const matches = projects.filter(item => item.name === node?.textContent);
      if (matches.length === 1) attr(node, 'interview', matches[0].id);
    });
    document.querySelectorAll('[data-rename-kind]').forEach(node => {
      if (node === active?.node) return;
      const value = nameFor(node.dataset);
      if (value && node.textContent !== value) node.textContent = value;
    });
    document.querySelectorAll('#memoInterviewSelect option').forEach(option => {
      if (!option.dataset.type) return;
      const value = nameFor({renameKind: option.dataset.type === 'uploaded' ? 'uploaded' : 'interview', renameId: option.dataset.key, renameOwner: selectedResearchProject?.id || ''});
      if (value && option.textContent !== value) option.textContent = value;
    });
    document.querySelectorAll('#memoProjectList button[data-project-id], #addEditorProjectList button[data-project-id]').forEach(button => {
      const name = researchProjects.find(project => project.id === button.dataset.projectId)?.name;
      if (name && button.textContent !== name) button.textContent = name;
    });
  }
  function nameFor(data) {
    if (data.renameKind === 'research') return researchProjects.find(p => p.id === data.renameId)?.name;
    if (data.renameKind === 'uploaded') return researchProjects.find(p => p.id === data.renameOwner)?.uploaded_transcripts?.[Number(data.renameId)]?.name;
    return projects.find(p => p.id === data.renameId)?.name || (selectedProject?.id === data.renameId ? selectedProject.name : '');
  }
  function refreshReferences(value, id, name) {
    if (!value || typeof value !== 'object') return;
    if (!Array.isArray(value) && (value.project_id === id || value.workspace_project_id === id || value.id === id)) {
      if ('name' in value) value.name = name;
      if ('material_name' in value) value.material_name = name;
    }
    Object.values(value).forEach(child => { if (child && typeof child === 'object') refreshReferences(child, id, name); });
  }
  function edit(node) {
    if (active) return;
    const data = {...node.dataset}, old = nameFor(data) || node.textContent;
    const input = document.createElement('input');
    input.type = 'text'; input.maxLength = 160; input.value = old;
    input.className = 'comparison-history-input'; input.setAttribute('aria-label', '名称');
    node.textContent = ''; node.append(input);
    active = {node}; input.focus(); input.select();
    let done = false;
    const finish = async cancel => {
      if (done) return;
      done = true;
      const name = input.value.trim();
      if (cancel || !name || name === old) { active = null; node.textContent = old; return; }
      input.disabled = true;
      try {
        const url = data.renameKind === 'research' ? `/api/research-projects/${encodeURIComponent(data.renameId)}/name`
          : data.renameKind === 'uploaded' ? `/api/research-projects/${encodeURIComponent(data.renameOwner)}/uploaded/${data.renameId}/name`
          : `/api/projects/${encodeURIComponent(data.renameId)}/name`;
        const result = await api(url, {method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name})});
        const interviewId = data.renameKind === 'interview' ? data.renameId : data.renameKind === 'uploaded' ? result.id : null;
        if (interviewId) [projects, researchProjects, selectedProject, selectedResearchProject, currentComparison, currentThemeAnalysis].forEach(value => refreshReferences(value, interviewId, name));
        if (data.renameKind === 'research') {
          const project = researchProjects.find(p => p.id === data.renameId); if (project) project.name = name;
          if (selectedResearchProject?.id === data.renameId) selectedResearchProject.name = name;
          renderEditorProjects();
        } else if (data.renameKind === 'uploaded' && !interviewId) {
          const project = researchProjects.find(p => p.id === data.renameOwner);
          if (project) project.uploaded_transcripts[Number(data.renameId)].name = name;
          if (selectedResearchProject?.id === data.renameOwner) selectedResearchProject.uploaded_transcripts[Number(data.renameId)].name = name;
        }
        active = null; node.textContent = name;
        if (selectedProject && $('#editor').classList.contains('active')) $('#currentProject').textContent = selectedProject.name;
        if (data.renameKind === 'research' && selectedResearchProject) $('#currentProject').textContent = selectedResearchProject.name;
        document.querySelectorAll('#themeProjectSelect option').forEach(option => {
          const project = researchProjects.find(p => p.id === option.value); if (project) option.textContent = project.name;
        });
        mark(); toast('名称已更新');
      } catch (error) { active = null; node.textContent = old; toast(error.message); }
    };
    input.onkeydown = event => {
      if (event.key === 'Enter' && !event.isComposing) { event.preventDefault(); finish(false); }
      if (event.key === 'Escape') { event.preventDefault(); finish(true); }
    };
    input.onblur = () => finish(false);
  }
  document.addEventListener('click', event => {
    const node = event.target.closest('[data-rename-kind]');
    if (!node || replay) return;
    event.stopImmediatePropagation();
    if (event.target.tagName === 'INPUT') return;
    event.preventDefault();
    clearTimeout(clickTimer);
    if (event.detail > 1) return;
    clickTimer = setTimeout(() => { replay = true; node.click(); replay = false; }, 500);
  }, true);
  document.addEventListener('dblclick', event => {
    const node = event.target.closest('[data-rename-kind]');
    if (!node || event.target.tagName === 'INPUT') return;
    clearTimeout(clickTimer); event.preventDefault(); event.stopImmediatePropagation(); edit(node);
  }, true);
  // Native option menus cannot contain editable fields. Mirror this interview picker
  // with a small dropdown; the original select still owns switching logic.
  const picker = $('#memoInterviewSelect');
  const toggle = document.createElement('button'), menu = document.createElement('div');
  toggle.type = 'button'; toggle.className = 'soft'; toggle.setAttribute('aria-haspopup', 'true');
  menu.className = 'comparison-history-list'; menu.hidden = true;
  const holder = document.createElement('div'); holder.style.position = 'relative';
  picker.after(holder); holder.append(toggle, menu); picker.hidden = true;
  function syncPicker() {
    const text = (picker.selectedOptions[0]?.textContent || '切换访谈稿') + ' ▾';
    if (toggle.textContent !== text) toggle.textContent = text;
  }
  menu.classList.add('memo-cascade-menu');
  toggle.setAttribute('aria-expanded','false');
  function openGroups(candidates=researchProjects){
    menu.replaceChildren();menu.hidden=false;toggle.setAttribute('aria-expanded','true');
    const assigned=new Set(researchProjects.flatMap(p=>[...(p.interviews||[]).map(x=>String(x.id)),...(p.uploaded_transcripts||[]).filter(x=>x.workspace_project_id).map(x=>String(x.workspace_project_id))]));
    const groups=candidates.map(project=>({project,name:project.name,rows:[...(project.interviews||[]).map(x=>({name:x.name,type:'workspace',key:String(x.id)})),...(project.uploaded_transcripts||[]).map((x,i)=>({name:x.name,type:'uploaded',key:String(i)}))]}));
    if(candidates===researchProjects){const rows=projects.filter(p=>p.status==='completed'&&!assigned.has(String(p.id))).map(p=>({name:p.name,type:'workspace',key:String(p.id)}));if(rows.length)groups.push({project:null,name:'未归入项目的访谈',rows});}
    if(!groups.length){menu.textContent='暂无访谈稿';return;}
    for(const group of groups){
      const row=document.createElement('div');row.className='memo-cascade-group';
      const parent=document.createElement('button');parent.type='button';parent.className='memo-cascade-parent';parent.setAttribute('aria-expanded','false');parent.setAttribute('aria-haspopup','true');
      const name=document.createElement('span');name.textContent=group.name;const count=document.createElement('small');count.textContent=group.rows.length+' 份';const arrow=document.createElement('span');arrow.textContent='›';parent.append(name,count,arrow);
      const sub=document.createElement('div');sub.className='memo-cascade-sub';sub.hidden=true;
      function expand(){for(const other of menu.querySelectorAll('.memo-cascade-sub'))other.hidden=true;for(const other of menu.querySelectorAll('.memo-cascade-parent'))other.setAttribute('aria-expanded','false');sub.hidden=false;parent.setAttribute('aria-expanded','true');sub.classList.remove('open-left');const box=sub.getBoundingClientRect();sub.classList.toggle('open-left',box.right>window.innerWidth-12);}
      parent.onclick=expand;row.onmouseenter=expand;parent.onkeydown=e=>{if(e.key==='ArrowRight'){e.preventDefault();expand();sub.querySelector('button')?.focus();}};
      for(const material of group.rows){const item=document.createElement('button');item.type='button';item.className='comparison-history-record';item.textContent=material.name;item.title=material.name;item.classList.toggle('active',group.project?.id===selectedResearchProject?.id&&material.type===currentMemoMaterial?.type&&material.key===String(currentMemoMaterial?.key));
        item.onclick=async()=>{menu.hidden=true;toggle.setAttribute('aria-expanded','false');collectMemo();selectedResearchProject=group.project;await openMaterialMemo(material.type,material.key);syncPicker();};
        item.onkeydown=e=>{if(e.key==='ArrowLeft'){e.preventDefault();sub.hidden=true;parent.setAttribute('aria-expanded','false');parent.focus();}};sub.append(item);}
      if(!group.rows.length){const empty=document.createElement('p');empty.textContent='暂无访谈稿';sub.append(empty);}
      row.append(parent,sub);menu.append(row);
    }
  }
  toggle.onclick=()=>{if(!menu.hidden){menu.hidden=true;toggle.setAttribute('aria-expanded','false');}else openGroups();};
  openMemoProjectPicker=function(candidates=researchProjects){switchView('analysis','familiarity');requestAnimationFrame(()=>openGroups(candidates));};
  holder.addEventListener('keydown',e=>{if(e.key==='Escape'){menu.hidden=true;toggle.setAttribute('aria-expanded','false');toggle.focus();}});
  document.addEventListener('click', event => { if (!holder.contains(event.target)) menu.hidden = true; });
  const observer = new MutationObserver(() => { mark(); syncPicker(); });
  observer.observe(document.querySelector('main') || document.body, {childList:true, subtree:true});
  document.querySelectorAll('dialog').forEach(dialog => observer.observe(dialog, {childList:true, subtree:true}));
  mark(); syncPicker();
})();
