// What the dashboard shows. Variable paths are resolved by the daemon from the flashed ELF (never offsets).
// A stage with no `var` is a part of the chain that has no variable to read yet: it is shown grey, not green.

export const STALE_S = 1.5; // a stage counter that did not change for this long is drawn red

export const STAGES = [
  { id: 'app', label: 'Remote: ứng dụng/đầu vào', target: 'remote', value: 's_app_input.data.controls.drive_ud', counter: 's_app_input.data.alive_tick' },
  { id: 'arb', label: 'Remote: arbiter', target: 'remote', value: 's_tx.out.source', flag: 's_tx.arbiter.armed' },
  { id: 'out', label: 'Remote: CONTROL gửi đi', target: 'remote', value: 's_tx.out.sent.drive_ud', counter: 's_tx.out.control_frames' },
  { id: 'air', label: 'Không trung (LoRa)', target: null, note: 'không có biến' },
  { id: 'par', label: 'Robot: parser', target: 'robot', counter: 's_lora_rx.parser.stats.frames' },
  { id: 'flt', label: 'Robot: filter', target: 'robot', counter: 's_lora_rx.filter.stats.accepted' },
  { id: 'inp', label: 'Robot: input', target: 'robot', value: 's_lora_rx.input.drive_ud', counter: 's_lora_rx.control_frames' },
  { id: 'can', label: 'Kinematics → CAN rpm', target: null, note: 'chưa có biến' },
];

// Counters drawn as rates (per second) in the link panel, one chart per board.
export const RATES = {
  robot: [
    { path: 's_lora_rx.parser.stats.frames', label: 'frames' },
    { path: 's_lora_rx.parser.stats.crc_errors', label: 'crc' },
    { path: 's_lora_rx.filter.stats.lost', label: 'lost' },
    { path: 's_lora_rx.filter.stats.duplicates', label: 'dup' },
    { path: 's_lora_rx.parser.stats.truncated', label: 'truncated' },
  ],
  remote: [
    { path: 's_tx.out.control_frames', label: 'control tx' },
    { path: 's_tx.out.tx_failures', label: 'tx fail' },
    { path: 's_link.frames_ok', label: 'rx ok' },
    { path: 's_link.frames_bad', label: 'rx bad' },
    { path: 's_link.frames_lost', label: 'rx lost' },
  ],
};

// Boolean-ish flags, side by side. `bad: true` means the flag being set is a problem.
export const FLAGS = [
  { target: 'remote', path: 's_link.link_up', label: 'remote link_up' },
  { target: 'remote', path: 's_tx.arbiter.armed', label: 'remote armed' },
  { target: 'remote', path: 's_tx.out.input_valid', label: 'remote input_valid' },
  { target: 'remote', path: 's_tx.out.sent.estop', label: 'remote ESTOP gửi', bad: true },
  { target: 'robot', path: 's_lora_rx.connected', label: 'robot connected' },
  { target: 'robot', path: 's_lora_rx.input.connected', label: 'robot input.connected' },
  { target: 'robot', path: 's_lora_rx.input.button_emergency', label: 'robot emergency', bad: true },
];

export function watchSet() {
  const w = { robot: new Set(), remote: new Set() };
  for (const s of STAGES) {
    if (!s.target) continue;
    for (const k of ['value', 'counter', 'flag']) if (s[k]) w[s.target].add(s[k]);
  }
  for (const [t, list] of Object.entries(RATES)) list.forEach((r) => w[t].add(r.path));
  FLAGS.forEach((f) => w[f.target].add(f.path));
  return Object.fromEntries(Object.entries(w).map(([t, s]) => [t, [...s]]));
}
