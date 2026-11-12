<script>
  import { findings, highlights, sendChat, chat } from './store.js';
  import { t, lang, findingText } from './i18n.js';
  const ORDER = { error: 0, warn: 1, info: 2 };
  $: list = [...$findings].sort((a, b) => ORDER[a.severity] - ORDER[b.severity] || a.t0 - b.t0).map((f) => ({ f, x: findingText(f, $lang) }));
  const ask = (f, title) => sendChat($t('find.askText', { title, target: f.target, t0: f.t0.toFixed(1), t1: f.t1.toFixed(1) }), null).catch(() => {});
  const mark = (f, title) => highlights.update((a) => [...a, { t0: f.t0, t1: Math.max(f.t1, f.t0 + 0.2), label: title }]);
</script>

<div class="card">
  <h2>{$t('find.title')} <span class="muted">({list.length})</span></h2>
  <div class="scroll">
  {#each list as { f, x }}
    <div class="f {f.severity}">
      <div class="head"><b>{x.title}</b><span class="muted mono">{f.target} · {f.t0.toFixed(1)}–{f.t1.toFixed(1)} s</span></div>
      <div>{x.detail}</div>
      {#if x.checks?.length}<ul class="muted">{#each x.checks as c}<li>{c}</li>{/each}</ul>{/if}
      <div class="acts"><button on:click={() => mark(f, x.title)}>{$t('find.mark')}</button><button on:click={() => ask(f, x.title)} disabled={$chat.busy}>{$t('find.ask')}</button></div>
    </div>
  {:else}
    <div class="muted">{$t('find.none')}</div>
  {/each}
  </div>
</div>

<style>
  .scroll { max-height: 340px; overflow-y: auto; padding-right: 4px; }
  .f { border-left: 4px solid var(--idle); padding: 6px 10px; margin-bottom: 8px; background: var(--panel2); border-radius: 2px; }
  .f.error { border-color: var(--bad); }
  .f.warn { border-color: var(--warn); }
  .f.info { border-color: var(--accent2); }
  .head { display: flex; gap: 10px; justify-content: space-between; flex-wrap: wrap; }
  ul { margin: 4px 0; padding-left: 18px; font-size: 12px; }
  .acts { display: flex; gap: 6px; }
  .acts button { font-size: 12px; padding: 2px 8px; }
</style>
