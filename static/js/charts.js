/* ECharts 图表只在收到非空数据后创建，不生成演示数据。 */
window.DashboardCharts = (() => {
  const instances = new Map();
  const colors = ['#48d6ca', '#5799f1', '#a293ed', '#e0b76b', '#76b3b0'];

  function empty(id, text = '暂无分析数据') {
    const element = document.getElementById(id);
    if (instances.has(id)) {
      instances.get(id).dispose();
      instances.delete(id);
    }
    element.replaceChildren();
    const placeholder = document.createElement('div');
    placeholder.className = 'chart-empty';
    const glyph = document.createElement('span');
    glyph.className = 'empty-glyph';
    glyph.setAttribute('aria-hidden', 'true');
    for (let i = 0; i < 3; i++) glyph.append(document.createElement('i'));
    const title = document.createElement('span');
    title.textContent = text;
    const hint = document.createElement('small');
    hint.textContent = '加载当前范围的数据后展示';
    placeholder.append(glyph, title, hint);
    element.append(placeholder);
  }

  function draw(id, option, hasData) {
    if (!hasData) return empty(id);
    if (!window.echarts) return empty(id, '图表库未加载，请检查网络');
    empty(id);
    const element = document.getElementById(id);
    element.replaceChildren();
    const chart = echarts.init(element);
    instances.set(id, chart);
    chart.setOption({
      animation: false,
      color: colors,
      textStyle: {color: '#8b9bb2', fontFamily: 'Microsoft YaHei, sans-serif', fontSize: 11},
      tooltip: {trigger: 'axis', renderMode: 'richText', backgroundColor: '#1b2d43', borderColor: '#35506a', textStyle: {color: '#e8eef7'}},
      grid: {left: 15, right: 20, bottom: 10, top: 30, containLabel: true},
      ...option
    });
  }

  function axis(type, name = '') {
    return {type, name, nameTextStyle: {color: '#8b9bb2', fontSize: 10}, axisLine: {lineStyle: {color: '#30425b'}}, axisTick: {show: false}, splitLine: {show: type === 'value', lineStyle: {color: '#243249', type: 'dashed'}}, axisLabel: {color: '#8b9bb2', fontSize: 10}};
  }

  function analysis(data) {
    const top = data.top10_play || {};
    const interactions = data.interaction_ratio || [];
    const lengths = data.title_len_play || {};
    const scatter = data.like_coin_scatter || [];
    draw('chart-top10', {
      grid: {left: 10, right: 35, top: 10, bottom: 5, containLabel: true},
      xAxis: axis('value'),
      yAxis: {...axis('category'), inverse: true, data: top.titles || [], axisLabel: {width: 100, overflow: 'truncate', fontSize: 10, color: '#8b9bb2'}},
      series: [{type: 'bar', data: top.values || [], barMaxWidth: 12, itemStyle: {borderRadius: [0, 3, 3, 0]}}]
    }, Array.isArray(top.titles) && top.titles.length > 0);
    draw('chart-interaction', {
      tooltip: {trigger: 'item', renderMode: 'richText'},
      legend: {bottom: 0, icon: 'circle', itemWidth: 8, itemHeight: 8, textStyle: {color: '#8b9bb2', fontSize: 11}},
      series: [{type: 'pie', radius: ['48%', '72%'], center: ['50%', '43%'], label: {show: false}, data: interactions}]
    }, Array.isArray(interactions) && interactions.some(item => item.value > 0));
    draw('chart-title', {
      xAxis: {...axis('category', '字数'), data: lengths.x || [], boundaryGap: false},
      yAxis: axis('value', '播放量 / 万'),
      series: [{type: 'line', data: lengths.y || [], smooth: false, symbolSize: 5, lineStyle: {width: 2}, areaStyle: {opacity: 0.08}}]
    }, Array.isArray(lengths.x) && lengths.x.length > 0);
    draw('chart-scatter', {
      tooltip: {trigger: 'item', renderMode: 'richText'},
      xAxis: axis('value', '点赞'), yAxis: axis('value', '投币'),
      series: [{type: 'scatter', data: scatter, symbolSize: 7, itemStyle: {color: colors[1], opacity: 0.7}}]
    }, Array.isArray(scatter) && scatter.length > 0);
  }

  function clusters(data) {
    const elbow = data.elbow || {};
    const distribution = data.distribution || [];
    draw('chart-elbow', {
      xAxis: {...axis('category', 'K'), data: elbow.k || []}, yAxis: axis('value', 'SSE'),
      series: [{type: 'line', data: elbow.sse || [], symbolSize: 6}]
    }, Array.isArray(elbow.k) && elbow.k.length > 0);
    draw('chart-clusters', {
      xAxis: {...axis('category'), data: distribution.map(item => item.name)}, yAxis: axis('value', '视频数'),
      series: [{type: 'bar', data: distribution.map((item, i) => ({value: item.value, itemStyle: {color: colors[i % colors.length]}})), barMaxWidth: 42}]
    }, distribution.length > 0);
  }

  function resize() {
    instances.forEach(chart => chart.resize());
  }
  window.addEventListener('resize', resize);
  return {analysis, clusters, empty, resize};
})();
