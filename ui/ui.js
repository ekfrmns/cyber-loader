// Layers: modal sheets/dialogs, popovers, toasts, live announcements.
// Sheets and popovers grow from their trigger and shrink back to it (springs, interruptible).
import { animate, set } from './spring.js';
import { icon } from './icons.js';

const $ = (s) => document.querySelector(s);
const stack = [];
let fallbackFocus = () => {};

export const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
export const hasModal = () => stack.some((l) => l.modal);
export const isOpen = (el) => stack.some((l) => l.el === el);
export function setFallbackFocus(fn) { fallbackFocus = fn; }

export function closeTop() {
  const l = stack[stack.length - 1];
  if (!l) return false;
  l.close();
  return true;
}

const FOCUSABLE = 'button:not([disabled]), [href], input:not([disabled]), select, textarea, summary, [tabindex]:not([tabindex="-1"])';
function focusables(el) {
  return [...el.querySelectorAll(FOCUSABLE)].filter((n) => !n.closest('[hidden]') && n.getClientRects().length);
}

function restoreFocus(trigger) {
  if (trigger && trigger.isConnected && !trigger.closest('[hidden]') && !trigger.closest('[inert]') && trigger.getClientRects().length) {
    trigger.focus({ preventScroll: true });
  } else {
    fallbackFocus();
  }
}

/** Set transform-origin so `el` scales out of / back into `trigger`. */
function originFrom(el, trigger) {
  if (!trigger || !trigger.isConnected || !trigger.getClientRects().length) { el.style.transformOrigin = '50% 60%'; return; }
  const prev = el.style.transform;
  el.style.transform = 'none';
  const b = el.getBoundingClientRect();
  el.style.transform = prev;
  const r = trigger.getBoundingClientRect();
  el.style.transformOrigin = `${(r.left + r.width / 2 - b.left).toFixed(1)}px ${(r.top + r.height / 2 - b.top).toFixed(1)}px`;
}

function setBackgroundInert(on) {
  for (const n of document.querySelectorAll('[data-modal-inert]')) n.inert = on;
}

let scrimOn = false;
function scrim(on) {
  const s = $('#scrim');
  if (on === scrimOn) return;
  scrimOn = on;
  if (on) {
    if (s.hidden) { s.hidden = false; set(s, { o: 0 }); }
    animate(s, { o: 1 }, { response: 0.35 });
  } else {
    animate(s, { o: 0 }, { response: 0.3 }).then((done) => { if (done && !scrimOn) s.hidden = true; });
  }
}

function trapTab(e) {
  if (e.key !== 'Tab') return;
  const f = focusables(e.currentTarget);
  if (!f.length) return;
  const first = f[0], last = f[f.length - 1];
  if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
  else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
}

/** Open a modal sheet or dialog. Returns its layer ({ close(result) }). */
export function openModal(el, { trigger, onClose, initialFocus } = {}) {
  closePopovers(false);
  const existing = stack.find((l) => l.el === el);
  if (existing) return existing;
  const layer = { el, trigger, modal: true, onClose };
  layer.close = (result) => closeModal(layer, result);
  stack.push(layer);

  setBackgroundInert(true);
  scrim(true);
  const wasHidden = el.hidden;
  el.hidden = false;
  el.dataset.open = 'true';
  originFrom(el, trigger);
  if (wasHidden) set(el, { s: 0.86, o: 0 });
  animate(el, { s: 1, o: 1 }, { response: 0.42 });
  el.addEventListener('keydown', trapTab);
  for (const b of el.querySelectorAll('[data-close]')) b.onclick = () => layer.close();

  const f = (initialFocus && el.querySelector(initialFocus)) || focusables(el)[0] || el;
  f.focus({ preventScroll: true });
  return layer;
}

function closeModal(layer, result) {
  const i = stack.indexOf(layer);
  if (i < 0) return;
  stack.splice(i, 1);
  const { el, trigger } = layer;
  el.dataset.open = 'false';
  el.removeEventListener('keydown', trapTab);
  originFrom(el, trigger);
  animate(el, { s: 0.9, o: 0 }, { response: 0.28 }).then((done) => {
    if (done && el.dataset.open === 'false') el.hidden = true;
  });
  if (!hasModal()) { setBackgroundInert(false); scrim(false); }
  restoreFocus(trigger);
  layer.onClose?.(result);
}

// ---------- Popovers / menus ----------
export function openPopover(el, trigger, { align = 'start', onClose } = {}) {
  if (isOpen(el)) { stack.find((l) => l.el === el).close(); return; }
  closePopovers(false);
  const wasHidden = el.hidden;
  el.hidden = false;
  el.dataset.open = 'true';

  const prev = el.style.transform;
  el.style.transform = 'none';
  const r = trigger.getBoundingClientRect();
  const w = el.offsetWidth, h = el.offsetHeight;
  let left = align === 'end' ? r.right - w : r.left;
  left = Math.max(12, Math.min(left, innerWidth - w - 12));
  const top = Math.max(12, Math.min(r.bottom + 8, innerHeight - h - 12));
  el.style.left = `${left}px`;
  el.style.top = `${top}px`;
  el.style.transform = prev;
  el.style.transformOrigin = `${(r.left + r.width / 2 - left).toFixed(1)}px ${(r.top + r.height / 2 - top).toFixed(1)}px`;

  if (wasHidden) set(el, { s: 0.92, o: 0 });
  animate(el, { s: 1, o: 1 }, { response: 0.3 });
  trigger.setAttribute('aria-expanded', 'true');

  const layer = { el, trigger, modal: false, onClose };
  layer.close = (opts = {}) => closePopover(layer, opts);
  stack.push(layer);
  el.onkeydown = menuKeys;
  const first = el.querySelector('[role^="menuitem"][aria-checked="true"]') || el.querySelector('[role^="menuitem"]');
  first?.focus({ preventScroll: true });
  return layer;
}

function closePopover(layer, { returnFocus = true } = {}) {
  const i = stack.indexOf(layer);
  if (i < 0) return;
  stack.splice(i, 1);
  const { el, trigger } = layer;
  el.dataset.open = 'false';
  trigger.setAttribute('aria-expanded', 'false');
  animate(el, { s: 0.95, o: 0 }, { response: 0.22 }).then((done) => {
    if (done && el.dataset.open === 'false') el.hidden = true;
  });
  if (returnFocus && el.contains(document.activeElement)) trigger.focus({ preventScroll: true });
  layer.onClose?.();
}

export function closePopovers(returnFocus = true) {
  for (const l of stack.filter((x) => !x.modal)) l.close({ returnFocus });
}

function menuKeys(e) {
  const items = [...e.currentTarget.querySelectorAll('[role^="menuitem"]')];
  const i = items.indexOf(document.activeElement);
  let j = null;
  if (e.key === 'ArrowDown') j = (i + 1) % items.length;
  else if (e.key === 'ArrowUp') j = (i - 1 + items.length) % items.length;
  else if (e.key === 'Home') j = 0;
  else if (e.key === 'End') j = items.length - 1;
  else if (e.key === 'Tab') { closePopovers(true); return; }
  if (j !== null) { e.preventDefault(); items[j].focus(); }
}

document.addEventListener('pointerdown', (e) => {
  for (const l of stack.filter((x) => !x.modal)) {
    if (!l.el.contains(e.target) && !l.trigger.contains(e.target)) l.close({ returnFocus: false });
  }
}, true);

addEventListener('resize', () => closePopovers(false));

// ---------- Toasts and announcements ----------
const TONE_ICON = { info: 'info', ok: 'check', warn: 'warning', error: 'warning' };

export function toast(text, { tone = 'info', timeout = 3400, sticky = false } = {}) {
  const box = $('#toasts');
  const el = document.createElement('div');
  el.className = 'toast';
  const paint = (t, tn) => { el.dataset.tone = tn; el.innerHTML = `${icon(TONE_ICON[tn] || 'info', 18)}<span>${esc(t)}</span>`; };
  paint(text, tone);
  box.append(el);
  // Enters from the edge it lives on (top) and leaves the same way; exit is quicker than entry.
  set(el, { o: 0, y: -8 });
  animate(el, { o: 1, y: 0 }, { response: 0.3 });
  let timer = 0;
  let closed = false;
  const close = () => {
    if (closed) return;
    closed = true;
    clearTimeout(timer);
    animate(el, { o: 0, y: -8 }, { response: 0.22 }).then(() => el.remove());
  };
  const arm = (ms) => { clearTimeout(timer); if (ms) timer = setTimeout(close, ms); };
  if (!sticky) arm(timeout);
  return {
    update(t, o = {}) { paint(t, o.tone || tone); arm(o.sticky ? 0 : (o.timeout ?? timeout)); },
    close,
  };
}

export function announce(text) {
  const sr = $('#sr');
  sr.textContent = '';
  setTimeout(() => { sr.textContent = text; }, 30);
}

// ---------- Dialog (confirm / prompt) ----------
/**
 * @returns Promise<null | { action: 'confirm'|'alt', value?: string, checked?: boolean }>
 */
export function dialog({ title, message = '', input = null, checkbox = null, confirm = 'OK', alt = null, cancel = 'Cancel', destructive = false, trigger, validate } = {}) {
  const el = $('#dialog');
  return new Promise((resolve) => {
    el.innerHTML = `
      <form class="dlg" novalidate>
        <h2 class="sheet-title" id="dlgTitle">${esc(title)}</h2>
        ${message ? `<p class="dlg-msg" id="dlgMsg">${esc(message)}</p>` : ''}
        ${input ? `<label class="input-field"><span>${esc(input.label)}</span><input id="dlgInput" type="text" autocomplete="off" spellcheck="false" maxlength="80" value="${esc(input.value || '')}" aria-describedby="dlgError"></label><p class="dlg-error" id="dlgError" role="alert"></p>` : ''}
        ${checkbox ? `<label class="check"><input id="dlgCheck" type="checkbox" ${checkbox.checked ? 'checked' : ''}><span>${esc(checkbox.label)}</span></label>` : ''}
        <div class="dlg-actions">
          <button class="btn" type="button" data-r="cancel">${esc(cancel)}</button>
          ${alt ? `<button class="btn" type="button" data-r="alt">${esc(alt)}</button>` : ''}
          <button class="btn ${destructive ? 'btn-danger' : 'btn-primary'}" type="submit" data-r="confirm">${esc(confirm)}</button>
        </div>
      </form>`;
    if (message) el.setAttribute('aria-describedby', 'dlgMsg'); else el.removeAttribute('aria-describedby');
    let result = null;
    const form = el.querySelector('form');
    const inp = el.querySelector('#dlgInput');
    const err = el.querySelector('#dlgError');
    form.addEventListener('submit', (e) => {
      e.preventDefault();
      const value = inp ? inp.value.trim() : undefined;
      if (inp && validate) {
        const msg = validate(value);
        if (msg) { err.textContent = msg; inp.setAttribute('aria-invalid', 'true'); inp.focus(); return; }
      }
      result = { action: 'confirm', value, checked: el.querySelector('#dlgCheck')?.checked };
      layer.close();
    });
    inp?.addEventListener('input', () => { err.textContent = ''; inp.removeAttribute('aria-invalid'); });
    el.querySelector('[data-r="cancel"]').onclick = () => layer.close();
    const altBtn = el.querySelector('[data-r="alt"]');
    if (altBtn) altBtn.onclick = () => { result = { action: 'alt' }; layer.close(); };
    const layer = openModal(el, {
      trigger,
      onClose: () => resolve(result),
      initialFocus: input ? '#dlgInput' : destructive ? '[data-r="cancel"]' : '[data-r="confirm"]',
    });
    if (inp) inp.select();
  });
}
