"""One-time setup of the installed app (stdlib only). Safe to re-run: it never touches versions/ or current.txt.

  python tools\\setup-cyberloader.py [--dest <install folder>] [--shortcut]

Creates in --dest:
  runtime\\        a private copy of the Python that runs this script (standard library only, ~25 MB)
  CyberLoader.exe  the launcher (compiled from launcher\\CyberLoader.cs with the .NET compiler that ships with Windows)
Optionally puts a "CyberLoader" shortcut on the Desktop and in the Start menu, both pointing at CyberLoader.exe.
Versions of the app itself are installed by tools\\release.py, never by this script.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_DEST = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Programs" / "CyberLoader"
CSC = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")
SKIP_DIRS = ["site-packages", "test", "tests", "idlelib", "tkinter", "turtledemo", "__pycache__", "ensurepip",
             "pydoc_data", "Doc", "include", "libs", "Scripts", "tcl", "lib2to3", "venv"]


def run(cmd, ok=(0,), **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode not in ok:
        sys.exit(f"command failed ({r.returncode}): {' '.join(map(str, cmd))}\n{r.stdout[-800:]}\n{r.stderr[-800:]}")
    return r


def build_runtime(dest: Path) -> None:
    src = Path(sys.base_prefix)
    out = dest / "runtime"
    print(f"runtime: copying Python {sys.version.split()[0]} from {src}")
    cmd = ["robocopy", str(src), str(out), "/E", "/NFL", "/NDL", "/NJH", "/NJS", "/NP", "/XD", *SKIP_DIRS,
           "/XF", "*.pyc", "NEWS.txt", "Activate.ps1"]
    run(cmd, ok=range(0, 8))  # robocopy: 0-7 are success codes
    # prove the copy is self-contained: isolated interpreter, stdlib parts the app uses
    r = run([str(out / "python.exe"), "-I", "-c",
             "import sys, http.server, json, urllib.request, subprocess, zipfile, tarfile, ctypes, ssl, sqlite3, uuid;"
             "print(sys.prefix)"])
    prefix = r.stdout.strip()
    if Path(prefix).resolve() != out.resolve():
        sys.exit(f"runtime is not self-contained: sys.prefix is {prefix}")
    # the check above made Python write compiled .pyc files that contain this build machine's folder names: remove them
    for d in list(out.rglob("__pycache__")):
        shutil.rmtree(d, ignore_errors=True)
    size = sum(f.stat().st_size for f in out.rglob("*") if f.is_file()) / 1e6
    print(f"runtime: OK, self-contained ({size:.0f} MB)")


def verify_vendor() -> Path:
    """The WebView2 SDK files are third-party binaries: check hashes against VENDOR.md and Microsoft's signature."""
    vdir = REPO / "launcher" / "vendor" / "webview2"
    expected = {}
    for line in (vdir / "VENDOR.md").read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) == 3 and re.fullmatch(r"[0-9A-F]{64}", parts[0]):
            expected[parts[2]] = parts[0]
    if len(expected) != 3:
        sys.exit("launcher/vendor/webview2/VENDOR.md does not list the three files")
    import hashlib
    for name, want in expected.items():
        got = hashlib.sha256((vdir / name).read_bytes()).hexdigest().upper()
        if got != want:
            sys.exit(f"{name} does not match the hash in VENDOR.md; refusing to use it")
        sig = run(["powershell", "-NoProfile", "-Command",
                   f"$s=Get-AuthenticodeSignature '{vdir / name}'; \"$($s.Status)|$($s.SignerCertificate.Subject)\""]).stdout.strip()
        if not sig.startswith("Valid|") or "CN=Microsoft Corporation" not in sig:
            sys.exit(f"{name}: signature check failed ({sig})")
    print("vendor: WebView2 SDK files match VENDOR.md and are signed by Microsoft Corporation")
    return vdir


def build_icon_and_exe(dest: Path) -> Path:
    ico = REPO / "launcher" / "cyberloader.ico"
    run([sys.executable, "-I", str(REPO / "launcher" / "make_icon.py"), str(ico)])
    vdir = verify_vendor()
    exe = dest / "CyberLoader.exe"
    if not CSC.exists():
        sys.exit(f"C# compiler not found at {CSC}")
    core, forms = vdir / "Microsoft.Web.WebView2.Core.dll", vdir / "Microsoft.Web.WebView2.WinForms.dll"
    run([str(CSC), "/nologo", "/target:winexe", "/platform:x64", f"/out:{exe}", f"/win32icon:{ico}",
         f"/resource:{REPO / 'launcher' / 'host.js'},host.js", f"/resource:{ico},cyberloader.ico",
         f"/r:{core}", f"/r:{forms}", "/r:System.Windows.Forms.dll", "/r:System.Drawing.dll", "/r:System.Web.Extensions.dll",
         str(REPO / "launcher" / "CyberLoader.cs")])
    for f in (core, forms, vdir / "WebView2Loader.dll"):
        shutil.copy2(f, dest / f.name)
    print(f"launcher: built {exe} (+ WebView2 SDK files)")
    return exe


def make_shortcut(exe: Path) -> None:
    """Desktop shortcut and Start menu entry, both called "Cyber Loader" and pointing at CyberLoader.exe.
    Earlier names ("CyberLoader", "Cyberpunk Mods") are removed if they point at this exe."""
    ps = (
        "$w=New-Object -ComObject WScript.Shell;"
        "foreach($d in @([Environment]::GetFolderPath('Desktop'),[Environment]::GetFolderPath('Programs'))){"
        "foreach($n in @('Cyberpunk Mods.lnk','CyberLoader.lnk')){$old=\"$d\\$n\"; if(Test-Path $old){ if($w.CreateShortcut($old).TargetPath -like '*CyberLoader.exe'){ Remove-Item $old } }};"
        "$s=$w.CreateShortcut(\"$d\\Cyber Loader.lnk\");"
        f"$s.TargetPath='{exe}';$s.WorkingDirectory='{exe.parent}';$s.IconLocation='{exe},0';"
        "$s.Description='CyberLoader: Cyberpunk 2077 mod manager';$s.Save();Write-Output \"$d\\Cyber Loader.lnk\"}"
    )
    r = run(["powershell", "-NoProfile", "-Command", ps])
    for line in r.stdout.strip().splitlines():
        print(f"shortcut: {line}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dest", default=str(DEFAULT_DEST))
    ap.add_argument("--shortcut", action="store_true", help="also create the Desktop shortcut")
    a = ap.parse_args()
    dest = Path(a.dest)
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "versions").mkdir(exist_ok=True)
    build_runtime(dest)
    exe = build_icon_and_exe(dest)
    if a.shortcut:
        make_shortcut(exe)
    (dest / "README.txt").write_text(
        "CyberLoader - installed by tools\\setup-cyberloader.py from the CyberLoader source folder\n"
        "runtime\\       private Python (do not edit)\n"
        "versions\\      every installed release, kept for rollback\n"
        "current.txt    the active version; edit it (or run tools\\release.py --use <version>) to roll back\n"
        "releases.log   append-only history of installs and switches\n"
        "Your data (library, profiles, logs) lives in the data\\ folder here and is not touched by upgrades.\n",
        encoding="utf-8")
    print("setup done. Install a version with: python tools\\release.py")


if __name__ == "__main__":
    main()
