<script>
  import { onMount, onDestroy } from 'svelte';
  import { get } from 'svelte/store';
  import uPlot from 'uplot';
  import 'uplot/dist/uPlot.min.css';
  import { RATES } from './panels.js';
  import { series } from './store.js';
  import { rate, chartColors } from './util.js';
  import { t, theme } from './i18n.js';

  const WINDOW_S = 60;
  const charts = {}; // target -> { plot, el }
  let els = {};

  function build(target) {
    const list = RATES[target];
    const { text, line, series: COLORS } = chartColors();
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
  // The theme changed: uPlot colours are fixed at creation, so rebuild the charts with the new palette.
  // (A plain subscription, not a `$:` block: a reactive block that touches `charts` would re-trigger itself.)
  function rebuild() {
    for (const k of Object.keys(RATES)) { charts[k]?.destroy(); if (els[k]) build(k); }
    draw(get(series));
  }
  let first = true;
  const unsubTheme = theme.subscribe(() => { if (first) { first = false; return; } queueMicrotask(rebuild); });
  onDestroy(() => {
    unsub();
    unsubTheme();
    cancelAnimationFrame(raf);
    Object.values(charts).forEach((c) => c.destroy());
  });
</script>

<div class="card">
  <h2>{$t('link.title')}</h2>
  {#each Object.keys(RATES) as target}
    <div class="muted small">{$t(target === 'robot' ? 'link.robot' : 'link.remote')}</div>
    <div bind:this={els[target]} class="chart"></div>
  {/each}
  <p class="muted small">{$t('link.note')}</p>
</div>

<style>
  .chart { margin-bottom: 8px; }
  .small { font-size: 12px; }
</style>
