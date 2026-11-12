<script>
  import { conn, replayName } from './store.js';
  import { t } from './i18n.js';
  let res = null;
  let err = '';
  async function load() {
    err = '';
    res = null;
    const url = $replayName ? `/api/sessions/${encodeURIComponent($replayName)}/sweep` : '/api/sweep';
    try {
      const r = await fetch(url);
      const j = await r.json();
      if (!r.ok) err = j.detail ?? r.statusText;
      else if (j.error) err = j.error;
      else res = j;
    } catch (e) {
      err = String(e);
    }
  }
  const HEAD = 'gap_ms,seconds,sent,control_rx,accepted,lost,loss_pct,crc_errors';
  $: csv = res
    ? 'data:text/csv;charset=utf-8,' +
      encodeURIComponent([HEAD, ...res.rows.map((r) => [r.gap_ms, r.seconds, r.sent ?? '', r.control_rx, r.accepted, r.lost, r.loss_pct, r.crc_errors].join(','))].join('\n'))
    : '';
</script>

<div class="card">
  <h2>{$t('sweep.title')}</h2>
  <div class="bar">
    <button on:click={load} disabled={$conn === 'offline'}>{$t('sweep.calc', { src: $t($replayName ? 'sweep.replay' : 'sweep.live') })}</button>
    {#if res}<a href={csv} download="link_sweep.csv">{$t('sweep.csv')}</a>{/if}
    <span class="muted">{$t('sweep.hint')}</span>
  </div>
  {#if err}<div class="muted">{err}</div>{/if}
  {#if res}
    <table class="mono">
      <thead><tr>{#each $t('sweep.cols').split('|') as h}<th>{h}</th>{/each}</tr></thead>
      <tbody>
        {#each res.rows as r}
          <tr class:bad={r.loss_pct >= 5} class:warn={r.loss_pct >= 1 && r.loss_pct < 5}>
            <td>{r.gap_ms}</td><td>{r.seconds}</td><td>{r.sent ?? '—'}</td><td>{r.control_rx}</td><td>{r.accepted}</td>
            <td>{r.lost}{r.restarts_removed ? $t('sweep.restart', { n: r.restarts_removed }) : ''}</td><td>{r.loss_pct}</td><td>{r.crc_errors}</td>
          </tr>
        {/each}
      </tbody>
    </table>
    <p class="muted small">{$t('sweep.src', { src: $t(res.source === 'vcp' ? 'sweep.srcVcp' : 'sweep.srcVar') })}</p>
  {/if}
</div>

<style>
  .bar { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin-bottom: 8px; }
  table { border-collapse: collapse; width: 100%; font-size: 12px; }
  th, td { text-align: right; padding: 3px 8px; border-bottom: 1px solid var(--line); }
  tr.warn td { background: color-mix(in srgb, var(--warn) 14%, transparent); }
  tr.bad td { background: color-mix(in srgb, var(--bad) 16%, transparent); }
  .small { font-size: 12px; }
</style>
