<script>
  // Reference page: monitored data, diagnosis rules, pyOCD and STM32_Programmer_CLI commands (from /api/reference).
  import { onMount } from 'svelte';
  import { t, lang } from './i18n.js';

  let data = null;
  let err = '';
  let q = '';
  let safety = 'all';
  let copied = '';

  onMount(async () => {
    try {
      const r = await fetch('/api/reference');
      if (!r.ok) throw new Error(r.statusText);
      data = await r.json();
    } catch (e) { err = String(e.message ?? e); }
  });

  const hit = (...parts) => !q.trim() || parts.join(' ').toLowerCase().includes(q.trim().toLowerCase());
  async function copy(text) {
    try { await navigator.clipboard.writeText(text); copied = text; setTimeout(() => (copied = ''), 1200); } catch { /* clipboard not available */ }
  }
  $: L = $lang;
  let sections = [];
  function rowsFor(id) {
    if (!data) return [];
    if (id === 'monitored') return data.monitored.filter((m) => hit(m.name, m.target, m.panel, m.en, m.vi));
    if (id === 'analyzers') return data.analyzers.filter((a) => hit(a.id, a.en, a.vi));
    return data[id].filter((c) => (safety === 'all' || c.safety === safety) && hit(c.name, c.syntax, c.en, c.vi));
  }
  // re-filter when the query or safety filter changes
  $: if (data) { q; safety; sections = data.sections.map((s) => ({ ...s, rows: rowsFor(s.id) })); }
</script>

<div class="card">
  <div class="bar">
    <h2>{$t('ref.title')}</h2>
    <input type="search" bind:value={q} placeholder={$t('ref.search')} />
    {#if data}
      <label>{$t('ref.safety')}
        <select bind:value={safety}>
          <option value="all">{$t('ref.safety.all')}</option>
          {#each Object.entries(data.safety) as [k, v]}<option value={k}>{v[L]}</option>{/each}
        </select>
      </label>
    {/if}
    <span class="muted">{$t('ref.docs')}</span>
  </div>
  {#if err}<div class="bad">{$t('ref.loadFail', { e: err })}</div>{/if}
  {#each sections as s}
    <h3>{s.title[L]} <span class="muted">({s.rows.length})</span></h3>
    <p class="muted">{s.intro[L]}</p>
    {#if s.id === 'monitored'}
      <table>
        <thead><tr><th>{$t('ref.cols.var')}</th><th>{$t('ref.board')}</th><th>{$t('ref.shown')}</th><th></th></tr></thead>
        <tbody>
          {#each s.rows as m}
            <tr><td class="mono"><button class="link" title={$t('ref.copy')} on:click={() => copy(m.name)}>{m.name}</button>{#if copied === m.name} ✓{/if}</td><td>{m.target}</td><td class="muted">{m.panel}</td><td>{m[L]}</td></tr>
          {/each}
        </tbody>
      </table>
    {:else if s.id === 'analyzers'}
      <table>
        <tbody>{#each s.rows as a}<tr><td class="mono">{a.id}</td><td class="sev {a.severity.split('/')[0]}">{a.severity}</td><td>{a[L]}</td></tr>{/each}</tbody>
      </table>
    {:else}
      <table>
        <tbody>
          {#each s.rows as c}
            <tr>
              <td class="mono name">{c.name}{#if c.used_by_rdt}<span class="used">{$t('ref.used')}</span>{/if}</td>
              <td><span class="safe {c.safety}">{data.safety[c.safety][L]}</span></td>
              <td class="mono syn"><button class="link" title={$t('ref.copy')} on:click={() => copy(c.syntax)}>{c.syntax}</button>{#if copied === c.syntax} ✓{/if}</td>
              <td>{c[L]}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
    {#if !s.rows.length}<div class="muted">{$t('ref.noMatch')}</div>{/if}
  {/each}
</div>

<style>
  .bar { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; margin-bottom: 8px; }
  .bar h2 { margin: 0; }
  h3 { margin: 18px 0 4px; font-size: 14px; color: var(--accent2); }
  p { margin: 2px 0 8px; }
  table { width: 100%; font-size: 12px; }
  td, th { text-align: left; vertical-align: top; padding: 5px 8px; border-bottom: 1px solid var(--line); }
  th { color: var(--muted); font-weight: 600; }
  .name { white-space: nowrap; }
  .syn { word-break: break-all; max-width: 380px; }
  .link { background: none; border: none; padding: 0; text-align: left; color: var(--accent); font: inherit; word-break: break-all; }
  .used { margin-left: 8px; font-size: 10px; border: 1px solid var(--accent); color: var(--accent); border-radius: 99px; padding: 0 6px; }
  .safe { font-size: 11px; border: 1px solid var(--line); border-radius: 99px; padding: 1px 8px; white-space: nowrap; }
  .safe.read { color: var(--ok); border-color: var(--ok); }
  .safe.control { color: var(--warn); border-color: var(--warn); }
  .safe.write, .safe.danger { color: var(--bad); border-color: var(--bad); }
  .sev.warn { color: var(--warn); } .sev.error { color: var(--bad); } .sev.info { color: var(--accent2); }
  .bad { color: var(--bad); }
  input[type='search'] { min-width: 220px; }
</style>
