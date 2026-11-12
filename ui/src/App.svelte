<script>
  import { onMount } from 'svelte';
  import { status, conn, replayName, connect, startWatch, stopWatch, record, listSessions, loadSession, backToLive } from './store.js';
  import { watchSet } from './panels.js';
  import SignalPath from './SignalPath.svelte';
  import LinkPanel from './LinkPanel.svelte';
  import Flags from './Flags.svelte';
  import Timeline from './Timeline.svelte';
  import Chat from './Chat.svelte';
  import ClaudeCharts from './ClaudeCharts.svelte';

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
  <span class="pill {$conn}">{$conn === 'live' ? 'daemon nối' : $conn === 'replay' ? `xem lại ${$replayName}` : 'daemon chưa chạy (rdt serve)'}</span>
  {#each Object.entries($status.targets) as [name, t]}
    {@const w = $status.watches[name]}
    <span class="pill {w?.alive ? 'live' : 'offline'}" title={t.probe_serial}>
      {name} {t.mcu}: {w ? `${w.reads} đọc${w.failures ? `, ${w.failures} lỗi` : ''}` : 'không theo dõi'}
    </span>
  {/each}
  <span class="grow"></span>
  {#if $conn !== 'replay'}
    <label>Hz <select bind:value={hz} disabled={$status.running}>{#each [2, 5, 10, 20] as h}<option value={h}>{h}</option>{/each}</select></label>
    <label title="VCP của remote; robot không có VCP dùng được"><input type="checkbox" bind:checked={vcp} disabled={$status.running} /> log remote</label>
    {#if !$status.running}
      <button class="primary" on:click={start} disabled={$conn !== 'live'}>Bắt đầu đọc</button>
    {:else}
      <button on:click={() => run(stopWatch)}>Dừng</button>
      <button class:danger={$status.recording} on:click={toggleRec}>{$status.recording ? '■ Ghi ' + $status.recording : '● Ghi phiên'}</button>
    {/if}
  {:else}
    <button on:click={backToLive}>Về trực tiếp</button>
  {/if}
  <select bind:value={pick} on:focus={reloadSessions}>
    <option value="">phiên đã ghi…</option>
    {#each sessions as s}<option value={s}>{s}</option>{/each}
  </select>
  <button on:click={open} disabled={!pick}>Mở</button>
</header>

{#if err}<div class="err">{err}</div>{/if}
{#each Object.entries($status.watches) as [name, w]}
  {#if w.fw && !w.fw.ok}<div class="err"><b>{name}</b>: {w.fw.text}</div>{/if}
{/each}
{#each $status.errors.filter((e) => !e.text.includes('FIRMWARE MISMATCH')).slice(-2) as e}<div class="err">{e.target}: {e.text}</div>{/each}

<div class="layout">
  <main>
    <div class="wide"><SignalPath /></div>
    <LinkPanel />
    <Flags />
    <div class="wide"><ClaudeCharts /></div>
    <div class="wide"><Timeline /></div>
  </main>
  <Chat />
</div>

<style>
  header { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; padding: 10px 14px; background: var(--panel); border-bottom: 1px solid var(--line); position: sticky; top: 0; z-index: 5; }
  .grow { flex: 1; }
  .pill { border: 1px solid var(--line); border-radius: 99px; padding: 2px 10px; font-size: 12px; color: var(--muted); }
  .pill.live { color: var(--ok); border-color: var(--ok); }
  .pill.replay { color: var(--accent); border-color: var(--accent); }
  label { display: flex; gap: 4px; align-items: center; }
  .err { background: color-mix(in srgb, var(--bad) 15%, transparent); color: var(--bad); padding: 6px 14px; }
  .layout { display: grid; grid-template-columns: minmax(0, 1fr) 380px; align-items: start; gap: 0 12px; padding-right: 12px; }
  @media (max-width: 1000px) { .layout { grid-template-columns: 1fr; } }
  main { display: grid; grid-template-columns: repeat(auto-fit, minmax(380px, 1fr)); gap: 12px; padding: 12px 14px; }
  .wide { grid-column: 1 / -1; }
</style>
