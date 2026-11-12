<script>
  // Saved chat conversations: search, open (the daemon resumes its Claude session), rename, export, delete.
  import { onMount, createEventDispatcher } from 'svelte';
  import { listChats, renameChat, deleteChat, openChat, chat } from './store.js';
  import { t, lang } from './i18n.js';

  const dispatch = createEventDispatcher();
  let items = [], current = null, q = '', err = '', editing = null, title = '', confirmDel = null, loaded = false;

  async function load() {
    try { const j = await listChats(); items = j.chats; current = j.current; err = ''; } catch (e) { err = String(e.message ?? e); }
    loaded = true;
  }
  onMount(load);
  $: active = $chat.chatId ?? current;
  $: shown = items.filter((m) => !q.trim() || m.title.toLowerCase().includes(q.trim().toLowerCase()));
  const when = (s) => new Date(s).toLocaleString($lang === 'vi' ? 'vi-VN' : 'en-GB');

  async function open(id) {
    err = '';
    try { await openChat(id); dispatch('opened'); } catch (e) { err = String(e.message ?? e); }
  }
  async function saveTitle(id) {
    try { await renameChat(id, title); editing = null; await load(); } catch (e) { err = String(e.message ?? e); }
  }
  async function del(id) {
    try { await deleteChat(id); confirmDel = null; if ($chat.chatId === id) chat.update((c) => ({ ...c, items: [], chatId: null, sessionId: null })); await load(); } catch (e) { err = String(e.message ?? e); }
  }
</script>

<div class="hist">
  <div class="bar">
    <input type="search" bind:value={q} placeholder={$t('hist.search')} />
    <button on:click={load} title={$t('hist.refresh')}>⟳</button>
  </div>
  {#if err}<div class="err small">{err}</div>{/if}
  <div class="list">
    {#each shown as m (m.id)}
      <div class="item" class:cur={m.id === active}>
        {#if editing === m.id}
          <input bind:value={title} class="ttl" on:keydown={(e) => e.key === 'Enter' && saveTitle(m.id)} />
          <button class="mini primary" on:click={() => saveTitle(m.id)}>{$t('hist.save')}</button>
          <button class="mini" on:click={() => (editing = null)}>{$t('hist.cancel')}</button>
        {:else}
          <button class="open" on:click={() => open(m.id)} disabled={$chat.busy} title={$t('hist.open')}>
            <span class="t">{m.title}</span>
            <span class="muted small">{when(m.updated)} · {$t('hist.msgs', { n: m.messages })}{m.cost_usd ? ` · $${m.cost_usd.toFixed(3)}` : ''}{m.id === active ? ' · ' + $t('hist.current') : ''}</span>
          </button>
          <div class="acts">
            <button class="mini" title={$t('hist.rename')} on:click={() => { editing = m.id; title = m.title; }}>✎</button>
            <a class="mini lnk" title={$t('hist.export')} href={'/api/chats/' + m.id + '/export'} download>⇩</a>
            {#if confirmDel === m.id}
              <button class="mini danger" on:click={() => del(m.id)}>{$t('hist.sure')}</button>
              <button class="mini" on:click={() => (confirmDel = null)}>{$t('hist.cancel')}</button>
            {:else}<button class="mini" title={$t('hist.delete')} on:click={() => (confirmDel = m.id)}>🗑</button>{/if}
          </div>
        {/if}
      </div>
    {:else}<div class="muted small">{loaded ? $t('hist.none') : '…'}</div>{/each}
  </div>
</div>

<style>
  .hist { border: 1px solid var(--line); border-radius: var(--radius); background: var(--panel2); padding: 6px; margin: 6px 0; }
  .bar { display: flex; gap: 6px; margin-bottom: 6px; }
  .bar input { flex: 1; }
  .list { max-height: 260px; overflow: auto; display: flex; flex-direction: column; gap: 4px; }
  .item { display: flex; gap: 6px; align-items: center; border: 1px solid var(--line); border-radius: var(--radius); padding: 3px 5px; }
  .item.cur { border-color: var(--accent); }
  .open { flex: 1; text-align: left; background: none; border: none; padding: 2px; display: flex; flex-direction: column; min-width: 0; }
  .t { font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .acts { display: flex; gap: 3px; }
  .mini { font-size: 11px; padding: 1px 6px; }
  .lnk { text-decoration: none; border: 1px solid var(--line); border-radius: var(--radius); color: var(--text); }
  .ttl { flex: 1; min-width: 0; }
  .small { font-size: 11px; }
  .err { color: var(--bad); }
</style>
