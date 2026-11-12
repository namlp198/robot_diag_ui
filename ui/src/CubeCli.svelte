<script>
  // Read-only STM32_Programmer_CLI runner (whitelist enforced by the daemon: rdt/cubecli.py).
  import { status } from './store.js';
  import { t, lang, localizeError } from './i18n.js';

  const CMDS = ['list', 'info', 'read32', 'ob_display'];
  let command = 'list';
  let target = 'remote';
  let address = '0x08000000';
  let size = '64';
  let line = '';
  let out = null;
  let err = '';
  let busy = false;

  $: stopped = !$status.running;
  $: needsTarget = command !== 'list';
  $: needsMem = command === 'read32';
  $: targets = Object.keys($status.targets ?? {});
  $: if (needsTarget && targets.length && !targets.includes(target)) target = targets[0];

  async function call(dry) {
    err = ''; busy = true; if (!dry) out = null;
    try {
      const r = await fetch('/api/cube/run', {
        method: 'POST', headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ command, target: needsTarget ? target : '', address: needsMem ? address : null, size: needsMem ? size : null, dry_run: dry }),
      });
      const j = await r.json();
      if (!r.ok) throw new Error(j.detail ?? r.statusText);
      line = j.command.map((a) => (/\s/.test(a) ? `"${a}"` : a)).join(' ');
      if (!dry) out = j;
    } catch (e) { err = String(e.message ?? e); }
    busy = false;
  }
</script>

<div class="card">
  <h2>{$t('cli.title')}</h2>
  <p class="muted">{$t('cli.intro')}</p>
  {#if !stopped}<div class="warn">{$t('cli.stopFirst')}</div>{/if}
  <div class="bar">
    <label>{$t('cli.command')}
      <select bind:value={command}>{#each CMDS as c}<option value={c}>{$t('cli.c.' + c)}</option>{/each}</select>
    </label>
    {#if needsTarget}
      <label>{$t('cli.target')}<select bind:value={target}>{#each targets as n}<option value={n}>{n}</option>{/each}</select></label>
    {/if}
    {#if needsMem}
      <label>{$t('cli.address')}<input bind:value={address} class="mono" size="12" /></label>
      <label>{$t('cli.size')}<input bind:value={size} class="mono" size="6" /></label>
    {/if}
    <button on:click={() => call(true)} disabled={busy}>{$t('cli.preview')}</button>
    <button class="primary" on:click={() => call(false)} disabled={busy || !stopped}>{$t('cli.run')}</button>
  </div>
  <div class="muted small">{$t('cli.hint.' + command)}</div>
  {#if err}<div class="bad">{localizeError(err, $lang)}</div>{/if}
  {#if line}<div class="small muted">{$t('cli.exact')}</div><pre class="cmd">{line}</pre>{/if}
  {#if out}<div class="small muted">{$t('cli.output', { rc: out.returncode })}</div><pre class="out">{out.output}</pre>{/if}
</div>

<style>
  .bar { display: flex; gap: 12px; align-items: end; flex-wrap: wrap; margin: 8px 0; }
  label { display: flex; flex-direction: column; gap: 2px; font-size: 11px; color: var(--muted); }
  .small { font-size: 12px; }
  .warn { color: var(--warn); margin-bottom: 6px; }
  .bad { color: var(--bad); margin-top: 6px; }
  pre { margin: 4px 0 8px; padding: 8px; background: var(--panel2); border: 1px solid var(--line); border-radius: var(--radius); white-space: pre-wrap; word-break: break-all; overflow: auto; }
  .out { max-height: 420px; }
</style>
