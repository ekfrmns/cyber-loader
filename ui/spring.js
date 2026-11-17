// A tiny spring animator.
// - Critically damped by default (damping 1 = no overshoot). Parameters follow Apple's
//   damping ratio + response (seconds), not mass/stiffness.
// - Interruptible: every call re-targets from the current on-screen value and keeps velocity.
// - Animates transform and opacity only.
// - Reduced motion: transforms jump to their target, opacity cross-fades.
import { pref } from './prefs.js';

const REST = { x: 0, y: 0, s: 1, sx: 1, sy: 1, o: 1 };
const EPS = { x: 0.1, y: 0.1, s: 0.0005, sx: 0.0005, sy: 0.0005, o: 0.002 };
const active = new Set();
let raf = 0;
let last = 0;

function track(el) {
  if (!el.__spring) {
    el.__spring = { el, cur: { ...REST }, vel: { x: 0, y: 0, s: 0, sx: 0, sy: 0, o: 0 }, to: {}, k: 0, c: 0, resolve: null };
  }
  return el.__spring;
}

function write(t) {
  const { x, y, s, sx, sy, o } = t.cur;
  const moved = x !== 0 || y !== 0 || s !== 1 || sx !== 1 || sy !== 1;
  t.el.style.transform = moved ? `translate3d(${x.toFixed(2)}px, ${y.toFixed(2)}px, 0) scale(${(s * sx).toFixed(4)}, ${(s * sy).toFixed(4)})` : '';
  t.el.style.opacity = o >= 1 ? '' : Math.max(0, o).toFixed(3);
}

/** Jump to values with no motion (and cancel velocity for those properties). */
export function set(el, values) {
  const t = track(el);
  for (const k in values) { t.cur[k] = values[k]; t.vel[k] = 0; t.to[k] = values[k]; }
  write(t);
}

export function current(el) { return { ...track(el).cur }; }

/**
 * Spring el toward `to`. Resolves true when settled, false if another call interrupted it.
 * @param {object} to e.g. { y: 0, s: 1, o: 1 }
 * @param {{response?: number, damping?: number, velocity?: object}} opts
 */
export function animate(el, to, { response = 0.38, damping = 1, velocity } = {}) {
  const t = track(el);
  const reduce = pref.reduceMotion;
  for (const k in to) {
    t.to[k] = to[k];
    if (reduce && k !== 'o') { t.cur[k] = to[k]; t.vel[k] = 0; }
  }
  if (velocity && !reduce) Object.assign(t.vel, velocity);
  const r = reduce ? Math.min(response, 0.22) : response;
  const d = reduce ? 1 : damping;
  t.k = (2 * Math.PI / r) ** 2;
  t.c = (4 * Math.PI * d) / r;
  const prev = t.resolve;
  const p = new Promise((res) => { t.resolve = res; });
  if (prev) prev(false);
  active.add(t);
  write(t);
  if (!raf) { last = performance.now(); raf = requestAnimationFrame(tick); }
  return p;
}

function tick(now) {
  // Allow long frames (busy machine, game running) so motion keeps real time instead of
  // dragging in slow motion; 240 Hz sub-steps keep the integration stable.
  const dt = Math.min((now - last) / 1000, 0.1);
  last = now;
  const steps = Math.max(1, Math.ceil(dt * 240));
  const h = dt / steps;
  for (const t of active) {
    const keys = Object.keys(t.to);
    for (let i = 0; i < steps; i++) {
      for (const k of keys) {
        const a = -t.k * (t.cur[k] - t.to[k]) - t.c * t.vel[k];
        t.vel[k] += a * h;
        t.cur[k] += t.vel[k] * h;
      }
    }
    let settled = true;
    for (const k of keys) {
      if (Math.abs(t.cur[k] - t.to[k]) > EPS[k] || Math.abs(t.vel[k]) > EPS[k] * 10) { settled = false; break; }
    }
    if (settled) {
      for (const k of keys) { t.cur[k] = t.to[k]; t.vel[k] = 0; }
      active.delete(t);
      write(t);
      const res = t.resolve; t.resolve = null;
      if (res) res(true);
    } else {
      write(t);
    }
  }
  raf = active.size ? requestAnimationFrame(tick) : 0;
}
