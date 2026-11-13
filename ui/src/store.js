import { writable, get } from 'svelte/store';

const KEEP_S = 120; // live window kept in memory for charts

export const status = writable({ running: false, recording: null, targets: {}, watches: {}, vcp: {}, errors: [] });
export const conn = writable('offline'); // offline | live | replay
export const latest = writable({}); // target -> path -> { v, t, changed }
export const series = writable({}); // target -> { cols: [path], t: [], v: { path: [] } }
export const events = writable([]); // { t, target, kind, text }
export const replayName = writable(null);
export const chat = writable({ items: [], busy: false, model: null, cost: 0, sessionId: null, chatId: null, repo: null, engine: 'idle', engineDetail: '' });
export const showTools = writable((() => { try { return localStorage.getItem('rdt.showTools') !== '0'; } catch { return true; } })());
showTools.subscribe((v) => { try { localStorage.setItem('rdt.showTools', v ? '1' : '0'); } catch { /* not persisted */ } });
export const claudeCharts = writable([]); // { id, title, series: [{target,path,as}], from, to }
export const highlights = writable([]);
export const frames = writable([]); // decoded RCL frames (rdt/rcl.py), live or from a recorded session
export const canFrames = writable([]); // CAN/FDCAN frames sampled on the robot (rdt/cantap.py)
export const canStats = writable({}); // target -> tap statistics
export const exprLatest = writable({}); // target -> { t, values: { id: value | { error } } } (live expressions)
export const findings = writable([]); // analyzer findings, live or from a recorded session // { t0, t1, label }

function chatEvent(m) {
  chat.update((c) => {
    const items = c.items;
    const last = items[items.length - 1];
    switch (m.kind) {
      case 'user': items.push({ k: 'user', text: m.text, attachments: m.attachments ?? [], chatId: m.chat_id ?? c.chatId }); c.chatId = m.chat_id ?? c.chatId; c.busy = true; break;
      case 'init': c.model = m.model; c.sessionId = m.session_id; break;
      case 'text_delta':
        if (last && last.k === 'assistant' && last.streaming) last.text += m.text;
        else items.push({ k: 'assistant', text: m.text, streaming: true });
        break;
      case 'text':
        if (last && last.k === 'assistant' && last.streaming) { last.text = m.text; last.streaming = false; }
        else items.push({ k: 'assistant', text: m.text });
        break;
      case 'tool_use': items.push({ k: 'tool', id: m.id, name: m.name, input: m.input, state: 'running' }); break;
      case 'tool_result': {
        const t = items.find((x) => x.k === 'tool' && x.id === m.id);
        if (t) { t.state = m.is_error ? 'error' : 'done'; t.result = m.text; }
        break;
      }
      case 'result': c.cost += m.cost_usd ?? 0; break;
      case 'error': items.push({ k: 'error', text: m.text }); break;
      case 'engine': c.repo = m.repo; c.engine = m.state; c.engineDetail = m.detail ?? ''; break;
      case 'approval': items.push({ k: 'approval', id: m.id, action: m.action, path: m.path, diff: m.diff, state: 'pending' }); break;
      case 'approval_done': { const a = items.find((x) => x.k === 'approval' && x.id === m.id); if (a) a.state = m.allow ? 'approved' : 'denied'; break; }
      case 'idle': c.busy = false; items.forEach((x) => (x.streaming = false)); break;
    }
    return c;
  });
}

function uiCommand(m) {
  if (m.cmd === 'show_chart') claudeCharts.update((a) => [...a.slice(-3), { id: Date.now() + Math.random(), title: m.title, series: m.series, from: m.from, to: m.to }]);
  else if (m.cmd === 'highlight') highlights.update((a) => [...a, { t0: m.t0, t1: m.t1, label: m.label }]);
  else if (m.cmd === 'annotate') pushEvent({ t: m.t, target: m.target || 'claude', kind: 'note', text: m.text });
}

// attachments: [{ name, data (base64) }] from ui/src/attach.js
export async function sendChat(text, view, attachments = [], repo = null) {
  const r = await fetch('/api/chat', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ text, view, repo, attachments: attachments.map(({ name, data }) => ({ name, data })) }) });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail ?? r.statusText);
}

// --- saved conversations ---
async function jreq(method, url, body) {
  const r = await fetch(url, { method, headers: { 'content-type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.detail ?? r.statusText);
  return j;
}
export const listChats = () => jreq('GET', '/api/chats');
export const renameChat = (id, title) => jreq('PATCH', '/api/chats/' + id, { title });
export const deleteChat = (id) => jreq('DELETE', '/api/chats/' + id);
// Opens a saved chat: the daemon makes it the current conversation (the next message resumes it) and the UI replays its events.
export async function openChat(id) {
  const j = await jreq('POST', '/api/chats/' + id + '/open');
  chat.set({ items: [], busy: false, model: null, cost: 0, sessionId: j.meta.session_id, chatId: id, repo: j.meta.repo ?? null, engine: 'idle', engineDetail: '' });
  claudeCharts.set([]);
  highlights.set([]);
  for (const ev of j.events) chatEvent(ev);
  chat.update((c) => { c.busy = false; c.cost = j.meta.cost_usd ?? 0; c.items.forEach((x) => { x.streaming = false; if (x.k === 'approval' && x.state === 'pending') x.state = 'expired'; }); c.engine = 'idle'; c.engineDetail = ''; return c; });
  return j.meta;
}
export const approve = (id, allow) => jreq('POST', '/api/chat/approve', { id, allow });
export const stopChat = () => fetch('/api/chat/stop', { method: 'POST' });
export async function resetChat() {
  await fetch('/api/chat/reset', { method: 'POST' });
  chat.set({ items: [], busy: false, model: null, cost: 0, sessionId: null, chatId: null, repo: null, engine: 'idle', engineDetail: '' });
  claudeCharts.set([]);
  highlights.set([]);
}

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
  else if (m.type === 'finding') {
    if (mode === 'live') {
      const { type, ...f } = m;
      findings.update((a) => [...a, f]);
      pushEvent({ t: f.t0, target: f.target, kind: 'finding', text: `${f.severity}: ${f.title}`, finding: f }); // `finding`: the UI re-translates it
    }
  }
  else if (m.type === 'frame') {
    if (mode === 'live') { const { type, ...f } = m; frames.update((a) => (a.length >= 600 ? [...a.slice(-500), f] : [...a, f])); }
  }
  else if (m.type === 'can') {
    if (mode === 'live') {
      if (m.frames.length) canFrames.update((a) => (a.length + m.frames.length > 1500 ? [...a.slice(-1000), ...m.frames] : [...a, ...m.frames]));
      canStats.update((s) => ({ ...s, [m.target]: m.stats }));
    }
  }
  else if (m.type === 'expr') exprLatest.update((L) => ({ ...L, [m.target]: { t: m.t, values: m.values } }));
  else if (m.type === 'chat') chatEvent(m);
  else if (m.type === 'ui') uiCommand(m);
  else if (m.type === 'files_changed') window.dispatchEvent(new Event('rdt-files-changed'));
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
  findings.set([]);
  frames.set([]);
  canFrames.set([]);
  canStats.set({});
  exprLatest.set({});
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
  try {
    const fr = await (await fetch(`/api/sessions/${encodeURIComponent(name)}/findings`)).json();
    findings.set(fr.findings ?? []);
    (fr.findings ?? []).forEach((f) => ev.push({ t: f.t0, target: f.target, kind: 'finding', text: `${f.severity}: ${f.title}`, finding: f }));
  } catch { findings.set([]); }
  try { frames.set((await (await fetch(`/api/sessions/${encodeURIComponent(name)}/frames`)).json()).frames ?? []); } catch { frames.set([]); }
  try { canFrames.set((await (await fetch(`/api/sessions/${encodeURIComponent(name)}/can`)).json()).frames ?? []); } catch { canFrames.set([]); }
  canStats.set({});
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
  findings.set([]);
  frames.set([]);
  canFrames.set([]);
  canStats.set({});
  refresh();
}
