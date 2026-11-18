<#
  Builds the optional save transfer add-on (addons\savetool) and installs it into a Cyber Loader data folder.

  The add-on is built on the MIT-licensed CP2077SaveEditor (CyberCAT-SimpleGUI by Deweh and contributors,
  https://github.com/Deweh/CyberCAT-SimpleGUI). Download its zip yourself, unzip it, and pass that folder as -EditorDir.
  Needs the .NET 10 SDK to build and the .NET 10 Desktop Runtime to run.

  Usage:
    powershell -File tools\build-savetool.ps1 -EditorDir "<unzipped editor folder>" -Data "<Cyber Loader data folder>"

  It only writes to <Data>\addons\savetool (and a temp build folder). Nothing else is touched.
#>
param(
  [Parameter(Mandatory = $true)][string]$EditorDir,
  [Parameter(Mandatory = $true)][string]$Data
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path (Join-Path $EditorDir "CP2077SaveEditor.dll"))) { throw "CP2077SaveEditor.dll not found in $EditorDir" }
$src = Join-Path $root "addons\savetool"
$build = Join-Path ([IO.Path]::GetTempPath()) ("savetool-build-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
try {
  dotnet build $src -c Release -o $build -p:EditorDir="$EditorDir" --nologo -v q
  if ($LASTEXITCODE -ne 0) { throw "build failed" }
  $dest = Join-Path $Data "addons\savetool"
  New-Item -ItemType Directory -Force $dest | Out-Null
  foreach ($f in "savetool.exe", "savetool.dll", "savetool.deps.json", "savetool.runtimeconfig.json") {
    if (Test-Path (Join-Path $build $f)) { Copy-Item (Join-Path $build $f) $dest -Force }
  }
  $ed = Join-Path $dest "editor"
  New-Item -ItemType Directory -Force $ed | Out-Null
  Copy-Item (Join-Path $EditorDir "*") $ed -Recurse -Force
  Write-Output "Installed save transfer add-on to $dest"
} finally {
  if (Test-Path $build) { Remove-Item $build -Recurse -Force -ErrorAction SilentlyContinue }
}
