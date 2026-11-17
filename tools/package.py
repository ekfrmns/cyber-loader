"""Build the shareable installer: dist\\CyberLoader-Setup-<version>.exe (stdlib only; needs Python, the C# compiler that
ships with Windows, and a 7-Zip install on THIS machine to copy the optional component from).

  python tools\\package.py            full build from main (clean tree, tests pass, CHANGELOG section, tags v<version>)
  python tools\\package.py --test     quick test build from the working tree (no checks, no tag)

The installer carries: the launcher exe + WebView2 DLLs, a private Python runtime, the committed engine/ui for the
current version, licences, and (as an optional component) 7z.exe/7z.dll. Nothing about this computer goes in.
"""
import argparse
import hashlib
import importlib.util
import io
import json
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DIST = REPO / "dist"
CSC = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")
SEVEN_ZIP_DIRS = [Path(r"C:\Program Files\7-Zip"), Path(r"C:\Program Files (x86)\7-Zip")]
PACKAGE = ["engine/modman", "engine/run.py", "ui"]
EXCLUDE_PREFIX = ("ui/design-system/",)


def git(*args, check=True):
    r = subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        sys.exit(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout.strip()


def load_setup_module():
    spec = importlib.util.spec_from_file_location("setup_cyberloader", REPO / "tools" / "setup-cyberloader.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def release_notes(version: str, digest: str, size_mb: float, is_test: bool) -> str:
    """RELEASE-NOTES.md for dist/<version>/: what changed since the previous version (from CHANGELOG.md) plus the checksum."""
    text = (REPO / "CHANGELOG.md").read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    sections = re.findall(r"^## (\d+\.\d+\.\d+)[^\n]*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    versions = [v for v, _ in sections]
    body = dict(sections).get(version, "(no CHANGELOG section for this version)").strip()
    prev = versions[versions.index(version) + 1] if version in versions and versions.index(version) + 1 < len(versions) else None
    head = f"# Cyber Loader {version}\n\n"
    if is_test:
        head += "**Quick test build, not a release. Do not share.**\n\n"
    head += f"Built {time.strftime('%Y-%m-%d')}. Installer: `CyberLoader-Setup-{version}.exe` ({size_mb:.1f} MB).\n"
    head += f"SHA-256: `{digest}`\n\n"
    head += f"## What changed since {prev}\n\n" if prev else "## What is in this version\n\n"
    return head + body + "\n"


def read_version() -> str:
    m = re.search(r'__version__\s*=\s*"(\d+\.\d+\.\d+)"', (REPO / "engine" / "modman" / "__init__.py").read_text())
    if not m:
        sys.exit("cannot read __version__")
    return m.group(1)


def export_version(version: str, dest: Path, ref: str) -> int:
    tar = subprocess.run(["git", "-C", str(REPO), "archive", "--format=tar", ref, *PACKAGE], capture_output=True)
    if tar.returncode != 0:
        sys.exit("git archive failed: " + tar.stderr.decode(errors="replace"))
    dest.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(tar.stdout)) as tf:
        tf.extractall(dest, members=[m for m in tf.getmembers() if not m.name.startswith(EXCLUDE_PREFIX)], filter="data")
    files = {str(p.relative_to(dest)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in sorted(dest.rglob("*")) if p.is_file()}
    (dest / "manifest.json").write_text(json.dumps(
        {"version": version, "commit": git("rev-parse", ref), "built": time.strftime("%Y-%m-%d %H:%M:%S"), "files": files}, indent=1),
        encoding="utf-8")
    return len(files)


def zip_dir(src: Path, out: Path) -> None:
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in sorted(src.rglob("*")):
            if p.is_file():
                z.write(p, str(p.relative_to(src)).replace("\\", "/"))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--test", action="store_true", help="build from the working tree without the release checks")
    a = ap.parse_args()
    version = read_version()
    ref = "HEAD"

    if not a.test:
        if git("rev-parse", "--abbrev-ref", "HEAD") != "main":
            sys.exit("package from main (or use --test)")
        if git("status", "--porcelain"):
            sys.exit("working tree is not clean")
        if f"## {version}" not in (REPO / "CHANGELOG.md").read_text(encoding="utf-8"):
            sys.exit(f"CHANGELOG.md has no '## {version}' section")
    print("running tests ...")
    t = subprocess.run([sys.executable, "-I", "-m", "unittest", "discover", "-s", str(REPO / "engine" / "tests")],
                       capture_output=True, text=True, cwd=REPO / "engine")
    if t.returncode != 0:
        sys.exit("tests failed:\n" + (t.stderr or t.stdout)[-1500:])
    print("tests passed")

    seven = next((d for d in SEVEN_ZIP_DIRS if (d / "7z.exe").exists() and (d / "7z.dll").exists() and (d / "License.txt").exists()), None)
    if not seven:
        sys.exit("7-Zip is not installed on this machine; it is copied into the installer as the optional component")

    work = Path(tempfile.mkdtemp(prefix="cyberloader-build-"))   # scratch space, removed when the build ends
    stage = work / "stage"
    stage.mkdir(parents=True)

    setup = load_setup_module()
    setup.build_runtime(stage)                 # private Python (stdlib only)
    setup.build_icon_and_exe(stage)            # CyberLoader.exe + WebView2 DLLs (signature/hash checked)
    n = export_version(version, stage / "versions" / version, ref)
    print(f"app files: {n} (version {version})")
    (stage / "version.txt").write_text(version, encoding="utf-8")
    shutil.copy2(REPO / "installer" / "README.txt", stage / "README.txt")
    lic = stage / "LICENSES"
    lic.mkdir()
    shutil.copy2(REPO / "installer" / "THIRD_PARTY.txt", lic / "THIRD_PARTY.txt")
    shutil.copy2(REPO / "launcher" / "vendor" / "webview2" / "LICENSE.txt", lic / "WebView2-LICENSE.txt")

    sz = work / "sevenzip"
    (sz / "tools" / "7z").mkdir(parents=True)
    for f in ("7z.exe", "7z.dll", "License.txt"):
        shutil.copy2(seven / f, sz / "tools" / "7z" / f)

    zip_dir(stage, work / "payload.zip")
    zip_dir(sz, work / "sevenzip.zip")
    outdir = DIST / (version + ("-test" if a.test else ""))      # dist/<version>/ holds that version's installer, checksum and notes
    outdir.mkdir(parents=True, exist_ok=True)
    out = outdir / f"CyberLoader-Setup-{version}.exe"
    ico = REPO / "launcher" / "cyberloader.ico"
    r = subprocess.run([str(CSC), "/nologo", "/target:winexe", f"/out:{out}", f"/win32icon:{ico}",
                        f"/resource:{work / 'payload.zip'},payload.zip", f"/resource:{work / 'sevenzip.zip'},sevenzip.zip",
                        f"/resource:{ico},cyberloader.ico",
                        "/r:System.Windows.Forms.dll", "/r:System.Drawing.dll", "/r:System.IO.Compression.dll",
                        "/r:System.IO.Compression.FileSystem.dll", str(REPO / "installer" / "Setup.cs")],
                       capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("compile failed:\n" + r.stdout[-2000:] + r.stderr[-800:])
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    (outdir / (out.name + ".sha256")).write_text(f"{digest}  {out.name}\n")
    (outdir / "RELEASE-NOTES.md").write_text(release_notes(version, digest, out.stat().st_size / 1e6, a.test), encoding="utf-8")
    readme = DIST / "README.txt"
    if not readme.exists():
        readme.write_text("One folder per version. Each holds the installer (CyberLoader-Setup-<version>.exe), its .sha256 checksum\n"
                          "and RELEASE-NOTES.md (what changed since the previous version). Send friends the .exe from the newest\n"
                          "folder. Folders ending in -test are quick test builds, never share those. Made by tools\\package.py.\n", encoding="utf-8")
    shutil.rmtree(work, ignore_errors=True)
    print(f"built {out}  ({out.stat().st_size / 1e6:.1f} MB)\nsha256 {digest}")
    if not a.test and not git("tag", "--list", f"v{version}"):
        git("tag", "-a", f"v{version}", "-m", f"CyberLoader {version}")
        print(f"tagged v{version}")


if __name__ == "__main__":
    main()
