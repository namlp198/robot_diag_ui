<script>
  // RCL frames sampled from the boards' buffers and decoded by the daemon (rdt/rcl.py).
  import { frames, status, latest as live } from './store.js';
  import { t } from './i18n.js';

  const SOURCES = ['remote_tx', 'robot_rx', 'remote_rx'];
  let filter = 'all';
  let picked = null; // a frame object chosen in the table or from a card
  let copied = false;

  $: latest = Object.fromEntries(SOURCES.map((s) => [s, [...$frames].reverse().find((f) => f.source === s) ?? null]));
  $: rows = [...$frames].filter((f) => filter === 'all' || f.source === filter).slice(-300).reverse();
  $: shown = picked ?? latest.remote_tx ?? latest.robot_rx ?? latest.remote_rx;
  $: gap = latest.remote_tx && latest.robot_rx ? (latest.remote_tx.seq - latest.robot_rx.seq + 256) % 256 : null;

  // Per source, SEQ steps between consecutive frames we saw: a step > 1 means frames we did not see (lost on air OR just
  // not polled in time), so it is shown as "+n", not as an error.
  $: missed = (() => {
    const prev = {}, out = new Map();
    for (const f of [...$frames].sort((a, b) => a.t - b.t)) {
      const p = prev[f.source];
      if (p !== undefined && f.type_name === p.type_name) { const d = (f.seq - p.seq + 256) % 256 - 1; if (d > 0 && d < 200) out.set(f, d); }
      prev[f.source] = f;
    }
    return out;
  })();
  // The same counters the dashboard uses: what the parsers themselves counted (all frames, including the bad ones).
  const COUNTERS = [
    ['robot', 's_lora_rx.parser.stats.frames', 'frames'], ['robot', 's_lora_rx.parser.stats.crc_errors', 'crc'],
    ['robot', 's_lora_rx.parser.stats.truncated', 'truncated'], ['robot', 's_lora_rx.filter.stats.lost', 'lost'],
    ['robot', 's_lora_rx.filter.stats.duplicates', 'dup'], ['remote', 's_tx.out.control_frames', 'control tx'],
    ['remote', 's_tx.out.tx_failures', 'tx fail'], ['remote', 's_link.frames_bad', 'rx bad'],
  ];
  $: counters = COUNTERS.map(([tg, p, label]) => ({ tg, label, v: $live[tg]?.[p]?.v }));
  const bytes = (hex) => hex.match(/../g) ?? [];
  const hex2 = (n) => n.toString(16).toUpperCase().padStart(2, '0');
  function fieldOf(f, i) {
    return f.fields.find((x) => i >= x.offset && i < x.offset + x.size)?.name ?? '';
  }
  async function copy(f) {
    try { await navigator.clipboard.writeText(bytes(f.hex).join(' ').toUpperCase()); copied = true; setTimeout(() => (copied = false), 1200); } catch { /* no clipboard */ }
  }
  const pretty = (v) => (Array.isArray(v) ? v.join(', ') : typeof v === 'object' && v !== null ? JSON.stringify(v) : String(v));
</script>

<div class="card">
  <h2>{$t('fr.title')}</h2>
  {#if !$status.running && !$frames.length}<div class="warn">{$t('fr.needWatch')}</div>{/if}
  <div class="cards">
    {#each SOURCES as s}
      {@const f = latest[s]}
      <button class="src" class:sel={shown && f && shown.hex === f.hex && shown.source === s} on:click={() => (picked = f)} disabled={!f}>
        <div class="srct">{$t('fr.src.' + s)}</div>
        {#if f}
          <div class="mono">{f.type_name} · SEQ {f.seq} · {f.size} B · <span class={f.crc_ok ? 'ok' : 'bad'}>{f.crc_ok ? $t('fr.crcOk') : $t('fr.crcBad')}</span></div>
          <div class="mono hex">{bytes(f.hex).join(' ').toUpperCase()}</div>
        {:else}<div class="muted">{$t('fr.none')}</div>{/if}
      </button>
    {/each}
  </div>
  <div class="muted small">{gap === null ? $t('fr.noMatch') : $t('fr.match', { tx: latest.remote_tx.seq, rx: latest.robot_rx.seq, d: gap })}</div>
  <div class="counters mono">
    {#each counters as c}<span><span class="muted">{c.tg} {c.label}</span> <b class:bad={(c.label === 'crc' || c.label === 'lost' || c.label === 'truncated' || c.label === 'tx fail' || c.label === 'rx bad') && c.v > 0}>{c.v ?? '—'}</b></span>{/each}
  </div>
  <p class="muted small">{$t('fr.why')}</p>
</div>

<div class="card">
  <h2>{$t('fr.inspect')}</h2>
  {#if shown}
    <div class="meta mono">
      {$t('fr.src.' + shown.source)} · {shown.type_name} (0x{hex2(shown.type_id)}) · VER {shown.version} · LINK_ID 0x{shown.link_id.toString(16).toUpperCase().padStart(4, '0')} · SEQ {shown.seq} · LEN {shown.length} · t={shown.t.toFixed(3)} s ·
      <span class={shown.crc_ok ? 'ok' : 'bad'}>{shown.crc_ok ? $t('fr.crcOk') : $t('fr.crcBad')} 0x{shown.crc.toString(16).toUpperCase().padStart(4, '0')}</span>
      <button class="mini" on:click={() => copy(shown)}>{copied ? $t('fr.copied') : $t('fr.copyHex')}</button>
    </div>
    <div class="dump mono">
      {#each bytes(shown.hex) as b, i}<span class="b f-{fieldOf(shown, i)}" title="{fieldOf(shown, i)} [{i}]">{b.toUpperCase()}</span>{/each}
    </div>
    <div class="legend">
      {#each shown.fields as fl}<span class="b f-{fl.name}">{fl.name}</span>{/each}
    </div>
    <h3>{$t('fr.payload')}</h3>
    {#if shown.payload && Object.keys(shown.payload).length}
      <dl>
        {#each Object.entries(shown.payload) as [k, v]}
          {#if k === 'slots'}
            <dt>{$t('fr.slots')}</dt><dd class="mono chips">{#each Object.entries(v) as [n, st]}<span class="chip s-{st}">{n}={st}</span>{/each}</dd>
          {:else if k === 'records'}
            <dt>{$t('fr.records')}</dt>
            <dd><table class="mono"><tbody>{#each v as r}<tr><td>0x{hex2(r.id)}</td><td>{r.name ?? ''}</td><td>{r.error ?? pretty(r.value)}</td></tr>{/each}</tbody></table></dd>
          {:else if k === 'tlv'}
            <dt>{$t('fr.tlv')}</dt>
            <dd><table class="mono"><tbody>{#each v as r}<tr><td>0x{hex2(r.id)}</td><td>{r.name ?? ''}</td><td>{r.error ?? pretty(r.value)}</td></tr>{:else}<tr><td class="muted">—</td></tr>{/each}</tbody></table></dd>
          {:else if k === 'flags' || k === 'robot_flags'}
            <dt>{$t('fr.flags')}</dt><dd class="mono chips">{#each v as n}<span class="chip">{n}</span>{:else}<span class="muted">—</span>{/each}</dd>
          {:else if !k.endsWith('_raw')}
            <dt>{k}</dt><dd class="mono">{pretty(v)}</dd>
          {/if}
        {/each}
      </dl>
    {:else}<div class="muted">—</div>{/if}
  {:else}<div class="muted">{$t('fr.pickRow')}</div>{/if}
</div>

<div class="card">
  <h2>{$t('fr.history')}</h2>
  <div class="bar">
    <label>{$t('fr.filter')}
      <select bind:value={filter}><option value="all">{$t('fr.all')}</option>{#each SOURCES as s}<option value={s}>{$t('fr.src.' + s)}</option>{/each}</select>
    </label>
    <span class="muted">{rows.length} / {$frames.length}</span>
  </div>
  <div class="tbl">
    <table class="mono">
      <thead><tr>{#each $t('fr.cols').split('|') as h}<th>{h}</th>{/each}<th></th></tr></thead>
      <tbody>
        {#each rows as f}
          <tr class:cur={picked === f} class:badrow={!f.crc_ok} on:click={() => (picked = f)}>
            <td>{f.t.toFixed(2)}</td><td>{$t('fr.src.' + f.source)}</td><td>{f.type_name}</td><td>{f.seq}{#if missed.get(f)} <span class="gapb" title={$t('fr.gapTip')}>+{missed.get(f)}</span>{/if}</td>
            <td>0x{f.link_id.toString(16).toUpperCase().padStart(4, '0')}</td><td>{f.size}</td><td>{f.crc_ok ? '✓' : '✕'}</td>
            <td class="hexcell">{bytes(f.hex).slice(0, 12).join(' ').toUpperCase()}{f.size > 12 ? ' …' : ''}</td>
          </tr>
        {:else}<tr><td colspan="8" class="muted">{$t('fr.none')}</td></tr>{/each}
      </tbody>
    </table>
  </div>
  <p class="muted small">{$t('fr.note')}</p>
</div>

<style>
  .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 8px; margin-bottom: 8px; }
  .src { text-align: left; display: block; padding: 8px; }
  .src.sel { border-color: var(--accent); }
  .srct { color: var(--accent2); font-size: 11px; text-transform: uppercase; letter-spacing: .05em; margin-bottom: 4px; }
  .hex { font-size: 11px; word-break: break-all; color: var(--muted); margin-top: 4px; }
  .ok { color: var(--ok); } .bad { color: var(--bad); }
  .warn { color: var(--warn); margin-bottom: 6px; }
  .small { font-size: 12px; }
  .meta { font-size: 12px; margin-bottom: 8px; }
  .mini { font-size: 11px; padding: 1px 8px; margin-left: 8px; }
  .dump { display: flex; flex-wrap: wrap; gap: 3px; margin-bottom: 6px; }
  .legend { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; font-size: 11px; }
  .b { padding: 1px 4px; border-radius: 2px; border: 1px solid var(--line); font-size: 12px; }
  .f-SOF { color: var(--muted); } .f-VER { color: var(--c4); border-color: var(--c4); } .f-TYPE { color: var(--c3); border-color: var(--c3); }
  .f-LINK_ID { color: var(--c5); border-color: var(--c5); } .f-SEQ { color: var(--c1); border-color: var(--c1); } .f-LEN { color: var(--c6); border-color: var(--c6); }
  .f-PAYLOAD { color: var(--text); } .f-CRC { color: var(--c2); border-color: var(--c2); }
  h3 { margin: 8px 0 4px; font-size: 12px; color: var(--accent2); }
  dl { display: grid; grid-template-columns: max-content 1fr; gap: 3px 14px; margin: 0; font-size: 12px; }
  dt { color: var(--muted); } dd { margin: 0; }
  .chips { display: flex; flex-wrap: wrap; gap: 4px; }
  .chip { border: 1px solid var(--line); border-radius: 99px; padding: 0 8px; }
  .chip.s-A, .chip.s-B { border-color: var(--ok); color: var(--ok); }
  .chip.s-absent { color: var(--muted); }
  .bar { display: flex; gap: 12px; align-items: center; margin-bottom: 6px; }
  label { display: flex; gap: 6px; align-items: center; font-size: 12px; }
  .tbl { max-height: 320px; overflow: auto; }
  table { width: 100%; font-size: 12px; }
  th, td { text-align: left; padding: 2px 8px; border-bottom: 1px dashed var(--line); white-space: nowrap; }
  th { color: var(--muted); font-weight: 600; position: sticky; top: 0; background: var(--panel); }
  tbody tr { cursor: pointer; } tbody tr:hover, tr.cur { background: color-mix(in srgb, var(--accent2) 14%, transparent); }
  tr.badrow td { color: var(--bad); }
  .hexcell { color: var(--muted); }
  .counters { display: flex; flex-wrap: wrap; gap: 4px 18px; font-size: 12px; margin: 6px 0; }
  .gapb { color: var(--warn); border: 1px solid var(--warn); border-radius: 99px; padding: 0 5px; font-size: 10px; }
</style>
