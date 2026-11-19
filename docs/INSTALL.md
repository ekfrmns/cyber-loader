# Installing CyberLoader

## For people using it
1. Get `CyberLoader-Setup-<version>.exe` (about 14 MB). Windows 10/11 with the Microsoft WebView2 Runtime (it ships with Windows 11 and Edge).
2. Run it. No administrator rights are needed. The wizard asks for:
   - **Install folder** (default: your local app data).
   - **Cyberpunk 2077 folder**: found automatically on Steam, GOG, Epic or common folders; browse if it isn't.
   - **Where your mods live**: the library can reach tens of GB. Keep it on the **same drive as the game**: CyberLoader then links mod files into the game (instant, no extra space) instead of copying them.
   - **Options**: *Install 7-Zip* (recommended; needed for `.7z` and `.rar` mods, plain `.zip` works without it), a Start menu shortcut ("Cyber Loader", on by default) and a Desktop shortcut (off by default; tick it if you want one).
3. Open **Cyber Loader**, drag a mod archive or folder onto the window to add it, turn mods on or off, then press Apply (the game must be closed).

Updating: run a newer Setup over the old install, pointing at the same folder. Your library, profiles and trash are kept.
Uninstall: Windows Settings > Apps > CyberLoader (or `Uninstall.exe` in the install folder). Your library is kept unless you tick the box to delete it.

Silent install: `Setup.exe /S /D=<install dir> /GAME=<Cyberpunk 2077 dir> /DATA=<data dir> [/7ZIP=0] [/DESKTOP] [/NOSTART] [/LAUNCH]`; silent uninstall: `Uninstall.exe /S [/DELETEDATA]`.

## For the maintainer (building the installer)
Needs on the build machine: Python 3.13, the C# compiler that ships with Windows, and 7-Zip (its files are copied into the installer as the optional component).

    python tools\package.py            full build from main: clean tree, tests, CHANGELOG section for the version; tags v<version>
    python tools\package.py --test     quick build from the working tree (no checks, no tag)

Output: one folder per version, `dist\<version>\`, holding `CyberLoader-Setup-<version>.exe`, its `.sha256` file and `RELEASE-NOTES.md` (what changed since the previous version, from CHANGELOG.md). Quick `--test` builds go to `dist\<version>-test\` (never share those). The installer contains the launcher, a private Python runtime, the committed engine and UI for the version, licences (`installer\THIRD_PARTY.txt`) and the optional 7-Zip. Nothing about the build machine is included.
Where the app reads its settings: `<install dir>\cyberloader.json` (`game`, `data`); the engine also honours `MODMAN_GAME` / `MODMAN_DATA` and `CYBERLOADER_CONFIG` for development and tests.
