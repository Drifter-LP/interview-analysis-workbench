/* Soft Cubic Bezier Step-by-Step Coach-Mark Tour for Empty States */
(() => {
  const $ = s => document.querySelector(s);
  const svgNs = 'http://www.w3.org/2000/svg';

  document.body.classList.add('cm-guide-enabled');

  const root = document.createElement('div');
  root.className = 'cm-tour-root';
  root.id = 'cmTourRoot';
  root.hidden = true;

  const svg = document.createElementNS(svgNs, 'svg');
  svg.setAttribute('class', 'cm-tour-svg');
  svg.setAttribute('aria-hidden', 'true');
  const glowPath = document.createElementNS(svgNs, 'path');
  glowPath.setAttribute('class', 'cm-arrow-glow');
  const linePath = document.createElementNS(svgNs, 'path');
  linePath.setAttribute('class', 'cm-arrow-line');
  const headPath = document.createElementNS(svgNs, 'path');
  headPath.setAttribute('class', 'cm-arrow-head');
  const startDot = document.createElementNS(svgNs, 'circle');
  startDot.setAttribute('class', 'cm-arrow-dot');
  startDot.setAttribute('r', '4.5');
  svg.append(glowPath, linePath, headPath, startDot);

  const card = document.createElement('aside');
  card.className = 'cm-tour-card';
  card.setAttribute('role', 'region');
  card.setAttribute('aria-live', 'polite');
  card.setAttribute('aria-label', '分步操作指引');
  card.innerHTML = `
    <div class="cm-tour-head">
      <div class="cm-tour-progress">
        <span class="cm-step-pill" id="cmStepPill">1 / 3</span>
        <div class="cm-step-dots" id="cmStepDots" role="tablist" aria-label="引导步骤"></div>
      </div>
      <button type="button" class="cm-tour-close" id="cmCloseBtn" title="暂不显示指引" aria-label="关闭操作指引">×</button>
    </div>
    <h3 class="cm-tour-title" id="cmStepTitle"></h3>
    <p class="cm-tour-desc" id="cmStepDesc"></p>
    <div class="cm-tour-foot">
      <button type="button" class="cm-tour-secondary" id="cmSecondaryBtn">跳过指引</button>
      <button type="button" class="cm-tour-primary" id="cmPrimaryBtn">下一步 →</button>
    </div>
  `;

  const reopenPill = document.createElement('button');
  reopenPill.type = 'button';
  reopenPill.className = 'cm-reopen-pill';
  reopenPill.id = 'cmReopenPill';
  reopenPill.hidden = true;
  reopenPill.innerHTML = '<span aria-hidden="true">💡</span><span>操作指引</span>';

  root.append(svg, card);
  document.body.append(root, reopenPill);

  const pillEl = card.querySelector('#cmStepPill');
  const dotsEl = card.querySelector('#cmStepDots');
  const titleEl = card.querySelector('#cmStepTitle');
  const descEl = card.querySelector('#cmStepDesc');
  const closeBtn = card.querySelector('#cmCloseBtn');
  const secondaryBtn = card.querySelector('#cmSecondaryBtn');
  const primaryBtn = card.querySelector('#cmPrimaryBtn');

  let activeScene = null;
  let stepIndex = 0;
  let highlightedTarget = null;
  const dismissedScenes = new Set();

  function isVisible(el) {
    if (!el || !el.isConnected || el.hidden) return false;
    const style = getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity) === 0) return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 4 && rect.height > 4;
  }

  function firstVisible(selectors) {
    for (const sel of selectors) {
      const nodes = typeof sel === 'string' ? document.querySelectorAll(sel) : [sel];
      for (const node of nodes) {
        if (isVisible(node)) return node;
      }
    }
    return null;
  }

  function hasOpenModal() {
    return !!document.querySelector('dialog[open]');
  }

  function hasAnyCompletedInterview() {
    return typeof projects !== 'undefined' && Array.isArray(projects) && projects.some(p => p.status === 'completed' && !p.hidden_in_library);
  }

  function getScenes() {
    return {
      'focused-theme': {
        isActive() {
          const analysisView = $('#analysis');
          const focusedPanel = $('#focused');
          if (!analysisView?.classList.contains('active') || !focusedPanel?.classList.contains('active')) return false;
          if (focusedPanel.classList.contains('network-active') || window.wordCooccurrence?.active) return false;
          const navTask = window.researchNavigation?.task || 'theme';
          if (navTask !== 'theme') return false;
          if (typeof currentThemeAnalysis !== 'undefined' && currentThemeAnalysis) return false;
          if ($('#themePanel .theme-integration-warning')) return false;
          return true;
        },
        steps: [
          {
            target: () => firstVisible(['.research-project-picker', '#themeProjectSelect', '#themeHistorySelect']),
            title: '先选定当前要分析的研究项目',
            desc: '在这里切换你的研究项目（如「硕士毕业论文」）；如果有保存过的历史结果，也可在右侧「分析记录」直接打开。'
          },
          {
            target: () => firstVisible(['#themeQuickInput', '.research-view-segments button:first-child', '.research-source-search']),
            title: '输入你想探究的核心研究问题',
            desc: '在输入框写下跨访谈研究问题或主题，输入后也可直接点击下一步继续。'
          },
          {
            target: () => {
              const quickBtn = $('#themeQuickStart');
              if (isVisible(quickBtn)) return quickBtn;
              const buttons = [...document.querySelectorAll('.research-source-search')];
              return buttons.find(b => b.textContent.includes('新建分析') && isVisible(b)) || firstVisible(['.research-source-search']);
            },
            title: '勾选 2 篇以上访谈稿开始分析',
            desc: '点击「选择访谈稿」勾选项目内的访谈，AI 会自动跨文本提取并归纳发现。'
          }
        ]
      },
      'focused-codes': {
        isActive() {
          const analysisView = $('#analysis');
          const focusedPanel = $('#focused');
          if (!analysisView?.classList.contains('active') || !focusedPanel?.classList.contains('active')) return false;
          if (window.researchNavigation?.task !== 'codes') return false;
          const table = $('#matrixTable');
          return !table || !table.querySelector('thead');
        },
        steps: [
          {
            target: () => firstVisible(['.research-project-picker']),
            title: '先确认要统计编码的研究项目',
            desc: '在顶栏切换研究项目，系统会自动汇总该项目下各篇访谈已确认的编码分布。'
          },
          {
            target: () => firstVisible(['.nav-item[data-tab="familiarity"]']),
            title: '前往单篇访谈确认编码',
            desc: '当前项目尚无已确认的编码片段；可先进入「单篇访谈分析 → 访谈编码」生成并审核编码。'
          }
        ]
      },
      'editor-empty': {
        isActive() {
          const editorView = $('#editor');
          if (!editorView?.classList.contains('active')) return false;
          return typeof selected === 'undefined' || !selected;
        },
        steps: [
          {
            target: () => firstVisible(['.editor-cascade-control button', '#editorInterviewSelect']),
            get title() { return hasAnyCompletedInterview() ? '先在顶栏选择一篇要校订的访谈稿' : '先导入访谈稿或载入示例访谈'; },
            get desc() { return hasAnyCompletedInterview() ? '点击顶栏下拉菜单选择已有访谈稿，或从左侧「最近访谈」一键切换进入。' : '当前工作台暂无访谈稿，可先在下方空状态卡片或左侧「访谈资料」导入文本/载入示例，再由顶栏切换。'; }
          },
          {
            target: () => firstVisible(['#optimizeBtn', '#saveBtn']),
            title: '使用 AI 修订错漏与标点',
            desc: '打开访谈稿后，可点击「AI修订」自动润色口语错漏，逐处确认后保存。'
          }
        ]
      },
      'familiarity-empty': {
        isActive() {
          const analysisView = $('#analysis');
          const famPanel = $('#familiarity');
          if (!analysisView?.classList.contains('active') || !famPanel?.classList.contains('active')) return false;
          return typeof selected === 'undefined' || !selected;
        },
        steps: [
          {
            target: () => firstVisible(['.memo-selector-control button', '#memoInterviewSelect']),
            get title() { return hasAnyCompletedInterview() ? '先选择一篇要分析的访谈稿' : '先导入访谈稿或载入示例访谈'; },
            get desc() { return hasAnyCompletedInterview() ? '在顶栏下拉菜单选择访谈稿，左侧将载入完整访谈原文。' : '当前工作台暂无访谈稿，可先点击左侧「访谈资料」导入文本或载入示例访谈，再回到此处切换。'; }
          },
          {
            target: () => firstVisible(['#generateMemoBtn']),
            title: '一键生成结构化访谈纪要',
            desc: '选定访谈后点击「生成纪要」，AI 会自动提取核心观点并标注原文段落索引。'
          }
        ]
      },
      'coding-empty': {
        isActive() {
          const analysisView = $('#analysis');
          const codingPanel = $('#coding');
          if (!analysisView?.classList.contains('active') || !codingPanel?.classList.contains('active')) return false;
          return typeof selected === 'undefined' || !selected;
        },
        steps: [
          {
            target: () => firstVisible(['.memo-selector-control button', '.workspace-selector-slot select', '#memoInterviewSelect', '.ai-coding-bar select']),
            get title() { return hasAnyCompletedInterview() ? '先选择要编码的访谈稿' : '先导入访谈稿或载入示例访谈'; },
            get desc() { return hasAnyCompletedInterview() ? '在顶栏切换目标访谈稿与所属研究项目，载入原文与编码工作区。' : '当前工作台暂无访谈稿，可先前往「访谈资料」导入文本或载入示例，再在此处选择访谈。'; }
          },
          {
            target: () => firstVisible(['.workspace-action-slot .ac-primary', '.workspace-action-slot button', '#aiCodeBtn', '.ai-coding-bar button']),
            title: '生成 AI 编码建议或划词手动编码',
            desc: '点击右上角运行 AI 编码（支持探索编码与问题聚焦两种模式），或直接在原文中选中文本新建编码。'
          }
        ]
      }
    };
  }

  function clearHighlight() {
    if (highlightedTarget) {
      highlightedTarget.classList.remove('cm-target-highlight');
      highlightedTarget = null;
    }
  }

  function bezierPoint(p0, c1, c2, p3, t) {
    const mt = 1 - t;
    return {
      x: mt * mt * mt * p0.x + 3 * mt * mt * t * c1.x + 3 * mt * t * t * c2.x + t * t * t * p3.x,
      y: mt * mt * mt * p0.y + 3 * mt * mt * t * c1.y + 3 * mt * t * t * c2.y + t * t * t * p3.y
    };
  }

  function drawSoftBezierArrow(p0, c1, c2, p3) {
    const d = `M ${p0.x.toFixed(1)} ${p0.y.toFixed(1)} C ${c1.x.toFixed(1)} ${c1.y.toFixed(1)}, ${c2.x.toFixed(1)} ${c2.y.toFixed(1)}, ${p3.x.toFixed(1)} ${p3.y.toFixed(1)}`;
    glowPath.setAttribute('d', d);
    linePath.setAttribute('d', d);
    startDot.setAttribute('cx', p0.x.toFixed(1));
    startDot.setAttribute('cy', p0.y.toFixed(1));

    const nearTip = bezierPoint(p0, c1, c2, p3, 0.92);
    const angle = Math.atan2(p3.y - nearTip.y, p3.x - nearTip.x);
    const armLen = 12.5;
    const spread = 0.52;
    const lx = p3.x - armLen * Math.cos(angle - spread);
    const ly = p3.y - armLen * Math.sin(angle - spread);
    const rx = p3.x - armLen * Math.cos(angle + spread);
    const ry = p3.y - armLen * Math.sin(angle + spread);
    headPath.setAttribute('d', `M ${lx.toFixed(1)} ${ly.toFixed(1)} L ${p3.x.toFixed(1)} ${p3.y.toFixed(1)} L ${rx.toFixed(1)} ${ry.toFixed(1)}`);
  }

  function positionCardAndArrow(target) {
    const tr = target.getBoundingClientRect();
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const mainEl = document.querySelector('main.workspace-main') || document.body;
    const mr = mainEl.getBoundingClientRect();
    const headerEl = document.querySelector('.workspace-header');
    const hr = headerEl ? headerEl.getBoundingClientRect() : { bottom: 96 };

    const cardW = Math.min(356, vw - 32);
    const cardH = card.offsetHeight || 176;

    const isSidebarTarget = tr.right <= mr.left + 24;
    let cardLeft;
    let cardTop;
    let p0, c1, c2, p3;

    if (isSidebarTarget) {
      cardLeft = Math.max(mr.left + 44, tr.right + 76);
      cardTop = Math.max(hr.bottom + 24, Math.min(vh - cardH - 36, tr.top - 12));
      card.style.left = `${Math.round(cardLeft)}px`;
      card.style.top = `${Math.round(cardTop)}px`;

      p0 = { x: cardLeft - 3, y: cardTop + 44 };
      p3 = { x: tr.right + 9, y: tr.top + tr.height / 2 };
      const dx = Math.max(42, Math.abs(p0.x - p3.x) * 0.52);
      c1 = { x: p0.x - dx, y: p0.y };
      c2 = { x: p3.x + dx, y: p3.y };
    } else {
      const targetCenterX = tr.left + tr.width / 2;
      const tabAction = document.querySelector('.workspace-tab-slot .workspace-tab-action:not([hidden])');
      const obsRect = tabAction && isVisible(tabAction) ? tabAction.getBoundingClientRect() : null;
      const hasBelowObstacle = obsRect && obsRect.top >= tr.bottom - 6 && obsRect.left < tr.right + 16 && obsRect.right > tr.left - 16;

      const minLeft = Math.max(16, mr.left + 24);
      const maxLeft = Math.max(minLeft, vw - cardW - 24);
      if (hasBelowObstacle) {
        // Place card to the left of the second-row button so the Bezier curve routes cleanly around its left side
        cardLeft = Math.max(minLeft, Math.min(maxLeft, obsRect.left - cardW + 12));
        cardTop = Math.max(hr.bottom + 24, tr.bottom + 64);
        card.style.left = `${Math.round(cardLeft)}px`;
        card.style.top = `${Math.round(cardTop)}px`;
        const anchorX = Math.min(cardLeft + cardW - 28, obsRect.left - 18);
        p0 = { x: Math.max(cardLeft + 32, anchorX), y: cardTop - 3 };
        p3 = { x: Math.max(tr.left + 6, Math.min(tr.left + 14, obsRect.left - 6)), y: tr.bottom + 4 };
        c1 = { x: p0.x, y: tr.bottom + 22 };
        c2 = { x: Math.min(p0.x + 14, obsRect.left - 14), y: p3.y + 8 };
      } else {
        const desiredLeft = targetCenterX - cardW * 0.42;
        cardLeft = Math.max(minLeft, Math.min(maxLeft, desiredLeft));
        cardTop = Math.max(hr.bottom + 36, tr.bottom + 68);
        if (cardTop + cardH > vh - 24) {
          cardTop = Math.max(hr.bottom + 18, vh - cardH - 24);
        }
        card.style.left = `${Math.round(cardLeft)}px`;
        card.style.top = `${Math.round(cardTop)}px`;

        const anchorX = Math.max(cardLeft + 36, Math.min(cardLeft + cardW - 36, targetCenterX + (cardLeft + cardW / 2 - targetCenterX) * 0.35));
        p0 = { x: anchorX, y: cardTop - 3 };
        p3 = { x: targetCenterX, y: tr.bottom + 8 };
        const dy = Math.max(40, Math.abs(p0.y - p3.y) * 0.54);
        c1 = { x: p0.x, y: p0.y - dy };
        c2 = { x: p3.x, y: p3.y + dy };
      }
    }

    drawSoftBezierArrow(p0, c1, c2, p3);
  }

  function renderStep(sceneKey, scene) {
    const steps = scene.steps;
    if (stepIndex >= steps.length) stepIndex = steps.length - 1;
    if (stepIndex < 0) stepIndex = 0;

    const currentStep = steps[stepIndex];
    const target = currentStep.target();
    if (!target) {
      root.hidden = true;
      reopenPill.hidden = false;
      clearHighlight();
      return;
    }

    root.hidden = false;
    reopenPill.hidden = true;

    if (highlightedTarget !== target) {
      clearHighlight();
      highlightedTarget = target;
      highlightedTarget.classList.add('cm-target-highlight');
    }

    pillEl.textContent = `${stepIndex + 1} / ${steps.length}`;
    titleEl.textContent = currentStep.title;
    descEl.textContent = currentStep.desc;

    dotsEl.replaceChildren(
      ...steps.map((_, idx) => {
        const dot = document.createElement('button');
        dot.type = 'button';
        dot.className = 'cm-step-dot' + (idx === stepIndex ? ' is-active' : '');
        dot.setAttribute('aria-label', `第 ${idx + 1} 步`);
        dot.setAttribute('aria-selected', String(idx === stepIndex));
        dot.onclick = e => {
          e.stopPropagation();
          stepIndex = idx;
          syncGuide();
        };
        return dot;
      })
    );

    if (stepIndex === 0) {
      secondaryBtn.textContent = '跳过指引';
    } else {
      secondaryBtn.textContent = '← 上一步';
    }

    if (stepIndex < steps.length - 1) {
      primaryBtn.textContent = '下一步 →';
    } else {
      primaryBtn.textContent = '完成指引 ✓';
    }

    positionCardAndArrow(target);
  }

  function syncGuide() {
    if (hasOpenModal()) {
      root.hidden = true;
      reopenPill.hidden = true;
      clearHighlight();
      return;
    }

    const scenes = getScenes();
    let matchedKey = null;
    let matchedScene = null;

    for (const [key, scene] of Object.entries(scenes)) {
      if (scene.isActive()) {
        matchedKey = key;
        matchedScene = scene;
        break;
      }
    }

    if (!matchedKey || !matchedScene) {
      activeScene = null;
      root.hidden = true;
      reopenPill.hidden = true;
      clearHighlight();
      return;
    }

    if (activeScene !== matchedKey) {
      activeScene = matchedKey;
      stepIndex = 0;
    }

    if (dismissedScenes.has(matchedKey)) {
      root.hidden = true;
      reopenPill.hidden = false;
      clearHighlight();
      return;
    }

    renderStep(matchedKey, matchedScene);
  }

  closeBtn.onclick = e => {
    e.stopPropagation();
    if (activeScene) dismissedScenes.add(activeScene);
    syncGuide();
  };

  secondaryBtn.onclick = e => {
    e.stopPropagation();
    if (stepIndex === 0) {
      if (activeScene) dismissedScenes.add(activeScene);
    } else {
      stepIndex = Math.max(0, stepIndex - 1);
    }
    syncGuide();
  };

  primaryBtn.onclick = e => {
    e.stopPropagation();
    const scenes = getScenes();
    const scene = activeScene ? scenes[activeScene] : null;
    if (!scene) return;
    if (stepIndex < scene.steps.length - 1) {
      stepIndex += 1;
    } else {
      dismissedScenes.add(activeScene);
    }
    syncGuide();
  };

  reopenPill.onclick = e => {
    e.stopPropagation();
    if (activeScene) dismissedScenes.delete(activeScene);
    stepIndex = 0;
    syncGuide();
  };

  document.addEventListener('change', e => {
    if (!activeScene || root.hidden) return;
    if (activeScene === 'focused-theme' && stepIndex === 0 && e.target.matches('.research-project-picker, #themeProjectSelect')) {
      stepIndex = 1;
      scheduleSync();
    }
  });

  let rafId = 0;
  function scheduleSync() {
    if (rafId) return;
    rafId = requestAnimationFrame(() => {
      rafId = 0;
      syncGuide();
    });
  }

  window.addEventListener('resize', scheduleSync);
  window.addEventListener('scroll', scheduleSync, true);
  window.addEventListener('hashchange', scheduleSync);
  window.addEventListener('popstate', scheduleSync);
  document.addEventListener('toggle', scheduleSync, true);
  document.addEventListener('click', () => setTimeout(scheduleSync, 40));

  const mainEl = document.querySelector('main');
  if (mainEl) {
    const obs = new MutationObserver(scheduleSync);
    obs.observe(mainEl, {
      subtree: true,
      childList: true,
      attributes: true,
      attributeFilter: ['class', 'hidden', 'open']
    });
  }
  // Dialogs live outside main; opening one must suppress the coachmark too.
  const modalObserver = new MutationObserver(scheduleSync);
  for (const dialog of document.querySelectorAll('dialog')) {
    modalObserver.observe(dialog, { attributes: true, attributeFilter: ['open'] });
  }

  const headerEl = document.querySelector('.workspace-header');
  if (headerEl && typeof ResizeObserver !== 'undefined') {
    const ro = new ResizeObserver(scheduleSync);
    ro.observe(headerEl);
  }

  for (const delay of [80, 260, 600, 1200]) {
    setTimeout(scheduleSync, delay);
  }

  window.emptyCoachmarkGuide = {
    refresh: scheduleSync,
    setStep(idx) {
      stepIndex = Number(idx) || 0;
      if (activeScene) dismissedScenes.delete(activeScene);
      syncGuide();
    },
    open() {
      if (activeScene) dismissedScenes.delete(activeScene);
      stepIndex = 0;
      syncGuide();
    },
    dismiss() {
      if (activeScene) dismissedScenes.add(activeScene);
      syncGuide();
    },
    get state() {
      return { activeScene, stepIndex, visible: !root.hidden };
    }
  };
})();
