// counter -> per-second rate over ~1 s, so lost/crc/dup read as "events per second", not a growing total.
export function rate(t, v) {
  const out = [];
  let j = 0;
  for (let i = 0; i < t.length; i++) {
    while (t[i] - t[j] > 1.0) j++;
    const dt = t[i] - t[j];
    const d = v[i] - v[j];
    out.push(dt > 0.2 && typeof d === 'number' && d >= 0 ? d / dt : null);
  }
  return out;
}
