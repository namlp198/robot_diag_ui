<script>
  import { events } from './store.js';
  import { t, lang, findingText } from './i18n.js';
  let filter = 'all';
  $: shown = ($events ?? []).filter((e) => filter === 'all' || e.kind === filter).slice(-200).reverse();
  // Findings are re-translated from their id; flag changes, log lines and errors are shown as they came.
  const text = (e, l) => (e.finding ? `${e.finding.severity}: ${findingText(e.finding, l).title}` : e.text);
</script>

<div class="card">
  <h2>{$t('tl.title')}</h2>
  <div class="bar">
    {#each ['all', 'log', 'flag', 'finding', 'note', 'error'] as f}
      <button class:primary={filter === f} on:click={() => (filter = f)}>{$t('tl.kind.' + f)}</button>
    {/each}
    <span class="muted">{$t('tl.count', { n: $events.length })}</span>
  </div>
  <div class="list mono">
    {#each shown as e}
      <div class="row {e.kind}"><span class="t">{e.t.toFixed(2)}</span><span class="tag">{e.target}/{$t('tl.kind.' + e.kind)}</span><span class="text">{text(e, $lang)}</span></div>
    {:else}
      <div class="muted">{$t('tl.none')}</div>
    {/each}
  </div>
</div>

<style>
  .bar { display: flex; gap: 6px; align-items: center; margin-bottom: 8px; flex-wrap: wrap; }
  .list { max-height: 260px; overflow: auto; font-size: 12px; }
  .row { display: flex; gap: 10px; padding: 1px 0; border-bottom: 1px dashed var(--line); }
  .t { color: var(--muted); width: 64px; flex: none; text-align: right; }
  .tag { color: var(--muted); width: 130px; flex: none; }
  .text { white-space: pre-wrap; word-break: break-all; }
  .flag .text { color: var(--accent); }
  .error .text { color: var(--bad); }
  .finding .text { color: var(--warn); font-weight: 600; }
  .note .text { color: var(--ok); }
</style>
