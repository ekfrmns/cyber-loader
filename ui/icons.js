// Inline SVG icons on a 20px grid, 1.6px strokes. Decorative: aria-hidden.
const P = {
  chevronDown: '<path d="M5.5 8l4.5 4.5L14.5 8"/>',
  chevronRight: '<path d="M8 5.5l4.5 4.5L8 14.5"/>',
  search: '<circle cx="8.8" cy="8.8" r="5.3"/><path d="M12.8 12.8l3.7 3.7"/>',
  more: '<circle cx="4.8" cy="10" r="1.35" fill="currentColor" stroke="none"/><circle cx="10" cy="10" r="1.35" fill="currentColor" stroke="none"/><circle cx="15.2" cy="10" r="1.35" fill="currentColor" stroke="none"/>',
  check: '<path d="M5 10.4l3.3 3.3L15.2 6.8"/>',
  close: '<path d="M6 6l8 8M14 6l-8 8"/>',
  warning: '<path d="M8.7 3.9L2.9 14.2a1.5 1.5 0 0 0 1.3 2.3h11.6a1.5 1.5 0 0 0 1.3-2.3L11.3 3.9a1.5 1.5 0 0 0-2.6 0z"/><path d="M10 8v3.4"/><circle cx="10" cy="14" r=".55" fill="currentColor"/>',
  conflict: '<rect x="3" y="3" width="9.5" height="9.5" rx="2.2"/><path d="M7.5 15.2v.3a1.5 1.5 0 0 0 1.5 1.5h6.5a1.5 1.5 0 0 0 1.5-1.5V9a1.5 1.5 0 0 0-1.5-1.5h-.3"/>',
  core: '<path d="M10 3.2l6.6 3.3L10 9.8 3.4 6.5z"/><path d="M3.4 10L10 13.3l6.6-3.3"/><path d="M3.4 13.5L10 16.8l6.6-3.3"/>',
  plus: '<path d="M10 4.5v11M4.5 10h11"/>',
  body: '<circle cx="10" cy="6.4" r="2.9"/><path d="M4.4 16.6c.6-3.4 2.8-5.2 5.6-5.2s5 1.8 5.6 5.2"/>',
  characters: '<circle cx="7.4" cy="7" r="2.5"/><path d="M2.6 16c.4-2.8 2.3-4.4 4.8-4.4s4.4 1.6 4.8 4.4"/><circle cx="13.9" cy="7.6" r="2"/><path d="M13.7 11.8c2 .1 3.2 1.4 3.7 3.7"/>',
  clothing: '<path d="M7 3.5L3 6.1l1.7 3L7 8.1V16h6V8.1l2.3 1 1.7-3L13 3.5c-.5 1.2-1.6 1.9-3 1.9S7.5 4.7 7 3.5z"/>',
  gameplay: '<rect x="2.8" y="6.2" width="14.4" height="8" rx="4"/><path d="M6.6 8.7v2.6M5.3 10h2.6"/><circle cx="13" cy="9.2" r=".75" fill="currentColor"/><circle cx="14.9" cy="11" r=".75" fill="currentColor"/>',
  content: '<path d="M10 3l1.6 4.4L16 9l-4.4 1.6L10 15l-1.6-4.4L4 9l4.4-1.6z"/>',
  other: '<rect x="3.5" y="3.5" width="5.2" height="5.2" rx="1.4"/><rect x="11.3" y="3.5" width="5.2" height="5.2" rx="1.4"/><rect x="3.5" y="11.3" width="5.2" height="5.2" rx="1.4"/><rect x="11.3" y="11.3" width="5.2" height="5.2" rx="1.4"/>',
  pencil:'<path d="M12.6 4.6l2.8 2.8"/><path d="M4.2 15.8l.7-3.4 8.7-8.7a1.4 1.4 0 0 1 2 0l.7.7a1.4 1.4 0 0 1 0 2l-8.7 8.7z"/>',
  save: '<path d="M5 3.5h7.8l3.2 3.2v8.8a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1v-11a1 1 0 0 1 1-1z"/><path d="M7 3.5V7h5.5V3.5"/><path d="M6.8 16.5v-4.3h6.4v4.3"/>',
  trash: '<path d="M3.8 6h12.4"/><path d="M8 6V4.3h4V6"/><path d="M5.4 6l.8 9.6a1 1 0 0 0 1 .9h5.6a1 1 0 0 0 1-.9l.8-9.6"/>',
  restore: '<path d="M3.8 10a6.2 6.2 0 1 0 1.9-4.5"/><path d="M3.8 3.8v3.6h3.6"/>',
  appearance: '<circle cx="10" cy="10" r="6.5"/><path d="M10 3.5a6.5 6.5 0 0 1 0 13z" fill="currentColor"/>',
  import: '<path d="M10 3.5v9"/><path d="M6.5 9.2l3.5 3.5 3.5-3.5"/><path d="M3.5 12.8v2.7a1 1 0 0 0 1 1h11a1 1 0 0 0 1-1v-2.7"/>',
  info: '<circle cx="10" cy="10" r="6.8"/><path d="M10 9v4.5"/><circle cx="10" cy="6.6" r=".55" fill="currentColor"/>',
  folder: '<path d="M3 6a1.5 1.5 0 0 1 1.5-1.5h3.2l1.6 1.8h6.2A1.5 1.5 0 0 1 17 7.8v6.7a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 3 14.5z"/>',
  plusCircle: '<circle cx="10" cy="10" r="6.8"/><path d="M10 7v6M7 10h6"/>',
  minusCircle: '<circle cx="10" cy="10" r="6.8"/><path d="M7 10h6"/>',
};

export function icon(name, size = 20, cls = '') {
  return `<svg class="ic${cls ? ' ' + cls : ''}" width="${size}" height="${size}" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">${P[name] || ''}</svg>`;
}

/** Replace <span data-icon="name" data-size="16"> placeholders in static HTML. */
export function hydrateIcons(root = document) {
  for (const el of root.querySelectorAll('[data-icon]')) {
    el.innerHTML = icon(el.dataset.icon, Number(el.dataset.size) || 20);
    el.removeAttribute('data-icon');
  }
}
