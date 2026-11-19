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
// Sample versions and upload dates (the real engine reads them from a Nexus download's folder name), and one pair that
// looks like two versions of the same mod: turning both on shows the "Another version is on too" warning.
const VERSIONS = {
  red4ext: ['1.31.1', '2026-10-02'], archivexl: ['1.28.8', '2026-10-20'], tweakxl: ['1.12.2', '2026-09-14'], redscript: ['0.5.27', '2026-08-01'],
  codeware: ['1.19.0', '2026-10-11'], inputloader: ['0.2.7', '2026-11-02'], hdjackets: ['2.1', '2024-03-18'], nointro: ['1.0', '2022-02-15'],
};
if (mods.length) mods.push({ id: 'inputloader-old', name: 'Key Binding Loader', group: 'Framework', files: 3, framework: true, requires: ['red4ext'] });
VERSIONS['inputloader-old'] = ['0.2.6', '2026-10-26'];
for (const m of mods) {
  const v = VERSIONS[m.id];
  m.version = v ? v[0] : null;
  m.uploaded = v ? v[1] : null;
  m.nexusId = v ? 4000 + (m.id.length * 37) : null;
  m.otherVersions = m.id === 'inputloader' ? ['inputloader-old'] : m.id === 'inputloader-old' ? ['inputloader'] : [];
}
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
let deployed = q.get('gfFree') === '1' ? new Set() : new Set(enabled);   // ?gfFree=1: nothing placed, so the game folder can be changed
let running = q.get('running') === '1';
let job = null;
let settings = { theme: 'dark', accent: '#FF375F' };
try { Object.assign(settings, JSON.parse(localStorage.getItem('cmm.settings') || '{}')); } catch { /* ignore */ }
const imports = new Map();

// Sample game folders for the "Game folder" sheet (invented paths). Anything else that looks like a path is "not the game".
const GAME_DIRS = {
  'c:\\program files (x86)\\steam\\steamapps\\common\\cyberpunk 2077': { version: '2.5', updated: '2026-10-21' },
  'e:\\gog games\\cyberpunk 2077': { version: '2.3', updated: '2026-06-02' },
  'c:\\games\\cyberpunk 2077 (copy)': { updated: '2026-03-14' },
};
let gameDir = 'C:\\Program Files (x86)\\Steam\\steamapps\\common\\Cyberpunk 2077';
const gameKey = (p) => p.replace(/\//g, '\\').replace(/\\+$/, '').toLowerCase();
function checkGame(raw) {
  let text = String(raw || '').trim().replace(/^"|"$/g, '').trim();
  const out = { path: text, isFolder: false, found: false, same: false };
  if (!text) return { ...out, message: 'Paste the full path of your Cyberpunk 2077 folder.' };
  if (!/^[a-z]:[\\/]/i.test(text)) return { ...out, message: 'Use the full path, starting with the drive letter, like C:\\Games\\Cyberpunk 2077.' };
  text = text.replace(/\\bin\\x64\\cyberpunk2077\.exe$/i, '').replace(/\\bin(\\x64)?$/i, '');
  out.path = text;
  if (/missing|nope/i.test(text)) return { ...out, message: 'That folder doesn’t exist.' };
  const info = GAME_DIRS[gameKey(text)];
  out.isFolder = true;
  if (!info) return { ...out, message: 'This doesn’t look like Cyberpunk 2077: bin\\x64\\Cyberpunk2077.exe isn’t in it. Choose the main game folder, the one that contains the bin folder.' };
  return { ...out, found: true, same: gameKey(text) === gameKey(gameDir), message: 'Cyberpunk 2077 found.', ...info };
}
function gameFolder() {
  const reason = running ? 'The game is running. Close it, then change the folder.'
    : job && !job.final ? 'An apply is running. Wait for it to finish, then change the folder.'
    : deployed.size ? 'Some mods are still placed in the current game folder. Turn everything off and apply first, then change the folder.' : null;
  const info = GAME_DIRS[gameKey(gameDir)] || {};
  return { path: gameDir, found: true, ...info, deployedCount: [...deployed].reduce((a, id) => a + (byId.get(id)?.files || 0), 0), canChange: !reason, reason };
}
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
  { id: 's1', at: '2026-11-15 22:10:03', profile: 'Core + Vehicles + extras', auto: true, pinned: false, name: null,
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
  return { id: m.id, name: m.name, group: m.group, files: m.files, enabled: on, pending: on === deployed.has(m.id) ? null : on ? 'on' : 'off', framework: m.framework, requires: [...m.requires], autoRequires: m.autoRequires.map((n) => ({ name: n.name, ids: [...n.ids] })), conflicts: conflictsOf(m.id), nexusId: m.nexusId ?? null, version: m.version ?? null, uploaded: m.uploaded ?? null, otherVersions: [...(m.otherVersions || [])] };
}

function state() {
  const v = mods.map(view);
  return {
    game: { running, found: true, ...(GAME_DIRS[gameKey(gameDir)] || {}) },
    profile: current,
    profiles: [...profiles.keys()],
    profileDirty: current ? !sameSet(enabled, profiles.get(current)) : false,
    deployedCount: [...deployed].reduce((a, id) => a + (byId.get(id)?.files || 0), 0),
    pendingCount: { on: v.filter((m) => m.pending === 'on').length, off: v.filter((m) => m.pending === 'off').length },
    saveTransfer: !q.has('nosave'),
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
    for (const o of m.otherVersions || []) if (enabled.has(o) && m.id < o) w.push(`“${m.name}” and “${nameOf(o)}” look like two versions of the same mod. Turn one of them off`);
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
// Save transfer (invented saves; ?nosave=1 hides the feature like an install without the add-on)
const SAVES = [
  { id: 'ManualSave-14', kind: 'manual', label: 'Manual save 14', bodyGender: 'Female', voice: 'Female', level: 15, hours: 2.2, lifePath: 'StreetKid', modded: true, playthrough: 'b', savedAt: 1794000000, patch: '2.5', hasPicture: true, counts: { clothes: 41, modItems: 26, guns: 15, outfits: 4, money: 49066 } },
  { id: 'AutoSave-9', kind: 'auto', label: 'Autosave 9', bodyGender: 'Female', voice: 'Female', level: 15, hours: 1.9, lifePath: 'StreetKid', modded: true, playthrough: 'b', savedAt: 1793990000, patch: '2.5', hasPicture: true, counts: { clothes: 41, modItems: 26, guns: 14, outfits: 4 } },
  { id: 'ManualSave-6', kind: 'manual', label: 'Manual save 6', bodyGender: 'Male', voice: 'Male', level: 15, hours: 8.0, lifePath: 'Nomad', modded: false, playthrough: 'a', savedAt: 1793900000, patch: '2.5', hasPicture: true, counts: { clothes: 41, modItems: 0, guns: 32, outfits: 0 } },
  { id: 'AutoSave-3', kind: 'auto', label: 'Autosave 3', bodyGender: 'Male', voice: 'Male', level: 12, hours: 6.4, lifePath: 'Nomad', modded: false, playthrough: 'a', savedAt: 1793800000, patch: '2.5', hasPicture: true, counts: { clothes: 38, modItems: 0, guns: 28, outfits: 0 } },
];
const PT_NAMES = {};
function playthroughs() {
  const groups = new Map();
  for (const x of [...SAVES].sort((m, n) => n.savedAt - m.savedAt)) { if (!groups.has(x.playthrough)) groups.set(x.playthrough, []); groups.get(x.playthrough).push(x); }
  return [...groups].map(([id, items]) => ({
    id, name: PT_NAMES[id] || null, count: items.length, first: Math.min(...items.map((x) => x.savedAt)), last: Math.max(...items.map((x) => x.savedAt)),
    bodies: [...new Set(items.map((x) => x.bodyGender))].sort(), level: items[0].level, hours: Math.max(...items.map((x) => x.hours)), saves: items.map((x) => x.id),
  })).sort((m, n) => n.last - m.last);
}
function xferReport(b) {
  const from = SAVES.find((x) => x.id === b.source) || { counts: { clothes: 0, modItems: 0, guns: 0, outfits: 0 } }, to = SAVES.find((x) => x.id === b.target);
  const r = {};
  if (b.look) r.look = true;
  if (b.gender && b.gender !== 'keep') r.gender = b.gender;
  if (b.clothes) r.clothesAdded = Math.max(0, from.counts.clothes + from.counts.modItems - to.counts.clothes);
  if (b.guns) r.gunsAdded = Math.max(0, from.counts.guns - to.counts.guns);
  if (b.money !== undefined && b.money !== null && b.money !== '') { r.moneyBefore = to.counts.money ?? 0; r.moneyAfter = Number(b.money); }
  if (b.stripMods) { r.modItemsRemoved = to.counts.modItems; r.modItemKinds = Math.round(to.counts.modItems * 0.85); r.modSlotsUnequipped = 0; r.outfitsCleared = to.counts.outfits; }
  if (b.tidy) { r.tidyRemoved = to.counts.clothes > 50 ? 72 : 0; r.tidyKinds = r.tidyRemoved ? { 'V’s street outfit': 72 } : {}; }
  if (b.outfits) {
    r.outfitsAdded = to.counts.outfits || to.modded ? from.counts.outfits : 0;
    r.outfitSetsSkipped = 0; r.outfitPartsSkipped = 0;
    if (!to.modded) r.outfitsNote = 'The target save has no Equipment-EX outfit data yet. Load it once in the game with your mods on, save, then transfer the outfits.';
  }
  return r;
}
function xferCheck(b) {
  const bad = (m) => err(400, m);
  const copies = b.look || b.clothes || b.outfits || b.guns;
  if (!(copies || b.tidy || b.stripMods || (b.money !== undefined && b.money !== null && b.money !== '') || (b.gender && b.gender !== 'keep'))) return bad('Tick at least one thing to transfer.');
  if ((copies && !SAVES.some((x) => x.id === b.source)) || !SAVES.some((x) => x.id === b.target)) return bad('Pick a save from the list.');
  if (copies && b.source === b.target) return bad('The two saves have to be different.');
  return null;
}

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

    case 'POST /api/snapshots/restore': {
      const s = SNAPS.find((x) => x.id === body.id);
      if (!s) return err(404, 'that snapshot no longer exists');
      const keep = s.mods.filter((m) => byId.has(m.id));
      enabled = new Set(keep.map((m) => m.id));
      return ok({ ...state(), restored: { count: keep.length, missing: s.mods.filter((m) => !byId.has(m.id)).map((m) => ({ name: m.name, version: m.version, date: m.date, nexusId: m.nexusId })), changed: s.mods.filter((m) => m.changed).length } });
    }

    case 'POST /api/mod/group': {
      const m = byId.get(body.id);
      if (!m) return err(404, 'That mod is no longer in the library.');
      if (!['Framework', 'Body', 'Characters', 'Clothing', 'Gameplay', 'Content', 'Other'].includes(body.group)) return err(400, 'Pick one of the categories.');
      m.group = body.group;
      m.framework = body.group === 'Framework';
      return ok({ ok: true, mod: view(m) });
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


    case 'GET /api/savetransfer':
      return ok({ available: true, reason: null, savesDir: '(sample saves)', gameRunning: running, playthroughs: playthroughs(), saves: [...SAVES].sort((m, n) => n.savedAt - m.savedAt).map(({ counts, ...x }) => x) });
    case 'POST /api/savetransfer/inspect': {
      const x = SAVES.find((v) => v.id === body.save);
      return x ? ok({ id: x.id, bodyGender: x.bodyGender, voice: x.voice, counts: x.counts }) : err(404, 'Can’t find that save.');
    }
    case 'POST /api/savetransfer/name': {
      if (!playthroughs().some((g) => g.id === body.playthrough)) return err(404, 'Can’t find that playthrough.');
      const text = String(body.name || '').split(/\s+/).join(' ').trim().slice(0, 60);
      if (text) PT_NAMES[body.playthrough] = text; else delete PT_NAMES[body.playthrough];
      return ok({ ok: true, id: body.playthrough, name: text || null });
    }
    case 'POST /api/savetransfer/preview': {
      await new Promise((r) => setTimeout(r, +q.get('xferDelay') || 0));   // ?xferDelay=8000 to see the waiting state
      const bad = xferCheck(body);
      return bad || ok({ ok: true, report: xferReport(body) });
    }
    case 'POST /api/savetransfer/run': {
      await new Promise((r) => setTimeout(r, +q.get('xferDelay') || 0));
      const bad = xferCheck(body);
      if (bad) return bad;
      if (running) return err(409, 'The game is running. Close it first (a running game can overwrite saves).');
      const slot = `ManualSave-${Math.max(...SAVES.map((x) => +(/(\d+)$/.exec(x.id)?.[1] || 0))) + 1}`;
      const report = xferReport(body);
      const to = SAVES.find((x) => x.id === body.target);
      SAVES.unshift({ ...to, id: slot, kind: 'manual', label: `Manual save ${slot.split('-')[1]}`, savedAt: Math.floor(Date.now() / 1000), bodyGender: body.gender === 'male' ? 'Male' : body.gender === 'female' ? 'Female' : to.bodyGender, counts: { ...to.counts } });
      return ok({ ok: true, slot, report, result: {}, backup: '(sample backup folder)', source: body.source || null, target: body.target, playthrough: to.playthrough });
    }

    case 'GET /api/game-folder':
      return ok(gameFolder());
    case 'POST /api/game-folder/check':
      return ok(checkGame(body.path));
    case 'POST /api/game-folder': {
      const c = checkGame(body.path);
      if (!c.found) return err(400, c.message);
      const g = gameFolder();
      if (!g.canChange) return err(job && !job.final ? 423 : 409, g.reason);
      const changed = !c.same;
      if (changed) gameDir = c.path;
      return ok({ ok: true, changed, ...gameFolder() });
    }

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
    // Stands in for the native folder dialog: picks a sample folder (?pickCancel=1: the user cancels).
    pickFolder() { return new Promise((r) => setTimeout(() => r(q.get('pickCancel') === '1' ? null : 'E:\\GOG Games\\Cyberpunk 2077'), 400)); },
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
