<script>
  import { onMount } from 'svelte';
  import { status } from './store.js';
  import { t } from './i18n.js';

  let cands = {};
  let target = 'remote';
  let image = '';
  let plan = null;
  let err = '';
  let typed = '';
  let safe = false;
  let result = null;
  let busy = false;

  onMount(async () => {
    try { cands = await (await fetch('/api/flash/candidates')).json(); } catch { cands = {}; }
  });
  $: list = cands[target] ?? [];
  $: if (!list.includes(image)) image = list[0] ?? '';
  $: stopped = !$status.running;

  async function call(path, extra = {}) {
    const r = await fetch(path, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ target, image, ...extra }) });
    const j = await r.json();
    if (!r.ok) throw new Error(j.detail ?? r.statusText);
    return j;
  }
  async function dry() {
    err = ''; result = null; plan = null; typed = ''; safe = false; busy = true;
    try { plan = await call('/api/flash/plan'); } catch (e) { err = String(e.message ?? e); }
    busy = false;
  }
  async function go() {
    err = ''; busy = true;
    try { result = await call('/api/flash/run', { confirm: typed, motors_safe: safe }); plan = null; } catch (e) { err = String(e.message ?? e); }
    busy = false;
  }
  const name = (p) => p.split(/[\\/]/).slice(-3).join('/');
</script>

<div class="card">
  <h2>{$t('flash.title')}</h2>
  <p class="muted small">{$t('flash.warn')}</p>
  <div class="bar">
    <select bind:value={target}>{#each Object.keys(cands) as t}<option value={t}>{t}</option>{/each}</select>
    <select bind:value={image}>{#each list as f}<option value={f}>{name(f)}</option>{/each}</select>
    <button on:click={dry} disabled={!stopped || !image || busy}>{$t('flash.dry')}</button>
    {#if !stopped}<span class="muted">{$t('flash.stopFirst')}</span>{/if}
  </div>
  {#if err}<div class="bad">{err}</div>{/if}
  {#if plan}
    {#each plan.checks as c}<div class={c.ok ? 'ok' : 'bad'}>{c.ok ? '✓' : '✕'} {c.name}: {c.detail}</div>{/each}
    {#if plan.already_flashed}<div class="muted">{$t('flash.already')}</div>{/if}
    <div class="muted mono small">{plan.command.join(' ')}</div>
    {#if plan.ok}
      <div class="confirm">
        {#if plan.needs_motors_safe}<label><input type="checkbox" bind:checked={safe} /> {$t('flash.safe')}</label>{/if}
        <div>{$t('flash.typeExactly')} <code>{plan.confirm}</code></div>
        <input bind:value={typed} placeholder={plan.confirm} />
        <button class="danger" on:click={go} disabled={busy || typed !== plan.confirm || (plan.needs_motors_safe && !safe)}>{$t('flash.go')}</button>
      </div>
    {:else}<div class="bad">{$t('flash.rejected')}</div>{/if}
  {/if}
  {#if result}
    <div class={result.programmed ? 'ok' : 'bad'}>{$t(result.programmed ? 'flash.done' : 'flash.failed')} {$t('flash.after', { rc: result.returncode, v: $t(result.verified_after === null ? 'flash.vNone' : result.verified_after ? 'flash.vOk' : 'flash.vBad') })}</div>
    <pre class="small">{result.output_tail}</pre>
  {/if}
</div>

<style>
  .bar, .confirm { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin: 6px 0; }
  .ok { color: var(--ok); font-size: 13px; }
  .bad { color: var(--bad); font-size: 13px; }
  .small { font-size: 12px; }
  pre { max-height: 160px; overflow: auto; white-space: pre-wrap; }
  input:not([type=checkbox]) { min-width: 220px; }
</style>
