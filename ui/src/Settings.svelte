<script>
  // Chat model / effort / cost cap, the register-read policy, and appearance. Stored by the daemon (rdt/settings.py).
  import { onMount } from 'svelte';
  import { t, lang, theme } from './i18n.js';

  let models = [];
  let efforts = [];
  let s = { model: '', effort: null, max_usd: 2, allow_peripheral_reads: false };
  let customModel = false;
  let info = null;
  let msg = '';
  let err = '';
  let busy = false;

  async function load() {
    try {
      const j = await (await fetch('/api/settings')).json();
      models = j.models; efforts = j.efforts; s = { ...j.settings, effort: j.settings.effort ?? '' };
      customModel = !models.includes(s.model);
    } catch (e) { err = String(e.message ?? e); }
    try { info = await (await fetch('/api/chat/info')).json(); } catch { info = null; }
  }
  onMount(load);

  async function save(changes) {
    err = ''; msg = ''; busy = true;
    try {
      const r = await fetch('/api/settings', { method: 'PUT', headers: { 'content-type': 'application/json' }, body: JSON.stringify(changes) });
      const j = await r.json();
      if (!r.ok) throw new Error(j.detail);
      s = { ...j.settings, effort: j.settings.effort ?? '' };
      msg = $t(j.chat_restarted ? 'set.savedRestart' : 'set.saved');
    } catch (e) { err = String(e.message ?? e); }
    busy = false;
  }
  const saveChat = () => save({ model: s.model, effort: s.effort || null, max_usd: Number(s.max_usd) });
  $: status = !info ? 'set.statusUnknown' : !info.sdk ? 'set.statusNoSdk' : info.logged_in === false ? 'set.statusLogin' : info.logged_in ? 'set.statusReady' : 'set.statusUnknown';
</script>

<div class="card">
  <h2>{$t('set.title')}</h2>

  <h3>{$t('set.chat')}</h3>
  <p class="muted small">{$t('set.engineNote')}</p>
  <div class="grid">
    <label>{$t('set.model')}
      <select value={customModel ? '__custom' : s.model} on:change={(e) => { customModel = e.target.value === '__custom'; if (!customModel) s.model = e.target.value; }}>
        {#each models as m}<option value={m}>{m}</option>{/each}
        <option value="__custom">{$t('set.modelCustom')}</option>
      </select>
      {#if customModel}<input bind:value={s.model} class="mono" placeholder="claude-…" />{/if}
    </label>
    <label>{$t('set.effort')}
      <select bind:value={s.effort}><option value="">{$t('set.effortDefault')}</option>{#each efforts as e}<option value={e}>{e}</option>{/each}</select>
    </label>
    <label>{$t('set.budget')}<input type="number" step="0.1" min="0.05" max="100" bind:value={s.max_usd} class="num" /></label>
  </div>
  <div class="row"><button class="primary" on:click={saveChat} disabled={busy}>{$t('set.save')}</button>
    <span class="muted">{$t('set.status')}: <b class:ok={status === 'set.statusReady'} class:bad={status === 'set.statusLogin' || status === 'set.statusNoSdk'}>{$t(status)}</b></span></div>
  {#if status === 'set.statusLogin'}<pre class="mono">{$t('chat.loginTip').replace(/^[^:]*: /, '')}</pre>{/if}

  <h3>{$t('set.reading')}</h3>
  <label class="check"><input type="checkbox" checked={s.allow_peripheral_reads} on:change={(e) => save({ allow_peripheral_reads: e.target.checked })} /> {$t('set.periph')}</label>
  <p class="warn small">{$t('set.periphWarn')}</p>

  <h3>{$t('set.appearance')}</h3>
  <div class="grid">
    <label>{$t('set.theme')}
      <select bind:value={$theme}><option value="dark">{$t('set.themeDark')}</option><option value="light">{$t('set.themeLight')}</option></select>
    </label>
    <label>{$t('set.lang')}
      <select bind:value={$lang}><option value="vi">Tiếng Việt</option><option value="en">English</option></select>
    </label>
  </div>

  {#if msg}<div class="ok">{msg}</div>{/if}
  {#if err}<div class="bad">{err}</div>{/if}
</div>

<style>
  h3 { margin: 16px 0 4px; font-size: 13px; color: var(--accent2); }
  .grid { display: flex; flex-wrap: wrap; gap: 16px; margin: 8px 0; }
  label { display: flex; flex-direction: column; gap: 4px; font-size: 11px; color: var(--muted); }
  .check { flex-direction: row; align-items: center; gap: 8px; font-size: 13px; color: var(--text); }
  .row { display: flex; gap: 16px; align-items: center; margin-top: 6px; }
  .num { width: 100px; }
  .small { font-size: 12px; margin: 2px 0 6px; }
  .ok { color: var(--ok); } .bad { color: var(--bad); } .warn { color: var(--warn); }
  pre { background: var(--panel2); border: 1px solid var(--line); padding: 6px 8px; border-radius: var(--radius); overflow: auto; }
</style>
