# Save transfer (optional add-on)

"Change or move a character…" in the "..." menu copies parts of one Cyberpunk 2077 save onto another: gender and voice, the look (face, hair,
body shape, tattoos), clothes, Equipment-EX outfits and guns. It always makes a **new** save; the two saves it reads are never changed.

The menu entry only appears when the add-on is installed. A normal install does not have it.

## What it does and does not do
- Reads two saves from the game's saves folder (`%USERPROFILE%\Saved Games\CD Projekt Red\Cyberpunk 2077`; override with the
  `saves` key in `cyberloader.json` or `MODMAN_SAVES`).
- **Gender and voice:** needs only the save you put it on (no source save). Switches the body to the default look for that gender (the editor's own method, made for patch 2.5) and sets the voice.
- **Look:** copies the whole appearance from the source save. The target keeps its own voice.
- **Clothes / guns:** copies every item the source has and the target lacks (compared by item and count), with its stats and attached
  parts, and fresh unique ids. Mod clothes the add-on cannot name are included.
- **Outfits:** copies Equipment-EX outfits and re-points every piece at the matching item copy in the target. The target must have run
  at least once with Equipment-EX (it needs the mod's saved data). Outfits whose name already exists are skipped.
- **Tidy up:** removes surplus copies of identical clothes (any clothing kind held more than 4 times is cut down to 2). Anything equipped
  and anything an Equipment-EX outfit points at is kept first. Needs no source save. Made for piles that some mods can create (for example the
  default underwear), which add weight and can stop V sprinting.
- **Remove mod items:** for a copy you want to play without mods. Removes every item the plain game does not know (mod clothes and similar) from
  every container, unequips anything worn from that set, and clears the saved Equipment-EX outfits. Scripts and settings that other mods keep in
  the save are left alone. Needs no source save. The old save is never changed.
  Tested once (patch 2.5, one save, loading and looking at the inventory): a save that still holds mod items loads in the plain game and the mod clothes
  are simply not shown; nothing breaks. Saving was tested too: a save the plain game wrote from such a copy (autosaves, same playthrough) held 0 mod items and 0 Equipment-EX outfits, down from 45 and 8, with guns, money and the rest unchanged. So the plain game drops them for good when it saves; removing them first gives the same result on purpose, and the original save is never changed.
- **Money:** sets the Eurodollars to an exact amount (0 to 2,000,000,000). Needs no source save. Use it to take money away or add some;
  do not use a console command with a negative number (the amount is stored as a positive number and could wrap around to billions).
- It does not equip anything, copy money, quests, stats or the vanilla wardrobe, and it cannot change the playthrough of a save.

## How long it takes
Reading one save with the add-on takes about 15 seconds on a normal PC (the save reader is slow, and it cannot read two saves at the same
time: it crashes). A transfer reads both saves, makes the change, saves it and reads the result back to check it: about 35 to 40 seconds.
`inspect` (what a save holds) takes about 15 seconds and the engine remembers the answer until the save file changes. The screen never
starts the add-on by itself while you tick boxes; the exact "what would be added" numbers are a button. `SAVETOOL_TIMING=1` makes the
add-on print how long each step took to stderr.

## Safety
1. Refused while the game is running or an apply is running.
2. Both saves are copied to `<data>\save-backups\<time>\` first.
3. The add-on writes into a temporary folder and reads the result back; only then is it put into the saves folder as
   `ManualSave-<highest number + 1>`. An existing folder is never reused.
4. Test it on a copy first (`MODMAN_SAVES` points the engine at any folder).

## Installing the add-on
It is built on **CP2077SaveEditor / CyberCAT-SimpleGUI** (MIT, Deweh and contributors, https://github.com/Deweh/CyberCAT-SimpleGUI),
which it loads as a library. Nothing from it is shipped in this repo.
1. Download the editor's zip from its GitHub releases page and unzip it somewhere (checked with v0.30.1).
2. Install the .NET 10 SDK (to build) and the .NET 10 Desktop Runtime (to run).
3. Run `powershell -File tools\build-savetool.ps1 -EditorDir "<unzipped editor folder>" -Data "<your Cyber Loader data folder>"`.
   It builds `addons\savetool` and copies the result plus the editor files into `<data>\addons\savetool`.
4. Restart Cyber Loader. "Change or move a character…" appears in the "..." menu.

The add-on is a console program that prints one JSON line per call: `savetool inspect <save>` and
`savetool transfer [--source S] --target T --out DIR [--gender keep|female|male] [--look] [--clothes] [--outfits] [--guns] [--dry-run]`.
The engine (`engine/modman/savetransfer.py`) is the only thing that calls it. Endpoints: see `docs/API.md`.
