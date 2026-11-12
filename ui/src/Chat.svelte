<script>
  import { afterUpdate } from 'svelte';
  import { chat, conn, sendChat, stopChat, resetChat, series } from './store.js';
  import { RATES } from './panels.js';

  let text = '';
  let err = '';
  let box;
  let open = {};

  afterUpdate(() => { if (box) box.scrollTop = box.scrollHeight; });

  // What the user is looking at: sent with the question so Claude need not be told numbers in the prompt.
  function view() {
    const s = $series;
    const win = {};
    for (const [t, d] of Object.entries(s)) if (d.t.length) win[t] = [d.t[0], d.t[d.t.length - 1]];
    return { mode: $conn, window_s: win, rate_series: Object.fromEntries(Object.entries(RATES).map(([t, l]) => [t, l.map((r) => r.path)])) };
  }
  async function send() {
    const q = text.trim();
    if (!q || $chat.busy) return;
    err = '';
    text = '';
    try { await sendChat(q, view()); } catch (e) { err = String(e.message ?? e); }
  }
  const key = (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } };
  const short = (o) => JSON.stringify(o).slice(0, 160);
</script>

<aside class="card chat">
  <div class="top">
    <h2>Chat Claude</h2>
    <span class="muted mono">{$chat.model ?? 'chưa kết nối'}{$chat.cost ? ` · $${$chat.cost.toFixed(3)}` : ''}</span>
    <button on:click={resetChat} title="Cuộc trò chuyện mới">Mới</button>
  </div>
  <div class="msgs" bind:this={box}>
    {#each $chat.items as m}
      {#if m.k === 'user'}
        <div class="m user">{m.text}</div>
      {:else if m.k === 'assistant'}
        <div class="m bot">{m.text}{#if m.streaming}<span class="cursor">▍</span>{/if}</div>
        {#if m.text.includes('Not logged in')}
          <div class="m err">Chat dùng bản Claude Code đi kèm SDK, chưa đăng nhập. Chạy một lần trong terminal rồi hỏi lại:<br /><code>.venv\Lib\site-packages\claude_agent_sdk\_bundled\claude.exe auth login</code></div>
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
      <div class="muted">Hỏi về dữ liệu đang xem, ví dụ: "link có mất gói không?". Claude chỉ có tool đọc và hiển thị; không ghi, không reset, không nạp.</div>
    {/each}
  </div>
  {#if err}<div class="err small">{err}</div>{/if}
  <div class="input">
    <textarea rows="2" bind:value={text} on:keydown={key} placeholder="Hỏi Claude… (Enter gửi)" disabled={$chat.busy}></textarea>
    {#if $chat.busy}<button class="danger" on:click={stopChat}>Dừng</button>{:else}<button class="primary" on:click={send} disabled={!text.trim()}>Gửi</button>{/if}
  </div>
</aside>

<style>
  .chat { display: flex; flex-direction: column; height: calc(100vh - 80px); position: sticky; top: 64px; }
  .top { display: flex; gap: 8px; align-items: center; }
  .top h2 { margin: 0; flex: 1; }
  .msgs { flex: 1; overflow: auto; display: flex; flex-direction: column; gap: 6px; margin: 8px 0; }
  .m { padding: 6px 9px; border-radius: 8px; white-space: pre-wrap; word-break: break-word; font-size: 13px; }
  .user { background: color-mix(in srgb, var(--accent) 18%, transparent); align-self: flex-end; max-width: 90%; }
  .bot { background: var(--bg); }
  .tool { text-align: left; display: block; width: 100%; border: 1px solid var(--line); background: var(--panel); font-size: 12px; }
  .tool.error { border-color: var(--bad); }
  .tool.running { border-style: dashed; }
  .tool pre { margin: 6px 0 0; max-height: 160px; overflow: auto; white-space: pre-wrap; }
  .err { background: color-mix(in srgb, var(--bad) 15%, transparent); color: var(--bad); }
  .small { font-size: 12px; padding: 4px 8px; margin-bottom: 4px; border-radius: 6px; }
  .input { display: flex; gap: 6px; }
  textarea { flex: 1; resize: none; font: inherit; color: inherit; background: var(--panel); border: 1px solid var(--line); border-radius: 6px; padding: 6px; }
  .cursor { opacity: .6; }
</style>
