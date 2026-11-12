<script>
  import { onMount } from 'svelte';
  import { status, conn, replayName, connect, startWatch, stopWatch, record, listSessions, loadSession, backToLive } from './store.js';
  import { watchSet } from './panels.js';
  import SignalPath from './SignalPath.svelte';
  import LinkPanel from './LinkPanel.svelte';
  import Flags from './Flags.svelte';
  import Timeline from './Timeline.svelte';
  import Chat from './Chat.svelte';
  import Findings from './Findings.svelte';
  import Sweep from './Sweep.svelte';
  import Flash from './Flash.svelte';
  import ClaudeCharts from './ClaudeCharts.svelte';
  import CubeCli from './CubeCli.svelte';
  import Reference from './Reference.svelte';
  import Frames from './Frames.svelte';
  import CanFrames from './CanFrames.svelte';
  import LiveExpr from './LiveExpr.svelte';
  import Settings from './Settings.svelte';
  import { t, theme, lang, toggleTheme, toggleLang, localizeError } from './i18n.js';

  let view = 'dashboard'; // dashboard | cli | reference (the dashboard stays mounted so its charts keep their state)
  let hz = 10;
  let vcp = true;
  let err = '';
  let sessions = [];
  let pick = '';

  onMount(() => {
    connect();
    reloadSessions();
  });
  async function reloadSessions() {
    try { sessions = (await listSessions()).reverse(); } catch { sessions = []; }
  }
  async function run(fn) {
    err = '';
    try { await fn(); } catch (e) { err = String(e.message ?? e); }
  }
  const start = () => run(() => startWatch(watchSet(), hz, vcp ? ['remote'] : []));
  const toggleRec = () => run(async () => { await record(!$status.recording, 'ui'); await reloadSessions(); });
  const open = () => run(() => loadSession(pick));
</script>

<header>
  <b>robot_diag</b>
  <span class="pill {$conn}">{$conn === 'live' ? $t('conn.live') : $conn === 'replay' ? $t('conn.replay', { name: $replayName }) : $t('conn.offline')}</span>
  {#each Object.entries($status.targets) as [name, tg]}
    {@const w = $status.watches[name]}
    <span class="pill {w?.alive ? 'live' : 'offline'}" title={tg.probe_serial}>
      {name} {tg.mcu}: {w ? `${$t('target.reads', { n: w.reads })}${w.failures ? $t('target.fail', { n: w.failures }) : ''}` : $t('target.idle')}
    </span>
  {/each}
  <span class="grow"></span>
  {#if $conn !== 'replay'}
    <label>Hz <select bind:value={hz} disabled={$status.running}>{#each [2, 5, 10, 20] as h}<option value={h}>{h}</option>{/each}</select></label>
    <label title={$t('hdr.vcpTip')}><input type="checkbox" bind:checked={vcp} disabled={$status.running} /> {$t('hdr.vcp')}</label>
    {#if !$status.running}
      <button class="primary" on:click={start} disabled={$conn !== 'live'}>{$t('hdr.start')}</button>
    {:else}
      <button on:click={() => run(stopWatch)}>{$t('hdr.stop')}</button>
      <button class:danger={$status.recording} on:click={toggleRec}>{$status.recording ? $t('hdr.recording', { name: $status.recording }) : $t('hdr.rec')}</button>
    {/if}
  {:else}
    <button on:click={backToLive}>{$t('hdr.live')}</button>
  {/if}
  <select bind:value={pick} on:focus={reloadSessions}>
    <option value="">{$t('hdr.sessions')}</option>
    {#each sessions as s}<option value={s}>{s}</option>{/each}
  </select>
  <button on:click={open} disabled={!pick}>{$t('hdr.open')}</button>
  <button on:click={toggleLang} title={$t('hdr.langTip')}>{$lang === 'vi' ? 'EN' : 'VI'}</button>
  <button on:click={toggleTheme} title={$t('hdr.themeTip')} aria-label={$t('hdr.themeTip')}>{$theme === 'dark' ? '☾' : '☀'}</button>
</header>
<nav>
  {#each ['dashboard', 'frames', 'expr', 'cli', 'reference', 'settings'] as v}
    <button class:primary={view === v} on:click={() => (view = v)}>{$t('nav.' + v)}</button>
  {/each}
</nav>

{#if err}<div class="err">{localizeError(err, $lang)}</div>{/if}
{#each Object.entries($status.watches) as [name, w]}
  {#if w.fw && !w.fw.ok}<div class="err"><b>{name}</b>: {localizeError(w.fw.text, $lang)}</div>{/if}
{/each}
{#each $status.errors.filter((e) => !e.text.includes('FIRMWARE MISMATCH')).slice(-2) as e}<div class="err">{e.target}: {localizeError(e.text, $lang)}</div>{/each}

<div class="layout">
  <main class:hide={view !== 'dashboard'}>
    <div class="wide"><SignalPath /></div>
    <div class="wide"><Findings /></div>
    <LinkPanel />
    <Flags />
    <div class="wide"><ClaudeCharts /></div>
    <div class="wide"><Sweep /></div>
    <div class="wide"><Timeline /></div>
    <div class="wide"><Flash /></div>
  </main>
  {#if view === 'frames'}<main class="single stack"><Frames /><CanFrames /></main>{/if}
  {#if view === 'expr'}<main class="single"><LiveExpr /></main>{/if}
  {#if view === 'cli'}<main class="single"><CubeCli /></main>{/if}
  {#if view === 'reference'}<main class="single"><Reference /></main>{/if}
  {#if view === 'settings'}<main class="single"><Settings /></main>{/if}
  <Chat />
</div>

<style>
  header { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; padding: 10px 14px; background: var(--panel); border-bottom: 1px solid var(--line); position: sticky; top: 0; z-index: 5; box-shadow: var(--glow); }
  .grow { flex: 1; }
  .pill { border: 1px solid var(--line); border-radius: 99px; padding: 2px 10px; font-size: 12px; color: var(--muted); }
  .pill.live { color: var(--ok); border-color: var(--ok); }
  .pill.replay { color: var(--accent); border-color: var(--accent); }
  label { display: flex; gap: 4px; align-items: center; }
  .err { background: color-mix(in srgb, var(--bad) 15%, transparent); color: var(--bad); padding: 6px 14px; }
  .pill.offline { color: var(--muted); }
  .layout { display: grid; grid-template-columns: minmax(0, 1fr) 380px; align-items: start; gap: 0 12px; padding-right: 12px; }
  @media (max-width: 1000px) { .layout { grid-template-columns: 1fr; } }
  main { display: grid; grid-template-columns: repeat(auto-fit, minmax(380px, 1fr)); gap: 12px; padding: 12px 14px; }
  .wide { grid-column: 1 / -1; }
  .hide { display: none; }
  .single { display: block; }
  .single.stack { display: flex; flex-direction: column; gap: 12px; }
  nav { display: flex; gap: 6px; padding: 6px 14px; border-bottom: 1px solid var(--line); }
  header b { color: var(--accent); text-shadow: var(--glow-text); letter-spacing: .06em; }
</style>
