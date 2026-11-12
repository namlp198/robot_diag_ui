<script>
  import { STAGES, STALE_S } from './panels.js';
  import { latest } from './store.js';

  // green = counter still moving, red = stopped for STALE_S, grey = no variable / not read yet
  function view(s, L) {
    if (!s.target) return { cls: 'idle', value: s.note, age: null };
    const T = L[s.target] ?? {};
    const c = s.counter ? T[s.counter] : null;
    const val = s.value ? T[s.value]?.v : undefined;
    const flag = s.flag ? T[s.flag]?.v : undefined;
    if (s.counter && !c) return { cls: 'idle', value: '—', age: null };
    const age = c ? c.t - c.changed : null;
    const cls = c ? (age > STALE_S ? 'bad' : 'ok') : val === undefined && flag === undefined ? 'idle' : 'ok';
    const bits = [];
    if (val !== undefined) bits.push(String(val));
    if (flag !== undefined) bits.push(flag ? 'armed' : 'disarmed');
    if (c) bits.push(`#${c.v}`);
    return { cls, value: bits.join('  ') || '—', age };
  }
  $: rows = STAGES.map((s) => ({ s, ...view(s, $latest) }));
</script>

<div class="card">
  <h2>1. Đường đi tín hiệu</h2>
  <div class="chain">
    {#each rows as r, i}
      <div class="stage {r.cls}">
        <div class="label">{r.s.label}</div>
        <div class="val mono">{r.value}</div>
        <div class="age muted">{r.age === null ? ' ' : r.age < 0.05 ? 'đang đổi' : `đứng ${r.age.toFixed(1)} s`}</div>
      </div>
      {#if i < rows.length - 1}<div class="arrow muted">→</div>{/if}
    {/each}
  </div>
  <p class="muted note">Đỏ: bộ đếm của chặng không đổi quá {STALE_S} s. Xám: chặng chưa có biến để đọc.</p>
</div>

<style>
  .chain { display: flex; flex-wrap: wrap; align-items: stretch; gap: 4px; }
  .stage { flex: 1 1 120px; border: 2px solid var(--idle); border-radius: 8px; padding: 6px 8px; min-width: 110px; }
  .stage.ok { border-color: var(--ok); }
  .stage.bad { border-color: var(--bad); background: color-mix(in srgb, var(--bad) 10%, transparent); }
  .label { font-size: 12px; color: var(--muted); }
  .val { font-size: 15px; margin: 2px 0; word-break: break-all; }
  .age { font-size: 11px; min-height: 14px; }
  .arrow { align-self: center; }
  .note { margin: 8px 0 0; font-size: 12px; }
</style>
