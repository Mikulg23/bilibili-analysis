// 预留 API 统一使用同源地址；这里不模拟任何业务结果。
window.apiRequest = async function (path, method = 'GET', data = {}) {
  const controller = new AbortController();
  // 清洗还包含存储写入，留出 60 秒；采集任务仍通过短请求查询进度。
  const timeout = setTimeout(() => controller.abort(), path === '/preprocess' ? 60000 : 20000);
  try {
    const options = {method, credentials: 'same-origin', signal: controller.signal, headers: {Accept: 'application/json'}};
    let url = `/api${path}`;
    if (method === 'GET') {
      url += `?${new URLSearchParams(data)}`;
    } else {
      options.headers['Content-Type'] = 'application/json';
      options.body = JSON.stringify(data);
    }
    const response = await fetch(url, options);
    if (response.status === 404 || response.status === 405) {
      throw new Error(path === '/login' ? '登录服务尚未接入。可使用下方入口预览管理界面。' : '接口尚未接入，暂时无法执行此操作。');
    }
    if (response.status === 401) throw new Error('登录已失效，请返回登录页。');
    if (response.status === 403) throw new Error('当前账号没有执行此操作的权限。');
    if (!response.headers.get('content-type')?.includes('application/json')) throw new Error('服务返回格式异常，请稍后重试。');
    const result = await response.json();
    if (!result || typeof result.success !== 'boolean') throw new Error('接口返回格式不符合约定。');
    if (!response.ok || !result.success) throw new Error(result.message || '操作失败，请稍后重试。');
    return result;
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('请求超时，请稍后重试。');
    if (error instanceof TypeError) throw new Error('网络连接失败，请检查本地服务是否已启动。');
    throw error;
  } finally {
    clearTimeout(timeout);
  }
};

if (document.querySelector('[data-dashboard]')) {
  const $ = id => document.getElementById(id);
  const pageInfo = {
    collect: ['数据采集', 'DATA COLLECTION', '从关键词出发，构建你的视频数据集。', '01 / COLLECT'],
    preprocess: ['数据预处理', 'DATA PREPROCESSING', '规范原始数据，为分析与挖掘准备可靠样本。', '02 / PREPARE'],
    analysis: ['数据分析', 'DATA ANALYTICS', '从多维度观察视频表现，让数据洞察更直观。', '03 / ANALYZE'],
    mining: ['数据挖掘', 'DATA MINING', '探索视频热度分布，发现互动行为之间的联系。', '04 / DISCOVER'],
    knowledge: ['AI 知识库', 'AI KNOWLEDGE BASE', '用自然语言探索数据，让洞察成为对话。', '05 / ASK']
  };
  const videoKeys = ['title', 'url', 'up', 'play', 'like', 'coin', 'favorite', 'share'];
  const charts = window.DashboardCharts;
  let contextVersion = 0;
  const filters = {date: '', keyword: ''};
  let collectionBusy = false;
  let collectionTimer = null;
  let collectionStatusPending = false;
  let collectionTaskId = null;

  function message(id, text, kind = '') {
    const element = $(id);
    element.textContent = text;
    element.className = `message ${kind}`;
    element.hidden = !text;
  }

  function metric(key, value) {
    document.querySelectorAll(`[data-value="${key}"]`).forEach(element => {
      element.textContent = typeof value === 'number' && Number.isFinite(value) ? value.toLocaleString('zh-CN') : '—';
    });
  }

  function table(id, rows, keys) {
    const body = $(id);
    body.replaceChildren();
    if (!Array.isArray(rows) || !rows.length) {
      const row = body.insertRow();
      const cell = row.insertCell();
      cell.colSpan = keys.length;
      cell.className = 'table-empty';
      cell.textContent = '暂无数据';
      const hint = document.createElement('span');
      hint.textContent = '执行操作后，在此查看当前范围的结果';
      cell.append(hint);
      return;
    }
    for (const item of rows) {
      const row = body.insertRow();
      for (const key of keys) {
        const cell = row.insertCell();
        const value = item[key];
        const text = Array.isArray(value) ? value.join('、') : value == null ? '—' : String(value);
        cell.textContent = text;
        cell.title = text;
        if (key === 'url' && typeof value === 'string') {
          try {
            const url = new URL(value);
            if (url.protocol === 'https:' || url.protocol === 'http:') {
              const link = document.createElement('a');
              link.href = url.href;
              link.target = '_blank';
              link.rel = 'noopener noreferrer';
              link.textContent = '查看视频 ↗';
              cell.replaceChildren(link);
            }
          } catch { /* 无效链接作为普通文本显示。 */ }
        }
      }
    }
  }

  function resetResults() {
    document.querySelectorAll('[data-value]').forEach(element => { element.textContent = '—'; });
    for (const id of ['chart-top10', 'chart-interaction', 'chart-title', 'chart-scatter', 'chart-elbow', 'chart-clusters']) charts.empty(id);
    table('collect-rows', [], videoKeys);
    $('collection-state').textContent = '尚未开始';
    $('collection-progress').textContent = '启动后显示页数、累计数量与失败数量，最多预览 20 条记录。';
    $('collection-file').textContent = 'CSV 保存到 data/raw/，本模块不写入 MySQL 或 HDFS。';
    table('preprocess-rows', [], videoKeys);
    $('preprocess-details').textContent = '选择实际采集日期；关键词留空可合并该日全部原始 CSV。';
    table('cluster-rows', [], ['title', 'play', 'like', 'coin', 'favorite', 'share', 'cluster', 'label']);
    table('rule-rows', [], ['antecedents', 'consequents', 'support', 'confidence', 'lift']);
    $('prediction-result').textContent = '输入五项特征后开始预测';
    $('prediction-result').className = 'result-empty';
    $('knowledge-status').textContent = '尚未连接知识库';
    $('knowledge-answer').textContent = '尚无回答，请先构建知识库并提交问题。';
    for (const id of ['analysis', 'collect', 'preprocess', 'mining', 'knowledge']) message(`${id}-message`, '');
  }

  const yesterday = new Date();
  yesterday.setDate(yesterday.getDate() - 1);
  filters.date = `${yesterday.getFullYear()}-${String(yesterday.getMonth() + 1).padStart(2, '0')}-${String(yesterday.getDate()).padStart(2, '0')}`;
  document.querySelectorAll('[data-filter]').forEach(input => {
    const key = input.dataset.filter;
    input.value = filters[key];
    input.addEventListener('input', () => {
      filters[key] = input.value;
      document.querySelectorAll(`[data-filter="${key}"]`).forEach(other => { if (other !== input) other.value = input.value; });
      contextVersion++;
      resetResults();
      message('global-message', '数据范围已变更，请在当前模块重新加载或执行操作。');
    });
  });
  resetResults();
  if (!window.echarts) $('chart-library-warning').hidden = false;

  // 切换数据范围后，忽略旧请求的返回，防止显示上一批数据。
  async function run(button, target, path, method, extra, render) {
    if (button.disabled) return;
    if (!$('filter-date').reportValidity()) return;
    const keyword = filters.keyword.trim();
    if (!keyword && path !== '/preprocess') {
      message(target, '请先填写数据关键词，以确定要操作的数据范围。', 'warning');
      $('filter-keyword').focus();
      return;
    }
    message('global-message', '');
    const version = contextVersion;
    const label = button.textContent;
    button.disabled = true;
    button.textContent = '请求中…';
    message(target, '正在请求服务，请稍候…');
    try {
      const result = await apiRequest(path, method, {date: filters.date, keyword, ...extra});
      if (version !== contextVersion) return;
      if (!result.data || typeof result.data !== 'object' || Array.isArray(result.data)) throw new Error('接口数据格式异常，请检查返回字段。');
      const hasData = render(result.data);
      message(target, hasData === false ? '当前范围暂无数据。' : (result.message || '操作完成。'), hasData === false ? '' : result.data.storage_complete === false ? 'warning' : 'success');
    } catch (error) {
      if (version === contextVersion) message(target, error.message, 'error');
    } finally {
      button.disabled = false;
      button.textContent = label;
    }
  }

  function closeMenu() {
    $('sidebar').classList.remove('open');
    $('sidebar-backdrop').hidden = true;
    $('menu-toggle').setAttribute('aria-expanded', 'false');
  }
  document.querySelectorAll('[data-page]').forEach(button => button.addEventListener('click', () => {
    const page = button.dataset.page;
    document.querySelectorAll('.page-section').forEach(section => { section.hidden = section.id !== `page-${page}`; });
    document.querySelectorAll('[data-page]').forEach(item => {
      item.classList.toggle('active', item === button);
      if (item === button) item.setAttribute('aria-current', 'page'); else item.removeAttribute('aria-current');
    });
    const [title, eyebrow, description, mark] = pageInfo[page];
    $('page-title').textContent = title;
    $('breadcrumb-title').textContent = title;
    $('page-eyebrow').textContent = eyebrow;
    $('page-description').textContent = description;
    document.querySelector('.section-mark').textContent = mark;
    document.title = `${title} · BiliScope`;
    closeMenu();
    charts.resize();
    if (page === 'collect') loadCollectionStatus(false);
  }));
  $('menu-toggle').addEventListener('click', () => {
    const open = $('sidebar').classList.toggle('open');
    $('sidebar-backdrop').hidden = !open;
    $('menu-toggle').setAttribute('aria-expanded', String(open));
    if (open) $('sidebar').querySelector('[aria-current="page"]').focus();
  });
  $('sidebar-backdrop').addEventListener('click', closeMenu);
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && $('sidebar').classList.contains('open')) { closeMenu(); $('menu-toggle').focus(); }
  });

  const tabs = [...document.querySelectorAll('[data-tab]')];
  function activateTab(tab) {
    tabs.forEach(item => {
      const active = item === tab;
      item.classList.toggle('active', active);
      item.setAttribute('aria-selected', String(active));
      item.tabIndex = active ? 0 : -1;
      $(`mining-${item.dataset.tab}`).hidden = !active;
    });
    charts.resize();
  }
  tabs.forEach((tab, index) => {
    tab.addEventListener('click', () => activateTab(tab));
    tab.addEventListener('keydown', event => {
      let next;
      if (event.key === 'ArrowRight') next = tabs[(index + 1) % tabs.length];
      if (event.key === 'ArrowLeft') next = tabs[(index + tabs.length - 1) % tabs.length];
      if (event.key === 'Home') next = tabs[0];
      if (event.key === 'End') next = tabs[tabs.length - 1];
      if (next) { event.preventDefault(); activateTab(next); next.focus(); }
    });
  });

  $('load-analysis').addEventListener('click', event => run(event.currentTarget, 'analysis-message', '/analysis', 'GET', {}, data => {
    const stats = data.summary || {};
    for (const key of ['video_count', 'total_play', 'total_interactions', 'up_count']) metric(key, stats[key]);
    charts.analysis(data);
    return (stats.video_count > 0) || (data.top10_play?.titles?.length > 0) || (data.interaction_ratio?.length > 0) || (data.title_len_play?.x?.length > 0) || (data.like_coin_scatter?.length > 0);
  }));
  function setCollectionBusy(busy) {
    collectionBusy = busy;
    const button = $('collect-form').querySelector('[type="submit"]');
    button.disabled = busy;
    button.textContent = busy ? '采集中…' : '开始采集 →';
    $('stop-collection').disabled = !busy || !collectionTaskId;
    if (!busy) $('stop-collection').textContent = '停止采集';
    $('collect-pages').disabled = busy;
    document.querySelectorAll('[data-filter]').forEach(input => { input.disabled = busy; });
  }

  function renderCollection(task, restore) {
    if (task.state === 'idle') {
      if (collectionBusy) {
        setCollectionBusy(false);
        message('collect-message', '当前没有运行中的任务，服务可能已重启。已写入的 CSV 保留。', 'warning');
      }
      return;
    }
    const matches = task.date === filters.date && task.keyword === filters.keyword.trim();
    const active = task.state === 'running' || task.state === 'stopping';
    // 正在运行的任务固定数据范围；刷新页面后也能继续查看进度。
    if (!matches && (restore || active)) {
      filters.date = task.date;
      filters.keyword = task.keyword;
      document.querySelectorAll('[data-filter]').forEach(input => { input.value = filters[input.dataset.filter]; });
      contextVersion++;
      resetResults();
    } else if (!matches) {
      return;
    }
    collectionTaskId = task.task_id;
    setCollectionBusy(active);
    $('stop-collection').disabled = !active || task.state === 'stopping';
    $('stop-collection').textContent = task.state === 'stopping' ? '正在停止…' : '停止采集';
    $('collection-state').textContent = {running: '正在采集', stopping: '正在停止', stopped: '已停止', completed: '采集完成', error: '采集失败'}[task.state] || task.state;
    $('collection-progress').textContent = `${task.date} · ${task.keyword} · 第 ${task.page}/${task.pages} 页 · 新增 ${task.new_count} 条 · 失败 ${task.failed_count} 条`;
    $('collection-file').textContent = task.filename ? `保存位置：data/raw/${task.filename}` : '正在准备 CSV 文件…';
    metric('collect_count', task.count);
    table('collect-rows', task.rows, videoKeys);
    message('collect-message', task.message, task.state === 'error' ? 'error' : task.state === 'completed' ? 'success' : '');
  }

  async function loadCollectionStatus(restore) {
    if (collectionStatusPending) return;
    collectionStatusPending = true;
    clearTimeout(collectionTimer);
    try {
      const result = await apiRequest('/collect/status');
      renderCollection(result.data, restore);
    } catch (error) {
      if (restore || collectionBusy) message('collect-message', `${error.message} 后台任务可能仍在运行，可稍后查看当前任务。`, 'error');
    } finally {
      collectionStatusPending = false;
      if (collectionBusy) collectionTimer = setTimeout(() => loadCollectionStatus(false), 2000);
    }
  }

  $('refresh-collection').addEventListener('click', () => loadCollectionStatus(true));
  $('stop-collection').addEventListener('click', async event => {
    const button = event.currentTarget;
    button.disabled = true;
    try {
      const result = await apiRequest('/collect/stop', 'POST', {task_id: collectionTaskId});
      renderCollection(result.data, true);
      await loadCollectionStatus(false);
    } catch (error) {
      message('collect-message', error.message, 'error');
      button.disabled = !collectionBusy;
    }
  });
  $('collect-form').addEventListener('submit', async event => {
    event.preventDefault();
    if (collectionBusy) return;
    const keyword = filters.keyword.trim();
    if (!keyword) { message('collect-message', '请输入有效的搜索关键词。', 'warning'); return; }
    collectionTaskId = null;
    setCollectionBusy(true);
    message('collect-message', '正在启动采集任务…');
    try {
      const result = await apiRequest('/collect', 'POST', {date: filters.date, keyword, pages: Number($('collect-pages').value)});
      renderCollection(result.data, true);
      await loadCollectionStatus(true);
    } catch (error) {
      setCollectionBusy(false);
      message('collect-message', error.message, 'error');
      await loadCollectionStatus(false);
    }
  });
  loadCollectionStatus(false);
  $('run-preprocess').addEventListener('click', event => run(event.currentTarget, 'preprocess-message', '/preprocess', 'POST', {}, data => {
    for (const key of ['before_count', 'after_count', 'removed_duplicates']) metric(key, data[key]);
    table('preprocess-rows', data.rows, videoKeys);
    $('preprocess-details').textContent = `读取 ${data.source_files} 个文件；填补 ${data.filled_numeric_cells} 个缺失/无效数值，IQR 截尾 ${data.clipped_outlier_cells} 个数值，移除 ${data.invalid_urls} 条无效链接。文件：data/processed/${data.filename}；目标表：${data.table_name}。`;
    return data.after_count > 0 || data.rows?.length > 0;
  }));
  function renderClusters(data) {
    metric('optimal_k', data.optimal_k);
    charts.clusters(data);
    table('cluster-rows', data.rows, ['title', 'play', 'like', 'coin', 'favorite', 'share', 'cluster', 'label']);
    return data.distribution?.length > 0 || data.rows?.length > 0;
  }
  $('load-clusters').addEventListener('click', event => run(event.currentTarget, 'mining-message', '/mining/clusters', 'GET', {}, renderClusters));
  $('train-model').addEventListener('click', event => run(event.currentTarget, 'mining-message', '/mining/train', 'POST', {}, renderClusters));
  $('predict-form').addEventListener('submit', event => {
    event.preventDefault();
    const features = {};
    for (const [key, value] of new FormData(event.currentTarget)) features[key] = Number(value);
    run(event.currentTarget.querySelector('[type="submit"]'), 'mining-message', '/mining/predict', 'POST', features, data => {
      if (typeof data.label !== 'string' || !data.label.trim()) throw new Error('接口未返回有效的热度判断。');
      $('prediction-result').textContent = data.label;
      $('prediction-result').className = 'result-empty prediction-result';
    });
  });
  $('load-rules').addEventListener('click', event => run(event.currentTarget, 'mining-message', '/mining/rules', 'GET', {}, data => {
    table('rule-rows', data.rules, ['antecedents', 'consequents', 'support', 'confidence', 'lift']);
    return data.rules?.length > 0;
  }));
  $('build-knowledge').addEventListener('click', event => run(event.currentTarget, 'knowledge-message', '/knowledge/build', 'POST', {}, data => {
    if (typeof data.status !== 'string' || !data.status.trim()) throw new Error('接口未返回知识库状态。');
    $('knowledge-status').textContent = data.status;
  }));
  document.querySelectorAll('[data-question]').forEach(button => button.addEventListener('click', () => {
    $('question').value = button.dataset.question;
    $('question').focus();
  }));
  $('question-form').addEventListener('submit', event => {
    event.preventDefault();
    const question = $('question').value.trim();
    if (!question) { message('knowledge-message', '请输入有效问题。', 'warning'); return; }
    run(event.currentTarget.querySelector('[type="submit"]'), 'knowledge-message', '/knowledge/ask', 'POST', {question}, data => {
      if (typeof data.answer !== 'string' || !data.answer.trim()) throw new Error('接口尚未返回回答。');
      $('knowledge-answer').textContent = data.answer;
    });
  });
  $('logout-button').addEventListener('click', async event => {
    const button = event.currentTarget;
    button.disabled = true;
    try {
      await apiRequest('/logout', 'POST');
      window.location.assign('/login');
    } catch (error) {
      message('global-message', error.message + ' 当前为预览，可通过左侧“返回登录页”离开。', 'error');
    } finally {
      button.disabled = false;
    }
  });
}
