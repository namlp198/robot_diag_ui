import { writable, get } from 'svelte/store';

const KEEP_S = 120; // live window kept in memory for charts

export const status = writable({ running: false, recording: null, targets: {}, watches: {}, vcp: {}, errors: [] });
export const conn = writable('offline'); // offline | live | replay
export const latest = writable({}); // target -> path -> { v, t, changed }
export const series = writable({}); // target -> { cols: [path], t: [], v: { path: [] } }
export const events = writable([]); // { t, target, kind, text }
export const replayName = writable(null);

let ws = null;
let mode = 'live';

function pushEvent(e) {
  events.update((a) => (a.length > 400 ? [...a.slice(-300), e] : [...a, e]));
}

function onSample(m) {
  if (mode !== 'live') return;
  latest.update((L) => {
    const T = (L[m.target] ??= {});
    const cols = get(status).watches[m.target]?.paths ?? [];
    cols.forEach((p, i) => {
      const v = m.values[i];
      const old = T[p];
      if (!old) T[p] = { v, t: m.t, changed: m.t };
      else {
        if (old.v !== v) {
          old.changed = m.t;
          if (typeof v === 'boolean') pushEvent({ t: m.t, target: m.target, kind: 'flag', text: `${p}: ${old.v} → ${v}` });
        }
        old.v = v;
        old.t = m.t;
      }
    });
    return L;
  });
  series.update((S) => {
    const s = (S[m.target] ??= { cols: get(status).watches[m.target]?.paths ?? [], t: [], v: {} });
    s.t.push(m.t);
    s.cols.forEach((p, i) => (s.v[p] ??= []).push(m.values[i]));
    while (s.t.length && s.t[0] < m.t - KEEP_S) {
      s.t.shift();
      s.cols.forEach((p) => s.v[p].shift());
    }
    return S;
  });
}

function onMessage(ev) {
  const m = JSON.parse(ev.data);
  if (m.type === 'hello') status.set(m.status);
  else if (m.type === 'sample') onSample(m);
  else if (m.type === 'log') pushEvent({ t: m.t, target: m.target, kind: 'log', text: m.line });
  else if (m.type === 'error') pushEvent({ t: m.t, target: m.target, kind: 'error', text: m.text });
}

export function connect() {
  const url = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`;
  ws = new WebSocket(url);
  ws.onopen = () => {
    if (mode === 'live') conn.set('live');
    refresh();
  };
  ws.onmessage = onMessage;
  ws.onclose = () => {
    if (mode === 'live') conn.set('offline');
    setTimeout(connect, 1500);
  };
}

export async function refresh() {
  try {
    status.set(await (await fetch('/api/status')).json());
  } catch {
    /* daemon offline: conn store already says so */
  }
}

async function post(url, body) {
  const r = await fetch(url, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body ?? {}) });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail ?? r.statusText);
  return r.json();
}

export async function startWatch(watches, hz, vcp) {
  mode = 'live';
  conn.set('live');
  replayName.set(null);
  latest.set({});
  series.set({});
  events.set([]);
  status.set(await post('/api/watch', { watches, hz, vcp }));
}

export async function stopWatch() {
  status.set(await post('/api/stop'));
}

export async function record(on, label = '') {
  if (on) await post('/api/record/start', { label });
  else await post('/api/record/stop');
  await refresh();
}

export async function listSessions() {
  return (await fetch('/api/sessions')).json();
}

// Load a recorded session into the same stores the live view uses.
export async function loadSession(name) {
  mode = 'replay';
  conn.set('replay');
  replayName.set(name);
  const L = {};
  const S = {};
  const ev = [];
  let meta = null;
  for (const target of ['robot', 'remote']) {
    const r = await fetch(`/api/sessions/${encodeURIComponent(name)}?target=${target}&limit=20000`);
    if (!r.ok) continue;
    const j = await r.json();
    meta = j.meta;
    const cols = j.columns.slice(1);
    const s = (S[target] = { cols, t: [], v: Object.fromEntries(cols.map((c) => [c, []])) });
    const T = (L[target] = {});
    for (const row of j.rows) {
      s.t.push(row[0]);
      cols.forEach((c, i) => {
        const v = row[i + 1];
        s.v[c].push(v);
        const o = T[c];
        if (!o) T[c] = { v, t: row[0], changed: row[0] };
        else {
          if (o.v !== v) {
            o.changed = row[0];
            if (typeof v === 'boolean') ev.push({ t: row[0], target, kind: 'flag', text: `${c}: ${o.v} → ${v}` });
          }
          o.v = v;
          o.t = row[0];
        }
      });
    }
    (j.log ?? []).forEach((l) => ev.push({ t: l.t, target, kind: 'log', text: l.line }));
    (j.events ?? []).forEach((e) => ev.push({ t: e.t, target, kind: e.kind, text: e.text }));
  }
  ev.sort((a, b) => a.t - b.t);
  latest.set(L);
  series.set(S);
  events.set(ev);
  return meta;
}

export function backToLive() {
  mode = 'live';
  conn.set(ws && ws.readyState === 1 ? 'live' : 'offline');
  replayName.set(null);
  latest.set({});
  series.set({});
  events.set([]);
  refresh();
}
