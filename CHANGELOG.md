# Changelog

Every release gets a section here BEFORE it is installed (`tools/release.py` refuses without one). Newest first. Versions follow `MAJOR.MINOR.PATCH`: PATCH = bug fix, MINOR = new feature, MAJOR = changes that need your data migrated.

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
