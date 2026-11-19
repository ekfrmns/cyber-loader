// A themed colour picker for the accent colour (replaces the browser's grey <input type="color">).
// Saturation/brightness square + hue slider + hex field. Mouse, touch and keyboard. No animation inside the picker itself:
// the knob follows the pointer 1:1. Opening and closing is done by the caller.
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const HEX = /^#?([0-9a-f]{6})$/i;
const HEX3 = /^#?([0-9a-f])([0-9a-f])([0-9a-f])$/i;

export function normalizeHex(text) {
  const t = String(text || '').trim();
  let m = HEX.exec(t);
  if (m) return `#${m[1].toUpperCase()}`;
  m = HEX3.exec(t);
  return m ? `#${m[1]}${m[1]}${m[2]}${m[2]}${m[3]}${m[3]}`.toUpperCase() : null;
}

export function hexToHsv(hex) {
  const n = parseInt(normalizeHex(hex).slice(1), 16);
  const r = ((n >> 16) & 255) / 255, g = ((n >> 8) & 255) / 255, b = (n & 255) / 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b), d = max - min;
  let h = 0;
  if (d) {
    if (max === r) h = ((g - b) / d) % 6;
    else if (max === g) h = (b - r) / d + 2;
    else h = (r - g) / d + 4;
    h = (h * 60 + 360) % 360;
  }
  return { h, s: max ? d / max : 0, v: max };
}

export function hsvToHex(h, s, v) {
  const c = v * s, x = c * (1 - Math.abs(((h / 60) % 2) - 1)), m = v - c;
  const [r, g, b] = h < 60 ? [c, x, 0] : h < 120 ? [x, c, 0] : h < 180 ? [0, c, x] : h < 240 ? [0, x, c] : h < 300 ? [x, 0, c] : [c, 0, x];
  const to = (k) => Math.round((k + m) * 255).toString(16).padStart(2, '0');
  return `#${to(r)}${to(g)}${to(b)}`.toUpperCase();
}

/**
 * @param {HTMLElement} root the (empty) panel element
 * @param {{ get: () => string, onInput: (hex: string) => void, onCommit: (hex: string) => void, onClose: () => void }} o
 */
export function createColorPicker(root, { get, onInput, onCommit, onClose }) {
  root.innerHTML = `
    <div class="cpick-sv" role="slider" tabindex="0" aria-label="Saturation and brightness. Arrow keys change it, hold Shift for bigger steps."><i class="cpick-knob"></i></div>
    <div class="cpick-hue" role="slider" tabindex="0" aria-label="Hue" aria-valuemin="0" aria-valuemax="360"><i class="cpick-hknob"></i></div>
    <div class="cpick-row">
      <span class="cpick-chip" aria-hidden="true"></span>
      <label class="cpick-hex"><span class="sr-only">Hex colour</span><input type="text" maxlength="7" spellcheck="false" autocomplete="off" aria-label="Hex colour" inputmode="text"></label>
      <button class="btn btn-quiet" type="button" data-done>Done</button>
    </div>
    <p class="cpick-note">Text and switches on this colour stay readable. It is adjusted for light and dark automatically.</p>`;
  const sv = root.querySelector('.cpick-sv'), hue = root.querySelector('.cpick-hue');
  const knob = root.querySelector('.cpick-knob'), hknob = root.querySelector('.cpick-hknob');
  const chip = root.querySelector('.cpick-chip'), input = root.querySelector('.cpick-hex input');
  let hsv = hexToHsv(get());
  let last = normalizeHex(get());

  const paint = () => {
    const hex = hsvToHex(hsv.h, hsv.s, hsv.v);
    sv.style.setProperty('--h', Math.round(hsv.h));
    knob.style.left = `${hsv.s * 100}%`;
    knob.style.top = `${(1 - hsv.v) * 100}%`;
    knob.style.background = hex;
    hknob.style.left = `${(hsv.h / 360) * 100}%`;
    hknob.style.background = hsvToHex(hsv.h, 1, 1);
    chip.style.background = hex;
    if (document.activeElement !== input) input.value = hex;
    input.removeAttribute('aria-invalid');
    sv.setAttribute('aria-valuetext', `Saturation ${Math.round(hsv.s * 100)} percent, brightness ${Math.round(hsv.v * 100)} percent`);
    hue.setAttribute('aria-valuenow', Math.round(hsv.h));
    return hex;
  };
  const push = () => { const hex = paint(); last = hex; onInput(hex); };
  const commit = () => onCommit(last);

  // Drag (mouse, touch, pen): the knob follows the pointer exactly
  const drag = (el, move) => {
    el.addEventListener('pointerdown', (e) => {
      el.setPointerCapture(e.pointerId); el.focus({ preventScroll: true });
      move(e); push();
      const mv = (ev) => { move(ev); push(); };
      const up = () => { el.removeEventListener('pointermove', mv); el.removeEventListener('pointerup', up); el.removeEventListener('pointercancel', up); commit(); };
      el.addEventListener('pointermove', mv); el.addEventListener('pointerup', up); el.addEventListener('pointercancel', up);
      e.preventDefault();
    });
  };
  drag(sv, (e) => { const r = sv.getBoundingClientRect(); hsv.s = clamp((e.clientX - r.left) / r.width, 0, 1); hsv.v = 1 - clamp((e.clientY - r.top) / r.height, 0, 1); });
  drag(hue, (e) => { const r = hue.getBoundingClientRect(); hsv.h = clamp((e.clientX - r.left) / r.width, 0, 1) * 360; });

  // Keyboard
  sv.addEventListener('keydown', (e) => {
    const step = e.shiftKey ? 0.1 : 0.01;
    const d = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, step], ArrowDown: [0, -step] }[e.key];
    if (!d) return;
    e.preventDefault(); hsv.s = clamp(hsv.s + d[0], 0, 1); hsv.v = clamp(hsv.v + d[1], 0, 1); push();
  });
  hue.addEventListener('keydown', (e) => {
    const step = e.shiftKey ? 30 : 3;
    const d = { ArrowLeft: -step, ArrowDown: -step, ArrowRight: step, ArrowUp: step }[e.key];
    if (d === undefined) return;
    e.preventDefault(); hsv.h = clamp(hsv.h + d, 0, 360); push();
  });
  root.addEventListener('keyup', (e) => { if (e.target === sv || e.target === hue) if (e.key.startsWith('Arrow')) commit(); });

  // Hex field
  input.addEventListener('input', () => {
    const hex = normalizeHex(input.value);
    if (!hex) { input.setAttribute('aria-invalid', 'true'); return; }
    hsv = hexToHsv(hex); push();
  });
  input.addEventListener('change', () => { if (normalizeHex(input.value)) commit(); input.value = last; input.removeAttribute('aria-invalid'); });
  input.addEventListener('blur', () => { input.value = last; input.removeAttribute('aria-invalid'); });
  input.addEventListener('keydown', (e) => { if (e.key === 'Enter') { input.blur(); commit(); } });

  root.querySelector('[data-done]').addEventListener('click', onClose);
  root.addEventListener('keydown', (e) => { if (e.key === 'Escape') { e.stopPropagation(); onClose(); } });

  paint();
  return {
    /** The accent was changed from outside (a preset swatch, a reload). Keep our hue if the colour is the one we just made. */
    sync() {
      const hex = normalizeHex(get());
      if (!hex || hex === last) { paint(); return; }
      hsv = hexToHsv(hex); last = hex; paint();
    },
  };
}
