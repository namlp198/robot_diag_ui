<script>
  import { onMount, onDestroy } from 'svelte';
  import uPlot from 'uplot';
  import 'uplot/dist/uPlot.min.css';
  import { RATES } from './panels.js';
  import { series } from './store.js';
  import { rate } from './util.js';

  const COLORS = ['#2b6cff', '#d23b3b', '#e08a00', '#1e8e4e', '#8a4fd0'];
  const WINDOW_S = 60;
  const charts = {}; // target -> { plot, el }
  let els = {};

  function build(target) {
    const list = RATES[target];
    const css = getComputedStyle(document.documentElement);
    const text = css.getPropertyValue('--muted').trim() || '#666';
    const line = css.getPropertyValue('--line').trim() || '#ddd';
    const opts = {
      width: els[target].clientWidth || 400, height: 170,
      scales: { x: { time: false } },
      axes: [{ stroke: text, grid: { stroke: line } }, { stroke: text, grid: { stroke: line }, size: 46 }],
      series: [{ label: 't (s)' }, ...list.map((r, i) => ({ label: r.label, stroke: COLORS[i % COLORS.length], width: 1.5, spanGaps: false }))],
      legend: { show: true },
    };
    charts[target] = new uPlot(opts, [[], ...list.map(() => [])], els[target]);
  }

  let raf = 0;
  function draw(data) {
    for (const target of Object.keys(RATES)) {
      const s = data[target];
      if (!s || !charts[target] || !s.t.length) continue;
      const end = s.t[s.t.length - 1];
      const from = Math.max(0, s.t.findIndex((x) => x >= end - WINDOW_S));
      const t = s.t.slice(from);
      const cols = RATES[target].map((r) => rate(t, (s.v[r.path] ?? []).slice(from)));
      charts[target].setData([t, ...cols]);
    }
  }
  const unsub = series.subscribe((data) => {
    cancelAnimationFrame(raf);
    raf = requestAnimationFrame(() => draw(data));
  });

  onMount(() => Object.keys(RATES).forEach(build));
  onDestroy(() => {
    unsub();
    cancelAnimationFrame(raf);
    Object.values(charts).forEach((c) => c.destroy());
  });
</script>

<div class="card">
  <h2>2. Link LoRa (sự kiện / giây)</h2>
  {#each Object.keys(RATES) as target}
    <div class="muted small">{target === 'robot' ? 'Robot (H755): nhận' : 'Remote (F446): gửi và nhận'}</div>
    <div bind:this={els[target]} class="chart"></div>
  {/each}
  <p class="muted small">Hai board không chung đồng hồ: trục thời gian là đồng hồ máy tính lúc nhận mẫu, sai số bằng chu kỳ poll.</p>
</div>

<style>
  .chart { margin-bottom: 8px; }
  .small { font-size: 12px; }
</style>
