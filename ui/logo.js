// The app logo, drawn on the spot from the accent colour (no image files, so any colour from the picker works and it follows the picker live).
// A dark rounded tile in the accent's hue, three bars in the accent (toned down a little), the middle bar a touch lighter.
// The shape is the same as the icon file (launcher/cyberloader.ico), which is not touched.
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));

function hexToHsl(hex) {
  const n = parseInt(hex.slice(1), 16), r = ((n >> 16) & 255) / 255, g = ((n >> 8) & 255) / 255, b = (n & 255) / 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b), d = max - min, l = (max + min) / 2;
  let h = 0;
  if (d) { h = max === r ? ((g - b) / d) % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4; h = (h * 60 + 360) % 360; }
  return [h, d ? d / (1 - Math.abs(2 * l - 1)) : 0, l];
}
const hsl = (h, s, l) => `hsl(${h.toFixed(1)} ${(s * 100).toFixed(1)}% ${(l * 100).toFixed(1)}%)`;

export function logoColors(accent) {
  const [h, s, l] = hexToHsl(/^#[0-9a-f]{6}$/i.test(accent) ? accent : '#FF375F');
  const grey = s < 0.08;
  const bs = grey ? 0 : Math.min(s, 0.86);          // toned down: saturation capped
  const bl = clamp(l, 0.52, 0.6);                    // never too dark or washed out
  return {
    tileA: hsl(h, grey ? 0 : Math.min(s, 0.5), 0.2),   // dark tile, hue at low strength
    tileB: hsl(h, grey ? 0 : Math.min(s, 0.25), 0.08),
    bar: hsl(h, bs, bl),
    mid: hsl(h, bs * 0.92, clamp(bl + 0.09, 0, 0.74)),
  };
}

export function logoSvg(accent, size = 26, id = 'logoGrad') {
  const c = logoColors(accent);
  return `<svg width="${size}" height="${size}" viewBox="0 0 256 256" aria-hidden="true" focusable="false"><defs><linearGradient id="${id}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="${c.tileA}"/><stop offset="1" stop-color="${c.tileB}"/></linearGradient></defs>
    <rect width="256" height="256" rx="56" fill="url(#${id})"/>
    <rect x="60.2" y="76.3" width="128" height="31.7" fill="${c.bar}"/>
    <rect x="85.8" y="114.7" width="122.9" height="31.7" fill="${c.mid}"/>
    <rect x="60.2" y="153.1" width="128" height="31.7" fill="${c.bar}"/></svg>`;
}
