<script>
  import { conn, replayName } from './store.js';
  let res = null;
  let err = '';
  async function load() {
    err = '';
    res = null;
    const url = $replayName ? `/api/sessions/${encodeURIComponent($replayName)}/sweep` : '/api/sweep';
    try {
      const r = await fetch(url);
      const j = await r.json();
      if (!r.ok) err = j.detail ?? r.statusText;
      else if (j.error) err = j.error;
      else res = j;
    } catch (e) {
      err = String(e);
    }
  }
  const HEAD = 'gap_ms,seconds,sent,control_rx,accepted,lost,loss_pct,crc_errors';
  $: csv = res
    ? 'data:text/csv;charset=utf-8,' +
      encodeURIComponent([HEAD, ...res.rows.map((r) => [r.gap_ms, r.seconds, r.sent ?? '', r.control_rx, r.accepted, r.lost, r.loss_pct, r.crc_errors].join(','))].join('\n'))
    : '';
</script>

<div class="card">
  <h2>Sweep Phase 0 (mất gói theo tốc độ gửi)</h2>
  <div class="bar">
    <button on:click={load} disabled={$conn === 'offline'}>Tính từ {$replayName ? 'phiên đang xem' : 'dữ liệu trực tiếp'}</button>
    {#if res}<a href={csv} download="link_sweep.csv">Tải CSV</a>{/if}
    <span class="muted">Remote phải chạy bản sweep và được reset sau khi bắt đầu đọc. rdt chỉ quan sát, không điều khiển remote.</span>
  </div>
  {#if err}<div class="muted">{err}</div>{/if}
  {#if res}
    <table class="mono">
      <thead><tr><th>gap ms</th><th>giây</th><th>gửi</th><th>robot rx</th><th>accepted</th><th>lost</th><th>loss %</th><th>crc</th></tr></thead>
      <tbody>
        {#each res.rows as r}
          <tr class:bad={r.loss_pct >= 5} class:warn={r.loss_pct >= 1 && r.loss_pct < 5}>
            <td>{r.gap_ms}</td><td>{r.seconds}</td><td>{r.sent ?? '—'}</td><td>{r.control_rx}</td><td>{r.accepted}</td>
            <td>{r.lost}{r.restarts_removed ? ` (−${r.restarts_removed} restart)` : ''}</td><td>{r.loss_pct}</td><td>{r.crc_errors}</td>
          </tr>
        {/each}
      </tbody>
    </table>
    <p class="muted small">Ranh giới bước lấy từ {res.source === 'vcp' ? 'log VCP' : 'biến sweep_step'} theo đồng hồ máy tính: sai số một chu kỳ poll.</p>
  {/if}
</div>

<style>
  .bar { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin-bottom: 8px; }
  table { border-collapse: collapse; width: 100%; font-size: 12px; }
  th, td { text-align: right; padding: 3px 8px; border-bottom: 1px solid var(--line); }
  tr.warn td { background: color-mix(in srgb, #e08a00 14%, transparent); }
  tr.bad td { background: color-mix(in srgb, var(--bad) 16%, transparent); }
  .small { font-size: 12px; }
</style>
