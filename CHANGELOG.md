# Changelog

Every release gets a section here BEFORE it is installed (`tools/release.py` refuses without one). Newest first. Versions follow `MAJOR.MINOR.PATCH`: PATCH = bug fix, MINOR = new feature, MAJOR = a redesign or changes that need your data migrated.

## 2.0.0 - 2026-11-19
A new look and layout for the whole app. Nothing about your data changes: your library, profiles, saves and settings carry over as they are, and the engine and its API are unchanged.
- **Side bar layout.** Library, Profiles, Runs, Characters, History and trash, and Settings are now pages you switch between from a side bar. The "..." menu, the "+" button and the old pop-up windows (Appearance, Game folder, History, Trash and the character tool) are gone; each is a page now. Your active profile (with a Switch button) sits at the top of the side bar and the game's state at the bottom. Below about 1100 px wide the side bar shrinks to icons, and below 760 px the Library's category list hides.
- **One layout rule.** Profiles, Runs, Characters and History all work the same way: pick on the left, see and change it on the right. The Library's category list on the left jumps to that category in the long list on the right. A slim strip under the top bar names the page and gives one line of help, and the search sits in the middle of the top bar on every page (typing on another page takes you to the Library).
- **Characters has its own page.** What used to be "Change or move a character" in the menu is now a page of its own in the side bar (it still only appears when the optional add-on is installed). The run and save choice is two steps ("Which run?", then "Which save?"), nothing jumps when you switch runs, and the save list shows the name large with the details small.
- **Themed controls.** The save lists use a themed drop-down instead of the system's plain grey list (arrow keys, type to jump, Escape to close). Checkboxes and radio buttons are rounded and take your accent colour. Buttons have one consistent look, with a soft red for delete actions, and the check mark on the "Applied" badge is centred.
- **Colour picker and accent.** Pink is first in the accent list. A custom colour opens a built-in rounded picker (square, hue slider and hex field, keyboard friendly) instead of the system colour dialog.
- **The logo follows your accent.** The logo in the top left is drawn from your accent colour and follows the colour picker as you drag. The pink is a little softer than before and the middle bar is a touch lighter. The app, taskbar and shortcut icons are unchanged.
- **The game's state, in plain sight.** The text above Settings is no longer in a box: it shows the game's name, a coloured dot (closed, running, not connected) and its version.
- **Setup makes no Desktop shortcut by default.** Before, every install put one back on the Desktop. Now only `/DESKTOP` (or the wizard's checkbox, which starts unticked) makes one. `/NODESKTOP` still works and does nothing new. The Start menu entry is unchanged.
- Window buttons sit with equal gaps and a soft red close, and the side bar's tooltips wait half a second.
- API: unchanged.

## 1.7.0 - 2026-11-18
A new default look and icon, plus two new options in "Change or move a character".
- **New default look.** A fresh install now starts in the dark theme with a pink-red accent instead of blue. Anything you already chose in the app is kept; this only changes what a new install starts with. The README screenshots show it.
- **New icon.** A dark, red-tinted square with red bars, used for the app, the taskbar, shortcuts, the installer and the browser tab. Windows remembers old icons, so an existing shortcut may keep the old one until it is pinned again or Windows refreshes its icon cache.
- **Set money** (in "Change or move a character..."): type an exact amount of Eurodollars (0 to 2,000,000,000) and it makes a new save with that amount. It needs no second save. Use it instead of a console command with a negative number, which can wrap around to billions.
- **Remove mod items** (same screen): makes a copy that is safe to play without mods. It removes every item the plain game does not know (mod clothes and the like) and clears saved Equipment-EX outfits; scripts and settings that mods keep in the save are left alone. The old save is never changed. Tested: a save the plain game wrote from a copy that still held mod items had none left, so the plain game drops them when it saves; this option does the same on purpose.
- The performance logger script (`tools/perf-watch.ps1`) also records read speed per drive and for the game.
- API (additive, see `docs/API.md`): the save-transfer options accept `money` and `stripMods`. Nothing was removed or changed.

## 1.6.0 - 2026-11-17
Change or move a character between Cyberpunk 2077 saves (optional add-on).
- **Change or move a character…** ("..." menu, only shown when the add-on is installed). Pick a save to copy from and a save to put it on, then choose what moves: gender and voice, the look (face, hair, body shape, tattoos), clothes, Equipment-EX outfits and guns. Or just change the gender, which needs no save to copy from (this is also how to turn a character back).
- **Saves are shown by playthrough.** The game files saves under a playthrough. Each one is a card with its save count, which bodies it holds, level, hours and when it was last played, with a drop-down of its saves (newest first, the latest marked). Saves are named plainly ("Manual save 34", "Autosave 1"). The pencil on a card lets you give a playthrough a name of your own (kept in `<data>\save-names.json`).
- **It always makes a new save.** Your saves are never changed: the result goes into the game's saves folder as the next free `ManualSave-<number>`, after the saves involved were copied to `<data>\save-backups\<time>\`. Refused while the game or an apply is running. The result is read back and checked before it is put in place. The new save stays in the playthrough of the save it was put on.
- **Short, visible waits.** The summary under the options is instant. The exact numbers ("get 26 pieces of clothing") come from a "Check what it would add" button (about 30 seconds). Making the save takes about 25 to 40 seconds and shows a spinner and a seconds counter. What a save contains is remembered until the save file changes.
- **Tidy up** option: cuts piles of identical clothes (more than 4 of a kind) down to 2 of each, keeping anything you wear or use in an outfit. Some mods can create such piles, which add weight.
- **The add-on** (`addons\savetool`, installed with `tools\build-savetool.ps1`) is built on the MIT-licensed CP2077SaveEditor / CyberCAT-SimpleGUI by Deweh and contributors, which you download yourself. It needs the .NET 10 Desktop Runtime. A normal install does not have it and does not show the menu entry. Details: `docs\SAVE-TRANSFER.md`.
- Outfits need the target save to have run at least once with Equipment-EX; if not, the summary says so instead of failing. Reading a save takes the add-on about 15 seconds and two cannot be read at once, so a transfer reads them one after the other.
- API (additive, see `docs/API.md`): `GET /api/savetransfer` (with `playthroughs`, and a `kind` and `label` per save), `POST /api/savetransfer/inspect`, `/name`, `/preview` and `/run`; `/api/state` has `saveTransfer`. Nothing was removed or changed.

## 1.5.0 - 2026-11-17
A Game folder screen, so you can change which Cyberpunk folder the app uses without running Setup again.
- **Game folder screen** ("..." menu). Shows the folder in use and its game version. Type or paste a path (the game's folder or its `Cyberpunk2077.exe` both work) and it checks that it really is Cyberpunk 2077 before saving. **Browse…** opens a folder dialog (needs this version's window host).
- **Safe by design.** The app refuses to change the folder while any mod is placed in the old one, while the game is running, or while an Apply is running, because switching with mods placed would lose track of them. Turn everything off and Apply first, then switch. Nothing is moved, copied or deleted in either game folder when you switch. A folder given on the command line or by environment variable stays locked and the screen says so.
- **Setup keeps your game folder.** Installing a new version over an old one now keeps the game folder (and data folder) already in `cyberloader.json` instead of detecting it again.
- Folder paths with accents or other non-English letters are saved as the real letters in `cyberloader.json` (not as escape codes), so Setup can read them back.
- API (additive, see `docs/API.md`): `GET/POST /api/game-folder` and `POST /api/game-folder/check`. Window host: `cyberHost.pickFolder()` (see `docs/HOST-API.md`). Nothing was removed or changed.

## 1.4.0 - 2026-11-17
Version and upload date on every mod, imports that keep their name, and a warning when two versions of one mod are on.
- **Version and upload date.** Each mod's row now shows its version and the month it was uploaded, like "6 files · v1.28.8 · Oct 2026", when its library folder name has them (Nexus downloads do). Hover the month for the full date. The page subtitle ends with your game's version ("Game 2.5"), and its tooltip gives the date of the game's last update. The older Nexus naming style writes versions as "2-0-1"; those are shown as "2.0.1".
- **Imports keep the file's name.** A mod you drag into the window, or import any other way, now keeps its original file name inside the library, so its Nexus number, version and date are not lost (they used to be cleaned away, so Setup history could not name the old version of those mods). The name you see is still cleaned. Importing the same file twice adds " (2)".
- **Two versions of one mod.** If the library holds two versions of the same Nexus mod (same Nexus number and the same name apart from the version) and you turn both on, the row warns "Another version is on too" and Review changes lists it once. Two different files of one Nexus page, like a body and a head, or four tattoo colours, are not treated as versions of each other.
- API (additive, see `docs/API.md`): each mod has `nexusId`, `version`, `uploaded` and `otherVersions`; `game` has `version` and `updated`. Nothing was removed or changed.

## 1.3.0 - 2026-11-17
Move a mod to another category.
- Right-click a mod, **"Move to category…"**: pick Framework, Body, Characters, Clothing, Gameplay, Content or Other. The choice is saved in the mod's own `.mod.json`, so the name-based guess never overrides it again. Before this, a mod that matched no keyword stayed in Other with no way to move it.
- The guess knows more names: tattoo, teeth, tooth, braces, grill and skin (as a whole word) now go to Body, and "UV Framework" goes to Framework.
- API (additive, see `docs/API.md`): `POST /api/mod/group`. Nothing was removed or changed.

## 1.2.1 - 2026-11-17
Setup history is simpler.
- Removed the "Keep current setup" and "Keep this one" buttons. Saving a named list of mods is what profiles are for; setup history stays automatic, with just Details and Restore.
- Setup history now keeps the newest 200 setups instead of 100 (older ones are still moved aside, never erased).
- The API for naming and keeping a setup is still there (`/api/snapshots/save` and `/pin`), the app just no longer shows it.

## 1.2.0 - 2026-11-17
Setup history, and a picker for what a mod needs.
- **Setup history** ("..." menu, "Setup history…"). A snapshot is saved after every successful Apply: which mods were on (in order), the profile, and for each mod its name, version, upload date and Nexus number as far as its library folder name says. It holds no mod files. Restore puts that mod list back on screen; nothing in the game changes until you review and apply, so every safety rule still applies.
- It names the old version of a mod after an update: "this setup used version 1.0.0, you have version 1.1.0 now", with a "Copy Nexus link" button so you can download the old version yourself. The app never contacts Nexus. Mods deleted since are skipped and named, and flagged when they are in Deleted mods. A mod whose files changed inside the same folder is flagged "changed since" (no old version is known for those).
- "Keep current setup…" saves a named setup that is never cleaned up; any setup can be kept, renamed or un-kept. Automatic ones past the newest 100 are moved to `snapshots\old` (nothing is erased). Setups live in `<data>\snapshots`.
- **What it needs:** right-click a mod, "What it needs…", and tick the mods it can't work without. You get the same "Needs …" warning as the automatic ones. It is saved in the mod's own `.mod.json`; nothing in the game folder changes.
- API (additive, see `docs/API.md`): `GET /api/snapshots`, `GET /api/snapshots/<id>`, `POST /api/snapshots/save|restore|pin`, `POST /api/mod/requires`. Nothing was removed or changed. No data migration: the new `snapshots` folder is created on first start.

## 1.1.0 - 2026-11-17
Mods now warn you when the core mod they depend on is off.
- The app looks at the files inside each mod and guesses which core mod it needs: Redscript, ArchiveXL, TweakXL, RED4ext, Cyber Engine Tweaks, Input Loader or Audioware. Turn a mod on while its core mod is off and the row says "Needs ...". Turn a core mod off while something that is on needs it and that row says "Needed by ...". The Review changes window lists the same warnings.
- It finds the core mod in your library by the files it ships, not by its name, and any matching one counts. If none is in your library the warning says "not in library".
- It is a guess from file types only, so it only covers those seven. It never blocks Apply. A "needs" entry you set yourself still works and replaces the guess for the same core mod.
- API: each mod has a new `autoRequires` list (see `docs/API.md`). Nothing was removed or changed.
- The sample data inside the app has generic names only (this ships the earlier fix that 1.0.1 missed).

## 1.0.1 - 2026-11-17
First public release on GitHub. Same app as 1.0.0, tidied for sharing.
- Sample names in the built-in demo data and in the group-guessing keywords are generic now, with no one's personal mod or profile names.
- Importing a Vortex deployment names its profile "Vortex import".
- Development scripts no longer assume a particular drive or folder (`tools/dev-host.ps1 -Install <dir>`).
- Removed the one-off repair action and its API call (`/api/restore-baseline`), which only made sense for one particular mod setup. The app never called it.
- Adds `tools/publish.py` for publishing a release to the public repo.

## 1.0.0 - 2026-11-17
First version anyone can install.
- Installer wizard (`CyberLoader-Setup-1.0.0.exe`): choose where to install, which Cyberpunk 2077 folder to use (found automatically on Steam, GOG, Epic or common folders), and where your mod library lives (it warns when that is on a different drive than the game, because mods can then only be copied, not linked). Optional private 7-Zip (recommended: needed for .7z and .rar mods), Desktop and Start menu shortcuts named "Cyber Loader", an uninstaller, and a silent mode (`/S /D= /GAME= /DATA=`).
- Nothing about one computer is built in any more: the game and data folders come from the install's `cyberloader.json`. A first run starts with a single "Empty" profile (the plain game); apply and restore explain clearly if the game folder can't be found.
- Plain `.zip` mods import without any extra software (with a zip-slip guard); `.7z` and `.rar` use the optional 7-Zip.
- Icon bars nudged right so the icon looks centred.
- The author's one-off setup command moved out of the shipped command line (`tools/personal`, never packaged).
- Installing over an older CyberLoader updates it and keeps the library, profiles and trash.
## 0.8.1 - 2026-11-17
- The search box now fills exactly the room between the profile picker and the status chip: it always starts 8 px after the picker, so it no longer jumps when you switch between profiles with short and long names (tested with a short, a medium and a very long name, and at 700 px wide).
- Darker app icon (near-black graphite to dark grey). The window now loads its icon from inside the exe instead of through Windows' icon cache, which is what kept the old blue icon in the taskbar.
## 0.8.0 - 2026-11-16
- Profiles moved out of the "..." menu. There is now a "+" button (tooltip "New profile") to the left of the profile picker, and every profile in the picker has a pencil (rename) and a trash (delete) icon with tooltips. When the selected profile has unsaved edits, "Save changes to ..." appears at the bottom of the picker. The picker is wider.
- The "..." menu now only has "Deleted mods" and "Appearance".
- The one-off repair button was taken out of the menu.
- New grey app icon to match the app's colour scheme (the window and shortcut pick it up after the launcher is rebuilt).
- Tools: `tools/dev-host.ps1` can run beside the normal app and open a debug port.
## 0.7.0 - 2026-11-16
- Tidy: everything the app keeps now lives under its own program folder, the `data` folder inside its install folder (library, profiles, state, logs, trash, downloads), instead of a separate "Cyberpunk Mod Manager" folder at the root of D:. The first time you open this version it moves the old folder there by itself (an instant rename; your mods, profiles and the links into the game are unaffected). If something is holding the old folder open it keeps using it and tries again next time.
- The developer test window now builds its throwaway sandbox inside `data\tmp\dev-sandbox` instead of the root of D:.
## 0.6.1 - 2026-11-16
- Look: each group (Framework, Body, ...) is now a full card instead of a bare text row. It has an icon tile, the group name with "N of M on" underneath, a small meter showing how much of the group is on, and the chevron on the right; its mods sit inside the same card when it is open. Works in light and dark, and the meter follows your toggles.
## 0.6.0 - 2026-11-16
- New: delete mods. Right-click a mod (or press Delete while it is selected) and choose "Move to trash". Deleted mods are kept in an in-app trash (menu "Deleted mods...") where you can restore them or delete them forever, one by one or with "Empty trash". Nothing is erased from disk until you empty the trash. A mod that is in the game right now cannot be deleted: turn it off and apply first. Profiles keep a deleted mod's entry, so restoring it puts it back where it was.
- Dev: a second copy of the window can run beside the real app (`CYBERLOADER_INSTANCE`), used for testing.
## 0.5.0 - 2026-11-16
- Fix: switches no longer lag or "click by themselves". The engine answers a toggle in about 1 ms (was about 340 ms: it launched a Windows process to check the game on every call), and the list now updates the changed rows in place instead of rebuilding all of them, so the switch animates and fast clicks are never lost. Toggles are also sent in order and stale replies are ignored. Tested with 19 rapid clicks through the real window.
- New: rename a profile (menu, "Rename ..."); works for any profile, keeps its place in the list.
- Look: more space above the top bar controls, a much rounder window (about 18 px, square when maximized), the title bar icon centred a few pixels lower, window title "CyberLoader".
- Shortcuts are now called "CyberLoader" (Desktop and Start menu).
- Tools: `tools/cdp.py` drives the real window through its debug port for tests (no real mouse).
## 0.4.0 - 2026-11-16
- New look for the window: the app now draws its own top bar (no Windows title bar). The bar blends into the page, is draggable, and holds the profile picker, search, game status and menu, with minimize / maximize / close buttons in the top-right corner (Windows 11 style, red close on hover, dimmed when the window is not active).
- The hard dark line under the profile picker is gone: the top bar has no background at the top of the page and only fades in softly when the list scrolls under it.
- New thin, rounded scrollbar that matches the theme, replacing the bright default one.
- Keyboard: PageUp / PageDown / Home / End scroll the page when nothing is focused; Alt+Space still opens the window menu.
- At 700 px wide the game status shrinks to its dot so search keeps its room; fixed garbled text ("Checking...") in the page markup.
- Not included yet: Windows 11 Snap Layouts popup on hovering the maximize button (needs host support; see docs/HOST-API-CHANGES.md).
## 0.3.0 - 2026-11-16
- New window: CyberLoader.exe now owns the app window (Microsoft WebView2, the engine Edge uses) instead of opening an Edge window. It shows the CyberLoader icon in the taskbar and title bar, remembers its size and position, opens only once (opening it again brings the window forward), and quitting the window quits the engine; closing while an apply is running asks first.
- Rounded corners when not maximized; square and flush to the screen edges when maximized. The title bar is dark to match the app.
- Ready for a fully custom top bar: pages can call `cyberHost.frameless(true)` and draw their own bar and window buttons (contract in `docs/HOST-API.md`). Drag, edge resizing and double-click maximize are handled by the host.
- Engine: `serve --host-managed --parent-pid N` for the window host (no window of its own, quits when the host is gone); `--ui` folder option.
## 0.2.0 - 2026-11-16
- New: a one-off repair action for a specific mod set (removed again in 1.0.1).
- Fix: the app window now shows the CyberLoader icon (the UI serves `favicon.ico`).
- Upgrades: opening the app after an upgrade replaces an idle older instance instead of reopening it (never while an apply is running).

## 0.1.0 - 2026-11-16
First installed release.
- Engine: mod library (one folder per mod), profiles, safe deploy by hardlink/copy with plan, apply and removal that only ever touches files it placed; blocks on unknown files; keeps files you modified; moves regenerated Input Loader files aside.
- Takes over a Vortex deployment (hardlink clone of its staging folder, state from its manifest).
- Local API (127.0.0.1 only) and CLI: status, mods, plan, apply, import, adopt-vortex, cleanup-vortex, serve.
- UI: mod list by group, profile picker, search, pending-changes bar, preview sheet with file lists, light/dark/system + accent colour, keyboard navigation, drag-and-drop import (upload), reduced-motion/transparency/contrast support.
- Launcher: `CyberLoader.exe` starts the active version, one instance only, exits after 3 minutes without the window open.
- Known gap: motion not yet reviewed in a real window.
