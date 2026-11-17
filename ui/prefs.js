// Accessibility preferences, mirrored onto <html> as data attributes so CSS has one path.
// URL flags force them for testing: ?reducedMotion=1 ?reducedTransparency=1 ?contrast=1
const q = new URLSearchParams(location.search);
const root = document.documentElement;

const DEFS = [
  { key: 'reduceMotion', mq: '(prefers-reduced-motion: reduce)', flag: 'reducedMotion' },
  { key: 'reduceTransparency', mq: '(prefers-reduced-transparency: reduce)', flag: 'reducedTransparency' },
  { key: 'moreContrast', mq: '(prefers-contrast: more)', flag: 'contrast' },
];

export const pref = { reduceMotion: false, reduceTransparency: false, moreContrast: false };

for (const d of DEFS) {
  const mq = matchMedia(d.mq);
  const forced = q.has(d.flag) ? q.get(d.flag) !== '0' : null;
  const update = () => {
    const on = forced ?? mq.matches;
    pref[d.key] = on;
    if (on) root.dataset[d.key] = ''; else delete root.dataset[d.key];
  };
  update();
  mq.addEventListener?.('change', update);
}
