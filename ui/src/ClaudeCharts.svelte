<script>
  // Charts Claude asked for with show_chart; highlight_range draws bands on them.
  import { onDestroy } from 'svelte';
  import uPlot from 'uplot';
  import 'uplot/dist/uPlot.min.css';
  import { claudeCharts, series, highlights } from './store.js';
  import { rate } from './util.js';

  const COLORS = ['#2b6cff', '#d23b3b', '#e08a00', '#1e8e4e', '#8a4fd0', '#0097a7'];
  const plots = new Map(); // id -> { u, el, spec }
  const hosts = {};
  let hl = [];

  function dataFor(spec, S) {
    // Series of different targets have different timestamps: merge onto the union of times.
    const cols = spec.series.map((s) => {
      const d = S[s.target];
      if (!d || !d.v[s.path]) return null;
      let t = d.t, v = d.v[s.path];
      if (s.as === 'rate') v = rate(t, v);
      const lo = spec.from ?? -Infinity, hi = spec.to ?? Infinity;
      const keep = t.map((x, i) => (x >= lo && x <= hi ? i : -1)).filter((i) => i >= 0);
      return { t: keep.map((i) => t[i]), v: keep.map((i) => v[i]) };
    });
    const times = [...new Set(cols.flatMap((c) => (c ? c.t : [])))].sort((a, b) => a - b);
    const data = [times];
    for (const c of cols) {
      const m = new Map(c ? c.t.map((x, i) => [x, c.v[i]]) : []);
      data.push(times.map((x) => (m.has(x) ? m.get(x) : null)));
    }
    return data;
  }

  function make(spec, el) {
    const css = getComputedStyle(document.documentElement);
    const text = css.getPropertyValue('--muted').trim() || '#666';
    const line = css.getPropertyValue('--line').trim() || '#ddd';
    const u = new uPlot({
      width: el.clientWidth || 400, height: 180, scales: { x: { time: false } },
      axes: [{ stroke: text, grid: { stroke: line } }, { stroke: text, grid: { stroke: line }, size: 46 }],
      series: [{ label: 't (s)' }, ...spec.series.map((s, i) => ({ label: `${s.target}:${s.path.split('.').slice(-2).join('.')}${s.as === 'rate' ? ' /s' : ''}`, stroke: COLORS[i % COLORS.length], width: 1.5, spanGaps: true }))],
      hooks: { draw: [(p) => {
        const { ctx, bbox } = p;
        for (const h of hl) {
          const x0 = p.valToPos(h.t0, 'x', true), x1 = p.valToPos(h.t1, 'x', true);
          ctx.save();
          ctx.fillStyle = 'rgba(255,170,0,0.22)';
          ctx.fillRect(Math.max(x0, bbox.left), bbox.top, Math.min(x1, bbox.left + bbox.width) - Math.max(x0, bbox.left), bbox.height);
          ctx.restore();
        }
      }] },
    }, dataFor(spec, {}), el);
    return u;
  }

  let raf = 0;
  function refresh(S) {
    cancelAnimationFrame(raf);
    raf = requestAnimationFrame(() => {
      for (const [id, p] of plots) p.u.setData(dataFor(p.spec, S));
    });
  }
  $: hl = $highlights, refresh($series);
  $: sync($claudeCharts);
  function sync(list) {
    queueMicrotask(() => {
      const ids = new Set(list.map((c) => c.id));
      for (const [id, p] of plots) if (!ids.has(id)) { p.u.destroy(); plots.delete(id); }
      for (const spec of list) {
        if (!plots.has(spec.id) && hosts[spec.id]) plots.set(spec.id, { u: make(spec, hosts[spec.id]), spec });
      }
      refresh($series);
    });
  }
  onDestroy(() => { cancelAnimationFrame(raf); plots.forEach((p) => p.u.destroy()); });
</script>

{#if $claudeCharts.length}
  <div class="card">
    <h2>Đồ thị Claude vẽ</h2>
    {#each $claudeCharts as c (c.id)}
      <div class="title">{c.title || 'đồ thị'} <span class="muted mono">{c.from ?? ''}{c.from != null || c.to != null ? '–' : ''}{c.to ?? ''}</span></div>
      <div bind:this={hosts[c.id]} class="chart"></div>
    {/each}
    {#each $highlights as h}<div class="muted mono">vùng {h.t0}–{h.t1} s {h.label}</div>{/each}
  </div>
{/if}

<style>
  .title { font-size: 12px; margin: 4px 0; }
  .chart { margin-bottom: 8px; }
</style>
