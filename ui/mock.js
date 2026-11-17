// Mock engine for building and testing the UI without touching anything on disk.
// Shaped like the real library: 164 mods in 7 groups, long names, 4 sample profile names,
// a handful of requires and 7 mods in conflict.
//
// URL flags (with ?mock=1): empty=1 (empty library), fail=1 (state errors), slow=1,
// running=1 (game starts running), applyFail=1 (apply fails at ~60%).
const q = new URLSearchParams(location.search);
const SLOW = q.has('slow') ? 3 : 1;

// [id, name, files, requires[]]
const FRAMEWORK = [
  ['red4ext', 'RED4ext', 4, []],
  ['redscript', 'redscript 0.5.27', 18, []],
  ['cet', 'CET 1.0.0 - sample build', 212, []],
  ['archivexl', 'ArchiveXL', 6, ['red4ext']],
  ['tweakxl', 'TweakXL', 5, ['red4ext']],
  ['codeware', 'Codeware', 7, ['red4ext']],
  ['modsettings', 'Settings Library', 9, ['red4ext', 'redscript']],
  ['nativesettings', 'In-Game Settings Panel', 6, ['cet']],
  ['inputloader', 'Key Binding Loader', 3, ['red4ext']],
  ['audioware', 'Audioware', 5, ['red4ext']],
  ['redfs', 'File System Helper', 3, ['red4ext']],
  ['reddata', 'Data Store Helper', 2, ['red4ext']],
  ['questcore', 'Quest Helper Library', 14, ['redscript', 'codeware']],
  ['equipex', 'Gear Slots Extended', 11, ['archivexl', 'codeware']],
  ['cyberwareex', 'Implant Slots Extended', 9, ['tweakxl', 'redscript']],
  ['virtualatelier', 'Virtual Boutique', 8, ['redscript']],
  ['ccxl', 'Character Creator Add-ons', 4, ['archivexl']],
  ['radioext', 'Radio Extender', 6, ['red4ext', 'cet']],
  ['nif', 'Interaction Framework', 5, ['codeware']],
  ['luakit', 'Lua Kit', 2, ['cet']],
  ['cetfonts', 'Overlay Fonts Pack', 3, ['cet']],
  ['redhottools', 'Hot Reload Tools', 4, ['red4ext']],
  ['worldbuilder', 'World Builder Core', 37, ['cet', 'archivexl']],
  ['mspatch', 'Settings Library Patch', 1, ['modsettings']],
  ['acucore', 'Appearance Unlock Core', 2, ['tweakxl']],
  ['dlssenabler', 'Upscaler Enabler', 4, []],
];

const BODY = [
  ['ebb', 'Body Shape Enhancer 5.0 + Microdetail patch', 46, ['archivexl']],
  ['angelbody', 'Angel Body Base Mesh - All Body Types', 38, ['archivexl']],
  ['naturalskin', 'Natural Skin Textures 4K', 24, []],
  ['bodyhair', 'Better Body Hair - Male and Female', 12, ['archivexl']],
  ['hdeyes', 'HD Eyes Reworked (Iris and Sclera)', 10, []],
  ['nails', 'Painted Nails - All Body Types', 18, ['archivexl']],
  ['feet', 'Realistic Feet and Toenails', 9, []],
  ['freckles', 'Body Freckles and Moles Pack', 7, ['archivexl']],
  ['smoothskin', 'Smooth Skin Textures - No Pores', 6, []],
  ['tattoos', 'Tattoo Pack - Street Ink Collection Vol. 2', 31, ['archivexl', 'ccxl']],
  ['muscle', 'Muscle Definition Normal Maps', 8, []],
  ['scars', 'Scars and Burns Overlay', 5, ['ccxl']],
  ['vbodyfix', 'Vanilla Body Fix', 4, []],
  ['eyebrows', 'Lush Eyebrows Retexture', 3, []],
  ['teeth', 'Teeth and Gums HD', 4, []],
  ['tanlines', 'Better Tan Lines', 3, []],
  ['chromeseams', 'Chrome Cyberware Skin Seams', 6, []],
  ['bodyselector', 'Body Type Selector for Character Creator', 3, ['ccxl']],
  ['hands', 'Realistic Hands - Veins and Knuckles', 5, []],
];

const CHARACTERS = [
  'Panam Palmer - Hair Refresh and Freckles', 'Judy Alvarez - Alternate Outfits and Hair', 'Johnny Silverhand Samurai Jacket Retexture',
  'Crowd Variety Expanded (NPC Appearances)', 'Viktor Vektor Clinic Look', 'Misty Olszewski Tarot Outfit', 'Kerry Eurodyne Tour Outfit',
  'River Ward Detective Coat', 'Rogue Amendiares Classic Look', 'Takemura Casual Suit', 'Claire Russell Garage Outfit',
  'Jackie Welles - Appearance Variants', 'Songbird Alternate Hair', 'Solomon Reed Field Agent Gear', 'Alt Cunningham Netrunner Glow',
  'Evelyn Parker HD Retexture', 'Meredith Stout Corpo Variants', 'Hanako Arasaka Kimono Retexture', 'Lizzy Wizzy Chrome Remaster',
  'Mitch Anderson Nomad Look', 'Saul Bright Aldecaldo Gear', 'Dexter DeShawn Suit Variants', 'Brendan Vending Machine Skins',
  'Mr. Blue Eyes Variant', 'Nix Netrunner Rig', 'Wakako Okada Kimono', 'Placide Voodoo Boys Outfit', 'Padre Church Robes',
  'Regina Jones Fixer Look', 'Kurt Hansen Dogtown Gear', 'Mama Welles Apron Retexture', 'Ozob Bozo Grenade Nose HD',
].map((n, i) => [slug(n), n, 3 + ((i * 7) % 23), i % 3 === 0 ? ['archivexl'] : []]);

const CLOTHING = [
  ['streetkid', 'Street Kid Wardrobe Pack', 84, ['archivexl', 'tweakxl']],
  ['corposuits', 'Corpo Suits Collection - 40 Variants', 62, ['archivexl', 'tweakxl']],
  ['nomadboots', 'Nomad Boots and Belts', 14, ['archivexl']],
  ['transmog', 'Wardrobe Transmog Extended', 11, ['equipex', 'virtualatelier']],
  ['visors', 'Visor and Tech Glasses Pack', 23, ['archivexl']],
  ['hdjackets', 'HD Jacket Textures 4K', 40, []],
  ['bomber', 'Neon Arasaka Bomber Jacket', 6, ['archivexl']],
  ['militechvest', 'Militech Tactical Vest Set', 9, ['archivexl']],
  ['kitsch', 'Kitsch Crop Tops - All Body Types', 17, ['archivexl']],
  ['netrunnersuit', 'Netrunner Suit Overhaul', 12, []],
  ['valentinos', 'Valentinos Gold Chains', 5, ['archivexl']],
  ['maelstrom', 'Maelstrom Spiked Leather', 8, ['archivexl']],
  ['tygerclaws', 'Tyger Claws Kimono Jackets', 10, ['archivexl']],
  ['sixthstreet', '6th Street Patriot Gear', 7, ['archivexl']],
  ['animals', 'Animals Gym Wear', 6, ['archivexl']],
  ['ponchos', 'Aldecaldo Ponchos and Scarves', 9, ['archivexl']],
  ['voodoo', 'Voodoo Boys Mesh Shirts', 4, ['archivexl']],
  ['mox', 'Mox Fishnet and Lace', 7, ['archivexl']],
  ['gloves', 'Biker Gloves Pack', 5, []],
  ['sneakers', 'Cyberpunk Sneakers Collection 2.0', 21, ['archivexl']],
  ['longcoats', 'Long Coats - Physics Enabled', 15, ['archivexl']],
  ['hats', 'Hats and Caps Megapack', 33, ['archivexl', 'tweakxl']],
  ['sleepwear', 'Sleepwear Set - Body Shape Compatible', 14, ['ebb']],
  ['swimwear', 'Swimwear Pack for Pacifica', 12, ['archivexl']],
  ['winter', 'Winter Clothes for Night City (Cold Weather Pack)', 26, ['archivexl']],
  ['heels', 'Corpo Heels and Pumps', 8, ['archivexl']],
  ['masks', 'Masks and Bandanas Collection', 11, ['archivexl']],
];

const GAMEPLAY = [
  ['coopmod', 'Co-op Framework', 58, ['red4ext', 'codeware', 'cet']],
  ['vehiclepack', 'Vehicle Pack', 19, ['codeware', 'redscript']],
  ['vehiclehandling', 'Better Vehicle Handling', 7, ['tweakxl']],
  ['traffic', 'Immersive Traffic Density', 10, ['tweakxl']],
  ['weather', 'Weather Control Panel', 6, ['cet', 'nativesettings']],
  ['quickhacks', 'Quickhack Rebalance', 4, ['tweakxl']],
  ['stash', 'Shared Stash', 3, ['redscript']],
  ['photomode', 'Photo Mode Extras', 5, ['cet']],
  ['amm', 'Appearance Menu Pro', 96, ['cet', 'archivexl']],
  ['flight', 'Skyline Flight', 22, ['red4ext', 'tweakxl', 'inputloader']],
  ['rippers', 'Ripper Clinics Plus', 8, ['redscript']],
  ['nointro', 'Skip Intro Videos', 2, []],
  ['lootmarkers', 'Better Loot Markers', 4, ['redscript']],
  ['damage', 'Realistic Damage Scaling', 3, ['tweakxl']],
  ['kiroshi', 'Optics Crowd Scanner', 6, ['cet', 'codeware']],
  ['fasttravel', 'Fast Travel Anywhere', 3, ['cet']],
  ['police', 'Police Response Overhaul', 9, ['tweakxl', 'redscript']],
  ['limitedhud', 'Minimal HUD', 7, ['redscript', 'modsettings']],
  ['metro', 'Metro System Expanded', 14, ['codeware']],
  ['dogtownpatrols', 'Enhanced Police - Dogtown Patrols', 5, ['tweakxl']],
  ['aptinteractions', 'Better Apartment Interactions', 6, ['codeware', 'nif']],
  ['hangouts', 'Friendly Hangouts', 18, ['cet', 'codeware']],
  ['silencers', 'Quiet Suppressors', 2, ['tweakxl']],
  ['scrapper', 'Better Scrapping', 3, ['redscript', 'modsettings']],
  ['durability', 'Dynamic Weapon Durability', 4, ['redscript']],
];

const CONTENT = [
  'Additional Apartments - Corpo Plaza Penthouse', 'Night City Billboards Remastered', 'Extra Radio Stations - 89.3 Static FM',
  'Classic Cars Pack (Quadra, Thorton, Mizutani)', 'Northside Motel Interiors', 'Japantown Night Market', 'New Bars of Westbrook',
  'Pacifica Beach Club', 'Dogtown Safehouse', 'Abandoned Mall Arena', 'Custom Holo-Ads Collection', 'Aerodyne Taxi Service',
  'Badlands Gas Station Interior', 'Afterlife Expanded', 'Lizzie’s Bar VIP Rooms', 'Corpo Plaza Office Tower', 'Glen Apartment Remodel',
  'Watson Docks Container Yard', 'Kabuki Arcade', 'Heywood Lowrider Garage', 'Arasaka Waterfront Warehouse', 'Rocky Ridge Cabin',
  'Night City Interiors Overhaul - Part 1', 'Night City Interiors Overhaul - Part 2',
].map((n, i) => [slug(n), n, 12 + ((i * 37) % 190), n.includes('Radio') ? ['radioext'] : i % 2 ? ['archivexl'] : ['archivexl', 'codeware']]);

const OTHER = [
  ['reshade', 'Neon Noir ReShade Preset', 3, []],
  ['lut', 'Cinematic LUT - Film Grain Off', 2, []],
  ['loadingscreens', 'Custom Loading Screens - Photo Mode Shots', 12, []],
  ['hudfonts', 'Readable HUD Fonts', 6, []],
  ['mainmenu', 'Main Menu Background Replacer', 3, []],
  ['ultraplus', 'Ultra Plus Path Tracing Config', 5, ['cet']],
  ['fsr3', 'FSR 3 Frame Gen Config', 2, []],
  ['subtitles', 'Better Subtitles', 2, []],
  ['sirens', 'Quieter Ambient Sirens', 4, []],
  ['streamersafe', 'Streamer Safe Radio', 3, ['radioext']],
  ['testarchive', 'Mod Manager Test Archive (empty)', 0, []],
];

function slug(s) { return s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 48); }

const SETS = { Framework: FRAMEWORK, Body: BODY, Characters: CHARACTERS, Clothing: CLOTHING, Gameplay: GAMEPLAY, Content: CONTENT, Other: OTHER };
let mods = q.has('empty') ? [] : Object.entries(SETS).flatMap(([group, rows]) =>
  rows.map(([id, name, files, requires]) => ({ id, name, group, files, framework: group === 'Framework', requires })));
const byId = new Map(mods.map((m) => [m.id, m]));

// What the real engine guesses from a mod's files (docs/API.md `autoRequires`): { name, ids: suppliers in the library }.
const AUTO = {
  netrunnersuit: [{ name: 'ArchiveXL', ids: ['archivexl'] }],
  gloves: [{ name: 'ArchiveXL', ids: ['archivexl'] }, { name: 'TweakXL', ids: ['tweakxl'] }],
};
for (const m of mods) m.autoRequires = AUTO[m.id] || [];
function autoMissing(m) { return m.autoRequires.filter((n) => !n.ids.some((i) => enabled.has(i))); }

// Files shared between mods. The last mod listed wins. 7 mods in total are involved.
const CONFLICTS = [
  { ids: ['naturalskin', 'smoothskin'], paths: ['archive/pc/mod/skin_body_d01.archive', 'archive/pc/mod/skin_body_n01.archive', 'archive/pc/mod/skin_face_d01.archive', 'archive/pc/mod/skin_face_n01.archive', 'archive/pc/mod/skin_detail_mask.archive', 'archive/pc/mod/skin_roughness.archive'] },
  { ids: ['traffic', 'vehiclehandling'], paths: ['r6/tweaks/vehicles/traffic_ai_speed.yaml', 'r6/tweaks/vehicles/handling_base.yaml'] },
  { ids: ['japantown-night-market', 'kabuki-arcade', 'night-city-interiors-overhaul-part-1'], paths: ['archive/pc/mod/jpn_market_props.archive', 'archive/pc/mod/kabuki_streetlights.archive', 'archive/pc/mod/watson_signage.archive'] },
];

function pathsFor(m) {
  const shared = CONFLICTS.filter((c) => c.ids.includes(m.id)).flatMap((c) => c.paths);
  const out = [...shared];
  const base = m.id.replace(/-/g, '_');
  for (let i = out.length; i < m.files; i++) {
    if (m.id === 'cet') out.push(i === 0 ? 'bin/x64/version.dll' : `bin/x64/plugins/cyber_engine_tweaks/scripts/module_${i}.lua`);
    else if (m.group === 'Framework') out.push(i === 0 ? `red4ext/plugins/${base}/${base}.dll` : `red4ext/plugins/${base}/data_${i}.bin`);
    else if (m.group === 'Gameplay') out.push(i % 2 ? `r6/scripts/${base}/module_${i}.reds` : `r6/tweaks/${base}/tweak_${i}.yaml`);
    else if (m.group === 'Other') out.push(`bin/x64/reshade-shaders/${base}_${i}.fx`);
    else out.push(`archive/pc/mod/${base}_${String(i).padStart(2, '0')}.archive`);
  }
  return out;
}

// ---------- Profiles and state ----------
const FW = FRAMEWORK.map((r) => r[0]);
const ids = (rows) => rows.map((r) => r[0]);
const coopBase = ['red4ext', 'redscript', 'cet', 'codeware', 'coopmod'];
const profiles = new Map([
  ['Empty', new Set()],
  ['Core only', new Set(coopBase)],
  ['Core + Vehicles + extras', new Set([...FW, 'coopmod', 'vehiclepack', 'vehiclehandling', 'traffic', 'weather', 'stash', 'photomode', 'amm', 'nointro', 'lootmarkers', 'limitedhud',
    'naturalskin', 'hdeyes', 'eyebrows', 'teeth', 'hands', ...ids(CLOTHING).slice(0, 8), ...ids(CHARACTERS).slice(0, 10), ...ids(CONTENT).slice(0, 7), 'reshade', 'hudfonts', 'subtitles'])],
  ['Full Night City', new Set([...FW, ...ids(BODY).filter((i) => i !== 'smoothskin'), ...ids(CLOTHING), ...ids(CHARACTERS), 'amm', 'photomode', 'hangouts', 'ultraplus', 'lut', 'loadingscreens'])],
]);
for (const set of profiles.values()) for (const id of [...set]) if (!byId.has(id)) set.delete(id);

let current = 'Core + Vehicles + extras';
let enabled = new Set(profiles.get(current));
let deployed = new Set(enabled);
let running = q.get('running') === '1';
let job = null;
let settings = { theme: 'system', accent: '#0A84FF' };
try { Object.assign(settings, JSON.parse(localStorage.getItem('cmm.settings') || '{}')); } catch { /* ignore */ }
const imports = new Map();
let trash = [];   // deleted mods: { tid, m, at }

const sameSet = (a, b) => a.size === b.size && [...a].every((x) => b.has(x));
const nameOf = (id) => byId.get(id)?.name ?? id;

function conflictsOf(id) {
  if (!enabled.has(id)) return 0;
  let n = 0;
  for (const c of CONFLICTS) {
    if (!c.ids.includes(id)) continue;
    if (c.ids.filter((x) => enabled.has(x)).length > 1) n += c.paths.length;
  }
  return n;
}

// Sample setup history (docs/API.md "Setup history"). Mods whose id is not in the sample library count as "missing".
const nm = (id) => byId.get(id)?.name || id;
const snapMod = (id, extra = {}) => ({ id, name: nm(id), version: null, date: null, nexusId: null, files: byId.get(id)?.files || 0, ...extra });
const SNAPS = [
  { id: 's3', at: '2026-11-17 21:40:12', profile: 'Core + Vehicles + extras', auto: true, pinned: false, name: null,
    mods: [snapMod('red4ext', { version: '1.31.0', date: '2026-10-02', nexusId: 2380 }), snapMod('archivexl', { version: '1.20.2', date: '2026-10-20', nexusId: 4198, changed: true }), snapMod('tweakxl')] },
  { id: 's2', at: '2026-11-16 18:05:44', profile: 'Core + Vehicles + extras', auto: true, pinned: false, name: null,
    mods: [snapMod('red4ext'), snapMod('old-key-loader', { name: 'Key Binding Loader', version: '0.2.6', date: '2026-10-26', nexusId: 4575 }), snapMod('tweakxl'), snapMod('old-radio', { name: 'Radio Pack (removed)', version: null, nexusId: null })] },
  { id: 's1', at: '2026-11-15 22:10:03', profile: 'Core + Vehicles + extras', auto: false, pinned: true, name: 'Works before the patch',
    mods: [snapMod('red4ext'), snapMod('archivexl'), snapMod('redscript')] },
];
const snapStatus = (m) => (!byId.has(m.id) ? 'missing' : m.changed ? 'changed' : 'same');
function snapItem(s) {
  const ids = s.mods.map((m) => m.id);
  return { id: s.id, at: s.at, profile: s.profile, auto: s.auto, pinned: s.pinned, name: s.name, count: ids.length,
    turnOn: ids.filter((i) => byId.has(i) && !enabled.has(i)).length, turnOff: [...enabled].filter((i) => !ids.includes(i)).length,
    missing: ids.filter((i) => !byId.has(i)).length, changed: s.mods.filter((m) => m.changed && byId.has(m.id)).length };
}
function snapDetail(s) {
  return { id: s.id, at: s.at, profile: s.profile, auto: s.auto, pinned: s.pinned, name: s.name,
    mods: s.mods.map((m) => ({ id: m.id, name: m.name, version: m.version, date: m.date, nexusId: m.nexusId, on: enabled.has(m.id), status: snapStatus(m),
      ...(snapStatus(m) === 'missing' && m.id === 'old-key-loader' ? { replacedBy: { id: 'inputloader', name: 'Key Binding Loader', version: '0.2.7', date: '2026-11-02' } } : {}) })) };
}

function view(m) {
  const on = enabled.has(m.id);
  return { id: m.id, name: m.name, group: m.group, files: m.files, enabled: on, pending: on === deployed.has(m.id) ? null : on ? 'on' : 'off', framework: m.framework, requires: [...m.requires], autoRequires: m.autoRequires.map((n) => ({ name: n.name, ids: [...n.ids] })), conflicts: conflictsOf(m.id) };
}

function state() {
  const v = mods.map(view);
  return {
    game: { running },
    profile: current,
    profiles: [...profiles.keys()],
    profileDirty: current ? !sameSet(enabled, profiles.get(current)) : false,
    deployedCount: [...deployed].reduce((a, id) => a + (byId.get(id)?.files || 0), 0),
    pendingCount: { on: v.filter((m) => m.pending === 'on').length, off: v.filter((m) => m.pending === 'off').length },
    mods: v,
  };
}

function warnings() {
  const w = [];
  for (const m of mods) {
    if (!enabled.has(m.id)) continue;
    const off = m.requires.filter((r) => !enabled.has(r));
    for (const r of off) w.push(`${nameOf(r)} is off but ${m.name} needs it`);
    for (const n of autoMissing(m)) w.push(`${m.name} needs ${n.name}, which is off`);
  }
  return w;
}

function progress() {
  if (!job) return { state: 'idle', percent: 0, text: '' };
  if (job.final) return job.final;
  const pct = Math.min(100, ((performance.now() - job.start) / job.duration) * 100);
  if (q.has('applyFail') && pct >= 60) {
    job.final = { state: 'error', percent: 60, text: 'Couldn’t link archive/pc/mod/skin_body_d01.archive: the file is in use (mock).' };
    return job.final;
  }
  if (pct >= 100) {
    deployed = new Set(enabled);
    job.final = { state: 'done', percent: 100, text: `Linked ${job.add.toLocaleString('en-US')} files, removed ${job.remove.toLocaleString('en-US')}` };
    return job.final;
  }
  const text = pct < 25 ? `Removing ${job.remove.toLocaleString('en-US')} old links…` : pct < 88 ? `Linking ${job.add.toLocaleString('en-US')} files…` : 'Checking the game folder…';
  return { state: 'running', percent: Math.round(pct), text };
}

const delay = () => new Promise((r) => setTimeout(r, (80 + Math.random() * 120) * SLOW));
const ok = (json) => ({ status: 200, json });
const err = (status, error) => ({ status, json: { error } });

// ---------- Mock controls (dev only) ----------
export function setGameRunning(v) { running = !!v; }
export function isGameRunning() { return running; }

// ---------- Request handler ----------
export async function handle(method, url, body = {}) {
  await delay();
  const [path, qs] = url.split('?');
  const params = new URLSearchParams(qs || '');
  const route = `${method} ${path}`;

  if (q.has('fail') && route === 'GET /api/state') return err(500, 'The engine couldn’t read the mod library at C:\\CyberLoader\\data\\library (mock failure).');

  if (method === 'GET' && path.startsWith('/api/snapshots/')) {
    const s = SNAPS.find((x) => x.id === path.slice('/api/snapshots/'.length));
    return s ? ok(snapDetail(s)) : err(404, 'that snapshot no longer exists');
  }

  switch (route) {
    case 'GET /api/state':
      return ok(state());

    case 'GET /api/snapshots':
      return ok({ items: SNAPS.map(snapItem) });

    case 'POST /api/snapshots/save': {
      const mods = [...enabled].map((id) => ({ id, name: nameOf(id), version: null, date: null, nexusId: null, files: byId.get(id)?.files || 0 }));
      SNAPS.unshift({ id: `s${Date.now()}`, at: new Date().toISOString().slice(0, 19).replace('T', ' '), profile: current, auto: false, pinned: true, name: body.name || 'Kept setup', mods });
      return ok({ ok: true, id: SNAPS[0].id });
    }

    case 'POST /api/snapshots/pin': {
      const s = SNAPS.find((x) => x.id === body.id);
      if (!s) return err(404, 'that snapshot no longer exists');
      s.pinned = body.pinned !== false;
      if (body.name !== undefined) s.name = body.name || null;
      return ok({ ok: true, pinned: s.pinned, name: s.name });
    }

    case 'POST /api/snapshots/restore': {
      const s = SNAPS.find((x) => x.id === body.id);
      if (!s) return err(404, 'that snapshot no longer exists');
      const keep = s.mods.filter((m) => byId.has(m.id));
      enabled = new Set(keep.map((m) => m.id));
      return ok({ ...state(), restored: { count: keep.length, missing: s.mods.filter((m) => !byId.has(m.id)).map((m) => ({ name: m.name, version: m.version, date: m.date, nexusId: m.nexusId })), changed: s.mods.filter((m) => m.changed).length } });
    }

    case 'POST /api/mod/requires': {
      const m = byId.get(body.id);
      if (!m) return err(404, 'That mod is no longer in the library.');
      if (!Array.isArray(body.requires) || body.requires.some((r) => r === m.id || !byId.has(r))) return err(400, 'Pick other mods from the library.');
      m.requires = [...new Set(body.requires)];
      const w = enabled.has(m.id) ? m.requires.filter((r) => !enabled.has(r)).map((r) => `${m.name} needs ${nameOf(r)}, which is off`) : [];
      return ok({ ok: true, mod: view(m), warnings: w });
    }

    case 'POST /api/toggle': {
      const m = byId.get(body.id);
      if (!m) return err(404, 'That mod is no longer in the library.');
      if (job && !job.final) return err(423, 'Wait for the current apply to finish.');
      if (body.enabled) enabled.add(m.id); else enabled.delete(m.id);
      const w = [];
      if (!body.enabled) for (const d of mods) if (enabled.has(d.id) && (d.requires.includes(m.id) || autoMissing(d).some((n) => n.ids.includes(m.id)))) w.push(`${m.name} is off but ${d.name} needs it`);
      if (body.enabled) {
        for (const r of m.requires) if (!enabled.has(r)) w.push(`${m.name} needs ${nameOf(r)}, which is off`);
        for (const n of autoMissing(m)) w.push(`${m.name} needs ${n.name}, which is off`);
      }
      return ok({ ok: true, mod: view(m), warnings: w });
    }

    case 'POST /api/discard':
      enabled = new Set(deployed);
      return ok(state());

    case 'POST /api/profile/select': {
      if (!profiles.has(body.name)) return err(404, `There’s no profile called “${body.name}”.`);
      current = body.name;
      enabled = new Set(profiles.get(current));
      return ok(state());
    }
    case 'POST /api/profile/save':
      profiles.set(body.name, new Set(enabled));
      return ok({ ok: true });
    case 'POST /api/profile/new': {
      const name = String(body.name || '').trim();
      if (!name) return err(400, 'Give the profile a name.');
      if (profiles.has(name)) return err(400, `A profile called “${name}” already exists.`);
      profiles.set(name, body.from && profiles.has(body.from) ? new Set(body.from === current ? enabled : profiles.get(body.from)) : new Set());
      return ok({ ok: true });
    }
    case 'GET /api/trash':
      return ok({ items: trash.map((t) => ({ id: t.tid, name: t.m.name, group: t.m.group, files: t.m.files, size: t.m.files * 3_400_000 + 20_000, deletedAt: t.at })),
                  totalSize: trash.reduce((a, t) => a + t.m.files * 3_400_000 + 20_000, 0) });
    case 'POST /api/mod/delete': {
      const m = byId.get(body.id);
      if (!m) return err(404, 'That mod no longer exists.');
      if (deployed.has(m.id)) return err(409, `“${m.name}” is in the game right now. Turn it off and apply first, then delete it.`);
      mods = mods.filter((x) => x.id !== m.id); byId.delete(m.id); enabled.delete(m.id);
      trash.unshift({ tid: `20261116-19${String(trash.length).padStart(2, '0')}00-${String(1000 + trash.length)}`, m, at: '2026-11-16 19:00:00' });
      return ok({ ok: true, trashId: trash[0].tid, name: m.name });
    }
    case 'POST /api/trash/restore': {
      const i = trash.findIndex((t) => t.tid === body.id);
      if (i < 0) return err(404, 'That item is no longer in the trash.');
      const [t] = trash.splice(i, 1);
      mods.push(t.m); byId.set(t.m.id, t.m);
      return ok({ ok: true, id: t.m.id, name: t.m.name });
    }
    case 'POST /api/trash/empty': {
      const n = body.id ? trash.filter((t) => t.tid === body.id).length : trash.length;
      trash = body.id ? trash.filter((t) => t.tid !== body.id) : [];
      return ok({ ok: true, removed: n, freed: 0 });
    }
    case 'POST /api/profile/rename': {
      const to = String(body.to || '').trim();
      if (!profiles.has(body.name)) return err(404, 'That profile no longer exists.');
      if (!to) return err(400, 'Give the profile a name.');
      if (to.toLowerCase() !== body.name.toLowerCase() && [...profiles.keys()].some((p) => p.toLowerCase() === to.toLowerCase())) return err(409, `A profile called “${to}” already exists.`);
      const entries = [...profiles.entries()].map(([k, v]) => [k === body.name ? to : k, v]);
      profiles.clear();
      for (const [k, v] of entries) profiles.set(k, v);
      if (current === body.name) current = to;
      return ok({ ok: true, profile: current, profiles: [...profiles.keys()] });
    }
    case 'POST /api/profile/delete': {
      if (!profiles.has(body.name)) return err(404, 'That profile no longer exists.');
      if (profiles.size === 1) return err(400, 'You need at least one profile.');
      profiles.delete(body.name);
      if (current === body.name) { current = [...profiles.keys()][0]; enabled = new Set(profiles.get(current)); }
      return ok({ ok: true });
    }

    case 'POST /api/preview': {
      const add = [], remove = [];
      for (const m of mods) {
        const on = enabled.has(m.id), was = deployed.has(m.id);
        if (on && !was) for (const p of pathsFor(m)) add.push({ id: m.id, path: p });
        if (!on && was) for (const p of pathsFor(m)) remove.push({ id: m.id, path: p });
      }
      const conflicts = [];
      for (const c of CONFLICTS) {
        const live = c.ids.filter((x) => enabled.has(x));
        if (live.length < 2) continue;
        for (const p of c.paths) conflicts.push({ path: p, winner: live[live.length - 1], losers: live.slice(0, -1) });
      }
      return ok({ add: add.length, remove: remove.length, conflicts, warnings: warnings(), files: { add, remove }, filesTruncated: false });
    }

    case 'POST /api/apply': {
      if (running) return err(409, 'Cyberpunk 2077 is running. Close the game, then apply.');
      if (job && !job.final) return err(423, 'An apply is already running.');
      let add = 0, remove = 0;
      for (const m of mods) {
        if (enabled.has(m.id) && !deployed.has(m.id)) add += m.files;
        if (!enabled.has(m.id) && deployed.has(m.id)) remove += m.files;
      }
      job = { start: performance.now(), duration: 3600 * SLOW, add, remove, final: null };
      return ok({ ok: true });
    }
    case 'GET /api/progress':
      return ok(progress());


    case 'GET /api/settings':
      return ok({ ...settings });
    case 'POST /api/settings':
      if (body.theme) settings.theme = body.theme;
      if (body.accent) settings.accent = body.accent;
      return ok({ ...settings });

    case 'POST /api/import/begin': {
      const token = Math.random().toString(36).slice(2, 10);
      imports.set(token, { name: String(body.name || 'Imported mod'), kind: body.kind, files: 0 });
      return ok({ token });
    }
    case 'PUT /api/import/file': {
      const imp = imports.get(params.get('token'));
      if (!imp) return err(400, 'Upload expired. Try dropping it again.');
      imp.files++;
      return ok({ ok: true });
    }
    case 'POST /api/import/finish': {
      const imp = imports.get(body.token);
      if (!imp) return err(400, 'Upload expired. Try dropping it again.');
      imports.delete(body.token);
      const clean = imp.name.replace(/\.(zip|7z|rar)$/i, '').replace(/[-_]+/g, ' ').replace(/\s+\d+(\s+\d+)*$/, '').trim() || 'Imported mod';
      let id = slug(clean) || 'imported';
      while (byId.has(id)) id += '-2';
      const m = { id, name: clean, group: 'Other', files: imp.kind === 'archive' ? 8 : imp.files, framework: false, requires: [] };
      mods.push(m); byId.set(id, m);
      const w = /\.rar$/i.test(imp.name) ? ['Unpacked a RAR archive; check the file list in Preview before applying.'] : [];
      return ok({ ok: true, id, warnings: w });
    }
  }
  return err(404, `No mock for ${route}`);
}

// ---------- Fake window host (?mock=1&host=1) ----------
// Stands in for the cyberHost object CyberLoader.exe injects (docs/HOST-API.md), so the
// frameless chrome can be checked in a normal browser. Same API and the same <html> attributes.
if (q.get('host') === '1' && !window.cyberHost) installFakeHost();

function installFakeHost() {
  const h = document.documentElement;
  const listeners = [];
  const state = { maximized: false, focused: document.hasFocus() };
  let frameless = false;
  let toastFn = null;
  import('./ui.js').then((m) => { toastFn = m.toast; });
  const note = (t) => (toastFn ? toastFn(t) : console.info('[fake host]', t));
  const paint = () => {
    h.classList.add('is-host');
    h.toggleAttribute('data-maximized', state.maximized);
    h.toggleAttribute('data-focused', state.focused);
    h.toggleAttribute('data-frameless', frameless);
  };
  const emit = () => {
    paint();
    for (const fn of listeners) { try { fn({ ...state }); } catch (e) { console.error(e); } }
  };
  addEventListener('focus', () => { state.focused = true; emit(); });
  addEventListener('blur', () => { state.focused = false; emit(); });
  window.cyberHost = {
    frameless(on) { frameless = !!on; paint(); },
    minimize() { note('Fake host: minimize'); },
    toggleMaximize() { state.maximized = !state.maximized; emit(); },
    close() { note('Fake host: close'); },
    setBackground(c) { document.body.style.background = String(c); window.__fakeHostBackground = String(c); },
    onState(fn) { listeners.push(fn); try { fn({ ...state }); } catch (e) { console.error(e); } },
  };
  // Like the real host: a press on [data-window-drag] (not on a control) starts a move; a quick
  // second press toggles maximize.
  const NO_DRAG = 'button,input,a,select,textarea,label,[data-no-drag],[role="button"],[contenteditable]';
  let last = 0;
  document.addEventListener('mousedown', (e) => {
    if (e.button !== 0 || !(e.target instanceof Element)) return;
    if (!e.target.closest('[data-window-drag]') || e.target.closest(NO_DRAG)) return;
    e.preventDefault();
    const now = Date.now();
    if (now - last < 450) { last = 0; window.cyberHost.toggleMaximize(); } else last = now;
  }, true);
  paint();
}
