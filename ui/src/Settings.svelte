<script>
  // Settings: environment checks (Programmer CLI, ST-LINK driver, Claude login), ELF files and firmware files per board, chat,
  // register-read policy, appearance. Everything is stored by the daemon (rdt/settings.py); file pickers are native dialogs opened by it.
  import { onMount, onDestroy } from 'svelte';
  import { status } from './store.js';
  import { t, lang, theme, localizeError } from './i18n.js';

  let models = [], efforts = [];
  let s = { model: '', effort: null, max_usd: 2, allow_peripheral_reads: false, cube_cli_path: null, elf_files: {}, active_elf: {}, firmware_files: {} };
  let defaults = {}; // board -> { mcu, elf, image_elf } from targets.yaml
  let customModel = false;
  let msg = '', err = '', busy = false;

  // environment
  let cube = null, stlink = null, claude = null;
  let cubeBusy = false, stBusy = false, loginMsg = '', loginPoll = null;

  // file info (path -> inspect result) and add forms
  let info = {};
  let elfAdd = {}; // board -> path being typed
  let fwAddr = {}; // path -> address text being edited

  const api = async (method, url, body) => {
    const r = await fetch(url, { method, headers: { 'content-type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.detail ?? r.statusText);
    return j;
  };

  async function load() {
    try {
      const j = await api('GET', '/api/settings');
      models = j.models; efforts = j.efforts; defaults = j.targets ?? {};
      s = { ...s, ...j.settings, effort: j.settings.effort ?? '' };
      customModel = !models.includes(s.model);
      for (const p of allPaths()) inspect(p);
    } catch (e) { err = String(e.message ?? e); }
  }
  const allPaths = () => [
    ...Object.values(defaults).flatMap((d) => [d.elf, d.image_elf].filter(Boolean)),
    ...Object.values(s.elf_files ?? {}).flat(),
    ...Object.values(s.firmware_files ?? {}).flat().map((e) => e.path),
  ];
  async function inspect(p) {
    if (info[p]) return;
    try { info[p] = await api('POST', '/api/firmware/inspect', { path: p }); info = info; } catch { /* offline */ }
  }

  async function checkCube() { cubeBusy = true; try { cube = await api('GET', '/api/env/cube'); } catch (e) { cube = { ready: false, error: String(e.message ?? e), candidates: [] }; } cubeBusy = false; }
  async function checkStlink() { stBusy = true; try { stlink = await api('GET', '/api/env/stlink'); } catch (e) { stlink = { ready: false, probes: [], reason: 'scan_failed: ' + e.message }; } stBusy = false; }
  async function checkClaude(fresh = false) { try { claude = await api('GET', '/api/env/claude' + (fresh ? '?fresh=1' : '')); } catch { claude = null; } return claude; }

  onMount(() => { load(); checkCube(); checkStlink(); checkClaude(); });
  onDestroy(() => clearInterval(loginPoll));

  async function login() {
    loginMsg = '';
    try {
      await api('POST', '/api/env/claude/login');
      loginMsg = $t('env.loginHint');
      clearInterval(loginPoll);
      let n = 0;
      loginPoll = setInterval(async () => {
        const c = await checkClaude(true);
        if ((c && c.logged_in) || ++n > 100) { clearInterval(loginPoll); if (c?.logged_in) loginMsg = ''; }
      }, 3000);
    } catch (e) { loginMsg = $t('env.loginFail', { e: e.message }); }
  }

  async function save(changes, ok) {
    err = ''; msg = ''; busy = true;
    try {
      const j = await api('PUT', '/api/settings', changes);
      s = { ...s, ...j.settings, effort: j.settings.effort ?? '' };
      msg = ok ?? $t(j.chat_restarted ? 'set.savedRestart' : 'set.saved');
      window.dispatchEvent(new Event('rdt-files-changed'));
      for (const p of allPaths()) inspect(p);
    } catch (e) { err = localizeError(String(e.message ?? e), $lang); }
    busy = false;
  }
  const saveChat = () => save({ model: s.model, effort: s.effort || null, max_usd: Number(s.max_usd) });

  async function pick(kind, initial) {
    try { return (await api('POST', '/api/dialog/open', { kind, initial })).path; } catch (e) { err = String(e.message ?? e); return null; }
  }

  // Programmer CLI
  async function browseCube() { const p = await pick('exe', s.cube_cli_path); if (p) { await save({ cube_cli_path: p }, ''); checkCube(); } }
  async function useCube(p) { await save({ cube_cli_path: p }, ''); checkCube(); }
  async function autoCube() { await save({ cube_cli_path: null }, ''); checkCube(); }

  // ELF files
  const boardName = (n) => $t('elf.for', { name: n, mcu: $status.targets?.[n]?.mcu ?? defaults[n]?.mcu ?? '' });
  $: boards = Object.keys(defaults);
  // `st`/`df` are passed from the template so Svelte sees the dependency and re-renders when settings change.
  function elfList(b, st = s, df = defaults) {
    const d = df[b] ?? {};
    const user = st.elf_files?.[b] ?? [];
    return [...new Set([d.elf, d.image_elf, ...user].filter(Boolean))].map((p) => ({ path: p, builtin: p === d.elf || p === d.image_elf }));
  }
  const activeSym = (b, st = s, df = defaults) => st.active_elf?.[b]?.symbols || df[b]?.elf;
  const activeImg = (b, st = s, df = defaults) => st.active_elf?.[b]?.image || df[b]?.image_elf;
  async function addElf(b, path) {
    path = path?.trim();
    if (!path) return;
    await save({ elf_files: { ...s.elf_files, [b]: [...(s.elf_files?.[b] ?? []), path] } }, '');
    elfAdd[b] = '';
  }
  async function browseElf(b) { const p = await pick('elf'); if (p) await addElf(b, p); }
  const setActive = (b, role, path) => save({ active_elf: { ...s.active_elf, [b]: { ...(s.active_elf?.[b] ?? {}), [role]: path } } }, $t('elf.intro'));
  async function removeElf(b, path) {
    const act = { ...(s.active_elf?.[b] ?? {}) };
    for (const k of Object.keys(act)) if (act[k] === path) act[k] = null;
    await save({ elf_files: { ...s.elf_files, [b]: (s.elf_files?.[b] ?? []).filter((x) => x !== path) }, active_elf: { ...s.active_elf, [b]: act } }, '');
  }

  // Firmware files
  const fwList = (b, st = s) => st.firmware_files?.[b] ?? [];
  async function addFw(b) {
    const p = await pick('firmware');
    if (!p) return;
    await save({ firmware_files: { ...s.firmware_files, [b]: [...fwList(b).filter((e) => e.path !== p), { path: p, address: null }] } }, '');
  }
  const removeFw = (b, path) => save({ firmware_files: { ...s.firmware_files, [b]: fwList(b).filter((e) => e.path !== path) } }, '');
  async function saveAddr(b, path) {
    const txt = (fwAddr[path] ?? '').trim();
    const v = txt === '' ? null : Number(txt);
    if (v !== null && (!Number.isInteger(v) || v < 0 || v % 4)) { err = $t('fw.badAddr'); return; }
    await save({ firmware_files: { ...s.firmware_files, [b]: fwList(b).map((e) => (e.path === path ? { ...e, address: v } : e)) } }, '');
  }
  const addrText = (e) => fwAddr[e.path] ?? (e.address === null || e.address === undefined ? '' : '0x' + e.address.toString(16).toUpperCase().padStart(8, '0'));

  const fmtSize = (n) => (n >= 1048576 ? (n / 1048576).toFixed(1) + ' MiB' : n >= 1024 ? (n / 1024).toFixed(0) + ' KiB' : n + ' B');
  const fmtTime = (s) => new Date(s * 1000).toLocaleString();
  const base = (p) => p.split(/[\\/]/).pop();

  $: claudeKey = !claude ? 'checking' : !claude.sdk ? 'nosdk' : claude.logged_in === false ? 'login' : claude.logged_in ? 'ready' : 'unknown';
  $: chatStatus = !claude ? 'set.statusUnknown' : !claude.sdk ? 'set.statusNoSdk' : claude.logged_in === false ? 'set.statusLogin' : claude.logged_in ? 'set.statusReady' : 'set.statusUnknown';
</script>

<div class="card">
  <h2>{$t('set.title')}</h2>

  <h3>{$t('env.title')}</h3>
  <div class="env">
    <!-- STM32_Programmer_CLI -->
    <div class="row">
      <div class="lab">{$t('env.cube')}</div>
      <div class="stat">
        {#if !cube || cubeBusy}<span class="pill">{$t('env.checking')}</span>
        {:else if cube.ready}<span class="pill ok">{$t('env.ready')}</span> <span class="muted">{$t('env.cubeVersion', { v: cube.active.version })}</span>
        {:else}<span class="pill bad">{$t('env.notFound')}</span>{/if}
        <button on:click={browseCube}>{$t('env.browse')}</button><button on:click={checkCube}>{$t('env.rescan')}</button>
        {#if s.cube_cli_path}<button on:click={autoCube}>{$t('env.auto')}</button>{/if}
      </div>
      {#if cube?.ready}
        <div class="muted small mono">{$t('env.cubeActive')} {cube.active.path} ({$t('env.src.' + cube.active.source)})</div>
        {#if cube.active.version !== cube.pinned}<div class="warn small">{$t('env.cubeDiff', { p: cube.pinned })}</div>{/if}
        {#if cube.candidates.filter((c) => c.version && c.path !== cube.active.path).length}
          <div class="muted small">{$t('env.cubeOthers')}</div>
          {#each cube.candidates.filter((c) => c.version && c.path !== cube.active.path) as c}
            <button class="link mono small" on:click={() => useCube(c.path)}>{c.version} · {$t('env.src.' + c.source)} · {c.path}</button>
          {/each}
        {/if}
      {:else if cube}<div class="warn small">{$t('env.cubeMissing')}</div>{/if}
    </div>

    <!-- ST-LINK driver -->
    <div class="row">
      <div class="lab">{$t('env.stlink')}</div>
      <div class="stat">
        {#if !stlink || stBusy}<span class="pill">{$t('env.checking')}</span>
        {:else if stlink.ready}<span class="pill ok">{$t('env.ready')}</span>
        {:else}<span class="pill bad">{$t(stlink.reason === 'driver_problem' ? 'env.driverProblem' : 'env.notFound')}</span>{/if}
        <button on:click={checkStlink}>{$t('env.scan')}</button>
      </div>
      {#if stlink && !stBusy}
        {#each stlink.probes as p}
          <div class="small mono" class:bad={!p.ready}>
            {p.ready ? '✓' : '✕'} {$t('env.probeLine', { name: p.name, s: p.serial, b: p.target ?? $t('env.noBoard'), c: p.vcp ?? $t('env.noCom'), d: p.driver.join(', ') || $t('env.noDrv') })}
            {#each p.problems as pr}<div class="bad">{pr}</div>{/each}
          </div>
        {/each}
        {#if stlink.reason === 'no_probe'}<div class="warn small">{$t('env.stlinkNone')}</div>
        {:else if stlink.reason === 'driver_problem'}<div class="warn small">{$t('env.stlinkBad')}</div>
        {:else if stlink.reason}<div class="warn small">{$t('env.stlinkFail', { e: stlink.reason })}</div>{/if}
        <div class="muted small">{stlink.packages.length ? $t('env.pkgs', { n: stlink.packages.length }) : $t('env.noPkgs')}</div>
      {/if}
    </div>

    <!-- Claude login -->
    <div class="row">
      <div class="lab">{$t('env.claude')}</div>
      <div class="stat">
        {#if claudeKey === 'checking'}<span class="pill">{$t('env.checking')}</span>
        {:else if claudeKey === 'ready'}<span class="pill ok">{$t('env.ready')}</span> <span class="muted">{$t('env.claudeReady')}</span>
        {:else if claudeKey === 'login'}<span class="pill bad">{$t('env.claudeLogin')}</span> <button class="primary mono" on:click={login}>{$t('env.loginBtn')}</button>
        {:else if claudeKey === 'nosdk'}<span class="pill bad">{$t('env.claudeNoSdk')}</span>
        {:else}<span class="pill">{$t('env.claudeUnknown')}</span>{/if}
        <button on:click={() => checkClaude(true)}>{$t('env.rescan')}</button>
      </div>
      {#if loginMsg}<div class="warn small">{loginMsg}</div>{/if}
    </div>
  </div>

  <h3>{$t('elf.title')}</h3>
  <p class="muted small">{$t('elf.intro')}</p>
  {#each boards as b}
    <div class="board">
      <div class="bt">{boardName(b)}</div>
      {#each elfList(b, s, defaults) as f (f.path)}
        {@const i = info[f.path]}
        <div class="file">
          <div class="radios">
            <label title={$t('elf.symbols')}><input type="radio" name="sym-{b}" checked={activeSym(b, s, defaults) === f.path} disabled={i && !i.dwarf} on:change={() => setActive(b, 'symbols', f.path)} /> {$t('elf.symbols')}</label>
            <label title={$t('elf.image')}><input type="radio" name="img-{b}" checked={activeImg(b, s, defaults) === f.path} on:change={() => setActive(b, 'image', f.path)} /> {$t('elf.image')}</label>
          </div>
          <div class="fp"><span class="mono" title={f.path}>{base(f.path)}</span> {#if f.builtin}<span class="tag">{$t('elf.default')}</span>{/if}
            {#if i}
              {#if i.exists === false}<span class="tag bad">{$t('elf.missing')}</span>
              {:else if i.error}<span class="tag bad">{i.error}</span>
              {:else}<span class="tag" class:ok={i.dwarf}>{i.dwarf ? $t('elf.dwarf') : $t('elf.noDwarf')}</span> <span class="muted small">{fmtSize(i.size)} · {fmtTime(i.mtime)} · {i.sha8}</span>{/if}
            {/if}
            <div class="muted small mono">{f.path}</div></div>
          {#if !f.builtin}<button class="mini" title={$t('elf.remove')} on:click={() => removeElf(b, f.path)}>✕</button>{/if}
        </div>
      {/each}
      <div class="addrow">
        <input class="mono grow" placeholder={$t('elf.pathPh')} bind:value={elfAdd[b]} on:keydown={(e) => e.key === 'Enter' && addElf(b, elfAdd[b])} />
        <button on:click={() => addElf(b, elfAdd[b])} disabled={!elfAdd[b]?.trim()}>{$t('elf.addBtn')}</button>
        <button on:click={() => browseElf(b)}>{$t('elf.add')}</button>
      </div>
    </div>
  {/each}

  <h3>{$t('fw.title')}</h3>
  <p class="muted small">{$t('fw.intro')}</p>
  {#each boards as b}
    <div class="board">
      <div class="bt">{boardName(b)} <span class="muted small">· {$t('fw.forBoard', { name: b })}</span></div>
      {#each fwList(b, s) as e (e.path)}
        {@const i = info[e.path]}
        <div class="file">
          <div class="fp"><span class="tag k">{(i?.kind ?? '').toUpperCase()}</span> <span class="mono" title={e.path}>{base(e.path)}</span>
            {#if i}{#if i.exists === false}<span class="tag bad">{$t('elf.missing')}</span>{:else if i.error}<span class="tag bad">{i.error}</span>
              {:else}<span class="muted small">{fmtSize(i.size)} · {fmtTime(i.mtime)} · {i.sha8}{#if i.flash} · 0x{i.flash[0].toString(16).toUpperCase()}…0x{i.flash[1].toString(16).toUpperCase()}{/if}</span>{/if}{/if}
            <div class="muted small mono">{e.path}</div>
            {#if i?.kind === 'bin'}
              <div class="addrow"><label class="small muted">{$t('fw.address')} <input class="mono" size="12" placeholder="0x08000000" value={addrText(e)} on:input={(ev) => (fwAddr[e.path] = ev.target.value)} /></label>
                <button class="mini" on:click={() => saveAddr(b, e.path)}>{$t('fw.saveAddr')}</button></div>
            {/if}</div>
          <button class="mini" title={$t('elf.remove')} on:click={() => removeFw(b, e.path)}>✕</button>
        </div>
      {:else}<div class="muted small">{$t('fw.none')}</div>{/each}
      <div class="addrow"><button on:click={() => addFw(b)}>{$t('fw.add')}</button></div>
    </div>
  {/each}

  <h3>{$t('set.chat')}</h3>
  <p class="muted small">{$t('set.engineNote')}</p>
  <div class="grid">
    <label>{$t('set.model')}
      <select value={customModel ? '__custom' : s.model} on:change={(e) => { customModel = e.target.value === '__custom'; if (!customModel) s.model = e.target.value; }}>
        {#each models as m}<option value={m}>{m}</option>{/each}
        <option value="__custom">{$t('set.modelCustom')}</option>
      </select>
      {#if customModel}<input bind:value={s.model} class="mono" placeholder="claude-…" />{/if}
    </label>
    <label>{$t('set.effort')}
      <select bind:value={s.effort}><option value="">{$t('set.effortDefault')}</option>{#each efforts as e}<option value={e}>{e}</option>{/each}</select>
    </label>
    <label>{$t('set.budget')}<input type="number" step="0.1" min="0.05" max="100" bind:value={s.max_usd} class="num" /></label>
  </div>
  <div class="row2"><button class="primary" on:click={saveChat} disabled={busy}>{$t('set.save')}</button>
    <span class="muted">{$t('set.status')}: <b class:ok={chatStatus === 'set.statusReady'} class:bad={chatStatus === 'set.statusLogin' || chatStatus === 'set.statusNoSdk'}>{$t(chatStatus)}</b></span></div>

  <h3>{$t('set.reading')}</h3>
  <label class="check"><input type="checkbox" checked={s.allow_peripheral_reads} on:change={(e) => save({ allow_peripheral_reads: e.target.checked })} /> {$t('set.periph')}</label>
  <p class="warn small">{$t('set.periphWarn')}</p>

  <h3>{$t('set.appearance')}</h3>
  <div class="grid">
    <label>{$t('set.theme')}
      <select bind:value={$theme}><option value="dark">{$t('set.themeDark')}</option><option value="light">{$t('set.themeLight')}</option></select>
    </label>
    <label>{$t('set.lang')}
      <select bind:value={$lang}><option value="vi">Tiếng Việt</option><option value="en">English</option></select>
    </label>
  </div>

  {#if msg}<div class="ok">{msg}</div>{/if}
  {#if err}<div class="bad">{err}</div>{/if}
</div>

<style>
  h3 { margin: 18px 0 4px; font-size: 13px; color: var(--accent2); }
  .env { display: flex; flex-direction: column; gap: 10px; }
  .row { border: 1px solid var(--line); border-radius: var(--radius); padding: 8px 10px; background: var(--panel2); display: flex; flex-direction: column; gap: 4px; }
  .lab { font-weight: 600; }
  .stat { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
  .pill { font-size: 12px; border: 1px solid var(--line); border-radius: 99px; padding: 1px 10px; color: var(--muted); }
  .pill.ok { color: var(--ok); border-color: var(--ok); } .pill.bad { color: var(--bad); border-color: var(--bad); }
  .small { font-size: 12px; }
  .board { border: 1px solid var(--line); border-radius: var(--radius); padding: 8px 10px; margin: 8px 0; }
  .bt { font-weight: 600; margin-bottom: 6px; }
  .file { display: flex; gap: 12px; align-items: flex-start; padding: 5px 0; border-bottom: 1px dashed var(--line); }
  .radios { display: flex; flex-direction: column; gap: 2px; min-width: 120px; font-size: 12px; }
  .radios label { flex-direction: row; align-items: center; gap: 6px; color: var(--text); }
  .fp { flex: 1; min-width: 0; word-break: break-all; }
  .tag { font-size: 10px; border: 1px solid var(--line); border-radius: 3px; padding: 0 5px; color: var(--muted); }
  .tag.ok { color: var(--ok); border-color: var(--ok); } .tag.bad { color: var(--bad); border-color: var(--bad); } .tag.k { color: var(--c3); border-color: var(--c3); }
  .addrow { display: flex; gap: 8px; align-items: center; margin-top: 6px; flex-wrap: wrap; }
  .grow { flex: 1; min-width: 220px; }
  .mini { font-size: 11px; padding: 1px 8px; }
  .link { background: none; border: none; padding: 1px 0; text-align: left; color: var(--accent); word-break: break-all; }
  .grid { display: flex; flex-wrap: wrap; gap: 16px; margin: 8px 0; }
  label { display: flex; flex-direction: column; gap: 4px; font-size: 11px; color: var(--muted); }
  .check { flex-direction: row; align-items: center; gap: 8px; font-size: 13px; color: var(--text); }
  .row2 { display: flex; gap: 16px; align-items: center; margin-top: 6px; }
  .num { width: 100px; }
  .ok { color: var(--ok); } .bad { color: var(--bad); } .warn { color: var(--warn); }
</style>
