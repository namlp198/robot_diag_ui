<script>
  import { FLAGS } from './panels.js';
  import { latest } from './store.js';
  $: rows = FLAGS.map((f) => {
    const x = $latest[f.target]?.[f.path];
    const on = x ? Boolean(x.v) : null;
    const cls = on === null ? 'idle' : f.bad ? (on ? 'bad' : 'ok') : on ? 'ok' : 'bad';
    return { f, on, cls };
  });
</script>

<div class="card">
  <h2>3. Cờ và trạng thái</h2>
  <div class="grid">
    {#each rows as r}
      <div class="flag {r.cls}"><span class="dot"></span>{r.f.label}<b class="mono">{r.on === null ? '—' : r.on ? '1' : '0'}</b></div>
    {/each}
  </div>
</div>

<style>
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(210px, 1fr)); gap: 6px; }
  .flag { display: flex; align-items: center; gap: 8px; border: 1px solid var(--line); border-radius: 6px; padding: 5px 8px; }
  .flag b { margin-left: auto; }
  .dot { width: 10px; height: 10px; border-radius: 50%; background: var(--idle); }
  .ok .dot { background: var(--ok); }
  .bad .dot { background: var(--bad); }
</style>
