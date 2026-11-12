<script>
  import { events } from './store.js';
  let filter = 'all';
  $: shown = ($events ?? []).filter((e) => filter === 'all' || e.kind === filter || (filter === 'log' && e.kind === 'log')).slice(-200).reverse();
</script>

<div class="card">
  <h2>5. Dòng thời gian</h2>
  <div class="bar">
    {#each ['all', 'log', 'flag', 'finding', 'note', 'error'] as f}
      <button class:primary={filter === f} on:click={() => (filter = f)}>{f}</button>
    {/each}
    <span class="muted">{$events.length} mục (log VCP remote, đổi cờ, lỗi đọc)</span>
  </div>
  <div class="list mono">
    {#each shown as e}
      <div class="row {e.kind}"><span class="t">{e.t.toFixed(2)}</span><span class="tag">{e.target}/{e.kind}</span><span class="text">{e.text}</span></div>
    {:else}
      <div class="muted">chưa có sự kiện</div>
    {/each}
  </div>
</div>

<style>
  .bar { display: flex; gap: 6px; align-items: center; margin-bottom: 8px; flex-wrap: wrap; }
  .list { max-height: 260px; overflow: auto; font-size: 12px; }
  .row { display: flex; gap: 10px; padding: 1px 0; border-bottom: 1px dashed var(--line); }
  .t { color: var(--muted); width: 64px; flex: none; text-align: right; }
  .tag { color: var(--muted); width: 110px; flex: none; }
  .text { white-space: pre-wrap; word-break: break-all; }
  .flag .text { color: var(--accent); }
  .error .text { color: var(--bad); }
  .finding .text { color: #e08a00; font-weight: 600; }
  .note .text { color: var(--ok); }
</style>
