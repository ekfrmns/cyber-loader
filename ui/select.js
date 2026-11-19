// A themed drop-down that replaces the browser's own <select> list (square, grey, can't be styled).
// The real <select> stays in the page, hidden, as the source of truth: this only draws it and sends it a normal "change"
// event, so the code that already listens to the select keeps working.
// Each <option> may carry data-name (big) and data-detail (small); without them its text is used.
import { icon } from './icons.js';

const insts = new WeakMap();
let openInst = null;

const optName = (o) => o.dataset.name || o.textContent;
const optDetail = (o) => o.dataset.detail || '';

export function themedSelect(select) {
  if (insts.has(select)) return insts.get(select);
  const wrap = document.createElement('span');
  wrap.className = 'tsel';
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'tsel-btn';
  btn.setAttribute('aria-haspopup', 'listbox');
  btn.setAttribute('aria-expanded', 'false');
  if (select.getAttribute('aria-label')) btn.setAttribute('aria-label', select.getAttribute('aria-label'));
  select.after(wrap);
  wrap.append(btn);
  select.classList.add('tsel-native');
  select.tabIndex = -1;
  select.setAttribute('aria-hidden', 'true');

  let pop = null, active = -1, typed = '', typedAt = 0, openedAt = 0;
  const opts = () => [...select.options];

  const paintButton = () => {
    const o = select.options[select.selectedIndex];
    btn.disabled = select.disabled || !select.options.length;
    btn.innerHTML = `<span class="tsel-val"><span class="tsel-name">${o ? esc(optName(o)) : ''}</span>${o && optDetail(o) ? `<span class="tsel-detail">${esc(optDetail(o))}</span>` : ''}</span>${icon('chevronDown', 16, 'tsel-chev')}`;
    btn.title = o ? [optName(o), optDetail(o)].filter(Boolean).join(' · ') : '';
  };

  const place = () => {
    const r = btn.getBoundingClientRect();
    const w = Math.max(r.width, 300);
    const room = innerHeight - r.bottom - 14, above = r.top - 14;
    const h = Math.min(pop.scrollHeight, 340);
    const up = room < h && above > room;
    pop.style.maxHeight = `${Math.max(120, Math.min(340, up ? above : room))}px`;
    pop.style.width = `${Math.min(w, innerWidth - 24)}px`;
    const left = Math.max(12, Math.min(r.right - Math.min(w, innerWidth - 24), innerWidth - Math.min(w, innerWidth - 24) - 12));
    pop.style.left = `${left}px`;
    if (up) { pop.style.top = ''; pop.style.bottom = `${innerHeight - r.top + 8}px`; pop.style.transformOrigin = '100% 100%'; }
    else { pop.style.bottom = ''; pop.style.top = `${r.bottom + 8}px`; pop.style.transformOrigin = '100% 0'; }
  };

  const setActive = (i, scroll = true) => {
    active = Math.max(0, Math.min(opts().length - 1, i));
    for (const [k, el] of [...pop.children].entries()) el.classList.toggle('is-active', k === active);
    pop.setAttribute('aria-activedescendant', pop.children[active]?.id || '');
    if (scroll) pop.children[active]?.scrollIntoView({ block: 'nearest' });
  };

  const choose = (i) => {
    const changed = select.selectedIndex !== i;
    select.selectedIndex = i;
    close(true);
    if (changed) select.dispatchEvent(new Event('change', { bubbles: true }));
    paintButton();
  };

  function open() {
    if (btn.disabled || openInst === api) return;
    openInst?.close();
    pop = document.createElement('div');
    pop.className = 'tsel-pop';
    pop.setAttribute('role', 'listbox');
    pop.tabIndex = -1;
    if (select.getAttribute('aria-label')) pop.setAttribute('aria-label', select.getAttribute('aria-label'));
    const uid = `tsel${Math.random().toString(36).slice(2, 8)}`;
    pop.innerHTML = opts().map((o, i) => `<div class="tsel-opt${i === select.selectedIndex ? ' is-selected' : ''}" role="option" id="${uid}-${i}" aria-selected="${i === select.selectedIndex}" data-i="${i}">
      <span class="tsel-opt-t"><span class="tsel-name">${esc(optName(o))}</span>${optDetail(o) ? `<span class="tsel-detail">${esc(optDetail(o))}</span>` : ''}</span>
      <span class="tsel-tick">${i === select.selectedIndex ? icon('check', 18) : ''}</span></div>`).join('');
    document.body.append(pop);
    place();
    btn.setAttribute('aria-expanded', 'true');
    setActive(Math.max(0, select.selectedIndex), false);
    pop.getBoundingClientRect();
    pop.dataset.open = 'true';
    pop.focus({ preventScroll: true });
    pop.scrollTop = Math.max(0, (pop.children[active]?.offsetTop || 0) - 60);
    openInst = api;
    openedAt = Date.now();
    pop.addEventListener('pointerdown', (e) => { e.preventDefault(); });          // keep focus in the list while clicking
    pop.addEventListener('click', (e) => { const o = e.target.closest('.tsel-opt'); if (o) choose(+o.dataset.i); });
    pop.addEventListener('pointermove', (e) => { const o = e.target.closest('.tsel-opt'); if (o && +o.dataset.i !== active) setActive(+o.dataset.i, false); });
    pop.addEventListener('keydown', onKey);
    pop.addEventListener('blur', () => setTimeout(() => { if (openInst === api && document.hasFocus() && !pop?.contains(document.activeElement)) close(false); }, 0));   // leaving the window keeps the list as it is
    setTimeout(() => {
      document.addEventListener('pointerdown', outside, true);
      addEventListener('resize', onGone); addEventListener('scroll', onGone, true);
    }, 0);
  }

  function close(refocus) {
    if (!pop) return;
    const p = pop; pop = null;
    if (openInst === api) openInst = null;
    document.removeEventListener('pointerdown', outside, true);
    removeEventListener('resize', onGone); removeEventListener('scroll', onGone, true);
    btn.setAttribute('aria-expanded', 'false');
    p.dataset.open = 'false';
    setTimeout(() => p.remove(), matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 120);
    if (refocus) btn.focus({ preventScroll: true });
  }

  const outside = (e) => { if (pop && !pop.contains(e.target) && !btn.contains(e.target)) close(false); };
  const onGone = (e) => { if (pop && Date.now() - openedAt > 350 && !(e.target instanceof Node && pop.contains(e.target))) close(false); };   // a scroll that is already running when the list opens does not close it

  function onKey(e) {
    const n = opts().length;
    if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); close(true); return; }
    if (e.key === 'Tab') { close(false); return; }
    const move = { ArrowDown: active + 1, ArrowUp: active - 1, Home: 0, End: n - 1, PageDown: active + 6, PageUp: active - 6 }[e.key];
    if (move !== undefined) { e.preventDefault(); setActive(move); return; }
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); choose(active); return; }
    if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {       // type to jump
      const now = Date.now();
      typed = now - typedAt > 700 ? e.key.toLowerCase() : typed + e.key.toLowerCase();
      typedAt = now;
      const i = opts().findIndex((o, k) => k >= (typed.length === 1 ? active + 1 : active) && optName(o).toLowerCase().startsWith(typed));
      const j = i >= 0 ? i : opts().findIndex((o) => optName(o).toLowerCase().startsWith(typed));
      if (j >= 0) setActive(j);
    }
  }

  btn.addEventListener('click', () => { if (openInst === api) close(true); else open(); });
  btn.addEventListener('keydown', (e) => {
    if (['ArrowDown', 'ArrowUp', 'Enter', ' '].includes(e.key)) { e.preventDefault(); open(); }
  });

  const api = { refresh() { if (pop) close(false); paintButton(); }, close: () => close(false) };
  insts.set(select, api);
  select._themed = api;
  paintButton();
  return api;
}

function esc(s) { return String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c])); }
