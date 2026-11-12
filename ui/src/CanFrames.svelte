<script>
  // CAN / FDCAN frames of the robot, sampled over SWD (rdt/cantap.py): last RX frame + TX FIFO elements. Not a bus capture.
  import { canFrames, canStats, status } from './store.js';
  import { t } from './i18n.js';

  let dir = 'all';
  let idq = '';
  let picked = null;

  $: st = $canStats.robot ?? null;
  $: rows = [...$canFrames].filter((f) => (dir === 'all' || f.dir === dir) && (!idq.trim() || ('0x' + f.id.toString(16)).includes(idq.trim().toLowerCase().replace(/^0x/, '0x')) || f.label.toLowerCase().includes(idq.trim().toLowerCase()))).slice(-400).reverse();
  $: ids = (() => {
    const m = new Map();
    for (const f of $canFrames) { const k = f.dir + ':' + f.id; const o = m.get(k) ?? { dir: f.dir, id: f.id, ext: f.ext, n: 0, last: f }; o.n++; o.last = f; m.set(k, o); }
    return [...m.values()].sort((a, b) => a.id - b.id || a.dir.localeCompare(b.dir));
  })();
  $: shown = picked ?? rows[0] ?? null;

  const idHex = (f) => '0x' + f.id.toString(16).toUpperCase().padStart(f.ext ? 8 : 3, '0');
  const bytes = (h) => (h.match(/../g) ?? []).join(' ').toUpperCase();
  $: reason = st?.tx_reason;
</script>

<div class="card">
  <h2>{$t('can.title')}</h2>
  {#if !$status.running && !$canFrames.length}<div class="warn">{$t('can.needWatch')}</div>{/if}
  {#if reason === 'peripheral_reads_off'}<div class="warn">{$t('can.txOff')}</div>
  {:else if reason === 'fdcan_not_initialised'}<div class="warn">{$t('can.notInit')}</div>
  {:else if reason}<div class="warn">{reason}</div>{/if}
  {#if st}
    <div class="counters mono">
      <span><span class="muted">TX</span> <b>{st.tx_frames}</b></span>
      <span><span class="muted">RX</span> <b>{st.rx_frames}</b></span>
      <span><span class="muted">{$t('can.fifo')}</span> <b>{st.tx_fifo_fill ?? '—'}</b></span>
      <span title={$t('can.lapTip')}><span class="muted">{$t('can.laps')}</span> <b class:bad={st.tx_possible_laps > 0}>{st.tx_possible_laps}</b></span>
    </div>
  {/if}
  <p class="muted small">{$t('can.note')}</p>

  <div class="ids">
    {#each ids as o}
      <button class="idchip" on:click={() => (picked = o.last)} title={o.last.label}>
        <span class="d {o.dir}">{o.dir.toUpperCase()}</span> <span class="mono">{idHex(o.last)}</span> <span class="muted">×{o.n}</span>
      </button>
    {/each}
  </div>

  <div class="bar">
    <label>{$t('can.dir')}<select bind:value={dir}><option value="all">{$t('fr.all')}</option><option value="tx">TX</option><option value="rx">RX</option></select></label>
    <label>{$t('can.filter')}<input bind:value={idq} placeholder="0x601, SDO…" class="mono" /></label>
    <span class="muted">{rows.length} / {$canFrames.length}</span>
  </div>

  {#if shown}
    <div class="detail mono">
      <span class="d {shown.dir}">{shown.dir.toUpperCase()}</span> {idHex(shown)} · {shown.ext ? '29-bit' : '11-bit'}{shown.rtr ? ' · RTR' : ''}{shown.fd ? ' · FD' : ''} · DLC {shown.dlc} · t={shown.t.toFixed(3)} s
      <div class="bytes">{#each (shown.data.match(/../g) ?? []) as b, i}<span class="b" title="byte {i}">{b.toUpperCase()}</span>{:else}<span class="muted">—</span>{/each}</div>
      <div class="lab">{shown.label}</div>
    </div>
  {/if}

  <div class="tbl">
    <table class="mono">
      <thead><tr>{#each $t('can.cols').split('|') as h}<th>{h}</th>{/each}</tr></thead>
      <tbody>
        {#each rows as f}
          <tr class:cur={picked === f} on:click={() => (picked = f)}>
            <td>{f.t.toFixed(3)}</td><td><span class="d {f.dir}">{f.dir.toUpperCase()}</span></td><td>{idHex(f)}</td><td>{f.dlc}</td>
            <td>{bytes(f.data)}</td><td class="lab">{f.label}</td>
          </tr>
        {:else}<tr><td colspan="6" class="muted">{$t('fr.none')}</td></tr>{/each}
      </tbody>
    </table>
  </div>
</div>

<style>
  .warn { color: var(--warn); margin-bottom: 6px; }
  .small { font-size: 12px; }
  .counters { display: flex; flex-wrap: wrap; gap: 4px 18px; font-size: 12px; margin: 6px 0; }
  .bad { color: var(--warn); }
  .ids { display: flex; flex-wrap: wrap; gap: 6px; margin: 8px 0; }
  .idchip { font-size: 12px; padding: 2px 8px; }
  .d { font-size: 10px; border-radius: 3px; padding: 0 4px; border: 1px solid var(--line); }
  .d.tx { color: var(--c3); border-color: var(--c3); } .d.rx { color: var(--c1); border-color: var(--c1); }
  .bar { display: flex; flex-wrap: wrap; gap: 14px; align-items: end; margin: 8px 0; }
  label { display: flex; flex-direction: column; gap: 2px; font-size: 11px; color: var(--muted); }
  .detail { font-size: 12px; margin-bottom: 8px; padding: 6px 8px; background: var(--panel2); border: 1px solid var(--line); border-radius: var(--radius); }
  .bytes { display: flex; flex-wrap: wrap; gap: 3px; margin: 6px 0; }
  .b { border: 1px solid var(--line); border-radius: 2px; padding: 1px 5px; }
  .lab { color: var(--accent2); }
  .tbl { max-height: 340px; overflow: auto; }
  table { width: 100%; font-size: 12px; }
  th, td { text-align: left; padding: 2px 8px; border-bottom: 1px dashed var(--line); white-space: nowrap; }
  th { color: var(--muted); font-weight: 600; position: sticky; top: 0; background: var(--panel); }
  tbody tr { cursor: pointer; } tbody tr:hover, tr.cur { background: color-mix(in srgb, var(--accent2) 14%, transparent); }
</style>
