<script>
  import { afterUpdate, onMount } from 'svelte';
  import { chat, conn, sendChat, stopChat, resetChat, series, showTools } from './store.js';
  import { RATES } from './panels.js';
  import { t, lang, localizeError } from './i18n.js';
  import { prepareFile, MAX_FILES } from './attach.js';
  import ChatHistory from './ChatHistory.svelte';

  // Is the chat usable? (SDK installed, bundled Claude Code logged in) - not which model: that is in Settings.
  let state = 'unknown';
  async function check() {
    try {
      const j = await (await fetch('/api/chat/info')).json();
      state = !j.sdk ? 'nosdk' : j.logged_in === false ? 'login' : j.logged_in ? 'ready' : 'unknown';
    } catch { state = 'unknown'; }
  }
  onMount(check);
  let wasBusy = false;
  $: { if (wasBusy && !$chat.busy) check(); wasBusy = $chat.busy; }

  let text = '';
  let err = '';
  let box;
  let open = {};
  let pending = []; // files chosen for the next message: { name, kind, size, data, preview }
  let drag = false;
  let showHistory = false;
  let fileInput;

  afterUpdate(() => { if (box) box.scrollTop = box.scrollHeight; });

  // What the user is looking at: sent with the question so Claude need not be told numbers in the prompt.
  function view() {
    const s = $series;
    const win = {};
    for (const [t, d] of Object.entries(s)) if (d.t.length) win[t] = [d.t[0], d.t[d.t.length - 1]];
    return { mode: $conn, window_s: win, rate_series: Object.fromEntries(Object.entries(RATES).map(([t, l]) => [t, l.map((r) => r.path)])) };
  }

  async function addFiles(list) {
    err = '';
    for (const f of [...list]) {
      if (pending.length >= MAX_FILES) { err = $t('chat.tooMany', { n: MAX_FILES }); break; }
      const r = await prepareFile(f);
      if (r.error) err = $t(r.error, { f: r.name });
      else pending = [...pending, r.item];
    }
  }
  const removeFile = (i) => { const f = pending[i]; if (f?.preview) URL.revokeObjectURL(f.preview); pending = pending.filter((_, j) => j !== i); };
  function onPaste(e) {
    const files = [...(e.clipboardData?.files ?? [])];
    if (files.length) { e.preventDefault(); addFiles(files); }
  }
  function onDrop(e) {
    e.preventDefault(); drag = false;
    if (e.dataTransfer?.files?.length) addFiles(e.dataTransfer.files);
  }

  async function send() {
    const q = text.trim();
    if ((!q && !pending.length) || $chat.busy) return;
    err = '';
    const files = pending;
    try {
      await sendChat(q, view(), files);
      text = '';
      files.forEach((f) => f.preview && URL.revokeObjectURL(f.preview));
      pending = [];
    } catch (e) { err = String(e.message ?? e); }   // the message and files stay in the box so nothing is lost
  }
  const key = (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } };
  const short = (o) => JSON.stringify(o).slice(0, 160);
  const fileUrl = (m, a) => (m.chatId && a.file ? `/api/chats/${m.chatId}/files/${encodeURIComponent(a.file)}` : null);
  const kb = (n) => (n >= 1048576 ? (n / 1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(n / 1024)) + ' KB');
  $: visible = $chat.items.filter((m) => $showTools || m.k !== 'tool');
</script>

<aside class="card chat" class:drag on:dragover|preventDefault={() => (drag = true)} on:dragleave={() => (drag = false)} on:drop={onDrop}>
  <div class="top">
    <h2>{$t('chat.title')}</h2>
    <span class="pill {state}" title={state === 'login' ? $t('chat.loginTip') : ''}>{$t('chat.' + (state === 'ready' ? 'ready' : state === 'login' ? 'needLogin' : state === 'nosdk' ? 'noSdk' : 'unknown'))}</span>
    {#if $chat.cost}<span class="muted mono">${$chat.cost.toFixed(3)}</span>{/if}
    <button class:primary={showHistory} on:click={() => (showHistory = !showHistory)} title={$t('chat.history')}>🕘</button>
    <button class:primary={$showTools} on:click={() => showTools.update((v) => !v)} title={$t('chat.toolsTip')}>⚙</button>
    <button on:click={resetChat} title={$t('chat.newTip')}>{$t('chat.new')}</button>
  </div>
  {#if showHistory}<ChatHistory on:opened={() => (showHistory = false)} />{/if}
  <div class="msgs" bind:this={box}>
    {#each visible as m}
      {#if m.k === 'user'}
        <div class="m user">
          {#if m.attachments?.length}
            <div class="atts">
              {#each m.attachments as a}
                {@const u = fileUrl(m, a)}
                {#if a.kind === 'image' && u}<a href={u} target="_blank" rel="noopener"><img src={u} alt={a.name} class="thumb" /></a>
                {:else}<span class="chip" title="{a.name} · {kb(a.size)}{a.truncated ? ' · ' + $t('chat.cut') : ''}">{a.kind === 'pdf' ? '📄' : '📎'} {a.name}</span>{/if}
              {/each}
            </div>
          {/if}
          {m.text}
        </div>
      {:else if m.k === 'assistant'}
        <div class="m bot">{m.text}{#if m.streaming}<span class="cursor">▍</span>{/if}</div>
        {#if m.text.includes('Not logged in')}
          <div class="m err">{$t('chat.login')}<br /><code>.venv\Lib\site-packages\claude_agent_sdk\_bundled\claude.exe auth login</code></div>
        {/if}
      {:else if m.k === 'tool'}
        <button class="m tool {m.state}" on:click={() => (open[m.id] = !open[m.id])}>
          <span class="mono">{m.state === 'running' ? '…' : m.state === 'error' ? '✕' : '✓'} {m.name}</span>
          <span class="muted mono">{short(m.input)}</span>
          {#if open[m.id] && m.result}<pre>{m.result}</pre>{/if}
        </button>
      {:else if m.k === 'error'}
        <div class="m err">{m.text}</div>
      {/if}
    {:else}
      <div class="muted">{$t('chat.empty')}</div>
    {/each}
  </div>
  {#if err}<div class="err small">{localizeError(err, $lang)}</div>{/if}
  {#if pending.length}
    <div class="pending">
      {#each pending as f, i}
        <span class="pchip">
          {#if f.preview}<img src={f.preview} alt={f.name} class="pthumb" />{:else}<span>{f.kind === 'pdf' ? '📄' : '📎'}</span>{/if}
          <span class="pn" title={f.name}>{f.name}</span><span class="muted small">{kb(f.size)}</span>
          <button class="x" on:click={() => removeFile(i)} title={$t('chat.remove')}>✕</button>
        </span>
      {/each}
    </div>
  {/if}
  <div class="input">
    <input type="file" multiple hidden bind:this={fileInput} on:change={(e) => { addFiles(e.target.files); e.target.value = ''; }} />
    <button on:click={() => fileInput.click()} disabled={$chat.busy} title={$t('chat.attachTip')} aria-label={$t('chat.attachTip')}>📎</button>
    <textarea rows="2" bind:value={text} on:keydown={key} on:paste={onPaste} placeholder={$t('chat.placeholder')} disabled={$chat.busy}></textarea>
    {#if $chat.busy}<button class="danger" on:click={stopChat}>{$t('chat.stop')}</button>{:else}<button class="primary" on:click={send} disabled={!text.trim() && !pending.length}>{$t('chat.send')}</button>{/if}
  </div>
  {#if drag}<div class="drop">{$t('chat.drop')}</div>{/if}
</aside>

<style>
  .chat { display: flex; flex-direction: column; height: calc(100vh - 80px); position: sticky; top: 64px; }
  .chat.drag { outline: 2px dashed var(--accent); }
  .drop { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; background: color-mix(in srgb, var(--bg) 80%, transparent); color: var(--accent); font-size: 15px; pointer-events: none; }
  .top { display: flex; gap: 6px; align-items: center; }
  .top h2 { margin: 0; flex: 1; }
  .top button { padding: 2px 8px; }
  .msgs { flex: 1; overflow: auto; display: flex; flex-direction: column; gap: 6px; margin: 8px 0; }
  .m { padding: 6px 9px; border-radius: 8px; white-space: pre-wrap; word-break: break-word; font-size: 13px; }
  .user { background: color-mix(in srgb, var(--accent) 18%, transparent); align-self: flex-end; max-width: 90%; }
  .atts { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 4px; }
  .thumb { max-width: 150px; max-height: 110px; border-radius: 4px; border: 1px solid var(--line); display: block; }
  .chip { font-size: 11px; border: 1px solid var(--line); border-radius: 99px; padding: 1px 8px; background: var(--panel); white-space: nowrap; align-self: center; }
  .bot { background: var(--bg); }
  .tool { text-align: left; display: block; width: 100%; border: 1px solid var(--line); background: var(--panel); font-size: 12px; }
  .tool.error { border-color: var(--bad); }
  .tool.running { border-style: dashed; }
  .tool pre { margin: 6px 0 0; max-height: 160px; overflow: auto; white-space: pre-wrap; }
  .err { background: color-mix(in srgb, var(--bad) 15%, transparent); color: var(--bad); }
  .small { font-size: 12px; padding: 4px 8px; margin-bottom: 4px; border-radius: 6px; }
  .pending { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 6px; }
  .pchip { display: flex; align-items: center; gap: 5px; border: 1px solid var(--line); border-radius: 6px; padding: 2px 5px; background: var(--panel2); font-size: 12px; max-width: 100%; }
  .pthumb { width: 28px; height: 28px; object-fit: cover; border-radius: 3px; }
  .pn { max-width: 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .x { padding: 0 5px; font-size: 11px; }
  .input { display: flex; gap: 6px; }
  textarea { flex: 1; resize: none; font: inherit; color: inherit; background: var(--panel); border: 1px solid var(--line); border-radius: 6px; padding: 6px; }
  .cursor { opacity: .6; }
  .pill { font-size: 11px; border: 1px solid var(--line); border-radius: 99px; padding: 0 8px; color: var(--muted); }
  .pill.ready { color: var(--ok); border-color: var(--ok); }
  .pill.login, .pill.nosdk { color: var(--bad); border-color: var(--bad); }
</style>
