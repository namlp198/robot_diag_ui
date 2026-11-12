<script>
  import { findings, highlights, sendChat, chat } from './store.js';
  const ORDER = { error: 0, warn: 1, info: 2 };
  $: list = [...$findings].sort((a, b) => ORDER[a.severity] - ORDER[b.severity] || a.t0 - b.t0);
  const ask = (f) => sendChat(`Giải thích phát hiện "${f.title}" (${f.target}, t=${f.t0.toFixed(1)}–${f.t1.toFixed(1)} s) và kiểm tra bằng số liệu.`, null).catch(() => {});
  const mark = (f) => highlights.update((a) => [...a, { t0: f.t0, t1: Math.max(f.t1, f.t0 + 0.2), label: f.title }]);
</script>

<div class="card">
  <h2>Chẩn đoán tự động</h2>
  {#each list as f}
    <div class="f {f.severity}">
      <div class="head"><b>{f.title}</b><span class="muted mono">{f.target} · {f.t0.toFixed(1)}–{f.t1.toFixed(1)} s</span></div>
      <div>{f.detail}</div>
      {#if f.checks?.length}<ul class="muted">{#each f.checks as c}<li>{c}</li>{/each}</ul>{/if}
      <div class="acts"><button on:click={() => mark(f)}>Đánh dấu trên đồ thị</button><button on:click={() => ask(f)} disabled={$chat.busy}>Hỏi Claude</button></div>
    </div>
  {:else}
    <div class="muted">Chưa có phát hiện nào. Quy tắc lấy từ bảng triệu chứng của debug_guide và task_history; biến thiếu thì quy tắc bị bỏ qua, không đoán.</div>
  {/each}
</div>

<style>
  .f { border-left: 4px solid var(--idle); padding: 6px 10px; margin-bottom: 8px; background: var(--bg); border-radius: 4px; }
  .f.error { border-color: var(--bad); }
  .f.warn { border-color: #e08a00; }
  .f.info { border-color: var(--accent); }
  .head { display: flex; gap: 10px; justify-content: space-between; flex-wrap: wrap; }
  ul { margin: 4px 0; padding-left: 18px; font-size: 12px; }
  .acts { display: flex; gap: 6px; }
  .acts button { font-size: 12px; padding: 2px 8px; }
</style>
