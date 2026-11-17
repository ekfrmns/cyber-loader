// Cyberpunk Mod Manager UI: state, rendering and interaction.
import { pref } from './prefs.js';
import { api, initApi, apiMode, mockModule } from './api.js';
import { animate, set, current } from './spring.js';
import { icon, hydrateIcons } from './icons.js';
import { openModal, openPopover, closePopovers, closeTop, hasModal, isOpen, toast, announce, dialog, esc, setFallbackFocus } from './ui.js';

const GROUPS = ['Framework', 'Body', 'Characters', 'Clothing', 'Gameplay', 'Content', 'Other'];
const ACCENTS = [
  ['Blue', '#0A84FF'], ['Purple', '#BF5AF2'], ['Pink', '#FF375F'], ['Orange', '#FF9F0A'],
  ['Yellow', '#FCEE0A'], ['Green', '#30D158'], ['Teal', '#40C8E0'], ['Graphite', '#8E8E93'],
];
const DEFAULT_SETTINGS = { theme: 'system', accent: '#0A84FF' };

const $ = (s, r = document) => r.querySelector(s);
const nf = new Intl.NumberFormat('en-US');
const plural = (n, one, many = `${one}s`) => `${nf.format(n)} ${n === 1 ? one : many}`;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const LS = {
  get(k, d) { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* storage blocked */ } },
};
const root = document.documentElement;
const darkMQ = matchMedia('(prefers-color-scheme: dark)');

const S = {
  st: null,                 // last /api/state
  status: 'loading',        // loading | ready | error
  error: null,
  query: '',
  collapsed: new Set(LS.get('cmm.collapsed', [])),
  navKey: null,             // roving tabindex position in the list
  inflight: 0,
  bar: null,                // overrides the bar view: 'applying' | 'done' | 'error'
  lost: false,              // live engine stopped answering
  lastJson: '',
  applyTotals: null,
  settings: { ...DEFAULT_SETTINGS, ...LS.get('cmm.settings', {}) },
};

// ---------- helpers ----------
const mods = () => S.st?.mods || [];
const byId = (id) => mods().find((m) => m.id === id);
const running = () => !!S.st?.game?.running;
function pending() {
  let on = 0, off = 0;
  for (const m of mods()) { if (m.pending === 'on') on++; else if (m.pending === 'off') off++; }
  return { on, off, total: on + off };
}
function listNames(names) {
  if (names.length <= 2) return names.join(' and ');
  return `${names[0]}, ${names[1]} and ${names.length - 2} more`;
}
// A need the engine guessed from the mod's files: { name: 'ArchiveXL', ids: [library mods that supply it] }.
// It is met as soon as any supplier is on.
const autoNeedsMe = (x, id) => (x.autoRequires || []).some((n) => n.ids.includes(id) && !n.ids.some((i) => byId(i)?.enabled));
function warningFor(m) {
  const all = mods();
  if (!m.enabled) {
    if (!m.framework && !all.some((x) => x.requires?.includes(m.id) || autoNeedsMe(x, m.id))) return '';
    const deps = all.filter((x) => x.enabled && (x.requires?.includes(m.id) || autoNeedsMe(x, m.id)));
    return deps.length ? `Needed by ${listNames(deps.map((d) => d.name))}` : '';
  }
  const missing = (m.requires || []).map((r) => {
    const dep = byId(r);
    if (!dep) return `${r} (not in library)`;
    return dep.enabled ? null : dep.name;
  }).filter(Boolean);
  for (const n of m.autoRequires || []) {
    if (n.ids.some((i) => byId(i)?.enabled)) continue;
    missing.push(n.ids.length ? n.name : `${n.name} (not in library)`);
  }
  return missing.length ? `Needs ${listNames(missing)}` : '';
}

// ---------- theme ----------
function hexToRgb(h) { const n = parseInt(h.slice(1), 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; }
function rgbToHex(c) { return `#${c.map((v) => Math.round(v).toString(16).padStart(2, '0')).join('')}`.toUpperCase(); }
function lum(c) { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]); }
function contrast(a, b) { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); }
function mix(a, b, t) { return a.map((v, i) => v + (b[i] - v) * t); }
function towards(base, target, ok) { for (let t = 0; t <= 1.0001; t += 0.025) { const c = mix(base, target, t); if (ok(c)) return { c, t }; } return { c: target, t: 1 }; }

/** Derive fill / on-fill / text / ring colours from the accent so every pairing passes 4.5:1. */
function accentVars(accent, theme) {
  const a = hexToRgb(accent);
  const W = [255, 255, 255], K = [0, 0, 0];
  const surfaces = theme === 'dark' ? [[13, 13, 16], [26, 26, 31], [30, 30, 36]] : [[255, 255, 255], [242, 242, 246]];
  // Button fill: keep white text if a small darkening gets there, otherwise use black text.
  const white = towards(a, K, (c) => contrast(c, W) >= 4.5);
  let fill, on;
  if (white.t <= 0.3) { fill = white.c; on = '#FFFFFF'; }
  else if (contrast(a, K) >= 4.5) { fill = a; on = '#000000'; }
  else { fill = white.c; on = '#FFFFFF'; }
  // Accent used as text or focus ring on the page.
  const text = towards(a, theme === 'dark' ? W : K, (c) => surfaces.every((s) => contrast(c, s) >= 4.5)).c;
  // Edge for filled controls (switch track): 3:1 against the card so pale accents still read.
  const edge = towards(a, theme === 'dark' ? W : K, (c) => contrast(c, surfaces[1]) >= 3 && contrast(c, surfaces[0]) >= 3).c;
  return { fill: rgbToHex(fill), on, text: rgbToHex(text), edge: rgbToHex(edge) };
}

function applyTheme(animated) {
  const theme = S.settings.theme === 'system' ? (darkMQ.matches ? 'dark' : 'light') : S.settings.theme;
  const accent = /^#[0-9a-f]{6}$/i.test(S.settings.accent) ? S.settings.accent : DEFAULT_SETTINGS.accent;
  const run = () => {
    const v = accentVars(accent, theme);
    root.dataset.theme = theme;
    root.style.setProperty('--accent', accent);
    root.style.setProperty('--accent-fill', v.fill);
    root.style.setProperty('--on-accent', v.on);
    root.style.setProperty('--accent-text', v.text);
    root.style.setProperty('--accent-edge', v.edge);
    syncHostBackground();
  };
  if (animated && document.startViewTransition && !document.hidden) document.startViewTransition(run);
  else run();
}

async function loadSettings() {
  try {
    const s = await api.get('/api/settings');
    S.settings = { ...S.settings, ...s };
    LS.set('cmm.settings', S.settings);
  } catch { /* fall back to localStorage */ }
  applyTheme(false);
  syncSettingsForm();
}

function saveSettings(patch, animated = true) {
  const themeChanged = patch.theme && patch.theme !== S.settings.theme;
  S.settings = { ...S.settings, ...patch };
  LS.set('cmm.settings', S.settings);
  applyTheme(animated && (themeChanged || 'accent' in patch));
  syncSettingsForm();
  clearTimeout(saveSettings.t);
  saveSettings.t = setTimeout(() => api.post('/api/settings', patch).catch(() => {}), 250);
}

// ---------- window host (CyberLoader.exe; docs/HOST-API.md) ----------
// Only inside the CyberLoader window does window.cyberHost exist. Without it: no window buttons.
const WIN_GLYPHS = {
  min: '<path d="M0 5.5h10"/>',
  max: '<rect x=".5" y=".5" width="9" height="9" rx="1.5"/>',
  restore: '<rect x=".5" y="2.5" width="7" height="7" rx="1.2"/><path d="M2.5 2.5V2A1.5 1.5 0 0 1 4 .5h4A1.5 1.5 0 0 1 9.5 2v4A1.5 1.5 0 0 1 8 7.5h-.5"/>',
  close: '<path d="M.5.5l9 9M9.5.5l-9 9"/>',
};
const winGlyph = (name, cls = '') => `<svg class="${cls}" width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" stroke-width="1" aria-hidden="true" focusable="false">${WIN_GLYPHS[name]}</svg>`;

function host() { return window.cyberHost || null; }

function syncHostBackground() {
  const h = host();
  if (!h) return;
  const bg = getComputedStyle(root).getPropertyValue('--bg').trim().toLowerCase();
  if (/^#[0-9a-f]{6}$/.test(bg)) { try { h.setBackground(bg); } catch { /* host gone */ } }
}

async function setupHost() {
  const q = new URLSearchParams(location.search);
  if (q.get('mock') === '1' && q.get('host') === '1') await import('./mock.js');   // installs the fake host
  const h = host();
  if (!h) return;
  try { h.frameless(true); } catch { return; }
  const box = $('#winctl');
  box.innerHTML = `
    <button class="winbtn" type="button" data-win="min" aria-label="Minimize" title="Minimize">${winGlyph('min')}</button>
    <button class="winbtn" type="button" data-win="max" aria-label="Maximize" title="Maximize">${winGlyph('max', 'g-max')}${winGlyph('restore', 'g-restore')}</button>
    <button class="winbtn is-close" type="button" data-win="close" aria-label="Close" title="Close">${winGlyph('close')}</button>`;
  box.hidden = false;
  box.addEventListener('click', (e) => {
    const b = e.target.closest('[data-win]');
    if (!b) return;
    if (b.dataset.win === 'min') h.minimize();
    else if (b.dataset.win === 'max') h.toggleMaximize();
    else h.close();
  });
  const maxBtn = box.querySelector('[data-win="max"]');
  h.onState(({ maximized }) => {
    const label = maximized ? 'Restore' : 'Maximize';
    maxBtn.setAttribute('aria-label', label);
    maxBtn.title = label;
  });
  syncHostBackground();
}

// ---------- rendering ----------
function render() {
  renderHeader();
  renderBanner();
  renderList();
  renderBar();
}

function renderHeader() {
  const st = S.st;
  $('#profileName').textContent = st ? st.profile || 'No profile' : '…';
  $('#profileBtn').title = st?.profile || '';
  const chip = $('#gameChip');
  const isRun = running();
  chip.classList.toggle('is-running', isRun);
  chip.querySelector('.chip-label').textContent = S.status === 'error' && !st ? 'Not connected' : !st ? 'Checking…' : isRun ? 'Game running' : 'Game closed';
  if (chip.tagName !== 'BUTTON') chip.title = chip.textContent.trim();   // the label is hidden at narrow widths
  if (chip.tagName === 'BUTTON') chip.setAttribute('aria-label', `${isRun ? 'Game running' : 'Game closed'}. Demo: click to simulate the game ${isRun ? 'closing' : 'starting'}.`);
  const sub = $('#pageSub');
  if (st && S.status === 'ready') {
    const on = st.mods.filter((m) => m.enabled).length;
    sub.textContent = `${nf.format(on)} of ${plural(st.mods.length, 'mod')} on · ${plural(st.deployedCount || 0, 'file')} in the game folder now`;
  } else sub.innerHTML = '&nbsp;';
}

function bannerContent() {
  if (S.lost) {
    return { kind: 'lost', cls: 'banner is-error', html: `${icon('warning', 20)}<div><div class="banner-title">Lost connection to the engine</div><div class="banner-text">Retrying every few seconds. Changes you make now may not be kept.</div></div>` };
  }
  if (S.status === 'ready' && running()) {
    return { kind: 'running', cls: 'banner', html: `${icon('warning', 20)}<div><div class="banner-title">Cyberpunk 2077 is running</div><div class="banner-text">You can still switch mods on and off. Applying them waits until the game is closed.</div></div>` };
  }
  return null;
}

/**
 * FLIP: run a layout change above the list, then spring the list from where it was on screen
 * to its new place (transform only). If the browser's scroll anchoring already kept the rows
 * still (you're scrolled down), the measured shift is zero and nothing moves.
 */
function shiftList(mutate) {
  const list = $('#list');
  const y0 = current(list).y;
  const before = list.getBoundingClientRect().top - y0;
  mutate();
  const after = list.getBoundingClientRect().top - y0;   // viewport-relative, so scroll anchoring is included
  const delta = before - after;
  if (Math.abs(delta) < 1) return;
  if (pref.reduceMotion) {
    // No slide: the rows settle in place and cross-fade so the move isn't abrupt.
    set(list, { o: 0.35 });
    animate(list, { o: 1 }, { response: 0.22 });
    return;
  }
  set(list, { y: y0 + delta });
  animate(list, { y: 0 }, { response: 0.42 });
}

function renderBanner() {
  const b = $('#banner');
  const want = bannerContent();
  const has = b.dataset.kind || '';
  const fill = () => { b.className = want.cls; b.innerHTML = want.html; b.dataset.kind = want.kind; };

  // First paint, or nothing to animate yet: just place it.
  if (!S.bannerLive) {
    if (want) { fill(); b.hidden = false; } else { b.hidden = true; b.innerHTML = ''; b.dataset.kind = ''; }
    set(b, { o: 1 });
    return;
  }
  if (want && has === want.kind) { if (b.innerHTML !== want.html) b.innerHTML = want.html; return; }
  if (want && has) { fill(); return; }                       // running <-> lost: swap in place
  if (want) {                                                 // appearing
    const wasHidden = b.hidden;
    shiftList(() => { fill(); b.hidden = false; });
    if (wasHidden) set(b, { o: 0 });
    animate(b, { o: 1 }, { response: 0.35 });
    return;
  }
  if (has) {                                                  // leaving: fade, then close the gap
    b.dataset.kind = '';
    animate(b, { o: 0 }, { response: 0.12 }).then((done) => {
      if (!done || b.dataset.kind) return;
      shiftList(() => { b.hidden = true; b.innerHTML = ''; });
    });
  }
}

function skeletonHTML() {
  const row = (w) => `<div class="sk-row"><div class="sk-lines"><div class="sk" style="width:${w}%"></div><div class="sk" style="width:14%;height:10px"></div></div><div class="sk-switch"></div></div>`;
  const group = (n, seed) => `<div class="sk sk-head"></div><div class="card" aria-hidden="true">${Array.from({ length: n }, (_, i) => row(30 + ((i * 17 + seed) % 40))).join('')}</div>`;
  return `<div aria-busy="true" aria-label="Loading mods">${group(5, 3)}${group(4, 11)}</div>`;
}

function stateHTML({ iconName, title, text, error = false, action = null }) {
  return `<div class="state"><div class="state-icon${error ? ' is-error' : ''}">${icon(iconName, 26)}</div>
    <h2 class="state-title">${esc(title)}</h2><p class="state-text">${esc(text)}</p>
    ${action ? `<button class="btn" type="button" data-action="${action.id}">${esc(action.label)}</button>` : ''}</div>`;
}

let rowIndex = 0;
const rowSig = new Map(); // mod id -> signature of what its row currently shows (lets patchList() touch only rows that changed)

// The text part of a row (name, meta line, warning) plus the conflict mark. The switch button is kept separate so it
// can stay in the DOM while everything around it changes: replacing it would cancel its animation and drop fast clicks.
function rowTextHTML(m, showGroup, i) {
  const warn = warningFor(m);
  const meta = [];
  if (m.pending) meta.push(`<span class="meta-pending">${m.pending === 'on' ? 'Turning on' : 'Turning off'}</span>`);
  meta.push(plural(m.files, 'file'));
  if (showGroup) meta.push(esc(m.group));
  const conflict = m.enabled && m.conflicts > 0;
  const conflictText = conflict ? `Shares ${plural(m.conflicts, 'file')} with other mods that are on` : '';
  return {
    warn,
    html: `<div class="row-text">
      <div class="row-name" id="rn-${i}" title="${esc(m.name)}"><span class="row-name-text">${esc(m.name)}</span>${m.framework ? `<span class="core-mark" title="Core dependency">${icon('core', 14)}<span class="sr-only">, core dependency</span></span>` : ''}</div>
      <div class="row-meta" id="rm-${i}">${meta.join('<span class="sep" aria-hidden="true"> · </span>')}${conflict ? `<span class="sr-only">. ${conflictText}</span>` : ''}</div>
      ${warn ? `<div class="row-warn" id="rw-${i}">${icon('warning', 14)}<span title="${esc(warn)}">${esc(warn)}</span></div>` : ''}
    </div>
    ${conflict ? `<span class="conflict-mark" title="${esc(conflictText)}">${icon('conflict', 16)}</span>` : ''}`,
  };
}

function rowSignature(m, text) { return `${m.enabled}|${S.bar === 'applying'}|${text.html}`; }

function rowHTML(m, showGroup) {
  const i = rowIndex++;
  const text = rowTextHTML(m, showGroup, i);
  const busy = S.bar === 'applying';
  rowSig.set(m.id, rowSignature(m, text));
  return `<li class="row${m.enabled ? ' is-on' : ''}" data-id="${esc(m.id)}" data-i="${i}" data-sg="${showGroup ? 1 : 0}"${busy ? ' aria-disabled="true"' : ''}>
    ${text.html}
    <button class="switch" type="button" role="switch" aria-checked="${m.enabled}" aria-labelledby="rn-${i}" aria-describedby="rm-${i}${text.warn ? ` rw-${i}` : ''}"${busy ? ' aria-disabled="true"' : ''} data-nav data-key="mod:${esc(m.id)}" tabindex="-1"></button>
  </li>`;
}

// Update the rows (and group headers) that changed, in place. Used for toggles so the switch animates and the
// element under the pointer is never replaced between press and release.
function patchList() {
  if (S.status !== 'ready') { renderList(); return; }
  const idsKey = mods().map((m) => m.id).join('\n');
  if (idsKey !== patchList.ids) { renderList(); return; }   // mods were added or removed: rebuild once
  const list = $('#list');
  const busy = S.bar === 'applying';
  for (const li of list.querySelectorAll('li.row')) {
    const m = byId(li.dataset.id);
    if (!m) continue;
    const i = li.dataset.i;
    const text = rowTextHTML(m, li.dataset.sg === '1', i);
    const sig = rowSignature(m, text);
    if (rowSig.get(m.id) === sig) continue;
    rowSig.set(m.id, sig);
    li.classList.toggle('is-on', m.enabled);
    if (busy) li.setAttribute('aria-disabled', 'true'); else li.removeAttribute('aria-disabled');
    const sw = li.querySelector('.switch');
    sw.setAttribute('aria-checked', String(m.enabled));
    sw.setAttribute('aria-describedby', `rm-${i}${text.warn ? ` rw-${i}` : ''}`);
    if (busy) sw.setAttribute('aria-disabled', 'true'); else sw.removeAttribute('aria-disabled');
    for (const el of li.querySelectorAll(':scope > .row-text, :scope > .conflict-mark')) el.remove();
    sw.insertAdjacentHTML('beforebegin', text.html);
  }
  const all = mods();
  for (const btn of list.querySelectorAll('.group-toggle[data-group]')) {
    const gm = all.filter((m) => (GROUPS.includes(m.group) ? m.group : 'Other') === btn.dataset.group);
    const gs = groupStats(gm);
    const el = btn.querySelector('.group-count');
    if (el && el.innerHTML !== gs.html) el.innerHTML = gs.html;
    const bar = btn.querySelector('.group-meter i');
    if (bar) bar.style.width = `${gs.pct}%`;
  }
}

const GROUP_ICON = { Framework: 'core', Body: 'body', Characters: 'characters', Clothing: 'clothing', Gameplay: 'gameplay', Content: 'content', Other: 'other' };

// "16 of 26 on" (plus "4 changing") and the width of the little meter, for one group's mods.
function groupStats(gm) {
  const on = gm.filter((m) => m.enabled).length;
  const changing = gm.filter((m) => m.pending).length;
  return {
    html: `${changing ? `<span class="changing">${nf.format(changing)} changing</span> · ` : ''}${nf.format(on)} of ${nf.format(gm.length)} on`,
    pct: gm.length ? Math.round((on / gm.length) * 100) : 0,
  };
}

function renderList() {
  const list = $('#list');
  const active = document.activeElement;
  const focusKey = list.contains(active) ? active.dataset.key : null;
  rowIndex = 0;
  rowSig.clear();
  patchList.ids = mods().map((m) => m.id).join('\n');

  if (S.status === 'loading') { list.innerHTML = skeletonHTML(); return; }
  if (S.status === 'error') {
    list.innerHTML = stateHTML({ iconName: 'warning', error: true, title: 'Can’t load your mods', text: S.error?.message || 'Something went wrong.', action: { id: 'retry', label: 'Try again' } });
    return;
  }
  const all = mods();
  if (!all.length) {
    list.innerHTML = stateHTML({ iconName: 'import', title: 'Your library is empty', text: 'Drag a mod archive or folder anywhere onto this window to add it.' });
    return;
  }

  const q = S.query.trim().toLowerCase();
  let html = '';
  if (q) {
    const terms = q.split(/\s+/);
    const hits = all.filter((m) => terms.every((t) => `${m.name} ${m.group}`.toLowerCase().includes(t)));
    hits.sort((a, b) => (b.name.toLowerCase().startsWith(q) - a.name.toLowerCase().startsWith(q)) || a.name.localeCompare(b.name));
    html = hits.length
      ? `<section class="group" aria-label="Search results"><h2 class="group-title-static">${plural(hits.length, 'result')}</h2><ul class="card">${hits.map((m) => rowHTML(m, true)).join('')}</ul></section>`
      : stateHTML({ iconName: 'search', title: `No mods match “${S.query.trim()}”`, text: 'Check the spelling, or press Esc to clear the search.' });
  } else {
    GROUPS.forEach((g, gi) => {
      const gm = all.filter((m) => (GROUPS.includes(m.group) ? m.group : 'Other') === g).sort((a, b) => a.name.localeCompare(b.name));
      if (!gm.length) return;
      const collapsed = S.collapsed.has(g);
      const gs = groupStats(gm);
      html += `<section class="group">
        <h2 class="group-head"><button class="group-toggle" type="button" data-nav data-key="group:${g}" data-group="${g}" tabindex="-1" aria-expanded="${!collapsed}" aria-controls="grp-${gi}">
          <span class="group-icon">${icon(GROUP_ICON[g] || 'other', 18)}</span>
          <span class="group-text"><span class="group-name">${g}</span><span class="group-count">${gs.html}</span></span>
          <span class="group-meter" aria-hidden="true"><i style="width:${gs.pct}%"></i></span>
          ${icon('chevronRight', 16, 'chev')}
        </button></h2>
        <ul class="card" id="grp-${gi}"${collapsed ? ' hidden' : ''}>${collapsed ? '' : gm.map((m) => rowHTML(m, false)).join('')}</ul>
      </section>`;
    });
  }
  list.innerHTML = html;
  applyRoving(focusKey);
}

function navItems() { return [...$('#list').querySelectorAll('[data-nav]')]; }

function applyRoving(focusKey) {
  const items = navItems();
  if (!items.length) return;
  let cur = items.find((n) => n.dataset.key === (focusKey || S.navKey)) || items[0];
  for (const n of items) n.tabIndex = n === cur ? 0 : -1;
  S.navKey = cur.dataset.key;
  if (focusKey) cur.focus({ preventScroll: true });
}

function focusNav(el) {
  for (const n of navItems()) n.tabIndex = -1;
  el.tabIndex = 0;
  S.navKey = el.dataset.key;
  el.focus({ preventScroll: true });
  (el.closest('.row') || el).scrollIntoView({ block: 'nearest' });
}

function focusListFallback() {
  const items = navItems();
  const el = items.find((n) => n.tabIndex === 0) || items[0];
  if (el) el.focus({ preventScroll: true }); else $('#search').focus();
}
setFallbackFocus(focusListFallback);

// ---------- pending bar ----------
function renderBar() {
  const p = pending();
  const view = S.bar || (S.status === 'ready' && p.total > 0 ? 'pending' : null);
  if (!view) { hideBar(); return; }

  if (view === 'pending') {
    const parts = [];
    if (p.on) parts.push(`${nf.format(p.on)} on`);
    if (p.off) parts.push(`${nf.format(p.off)} off`);
    $('#barSummary').innerHTML = parts.join('<span class="dim"> · </span>');
    $('#barSummary').setAttribute('aria-label', [p.on && `${plural(p.on, 'mod')} turning on`, p.off && `${plural(p.off, 'mod')} turning off`].filter(Boolean).join(', '));
    const reason = $('#barReason');
    if (running()) {
      reason.className = 'bar-sub is-blocked';
      reason.innerHTML = `${icon('warning', 14)}<span>Close the game to apply</span>`;
    } else {
      reason.className = 'bar-sub';
      reason.innerHTML = `<span>Nothing changes in the game until you apply</span>`;
    }
    $('#applyBtn').setAttribute('aria-disabled', String(running()));
  }
  showBar(view);
}

function showBar(view) {
  const bar = $('#bar');
  const first = bar.hidden || bar.dataset.open !== 'true';
  bar.dataset.open = 'true';
  if (bar.hidden) { bar.hidden = false; set(bar, { y: 32, s: 0.96, o: 0 }); }
  if (first) animate(bar, { y: 0, s: 1, o: 1 }, { response: 0.45 });
  switchBarView(view, first);
}

function hideBar() {
  const bar = $('#bar');
  if (bar.dataset.open !== 'true') return;
  bar.dataset.open = 'false';
  if (bar.contains(document.activeElement)) focusListFallback();
  animate(bar, { y: 32, s: 0.96, o: 0 }, { response: 0.32 }).then((done) => {
    if (done && bar.dataset.open === 'false') bar.hidden = true;
  });
}

function switchBarView(name, instant) {
  const bar = $('#bar');
  if (bar.dataset.view === name && !instant) return;
  bar.dataset.view = name;
  for (const v of bar.querySelectorAll('.bar-view')) {
    if (v.dataset.view === name) {
      v.inert = false;
      if (v.hidden) { v.hidden = false; set(v, { o: instant ? 1 : 0 }); }
      animate(v, { o: 1 }, { response: 0.3 });
    } else if (!v.hidden) {
      v.inert = true;
      if (instant) { v.hidden = true; continue; }
      animate(v, { o: 0 }, { response: 0.2 }).then((done) => { if (done && bar.dataset.view !== v.dataset.view) v.hidden = true; });
    }
  }
}

// ---------- actions ----------
async function load() {
  S.status = 'loading';
  render();
  try {
    const st = await api.get('/api/state');
    setState(st);
    S.status = 'ready';
  } catch (e) {
    S.status = 'error';
    S.error = e;
  }
  render();
}

function setState(st) {
  S.st = st;
  S.lastJson = JSON.stringify(st);
}

async function refresh() {
  const st = await api.get('/api/state');
  setState(st);
  render();
}

// Toggles are sent one at a time, in click order, and only the newest answer for a mod may change what the switch shows.
// (Otherwise a slow reply to an earlier click could flip the switch back, which looked like the app clicking by itself.)
let toggleQueue = Promise.resolve();
const toggleSeq = new Map();

function toggleMod(id) {
  const m = byId(id);
  if (!m || S.bar === 'applying') return;
  const next = !m.enabled;
  const prev = { enabled: m.enabled, pending: m.pending };
  m.enabled = next;
  m.pending = m.pending ? null : next ? 'on' : 'off';
  patchList(); renderBar(); renderHeader();
  const seq = (toggleSeq.get(id) || 0) + 1;
  toggleSeq.set(id, seq);
  S.inflight++;
  toggleQueue = toggleQueue.then(async () => {
    try {
      const r = await api.post('/api/toggle', { id, enabled: next });
      const cur = byId(id);
      if (cur && toggleSeq.get(id) === seq && r.mod) Object.assign(cur, r.mod);
      if (r.warnings?.length) announce(r.warnings.join('. '));
    } catch (e) {
      const cur = byId(id);
      if (cur && toggleSeq.get(id) === seq) Object.assign(cur, prev);
      toast(e.message, { tone: 'error', timeout: 5000 });
    } finally {
      S.inflight--;
      S.lastJson = JSON.stringify(S.st);
      patchList(); renderBar(); renderHeader();
    }
    // Once rapid toggles settle, re-sync: other mods' conflict counts and profileDirty change too.
    if (!S.inflight) {
      clearTimeout(toggleMod.sync);
      toggleMod.sync = setTimeout(async () => {
        if (S.inflight || S.bar === 'applying') return;
        try {
          const st = await api.get('/api/state');
          if (!S.inflight && JSON.stringify(st) !== S.lastJson) { setState(st); patchList(); renderBar(); renderHeader(); }
        } catch { /* the poll will retry */ }
      }, 150);
    }
  });
  return toggleQueue;
}

function toggleGroup(g) {
  if (S.collapsed.has(g)) S.collapsed.delete(g); else S.collapsed.add(g);
  LS.set('cmm.collapsed', [...S.collapsed]);
  renderList();
}

// ----- Apply -----
async function startApply(trigger) {
  if (running()) {
    announce('Close the game to apply.');
    return;
  }
  if (S.bar === 'applying') return;
  let add = 0, remove = 0;
  for (const m of mods()) { if (m.pending === 'on') add += m.files; if (m.pending === 'off') remove += m.files; }
  S.applyTotals = { add, remove };
  try {
    await api.post('/api/apply');
  } catch (e) {
    if (e.status !== 423) { showApplyError(e.message); return; }
  }
  if (isOpen($('#previewSheet'))) closeTop();
  S.bar = 'applying';
  set($('#progFill'), { sx: 0 });
  setProgress({ percent: 0, text: 'Starting…' });
  renderList(); renderBar();
  const keyboard = trigger && trigger.matches(':focus-visible');
  $('#progBar').focus({ preventScroll: true });
  if (!keyboard) $('#progBar').blur();
  pollProgress();
}

function setProgress(p) {
  const pct = Math.max(0, Math.min(100, Math.round(p.percent || 0)));
  $('#progText').textContent = p.text || 'Applying…';
  $('#progPct').textContent = `${pct}%`;
  $('#progBar').setAttribute('aria-valuenow', String(pct));
  animate($('#progFill'), { sx: pct / 100 }, { response: 0.5 });
}

async function pollProgress() {
  let failures = 0;
  while (S.bar === 'applying') {
    let p;
    try { p = await api.get('/api/progress'); failures = 0; }
    catch { if (++failures > 20) { showApplyError('Lost contact with the engine while applying. Check the game folder before playing.'); return; } await sleep(500); continue; }
    if (p.state === 'running' || p.state === 'idle') { setProgress(p); await sleep(200); continue; }
    if (p.state === 'done') { setProgress(p); await sleep(250); await applySucceeded(p); return; }
    if (p.state === 'error') { showApplyError(p.text || 'Something went wrong while applying.'); await refresh().catch(() => {}); return; }
  }
}

async function applySucceeded(p) {
  S.bar = 'done';
  const t = S.applyTotals || { add: 0, remove: 0 };
  $('#doneText').textContent = [t.add && `${plural(t.add, 'file')} linked`, t.remove && `${plural(t.remove, 'link')} removed`].filter(Boolean).join(' · ') || p.text || 'The game folder is up to date';
  try { await refresh(); } catch { renderBar(); }
  announce('Applied. The game folder is up to date.');
  // The success moment: badge settles in, a soft halo blooms out and fades.
  const badge = $('#badge'), halo = $('#halo');
  set(badge, { s: 0.4, o: 0 });
  set(halo, { s: 1, o: 0.45 });
  animate(badge, { s: 1, o: 1 }, { response: 0.5 });
  animate(halo, { s: 2.4, o: 0 }, { response: 1.1 });
  if ($('#bar').contains(document.activeElement)) focusListFallback();
  await sleep(2200);
  if (S.bar === 'done') { S.bar = null; renderBar(); }
}

function showApplyError(msg) {
  S.bar = 'error';
  $('#errText').textContent = msg;
  $('#errText').title = msg;
  renderList(); renderBar();
  announce(`Couldn’t apply. ${msg}`);
}

// ----- Preview sheet -----
async function openPreview(trigger) {
  const sheet = $('#previewSheet');
  const body = $('#pvBody');
  body.innerHTML = `<div aria-busy="true"><div class="stats">${'<div class="stat"><div class="sk" style="width:50%;height:20px"></div><div class="sk" style="width:70%;height:10px;margin-top:8px"></div></div>'.repeat(3)}</div><div class="sk" style="width:30%;margin:18px 2px 10px"></div><div class="pv-list">${'<div class="sk-row"><div class="sk-lines"><div class="sk" style="width:55%"></div></div></div>'.repeat(3)}</div></div>`;
  syncPreviewFoot();
  openModal(sheet, { trigger, initialFocus: '[data-close]' });
  try {
    const p = await api.post('/api/preview');
    if (isOpen(sheet)) body.innerHTML = previewHTML(p);
  } catch (e) {
    body.innerHTML = `<div class="callout">${icon('warning', 18)}<span>${esc(e.message)}</span></div>`;
  }
}

function syncPreviewFoot() {
  const isRun = running();
  $('#pvApply').setAttribute('aria-disabled', String(isRun));
  $('#pvReason').textContent = isRun ? 'Close the game to apply' : '';
  $('#pvDiscard').hidden = pending().total === 0;
}

function pathList(paths, cap = 150) {
  const shown = paths.slice(0, cap);
  return `<ul class="paths">${shown.map((p) => `<li>${esc(p)}</li>`).join('')}${paths.length > cap ? `<li class="more">and ${nf.format(paths.length - cap)} more</li>` : ''}</ul>`;
}

function previewHTML(p) {
  const name = (id) => byId(id)?.name || id;
  const filesBy = (arr) => { const m = new Map(); for (const f of arr || []) { if (!m.has(f.id)) m.set(f.id, []); m.get(f.id).push(f.path); } return m; };
  const addBy = filesBy(p.files?.add), remBy = filesBy(p.files?.remove);
  const on = mods().filter((m) => m.pending === 'on').sort((a, b) => a.name.localeCompare(b.name));
  const off = mods().filter((m) => m.pending === 'off').sort((a, b) => a.name.localeCompare(b.name));
  const conflictFiles = new Set((p.conflicts || []).map((c) => c.path)).size;

  const modItem = (m, paths, kind) => {
    const sign = `<span class="pv-sign ${kind}">${icon(kind === 'add' ? 'plusCircle' : 'minusCircle', 18)}</span>`;
    const meta = `<span class="pv-meta">${plural(m.files, 'file')}</span>`;
    if (!paths?.length) return `<div class="pv-item"><div class="pv-line">${sign}<span class="pv-name">${esc(m.name)}</span>${meta}<span class="pv-chev-space"></span></div></div>`;
    return `<details class="pv-item"><summary>${sign}<span class="pv-name">${esc(m.name)}</span>${meta}${icon('chevronRight', 16, 'chev')}</summary>${pathList(paths)}</details>`;
  };

  const groups = new Map();
  for (const c of p.conflicts || []) {
    const key = `${c.winner}|${[...c.losers].sort().join(',')}`;
    if (!groups.has(key)) groups.set(key, { winner: c.winner, losers: c.losers, paths: [] });
    groups.get(key).paths.push(c.path);
  }

  let html = `<div class="stats">
    <div class="stat"><div class="stat-num">${nf.format(p.add || 0)}</div><div class="stat-label">${(p.add || 0) === 1 ? 'file' : 'files'} to link</div></div>
    <div class="stat"><div class="stat-num">${nf.format(p.remove || 0)}</div><div class="stat-label">${(p.remove || 0) === 1 ? 'link' : 'links'} to remove</div></div>
    <div class="stat"><div class="stat-num">${nf.format(conflictFiles)}</div><div class="stat-label">${conflictFiles === 1 ? 'file' : 'files'} in conflict</div></div>
  </div>`;

  if (p.warnings?.length) {
    // Collapse "X is off but Y needs it" into one line per X; keep any other wording as-is.
    const needs = new Map();
    const other = [];
    for (const w of p.warnings) {
      const m = /^(.+?) is off but (.+?) needs it\.?$/.exec(w);
      if (m) { if (!needs.has(m[1])) needs.set(m[1], []); needs.get(m[1]).push(m[2]); } else other.push(w);
    }
    const lines = [
      ...[...needs].map(([dep, users]) => users.length === 1
        ? `<div class="callout">${icon('warning', 18)}<span>${esc(dep)} is off but ${esc(users[0])} needs it</span></div>`
        : `<details class="callout callout-more"><summary>${icon('warning', 18)}<span><strong>${esc(dep)}</strong> is off but ${users.length} mods need it</span>${icon('chevronRight', 16, 'chev')}</summary><ul class="callout-list">${users.map((u) => `<li>${esc(u)}</li>`).join('')}</ul></details>`),
      ...other.map((w) => `<div class="callout">${icon('warning', 18)}<span>${esc(w)}</span></div>`),
    ];
    html += `<section class="pv-section"><h3 class="pv-heading">Warnings <span class="count">${lines.length}</span></h3>${lines.join('')}</section>`;
  }
  if (on.length) html += `<section class="pv-section"><h3 class="pv-heading">Turning on <span class="count">${on.length}</span></h3><div class="pv-list">${on.map((m) => modItem(m, addBy.get(m.id), 'add')).join('')}</div></section>`;
  if (off.length) html += `<section class="pv-section"><h3 class="pv-heading">Turning off <span class="count">${off.length}</span></h3><div class="pv-list">${off.map((m) => modItem(m, remBy.get(m.id), 'remove')).join('')}</div></section>`;
  if (groups.size) {
    html += `<section class="pv-section"><h3 class="pv-heading">Conflicts <span class="count">${groups.size}</span></h3><div class="pv-list">${[...groups.values()].map((g) => `
      <details class="pv-item"><summary><span class="pv-sign remove">${icon('conflict', 18)}</span>
        <span class="pv-name">${esc(name(g.winner))} <span class="quiet">wins over ${esc(listNames(g.losers.map(name)))}</span></span>
        <span class="pv-meta">${plural(g.paths.length, 'file')}</span>${icon('chevronRight', 16, 'chev')}</summary>${pathList(g.paths)}</details>`).join('')}</div>
      <p class="pv-note">When two mods ship the same file, the winner’s copy is the one placed in the game.</p></section>`;
  }
  if (!on.length && !off.length) html += `<p class="pv-empty">The game folder already matches this profile.</p>`;
  if (p.filesTruncated) html += `<p class="pv-note">File lists are shortened. The counts above are complete.</p>`;
  return html;
}

async function discardChanges() {
  const layer = isOpen($('#previewSheet'));
  try {
    let st;
    try { st = await api.post('/api/discard'); }
    catch (e) {
      if (e.status !== 404) throw e;
      // Engine without /api/discard: toggle each staged change back.
      for (const m of mods().filter((x) => x.pending)) await api.post('/api/toggle', { id: m.id, enabled: !m.enabled });
      st = await api.get('/api/state');
    }
    if (st?.mods) setState(st); else await refresh();
    if (layer) closeTop();
    render();
    toast('Changes discarded. The list matches the game again.', { tone: 'ok' });
  } catch (e) {
    toast(e.message, { tone: 'error', timeout: 5000 });
  }
}

// ----- Profiles and the overflow menu -----
function renderProfileMenu() {
  const st = S.st;
  const menu = $('#profileMenu');
  const names = st?.profiles || [];
  const onlyOne = names.length <= 1;
  const rows = names.map((name) => {
    const cur = name === st.profile;
    return `<div class="menu-row" role="none">
      <button class="menu-item" type="button" role="menuitemradio" aria-checked="${cur}" data-profile="${esc(name)}" tabindex="-1">
        <span class="check-slot">${cur ? icon('check', 18) : ''}</span>
        <span class="label"><span>${esc(name)}</span></span>
        ${cur && st.profileDirty ? '<span class="tag">Edited</span>' : ''}
      </button>
      <button class="menu-icon" type="button" role="menuitem" data-profile-act="rename" data-profile="${esc(name)}" aria-label="Rename “${esc(name)}”" title="Rename" tabindex="-1">${icon('pencil', 16)}</button>
      <button class="menu-icon is-danger" type="button" role="menuitem" data-profile-act="delete" data-profile="${esc(name)}" aria-label="Delete “${esc(name)}”" title="${onlyOne ? 'You need at least one profile' : 'Delete'}"${onlyOne ? ' aria-disabled="true"' : ''} tabindex="-1">${icon('trash', 16)}</button>
    </div>`;
  }).join('') || '<div class="menu-item" aria-disabled="true">No profiles yet</div>';
  // Saving edits to the selected profile only shows up when there is something to save.
  const save = st?.profile && st.profileDirty
    ? `<div class="menu-sep" role="separator"></div>
       <button class="menu-item" type="button" role="menuitem" data-profile-act="save" data-profile="${esc(st.profile)}" tabindex="-1">${icon('save', 18)}<span class="label"><span>Save changes to “${esc(st.profile)}”</span></span></button>`
    : '';
  menu.innerHTML = rows + save;
}

// The "..." menu is only for app-level things; everything about profiles lives in the profile menu and the "+" button.
function renderMoreMenu() {
  const item = (act, ic, label) =>
    `<button class="menu-item" type="button" role="menuitem" data-act="${act}" tabindex="-1">${icon(ic, 18)}<span class="label"><span>${esc(label)}</span></span></button>`;
  $('#moreMenu').innerHTML = [item('history', 'restore', 'Setup history…'), item('trash', 'trash', 'Deleted mods…'), item('appearance', 'appearance', 'Appearance…')].join('');
}

// ---------- Deleting mods: an in-app trash ----------
const fmtSize = (b) => (b >= 1073741824 ? `${(b / 1073741824).toFixed(1)} GB` : b >= 1048576 ? `${Math.round(b / 1048576)} MB` : `${Math.max(1, Math.round(b / 1024))} KB`);

async function deleteMod(id, trigger) {
  const m = byId(id);
  if (!m) return;
  const r = await dialog({
    title: `Move “${m.name}” to the trash?`,
    message: 'It leaves your library but is kept in the trash until you empty it, so you can restore it. Nothing in the game folder changes.',
    confirm: 'Move to trash', destructive: true, trigger,
  });
  if (!r) return;
  try {
    await api.post('/api/mod/delete', { id });
    await refresh();
    toast(`Moved “${m.name}” to the trash`, { tone: 'ok' });
    focusListFallback();
  } catch (e) {
    toast(e.message, { tone: 'error', timeout: 6000 });
  }
}

function trashHTML(t) {
  const sub = $('#trSub');
  const n = t.items.length;
  sub.textContent = n ? `${n} ${n === 1 ? 'mod' : 'mods'} · ${fmtSize(t.totalSize)}. Kept here until you empty the trash.` : 'Kept here until you empty the trash.';
  $('#trEmpty').toggleAttribute('hidden', !n);
  if (!n) return '<p class="trash-empty">Nothing in the trash.</p>';
  return `<div class="trash-list">${t.items.map((i) => `
    <div class="trash-row" data-trash="${esc(i.id)}">
      <div class="trash-text"><div class="trash-name" title="${esc(i.name)}">${esc(i.name)}</div>
        <div class="trash-meta">${plural(i.files, 'file')} · ${fmtSize(i.size)} · deleted ${esc(i.deletedAt)}</div></div>
      <div class="trash-actions">
        <button class="btn btn-quiet" type="button" data-trash-act="restore">Restore</button>
        <button class="btn btn-quiet is-danger" type="button" data-trash-act="forever">Delete forever</button>
      </div></div>`).join('')}</div>`;
}

async function loadTrash() {
  const t = await api.get('/api/trash');
  S.trash = t;
  $('#trBody').innerHTML = trashHTML(t);
  return t;
}

async function openTrash(trigger) {
  await loadTrash();
  openModal($('#trashSheet'), { trigger, initialFocus: '[data-close]' });
}

async function trashClick(e) {
  const b = e.target.closest('[data-trash-act]');
  if (!b) return;
  const row = b.closest('[data-trash]');
  const item = S.trash?.items.find((i) => i.id === row.dataset.trash);
  if (!item) return;
  try {
    if (b.dataset.trashAct === 'restore') {
      await api.post('/api/trash/restore', { id: item.id });
      await loadTrash();
      await refresh();
      toast(`Restored “${item.name}”`, { tone: 'ok' });
    } else {
      const r = await dialog({
        title: `Delete “${item.name}” forever?`,
        message: `This erases ${fmtSize(item.size)} from your computer and can’t be undone.`,
        confirm: 'Delete forever', destructive: true, trigger: b,
      });
      if (!r) return;
      await api.post('/api/trash/empty', { id: item.id });
      await loadTrash();
      toast(`Deleted “${item.name}” forever`, { tone: 'ok' });
    }
  } catch (err) {
    toast(err.message, { tone: 'error', timeout: 6000 });
  }
}

async function emptyTrash(trigger) {
  const t = S.trash;
  if (!t?.items.length) return;
  const r = await dialog({
    title: 'Empty the trash?',
    message: `${t.items.length} ${t.items.length === 1 ? 'mod' : 'mods'} (${fmtSize(t.totalSize)}) will be erased from your computer. This can’t be undone.`,
    confirm: 'Empty trash', destructive: true, trigger,
  });
  if (!r) return;
  try {
    await api.post('/api/trash/empty', {});
    await loadTrash();
    toast('Trash emptied', { tone: 'ok' });
  } catch (e) {
    toast(e.message, { tone: 'error', timeout: 6000 });
  }
}

function openRowMenu(li, x) {
  const id = li.dataset.id;
  const m = byId(id);
  if (!m) return;
  const menu = $('#rowMenu');
  menu.dataset.id = id;
  menu.innerHTML = `<button class="menu-item" type="button" role="menuitem" data-row-act="needs" tabindex="-1">${icon('core', 18)}<span class="label"><span>What it needs…</span></span></button>
    <button class="menu-item" type="button" role="menuitem" data-row-act="group" tabindex="-1">${icon('other', 18)}<span class="label"><span>Move to category…</span></span></button>
    <div class="menu-sep" role="separator"></div>
    <button class="menu-item is-danger" type="button" role="menuitem" data-row-act="delete" tabindex="-1">${icon('trash', 18)}<span class="label"><span>Move “${esc(m.name)}” to trash…</span></span></button>`;
  openPopover(menu, li.querySelector('.switch') || li, { align: 'end' });
}

// ---------- Setup history: snapshots saved after every apply ----------
const fmtWhen = (at) => {
  const d = new Date(String(at).replace(' ', 'T'));
  return Number.isNaN(d.getTime()) ? String(at) : d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
};
const fmtDay = (day) => {
  const d = new Date(`${day}T00:00:00`);
  return Number.isNaN(d.getTime()) ? day : d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
};
const nexusUrl = (id) => `https://www.nexusmods.com/cyberpunk2077/mods/${id}`;
const histOpen = new Set();   // snapshot ids whose details are showing

function histTitle(i) { return i.name || `Applied ${fmtWhen(i.at)}`; }

function histRowHTML(i) {
  const bits = [];
  if (i.name) bits.push(esc(fmtWhen(i.at)));
  bits.push(esc(i.profile || 'No profile'), `${plural(i.count, 'mod')} on`);
  const diff = [];
  if (i.turnOn) diff.push(`Turns on ${plural(i.turnOn, 'mod')}`);
  if (i.turnOff) diff.push(`Turns off ${plural(i.turnOff, 'mod')}`);
  const flags = [];
  if (i.missing) flags.push(`<span class="hist-flag">${plural(i.missing, 'mod')} not in your library now</span>`);
  if (i.changed) flags.push(`<span class="hist-flag">${plural(i.changed, 'mod')} changed since</span>`);
  const open = histOpen.has(i.id);
  return `<div class="hist-row" data-snap="${esc(i.id)}">
    <div class="hist-main">
      <div class="hist-text">
        <div class="hist-title">${esc(histTitle(i))}${i.pinned ? '<span class="needs-tag">Kept</span>' : ''}</div>
        <div class="hist-meta">${bits.join('<span class="sep" aria-hidden="true"> · </span>')}</div>
        <div class="hist-meta">${diff.length ? esc(diff.join(' · ')) : 'Same mods as now'}</div>
        ${flags.length ? `<div class="hist-flags">${flags.join('')}</div>` : ''}
      </div>
      <div class="hist-actions">
        <button class="btn btn-quiet" type="button" data-hist-act="details" aria-expanded="${open}">${open ? 'Hide details' : 'Details'}</button>
        <button class="btn btn-quiet" type="button" data-hist-act="restore">Restore</button>
      </div>
    </div>
    <div class="hist-detail" ${open ? '' : 'hidden'}></div>
  </div>`;
}

function histDetailHTML(d) {
  const differs = d.mods.filter((m) => m.status !== 'same');
  const same = d.mods.length - differs.length;
  const line = (m) => {
    const ver = m.version ? `version ${esc(m.version)}` : '';
    const when = m.date ? ` (${esc(fmtDay(m.date))})` : '';
    const nx = m.nexusId ? `<button class="link-btn" type="button" data-hist-act="copy" data-url="${esc(nexusUrl(m.nexusId))}">Copy Nexus link (mod ${m.nexusId})</button>` : '';
    if (m.status === 'changed') {
      return `<li><b>${esc(m.name)}</b>: its files changed since this setup${ver ? ` (it was ${ver}${m.date ? `, ${esc(fmtDay(m.date))}` : ''})` : ''}. ${nx}</li>`;
    }
    const now = m.replacedBy
      ? `You have ${m.replacedBy.version ? `version ${esc(m.replacedBy.version)}` : 'a newer copy'}${m.replacedBy.date ? ` (${esc(fmtDay(m.replacedBy.date))})` : ''} now.`
      : m.inTrash ? 'It is in Deleted mods, restore it from there.' : 'It is not in your library any more.';
    return `<li><b>${esc(m.name)}</b>: this setup used ${ver ? `${ver}${when}` : 'an older copy'}. ${now} ${nx}</li>`;
  };
  return `${differs.length ? `<p class="hist-lead">Different from your library now</p><ul class="hist-list">${differs.map(line).join('')}</ul>` : '<p class="hist-lead">Every mod in it is in your library, unchanged.</p>'}
    <p class="hist-meta">${same ? `${plural(same, 'other mod')} unchanged. ` : ''}Older setups are moved aside after the newest 200, never erased.</p>`;
}

function histBodyHTML(items) {
  $('#hsSub').textContent = items.length
    ? `${plural(items.length, 'setup')}. A new one is saved every time you apply.`
    : 'A setup is saved every time you apply. Restore one to get that list of mods back.';
  if (!items.length) return '<p class="trash-empty">Nothing yet. Your first setup is saved the next time you apply.</p>';
  return `<div class="hist-all">${items.map(histRowHTML).join('')}</div>`;
}

async function loadHistory() {
  const r = await api.get('/api/snapshots');
  S.history = r.items;
  $('#hsBody').innerHTML = histBodyHTML(r.items);
  for (const id of histOpen) fillHistDetail(id);
  return r;
}

async function fillHistDetail(id) {
  const row = $(`#hsBody [data-snap="${CSS.escape(id)}"]`);
  if (!row) return;
  const box = row.querySelector('.hist-detail');
  try {
    box.innerHTML = histDetailHTML(await api.get(`/api/snapshots/${id}`));
  } catch (e) {
    box.innerHTML = `<p class="hist-meta">${esc(e.message)}</p>`;
  }
}

async function openHistory(trigger) {
  histOpen.clear();
  await loadHistory();
  openModal($('#historySheet'), { trigger, initialFocus: '[data-close]' });
}

async function copyText(text) {
  try { await navigator.clipboard.writeText(text); return true; } catch { return false; }
}

async function historyClick(e) {
  const b = e.target.closest('[data-hist-act]');
  if (!b) return;
  const row = b.closest('[data-snap]');
  const id = row?.dataset.snap;
  const item = S.history?.find((i) => i.id === id);
  const act = b.dataset.histAct;
  try {
    if (act === 'details') {
      const detail = row.querySelector('.hist-detail');
      const open = detail.hidden;
      detail.hidden = !open;
      b.textContent = open ? 'Hide details' : 'Details';
      b.setAttribute('aria-expanded', String(open));
      if (open) { histOpen.add(id); detail.innerHTML = '<p class="hist-meta">Loading…</p>'; await fillHistDetail(id); } else histOpen.delete(id);
    } else if (act === 'copy') {
      toast((await copyText(b.dataset.url)) ? 'Link copied' : b.dataset.url, { tone: 'ok', timeout: 5000 });
    } else if (act === 'restore' && item) {
      const extra = item.missing ? `${plural(item.missing, 'mod')} from it ${item.missing === 1 ? 'is' : 'are'} not in your library any more and will be skipped (Details shows which).` : '';
      const r = await dialog({
        title: `Go back to “${histTitle(item)}”?`,
        message: `Your mod list becomes the one from that setup. Nothing in the game changes until you review and apply. ${extra}`.trim(),
        confirm: 'Restore', trigger: b,
      });
      if (!r) return;
      const next = await api.post('/api/snapshots/restore', { id });
      setState(next);
      closeTop();
      render();
      const res = next.restored || {};
      const skipped = res.missing?.length || 0;
      toast(skipped ? `Restored, but ${plural(skipped, 'mod')} could not come back. Check Setup history.` : 'Restored. Review changes to apply it.',
        { tone: skipped ? 'warn' : 'ok', timeout: 6000 });
    }
  } catch (err) {
    toast(err.message, { tone: 'error', timeout: 6000 });
  }
}

// ---------- Move a mod to another category ----------
function openGroupPicker(id, trigger) {
  const m = byId(id);
  if (!m) return;
  const cur = GROUPS.includes(m.group) ? m.group : 'Other';
  $('#gpTitle').textContent = `Where does “${m.name}” go?`;
  $('#gpBody').innerHTML = `<div class="grp-list" role="group" aria-label="Categories">${GROUPS.map((g) => `
    <button class="menu-item grp-item" type="button" data-group-pick="${g}" ${g === cur ? 'aria-current="true"' : ''}>
      ${icon(GROUP_ICON[g] || 'other', 18)}<span class="label"><span>${g}</span></span>
      <span class="check-slot">${g === cur ? icon('check', 16) : ''}</span>
    </button>`).join('')}</div>`;
  $('#gpBody').dataset.id = id;
  openModal($('#groupSheet'), { trigger, initialFocus: '[aria-current="true"]' });
}

async function pickGroup(group) {
  const id = $('#gpBody').dataset.id;
  const m = byId(id);
  if (!m) return;
  if (m.group === group) { closeTop(); return; }
  try {
    await api.post('/api/mod/group', { id, group });
    closeTop();
    await refresh();
    toast(`Moved “${m.name}” to ${group}`, { tone: 'ok' });
  } catch (e) {
    toast(e.message, { tone: 'error', timeout: 6000 });
  }
}

// ---------- What a mod needs: the manual list (the app also guesses some from the mod's files) ----------
const needsState = { id: null, picked: new Set(), start: '' };

function needsRowsHTML(m) {
  // Picked first, then core mods, then the rest by name. The mod itself is never offered.
  const others = mods().filter((x) => x.id !== m.id);
  const rank = (x) => (needsState.picked.has(x.id) ? 0 : x.framework ? 1 : 2);
  others.sort((a, b) => rank(a) - rank(b) || a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }));
  return others.map((x) => `
    <label class="check needs-row" data-name="${esc(x.name.toLowerCase())}">
      <input type="checkbox" value="${esc(x.id)}" ${needsState.picked.has(x.id) ? 'checked' : ''}>
      <span class="needs-name" title="${esc(x.name)}">${esc(x.name)}</span>${x.framework ? `<span class="needs-tag">Core</span>` : ''}
    </label>`).join('');
}

function needsRefreshFooter() {
  const n = needsState.picked.size;
  $('#ndCount').textContent = n ? `${n} selected` : 'Nothing selected';
  $('#ndCount').style.color = 'var(--text-2)';
  $('#ndSave').disabled = [...needsState.picked].sort().join('\n') === needsState.start;
}

function openNeeds(id, trigger) {
  const m = byId(id);
  if (!m) return;
  needsState.id = id;
  needsState.picked = new Set((m.requires || []).filter((r) => byId(r)));
  needsState.start = [...needsState.picked].sort().join('\n');
  $('#ndTitle').textContent = `What does “${m.name}” need?`;
  const auto = (m.autoRequires || []).map((n) => n.name);
  const autoEl = $('#ndAuto');
  autoEl.hidden = !auto.length;
  autoEl.textContent = auto.length ? `Found automatically from its files: ${auto.join(', ')}. You don’t need to add those.` : '';
  $('#ndSearch').value = '';
  $('#ndList').innerHTML = needsRowsHTML(m);
  $('#ndNone').hidden = true;
  needsRefreshFooter();
  openModal($('#needsSheet'), { trigger, initialFocus: '#ndSearch' });
}

function needsFilter() {
  const q = $('#ndSearch').value.trim().toLowerCase();
  let shown = 0;
  for (const row of $('#ndList').children) {
    const hit = !q || row.dataset.name.includes(q);
    row.hidden = !hit;
    if (hit) shown++;
  }
  $('#ndNone').hidden = shown > 0;
}

async function saveNeeds(trigger) {
  const m = byId(needsState.id);
  if (!m) return;
  try {
    const r = await api.post('/api/mod/requires', { id: m.id, requires: [...needsState.picked] });
    closeTop();
    await refresh();
    const n = r.mod.requires.length;
    toast(n ? `“${m.name}” needs ${n} ${n === 1 ? 'mod' : 'mods'} now` : `“${m.name}” has no hand-picked needs now`, { tone: 'ok' });
  } catch (e) {
    toast(e.message, { tone: 'error', timeout: 6000 });
  }
}

async function selectProfile(name, trigger) {
  const st = S.st;
  if (!st || name === st.profile) return;
  if (st.profileDirty) {
    const r = await dialog({
      title: `Save changes to “${st.profile}”?`,
      message: `You changed which mods are on. If you switch to “${name}” without saving, those changes are lost.`,
      confirm: 'Save and switch', alt: 'Don’t save', trigger,
    });
    if (!r) return;
    if (r.action === 'confirm') {
      try { await api.post('/api/profile/save', { name: st.profile }); }
      catch (e) { toast(e.message, { tone: 'error', timeout: 5000 }); return; }
    }
  }
  try {
    const next = await api.post('/api/profile/select', { name });
    setState(next);
    // The whole list changes at once: bridge it with a short opacity lift so it doesn't teleport.
    set($('#list'), { o: 0.25 });
    render();
    animate($('#list'), { o: 1 }, { response: 0.24 });
    announce(`Switched to ${name}`);
  } catch (e) {
    toast(e.message, { tone: 'error', timeout: 5000 });
  }
}

// ----- Profiles: the "+" button and the per-profile actions in the profile menu -----
async function newProfile(trigger) {
  const st = S.st || {};
  const cur = st.profile;
  try {
    const r = await dialog({
      title: 'New profile', input: { label: 'Name', value: '' },
      checkbox: cur ? { label: `Start with the mods that are on in “${cur}”`, checked: true } : null,
      confirm: 'Create', trigger,
      validate: (v) => (!v ? 'Give the profile a name.' : (st.profiles || []).some((p) => p.toLowerCase() === v.toLowerCase()) ? 'A profile with that name already exists.' : null),
    });
    if (!r) return;
    await api.post('/api/profile/new', { name: r.value, ...(r.checked && cur ? { from: cur } : {}) });
    setState(await api.post('/api/profile/select', { name: r.value }));
    render();
    toast(`Created “${r.value}”`, { tone: 'ok' });
  } catch (e) {
    toast(e.message, { tone: 'error', timeout: 5000 });
  }
}

async function profileAction(act, name, trigger) {
  const st = S.st || {};
  try {
    if (act === 'rename') {
      const r = await dialog({
        title: `Rename “${name}”`, input: { label: 'Name', value: name }, confirm: 'Rename', trigger,
        validate: (v) => (!v ? 'Give the profile a name.'
          : v.toLowerCase() !== name.toLowerCase() && (st.profiles || []).some((p) => p.toLowerCase() === v.toLowerCase()) ? 'A profile with that name already exists.' : null),
      });
      if (!r || r.value === name) return;
      await api.post('/api/profile/rename', { name, to: r.value });
      await refresh();
      toast(`Renamed to “${r.value}”`, { tone: 'ok' });
    } else if (act === 'delete') {
      const r = await dialog({
        title: `Delete “${name}”?`,
        message: 'Only the profile is removed. Your mods stay in the library and nothing in the game folder changes.',
        confirm: 'Delete', destructive: true, trigger,
      });
      if (!r) return;
      await api.post('/api/profile/delete', { name });
      await refresh();
      toast(`Deleted “${name}”`, { tone: 'ok' });
    } else if (act === 'save') {
      await api.post('/api/profile/save', { name });
      await refresh();
      toast(`Saved “${name}”`, { tone: 'ok' });
    }
  } catch (e) {
    toast(e.message, { tone: 'error', timeout: 5000 });
  }
}

async function runMenuAction(act, trigger) {
  try {
    if (act === 'history') {
      await openHistory(trigger);
    } else if (act === 'trash') {
      await openTrash(trigger);
    } else if (act === 'appearance') {
      syncSettingsForm();
      openModal($('#settingsSheet'), { trigger, initialFocus: 'input[name="theme"]:checked' });
    }
  } catch (e) {
    toast(e.message, { tone: 'error', timeout: 5000 });
  }
}

// ----- Appearance -----
function buildSwatches() {
  const box = $('#swatches');
  box.innerHTML = ACCENTS.map(([label, hex]) => `
    <label class="swatch" style="--c:${hex}" title="${label}"><input type="radio" name="accent" value="${hex}" aria-label="${label}"><span class="swatch-dot"></span></label>`).join('') +
    `<label class="swatch swatch-custom" title="Custom colour"><input type="color" id="accentPicker" aria-label="Custom accent colour"><span class="swatch-dot"></span></label>`;
}

function syncSettingsForm() {
  const s = S.settings;
  for (const r of document.querySelectorAll('input[name="theme"]')) r.checked = r.value === s.theme;
  const preset = ACCENTS.find(([, hex]) => hex.toLowerCase() === String(s.accent).toLowerCase());
  for (const r of document.querySelectorAll('input[name="accent"]')) r.checked = !!preset && r.value === preset[1];
  const custom = $('.swatch-custom');
  if (custom) {
    custom.classList.toggle('is-selected', !preset);
    custom.style.setProperty('--c', s.accent);
    $('#accentPicker').value = /^#[0-9a-f]{6}$/i.test(s.accent) ? s.accent.toLowerCase() : '#0a84ff';
  }
}

// ----- Import by drag and drop -----
function setupDrop() {
  let depth = 0;
  const drop = $('#drop');
  const hasFiles = (e) => [...(e.dataTransfer?.types || [])].includes('Files');
  const show = () => { if (drop.hidden) { drop.hidden = false; set(drop, { o: 0 }); } drop.dataset.open = 'true'; animate(drop, { o: 1 }, { response: 0.25 }); };
  const hide = () => { drop.dataset.open = 'false'; animate(drop, { o: 0 }, { response: 0.22 }).then((d) => { if (d && drop.dataset.open === 'false') drop.hidden = true; }); };
  addEventListener('dragenter', (e) => { if (!hasFiles(e)) return; e.preventDefault(); if (depth++ === 0) show(); });
  addEventListener('dragover', (e) => { if (!hasFiles(e)) return; e.preventDefault(); e.dataTransfer.dropEffect = 'copy'; });
  addEventListener('dragleave', (e) => { if (!hasFiles(e)) return; depth = Math.max(0, depth - 1); if (!depth) hide(); });
  addEventListener('drop', (e) => {
    if (!hasFiles(e)) return;
    e.preventDefault();
    depth = 0;
    hide();
    // Entries must be read synchronously inside the drop event.
    const entries = [...e.dataTransfer.items].map((i) => i.webkitGetAsEntry?.()).filter(Boolean);
    const files = entries.length ? [] : [...e.dataTransfer.files];
    importDropped(entries, files);
  });
}

function readAll(reader) {
  return new Promise((resolve, reject) => {
    const out = [];
    const next = () => reader.readEntries((batch) => { if (!batch.length) resolve(out); else { out.push(...batch); next(); } }, reject);
    next();
  });
}
async function walk(dir, prefix = '') {
  const out = [];
  for (const entry of await readAll(dir.createReader())) {
    const p = prefix ? `${prefix}/${entry.name}` : entry.name;
    if (entry.isDirectory) out.push(...await walk(entry, p));
    else out.push({ path: p, file: await new Promise((res, rej) => entry.file(res, rej)) });
  }
  return out;
}

async function importDropped(entries, files) {
  const items = entries.length
    ? entries.map((e) => ({ name: e.name, kind: e.isDirectory ? 'folder' : 'archive', load: () => (e.isDirectory ? walk(e) : new Promise((res, rej) => e.file((f) => res([{ path: e.name, file: f }]), rej))) }))
    : files.map((f) => ({ name: f.name, kind: 'archive', load: async () => [{ path: f.name, file: f }] }));
  for (const item of items) {
    const t = toast(`Adding “${item.name}” to your library…`, { sticky: true });
    try {
      const list = await item.load();
      const { token } = await api.post('/api/import/begin', { name: item.name, kind: item.kind });
      let i = 0;
      for (const f of list) {
        await api.put(`/api/import/file?token=${encodeURIComponent(token)}&path=${encodeURIComponent(f.path)}`, f.file);
        i++;
        if (list.length > 5 && i % 5 === 0) t.update(`Adding “${item.name}”… ${Math.round((i / list.length) * 100)}%`, { sticky: true });
      }
      const r = await api.post('/api/import/finish', { token });
      await refresh();
      const added = byId(r.id);
      const where = added ? ` to ${added.group}` : '';
      t.update(r.warnings?.length ? `Added “${added?.name || item.name}”${where}. ${r.warnings[0]}` : `Added “${added?.name || item.name}”${where}. Switch it on when you want it.`, { tone: r.warnings?.length ? 'warn' : 'ok', timeout: 5000 });
    } catch (e) {
      t.update(`Couldn’t add “${item.name}”. ${e.message}`, { tone: 'error', timeout: 7000 });
    }
  }
}

// ---------- polling ----------
async function poll() {
  if (document.hidden || S.inflight || S.bar === 'applying' || S.status === 'loading') return;
  try {
    const st = await api.get('/api/state');
    const wasLost = S.lost;
    S.lost = false;
    if (S.status !== 'ready') { S.status = 'ready'; setState(st); render(); return; }
    const json = JSON.stringify(st);
    if (json !== S.lastJson && !S.inflight) { setState(st); renderHeader(); renderBanner(); patchList(); renderBar(); }
    else if (wasLost) renderBanner();
    if (isOpen($('#previewSheet'))) syncPreviewFoot();
  } catch (e) {
    if (e.network && !S.lost) { S.lost = true; renderBanner(); }
  }
}

// ---------- wiring ----------
function isTyping(el) { return el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable); }

function wire() {
  const list = $('#list');
  list.addEventListener('click', (e) => {
    const action = e.target.closest('[data-action]');
    if (action?.dataset.action === 'retry') { load(); return; }
    const g = e.target.closest('.group-toggle');
    if (g) { S.navKey = g.dataset.key; toggleGroup(g.dataset.key.slice(6)); return; }
    const row = e.target.closest('.row');
    if (row && row.getAttribute('aria-disabled') !== 'true') {
      S.navKey = row.querySelector('.switch').dataset.key;
      toggleMod(row.dataset.id);
    }
  });
  list.addEventListener('focusin', (e) => {
    if (!e.target.dataset || !('nav' in e.target.dataset)) return;
    for (const n of navItems()) n.tabIndex = n === e.target ? 0 : -1;
    S.navKey = e.target.dataset.key;
  });
  // Right-click a mod (or press Delete on it) to move it to the trash.
  list.addEventListener('contextmenu', (e) => {
    const li = e.target.closest('li.row');
    if (!li) return;
    e.preventDefault();
    openRowMenu(li);
  });
  $('#rowMenu').addEventListener('click', (e) => {
    const b = e.target.closest('[data-row-act]');
    if (!b) return;
    const id = $('#rowMenu').dataset.id;
    closePopovers(true);
    if (b.dataset.rowAct === 'delete') deleteMod(id, document.activeElement);
    else if (b.dataset.rowAct === 'needs') openNeeds(id, document.activeElement);
    else if (b.dataset.rowAct === 'group') openGroupPicker(id, document.activeElement);
  });
  $('#ndList').addEventListener('change', (e) => {
    if (e.target.type !== 'checkbox') return;
    if (e.target.checked) needsState.picked.add(e.target.value); else needsState.picked.delete(e.target.value);
    needsRefreshFooter();
  });
  $('#ndSearch').addEventListener('input', needsFilter);
  $('#gpBody').addEventListener('click', (e) => { const b = e.target.closest('[data-group-pick]'); if (b) pickGroup(b.dataset.groupPick); });
  $('#ndSave').addEventListener('click', (e) => saveNeeds(e.currentTarget));
  $('#historySheet').addEventListener('click', historyClick);
  $('#trashSheet').addEventListener('click', trashClick);
  $('#trEmpty').addEventListener('click', (e) => emptyTrash(e.currentTarget));
  list.addEventListener('keydown', (e) => {
    const items = navItems();
    const i = items.indexOf(document.activeElement);
    if (i < 0) return;
    const el = items[i];
    if (e.key === 'Delete' && el.classList.contains('switch')) { e.preventDefault(); deleteMod(el.dataset.key.slice(4), el); return; }
    let j = null;
    switch (e.key) {
      case 'ArrowDown': j = Math.min(i + 1, items.length - 1); break;
      case 'ArrowUp': j = Math.max(i - 1, 0); break;
      case 'Home': j = 0; break;
      case 'End': j = items.length - 1; break;
      case 'PageDown': j = Math.min(i + 8, items.length - 1); break;
      case 'PageUp': j = Math.max(i - 8, 0); break;
      case 'ArrowLeft':
        if (el.classList.contains('group-toggle')) { if (el.getAttribute('aria-expanded') === 'true') { e.preventDefault(); toggleGroup(el.dataset.key.slice(6)); } }
        else { const head = el.closest('.group')?.querySelector('.group-toggle'); if (head) { e.preventDefault(); focusNav(head); } }
        return;
      case 'ArrowRight':
        if (el.classList.contains('group-toggle') && el.getAttribute('aria-expanded') === 'false') { e.preventDefault(); toggleGroup(el.dataset.key.slice(6)); }
        return;
      case 'Enter':
        if (el.classList.contains('switch')) { e.preventDefault(); el.click(); }
        return;
      default: return;
    }
    e.preventDefault();
    if (j !== null && items[j]) focusNav(items[j]);
  });

  const search = $('#search');
  search.addEventListener('input', () => { S.query = search.value; renderList(); });
  search.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown') { const first = navItems()[0]; if (first) { e.preventDefault(); focusNav(first); } }
    if (e.key === 'Enter') { const first = navItems().find((n) => n.classList.contains('switch')); if (first && S.query) { e.preventDefault(); focusNav(first); } }
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      if (closeTop()) { e.preventDefault(); return; }
      if (document.activeElement === search) {
        e.preventDefault();
        if (search.value) { search.value = ''; S.query = ''; renderList(); } else search.blur();
      }
      return;
    }
    if (e.key === '/' && !e.ctrlKey && !e.metaKey && !e.altKey && !isTyping(e.target) && !hasModal()) {
      e.preventDefault();
      closePopovers(false);
      search.focus();
      search.select();
      return;
    }
    // Nothing focused: the page scrolls inside #scroller now, so the browser's own page keys
    // (which target the document) would do nothing. Do them on the scroller instead.
    const t = e.target;
    if ((t === document.body || t === root) && !hasModal() && !e.ctrlKey && !e.metaKey && !e.altKey && !e.defaultPrevented) {
      const sc = $('#scroller');
      const page = sc.clientHeight - 80;
      const by = { PageDown: page, PageUp: -page, ' ': e.shiftKey ? -page : page, ArrowDown: 40, ArrowUp: -40 }[e.key];
      const to = { Home: 0, End: sc.scrollHeight }[e.key];
      if (by === undefined && to === undefined) return;
      e.preventDefault();
      const behavior = pref.reduceMotion ? 'auto' : 'smooth';
      if (to !== undefined) sc.scrollTo({ top: to, behavior }); else sc.scrollBy({ top: by, behavior });
    }
  });

  $('#profileBtn').addEventListener('click', (e) => { renderProfileMenu(); openPopover($('#profileMenu'), e.currentTarget, { align: 'start' }); });
  $('#moreBtn').addEventListener('click', (e) => { renderMoreMenu(); openPopover($('#moreMenu'), e.currentTarget, { align: 'end' }); });

  $('#newProfileBtn').addEventListener('click', (e) => newProfile(e.currentTarget));
  $('#profileMenu').addEventListener('click', (e) => {
    const act = e.target.closest('[data-profile-act]');
    if (act) {
      if (act.getAttribute('aria-disabled') === 'true') return;
      closePopovers(true);
      profileAction(act.dataset.profileAct, act.dataset.profile, $('#profileBtn'));
      return;
    }
    const b = e.target.closest('[data-profile]');
    if (!b) return;
    closePopovers(true);
    selectProfile(b.dataset.profile, $('#profileBtn'));
  });
  $('#moreMenu').addEventListener('click', (e) => {
    const b = e.target.closest('[data-act]');
    if (!b || b.getAttribute('aria-disabled') === 'true') return;
    closePopovers(true);
    runMenuAction(b.dataset.act, $('#moreBtn'));
  });

  $('#previewBtn').addEventListener('click', (e) => openPreview(e.currentTarget));
  $('#applyBtn').addEventListener('click', (e) => { if (e.currentTarget.getAttribute('aria-disabled') !== 'true') startApply(e.currentTarget); });
  $('#pvApply').addEventListener('click', (e) => { if (e.currentTarget.getAttribute('aria-disabled') !== 'true') startApply(e.currentTarget); });
  $('#pvDiscard').addEventListener('click', discardChanges);
  $('#errDismiss').addEventListener('click', () => { S.bar = null; renderList(); renderBar(); focusListFallback(); });
  $('#errRetry').addEventListener('click', (e) => { S.bar = null; startApply(e.currentTarget); });
  $('#scrim').addEventListener('click', () => closeTop());

  for (const r of document.querySelectorAll('input[name="theme"]')) r.addEventListener('change', () => saveSettings({ theme: r.value }));
  $('#swatches').addEventListener('change', (e) => { if (e.target.name === 'accent') saveSettings({ accent: e.target.value }); });
  // Custom picker: live while dragging (no cross-fade for a high-frequency input), saved on change.
  $('#accentPicker').addEventListener('input', (e) => { S.settings.accent = e.target.value.toUpperCase(); applyTheme(false); syncSettingsForm(); });
  $('#accentPicker').addEventListener('change', (e) => saveSettings({ accent: e.target.value.toUpperCase() }, false));
  darkMQ.addEventListener('change', () => { if (S.settings.theme === 'system') applyTheme(true); });

  // The page scrolls inside #scroller (so the top bar and window buttons can sit over its scrollbar column).
  const topbar = $('#topbar');
  const scroller = $('#scroller');
  const onScroll = () => { if (scroller.scrollTop > 4) topbar.dataset.scrolled = ''; else delete topbar.dataset.scrolled; };
  scroller.addEventListener('scroll', onScroll, { passive: true });
  onScroll();

  setupDrop();
  setInterval(poll, 3000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) poll(); });
}

function setupMockChip() {
  const old = $('#gameChip');
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.id = 'gameChip';
  btn.className = old.className;
  btn.innerHTML = old.innerHTML;
  btn.title = 'Demo: click to simulate the game starting or closing';
  old.replaceWith(btn);
  btn.addEventListener('click', async () => {
    const mock = mockModule();
    mock.setGameRunning(!mock.isGameRunning());
    await refresh();
    if (isOpen($('#previewSheet'))) syncPreviewFoot();
    announce(running() ? 'Game running' : 'Game closed');
  });
}

async function resumeApplyIfRunning() {
  try {
    const p = await api.get('/api/progress');
    if (p.state === 'running') {
      S.bar = 'applying';
      set($('#progFill'), { sx: (p.percent || 0) / 100 });
      setProgress(p);
      renderBar();
      pollProgress();
    }
  } catch { /* engine without progress yet */ }
}

async function init() {
  await setupHost();
  hydrateIcons();
  buildSwatches();
  applyTheme(false);
  syncSettingsForm();
  wire();
  render();
  const mode = await initApi();
  if (mode === 'mock') { $('#demoChip').hidden = false; setupMockChip(); }
  await loadSettings();
  await load();
  S.bannerLive = true;   // from here on, the banner animates in and out
  await resumeApplyIfRunning();
}

init();
