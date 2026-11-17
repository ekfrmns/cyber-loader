# Opens the UI from this working tree inside the real CyberLoader window (WebView2 host), on a throwaway SANDBOX:
# a fake game folder and a data folder with ~12 real mods hardlinked in. It never touches your real game or real data.
#   powershell -File tools\dev-host.ps1                  open the window (it runs beside a normal CyberLoader: own lock and profile)
#   powershell -File tools\dev-host.ps1 -Debug           also enable F5 reload, F12 dev tools and host.log
#   powershell -File tools\dev-host.ps1 -Fresh           rebuild the sandbox from scratch
#   powershell -File tools\dev-host.ps1 -DebugPort 9333  open a debug port so tools\cdp.py can drive the page (no real mouse)
#   powershell -File tools\dev-host.ps1 -Install <dir>   the installed app to borrow the exe, Python and sample mods from (default: %LOCALAPPDATA%\Programs\CyberLoader)
#   powershell -File tools\dev-host.ps1 -Exe <path>      use another build of CyberLoader.exe (default: the one in the install folder)
# Edit files in ui\, press F5 in the window (needs -Debug) to see the change. Close the window to stop the engine.
param([switch]$Debug, [switch]$Fresh, [int]$DebugPort = 0, [string]$Install = "$env:LOCALAPPDATA\Programs\CyberLoader", [string]$Exe = '')
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
if (-not $Exe) { $Exe = "$Install\CyberLoader.exe" }
$exe = $Exe
$py = "$Install\runtime\python.exe"
$data = "$Install\data"                     # the installed app's data folder (its mods are hardlinked into the sandbox)
$sandbox = "$data\tmp\dev-sandbox"          # same drive as the real library so hardlinks work; delete it any time
$real = "$data\library"
if (-not (Test-Path $exe)) { throw "CyberLoader is not installed at $exe" }
if ($Fresh -and (Test-Path $sandbox)) { Remove-Item $sandbox -Recurse -Force }
if (-not (Test-Path "$sandbox\data\profiles")) {
  New-Item -ItemType Directory -Force "$sandbox\game\bin\x64", "$sandbox\data" | Out-Null
  $seed = @"
import sys
sys.path.insert(0, r'$repo\engine')
from pathlib import Path
from modman.app import App, clone_tree
from modman.config import Config
real, sb = Path(r'$real'), Path(r'$sandbox')
names = [d.name for d in sorted(real.iterdir()) if d.is_dir()]
chosen = []
for n in names:                      # the first 13 mods under 80 MB, so the sandbox stays small
    size = sum(f.stat().st_size for f in (real/n).rglob('*') if f.is_file())
    if size < 80_000_000: chosen.append(n)
    if len(chosen) >= 13: break
for n in chosen: clone_tree(real/n, sb/'data'/'library'/n)
app = App(Config(game=sb/'game', data=sb/'data'))
ids = list(app.library.mods)
app.profiles.save('Empty', []); app.profiles.save('Sandbox profile', ids[:7]); app.profiles.save('Everything', ids)
app.profiles.set_order(['Empty','Sandbox profile','Everything'])
app.select_profile('Sandbox profile')
print(len(ids), 'sandbox mods')
"@
  & $py -I -c $seed
}
$env:MODMAN_GAME = "$sandbox\game"
$env:MODMAN_DATA = "$sandbox\data"
$env:CYBERLOADER_APP = "$repo\engine\run.py"
$env:CYBERLOADER_UI = "$repo\ui"
$env:CYBERLOADER_INSTANCE = '-dev'      # own single-instance lock, WebView2 profile and window position (needs 0.6.0+ launcher)
if ($Debug) { $env:CYBERLOADER_DEBUG = '1' } else { Remove-Item Env:\CYBERLOADER_DEBUG -ErrorAction SilentlyContinue }
if ($DebugPort -gt 0) { $env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS = "--remote-debugging-port=$DebugPort --remote-allow-origins=*" }
$p = Start-Process $exe -PassThru
"CyberLoader dev window started (pid $($p.Id)) on the sandbox. UI from: $repo\ui"
