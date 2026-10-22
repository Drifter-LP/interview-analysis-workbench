(() => {
  const workspace = document.createElement('div');
  workspace.id = 'sourceSearch'; workspace.className = 'tab-panel';
  workspace.innerHTML = '<div class="source-search-controls"><select id="sourceSearchInterview" aria-label="选择检索访谈稿"></select></div><div class="source-search-grid"><article id="sourceSearchSource" class="memo-source">请选择访谈稿并输入主题。</article><aside id="sourceSearchPanel"></aside></div>';
  document.querySelector('#analysis').append(workspace);
  labels.sourceSearch = '查找主题原文';
  const nav = document.createElement('button'); nav.className = 'nav-item'; nav.dataset.view = 'analysis'; nav.dataset.tab = 'sourceSearch'; nav.textContent = '查找主题原文';
  // This is a single-interview view, not a separate sidebar destination.
  const picker = workspace.querySelector('select');
  function refreshPicker() {
    const rows = projects.filter(p => p.status === 'completed');
    picker.replaceChildren(new Option('请选择访谈稿', ''), ...rows.map(p => new Option(p.name, String(p.id))));
    picker.value = selected ? String(selected) : '';
  }
  window.openSourceSearch = () => {refreshPicker(); switchView('analysis', 'sourceSearch');};
  picker.onchange = async () => {
    if (!picker.value) return;
    try { await openProject(picker.value); refreshPicker(); switchView('analysis', 'sourceSearch'); }
    catch(error) { toast(error.message); }
  };
  const bar = document.createElement('section');
  bar.className = 'source-search-bar';
  bar.innerHTML = '<form><input aria-label="查找主题原文" placeholder="想找什么主题的原文？"><button class="soft" type="submit">查找主题原文</button></form><small>检索当前已保存的访谈稿，返回逐字原文；未保存的修改不参与检索。</small><div class="source-search-results" aria-live="polite"></div>';
  workspace.querySelector('#sourceSearchPanel').append(bar);
  const form = bar.querySelector('form'), input = bar.querySelector('input'), button = bar.querySelector('button'), results = bar.querySelector('.source-search-results');
  let generation = 0, controller;
  const oldOpen = openProject;
  document.addEventListener('interview-library-updated', event => {
    refreshPicker();
    if (!selected || event.detail.deletedId === selected) {
      generation++; controller?.abort(); results.replaceChildren(); button.disabled = false;
      document.querySelector('#sourceSearchSource').textContent = '请选择访谈稿并输入主题。';
    }
  });
  openProject = async function(...args) {
    generation++; controller?.abort(); results.replaceChildren(); button.disabled = false;
    document.querySelector('#sourceSearchSource').textContent = '输入主题后查找相关原文。';
    return oldOpen.apply(this, args);
  };
  form.onsubmit = async event => {
    event.preventDefault();
    if (!selected) return toast('请先打开一份访谈稿');
    const query = input.value.trim(); if (!query) return input.focus();
    controller?.abort(); controller = new AbortController();
    const token = ++generation, project = selected;
    button.disabled = true; results.textContent = '正在查找相关原文…';
    try {
      const response = await fetch(`/api/projects/${encodeURIComponent(project)}/source-search`, {
        method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({query}), signal:controller.signal
      });
      const data = await response.json(); if (!response.ok) throw new Error(data.detail || '查找失败');
      if (token !== generation || selected !== project) return;
      document.querySelector('#sourceSearchSource').textContent = data.source_text;
      results.replaceChildren();
      const status = document.createElement('p'); status.textContent = `找到 ${data.results.length} 段相关原文（语义检索结果，请结合上下文核对）`; results.append(status);
      for (const item of data.results) {
        const card = document.createElement('article'), quote = document.createElement('blockquote'), jump = document.createElement('button');
        quote.textContent = item.text; jump.type = 'button'; jump.className = 'ghost'; jump.textContent = `定位原文 · 片段 ${item.id}`;
        jump.onclick = () => {
          const box = document.querySelector('#sourceSearchSource');
          box.dataset.text = data.source_text;
          box.innerHTML = escapeHtml(data.source_text.slice(0,item.start)) + '<mark id="sourceSearchHit" class="memo-source-hit">' + escapeHtml(data.source_text.slice(item.start,item.end)) + '</mark>' + escapeHtml(data.source_text.slice(item.end));
          document.querySelector('#sourceSearchHit').scrollIntoView({behavior:'smooth',block:'center'});
        };
        card.append(quote,jump); results.append(card);
      }
    } catch (error) { if (token === generation && error.name !== 'AbortError') results.textContent = error.message; }
    finally { if (token === generation) button.disabled = false; }
  };
  const style = document.createElement('style');
  style.textContent = '.source-search-bar{padding:12px 24px;border-bottom:1px solid #e2e9ec;background:white}.source-search-bar form{display:flex;gap:8px;flex-wrap:wrap}.source-search-bar input{flex:1;min-width:180px;height:36px;border:1px solid #d5e2e7;border-radius:8px;padding:0 12px}.source-search-bar small{display:block;color:#70858b;margin-top:6px}.source-search-results:not(:empty){max-height:280px;overflow:auto;margin-top:8px}.source-search-results article{border-top:1px solid #e6eeee;padding:8px 0}.source-search-results blockquote{margin:0 0 6px;white-space:pre-wrap;font-size:14px;line-height:1.7}';
  document.head.append(style);
  const layout = document.createElement('style');
  layout.textContent = '#sourceSearch.active{display:flex;flex-direction:column;min-height:0} .source-search-controls{padding:12px 24px}.source-search-grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);flex:1;min-height:0;padding:16px 24px;gap:20px}#sourceSearchSource{white-space:pre-wrap;overflow:auto;max-height:calc(100vh - 190px)}#sourceSearchPanel{min-width:0;overflow:auto;max-height:calc(100vh - 190px)}#sourceSearchPanel .source-search-bar{padding:0;border:0}#sourceSearchPanel .source-search-results{max-height:none;overflow:visible}@media(max-width:900px){.source-search-grid{grid-template-columns:1fr}#sourceSearchSource,#sourceSearchPanel{max-height:45vh}}';
  document.head.append(layout);
})();
