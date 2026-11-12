<script>
  // Live Expressions: read-only watch of variables (by name, from the ELF) and raw addresses, like the CubeIDE view.
  // The list is kept in localStorage and sent to the daemon, which reads it on every sampling tick (rdt/exprs.py).
  import { onMount, onDestroy } from 'svelte';
  import { exprLatest, status } from './store.js';
  import { t } from './i18n.js';

  const KEY = 'rdt.exprs';
  const TYPES = ['u8', 'i8', 'u16', 'i16', 'u32', 'i32', 'f32', 'u64', 'i64', 'f64'];
  let items = []; // { id, target, text, type, count }
  let info = {}; // id -> { address, size, type, kind, error }
  let allowPeriph = false;
  let core = [];
  let fmt = 'auto';
  let target = 'robot';
  let text = '';
  let type = 'u32';
  let count = 1;
  let hints = [];
  let err = '';
  let ticks = {}; // id -> { v, changed } (when the shown value last changed, PC clock of the sample)
  let now = 0;

  const load = () => { try { return JSON.parse(localStorage.getItem(KEY) ?? '[]'); } catch { return []; } };
  const save = () => { try { localStorage.setItem(KEY, JSON.stringify(items)); } catch { /* not persisted */ } };
  const uid = () => 'e' + Math.random().toString(36).slice(2, 8);

  async function push() {
    save();
    for (const tg of new Set([...items.map((i) => i.target), ...Object.keys($status.targets ?? {})])) {
      try {
        const r = await fetch('/api/expr', { method: 'PUT', headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ target: tg, items: items.filter((i) => i.target === tg).map(({ id, text, type, count }) => ({ id, text, type, count })) }) });
        if (!r.ok) throw new Error((await r.json()).detail);
        for (const i of (await r.json()).items) info[i.id] = i;
      } catch (e) { err = String(e.message ?? e); }
    }
    info = info;
  }

  onMount(async () => {
    items = load();
    try { const s = await (await fetch('/api/settings')).json(); core = s.core_registers; allowPeriph = s.settings.allow_peripheral_reads; } catch { /* offline */ }
    if (items.length) push();
  });

  async function suggest() {
    if (text.length < 2 || /^(0x)?[0-9a-f]+$/i.test(text)) { hints = []; return; }
    try { hints = (await (await fetch(`/api/symbols?target=${target}&q=${encodeURIComponent(text)}&limit=25`)).json()).map((x) => x.path); } catch { hints = []; }
  }
  function add(spec) {
    err = '';
    const it = { id: uid(), target, type: 'u32', count: 1, ...spec };
    if (!it.text.trim()) return;
    items = [...items, it];
    text = '';
    push();
  }
  const addTyped = () => add({ text: text.trim(), type, count: Number(count) || 1 });
  function addCore(e) {
    const r = core.find((c) => c.name === e.target.value);
    e.target.value = '';
    if (r) add({ text: '0x' + r.address.toString(16).toUpperCase(), type: r.type, label: r.name });
  }
  function remove(id) { items = items.filter((i) => i.id !== id); delete info[id]; push(); }
  async function expand(it) {
    try {
      const m = await (await fetch(`/api/members?target=${it.target}&path=${encodeURIComponent(it.text)}`)).json();
      if (!Array.isArray(m) || !m.length) return;
      items = [...items.filter((i) => i.id !== it.id), ...m.slice(0, 64).map((x) => ({ id: uid(), target: it.target, text: x.path, type: 'u32', count: 1 }))];
      push();
    } catch (e) { err = String(e.message ?? e); }
  }

  // formatting
  function asInt(v, size) { return typeof v === 'number' && Number.isInteger(v) ? (v < 0 ? v + 2 ** (size * 8) : v) : null; }
  function show(v, inf) {
    if (v && typeof v === 'object' && !Array.isArray(v)) return { text: v.error, bad: true };
    const one = (x) => {
      if (typeof x === 'boolean') return x ? 'true' : 'false';
      if (typeof x === 'string') return x; // hex of a struct / array / bytes variable
      const unit = Math.max(1, Math.round((inf?.size ?? 4) / (inf?.count ?? 1))) || 4;
      const u = asInt(x, Math.min(unit, 4));
      if (u === null || fmt === 'dec' || (fmt === 'auto' && false)) return String(x);
      if (fmt === 'hex') return '0x' + u.toString(16).toUpperCase().padStart(unit * 2, '0');
      if (fmt === 'bin') return '0b' + u.toString(2).padStart(unit * 8, '0').replace(/(.{4})(?=.)/g, '$1_');
      return typeof x === 'number' && !Number.isInteger(x) ? String(Number(x.toPrecision(7))) : String(x);
    };
    return { text: Array.isArray(v) ? '[' + v.map(one).join(', ') + ']' : one(v), bad: false };
  }

  // When did a value last change (sample time on the PC clock). A plain subscription, not a `$:` block: a reactive
  // block that assigns what it reads re-triggers itself forever.
  const unsub = exprLatest.subscribe((all) => {
    for (const it of items) {
      const L = all[it.target];
      if (!L || !(it.id in L.values)) continue;
      const s = JSON.stringify(L.values[it.id]);
      const o = ticks[it.id];
      if (!o) ticks[it.id] = { s, changed: L.t };
      else if (o.s !== s) { o.s = s; o.changed = L.t; }
      if (L.t > now) now = L.t;
    }
  });
  onDestroy(unsub);
  $: targets = Object.keys($status.targets ?? {});
  $: rows = items.map((it) => ({ it, inf: info[it.id] ?? {}, v: $exprLatest[it.target]?.values?.[it.id], tk: ticks[it.id] }));
</script>

<div class="card">
  <h2>{$t('ex.title')}</h2>
  <p class="muted">{$t('ex.intro')}</p>
  <p class="muted small">{$t('ex.readOnly')}</p>
  {#if !$status.running}<div class="warn">{$t('ex.needWatch')}</div>{/if}
  {#if !allowPeriph}<div class="muted small">{$t('ex.periph')}</div>{/if}
  <div class="bar">
    <label>{$t('ex.target')}<select bind:value={target}>{#each targets as n}<option value={n}>{n}</option>{/each}</select></label>
    <label class="grow">{$t('ex.expr')}
      <input bind:value={text} on:input={suggest} on:keydown={(e) => e.key === 'Enter' && addTyped()} list="expr-hints" placeholder={$t('ex.exprPh')} class="mono" />
      <datalist id="expr-hints">{#each hints as h}<option value={h}></option>{/each}</datalist>
    </label>
    <label>{$t('ex.type')}<select bind:value={type}>{#each TYPES as ty}<option value={ty}>{ty}</option>{/each}</select></label>
    <label>{$t('ex.count')}<input type="number" min="1" max="256" bind:value={count} class="num" /></label>
    <button class="primary" on:click={addTyped} disabled={!text.trim()}>{$t('ex.add')}</button>
    <select on:change={addCore}><option value="">{$t('ex.core')}</option>{#each core as c}<option value={c.name} title={c.meaning}>{c.name}</option>{/each}</select>
    <label>{$t('ex.format')}
      <select bind:value={fmt}>{#each ['auto', 'dec', 'hex', 'bin'] as f}<option value={f}>{$t('ex.fmt.' + f)}</option>{/each}</select>
    </label>
    {#if items.length}<button on:click={() => { items = []; info = {}; push(); }}>{$t('ex.clear')}</button>{/if}
  </div>
  {#if err}<div class="bad">{err}</div>{/if}
  <div class="tbl">
    <table class="mono">
      <thead><tr>{#each $t('ex.cols').split('|') as h}<th>{h}</th>{/each}<th></th></tr></thead>
      <tbody>
        {#each rows as { it, inf, v, tk } (it.id)}
          {@const s = v === undefined ? null : show(v, { ...inf, count: it.count })}
          <tr>
            <td>{it.target}</td>
            <td>{it.text}{#if it.count > 1 && !inf.symbol} ×{it.count}{/if}</td>
            <td class="muted">{inf.address !== undefined ? '0x' + inf.address.toString(16).toUpperCase().padStart(8, '0') : ''}</td>
            <td class="muted">{inf.type ?? it.type}</td>
            <td class:bad={inf.error || s?.bad} class="val">
              {#if inf.error}{inf.error}{:else if s}{s.text}{:else}<span class="muted">…</span>{/if}
            </td>
            <td class="muted">{tk && now ? $t('ex.ago', { s: Math.max(0, now - tk.changed).toFixed(1) }) : $t('ex.never')}</td>
            <td class="act">
              {#if inf.kind === 'struct' || inf.kind === 'array'}<button class="mini" on:click={() => expand(it)}>{$t('ex.expand')}</button>{/if}
              <button class="mini" on:click={() => remove(it.id)} title={$t('ex.remove')}>✕</button>
            </td>
          </tr>
        {:else}<tr><td colspan="7" class="muted">{$t('ex.empty')}</td></tr>{/each}
      </tbody>
    </table>
  </div>
</div>

<style>
  .bar { display: flex; flex-wrap: wrap; gap: 10px; align-items: end; margin: 8px 0; }
  label { display: flex; flex-direction: column; gap: 2px; font-size: 11px; color: var(--muted); }
  .grow { flex: 1; min-width: 260px; }
  .num { width: 70px; }
  .small { font-size: 12px; margin: 2px 0 6px; }
  .warn { color: var(--warn); margin-bottom: 6px; }
  .bad { color: var(--bad); }
  .tbl { overflow: auto; }
  table { width: 100%; font-size: 12px; }
  th, td { text-align: left; padding: 3px 8px; border-bottom: 1px dashed var(--line); white-space: nowrap; }
  th { color: var(--muted); font-weight: 600; }
  .val { color: var(--accent); white-space: normal; word-break: break-all; }
  .act { text-align: right; }
  .mini { font-size: 11px; padding: 1px 8px; }
</style>
